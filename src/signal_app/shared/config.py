import os

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:19092")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://signal_api:signal_api@localhost:5432/signal")
WORKER_DATABASE_URL = os.getenv("WORKER_DATABASE_URL", "postgresql://signal:signal@localhost:5432/signal")
TOPIC_RAW = os.getenv("TOPIC_RAW", "feedback.raw")
# Salt for hashing customer references. Override in any real deployment.
CUSTOMER_SALT = os.getenv("CUSTOMER_SALT", "dev-only-salt")
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(64 * 1024)))
# Themes (ADR 0007). AS_OF empty means "now"; a date such as 2026-10-19 ranks the week before it,
# which is what the data pack needs (its feedback ends on 2026-10-18).
AS_OF = os.getenv("AS_OF", "")
THEME_INTERVAL_SECONDS = int(os.getenv("THEME_INTERVAL_SECONDS", "300"))
# Alarms (ADR 0008): how often the scheduler checks alarms 1 and 2.
ALARM_INTERVAL_SECONDS = int(os.getenv("ALARM_INTERVAL_SECONDS", "60"))
# Database connections per process. The API serves requests on worker threads; each one holds a
# connection while it waits, so more threads than connections means waiting for a connection.
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
# The worker and the scheduler answer GET /metrics on this port (the API uses its own port).
METRICS_PORT = int(os.getenv("METRICS_PORT", "9100"))
