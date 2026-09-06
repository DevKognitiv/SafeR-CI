"""SIA DC-09 receiver tests: CRC, frame codec, SIA-DCS / Contact ID parsing, event mapping, ACK/NAK, TCP server."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import pytest

from app.hub.services import sia_receiver as sia
from app.hub.services.sia_receiver import (
    SiaEvent, SiaFrameError, SiaReceiver, build_ack, build_nak, crc16, encode_frame, map_event, parse_cid, parse_frame,
    parse_sia_dcs,
)
from app.hub.tests.conftest import make_settings


def reference_crc(data: bytes) -> int:
    """Independent table-driven CRC-16/ARC (poly 0x8005 reflected -> 0xA001, init 0, no xor-out)."""
    table = []
    for index in range(256):
        value = index
        for _ in range(8):
            value = (value >> 1) ^ 0xA001 if value & 1 else value >> 1
        table.append(value)
    crc = 0
    for byte in data:
        crc = (crc >> 8) ^ table[(crc ^ byte) & 0xFF]
    return crc


class FakeDeviceService:
    """Records ``handle_push`` calls like ``DeviceService`` would receive them."""

    def __init__(self) -> None:
        self.pushes: List[Tuple[str, str, str, Dict[str, Any]]] = []

    async def handle_push(self, brand: str, external_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        self.pushes.append((brand, external_id, event_type, payload))

    def states(self, external_id: str) -> List[Dict[str, Any]]:
        return [p["state"] for _, ext, kind, p in self.pushes if kind == "state" and ext == external_id]

    def events(self, external_id: str) -> List[str]:
        return [p["type"] for _, ext, kind, p in self.pushes if kind == "event" and ext == external_id]


class FakeRuntime:
    def __init__(self, **settings: Any) -> None:
        self.settings = make_settings(**settings)
        self.services = {"devices": FakeDeviceService()}


@pytest.fixture
def runtime() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def receiver(runtime: FakeRuntime) -> SiaReceiver:
    return SiaReceiver(runtime, port=0)


STAMP = datetime(2026, 9, 6, 12, 34, 56, tzinfo=timezone.utc)


# ----------------------------------------------------------------------------- codec
def test_crc16_known_vectors():
    assert crc16(b"123456789") == 0xBB3D  # CRC-16/ARC check value
    assert crc16(b"") == 0
    body = b'"SIA-DCS"0002R0L0#1234[#1234|Nri1/BA01]_12:34:56,09-06-2026'
    assert crc16(body) == reference_crc(body)
    for sample in (b"A", b"\x00\xff", b'"NULL"0001R0L0#AB12[]'):
        assert crc16(sample) == reference_crc(sample)


def test_encode_frame_layout_and_parse_roundtrip():
    frame = encode_frame("SIA-DCS", 2, 0, 0, "1234", "#1234|Nri1/BA01", STAMP)
    body = b'"SIA-DCS"0002R0L0#1234[#1234|Nri1/BA01]_12:34:56,09-06-2026'
    assert frame == b"\n" + f"{reference_crc(body):04X}".encode() + f"{len(body):04X}".encode() + body + b"\r"
    assert frame[9:10] == b'"' and frame[5:6] == b"0"  # 4 hex CRC then 0LLL length
    parsed = parse_frame(frame)
    assert parsed.crc_ok and parsed.length_ok and not parsed.encrypted
    assert parsed.msg_type == "SIA-DCS" and parsed.sequence == "0002" and parsed.receiver == "0" and parsed.line == "0"
    assert parsed.account == "1234" and parsed.data == "#1234|Nri1/BA01" and parsed.timestamp == STAMP
    # receiver/line as hex ints, lower-case hex tolerated, extension fields kept
    other = encode_frame("ADM-CID", "17", 0x1A, 0xF, "abcd", "#ABCD|1130 01 003", "01:02:03,01-31-2026")
    assert b'"ADM-CID"0017R1ALF#ABCD[#ABCD|1130 01 003]_01:02:03,01-31-2026' in other
    lower_body = b'"ADM-CID"0017R1aLf#abcd[#ABCD|1130 01 003]_01:02:03,01-31-2026'
    lower = b"\n" + f"{crc16(lower_body):04x}{len(lower_body):04x}".encode() + lower_body + b"\r"
    reparsed = parse_frame(lower)
    assert reparsed.crc_ok and reparsed.receiver == "1A" and reparsed.line == "F" and reparsed.account == "ABCD"
    ext = parse_frame(b'\n' + b'0000002F"SIA-DCS"0003R0L0#1234[#1234|NRP0000][X1234]')
    assert ext.extensions == ["X1234"] and ext.timestamp is None


def test_parse_frame_without_timestamp_or_header():
    frame = encode_frame("NULL", 1, "0", "0", "1234", "", with_timestamp=False)
    assert frame.endswith(b"[]\r")
    parsed = parse_frame(frame)
    assert parsed.crc_ok and parsed.timestamp is None and parsed.msg_type == "NULL"
    bare = parse_frame(b'"SIA-DCS"0009R0L0#77[#77|NCL03]')
    assert bare.crc is None and bare.crc_ok and bare.length is None and bare.length_ok and bare.account == "77"
    binary_body = b'"NULL"0004R0L0#1234[]'
    binary = parse_frame(b"\n" + crc16(binary_body).to_bytes(2, "big") + f"{len(binary_body):04X}".encode() + binary_body + b"\r")
    assert binary.crc_ok and binary.account == "1234"
    for junk in (b"", b"\n\r", b"hello world\r", b'\n1234000A"SIA-DCS"broken\r'):
        with pytest.raises(SiaFrameError):
            parse_frame(junk)


def test_parse_frame_crc_mismatch_and_encrypted():
    frame = bytearray(encode_frame("SIA-DCS", 5, 0, 0, "1234", "#1234|Nri1/BA01", STAMP))
    frame[1:5] = b"0000"
    parsed = parse_frame(bytes(frame))
    assert not parsed.crc_ok and parsed.crc == 0 and parsed.crc_expected == crc16(parsed.body.encode())
    encrypted = parse_frame(encode_frame("*SIA-DCS", 5, 0, 0, "1234", "0A1B2C3D", STAMP))
    assert encrypted.encrypted and encrypted.msg_type == "SIA-DCS" and encrypted.crc_ok


# ----------------------------------------------------------------------------- data parsing
def test_parse_sia_dcs_variants():
    assert parse_sia_dcs("#1234|Nri1/BA01") == [SiaEvent("sia", "BA", "N", "01", "1", "", "", "1234")]
    events = parse_sia_dcs("#1234|NBA01^Porte avant^|Nri2/id7/OP07|Oti12:00/TA03", "9999")
    assert [(e.code, e.zone, e.area, e.user, e.text, e.qualifier) for e in events] == [
        ("BA", "01", "", "", "Porte avant", "N"), ("OP", "07", "2", "7", "", "N"), ("TA", "03", "", "", "", "O"),
    ]
    assert all(e.account == "1234" for e in events)
    # Without the #acct prefix the frame account is used; OP must not be mistaken for the "O" qualifier
    assert parse_sia_dcs("Nri1/NL02|OP01", "AB12") == [
        SiaEvent("sia", "NL", "N", "02", "1", "", "", "AB12"), SiaEvent("sia", "OP", "N", "01", "", "", "", "AB12"),
    ]
    assert parse_sia_dcs("#1234|") == [] and parse_sia_dcs("garbage") == []


def test_parse_adm_cid():
    assert parse_cid("#1234|1130 01 003") == [SiaEvent("cid", "130", "1", "003", "01", "", "", "1234")]
    assert parse_cid("#1234|3401 02 012") == [SiaEvent("cid", "401", "3", "012", "02", "012", "", "1234")]
    assert parse_cid("6302 00 000", "77AA") == [SiaEvent("cid", "302", "6", "000", "00", "", "", "77AA")]
    assert parse_cid("#1234|113001003")[0].code == "130"
    assert parse_cid("#1234|nothing") == []


@pytest.mark.parametrize(
    "code,category,state,event_type",
    [
        ("BA", "burglary", {"alarm": True, "triggered_zone": "Zone 1"}, "burglary"),
        ("BR", "restore", {"alarm": False}, "restore"),
        ("FA", "fire", {"alarm": True, "triggered_zone": "Zone 1"}, "fire"),
        ("FR", "restore", {"alarm": False}, "restore"),
        ("PA", "panic", {"alarm": True, "triggered_zone": "Zone 1"}, "panic"),
        ("PR", "restore", {"alarm": False}, "restore"),
        ("TA", "tamper", {"tamper": True}, "tamper"),
        ("TR", "tamper_restore", {"tamper": False}, "tamper_restore"),
        ("CL", "arm_away", {"arm_mode": "armed_away"}, None),
        ("CG", "arm_away", {"arm_mode": "armed_away"}, None),
        ("CQ", "arm_away", {"arm_mode": "armed_away"}, None),
        ("NL", "arm_night", {"arm_mode": "armed_night"}, None),
        ("CF", "arm_home", {"arm_mode": "armed_home"}, None),
        ("CP", "arm_home", {"arm_mode": "armed_home"}, None),
        ("OP", "disarm", {"arm_mode": "disarmed", "alarm": False}, None),
        ("OG", "disarm", {"arm_mode": "disarmed", "alarm": False}, None),
        ("OQ", "disarm", {"arm_mode": "disarmed", "alarm": False}, None),
        ("BB", "bypass", {}, "bypass"),
        ("YT", "battery_low", {}, "battery_low"),
        ("YR", "battery_ok", {}, "battery_ok"),
        ("AT", "ac_loss", {}, "ac_loss"),
        ("AR", "ac_restore", {}, "ac_restore"),
        ("WA", "water", {"alarm": True, "triggered_zone": "Zone 1"}, "water"),
        ("GA", "gas", {"alarm": True, "triggered_zone": "Zone 1"}, "gas"),
        ("QQ", "unknown", {}, "sia"),
        ("KT", "trouble", {}, "trouble"),
    ],
)
def test_sia_code_mapping_table(code: str, category: str, state: Dict[str, Any], event_type: Any):
    update = map_event(SiaEvent("sia", code, "N", zone="01", area="1"))
    assert update.category == category and update.state == state and not update.ignored
    if event_type is None:
        assert update.events == []
    else:
        assert [e["type"] for e in update.events] == [event_type]
        assert update.events[0]["code"] == code and update.events[0]["zone"] == "01"


def test_test_reports_are_ignored_and_text_is_used_as_zone():
    assert map_event(SiaEvent("sia", "RP", "N", zone="0000")).ignored
    assert map_event(SiaEvent("cid", "602", "1", zone="000")).ignored
    named = map_event(SiaEvent("sia", "BA", "N", zone="04", text="Fenêtre cuisine"))
    assert named.state["triggered_zone"] == "Fenêtre cuisine"
    heuristic = map_event(SiaEvent("sia", "XX", "N"))
    assert heuristic.category == "test" and heuristic.ignored


@pytest.mark.parametrize(
    "code,qualifier,category,state,event_type",
    [
        ("130", "1", "burglary", {"alarm": True, "triggered_zone": "Zone 3"}, "burglary"),
        ("130", "3", "restore", {"alarm": False}, "restore"),
        ("110", "1", "fire", {"alarm": True, "triggered_zone": "Zone 3"}, "fire"),
        ("120", "1", "panic", {"alarm": True, "triggered_zone": "Zone 3"}, "panic"),
        ("137", "1", "tamper", {"tamper": True}, "tamper"),
        ("383", "3", "tamper_restore", {"tamper": False}, "tamper_restore"),
        ("401", "3", "arm_away", {"arm_mode": "armed_away"}, None),
        ("401", "1", "disarm", {"arm_mode": "disarmed", "alarm": False}, None),
        ("402", "3", "arm_away", {"arm_mode": "armed_away"}, None),
        ("441", "3", "arm_home", {"arm_mode": "armed_home"}, None),
        ("441", "1", "disarm", {"arm_mode": "disarmed", "alarm": False}, None),
        ("570", "1", "bypass", {}, "bypass"),
        ("570", "3", "unbypass", {}, "unbypass"),
        ("302", "1", "battery_low", {}, "battery_low"),
        ("302", "3", "battery_ok", {}, "battery_ok"),
        ("301", "1", "ac_loss", {}, "ac_loss"),
        ("301", "3", "ac_restore", {}, "ac_restore"),
        ("162", "6", "co", {"alarm": True, "triggered_zone": "Zone 3"}, "co"),
        ("199", "1", "burglary", {"alarm": True, "triggered_zone": "Zone 3"}, "burglary"),
        ("399", "1", "trouble", {}, "trouble"),
        ("499", "3", "arm_away", {"arm_mode": "armed_away"}, None),
    ],
)
def test_contact_id_mapping_table(code: str, qualifier: str, category: str, state: Dict[str, Any], event_type: Any):
    update = map_event(SiaEvent("cid", code, qualifier, zone="003", area="01"))
    assert update.category == category and update.state == state
    assert [e["type"] for e in update.events] == ([event_type] if event_type else [])


# ----------------------------------------------------------------------------- receiver
async def test_handle_line_acks_and_applies_state(receiver: SiaReceiver, runtime: FakeRuntime):
    devices: FakeDeviceService = runtime.services["devices"]
    reply = await receiver.handle_line(encode_frame("SIA-DCS", 7, 0, 0, "1234", "#1234|Nri1/BA01^Salon^", STAMP))
    ack = parse_frame(reply)
    assert ack.msg_type == "ACK" and ack.sequence == "0007" and ack.receiver == "0" and ack.line == "0"
    assert ack.account == "1234" and ack.data == "" and ack.crc_ok and ack.timestamp is not None
    assert reply.startswith(b"\n") and reply.endswith(b"\r") and b'"ACK"0007R0L0#1234[]_' in reply
    assert devices.pushes[0][:3] == ("ajax", "sia:1234", "state")
    assert devices.pushes[0][3] == {"state": {"alarm": True, "triggered_zone": "Salon"}, "online": True}
    assert devices.pushes[1][:3] == ("ajax", "sia:1234", "event")
    assert devices.pushes[1][3]["type"] == "burglary" and devices.pushes[1][3]["text"] == "Salon"

    await receiver.handle_line(encode_frame("SIA-DCS", 8, 0, 0, "1234", "#1234|Nri1/id2/CL02", STAMP))
    await receiver.handle_line(encode_frame("ADM-CID", 9, 0, 0, "1234", "#1234|1401 01 002", STAMP))
    await receiver.handle_line(encode_frame("SIA-DCS", 10, 0, 0, "1234", "#1234|Nri1/RP0000", STAMP))
    assert devices.states("sia:1234")[1:] == [{"arm_mode": "armed_away"}, {"arm_mode": "disarmed", "alarm": False}]
    assert receiver.stats["ack"] == 4 and receiver.stats["events"] == 3 and receiver.stats["nak"] == 0
    assert "1234" in receiver.last_seen
    # The account in the header wins over a stale data prefix; lower-case accounts are normalised
    await receiver.handle_line(encode_frame("SIA-DCS", 11, 0, 0, "ab12", "Nri1/TA05", STAMP))
    assert devices.states("sia:AB12") == [{"tamper": True}]


async def test_handle_line_nak_on_crc_error_garbage_and_unknown_account(receiver: SiaReceiver, runtime: FakeRuntime):
    frame = bytearray(encode_frame("SIA-DCS", 3, 0, 0, "1234", "#1234|Nri1/BA01", STAMP))
    frame[1:5] = b"BEEF"
    reply = await receiver.handle_line(bytes(frame))
    nak = parse_frame(reply)
    assert nak.msg_type == "NAK" and nak.sequence == "0000" and nak.account == "" and nak.crc_ok
    assert reply == build_nak(nak.timestamp)
    assert parse_frame(await receiver.handle_line(b"\nthis is not sia\r")).msg_type == "NAK"
    assert runtime.services["devices"].pushes == []

    strict = SiaReceiver(FakeRuntime(HUB_SIA_ACCOUNTS="1234:home-a"), port=0)
    good = await strict.handle_line(encode_frame("SIA-DCS", 4, 0, 0, "1234", "#1234|Nri1/OP01", STAMP))
    bad = await strict.handle_line(encode_frame("SIA-DCS", 5, 0, 0, "9999", "#9999|Nri1/OP01", STAMP))
    assert parse_frame(good).msg_type == "ACK" and parse_frame(bad).msg_type == "NAK"
    assert strict.stats == {"frames": 2, "ack": 1, "nak": 1, "duh": 0, "events": 1}
    assert strict.allowed_accounts == {"1234"} and receiver.allowed_accounts == set()


async def test_handle_line_keepalive_and_unsupported(receiver: SiaReceiver, runtime: FakeRuntime):
    devices: FakeDeviceService = runtime.services["devices"]
    reply = await receiver.handle_line(encode_frame("NULL", 12, 0, 0, "1234", "", STAMP))
    assert parse_frame(reply).msg_type == "ACK" and parse_frame(reply).sequence == "0012"
    assert devices.pushes == [("ajax", "sia:1234", "state", {"state": {}, "online": True})]
    duh = await receiver.handle_line(encode_frame("*SIA-DCS", 13, 0, 0, "1234", "0A1B2C", STAMP))
    assert parse_frame(duh).msg_type == "DUH" and parse_frame(duh).sequence == "0013"
    weird = await receiver.handle_line(encode_frame("XYZ-FMT", 14, 0, 0, "1234", "", STAMP))
    assert parse_frame(weird).msg_type == "DUH"
    assert receiver.stats["duh"] == 2 and len(devices.pushes) == 1
    # No device service: frames are still acknowledged
    lonely = SiaReceiver(type("R", (), {"settings": make_settings(), "services": {}})(), port=0)
    assert parse_frame(await lonely.handle_line(encode_frame("SIA-DCS", 1, 0, 0, "1234", "#1234|NBA01"))).msg_type == "ACK"


async def test_build_ack_echoes_frame():
    frame = parse_frame(encode_frame("SIA-DCS", 42, 0x2, 0x7, "ABCDEF", "#ABCDEF|Nri1/OP01", STAMP))
    ack = parse_frame(build_ack(frame, STAMP))
    assert (ack.msg_type, ack.sequence, ack.receiver, ack.line, ack.account, ack.timestamp) == ("ACK", "0042", "2", "7", "ABCDEF", STAMP)
    assert build_ack(frame, STAMP) == encode_frame("ACK", 42, "2", "7", "ABCDEF", "", STAMP)


async def test_socket_roundtrip(runtime: FakeRuntime):
    receiver = SiaReceiver(runtime, port=0, host="127.0.0.1", idle_timeout=5.0)
    assert receiver.port == 0 and not receiver.running
    await receiver.start()
    try:
        assert receiver.running and receiver.bound_port > 0
        reader, writer = await asyncio.open_connection("127.0.0.1", receiver.bound_port)
        try:
            writer.write(encode_frame("SIA-DCS", 21, 0, 0, "1234", "#1234|Nri1/NL01", STAMP))
            await writer.drain()
            ack = parse_frame(await asyncio.wait_for(reader.readuntil(b"\r"), timeout=5))
            assert ack.msg_type == "ACK" and ack.sequence == "0021" and ack.account == "1234"
            # Two frames in one TCP segment are answered separately, in order
            writer.write(encode_frame("NULL", 22, 0, 0, "1234", "", STAMP) + encode_frame("ADM-CID", 23, 0, 0, "1234", "#1234|1130 01 007", STAMP))
            await writer.drain()
            first = parse_frame(await asyncio.wait_for(reader.readuntil(b"\r"), timeout=5))
            second = parse_frame(await asyncio.wait_for(reader.readuntil(b"\r"), timeout=5))
            assert (first.msg_type, first.sequence) == ("ACK", "0022") and (second.msg_type, second.sequence) == ("ACK", "0023")
            broken = bytearray(encode_frame("SIA-DCS", 24, 0, 0, "1234", "#1234|Nri1/BA02", STAMP))
            broken[1:5] = b"0000"
            writer.write(bytes(broken))
            await writer.drain()
            assert parse_frame(await asyncio.wait_for(reader.readuntil(b"\r"), timeout=5)).msg_type == "NAK"
        finally:
            writer.close()
            await writer.wait_closed()
        devices: FakeDeviceService = runtime.services["devices"]
        assert devices.states("sia:1234") == [{"arm_mode": "armed_night"}, {}, {"alarm": True, "triggered_zone": "Zone 7"}]
        assert devices.events("sia:1234") == ["burglary"]
        assert receiver.stats["ack"] == 3 and receiver.stats["nak"] == 1
    finally:
        await receiver.stop()
    assert not receiver.running
    await receiver.stop()  # idempotent


async def test_port_defaults_from_settings():
    assert SiaReceiver(FakeRuntime(HUB_SIA_PORT=9500)).port == 9500
    assert SiaReceiver(FakeRuntime(HUB_SIA_PORT=9500), port=0).port == 0
    assert sia.DEFAULT_BRAND == "ajax" and SiaReceiver.external_id("ab12") == "sia:AB12"


# ----------------------------------------------------------------------------- end to end (real DeviceService)
async def test_receiver_updates_paired_panel_through_device_service(hub_app, client, auth, home):
    """Pair a SIA panel through the adapter + DeviceService, then feed frames and read the persisted state back."""
    from sqlalchemy import select  # pylint: disable=import-outside-toplevel

    from app.hub.adapters.base import AdapterContext  # pylint: disable=import-outside-toplevel
    from app.hub.adapters.registry import registry  # pylint: disable=import-outside-toplevel
    from app.hub.models import Device, DeviceEvent  # pylint: disable=import-outside-toplevel

    runtime = hub_app.state.hub_runtime
    devices_service = runtime.services["devices"]
    adapter = registry.get("ajax")
    result = await adapter.pair("sia_receiver", {"account": "1234", "name": "Centrale"}, AdapterContext(settings=runtime.settings))
    async with runtime.db.session() as session:
        devices, integration = await devices_service.materialize(session, home["id"], None, "ajax", result)
        assert integration is None and len(devices) == 1
        device_id = devices[0].id
        assert devices[0].external_id == "sia:1234" and devices[0].state["arm_mode"] == "disarmed"

    receiver = SiaReceiver(runtime, port=0)
    for seq, data in ((1, "#1234|Nri1/id4/CL04"), (2, "#1234|Nri1/BA02^Cuisine^"), (3, "#1234|Nri1/RP0000")):
        assert parse_frame(await receiver.handle_line(encode_frame("SIA-DCS", seq, 0, 0, "1234", data, STAMP))).msg_type == "ACK"
    assert parse_frame(await receiver.handle_line(encode_frame("ADM-CID", 4, 0, 0, "1234", "#1234|1401 01 004", STAMP))).msg_type == "ACK"

    async with runtime.db.session() as session:
        device = await session.get(Device, device_id)
        assert device is not None and device.online is True
        assert device.state["arm_mode"] == "disarmed" and device.state["alarm"] is False and device.state["triggered_zone"] == "Cuisine"
        types = [e.type for e in (await session.execute(select(DeviceEvent).where(DeviceEvent.device_id == device_id))).scalars()]
    assert "alarm" in types and "burglary" in types and "arm_mode" in types
    assert receiver.stats["ack"] == 4 and receiver.stats["events"] == 3
