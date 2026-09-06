"""Scene runner: executes scene/automation action lists against the hub.

Actions (see the design spec, section 3) are executed **in order** and every action produces one result
dict ``{"index", "type", "status": "ok"|"error"|"skipped", ...}``. A failing action never aborts the run:
its error is recorded in the result (``"error"`` and, for adapter failures, ``"code"``) and the next
action is executed, which is what users expect from a Tuya "tap-to-run" scene where one unreachable bulb
must not stop the shutters from closing.

Supported actions
-----------------
* ``device_command`` ``{device_id, code, value}`` — the device must belong to the home; goes through
  ``DeviceService.command`` so capability validation, state merge, events and WebSocket updates apply.
* ``delay`` ``{seconds}`` — ``asyncio.sleep``, capped at ``MAX_DELAY_SECONDS`` (5 minutes).
* ``security_mode`` ``{mode}`` — delegates to ``services.security_service.set_security_mode`` when that
  module exists (propagates ``arm_mode`` to alarm panels, posts a message); otherwise the home mode is set
  directly and ``security.mode`` is published.
* ``notify`` ``{title, body}`` — message-center entry of kind ``notice``.
* ``run_scene`` ``{scene_id}`` — runs another scene of the same home; nesting is limited to
  ``MAX_SCENE_DEPTH`` hops so cycles (A -> B -> A) terminate.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.hub import events as ev
from app.hub.adapters.base import AdapterError
from app.hub.capabilities import SECURITY_MODES
from app.hub.models import Device, Home, Scene, utcnow
from app.hub.services.device_service import DeviceService

logger = logging.getLogger("safer.hub.automation.runner")

__all__ = ["SceneRunner", "scene_summary", "MAX_DELAY_SECONDS", "MAX_SCENE_DEPTH", "SCENE_RAN_TITLE"]

MAX_DELAY_SECONDS = 300.0
MAX_SCENE_DEPTH = 3
SCENE_RAN_TITLE = "Scène exécutée"

_SOURCE_LABELS = {"scene": "manuellement", "automation": "par une automatisation", "manual": "manuellement"}


class SceneRunner:
    """Runs action lists for scenes and automations (one instance per runtime is enough, it is stateless)."""

    def __init__(self, runtime: Any):
        self.runtime = runtime

    # ------------------------------------------------------------------ helpers
    def _service(self) -> DeviceService:
        service = self.runtime.services.get("devices")
        if service is None:
            service = DeviceService(self.runtime)
            self.runtime.services["devices"] = service
        return service

    # ------------------------------------------------------------------ public API
    async def run_actions(
        self,
        session: AsyncSession,
        home_id: str,
        actions: List[Dict[str, Any]],
        source: str = "scene",
        _depth: int = 0,
    ) -> List[Dict[str, Any]]:
        """Execute ``actions`` in order for ``home_id`` and return one result per action.

        ``source`` (``scene`` | ``automation`` | ``manual``) is recorded in device state changes and in the
        messages posted by nested scenes. ``_depth`` is the ``run_scene`` nesting level (internal).
        """
        results: List[Dict[str, Any]] = []
        for index, action in enumerate(actions or []):
            action = action if isinstance(action, dict) else {}
            atype = str(action.get("type") or "")
            result: Dict[str, Any] = {"index": index, "type": atype, "status": "ok"}
            try:
                extra = await self._run_one(session, home_id, action, source, _depth)
                result.update(extra or {})
            except AdapterError as exc:
                result.update(status="error", error=exc.message, code=exc.code)
                logger.warning("Action %d (%s) failed for home %s: %s [%s]", index, atype, home_id, exc.message, exc.code)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pylint: disable=broad-except
                result.update(status="error", error=str(exc) or exc.__class__.__name__)
                logger.exception("Action %d (%s) crashed for home %s", index, atype, home_id)
                # A crashed action may have left the session in a failed transaction: reset it.
                try:
                    await session.rollback()
                except Exception:  # pylint: disable=broad-except
                    logger.debug("Session rollback after a failed action did not succeed", exc_info=True)
            results.append(result)
        return results

    async def run_scene(
        self, session: AsyncSession, scene: Scene, source: str = "scene", _depth: int = 0
    ) -> List[Dict[str, Any]]:
        """Run a scene: execute its actions, stamp ``last_run_at``, post a message and publish ``scene.ran``."""
        results = await self.run_actions(session, scene.home_id, list(scene.actions or []), source=source, _depth=_depth)
        failed = sum(1 for item in results if item.get("status") == "error")
        scene.last_run_at = utcnow()
        await session.commit()
        total = len(results)
        body = f"{total} action{'s' if total > 1 else ''} exécutée{'s' if total > 1 else ''} {_SOURCE_LABELS.get(source, source)}."
        if failed:
            body += f" {failed} en échec."
        await self._service().create_message(
            session, scene.home_id, "home", f"{SCENE_RAN_TITLE}: {scene.name}", body,
            severity="warning" if failed else "info", publish=True,
        )
        await session.commit()
        await self.runtime.bus.publish(
            ev.HubEvent(
                ev.SCENE_RAN, home_id=scene.home_id,
                payload={"scene_id": scene.id, "name": scene.name, "source": source, "ok": failed == 0, "actions": total},
            )
        )
        logger.info("Scene %s (%s) ran (%s): %d action(s), %d failed", scene.id, scene.name, source, total, failed)
        return results

    # ------------------------------------------------------------------ actions
    async def _run_one(
        self, session: AsyncSession, home_id: str, action: Dict[str, Any], source: str, depth: int
    ) -> Dict[str, Any]:
        atype = action.get("type")
        if atype == "device_command":
            return await self._device_command(session, home_id, action)
        if atype == "delay":
            return await self._delay(action)
        if atype == "security_mode":
            return await self._security_mode(session, home_id, action, source)
        if atype == "notify":
            return await self._notify(session, home_id, action)
        if atype == "run_scene":
            return await self._run_scene_action(session, home_id, action, source, depth)
        raise AdapterError(f"Unknown action type '{atype}'", "invalid_input")

    async def _device_command(self, session: AsyncSession, home_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
        device_id, code = action.get("device_id"), action.get("code")
        if not device_id or not code:
            raise AdapterError("device_command requires device_id and code", "invalid_input")
        device = await session.get(Device, device_id)
        if device is None or device.home_id != home_id:
            raise AdapterError("Device not found in this home", "not_found")
        value = action.get("value")
        await self._service().command(session, device, code, value)
        return {"device_id": device.id, "code": code, "value": value, "state": {code: (device.state or {}).get(code)}}

    @staticmethod
    async def _delay(action: Dict[str, Any]) -> Dict[str, Any]:
        try:
            seconds = float(action.get("seconds") or 0)
        except (TypeError, ValueError) as exc:
            raise AdapterError("delay requires a numeric 'seconds'", "invalid_input") from exc
        seconds = max(0.0, min(MAX_DELAY_SECONDS, seconds))
        if seconds > 0:
            await asyncio.sleep(seconds)
        return {"seconds": seconds}

    async def _security_mode(
        self, session: AsyncSession, home_id: str, action: Dict[str, Any], source: str
    ) -> Dict[str, Any]:
        mode = action.get("mode")
        if mode not in SECURITY_MODES:
            raise AdapterError(f"Invalid security mode '{mode}'", "invalid_input")
        home = await session.get(Home, home_id)
        if home is None:
            raise AdapterError("Home not found", "not_found")
        try:
            from app.hub.services.security_service import set_security_mode  # pylint: disable=import-outside-toplevel
        except ImportError:
            set_security_mode = None  # pylint: disable=invalid-name
        previous = home.security_mode
        if set_security_mode is not None:
            await set_security_mode(self.runtime, session, home, mode, user_id=None, propagate=True)
        else:
            if home.security_mode != mode:
                home.security_mode = mode
                home.security_changed_at = utcnow()
                await session.commit()
            await self.runtime.bus.publish(
                ev.HubEvent(ev.SECURITY_MODE, home_id=home.id, payload={"mode": mode, "source": source})
            )
        return {"mode": mode, "previous": previous}

    async def _notify(self, session: AsyncSession, home_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
        title = str(action.get("title") or "").strip() or "Notification"
        body = str(action.get("body") or "")
        message = await self._service().create_message(session, home_id, "notice", title, body, severity="info", publish=True)
        await session.commit()
        return {"message_id": message.id, "title": title}

    async def _run_scene_action(
        self, session: AsyncSession, home_id: str, action: Dict[str, Any], source: str, depth: int
    ) -> Dict[str, Any]:
        scene_id = action.get("scene_id")
        if not scene_id:
            raise AdapterError("run_scene requires scene_id", "invalid_input")
        if depth >= MAX_SCENE_DEPTH:
            raise AdapterError(f"Scene nesting deeper than {MAX_SCENE_DEPTH} levels is not allowed", "invalid_input")
        scene = await session.get(Scene, scene_id)
        if scene is None or scene.home_id != home_id:
            raise AdapterError("Scene not found in this home", "not_found")
        if not scene.enabled:
            return {"scene_id": scene.id, "name": scene.name, "status": "skipped", "error": "Scene is disabled"}
        nested = await self.run_scene(session, scene, source=source, _depth=depth + 1)
        failed = sum(1 for item in nested if item.get("status") == "error")
        result: Dict[str, Any] = {"scene_id": scene.id, "name": scene.name, "results": nested}
        if failed:
            result.update(status="error", error=f"{failed} nested action(s) failed")
        return result


def scene_summary(results: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count ``ok`` / ``error`` / ``skipped`` results (top level only)."""
    summary = {"ok": 0, "error": 0, "skipped": 0}
    for item in results:
        summary[item.get("status", "ok")] = summary.get(item.get("status", "ok"), 0) + 1
    return summary
