"""Worker: reads the raw feedback topic, labels each item and stores it in PostgreSQL.

Themes and alarms plug in later. Re-delivery is safe: saving is idempotent.
"""
import logging

from ..adapters.kafka import consume_forever
from ..adapters.postgres import PostgresFeedbackRepository
from ..core.process import ProcessFeedback
from ..shared import config

log = logging.getLogger("signal.worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    process = ProcessFeedback(PostgresFeedbackRepository(config.WORKER_DATABASE_URL))
    log.info("worker started")
    consume_forever(process.run)


if __name__ == "__main__":
    main()
