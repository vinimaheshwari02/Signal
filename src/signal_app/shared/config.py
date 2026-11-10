import os

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:19092")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://signal_api:signal_api@localhost:5432/signal")
WORKER_DATABASE_URL = os.getenv("WORKER_DATABASE_URL", "postgresql://signal:signal@localhost:5432/signal")
TOPIC_RAW = os.getenv("TOPIC_RAW", "feedback.raw")
# Salt for hashing customer references. Override in any real deployment.
CUSTOMER_SALT = os.getenv("CUSTOMER_SALT", "dev-only-salt")
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", str(64 * 1024)))
