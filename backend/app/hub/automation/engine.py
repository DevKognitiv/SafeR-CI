"""Automation engine: evaluates "if this then that" automations against bus events and a minute tick.

Sources of evaluation
---------------------
* ``device.state`` bus events (payload ``{"state", "online", "changed"}`` published by ``DeviceService``)
  feed ``device_state`` triggers. Triggers are **edge based**: when the payload carries ``changed`` the code
  must be part of it (the value actually transitioned) and the comparison runs on the new value; without
  ``changed`` (foreign publishers) the full ``state`` is used.
* ``security.mode`` bus events feed ``security_mode`` triggers.
* A ``tick`` event published every minute (aligned on the minute boundary) feeds ``schedule`` triggers,
  compared in **local time** (``datetime.now``; injectable for tests). Weekdays follow Python: Monday = 0.

Triggers are OR-ed (any matching trigger fires); ``conditions`` are then checked with ``match`` (``all`` |
``any``): ``device_state`` against the device's current state, ``time_range`` (overnight ranges such as
``22:00``-``06:00`` supported, start inclusive / end exclusive) and ``security_mode`` against the home.

Actions run through ``SceneRunner`` with ``source="automation"``; ``last_triggered_at`` is stamped and an
``automation.ran`` event ``{automation_id, name, source, ok}`` is published.

Safety
------
* Bus delivery never blocks publishers: events are queued and evaluated by a worker task; action runs
  (which may contain delays) are spawned as tasks, at most ``concurrency`` at a time (one on a shared
  in-memory SQLite connection, like the poller).
* Re-entrancy guard: an automation cannot fire again within ``reentry_seconds`` (2 s) of its last run,
  so "when light changes -> change light" style loops terminate.
* Schedule triggers fire at most once per minute slot even if several ticks land in the same minute.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import StaticPool

from app.hub import events as ev
from app.hub.automation.runner import SceneRunner
from app.hub.models import Automation, Device, Home, utcnow

logger = logging.getLogger("safer.hub.automation.engine")

__all__ = [
    "AutomationEngine", "AUTOMATION_RAN", "HANDLED_EVENTS", "run_automation", "compare_values", "in_time_range",
    "parse_hhmm",
]

AUTOMATION_RAN = "automation.ran"
HANDLED_EVENTS = {ev.DEVICE_STATE, ev.SECURITY_MODE, ev.TICK}
DEFAULT_TICK_INTERVAL = 60.0
DEFAULT_REENTRY_SECONDS = 2.0
DEFAULT_CONCURRENCY = 8
MINUTES_PER_DAY = 24 * 60

_TRUE_WORDS = {"true", "on", "yes", "open", "1"}
_FALSE_WORDS = {"false", "off", "no", "closed", "0"}


# ----------------------------------------------------------------------------- value helpers
def _to_number(value: Any) -> Optional[float]:
    """Float for ints/floats/bools/numeric strings, else None."""
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return number if number == number and number not in (float("inf"), float("-inf")) else None
    return None


def _normalize(value: Any) -> str:
    """Canonical string for equality checks ("on"/"true"/True all become ``"true"``)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return str(value)
    text = str(value).strip().lower()
    if text in _TRUE_WORDS:
        return "true"
    if text in _FALSE_WORDS:
        return "false"
    return text


def compare_values(op: str, actual: Any, expected: Any) -> bool:
    """Evaluate ``actual <op> expected``. Numeric comparisons tolerate numeric strings; ``changed`` is True."""
    op = (op or "eq").lower()
    if op == "changed":
        return True
    a_num, e_num = _to_number(actual), _to_number(expected)
    if op in ("gt", "lt", "gte", "lte"):
        if a_num is None or e_num is None:
            return False
        if op == "gt":
            return a_num > e_num
        if op == "lt":
            return a_num < e_num
        if op == "gte":
            return a_num >= e_num
        return a_num <= e_num
    if a_num is not None and e_num is not None and not (isinstance(actual, bool) and isinstance(expected, str)):
        equal = a_num == e_num
    else:
        equal = _normalize(actual) == _normalize(expected)
    if op == "ne":
        return not equal
    return equal  # eq and anything unknown behaves like eq


def parse_hhmm(value: Any) -> Optional[Tuple[int, int]]:
    """``"HH:MM"`` (also ``"H:MM"`` / ``"HH:MM:SS"``) -> (hour, minute) or None."""
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) < 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return hour, minute


