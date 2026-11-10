"""Business errors. Adapters decide how each one is shown (HTTP status, log line, ...)."""


class Unauthorized(Exception):
    """Missing or unknown API key."""


class Forbidden(Exception):
    """The API key is valid but not for this channel."""


class UnknownChannel(Exception):
    """No normaliser exists for the channel."""


class PayloadTooLarge(Exception):
    """Request body is over the size limit."""


class BadJson(Exception):
    """Request body is not valid JSON."""


class Rejected(Exception):
    """The normaliser could not use the payload."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class PublishError(Exception):
    """The message could not be delivered to the log."""
