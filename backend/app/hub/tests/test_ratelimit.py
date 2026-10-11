"""Rate limiting and lockout on /auth: per-IP and per-account windows, lockout, proxy trust, no account enumeration."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

import httpx
from starlette.requests import Request

from app.hub.app import create_app
from app.hub.ratelimit import RateLimiter, client_ip
from app.hub.routes import auth as auth_routes
from app.hub.runtime import set_runtime
from app.hub.tests.conftest import PREFIX, make_settings, register_user

LOGIN = f"{PREFIX}/auth/login"
REGISTER = f"{PREFIX}/auth/register"
PUSH = f"{PREFIX}/auth/push-token"


class FakeClock:
    """Monotonic clock the tests move by hand."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        """Current fake time."""
        return self.now

    def advance(self, seconds: float) -> None:
        """Move the clock forward."""
        self.now += seconds


@asynccontextmanager
async def hub(**overrides: Any) -> AsyncIterator[Dict[str, Any]]:
    """Hub with an injected limiter clock; ``alice@safer.ci`` / ``secret123`` is registered."""
    app = create_app(settings=make_settings(**overrides), database_url="sqlite+aiosqlite://", start_services=False)
    runtime = app.state.hub_runtime
    clock = FakeClock()
    runtime.limiter = RateLimiter(clock=clock)
    await runtime.start()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as http:
            alice = await register_user(http)
            alice["headers"] = {"Authorization": f"Bearer {alice['token']}"}
            runtime.limiter.reset()  # the registration above must not count
            yield {"app": app, "client": http, "runtime": runtime, "clock": clock, "alice": alice}
    finally:
        await runtime.stop()
        set_runtime(None)


async def login(
    http: httpx.AsyncClient, email: str = "alice@safer.ci", password: str = "secret123", headers: Optional[Dict[str, str]] = None
) -> httpx.Response:
    """One login attempt."""
    return await http.post(LOGIN, json={"email": email, "password": password}, headers=headers or {})


def assert_rate_limited(response: httpx.Response) -> None:
    """429 + Retry-After + ``rate_limited`` code."""
    assert response.status_code == 429, response.text
    assert response.json()["detail"]["code"] == "rate_limited"
    assert int(response.headers["Retry-After"]) >= 1
    assert response.json()["detail"]["retry_after"] == int(response.headers["Retry-After"])


def assert_locked(response: httpx.Response, retry_after: int = 900) -> None:
    """423 + exact Retry-After + ``account_locked`` code."""
    assert response.status_code == 423, response.text
    assert response.json()["detail"]["code"] == "account_locked"
    assert response.headers["Retry-After"] == str(retry_after)


# ----------------------------------------------------------------------------- limiter unit tests
def test_sliding_window_allows_limit_then_waits():
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    assert [limiter.hit("b", "k", 3, 60.0) for _ in range(3)] == [None, None, None]
    wait = limiter.hit("b", "k", 3, 60.0)
    assert wait is not None and 59.0 < wait <= 60.0
    # keys are normalised (case, spaces) and buckets are independent
    assert limiter.hit("b", "  K ", 3, 60.0) is not None
    assert limiter.hit("other", "k", 3, 60.0) is None
    assert limiter.hit("b", "k", 0, 60.0) is None  # limit 0 disables the bucket
    clock.advance(30)
    assert limiter.hit("b", "k", 3, 60.0) == 30.0  # refused hits are not counted: still the first three
    clock.advance(30.5)  # the three hits leave the window together
    assert limiter.hit("b", "k", 3, 60.0) is None
    assert limiter.hit("b", "k", 3, 60.0) is None
    assert limiter.hit("b", "k", 3, 60.0) is None
    assert limiter.hit("b", "k", 3, 60.0) == 60.0


def test_lockout_threshold_and_reset():
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    for _ in range(4):
        assert limiter.record_failure("a@x.ci", 5, 900.0, 900.0) is None
    assert limiter.locked_for("a@x.ci") is None
    assert limiter.record_failure("A@x.ci", 5, 900.0, 900.0) == 900.0
    assert limiter.locked_for("a@x.ci") == 900.0
    clock.advance(899)
    assert limiter.locked_for("a@x.ci") == 1.0
    clock.advance(1)
    assert limiter.locked_for("a@x.ci") is None
    # a success resets the series
    for _ in range(4):
        limiter.record_failure("a@x.ci", 5, 900.0, 900.0)
    limiter.record_success("a@x.ci")
    for _ in range(4):
        assert limiter.record_failure("a@x.ci", 5, 900.0, 900.0) is None
    # failures outside the window do not count
    clock.advance(901)
    assert limiter.record_failure("a@x.ci", 5, 900.0, 900.0) is None
    limiter.reset()
    assert limiter.tracked == 0


def test_expired_entries_are_pruned():
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    for i in range(500):
        limiter.hit("login:ip", f"10.0.0.{i}", 10, 60.0)
        limiter.record_failure(f"user{i}@x.ci", 5, 900.0, 900.0)
    assert limiter.tracked == 1000
    clock.advance(1000)
    limiter.hit("login:ip", "fresh", 10, 60.0)  # any access after the sweep interval sweeps
    assert limiter.tracked == 1


def test_client_ip_trusts_forwarded_header_only_when_told():
    def request(client: Optional[tuple], forwarded: Optional[str] = None) -> Request:
        headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
        return Request({"type": "http", "method": "POST", "path": "/", "headers": headers, "client": client, "query_string": b""})

    assert client_ip(request(("1.2.3.4", 5555), "9.9.9.9, 10.0.0.1")) == "1.2.3.4"
    # the last entry is the one the trusted proxy appended for the peer it saw; the first is client-chosen
    assert client_ip(request(("1.2.3.4", 5555), "9.9.9.9, 10.0.0.1"), trust_proxy_headers=True) == "10.0.0.1"
    assert client_ip(request(("1.2.3.4", 5555), "9.9.9.9,10.0.0.1 , 198.51.100.7"), trust_proxy_headers=True) == "198.51.100.7"
    assert client_ip(request(("1.2.3.4", 5555), "   "), trust_proxy_headers=True) == "1.2.3.4"
    # only real addresses are accepted from the header; junk falls back to the peer (and cannot bloat the keys)
    assert client_ip(request(("1.2.3.4", 5555), "x" * 500), trust_proxy_headers=True) == "1.2.3.4"
    assert client_ip(request(("1.2.3.4", 5555), "9.9.9.9, evil@example"), trust_proxy_headers=True) == "1.2.3.4"
    assert client_ip(request(("1.2.3.4", 5555), "evil@example, 9.9.9.9"), trust_proxy_headers=True) == "9.9.9.9"
    assert client_ip(request(("1.2.3.4", 5555), "2001:db8::1"), trust_proxy_headers=True) == "2001:db8::1"
    assert client_ip(request(("1.2.3.4", 5555), "[2001:DB8::1]:443"), trust_proxy_headers=True) == "2001:db8::1"
    assert client_ip(request(("1.2.3.4", 5555), "203.000.113.9"), trust_proxy_headers=True) == "1.2.3.4"
    assert client_ip(request(("1.2.3.4", 5555), "198.51.100.7:52000"), trust_proxy_headers=True) == "198.51.100.7"
    assert client_ip(request(None)) == "unknown"


# ----------------------------------------------------------------------------- routes
async def test_login_per_ip_limit():
    async with hub() as h:
        http, clock = h["client"], h["clock"]
        for i in range(10):  # distinct accounts: only the per-IP window applies
            assert (await login(http, email=f"user{i}@safer.ci", password="nope-nope")).status_code == 401
        assert_rate_limited(await login(http, email="user99@safer.ci", password="nope-nope"))
        assert_rate_limited(await login(http))  # even with valid credentials
        clock.advance(60)
        assert (await login(http)).status_code == 200


async def test_login_per_account_limit_and_recovery():
    async with hub() as h:
        http, clock = h["client"], h["clock"]
        for _ in range(5):
            assert (await login(http)).status_code == 200
        assert_rate_limited(await login(http))
        assert (await login(http, email="bob@safer.ci", password="x")).status_code == 401  # other accounts unaffected
        clock.advance(60)
        assert (await login(http)).status_code == 200


async def test_lockout_engages_and_resets_on_success():
    async with hub() as h:
        http, clock = h["client"], h["clock"]
        for _ in range(5):
            wrong = await login(http, password="wrong-pass")
            assert wrong.status_code == 401 and wrong.json()["detail"] == auth_routes.INVALID_CREDENTIALS
        assert_locked(await login(http))  # right password, still locked
        clock.advance(60)
        assert_locked(await login(http), retry_after=840)
        clock.advance(840)
        assert (await login(http)).status_code == 200  # lock expired, success resets the failure series
        for _ in range(4):
            assert (await login(http, password="wrong-pass")).status_code == 401
        clock.advance(60)
        assert (await login(http)).status_code == 200  # 4 failures + success: counter back to zero
        clock.advance(60)
        for _ in range(4):
            assert (await login(http, password="wrong-pass")).status_code == 401
        clock.advance(60)
        assert (await login(http)).status_code == 200  # not locked: the series restarted after the success


async def test_disabled_flag_bypasses_everything():
    async with hub(HUB_RATE_LIMIT_ENABLED=False) as h:
        http = h["client"]
        for _ in range(20):
            assert (await login(http, password="wrong-pass")).status_code == 401
        assert (await login(http)).status_code == 200
        for i in range(8):
            assert (await http.post(REGISTER, json={"email": f"u{i}@safer.ci", "password": "secret123"})).status_code == 201
        assert h["runtime"].limiter.tracked == 0


async def test_forwarded_header_is_ignored_unless_proxy_is_trusted():
    async with hub() as h:
        http = h["client"]
        for i in range(10):
            response = await login(http, email=f"u{i}@safer.ci", password="nope-nope", headers={"X-Forwarded-For": f"203.0.113.{i}"})
            assert response.status_code == 401
        assert_rate_limited(await login(http, email="u99@safer.ci", password="nope-nope", headers={"X-Forwarded-For": "203.0.113.99"}))
    async with hub(HUB_TRUST_PROXY_HEADERS=True) as h:
        http = h["client"]
        # an appending proxy leaves the client-chosen entry first and the real peer last: forging the first
        # entry does not spread the attempts over new addresses
        for i in range(10):
            response = await login(http, email=f"u{i}@safer.ci", password="nope-nope", headers={"X-Forwarded-For": f"203.0.113.{i}, 10.0.0.1"})
            assert response.status_code == 401
        assert_rate_limited(await login(http, email="u99@safer.ci", password="nope-nope", headers={"X-Forwarded-For": "203.0.113.99, 10.0.0.1"}))
        # nor can it pin the attempts on a victim's address: the victim behind the proxy is a different client
        assert (await login(http, headers={"X-Forwarded-For": "10.0.0.1, 192.0.2.5"})).status_code == 200
        for i in range(10):
            assert (await login(http, email=f"v{i}@safer.ci", password="nope-nope", headers={"X-Forwarded-For": "198.51.100.7"})).status_code == 401
        assert_rate_limited(await login(http, email="v99@safer.ci", password="nope-nope", headers={"X-Forwarded-For": "198.51.100.7"}))


async def test_login_failures_do_not_reveal_whether_the_email_exists(monkeypatch):
    checks = []
    real_verify = auth_routes.verify_password

    def counting_verify(password: str, password_hash: str) -> bool:
        checks.append(password_hash)
        return real_verify(password, password_hash)

    monkeypatch.setattr(auth_routes, "verify_password", counting_verify)
    async with hub() as h:
        http, clock = h["client"], h["clock"]
        existing = [await login(http, password="wrong-pass") for _ in range(5)]
        unknown = [await login(http, email="nobody@safer.ci", password="wrong-pass") for _ in range(5)]
        assert {r.status_code for r in existing + unknown} == {401}
        assert {r.json()["detail"] for r in existing + unknown} == {auth_routes.INVALID_CREDENTIALS}
        # the bcrypt check ran for every attempt, known or unknown account
        assert len(checks) == 10 and all(h.startswith("$2") for h in checks)
        # both are locked the same way afterwards (a minute later, past the per-IP window)
        clock.advance(60)
        locked_existing = await login(http)
        locked_unknown = await login(http, email="nobody@safer.ci", password="whatever")
        assert_locked(locked_existing, retry_after=840)
        assert_locked(locked_unknown, retry_after=840)
        assert locked_existing.json() == locked_unknown.json()
        clock.advance(840)
        assert (await login(http, email="nobody@safer.ci", password="whatever")).status_code == 401


async def test_register_per_ip_per_hour():
    async with hub() as h:
        http, clock = h["client"], h["clock"]
        for i in range(5):
            assert (await http.post(REGISTER, json={"email": f"u{i}@safer.ci", "password": "secret123"})).status_code == 201
        assert_rate_limited(await http.post(REGISTER, json={"email": "u5@safer.ci", "password": "secret123"}))
        clock.advance(3600)
        assert (await http.post(REGISTER, json={"email": "u5@safer.ci", "password": "secret123"})).status_code == 201


async def test_push_token_per_user_per_minute():
    async with hub() as h:
        http, clock, alice = h["client"], h["clock"], h["alice"]
        for i in range(10):
            response = await http.post(PUSH, json={"platform": "android", "token": f"token-{i}-abcdefgh"}, headers=alice["headers"])
            assert response.status_code == 204, response.text
        assert_rate_limited(await http.post(PUSH, json={"platform": "android", "token": "token-x-abcdefgh"}, headers=alice["headers"]))
        bob = await register_user(http, email="bob@safer.ci", name="Bob")
        bob_headers = {"Authorization": f"Bearer {bob['token']}"}
        assert (await http.post(PUSH, json={"platform": "android", "token": "token-bob-abcdefgh"}, headers=bob_headers)).status_code == 204
        clock.advance(60)
        assert (await http.post(PUSH, json={"platform": "android", "token": "token-x-abcdefgh"}, headers=alice["headers"])).status_code == 204


async def test_limiter_is_per_runtime():
    async with hub() as first:
        for _ in range(5):
            assert (await login(first["client"], password="wrong-pass")).status_code == 401
        assert_locked(await login(first["client"]))
    async with hub() as second:
        assert (await login(second["client"])).status_code == 200


async def test_lockout_is_scoped_to_the_client_address():
    """A stranger's five wrong passwords lock the stranger, not the owner on their own phone."""
    async with hub(HUB_TRUST_PROXY_HEADERS=True) as h:
        http, clock = h["client"], h["clock"]
        attacker = {"X-Forwarded-For": "203.0.113.66"}
        owner = {"X-Forwarded-For": "198.51.100.7"}
        for _ in range(5):
            assert (await login(http, password="wrong-wrong", headers=attacker)).status_code == 401
        assert_locked(await login(http, headers=attacker))  # the attacker is locked, right password or not
        clock.advance(60)  # the stranger can still fill the per-account minute window; that denial ends with it
        assert (await login(http, headers=owner)).status_code == 200  # the owner is not locked
        # the owner's own typos still lock the owner's own address (the brake against a local guesser stays)
        clock.advance(60)
        for _ in range(5):
            assert (await login(http, password="typo-typo", headers=owner)).status_code == 401
        assert_locked(await login(http, headers=owner))
        clock.advance(900)
        assert (await login(http, headers=owner)).status_code == 200
        # the per-account window still brakes guessing spread over many addresses: 5 attempts per minute in total
        clock.advance(60)  # past the owner's successful login above, which counted in the window
        for i in range(5):
            assert (await login(http, password="guess", headers={"X-Forwarded-For": f"203.0.113.{i}"})).status_code == 401
        assert_rate_limited(await login(http, password="guess", headers={"X-Forwarded-For": "203.0.113.200"}))
