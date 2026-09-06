"""Demo adapter: virtual devices so the app can be exercised without hardware."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.hub.adapters.base import (
    AdapterContext, AdapterError, BrandAdapter, BrandInfo, DeviceDraft, DeviceRef, DeviceState,
    DiscoveredDevice, FormField, PairResult, PairingMethod, StreamInfo,
)
from app.hub.adapters.registry import registry
from app.hub.capabilities import (
    alarm_panel_caps, alarm_zone_caps, camera_caps, cover_caps, light_caps, lock_caps, sensor_caps, switch_caps,
    thermostat_caps,
)

BRAND_ID = "demo"

# Blueprint of the virtual home: (external_id, name, category, capabilities, initial state, parent)
BLUEPRINT: List[Dict[str, Any]] = [
    {"external_id": "demo-light-1", "name": "Lampe salon", "category": "light",
     "capabilities": light_caps(True, True, True), "state": {"switch": True, "brightness": 80, "color_temp": 4000,
                                                              "color": {"h": 30, "s": 40, "v": 100}, "work_mode": "white"}},
    {"external_id": "demo-plug-1", "name": "Prise TV", "category": "plug",
     "capabilities": switch_caps(1) + [{"code": "power", "type": "float", "writable": False, "unit": "W"}],
     "state": {"switch": False, "power": 0.0}},
    {"external_id": "demo-switch-2", "name": "Interrupteur cuisine", "category": "switch",
     "capabilities": switch_caps(2), "state": {"switch_1": True, "switch_2": False}},
    {"external_id": "demo-cover-1", "name": "Volet chambre", "category": "cover",
     "capabilities": cover_caps(), "state": {"position": 100, "control": "stop"}},
    {"external_id": "demo-thermo-1", "name": "Climatisation", "category": "thermostat",
     "capabilities": thermostat_caps(), "state": {"temp_current": 27.5, "temp_set": 24.0, "mode": "cool", "humidity_current": 71}},
    {"external_id": "demo-door-1", "name": "Porte d'entrée", "category": "sensor_contact",
     "capabilities": sensor_caps("sensor_contact"), "state": {"contact": False, "battery": 92}},
    {"external_id": "demo-pir-1", "name": "Détecteur couloir", "category": "sensor_motion",
     "capabilities": sensor_caps("sensor_motion"), "state": {"motion": False, "battery": 78}},
    {"external_id": "demo-smoke-1", "name": "Détecteur fumée cuisine", "category": "sensor_smoke",
     "capabilities": sensor_caps("sensor_smoke"), "state": {"smoke": False, "battery": 100}},
    {"external_id": "demo-water-1", "name": "Capteur inondation", "category": "sensor_water",
     "capabilities": sensor_caps("sensor_water"), "state": {"water_leak": False, "battery": 88}},
    {"external_id": "demo-cam-1", "name": "Caméra entrée", "category": "camera",
     "capabilities": camera_caps(ptz=True, siren=True, light=True),
     "state": {"motion": False, "recording": True, "siren": False, "light": False,
               "stream_main": "rtsp://demo.safer.local:554/cam1/main", "stream_sub": "rtsp://demo.safer.local:554/cam1/sub",
               "snapshot": "https://demo.safer.local/cam1/snapshot.jpg"}},
    {"external_id": "demo-lock-1", "name": "Serrure entrée", "category": "lock",
     "capabilities": lock_caps(), "state": {"locked": True, "door": False, "battery": 65}},
    {"external_id": "demo-panel-1", "name": "Centrale d'alarme", "category": "alarm_panel",
     "capabilities": alarm_panel_caps(), "state": {"arm_mode": "disarmed", "alarm": False, "triggered_zone": "", "ready": True}},
    {"external_id": "demo-zone-1", "name": "Zone salon", "category": "alarm_zone", "parent": "demo-panel-1",
     "capabilities": alarm_zone_caps(), "state": {"open": False, "alarm": False, "bypass": False, "tamper": False, "battery": 90, "signal": 80}},
]


class DemoAdapter(BrandAdapter):
    """Virtual devices with in-memory state (per external id)."""

    brand_id = BRAND_ID

    def __init__(self) -> None:
        self._state: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def info(self) -> BrandInfo:
        return BrandInfo(
            id=BRAND_ID,
            name="Appareils de démonstration",
            vendor="SafeR",
            description="Appareils virtuels pour découvrir l'application sans matériel.",
            protocols=["demo"],
            categories=sorted({item["category"] for item in BLUEPRINT}),
            methods=[
                PairingMethod(
                    id="virtual",
                    title="Ajouter la maison de démonstration",
                    description="Crée un jeu complet d'appareils virtuels (lumière, prise, capteurs, caméra, serrure, centrale).",
                    fields=[
                        FormField(name="prefix", label="Préfixe des noms", type="text", required=False, default="",
                                  help="Optionnel, ajouté devant le nom de chaque appareil."),
                    ],
                    supports_discovery=True,
                    icon="science",
                )
            ],
            icon="science",
            color="#7C3AED",
        )

    async def discover(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> List[DiscoveredDevice]:
        self.method(method_id)
        return [
            DiscoveredDevice(external_id=item["external_id"], name=item["name"], category=item["category"],
                             model="SafeR Virtual", manufacturer="SafeR", address="virtual")
            for item in BLUEPRINT
        ]

    async def pair(self, method_id: str, payload: Dict[str, Any], ctx: AdapterContext) -> PairResult:
        self.method(method_id)
        prefix = (payload.get("prefix") or "").strip()
        drafts: List[DeviceDraft] = []
        for item in BLUEPRINT:
            self._state.setdefault(item["external_id"], dict(item["state"]))
            drafts.append(
                DeviceDraft(
                    external_id=item["external_id"],
                    name=f"{prefix} {item['name']}".strip(),
                    category=item["category"],
                    protocol="demo",
                    model="SafeR Virtual",
                    manufacturer="SafeR",
                    firmware="1.0.0",
                    capabilities=item["capabilities"],
                    state=dict(self._state[item["external_id"]]),
                    config={"virtual": True},
                    parent_external_id=item.get("parent"),
                )
            )
        return PairResult(devices=drafts, message=f"{len(drafts)} appareils virtuels ajoutés")

    async def refresh(self, device: DeviceRef, ctx: AdapterContext) -> DeviceState:
        state = self._state.get(device.external_id)
        if state is None:
            blueprint = next((i for i in BLUEPRINT if i["external_id"] == device.external_id), None)
            if blueprint is None:
                raise AdapterError("Unknown virtual device", "not_found")
            state = self._state.setdefault(device.external_id, dict(blueprint["state"]))
        return DeviceState(online=True, state=dict(state))

    async def send_command(self, device: DeviceRef, code: str, value: Any, ctx: AdapterContext) -> Dict[str, Any]:
        async with self._lock:
            state = self._state.setdefault(device.external_id, dict(device.state))
            state[code] = value
            partial: Dict[str, Any] = {code: value}
            if code == "control":
                state["position"] = {"open": 100, "close": 0}.get(value, state.get("position", 0))
                partial["position"] = state["position"]
            if code == "switch" and device.category == "plug":
                state["power"] = 42.5 if value else 0.0
                partial["power"] = state["power"]
            if code == "arm_mode":
                state["alarm"] = False
                partial["alarm"] = False
            if code == "ptz":
                partial = {}
            return partial

    async def stream(self, device: DeviceRef, quality: str, ctx: AdapterContext) -> Optional[StreamInfo]:
        if device.category not in ("camera", "nvr", "doorbell"):
            return None
        url = device.state.get("stream_main" if quality != "sub" else "stream_sub") or "rtsp://demo.safer.local:554/demo"
        return StreamInfo(url=url, type="rtsp")

    async def snapshot(self, device: DeviceRef, ctx: AdapterContext) -> Optional[bytes]:
        if device.category not in ("camera", "nvr", "doorbell"):
            return None
        # Smallest valid JPEG (1x1 grey pixel)
        return bytes.fromhex(
            "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f14"
            "1d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffc0000b080001000101011100"
            "ffc4001f0000010501010101010100000000000000000102030405060708090a0bffc400b5100002010303020403050504040000"
            "017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a"
            "3435363738393a434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a9293949596"
            "9798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2"
            "f3f4f5f6f7f8f9faffda0008010100003f00fbd3ffd9"
        )

    # Test/QA helper: simulate a sensor trip from the outside (used by tests and the demo seed)
    async def simulate(self, external_id: str, state: Dict[str, Any], ctx: AdapterContext) -> None:
        """Update virtual state and push it to the hub as if the device reported it."""
        async with self._lock:
            current = self._state.setdefault(external_id, {})
            current.update(state)
        await ctx.emit("state", external_id, {"state": dict(state), "online": True})


registry.register(DemoAdapter())
