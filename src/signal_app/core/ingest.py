"""Use case: accept one piece of feedback (see ADR 0002: publish first, then remember the key)."""
import json

from .auth import authenticate
from .errors import BadJson, Forbidden, PayloadTooLarge, Rejected, UnknownChannel
from .ids import feedback_id, idempotency_key
from .models import IngestResult
from .normalise import NORMALISERS
from .ports import ApiKeyDirectory, Clock, FeedbackPublisher, KeyStore


class IngestFeedback:
    def __init__(self, publisher: FeedbackPublisher, key_store: KeyStore, keys: ApiKeyDirectory,
                 clock: Clock, salt: str, max_body_bytes: int):
        self.publisher = publisher
        self.key_store = key_store
        self.keys = keys
        self.clock = clock
        self.salt = salt
        self.max_body_bytes = max_body_bytes

    def run(self, channel: str, api_key: str | None, raw_body: bytes,
            idempotency_header: str | None) -> IngestResult:
        if channel not in NORMALISERS:
            raise UnknownChannel(f"unknown channel '{channel}'")
        tenant, key_channel = authenticate(self.keys, api_key)
        if key_channel != channel:
            raise Forbidden("this API key is not valid for this channel")

        if len(raw_body) > self.max_body_bytes:
            raise PayloadTooLarge("body too large")
        try:
            # strict=False: real sources sometimes put raw line breaks inside strings.
            payload = json.loads(raw_body, strict=False)
        except ValueError:
            raise BadJson("body is not valid JSON")

        received_at = self.clock.now()
        # Rejected (422) propagates as is.
        item = NORMALISERS[channel](tenant, payload, received_at, self.salt)

        key = idempotency_key(tenant, channel, item["source_id"], idempotency_header, payload)
        fid = feedback_id(key)

        seen = self.key_store.get(key)
        if seen:
            return IngestResult(seen, "duplicate")

        # Publish first, then remember the key: a failure in between can cause a duplicate, never a loss.
        message = {"feedback_id": fid, "tenant_id": tenant, "channel": channel,
                   "received_at": received_at.isoformat(), **item}
        self.publisher.publish(message)  # PublishError propagates; the key is not saved
        self.key_store.save(key, tenant, fid)
        return IngestResult(fid, "accepted")
