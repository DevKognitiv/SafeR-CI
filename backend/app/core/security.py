"""
SafeR CI — API security helpers

Pragmatic, immediate protection for the emergency API. There is no user/login
system yet, so we use a shared bearer token for the mutating/PII endpoints and
an HMAC-SHA256 signature for the Home Assistant webhook. Both comparisons are
constant-time. These guards fail closed when their secret is unconfigured.
"""
import hmac
from hashlib import sha256

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)


def require_api_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> None:
    """
    Verify the caller's bearer token against ``settings.SAFER_API_TOKEN``.

    Fails closed with 503 when no token is configured, and 401 on a missing or
    mismatched token. Uses a constant-time comparison to avoid timing attacks.
    """
    expected = settings.SAFER_API_TOKEN
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured",
        )
    if credentials is None or not hmac.compare_digest(
        credentials.credentials, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_ha_signature(
    request: Request,
    x_hub_signature_256: str = Header(default=None, alias="X-Hub-Signature-256"),
) -> None:
    """
    Verify the HMAC-SHA256 signature of the raw request body against
    ``settings.HUB_WEBHOOK_SECRET``.

    The signature header value must be ``sha256=<hexdigest>``. Fails closed with
    503 when no secret is configured, 401 when the signature header is missing,
    and 403 on mismatch. FastAPI caches the body, so parsing the Pydantic model
    afterwards still works.
    """
    secret = settings.HUB_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret is not configured",
        )
    if not x_hub_signature_256:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing webhook signature",
        )
    body = await request.body()
    expected = "sha256=" + hmac.new(secret.encode(), body, sha256).hexdigest()
    if not hmac.compare_digest(x_hub_signature_256, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature",
        )
