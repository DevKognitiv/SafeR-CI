"""SOS: panic button of the app, bridged to the SafeR CI incident platform.

:func:`raise_sos` stores a ``SosAlert``, trips the home's software alarm (so the Security tab shows the red
banner), posts a critical *alarm* message, publishes ``sos.raised`` on the bus and, when
``SAFER_INCIDENTS_URL`` is configured, forwards the alert as an incident through
``runtime.ctx_for("sos").http()`` (so tests inject an ``httpx.MockTransport``). Forwarding is fire-and-forget:
it runs in a background task (``runtime.spawn``) with its own session so the panic button answers immediately;
network/HTTP failures are logged and the alert simply stays ``forwarded=False``. ``GET /homes/{id}/sos`` shows
``forwarded``/``incident_id`` once the platform answered.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub import events as ev
from app.hub.models import Home, SosAlert, User
from app.hub.schemas import SosIn
from app.hub.services.device_service import DeviceService

logger = logging.getLogger("safer.hub.sos")

__all__ = ["raise_sos", "forward_sos", "forward_later", "build_incident_payload", "DEFAULT_LAT", "DEFAULT_LON", "SOS_TITLE"]

# Abidjan (Plateau) — used when neither the phone nor the home has a position.
DEFAULT_LAT = 5.36
DEFAULT_LON = -4.0083
HUB_ID = "safer-hub"
SOURCE = "mobile_app"
SOS_TITLE = "🆘 SOS déclenché"
CONTEXT_BRAND = "sos"


def _device_service(runtime: Any) -> DeviceService:
    service = runtime.services.get("devices")
    if service is None:
        service = DeviceService(runtime)
        runtime.services["devices"] = service
    return service


def _display_name(user: User) -> str:
    return (getattr(user, "name", "") or "").strip() or getattr(user, "email", "") or "Un membre"


def _pick(*values: Optional[float], default: float) -> float:
    for value in values:
        if value is not None:
            return float(value)
    return default


def build_incident_payload(home: Home, user: User, alert: SosAlert, incident_type: str = "panic") -> Dict[str, Any]:
    """Incident body sent to the SafeR CI platform (position: phone > home > Abidjan)."""
    return {
        "incident_type": incident_type or "panic",
        "severity": "critical",
        "location_lat": _pick(alert.lat, home.lat, default=DEFAULT_LAT),
        "location_lon": _pick(alert.lon, home.lon, default=DEFAULT_LON),
        "source": SOURCE,
        "description": (alert.note or "").strip() or "SOS SafeR app",
        "hub_id": HUB_ID,
        "triggered_by": getattr(user, "email", None),
        "home_id": home.id,
        "home_name": home.name,
        "sos_id": alert.id,
    }


def _extract_incident_id(response: httpx.Response) -> Optional[str]:
    """``id`` of the created incident from common response shapes (``{id}``, ``{incident:{id}}``, ``{data:{id}}``)."""
    try:
        data = response.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    for key in ("id", "incident_id"):
        if data.get(key) not in (None, ""):
            return str(data[key])
    for nested in ("incident", "data"):
        inner = data.get(nested)
        if isinstance(inner, dict) and inner.get("id") not in (None, ""):
            return str(inner["id"])
    return None


async def forward_sos(runtime: Any, session: AsyncSession, home: Home, user: User, alert: SosAlert, incident_type: str = "panic") -> bool:
    """POST the alert to ``SAFER_INCIDENTS_URL``. Returns True on 2xx (alert updated + committed); never raises."""
    settings = runtime.settings
    url = (getattr(settings, "SAFER_INCIDENTS_URL", "") or "").strip()
    if not url:
        return False
    headers = {"Accept": "application/json", "User-Agent": "SafeR-Hub/sos"}
    token = (getattr(settings, "SAFER_INCIDENTS_TOKEN", "") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = build_incident_payload(home, user, alert, incident_type)
    try:
        async with runtime.ctx_for(CONTEXT_BRAND).http() as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("SOS %s could not be forwarded to %s: %s", alert.id, url, exc)
        return False
    except Exception:  # pylint: disable=broad-except
        logger.exception("SOS %s: unexpected error forwarding to %s", alert.id, url)
        return False
    if not 200 <= response.status_code < 300:
        logger.warning("SOS %s rejected by %s: HTTP %s %s", alert.id, url, response.status_code, response.text[:200])
        return False
    alert.forwarded = True
    alert.incident_id = _extract_incident_id(response)
    try:
        await session.commit()
    except Exception:  # pylint: disable=broad-except
        logger.exception("SOS %s forwarded but its status could not be saved", alert.id)
        await session.rollback()
        return True
    logger.info("SOS %s forwarded as incident %s", alert.id, alert.incident_id)
    return True


async def forward_later(runtime: Any, alert_id: str, user: User, incident_type: str = "panic") -> bool:
    """Background half of ``raise_sos``: reload the alert/home in a fresh session and forward them."""
    async with runtime.db.session() as session:
        alert = await session.get(SosAlert, alert_id)
        home = await session.get(Home, alert.home_id) if alert is not None else None
        if alert is None or home is None:
            logger.warning("SOS %s vanished before it could be forwarded", alert_id)
            return False
        return await forward_sos(runtime, session, home, user, alert, incident_type)


async def raise_sos(runtime: Any, session: AsyncSession, home: Home, user: User, body: SosIn) -> SosAlert:
    """Create an SOS alert: trip the home alarm, post an alarm message, publish ``sos.raised`` and queue forwarding."""
    alert = SosAlert(
        home_id=home.id, user_id=getattr(user, "id", None), lat=body.lat, lon=body.lon,
        note=(body.note or "").strip() or None, status="open",
    )
    session.add(alert)
    was_active = bool(home.alarm_active)
    home.alarm_active = True
    await session.flush()

    who = _display_name(user)
    details = [f"{who} a déclenché un SOS depuis l'application SafeR."]
    if alert.note:
        details.append(f"Message: {alert.note}")
    if alert.lat is not None and alert.lon is not None:
        details.append(f"Position: {alert.lat:.5f}, {alert.lon:.5f}")
    service = _device_service(runtime)
    await service.create_message(session, home.id, "alarm", SOS_TITLE, " ".join(details), severity="critical", publish=True)
    await session.commit()

    bus = runtime.bus
    await bus.publish(
        ev.HubEvent(
            ev.SOS_RAISED, home_id=home.id,
            payload={"sos_id": alert.id, "lat": alert.lat, "lon": alert.lon, "user_id": alert.user_id, "note": alert.note},
        )
    )
    if not was_active:
        await bus.publish(ev.HubEvent(ev.SECURITY_ALARM, home_id=home.id, payload={"active": True, "sos_id": alert.id}))
    logger.warning("SOS %s raised in home %s by %s", alert.id, home.id, getattr(user, "email", "?"))

    if (getattr(runtime.settings, "SAFER_INCIDENTS_URL", "") or "").strip():
        # Fire-and-forget: the request session closes with the response, so the task opens its own.
        runtime.spawn(forward_later(runtime, alert.id, user, body.incident_type), name=f"safer-hub-sos-forward-{alert.id}")
    return alert
