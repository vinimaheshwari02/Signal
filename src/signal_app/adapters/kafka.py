"""Kafka adapters: the publisher used by the API and the consumer loop used by the worker."""
import json
import logging
from typing import Callable

from confluent_kafka import Consumer, KafkaException, Producer, TopicPartition

from ..core.errors import PublishError
from ..shared import config

log = logging.getLogger("signal.kafka")


class KafkaPublisher:
    def __init__(self, bootstrap: str | None = None, topic: str | None = None):
        self.bootstrap = bootstrap or config.KAFKA_BOOTSTRAP
        self.topic = topic or config.TOPIC_RAW
        self._producer: Producer | None = None

    def _producer_or_create(self) -> Producer:
        """The producer is created on first use, so starting the API does not need Kafka."""
        if self._producer is None:
            self._producer = Producer({"bootstrap.servers": self.bootstrap, "acks": "all",
                                       "enable.idempotence": True})
        return self._producer

    def publish(self, message: dict) -> None:
        """Send one message and wait until Kafka confirms it. Raises PublishError otherwise."""
        errors = []

        def remember_error(error, _message):
            # Kafka calls this when the message is delivered (error is None) or has failed.
            if error is not None:
                errors.append(error)

        try:
            producer = self._producer_or_create()
            producer.produce(self.topic, key=message["feedback_id"], value=json.dumps(message),
                             on_delivery=remember_error)
            # Wait up to 5 seconds for the confirmation. flush() returns how many messages are
            # still waiting to be sent.
            still_waiting = producer.flush(5)
            if errors:
                raise KafkaException(errors[0])
            if still_waiting > 0:  # no confirmation in time (Kafka down, or the topic is missing)
                raise KafkaException("delivery timeout")
        except KafkaException as error:
            log.exception("kafka publish failed")
            raise PublishError(str(error)) from error


def consume_forever(handle: Callable[[bytes], None], bootstrap: str | None = None,
                    topic: str | None = None, group_id: str = "signal-workers") -> None:
    """Poll and hand each message value to `handle`.

    handle raising ValueError/KeyError/TypeError means the message is unreadable: skip it.
    Any other exception means a temporary problem: re-read the same message, do not commit.
    """
    consumer = Consumer({"bootstrap.servers": bootstrap or config.KAFKA_BOOTSTRAP, "group.id": group_id,
                         "auto.offset.reset": "earliest", "enable.auto.commit": False})
    consumer.subscribe([topic or config.TOPIC_RAW])
    while True:
        message = consumer.poll(1.0)
        if message is None:  # nothing new in the last second
            continue
        if message.error():
            log.warning("kafka error: %s", message.error())
            continue
        handle_one(consumer, message, handle)


def handle_one(consumer, message, handle: Callable[[bytes], None]) -> None:
    """Process one message, then either commit it (done or unreadable) or go back to it (retry)."""
    try:
        handle(message.value())
    except (ValueError, KeyError, TypeError):
        # Unreadable: retrying cannot help, so log it and move on.  TODO: dead-letter topic
        log.exception("skipping unreadable message at offset %s", message.offset())
    except Exception:
        # A temporary problem such as the database being down: do not commit, and move the
        # consumer back to this message so the next poll returns it again.
        log.exception("database problem, will retry")
        same_message = TopicPartition(message.topic(), message.partition(), message.offset())
        consumer.seek(same_message)
        return
    consumer.commit(message)
