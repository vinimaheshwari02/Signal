"""Kafka adapters: the publisher used by the API and the consumer loop used by the worker."""
import json
import logging
import time
from typing import Callable

from confluent_kafka import Consumer, KafkaException, Producer, TopicPartition

from ..core.errors import PublishError
from ..shared import config
from . import metrics

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
    failures = 0  # retries in a row; reset as soon as a message goes through
    lag_checked = 0.0
    while True:
        if time.monotonic() - lag_checked >= LAG_CHECK_SECONDS:
            update_lag(consumer)
            lag_checked = time.monotonic()
        message = consumer.poll(1.0)
        if message is None:  # nothing new in the last second
            continue
        if message.error():
            log.warning("kafka error: %s", message.error())
            continue
        if handle_one(consumer, message, handle):
            failures = 0
        else:
            failures += 1
            time.sleep(retry_delay(failures))  # give the database time to come back


LAG_CHECK_SECONDS = 10


def update_lag(consumer) -> None:
    """Lag = messages in Kafka this worker has not processed yet, per partition it owns.
    For each partition: the end of the log (high watermark) minus where this worker is."""
    try:
        assigned = consumer.assignment()
        if not assigned:
            return
        committed = {p.partition: p.offset for p in consumer.committed(assigned, timeout=1.0)}
        for partition in consumer.position(assigned):
            low, high = consumer.get_watermark_offsets(partition, timeout=1.0)
            at = partition.offset
            if at < 0:  # nothing read since start-up: continue from the last commit
                at = committed.get(partition.partition, -1)
            if at < 0:  # never committed either: everything still in the log is waiting
                at = low
            metrics.WORKER_LAG.labels(str(partition.partition)).set(max(0, high - at))
    except KafkaException:
        log.warning("could not read the consumer lag", exc_info=True)


def retry_delay(failures: int) -> float:
    """Seconds to wait before retrying: 0.5, 1, 2, 4 ... and never more than 30.
    Without a pause, a database outage would make the worker retry thousands of times a second."""
    return min(30.0, 0.5 * 2 ** (failures - 1))


def handle_one(consumer, message, handle: Callable[[bytes], None]) -> bool:
    """Process one message, then either commit it (done or unreadable) or go back to it (retry).
    Returns False when it should be retried."""
    started = time.perf_counter()
    try:
        handle(message.value())
        metrics.WORKER_MESSAGES.labels("saved").inc()
        metrics.WORKER_DURATION.observe(time.perf_counter() - started)
    except (ValueError, KeyError, TypeError):
        # Unreadable: retrying cannot help, so log it and move on.  TODO: dead-letter topic
        log.exception("skipping unreadable message at offset %s", message.offset())
        metrics.WORKER_MESSAGES.labels("skipped").inc()
    except Exception:
        # A temporary problem such as the database being down: do not commit, and move the
        # consumer back to this message so the next poll returns it again.
        log.exception("database problem, will retry")
        metrics.WORKER_MESSAGES.labels("retry").inc()
        same_message = TopicPartition(message.topic(), message.partition(), message.offset())
        consumer.seek(same_message)
        return False
    consumer.commit(message)
    return True