def in_time_range(start: Any, end: Any, moment: datetime) -> bool:
    """True when ``moment`` (local) is inside ``[start, end)``; overnight ranges wrap past midnight.

    ``start == end`` means the whole day. Unparseable bounds never match.
    """
    start_hm, end_hm = parse_hhmm(start), parse_hhmm(end)
    if start_hm is None or end_hm is None:
        return False
    start_min = start_hm[0] * 60 + start_hm[1]
    end_min = end_hm[0] * 60 + end_hm[1]
    now_min = moment.hour * 60 + moment.minute
    if start_min == end_min:
        return True
    if start_min < end_min:
        return start_min <= now_min < end_min
    return now_min >= start_min or now_min < end_min


def _weekdays(value: Any) -> Optional[Set[int]]:
    """Normalise a ``days`` list (ints or numeric strings, Monday = 0) — None/empty means every day."""
    if not value:
        return None
    days: Set[int] = set()
    for item in value if isinstance(value, (list, tuple, set)) else [value]:
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 6:
            days.add(day)
    return days or None


# ----------------------------------------------------------------------------- shared run helper
async def run_automation(
    runtime: Any, session: AsyncSession, automation: Automation, source: str = "automation"
) -> List[Dict[str, Any]]:
    """Run an automation's actions, stamp ``last_triggered_at`` and publish ``automation.ran``.

    Used by the engine (``source="automation"``) and by the manual trigger endpoint (``source="manual"``).
    """
    runner = SceneRunner(runtime)
    results = await runner.run_actions(session, automation.home_id, list(automation.actions or []), source=source)
    failed = sum(1 for item in results if item.get("status") == "error")
    automation.last_triggered_at = utcnow()
    await session.commit()
    await runtime.bus.publish(
        ev.HubEvent(
            AUTOMATION_RAN, home_id=automation.home_id,
            payload={"automation_id": automation.id, "name": automation.name, "source": source,
                     "ok": failed == 0, "actions": len(results)},
        )
    )
    logger.info("Automation %s (%s) ran (%s): %d action(s), %d failed", automation.id, automation.name, source, len(results), failed)
    return results


