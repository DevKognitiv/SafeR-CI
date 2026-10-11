"""In-process rate limiting and login lockout for the hub's ``/auth`` routes.

Sliding-window counters keyed by client IP and by normalised account e-mail (or user id), plus a consecutive
failure counter per account that locks it for ``HUB_LOGIN_LOCKOUT_SECONDS``. Over-limit requests answer
``429`` and locked accounts ``423``, both with a ``Retry-After`` header and a JSON ``detail`` carrying a ``code``
(``rate_limited`` / ``account_locked``) the app can map to its own strings.

One :class:`RateLimiter` lives on the ``HubRuntime`` (fresh per runtime, so tests are isolated); its clock is
injectable (``limiter.clock``) and ``reset()`` clears every counter. Expired entries are pruned on every access
and swept periodically so memory stays bounded by the number of distinct clients active within a window.

Deployment note: the counters are per process. Raspberry Pi hubs run a single uvicorn worker, which is what this
module is written for; a multi-worker or multi-host deployment needs a shared store (Redis) behind the same
interface before the limits mean anything globally.
"""
from __future__ import annotations

import ipaddress
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Optional, Tuple

from fastapi import HTTPException, Request, status

__all__ = [
    "RateLimiter", "AuthThrottle", "client_ip", "rate_limited", "account_locked", "RATE_LIMITED", "ACCOUNT_LOCKED",
]

RATE_LIMITED = "rate_limited"
ACCOUNT_LOCKED = "account_locked"
RATE_LIMITED_MESSAGE = "Trop de tentatives, réessayez dans quelques instants"
ACCOUNT_LOCKED_MESSAGE = "Compte temporairement verrouillé après plusieurs échecs de connexion"
UNKNOWN_CLIENT = "unknown"
MAX_KEY_LENGTH = 128  # keys come from request data (e-mails, forwarded IPs): cap them so they cannot bloat memory
SWEEP_INTERVAL = 60.0
MINUTE = 60.0
HOUR = 3600.0


@dataclass
class _Window:
    """Timestamps of the accepted hits of one key within ``window`` seconds."""

    window: float
    hits: Deque[float] = field(default_factory=deque)

    def prune(self, now: float) -> None:
        """Drop hits older than the window."""
        cutoff = now - self.window
        while self.hits and self.hits[0] <= cutoff:
            self.hits.popleft()

    def expired(self, now: float) -> bool:
        """True when nothing in the window can still count."""
        return not self.hits or self.hits[-1] + self.window <= now


def _normalise(key: Any) -> str:
    return str(key or "").strip().lower()[:MAX_KEY_LENGTH]


