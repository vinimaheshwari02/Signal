"""The API's Kafka publisher: confirmed, failed, or timed out. No broker needed."""
from unittest.mock import create_autospec

import pytest
from confluent_kafka import KafkaError, Producer

from signal_app.adapters.kafka import KafkaPublisher
from signal_app.core.errors import PublishError

MESSAGE = {"feedback_id": "fb_1", "text": "hi"}


def publisher_with(producer):
    publisher = KafkaPublisher(bootstrap="unused:9092", topic="feedback.raw")
    publisher._producer = producer  # skip creating a real connection
    return publisher


def fake_producer(still_waiting=0, delivery_error=None):
    # autospec: calling a method the real Producer does not have fails the test.
    producer = create_autospec(Producer, instance=True)

    def produce(topic, key, value, on_delivery):
        on_delivery(delivery_error, None)  # Kafka reports the result through this callback

    producer.produce.side_effect = produce
    producer.flush.return_value = still_waiting
    return producer


def test_a_confirmed_message_is_published():
    producer = fake_producer()
    publisher_with(producer).publish(MESSAGE)
    args, kwargs = producer.produce.call_args
    assert args == ("feedback.raw",) and kwargs["key"] == "fb_1"


def test_a_delivery_error_becomes_publish_error():
    producer = fake_producer(delivery_error=KafkaError(KafkaError._MSG_TIMED_OUT))
    with pytest.raises(PublishError):
        publisher_with(producer).publish(MESSAGE)


def test_no_confirmation_in_time_becomes_publish_error():
    producer = create_autospec(Producer, instance=True)
    producer.flush.return_value = 1  # one message still waiting after 5 seconds
    with pytest.raises(PublishError):
        publisher_with(producer).publish(MESSAGE)
