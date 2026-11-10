"""Idempotency key and feedback id (see ADR 0002)."""
import hashlib
import json


def canonical_hash(payload: object) -> str:
    """Same content -> same hash, whatever the key order or spacing."""
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()


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
    return "fb_" + key[:32]


def hash_customer(tenant: str, customer_ref: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}|{tenant}|{customer_ref}".encode()).hexdigest()[:24]


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()