class RateLimiter:
    """Sliding-window limiter + lockout registry. Not thread-safe: it belongs to the event loop thread."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._windows: Dict[Tuple[str, str], _Window] = {}
        self._failures: Dict[str, _Window] = {}
        self._locks: Dict[str, float] = {}  # key -> locked until (clock seconds)
        self._last_sweep: Optional[float] = None

    # ------------------------------------------------------------------ housekeeping
    def reset(self) -> None:
        """Forget every counter and lock."""
        self._windows.clear()
        self._failures.clear()
        self._locks.clear()
        self._last_sweep = None

    @property
    def tracked(self) -> int:
        """Number of keys currently held (tests assert pruning keeps it bounded)."""
        return len(self._windows) + len(self._failures) + len(self._locks)

    def _sweep(self, now: float) -> None:
        """Drop keys whose entries all expired (runs at most every ``SWEEP_INTERVAL`` seconds)."""
        if self._last_sweep is not None and now - self._last_sweep < SWEEP_INTERVAL:
            return
        self._last_sweep = now
        for key in [k for k, window in self._windows.items() if window.expired(now)]:
            del self._windows[key]
        for key in [k for k, window in self._failures.items() if window.expired(now)]:
            del self._failures[key]
        for key in [k for k, until in self._locks.items() if until <= now]:
            del self._locks[key]

    # ------------------------------------------------------------------ sliding windows
    def hit(self, bucket: str, key: Any, limit: int, window: float) -> Optional[float]:
        """Count one request of ``key`` in ``bucket``.

        Returns ``None`` when the request is allowed (and counted), or the seconds to wait when ``limit`` requests
        were already accepted within ``window`` seconds (the refused request is not counted, so a client that
        backs off recovers as soon as the oldest hit leaves the window). ``limit <= 0`` disables the bucket.
        """
        now = self.clock()
        self._sweep(now)
        if limit <= 0:
            return None
        slot = (bucket, _normalise(key))
        entry = self._windows.get(slot)
        if entry is None or entry.window != window:
            entry = self._windows[slot] = _Window(window)
        entry.prune(now)
        if len(entry.hits) >= limit:
            return max(entry.hits[0] + window - now, 0.0)
        entry.hits.append(now)
        return None

    # ------------------------------------------------------------------ lockout
    def locked_for(self, key: Any) -> Optional[float]:
        """Seconds left on the lock of ``key``, or ``None`` when it is not locked."""
        now = self.clock()
        slot = _normalise(key)
        until = self._locks.get(slot)
        if until is None:
            return None
        if until <= now:
            del self._locks[slot]
            return None
        return until - now

    def record_failure(self, key: Any, threshold: int, window: float, lock_seconds: float) -> Optional[float]:
        """Count a failed login for ``key``; returns the lock duration once ``threshold`` failures happened in ``window``."""
        now = self.clock()
        if threshold <= 0 or lock_seconds <= 0:
            return None
        slot = _normalise(key)
        entry = self._failures.get(slot)
        if entry is None or entry.window != window:
            entry = self._failures[slot] = _Window(window)
        entry.prune(now)
        entry.hits.append(now)
        if len(entry.hits) < threshold:
            return None
        self._locks[slot] = now + lock_seconds
        del self._failures[slot]  # the next failure after the lock expires starts a new series
        return lock_seconds

    def record_success(self, key: Any) -> None:
        """A successful login resets the consecutive failure counter (and any expired lock) of ``key``."""
        slot = _normalise(key)
        self._failures.pop(slot, None)
        if self._locks.get(slot, 0.0) <= self.clock():
            self._locks.pop(slot, None)


# ---------------------------------------------------------------------- HTTP helpers
def _retry_after(seconds: float) -> int:
    return max(1, math.ceil(seconds))


def rate_limited(retry_after: float) -> HTTPException:
    """429 with ``Retry-After`` and ``detail.code == "rate_limited"``."""
    wait = _retry_after(retry_after)
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"code": RATE_LIMITED, "message": RATE_LIMITED_MESSAGE, "retry_after": wait},
        headers={"Retry-After": str(wait)},
    )


def account_locked(retry_after: float) -> HTTPException:
    """423 with ``Retry-After`` and ``detail.code == "account_locked"``."""
    wait = _retry_after(retry_after)
    return HTTPException(
        status_code=status.HTTP_423_LOCKED,
        detail={"code": ACCOUNT_LOCKED, "message": ACCOUNT_LOCKED_MESSAGE, "retry_after": wait},
        headers={"Retry-After": str(wait)},
    )


def _as_ip(value: str) -> Optional[str]:
    """Canonical form of ``value`` when it is an IP address (an optional ``[v6]:port`` / ``v4:port`` is tolerated)."""
    candidate = value.strip()
    if candidate.startswith("["):
        candidate = candidate[1:].split("]", 1)[0]
    elif candidate.count(":") == 1:
        candidate = candidate.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def client_ip(request: Request, trust_proxy_headers: bool = False) -> str:
    """Peer address of the request; the *last* ``X-Forwarded-For`` entry only when a trusted proxy sets it.

    Without ``trust_proxy_headers`` the header is ignored entirely, so a client cannot spread its attempts over
    forged addresses or pin them on somebody else's. With it, the last entry is used: that is the one the proxy
    in front of the hub added for the peer it saw (nginx ``$proxy_add_x_forwarded_for`` appends it,
    ``$remote_addr`` overwrites the header with it; both leave it last), whereas the first entry is whatever the
    client sent. The entry must parse as an IP address (anything else falls back to the peer). The flag means
    "the hub is only reachable through that proxy": a client that can bypass the proxy could still forge it.
    """
    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        last = _as_ip(forwarded.rsplit(",", 1)[-1])
        if last:
            return last
    client = request.client
    if client is not None and client.host:
        return client.host
    return UNKNOWN_CLIENT


class AuthThrottle:
    """The configured ``/auth`` limits for one request (a no-op when ``HUB_RATE_LIMIT_ENABLED`` is off)."""

    def __init__(self, runtime: Any, request: Request):
        self.settings = runtime.settings
        self.limiter: RateLimiter = runtime.limiter
        self.enabled = bool(getattr(self.settings, "HUB_RATE_LIMIT_ENABLED", True))
        self.ip = client_ip(request, bool(getattr(self.settings, "HUB_TRUST_PROXY_HEADERS", False)))

    def _enforce(self, bucket: str, key: Any, limit: int, window: float) -> None:
        wait = self.limiter.hit(bucket, key, limit, window)
        if wait is not None:
            raise rate_limited(wait)

    def _lock_key(self, email: str) -> str:
        """The lock is per account (normalised e-mail), whatever the client address.

        Anyone who knows the e-mail can trigger it: a bounded, 15-minute denial surfaced with a countdown, and
        already issued tokens keep working. Scoping the lock to the client address was considered and rejected:
        on a LAN a guesser rotates addresses for free, which would raise the budget against a weak password from
        5 attempts per 15 minutes to 5 per minute (the per-account window alone).
        """
        return _normalise(email)

    def before_login(self, email: str) -> None:
        """429 over the per-IP / per-account limits, 423 while the account is locked."""
        if not self.enabled:
            return
        self._enforce("login:ip", self.ip, self.settings.HUB_LOGIN_PER_IP_PER_MINUTE, MINUTE)
        locked = self.limiter.locked_for(self._lock_key(email))
        if locked is not None:
            raise account_locked(locked)
        self._enforce("login:account", email, self.settings.HUB_LOGIN_PER_ACCOUNT_PER_MINUTE, MINUTE)

    def login_failed(self, email: str) -> None:
        """Count a failed attempt; the account locks after ``HUB_LOGIN_LOCKOUT_THRESHOLD`` consecutive failures.

        Unknown e-mails are counted exactly like existing ones so the lockout cannot be used to enumerate accounts.
        """
        if not self.enabled:
            return
        self.limiter.record_failure(
            self._lock_key(email), self.settings.HUB_LOGIN_LOCKOUT_THRESHOLD,
            float(self.settings.HUB_LOGIN_LOCKOUT_WINDOW_SECONDS), float(self.settings.HUB_LOGIN_LOCKOUT_SECONDS),
        )

    def login_succeeded(self, email: str) -> None:
        """Reset the failure counter of ``email``."""
        if self.enabled:
            self.limiter.record_success(self._lock_key(email))

    def before_register(self) -> None:
        """429 over ``HUB_REGISTER_PER_IP_PER_HOUR``."""
        if self.enabled:
            self._enforce("register:ip", self.ip, self.settings.HUB_REGISTER_PER_IP_PER_HOUR, HOUR)

    def before_push_token(self, user_id: str) -> None:
        """429 over ``HUB_PUSH_TOKEN_PER_USER_PER_MINUTE``."""
        if self.enabled:
            self._enforce("push-token:user", user_id, self.settings.HUB_PUSH_TOKEN_PER_USER_PER_MINUTE, MINUTE)
