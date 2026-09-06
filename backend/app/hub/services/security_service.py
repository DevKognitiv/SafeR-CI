"""Home-level security: arm/disarm, alarm acknowledgement and the "Security" tab snapshot.

The hub is the *software* alarm panel of a home (``Home.security_mode`` / ``Home.alarm_active``, tripped by
``DeviceService._evaluate_security`` when armed sensors fire). Hardware panels (Hikvision AX PRO, Ajax hub,
Tuya gateways...) are mirrored best effort:

* :func:`set_security_mode` writes ``arm_mode`` to every ``alarm_panel`` device exposing a writable
  ``arm_mode`` capability through ``DeviceService.command`` (capability validation, state merge, events).
  One-way panels (SIA DC-09 receivers) raise ``unsupported`` and are skipped silently; any other failure is
  logged, turned into a *notice* message so the user knows the panel is out of sync, and never fails the call.
* :func:`clear_alarm` acknowledges the software alarm and asks hardware panels to clear theirs
  (``clear_alarm``/``True`` first, then the ``alarm``/``False`` convention), swallowing every adapter error.
* :func:`security_state` builds the ``SecurityOut`` payload (mode, alarm flag, panels, zones, sensors).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub import events as ev
from app.hub.adapters.base import AdapterError
from app.hub.adapters.registry import registry
from app.hub.capabilities import CATEGORIES, SECURITY_MODES, find_capability
from app.hub.models import Device, Home, utcnow
from app.hub.schemas import DeviceOut, SecurityOut
from app.hub.services.device_service import DeviceService

logger = logging.getLogger("safer.hub.security")

__all__ = [
    "MODE_LABELS", "SENSOR_CATEGORIES", "DEMO_BRAND", "set_security_mode", "clear_alarm", "security_state",
    "mode_label", "list_panels",
]

DEMO_BRAND = "demo"
PANEL_CATEGORY = "alarm_panel"
ZONE_CATEGORY = "alarm_zone"
SENSOR_CATEGORIES: Tuple[str, ...] = tuple(c for c in CATEGORIES if c.startswith("sensor_")) + ("lock", "siren")

# French labels shown in the message center (the app translates the mode itself from the code).
MODE_LABELS: Dict[str, str] = {
    "disarmed": "Désarmé",
    "armed_home": "Armé (présence)",
    "armed_away": "Armé (absence)",
    "armed_night": "Mode nuit",
}

# Commands tried, in order, to clear a hardware panel's alarm. Hikvision AX PRO accepts ``clear_alarm``;
# adapters modelled on the ``alarm`` capability accept ``alarm=False``. ``unsupported`` moves to the next one.
CLEAR_ALARM_COMMANDS: Tuple[Tuple[str, Any], ...] = (("clear_alarm", True), ("alarm", False))


def mode_label(mode: str) -> str:
    """French label of a security mode (falls back to the code)."""
    return MODE_LABELS.get(mode, mode)


def _device_service(runtime: Any) -> DeviceService:
    service = runtime.services.get("devices")
    if service is None:
        service = DeviceService(runtime)
        runtime.services["devices"] = service
    return service


async def list_panels(session: AsyncSession, home_id: str) -> List[Device]:
    """Alarm panels of a home (oldest first)."""
    rows = await session.execute(
        select(Device).where(Device.home_id == home_id, Device.category == PANEL_CATEGORY).order_by(Device.created_at, Device.name)
    )
    return list(rows.scalars().all())


def _error_text(exc: BaseException) -> str:
    if isinstance(exc, AdapterError):
        return exc.message
    return str(exc) or exc.__class__.__name__


# ----------------------------------------------------------------------------- arm / disarm
async def _propagate_mode(
    runtime: Any, session: AsyncSession, home: Home, mode: str
) -> List[Tuple[Device, BaseException]]:
    """Send ``arm_mode`` to every writable panel of the home. Returns ``[(panel, error)]`` for failures."""
    service = _device_service(runtime)
    errors: List[Tuple[Device, BaseException]] = []
    for panel in await list_panels(session, home.id):
        capability = find_capability(panel.capabilities or [], "arm_mode")
        if capability is None or not capability.get("writable"):
            logger.debug("Panel %s (%s) has no writable arm_mode; skipped", panel.name, panel.brand)
            continue
        try:
            await service.command(session, panel, "arm_mode", mode)
        except AdapterError as exc:
            if exc.code == "unsupported":
                # One-way panels (SIA receivers, read-only integrations): nothing to push.
                logger.info("Panel %s (%s) does not accept arm_mode: %s", panel.name, panel.brand, exc.message)
                continue
            logger.warning("arm_mode=%s failed on panel %s (%s): %s [%s]", mode, panel.name, panel.brand, exc.message, exc.code)
            errors.append((panel, exc))
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Unexpected failure sending arm_mode=%s to panel %s (%s)", mode, panel.name, panel.brand)
            await session.rollback()
            errors.append((panel, exc))
    return errors


async def set_security_mode(
    runtime: Any,
    session: AsyncSession,
    home: Home,
    mode: str,
    user_id: Optional[str] = None,
    propagate: bool = True,
) -> Home:
    """Set the home security mode, mirror it on hardware panels (best effort), notify and record it.

    ``user_id`` marks a change made from the app (event ``source="user"``); ``None`` means an automation or
    scene (``source="automation"``). Disarming also clears the software alarm. Raises
    ``AdapterError(invalid_input)`` for an unknown mode; panel failures never propagate.
    """
    if mode not in SECURITY_MODES:
        raise AdapterError(f"Invalid security mode '{mode}' (expected one of {', '.join(SECURITY_MODES)})", "invalid_input")
    source = "user" if user_id else "automation"
    previous = home.security_mode
    alarm_cleared = False

    home.security_mode = mode
    home.security_changed_at = utcnow()
    if mode == "disarmed" and (home.alarm_active or home.alarm_device_id):
        alarm_cleared = bool(home.alarm_active)
        home.alarm_active = False
        home.alarm_device_id = None
    # Commit before touching panels: ``apply_state`` sees the new mode (no duplicate ``security.mode``) and a
    # failing panel cannot roll the home change back.
    await session.commit()

    errors: List[Tuple[Device, BaseException]] = []
    if propagate:
        errors = await _propagate_mode(runtime, session, home, mode)

    bus = runtime.bus
    await bus.publish(ev.HubEvent(ev.SECURITY_MODE, home_id=home.id, payload={"mode": mode, "source": source}))
    if alarm_cleared:
        await bus.publish(ev.HubEvent(ev.SECURITY_ALARM, home_id=home.id, payload={"active": False}))

    service = _device_service(runtime)
    label = mode_label(mode)
    origin = "depuis l'application" if source == "user" else "par une automatisation"
    body = f"Le mode de sécurité est passé de {mode_label(previous)} à {label} {origin}."
    await service.create_message(session, home.id, "home", f"Mode sécurité: {label}", body, severity="info", publish=True)
    for panel, exc in errors:
        await service.create_message(
            session, home.id, "notice", f"Centrale non synchronisée — {panel.name}",
            f"Impossible d'appliquer le mode {label} sur la centrale: {_error_text(exc)}",
            device_id=panel.id, severity="warning", publish=True,
        )
    await session.commit()
    logger.info("Home %s security mode %s -> %s (%s, %d panel error(s))", home.id, previous, mode, source, len(errors))
    return home


# ----------------------------------------------------------------------------- alarm acknowledgement
async def _hardware_clear(runtime: Any, service: DeviceService, session: AsyncSession, panel: Device) -> bool:
    """Ask one hardware panel to clear its alarm. Never raises; returns True when a command succeeded."""
    adapter = registry.get(panel.brand)
    if adapter is None:
        logger.debug("No adapter for panel brand %s; hardware clear skipped", panel.brand)
        return False
    ref = await service.ref_for(session, panel)
    ctx = runtime.ctx_for(panel.brand)
    for code, value in CLEAR_ALARM_COMMANDS:
        try:
            partial = await adapter.send_command(ref, code, value, ctx)
        except AdapterError as exc:
            if exc.code == "unsupported":
                continue
            logger.warning("Clearing alarm on panel %s (%s) failed: %s [%s]", panel.name, panel.brand, exc.message, exc.code)
            return False
        except Exception:  # pylint: disable=broad-except
            logger.exception("Unexpected failure clearing alarm on panel %s (%s)", panel.name, panel.brand)
            return False
        if partial:
            try:
                await service.apply_state(session, panel, dict(partial), online=True, source="command")
            except Exception:  # pylint: disable=broad-except
                logger.exception("Could not apply cleared state of panel %s", panel.name)
                await session.rollback()
        return True
    logger.info("Panel %s (%s) has no alarm-clear command", panel.name, panel.brand)
    return False


async def clear_alarm(runtime: Any, session: AsyncSession, home: Home) -> Home:
    """Acknowledge the home alarm: reset the software flag, clear hardware panels (best effort), notify."""
    previous_device = home.alarm_device_id
    home.alarm_active = False
    home.alarm_device_id = None
    await session.commit()

    service = _device_service(runtime)
    for panel in await list_panels(session, home.id):
        if panel.brand == DEMO_BRAND:
            continue  # virtual panel: the hub itself is the software panel
        await _hardware_clear(runtime, service, session, panel)

    await runtime.bus.publish(
        ev.HubEvent(ev.SECURITY_ALARM, home_id=home.id, device_id=previous_device, payload={"active": False})
    )
    await service.create_message(
        session, home.id, "notice", "Alarme acquittée", "L'alarme a été acquittée depuis l'application.",
        device_id=previous_device, severity="info", publish=True,
    )
    await session.commit()
    logger.info("Home %s alarm cleared (device %s)", home.id, previous_device)
    return home


# ----------------------------------------------------------------------------- snapshot
async def security_state(session: AsyncSession, home: Home) -> SecurityOut:
    """``SecurityOut`` for the Security tab: mode, alarm flag, panels, zones and security sensors."""
    categories = [PANEL_CATEGORY, ZONE_CATEGORY, *SENSOR_CATEGORIES]
    rows = await session.execute(
        select(Device).where(Device.home_id == home.id, Device.category.in_(categories)).order_by(Device.created_at, Device.name)
    )
    panels: List[DeviceOut] = []
    zones: List[DeviceOut] = []
    sensors: List[DeviceOut] = []
    for device in rows.scalars().all():
        out = DeviceOut.model_validate(device)
        if device.category == PANEL_CATEGORY:
            panels.append(out)
        elif device.category == ZONE_CATEGORY:
            zones.append(out)
        else:
            sensors.append(out)
    return SecurityOut(
        home_id=home.id,
        mode=home.security_mode or "disarmed",
        alarm_active=bool(home.alarm_active),
        alarm_device_id=home.alarm_device_id,
        changed_at=home.security_changed_at,
        panels=panels,
        zones=zones,
        sensors=sensors,
    )
