"""Kafka adapters: the publisher used by the API and the consumer loop used by the worker."""
import json
import logging
from typing import Callable

from confluent_kafka import Consumer, KafkaException, Producer

from ..core.errors import PublishError
from ..shared import config

log = logging.getLogger("signal.kafka")


class KafkaPublisher:
    def __init__(self, bootstrap: str | None = None, topic: str | None = None):
        self.bootstrap = bootstrap or config.KAFKA_BOOTSTRAP
        self.topic = topic or config.TOPIC_RAW
        self._producer: Producer | None = None

    def _get(self) -> Producer:
        if self._producer is None:
            self._producer = Producer({"bootstrap.servers": self.bootstrap, "acks": "all",
                                       "enable.idempotence": True})
        return self._producer

    def publish(self, message: dict) -> None:
        try:
            errors = []
            self._get().produce(self.topic, key=message["feedback_id"], value=json.dumps(message),
                                on_delivery=lambda e, _m: e and errors.append(e))
            self._get().flush(5)
            if errors or self._get().len() > 0:
                raise KafkaException(errors[0] if errors else "delivery timeout")
        except KafkaException as e:
            log.exception("kafka publish failed")
            raise PublishError(str(e)) from e


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
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            log.warning("kafka error: %s", msg.error())
            continue
        try:
            handle(msg.value())
        except (ValueError, KeyError, TypeError):
            log.exception("skipping unreadable message at offset %s", msg.offset())  # TODO: dead-letter topic
        except Exception:
            log.exception("database problem, will retry")
            consumer.seek(msg.topic_partition())  # re-read the same message; do not commit
            continue
        consumer.commit(msg)
