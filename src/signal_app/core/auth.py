from .errors import Unauthorized
from .ports import ApiKeyDirectory


def authenticate(keys: ApiKeyDirectory, api_key: str | None) -> tuple[str, str]:
    """API key -> (tenant, channel). One key per tenant + channel."""
    if not api_key:
        raise Unauthorized("missing X-Api-Key")
    found = keys.lookup(api_key)
    if not found:
        raise Unauthorized("invalid API key")
    return found
