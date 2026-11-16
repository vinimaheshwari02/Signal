"""Use case: accept one piece of feedback (see ADR 0002: publish first, then remember the key)."""
import json

from .auth import authenticate
from .errors import BadJson, Forbidden, PayloadTooLarge, UnknownChannel
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
        normalise = NORMALISERS[channel]
        # An unusable payload raises Rejected here, which the API shows as 422.
        item = normalise(tenant=tenant, payload=payload, received_at=received_at, salt=self.salt)

        key = idempotency_key(tenant=tenant, channel=channel, source_id=item["source_id"],
                              header_key=idempotency_header, payload=payload)
        new_feedback_id = feedback_id(key)

        existing_feedback_id = self.key_store.get(key)
        if existing_feedback_id:
            return IngestResult(feedback_id=existing_feedback_id, status="duplicate")

        # Publish first, then remember the key: a failure in between can cause a duplicate, never a loss.
        message = {"feedback_id": new_feedback_id, "tenant_id": tenant, "channel": channel,
                   "received_at": received_at.isoformat()}
        message.update(item)  # add the normalised fields: text, created_at, market, ...
        self.publisher.publish(message)  # a failure raises PublishError; the key is then not saved
        self.key_store.save(key, tenant, new_feedback_id)
        return IngestResult(feedback_id=new_feedback_id, status="accepted")
