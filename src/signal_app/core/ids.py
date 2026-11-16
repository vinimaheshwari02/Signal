"""Idempotency key and feedback id (see ADR 0002)."""
import hashlib
import json


def canonical_hash(payload: object) -> str:
    """Same content -> same hash, whatever the key order or spacing."""
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode()).hexdigest()


def idempotency_key(tenant: str, channel: str, source_id: str | None,
                    header_key: str | None, payload: object) -> str:
    """Best identity first: source id, then the sender's header, then a hash of the payload."""
    if source_id:
        part = f"src:{source_id}"
    elif header_key:
        part = f"hdr:{header_key}"
    else:
        part = f"hash:{canonical_hash(payload)}"
    return hashlib.sha256(f"{tenant}|{channel}|{part}".encode()).hexdigest()


def feedback_id(key: str) -> str:
    """The id we give back to the sender: "fb_" plus the first 32 characters of the key, so the
    same item always gets the same id."""
    return "fb_" + key[:32]


def hash_customer(tenant: str, customer_ref: str, salt: str) -> str:
    """A customer reference we can store: the same customer gives the same value, but the real
    reference cannot be read back. The secret salt stops guessing."""
    return hashlib.sha256(f"{salt}|{tenant}|{customer_ref}".encode()).hexdigest()[:24]


def hash_api_key(api_key: str) -> str:
    """Only this hash of an API key is stored, never the key itself."""
    return hashlib.sha256(api_key.encode()).hexdigest()
