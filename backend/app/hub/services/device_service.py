"""Device service: persists pairing results, applies state, records events/messages, drives adapters."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub import events as ev
from app.hub.adapters.base import AdapterError, BrandAdapter, DeviceRef, DeviceState, PairResult, StreamInfo
from app.hub.adapters.registry import registry
from app.hub.capabilities import NOTABLE_CODES, coerce_value, find_capability
from app.hub.models import Device, DeviceEvent, Home, Integration, Message, utcnow

logger = logging.getLogger("safer.hub.devices")

# Which sensor codes trip the software alarm in each armed mode (Tuya "Security" behaviour)
ARMED_TRIGGERS = {
    "armed_away": {"contact", "motion", "smoke", "gas", "water_leak", "co", "tamper"},
    "armed_home": {"contact", "smoke", "gas", "water_leak", "co", "tamper"},
    "armed_night": {"contact", "smoke", "gas", "water_leak", "co", "tamper"},
    "disarmed": {"smoke", "gas", "water_leak", "co"},  # life-safety sensors always alarm
}


def _serialize_device(device: Device) -> Dict[str, Any]:
    return {
        "id": device.id,
        "home_id": device.home_id,
        "room_id": device.room_id,
        "name": device.name,
        "brand": device.brand,
        "protocol": device.protocol,
        "category": device.category,
        "online": device.online,
        "state": dict(device.state or {}),
        "capabilities": list(device.capabilities or []),
        "icon": device.icon,
        "parent_id": device.parent_id,
        "model": device.model,
    }


class DeviceService:
    """All device mutations go through here so events/messages stay consistent."""

    def __init__(self, runtime: Any):
        self.runtime = runtime

    # ----------------------------------------------------------------- helpers
    def adapter(self, brand: str) -> BrandAdapter:
        """Adapter for a brand or AdapterError(unsupported)."""
        adapter = registry.get(brand)
        if adapter is None:
            raise AdapterError(f"No adapter for brand '{brand}'", "unsupported")
        return adapter

    async def integration_for(self, session: AsyncSession, device: Device) -> Optional[Integration]:
        """Integration row for a device (or None)."""
        if not device.integration_id:
            return None
        return await session.get(Integration, device.integration_id)

    def to_ref(self, device: Device, integration: Optional[Integration] = None, parent: Optional[Device] = None) -> DeviceRef:
        """Build the adapter-facing reference with decrypted credentials."""
        vault = self.runtime.vault
        return DeviceRef(
            id=device.id,
            external_id=device.external_id,
            brand=device.brand,
            protocol=device.protocol,
            category=device.category,
            config=dict(device.config or {}),
            credentials=vault.decrypt(device.credentials_enc),
            integration_config=dict(integration.config or {}) if integration else {},
            integration_credentials=vault.decrypt(integration.credentials_enc) if integration else {},
            parent_external_id=parent.external_id if parent else None,
            state=dict(device.state or {}),
            capabilities=list(device.capabilities or []),
            name=device.name,
        )

    async def ref_for(self, session: AsyncSession, device: Device) -> DeviceRef:
        """Load integration + parent and build a DeviceRef."""
        integration = await self.integration_for(session, device)
        parent = await session.get(Device, device.parent_id) if device.parent_id else None
        ref = self.to_ref(device, integration, parent)
        # Channel/zone devices inherit host credentials from their parent when they have none
        if parent is not None:
            parent_ref = self.to_ref(parent, integration)
            for key, value in parent_ref.config.items():
                ref.config.setdefault(key, value)
            for key, value in parent_ref.credentials.items():
                ref.credentials.setdefault(key, value)
        return ref

    # ----------------------------------------------------------------- pairing
    async def materialize(
        self,
        session: AsyncSession,
        home_id: str,
        room_id: Optional[str],
        brand: str,
        result: PairResult,
        selected_external_ids: Optional[List[str]] = None,
    ) -> Tuple[List[Device], Optional[Integration]]:
        """Upsert integration + devices from a PairResult and emit ``device.added`` events."""
        vault = self.runtime.vault
        integration: Optional[Integration] = None
        if result.integration is not None:
            integration = (
                await session.execute(
                    select(Integration).where(Integration.home_id == home_id, Integration.key == result.integration.key)
                )
            ).scalar_one_or_none()
            if integration is None:
                integration = Integration(home_id=home_id, brand=brand, key=result.integration.key)
                session.add(integration)
            integration.name = result.integration.name or integration.name
            integration.config = dict(result.integration.config or {})
            if result.integration.credentials:
                integration.credentials_enc = vault.encrypt(result.integration.credentials)
            await session.flush()

        selected = set(selected_external_ids) if selected_external_ids else None
        drafts = [d for d in result.devices if selected is None or d.external_id in selected or d.parent_external_id is None and _has_selected_child(d, result.devices, selected)]
        # Parents first so children can resolve parent_id
        drafts.sort(key=lambda d: 0 if d.parent_external_id is None else 1)
        by_external: Dict[str, Device] = {}
        devices: List[Device] = []
        for draft in drafts:
            device = (
                await session.execute(
                    select(Device).where(Device.home_id == home_id, Device.brand == brand, Device.external_id == draft.external_id)
                )
            ).scalar_one_or_none()
            created = device is None
            if device is None:
                device = Device(home_id=home_id, brand=brand, external_id=draft.external_id, name=draft.name, room_id=room_id)
                session.add(device)
            device.protocol = draft.protocol
            device.category = draft.category
            device.model = draft.model
            device.manufacturer = draft.manufacturer
            device.firmware = draft.firmware
            device.capabilities = list(draft.capabilities)
            device.state = {**(device.state or {}), **draft.state}
            device.config = dict(draft.config)
            device.online = draft.online
            device.icon = draft.icon or device.icon
            device.last_seen_at = utcnow()
            if draft.credentials:
                device.credentials_enc = vault.encrypt(draft.credentials)
            if integration is not None:
                device.integration_id = integration.id
            if draft.parent_external_id:
                parent = by_external.get(draft.parent_external_id)
                if parent is None:
                    parent = (
                        await session.execute(
                            select(Device).where(
                                Device.home_id == home_id, Device.brand == brand, Device.external_id == draft.parent_external_id
                            )
                        )
                    ).scalar_one_or_none()
                if parent is not None:
                    device.parent_id = parent.id
            await session.flush()
            by_external[device.external_id] = device
            devices.append(device)
            if created:
                await self.runtime.bus.publish(
                    ev.HubEvent(ev.DEVICE_ADDED, home_id=home_id, device_id=device.id, payload={"device": _serialize_device(device)})
                )
        await session.commit()
        return devices, integration

    # ----------------------------------------------------------------- state
    async def apply_state(
        self,
        session: AsyncSession,
        device: Device,
        state: Optional[Dict[str, Any]],
        online: Optional[bool] = None,
        source: str = "adapter",
    ) -> List[DeviceEvent]:
        """Merge state, record notable events/messages, run the software alarm, publish on the bus."""
        old_state = dict(device.state or {})
        new_state = dict(old_state)
        changed: Dict[str, Any] = {}
        for code, value in (state or {}).items():
            if old_state.get(code) != value or code not in old_state:
                changed[code] = value
            new_state[code] = value
        was_online = device.online
        if online is not None:
            device.online = online
        device.state = new_state
        device.last_seen_at = utcnow()

        recorded: List[DeviceEvent] = []
        for code, value in changed.items():
            rule = NOTABLE_CODES.get(code)
            if rule is None:
                continue
            if rule["when"] is not None and value != rule["when"]:
                continue
            if code not in old_state and value in (False, None, 0):
                continue  # initial sync of an idle sensor is not an event
            event = DeviceEvent(device_id=device.id, home_id=device.home_id, type=code, payload={"value": value, "source": source})
            session.add(event)
            recorded.append(event)
            if rule["kind"] in ("alarm", "home") and rule["when"] is not None:
                await self.create_message(
                    session, device.home_id, rule["kind"], f"{rule['title']} — {device.name}",
                    _describe(code, value), device_id=device.id, severity=rule["severity"], publish=False,
                )
        if online is not None and was_online != online:
            event = DeviceEvent(device_id=device.id, home_id=device.home_id, type="online", payload={"value": online})
            session.add(event)
            recorded.append(event)
            if not online:
                await self.create_message(
                    session, device.home_id, "notice", f"Appareil hors ligne — {device.name}",
                    "L'appareil ne répond plus.", device_id=device.id, severity="warning", publish=False,
                )
        await session.flush()
        await self._evaluate_security(session, device, changed)
        await session.commit()

        bus = self.runtime.bus
        await bus.publish(
            ev.HubEvent(ev.DEVICE_STATE, home_id=device.home_id, device_id=device.id,
                        payload={"state": new_state, "online": device.online, "changed": changed})
        )
        for event in recorded:
            await bus.publish(
                ev.HubEvent(ev.DEVICE_EVENT, home_id=device.home_id, device_id=device.id,
                            payload={"event": {"id": event.id, "type": event.type, "payload": event.payload,
                                               "created_at": event.created_at.isoformat() if event.created_at else None}})
            )
        return recorded

    async def _evaluate_security(self, session: AsyncSession, device: Device, changed: Dict[str, Any]) -> None:
        """Software alarm panel: trip the home alarm when armed sensors fire, mirror hardware panels."""
        home = await session.get(Home, device.home_id)
        if home is None:
            return
        triggered = False
        if device.category == "alarm_panel":
            if changed.get("alarm") is True:
                triggered = True
            if "arm_mode" in changed and changed["arm_mode"] in ARMED_TRIGGERS and changed["arm_mode"] != home.security_mode:
                home.security_mode = changed["arm_mode"]
                home.security_changed_at = utcnow()
                await self.runtime.bus.publish(
                    ev.HubEvent(ev.SECURITY_MODE, home_id=home.id, payload={"mode": home.security_mode, "source": device.id})
                )
        else:
            codes = ARMED_TRIGGERS.get(home.security_mode, set())
            for code in codes:
                if changed.get(code) is True and device.category != "alarm_zone" or (device.category == "alarm_zone" and changed.get("alarm") is True):
                    triggered = True
                    break
        if triggered and not home.alarm_active:
            home.alarm_active = True
            home.alarm_device_id = device.id
            await self.create_message(
                session, home.id, "alarm", f"🚨 Alarme — {device.name}", "Une alarme a été déclenchée dans votre domicile.",
                device_id=device.id, severity="critical", publish=True,
            )
            await self.runtime.bus.publish(
                ev.HubEvent(ev.SECURITY_ALARM, home_id=home.id, device_id=device.id, payload={"active": True})
            )

    async def create_message(
        self,
        session: AsyncSession,
        home_id: str,
        kind: str,
        title: str,
        body: str = "",
        device_id: Optional[str] = None,
        severity: str = "info",
        publish: bool = True,
    ) -> Message:
        """Add a message-center entry and publish ``message.new``."""
        message = Message(home_id=home_id, kind=kind, title=title, body=body, device_id=device_id, severity=severity)
        session.add(message)
        await session.flush()
        payload = {"message": {"id": message.id, "home_id": home_id, "kind": kind, "title": title, "body": body,
                               "device_id": device_id, "severity": severity, "read": False,
                               "created_at": (message.created_at or utcnow()).isoformat()}}
        if publish:
            await self.runtime.bus.publish(ev.HubEvent(ev.MESSAGE_NEW, home_id=home_id, device_id=device_id, payload=payload))
        else:
            self.runtime.bus.publish_nowait(ev.HubEvent(ev.MESSAGE_NEW, home_id=home_id, device_id=device_id, payload=payload))
        return message

    # ----------------------------------------------------------------- adapter operations
    async def refresh(self, session: AsyncSession, device: Device) -> Device:
        """Ask the adapter for fresh state and apply it."""
        adapter = self.adapter(device.brand)
        ref = await self.ref_for(session, device)
        try:
            result: DeviceState = await adapter.refresh(ref, self.runtime.ctx_for(device.brand))
        except AdapterError as exc:
            if exc.code == "unreachable":
                await self.apply_state(session, device, None, online=False)
            raise
        await self.apply_state(session, device, result.state, online=result.online)
        return device

    async def command(self, session: AsyncSession, device: Device, code: str, value: Any) -> Device:
        """Validate and execute one command."""
        capability = find_capability(device.capabilities or [], code)
        if capability is None:
            raise AdapterError(f"Unknown capability '{code}'", "invalid_input")
        if not capability.get("writable"):
            raise AdapterError(f"Capability '{code}' is read-only", "invalid_input")
        try:
            value = coerce_value(capability, value)
        except ValueError as exc:
            raise AdapterError(str(exc), "invalid_input") from exc
        adapter = self.adapter(device.brand)
        ref = await self.ref_for(session, device)
        partial = await adapter.send_command(ref, code, value, self.runtime.ctx_for(device.brand))
        new_state = {code: value}
        if partial:
            new_state.update(partial)
        await self.apply_state(session, device, new_state, online=True, source="command")
        return device

    async def stream(self, session: AsyncSession, device: Device, quality: str = "main") -> Optional[StreamInfo]:
        """Stream info from the adapter."""
        adapter = self.adapter(device.brand)
        ref = await self.ref_for(session, device)
        return await adapter.stream(ref, quality, self.runtime.ctx_for(device.brand))

    async def snapshot(self, session: AsyncSession, device: Device) -> Optional[bytes]:
        """Snapshot bytes from the adapter."""
        adapter = self.adapter(device.brand)
        ref = await self.ref_for(session, device)
        return await adapter.snapshot(ref, self.runtime.ctx_for(device.brand))

    async def remove(self, session: AsyncSession, device: Device) -> None:
        """Unpair (best effort) and delete a device with its children."""
        adapter = registry.get(device.brand)
        if adapter is not None:
            try:
                ref = await self.ref_for(session, device)
                await adapter.unpair(ref, self.runtime.ctx_for(device.brand))
            except Exception:  # pylint: disable=broad-except
                logger.warning("unpair failed for %s/%s (continuing)", device.brand, device.external_id, exc_info=True)
        children = (await session.execute(select(Device).where(Device.parent_id == device.id))).scalars().all()
        home_id, device_id = device.home_id, device.id
        for child in children:
            await session.delete(child)
        await session.delete(device)
        await session.commit()
        await self.runtime.bus.publish(ev.HubEvent(ev.DEVICE_REMOVED, home_id=home_id, device_id=device_id))

    # ----------------------------------------------------------------- push from adapters
    async def handle_push(self, brand: str, external_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """Entry point for adapter subscriptions (opens its own session)."""
        async with self.runtime.db.session() as session:
            devices = (
                await session.execute(select(Device).where(Device.brand == brand, Device.external_id == external_id))
            ).scalars().all()
            for device in devices:
                if event_type == "state":
                    await self.apply_state(session, device, payload.get("state") or {}, online=payload.get("online"))
                elif event_type == "event":
                    etype = payload.get("type", "event")
                    event = DeviceEvent(device_id=device.id, home_id=device.home_id, type=etype,
                                        payload={k: v for k, v in payload.items() if k != "type"})
                    session.add(event)
                    await session.commit()
                    await self.runtime.bus.publish(
                        ev.HubEvent(ev.DEVICE_EVENT, home_id=device.home_id, device_id=device.id,
                                    payload={"event": {"id": event.id, "type": etype, "payload": event.payload}})
                    )


def _has_selected_child(draft: Any, drafts: List[Any], selected: Optional[set]) -> bool:
    if not selected:
        return False
    return any(d.parent_external_id == draft.external_id and d.external_id in selected for d in drafts)


def _describe(code: str, value: Any) -> str:
    texts = {
        "motion": "Un mouvement a été détecté.",
        "contact": "Une porte ou une fenêtre a été ouverte.",
        "smoke": "De la fumée a été détectée. Vérifiez immédiatement.",
        "co": "Monoxyde de carbone détecté. Aérez et évacuez.",
        "water_leak": "Une fuite d'eau a été détectée.",
        "gas": "Une fuite de gaz a été détectée. Évacuez.",
        "alarm": "L'alarme s'est déclenchée.",
        "tamper": "Le boîtier de l'appareil a été ouvert.",
        "doorbell_pressed": "Quelqu'un a appuyé sur la sonnette.",
    }
    if code == "locked":
        return "La serrure a été verrouillée." if value else "La serrure a été déverrouillée."
    if code == "arm_mode":
        return f"Mode de sécurité: {value}"
    return texts.get(code, f"{code}: {value}")


def now_iso() -> str:
    """ISO timestamp helper for payloads."""
    return datetime.utcnow().isoformat()
