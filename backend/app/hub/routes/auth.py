"""Auth routes: register / login / profile / push tokens (mounted under ``/auth`` by ``app.py``).

``POST /login``, ``POST /register`` and ``POST /push-token`` go through the runtime's rate limiter
(``ratelimit.py``): 429 ``rate_limited`` over the per-IP / per-account limits and 423 ``account_locked`` after
``HUB_LOGIN_LOCKOUT_THRESHOLD`` consecutive failed logins, both with a ``Retry-After`` header. Login failures
never reveal whether an e-mail exists: same message, same lockout rules and a password check that runs even
for unknown accounts so the response time does not differ.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from app.hub.deps import get_current_user, get_db
from app.hub.models import PushToken, User
from app.hub.ratelimit import AuthThrottle
from app.hub.runtime import get_runtime
from app.hub.schemas import LoginIn, PushTokenIn, RegisterIn, TokenOut, UserOut, UserUpdate
from app.hub.security import create_access_token, dummy_password_hash, hash_password, verify_password

logger = logging.getLogger("safer.hub.auth")

router = APIRouter()

INVALID_CREDENTIALS = "Invalid e-mail or password"
THROTTLED_RESPONSES = {
    429: {"description": "Rate limited (detail.code = rate_limited, Retry-After header)"},
}
LOGIN_RESPONSES = {
    **THROTTLED_RESPONSES,
    423: {"description": "Account locked after repeated failures (detail.code = account_locked, Retry-After header)"},
}


def token_for(user: User) -> TokenOut:
    """Issue a bearer token for ``user`` using the runtime settings."""
    settings = get_runtime().settings
    token = create_access_token(user.id, settings.SECRET_KEY, settings.HUB_TOKEN_TTL_DAYS)
    return TokenOut(token=token, user=UserOut.model_validate(user))


async def _user_count(db: AsyncSession) -> int:
    return int((await db.execute(select(count()).select_from(User))).scalar_one())


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED, responses=THROTTLED_RESPONSES)
async def register(body: RegisterIn, request: Request, db: AsyncSession = Depends(get_db)) -> TokenOut:
    """Create an account. The first user of a fresh hub becomes admin.

    409 on duplicate e-mail; 403 when ``HUB_ALLOW_OPEN_REGISTRATION`` is off and an account already exists;
    429 over ``HUB_REGISTER_PER_IP_PER_HOUR``.
    """
    runtime = get_runtime()
    AuthThrottle(runtime, request).before_register()
    settings = runtime.settings
    existing = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail already registered")
    first_user = await _user_count(db) == 0
    if not first_user and not settings.HUB_ALLOW_OPEN_REGISTRATION:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration is closed on this hub")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=(body.name or "").strip(),
        phone=body.phone,
        locale=body.locale or "fr",
        is_admin=first_user,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:  # concurrent registration with the same e-mail
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail already registered") from None
    await db.refresh(user)
    logger.info("Registered user %s (%s)%s", user.id, user.email, " as hub admin" if first_user else "")
    return token_for(user)


@router.post("/login", response_model=TokenOut, responses=LOGIN_RESPONSES)
async def login(body: LoginIn, request: Request, db: AsyncSession = Depends(get_db)) -> TokenOut:
    """Exchange e-mail + password for a bearer token (401 on bad credentials, 429 rate limited, 423 locked)."""
    throttle = AuthThrottle(get_runtime(), request)
    throttle.before_login(body.email)
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    # The hash check runs for unknown e-mails too (against a throw-away hash) so timing does not reveal accounts.
    password_hash = user.password_hash if user is not None else dummy_password_hash()
    if not verify_password(body.password, password_hash) or user is None:
        throttle.login_failed(body.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)
    throttle.login_succeeded(body.email)
    return token_for(user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    """Profile of the authenticated user."""
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_me(body: UserUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> UserOut:
    """Update profile fields (only the fields present in the body are touched)."""
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        changes["name"] = changes["name"].strip()
    for field, value in changes.items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/push-token", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, responses=THROTTLED_RESPONSES)
async def register_push_token(
    body: PushTokenIn, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    """Upsert a mobile push token (a token re-registered by another account moves to the caller); 429 over the per-user limit."""
    AuthThrottle(get_runtime(), request).before_push_token(user.id)
    existing = (await db.execute(select(PushToken).where(PushToken.token == body.token))).scalar_one_or_none()
    if existing is None:
        db.add(PushToken(user_id=user.id, platform=body.platform, token=body.token))
    else:
        existing.user_id = user.id
        existing.platform = body.platform
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/push-token/{token}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_push_token(token: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Response:
    """Forget one of the caller's push tokens (idempotent)."""
    await db.execute(delete(PushToken).where(PushToken.token == token, PushToken.user_id == user.id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