# ----------------------------------------------------------------------------- engine
class AutomationEngine:
    """Bus subscriber + minute tick evaluating automations (see module docstring)."""

    def __init__(
        self,
        runtime: Any,
        now: Optional[Callable[[], datetime]] = None,
        tick_interval: float = DEFAULT_TICK_INTERVAL,
        reentry_seconds: float = DEFAULT_REENTRY_SECONDS,
        concurrency: Optional[int] = None,
    ):
        self.runtime = runtime
        self._now: Callable[[], datetime] = now or datetime.now
        self.tick_interval = float(tick_interval)
        self.reentry_seconds = max(0.0, float(reentry_seconds))
        self.concurrency = max(1, int(concurrency)) if concurrency else self._default_concurrency()
        self.evaluated = 0
        self.fired = 0
        self.ticks = 0
        self.last_fired_at: Optional[datetime] = None
        self.last_tick_at: Optional[datetime] = None
        self._queue: "asyncio.Queue[ev.HubEvent]" = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._tasks: Set["asyncio.Task[Any]"] = set()
        self._worker_task: Optional["asyncio.Task[None]"] = None
        self._tick_task: Optional["asyncio.Task[None]"] = None
        self._bus_unsubscribe: Optional[Callable[[], None]] = None
        self._recent_fires: Dict[str, float] = {}
        self._schedule_slots: Dict[str, str] = {}

    # ------------------------------------------------------------------ configuration
    def _default_concurrency(self) -> int:
        """Parallel action runs; a single shared connection (in-memory SQLite) forces one at a time."""
        engine = getattr(getattr(self.runtime, "db", None), "engine", None)
        pool = getattr(engine, "pool", None)
        if pool is not None and isinstance(pool, StaticPool):
            return 1
        return DEFAULT_CONCURRENCY

    def now(self) -> datetime:
        """Current local time (injectable through the constructor for tests)."""
        return self._now()

    @property
    def running(self) -> bool:
        """True while the worker task is alive."""
        return self._worker_task is not None and not self._worker_task.done()

    @property
    def pending(self) -> int:
        """Queued events plus action runs still in flight."""
        return self._queue.qsize() + sum(1 for task in self._tasks if not task.done())

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        """Subscribe to the bus and start the worker + minute tick (idempotent)."""
        if self._bus_unsubscribe is None:
            self._bus_unsubscribe = self.runtime.bus.subscribe(self._on_event)
        if not self.running:
            self._worker_task = asyncio.create_task(self._worker(), name="safer-hub-automations")
        if self.tick_interval > 0 and (self._tick_task is None or self._tick_task.done()):
            self._tick_task = asyncio.create_task(self._tick_loop(), name="safer-hub-automations-tick")
        logger.info("Automation engine started (tick every %.0fs, concurrency %d)", self.tick_interval, self.concurrency)

    async def stop(self) -> None:
        """Unsubscribe, stop the tick and worker and cancel in-flight action runs."""
        if self._bus_unsubscribe is not None:
            self._bus_unsubscribe()
            self._bus_unsubscribe = None
        for attr in ("_tick_task", "_worker_task"):
            task = getattr(self, attr)
            setattr(self, attr, None)
            await self._cancel(task)
        for task in list(self._tasks):
            await self._cancel(task)
        self._tasks.clear()
        logger.info("Automation engine stopped (%d evaluation(s), %d run(s))", self.evaluated, self.fired)

    @staticmethod
    async def _cancel(task: Optional["asyncio.Task[Any]"]) -> None:
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:  # pylint: disable=broad-except
            logger.exception("Automation task ended with an error")

    async def drain(self, timeout: float = 10.0) -> None:
        """Wait until every queued event is evaluated and every action run finished (tests)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError("automation engine did not settle in time")
            if self.running:
                await asyncio.wait_for(self._queue.join(), timeout=remaining)
            tasks = [task for task in self._tasks if not task.done()]
            if not tasks and self._queue.empty():
                return
            if tasks:
                await asyncio.wait(tasks, timeout=max(0.0, deadline - loop.time()))

    # ------------------------------------------------------------------ bus / worker / tick
    async def _on_event(self, event: ev.HubEvent) -> None:
        if event.type in HANDLED_EVENTS:
            self._queue.put_nowait(event)

    async def _worker(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                await self.evaluate_event(event, background=True)
            except asyncio.CancelledError:
                raise
            except Exception:  # pylint: disable=broad-except
                logger.exception("Automation evaluation failed for %s", event.type)
            finally:
                self._queue.task_done()

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(self.tick_interval - (time.time() % self.tick_interval) + 0.05)
            self.ticks += 1
            self.last_tick_at = utcnow()
            try:
                await self.runtime.bus.publish(ev.HubEvent(ev.TICK, payload={"at": self.now().isoformat(timespec="minutes")}))
            except Exception:  # pylint: disable=broad-except
                logger.exception("Tick publication failed")

    def _spawn(self, coro: Any, name: str) -> "asyncio.Task[Any]":
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # ------------------------------------------------------------------ evaluation
    async def evaluate_event(
        self, event: ev.HubEvent, now: Optional[datetime] = None, background: bool = False
    ) -> List[str]:
        """Evaluate one event against the enabled automations; returns the ids of the automations fired.

        ``now`` overrides the engine clock (schedule / time_range checks). With ``background`` the action runs
        are spawned as tasks (bus path); otherwise they are awaited before returning (tests, manual use).
        """
        if event.type not in HANDLED_EVENTS:
            return []
        moment = now or self.now()
        self.evaluated += 1
        async with self.runtime.db.session() as session:
            matched: List[Tuple[str, str]] = []
            for automation in await self._candidates(session, event):
                if not self._triggers_match(automation, event, moment):
                    continue
                if not await self._conditions_match(session, automation, moment):
                    logger.debug("Automation %s: trigger matched but conditions failed", automation.id)
                    continue
                matched.append((automation.id, automation.name))
        fired: List[str] = []
        for automation_id, name in matched:
            if not self._guard(automation_id):
                logger.info("Automation %s (%s) skipped: fired less than %.1fs ago", automation_id, name, self.reentry_seconds)
                continue
            fired.append(automation_id)
            self.fired += 1
            self.last_fired_at = utcnow()
            if background:
                self._spawn(self._fire(automation_id), name=f"safer-hub-automation-{automation_id[:8]}")
            else:
                await self._fire(automation_id)
        return fired

    async def _candidates(self, session: AsyncSession, event: ev.HubEvent) -> List[Automation]:
        query = select(Automation).where(Automation.enabled.is_(True))
        if event.type == ev.TICK:
            rows = (await session.execute(query.order_by(Automation.created_at))).scalars().all()
            return [a for a in rows if any(isinstance(t, dict) and t.get("type") == "schedule" for t in (a.triggers or []))]
        if not event.home_id:
            return []
        return list((await session.execute(query.where(Automation.home_id == event.home_id).order_by(Automation.created_at))).scalars().all())

    def _guard(self, automation_id: str) -> bool:
        """Mark ``automation_id`` as firing now; False when it fired within the re-entrancy window."""
        now = time.monotonic()
        last = self._recent_fires.get(automation_id)
        if last is not None and self.reentry_seconds > 0 and now - last < self.reentry_seconds:
            return False
        self._recent_fires[automation_id] = now
        if len(self._recent_fires) > 256:
            window = max(self.reentry_seconds, 1.0)
            self._recent_fires = {k: v for k, v in self._recent_fires.items() if now - v < window}
        return True

    # ------------------------------------------------------------------ triggers
    def _triggers_match(self, automation: Automation, event: ev.HubEvent, moment: datetime) -> bool:
        for trigger in automation.triggers or []:
            if not isinstance(trigger, dict):
                continue
            if self._trigger_ok(automation, trigger, event, moment):
                return True
        return False

    def _trigger_ok(self, automation: Automation, trigger: Dict[str, Any], event: ev.HubEvent, moment: datetime) -> bool:
        ttype = trigger.get("type")
        payload = event.payload or {}
        if ttype == "device_state":
            if event.type != ev.DEVICE_STATE or event.device_id != trigger.get("device_id"):
                return False
            code = trigger.get("code")
            changed = payload.get("changed")
            if isinstance(changed, dict):
                if code not in changed:
                    return False
                value = changed[code]
            else:
                state = payload.get("state") or {}
                if code not in state:
                    return False
                value = state[code]
            return compare_values(trigger.get("op", "eq"), value, trigger.get("value"))
        if ttype == "security_mode":
            return event.type == ev.SECURITY_MODE and payload.get("mode") == trigger.get("mode")
        if ttype == "schedule":
            if event.type != ev.TICK:
                return False
            at = parse_hhmm(trigger.get("time"))
            if at is None or at != (moment.hour, moment.minute):
                return False
            days = _weekdays(trigger.get("days"))
            if days is not None and moment.weekday() not in days:
                return False
            slot = moment.strftime("%Y-%m-%d %H:%M")
            if self._schedule_slots.get(automation.id) == slot:
                return False  # already fired for this minute
            self._schedule_slots[automation.id] = slot
            return True
        return False

    # ------------------------------------------------------------------ conditions
    async def _conditions_match(self, session: AsyncSession, automation: Automation, moment: datetime) -> bool:
        conditions = [c for c in (automation.conditions or []) if isinstance(c, dict)]
        if not conditions:
            return True
        any_mode = (automation.match or "all") == "any"
        outcome = False if any_mode else True
        for condition in conditions:
            ok = await self._condition_ok(session, automation.home_id, condition, moment)
            if any_mode and ok:
                return True
            if not any_mode and not ok:
                return False
            outcome = ok if any_mode else outcome and ok
        return outcome

    async def _condition_ok(self, session: AsyncSession, home_id: str, condition: Dict[str, Any], moment: datetime) -> bool:
        ctype = condition.get("type")
        if ctype == "device_state":
            device = await session.get(Device, condition.get("device_id") or "")
            if device is None or device.home_id != home_id:
                return False
            state = device.state or {}
            code = condition.get("code")
            if code not in state:
                return False
            return compare_values(condition.get("op", "eq"), state[code], condition.get("value"))
        if ctype == "time_range":
            return in_time_range(condition.get("start"), condition.get("end"), moment)
        if ctype == "security_mode":
            home = await session.get(Home, home_id)
            return home is not None and home.security_mode == condition.get("mode")
        return False

    # ------------------------------------------------------------------ firing
    async def _fire(self, automation_id: str) -> Optional[List[Dict[str, Any]]]:
        """Run one automation's actions in its own session (re-checks that it still exists and is enabled)."""
        async with self._semaphore:
            try:
                async with self.runtime.db.session() as session:
                    automation = await session.get(Automation, automation_id)
                    if automation is None or not automation.enabled:
                        return None
                    return await run_automation(self.runtime, session, automation, source="automation")
            except asyncio.CancelledError:
                raise
            except Exception:  # pylint: disable=broad-except
                logger.exception("Automation %s run failed", automation_id)
                return None
