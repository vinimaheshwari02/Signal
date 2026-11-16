"""The worker's handling of one Kafka message: commit, skip or retry. No broker needed."""
from unittest.mock import create_autospec

from confluent_kafka import Consumer, Message, TopicPartition

from signal_app.adapters.kafka import handle_one


def kafka_message():
    # autospec: calling a method the real Message does not have fails the test.
    message = create_autospec(Message, instance=True)
    message.topic.return_value = "feedback.raw"
    message.partition.return_value = 2
    message.offset.return_value = 41
    message.value.return_value = b'{"text": "hi"}'
    return message


def test_a_processed_message_is_committed():
    consumer, message, seen = create_autospec(Consumer, instance=True), kafka_message(), []
    handle_one(consumer, message, seen.append)
    assert seen == [b'{"text": "hi"}']
    consumer.commit.assert_called_once_with(message)
    consumer.seek.assert_not_called()


def test_an_unreadable_message_is_skipped_and_committed():
    consumer, message = create_autospec(Consumer, instance=True), kafka_message()

    def unreadable(_value):
        raise ValueError("not JSON")

    handle_one(consumer, message, unreadable)
    consumer.commit.assert_called_once_with(message)
    consumer.seek.assert_not_called()


def test_a_database_problem_goes_back_to_the_same_message_without_committing():
    consumer, message = create_autospec(Consumer, instance=True), kafka_message()

    def database_down(_value):
        raise RuntimeError("database is down")

    handle_one(consumer, message, database_down)   # must not raise: the worker keeps running
    consumer.commit.assert_not_called()
    (position,), _ = consumer.seek.call_args
    assert isinstance(position, TopicPartition)
    assert (position.topic, position.partition, position.offset) == ("feedback.raw", 2, 41)
