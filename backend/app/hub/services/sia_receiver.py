"""SIA DC-09 receiver: a TCP "monitoring station" any alarm panel can report to.

Ajax hubs, Hikvision AX PRO, Paradox, DSC, Honeywell... all speak ANSI/SIA DC-09-2013 in plain
(unencrypted) mode.  One frame per event::

    <LF><CRC><0LLL>"<id>"<seq>R<rcvr>L<line>#<acct>[<data>]_<HH:MM:SS,MM-DD-YYYY><CR>

* ``id``    ``SIA-DCS`` (SIA DC-03 two-letter codes), ``ADM-CID`` (Ademco Contact ID) or ``NULL``
            (keep-alive / link test)
* ``CRC``   CRC-16/ARC (polynomial 0x8005 reflected, init 0, no final XOR) over the bytes between
            the length field and <CR> exclusive - i.e. from the opening quote through the
            timestamp - written as 4 upper-case hex digits (two binary bytes are tolerated)
* ``0LLL``  length of the same bytes as 4 hex digits with a leading zero
* the timestamp is GMT and optional on the wire (some panels omit it)

Every frame is answered: ``"ACK"`` when it was processed, ``"NAK"`` on CRC mismatch, unparsable
frames or an unknown account, ``"DUH"`` for frames we cannot process (encrypted ``"*SIA-DCS"``).

Events are turned into hub updates for the ``alarm_panel`` device whose external id is
``sia:<ACCOUNT>`` (brand ``ajax``, see the ``sia_receiver`` pairing method in ``adapters/ajax.py``)
through ``runtime.services["devices"].handle_push``.  The codec (``encode_frame``/``parse_frame``)
and the event mapping are pure functions so tests and the Ajax webhook handler can reuse them.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("safer.hub.sia")

SIA_DCS = "SIA-DCS"
ADM_CID = "ADM-CID"
NULL = "NULL"
ACK = "ACK"
NAK = "NAK"
DUH = "DUH"

DEFAULT_BRAND = "ajax"
DEFAULT_HOST = "0.0.0.0"
TIMESTAMP_FORMAT = "%H:%M:%S,%m-%d-%Y"
MAX_FRAME_BYTES = 8192
IDLE_TIMEOUT = 300.0  # panels send a NULL link test at least every few minutes

SECURITY_MODES = ("disarmed", "armed_home", "armed_away", "armed_night")


class SiaFrameError(ValueError):
    """Raised by ``parse_frame`` when the bytes are not a DC-09 frame."""


# =============================================================================== codec
def crc16(data: bytes) -> int:
    """CRC-16/ARC (poly 0x8005 reflected = 0xA001, init 0, no xor-out) as used by DC-09."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def format_timestamp(when: Optional[datetime] = None) -> str:
    """DC-09 timestamp ``HH:MM:SS,MM-DD-YYYY`` in GMT."""
    when = when or datetime.now(timezone.utc)
    if when.tzinfo is not None:
        when = when.astimezone(timezone.utc)
    return when.strftime(TIMESTAMP_FORMAT)


def parse_timestamp(text: str) -> Optional[datetime]:
    """Parse a DC-09 timestamp into an aware UTC datetime (None when malformed)."""
    try:
        return datetime.strptime(text, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _hex_field(value: Union[int, str, None], default: str = "0") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, int):
        return f"{value:X}"
    return str(value).strip().upper()


def encode_frame(
    msg_type: str,
    sequence: Union[int, str] = 1,
    receiver: Union[int, str] = "0",
    line: Union[int, str] = "0",
    account: str = "",
    data: str = "",
    timestamp: Union[None, datetime, str] = None,
    with_timestamp: bool = True,
) -> bytes:
    """Build a complete DC-09 frame (``<LF>...<CR>``) with CRC and length.

    ``timestamp`` may be a datetime, a pre-formatted string, or None (= now, GMT). Pass
    ``with_timestamp=False`` to omit the field entirely (some panels do).
    """
    seq = f"{int(sequence):04d}" if not isinstance(sequence, str) else sequence.zfill(4)[-4:]
    body = f'"{msg_type}"{seq}R{_hex_field(receiver)}L{_hex_field(line)}'
    if account:
        body += f"#{account.upper()}"
    body += f"[{data}]"
    if with_timestamp:
        stamp = timestamp if isinstance(timestamp, str) else format_timestamp(timestamp)
        body += f"_{stamp}"
    raw = body.encode("latin-1")
    header = f"{crc16(raw):04X}{len(raw):04X}".encode("ascii")
    return b"\n" + header + raw + b"\r"


@dataclass
class SiaFrame:
    """A decoded DC-09 frame."""

    msg_type: str
    sequence: str
    receiver: str
    line: str
    account: str
    data: str
    body: str
    crc: Optional[int]
    crc_expected: int
    length: Optional[int]
    timestamp: Optional[datetime] = None
    encrypted: bool = False
    extensions: List[str] = field(default_factory=list)

    @property
    def crc_ok(self) -> bool:
        """True when the CRC matches (or the sender omitted the header)."""
        return self.crc is None or self.crc == self.crc_expected

    @property
    def length_ok(self) -> bool:
        """True when the declared length matches the body."""
        return self.length is None or self.length == len(self.body)


HEX_HEADER_RE = re.compile(rb'^[0-9A-Fa-f]{4}0[0-9A-Fa-f]{3}"')
HEX4_RE = re.compile(rb"^[0-9A-Fa-f]{4}$")
BODY_RE = re.compile(
    r'^"(?P<enc>\*?)(?P<id>[A-Za-z0-9\-]+)"'
    r"(?P<seq>[0-9]{4})"
    r"(?:R(?P<rcvr>[0-9A-Fa-f]{1,6}))?"
    r"(?:L(?P<line>[0-9A-Fa-f]{1,6}))?"
    r"(?:#(?P<acct>[0-9A-Za-z]{1,16}))?"
    r"\[(?P<data>[^\]]*)\]"
    r"(?P<ext>(?:\[[^\]]*\])*)"
    r"(?:_?(?P<ts>[0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]{2}-[0-9]{2}-[0-9]{4}))?"
    r"\s*$"
)


def parse_frame(raw: Union[bytes, str]) -> SiaFrame:
    """Decode one frame (with or without the surrounding LF/CR). Raises ``SiaFrameError``.

    Tolerates: hex or binary CRC, a missing CRC/length header, a missing timestamp, extra
    ``[...]`` extension fields and lower-case hex.
    """
    data = raw.encode("latin-1") if isinstance(raw, str) else bytes(raw)
    data = data.strip(b"\r\n\x00 \t")
    if not data:
        raise SiaFrameError("empty frame")
    crc_value: Optional[int]
    length: Optional[int]
    if HEX_HEADER_RE.match(data):
        crc_value, length, body = int(data[:4], 16), int(data[4:8], 16), data[8:]
    elif len(data) > 6 and data[6:7] == b'"' and HEX4_RE.match(data[2:6]):
        crc_value, length, body = int.from_bytes(data[:2], "big"), int(data[2:6], 16), data[6:]
    elif data[:1] == b'"':
        crc_value, length, body = None, None, data
    else:
        raise SiaFrameError("frame does not start with a CRC/length header")
    text = body.decode("latin-1")
    match = BODY_RE.match(text)
    if match is None:
        raise SiaFrameError(f"unparsable frame body {text[:80]!r}")
    extensions = re.findall(r"\[([^\]]*)\]", match.group("ext") or "")
    return SiaFrame(
        msg_type=match.group("id").upper(),
        sequence=match.group("seq"),
        receiver=(match.group("rcvr") or "0").upper(),
        line=(match.group("line") or "0").upper(),
        account=(match.group("acct") or "").upper(),
        data=match.group("data"),
        body=text,
        crc=crc_value,
        crc_expected=crc16(body),
        length=length,
        timestamp=parse_timestamp(match.group("ts")) if match.group("ts") else None,
        encrypted=bool(match.group("enc")),
        extensions=extensions,
    )


def build_ack(frame: SiaFrame, when: Optional[datetime] = None) -> bytes:
    """Positive acknowledgement echoing sequence, receiver, line prefix and account."""
    return encode_frame(ACK, frame.sequence, frame.receiver, frame.line, frame.account, "", when)


def build_nak(when: Optional[datetime] = None) -> bytes:
    """Negative acknowledgement (``"NAK"0000R0L0[]``) — the panel will retry."""
    return encode_frame(NAK, "0000", "0", "0", "", "", when)


def build_duh(frame: SiaFrame, when: Optional[datetime] = None) -> bytes:
    """"Unable to process" reply for frames we understand but cannot handle (encryption)."""
    return encode_frame(DUH, frame.sequence, frame.receiver, frame.line, frame.account, "", when)


# =============================================================================== events
@dataclass
class SiaEvent:
    """One event extracted from a frame's data field."""

    protocol: str  # "sia" (DC-03 two-letter code) or "cid" (Contact ID three digits)
    code: str
    qualifier: str = "N"  # SIA: N new / O old ; CID: 1 new, 3 restore, 6 status
    zone: str = ""
    area: str = ""
    user: str = ""
    text: str = ""
    account: str = ""


@dataclass
class SiaUpdate:
    """Hub-side effect of an event: partial panel state + device events."""

    code: str
    category: str
    description: str
    state: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    ignored: bool = False


def split_account(data: str) -> Tuple[str, str]:
    """Split the optional ``#ACCT|`` prefix of a data field -> (account, remainder)."""
    data = data.strip()
    if data.startswith("#"):
        account, _, rest = data[1:].partition("|")
        return account.strip().upper(), rest
    return "", data


MODIFIER_PREFIXES = ("ri", "id", "ti", "pi", "da")  # area, user, time, peripheral, date
CODE_RE = re.compile(r"^[A-Z]{2}[0-9A-Za-z]*$")
TEXT_RE = re.compile(r"\^([^^]*)\^")
CID_RE = re.compile(r"(?P<q>[136])(?P<event>[0-9]{3})\s*(?P<group>[0-9]{2})\s*(?P<zone>[0-9]{3})")


def parse_sia_dcs(data: str, account: str = "") -> List[SiaEvent]:
    """Parse SIA-DCS data such as ``#1234|Nri1/BA01`` / ``#1234|NBA01^Front door^|Nri1/id3/OP03``."""
    found, rest = split_account(data)
    account = found or account
    events: List[SiaEvent] = []
    for segment in rest.split("|"):
        segment = segment.strip()
        if not segment:
            continue
        text = ""
        match = TEXT_RE.search(segment)
        if match:
            text = match.group(1).strip()
            segment = (segment[: match.start()] + segment[match.end():]).strip()
        tokens = [token for token in segment.split("/") if token]
        if not tokens:
            continue
        qualifier = "N"
        first = tokens[0]
        if first in ("N", "O"):
            qualifier = first
            tokens.pop(0)
        elif first[0] in "NO" and (first[1:3] in MODIFIER_PREFIXES or CODE_RE.match(first[1:])):
            qualifier = first[0]
            tokens[0] = first[1:]
        area = user = code = zone = ""
        for token in tokens:
            prefix = token[:2]
            if prefix == "ri":
                area = token[2:]
            elif prefix == "id":
                user = token[2:]
            elif prefix in ("ti", "pi", "da"):
                continue
            elif not code and CODE_RE.match(token):
                code, zone = token[:2], token[2:]
        if code:
            events.append(SiaEvent("sia", code, qualifier, zone, area, user, text, account))
    return events


def parse_cid(data: str, account: str = "") -> List[SiaEvent]:
    """Parse ADM-CID data such as ``#1234|1130 01 003`` (qualifier, event, group, zone/user)."""
    found, rest = split_account(data)
    account = found or account
    events: List[SiaEvent] = []
    for segment in rest.split("|"):
        match = CID_RE.search(segment)
        if match is None:
            continue
        code = match.group("event")
        zone = match.group("zone")
        user = zone if code.startswith("4") else ""
        events.append(SiaEvent("cid", code, match.group("q"), zone, match.group("group"), user, "", account))
    return events


def parse_events(frame: SiaFrame) -> List[SiaEvent]:
    """Events carried by a frame (empty for NULL / unknown ids)."""
    if frame.msg_type == SIA_DCS:
        return parse_sia_dcs(frame.data, frame.account)
    if frame.msg_type == ADM_CID:
        return parse_cid(frame.data, frame.account)
    return []


# --- SIA DC-03 two-letter codes -> (category, description) -------------------------------------
SIA_CODES: Dict[str, Tuple[str, str]] = {
    # burglary
    "BA": ("burglary", "Burglary alarm"), "BB": ("bypass", "Burglary bypass"), "BC": ("restore", "Burglary cancel"),
    "BH": ("restore", "Burglary alarm restore"), "BJ": ("trouble_restore", "Burglary trouble restore"),
    "BR": ("restore", "Burglary restore"), "BS": ("burglary", "Burglary supervisory"), "BT": ("trouble", "Burglary trouble"),
    "BU": ("unbypass", "Burglary unbypass"), "BV": ("burglary", "Burglary verified"), "BX": ("test", "Burglary test"),
    "BZ": ("trouble", "Missing supervision"), "UA": ("burglary", "Untyped zone alarm"), "UR": ("restore", "Untyped zone restore"),
    "UB": ("bypass", "Untyped zone bypass"), "UU": ("unbypass", "Untyped zone unbypass"), "UT": ("trouble", "Untyped zone trouble"),
    "UJ": ("trouble_restore", "Untyped zone trouble restore"), "EA": ("burglary", "Exit alarm"),
    # fire / heat / gas / water / CO / environment
    "FA": ("fire", "Fire alarm"), "FB": ("bypass", "Fire bypass"), "FC": ("restore", "Fire cancel"),
    "FH": ("restore", "Fire alarm restore"), "FI": ("test", "Fire test begin"), "FJ": ("trouble_restore", "Fire trouble restore"),
    "FK": ("test", "Fire test end"), "FR": ("restore", "Fire restore"), "FS": ("fire", "Fire supervisory"),
    "FT": ("trouble", "Fire trouble"), "FU": ("unbypass", "Fire unbypass"), "FX": ("test", "Fire test"),
    "KA": ("fire", "Heat alarm"), "KR": ("restore", "Heat restore"), "KT": ("trouble", "Heat trouble"),
    "GA": ("gas", "Gas alarm"), "GR": ("restore", "Gas restore"), "GT": ("trouble", "Gas trouble"), "GJ": ("trouble_restore", "Gas trouble restore"),
    "WA": ("water", "Water alarm"), "WR": ("restore", "Water restore"), "WT": ("trouble", "Water trouble"),
    "ZA": ("environment", "Freeze alarm"), "ZR": ("restore", "Freeze restore"),
    "SA": ("fire", "Sprinkler alarm"), "SR": ("restore", "Sprinkler restore"),
    # panic / hold-up / medical / emergency
    "PA": ("panic", "Panic alarm"), "PB": ("bypass", "Panic bypass"), "PH": ("restore", "Panic alarm restore"),
    "PR": ("restore", "Panic restore"), "PT": ("trouble", "Panic trouble"), "PU": ("unbypass", "Panic unbypass"),
    "HA": ("panic", "Hold-up alarm"), "HH": ("restore", "Hold-up alarm restore"), "HR": ("restore", "Hold-up restore"),
    "QA": ("panic", "Emergency alarm"), "QR": ("restore", "Emergency restore"),
    "MA": ("medical", "Medical alarm"), "MH": ("restore", "Medical alarm restore"), "MR": ("restore", "Medical restore"),
    # tamper
    "TA": ("tamper", "Tamper alarm"), "TB": ("bypass", "Tamper bypass"), "TH": ("tamper_restore", "Tamper alarm restore"),
    "TR": ("tamper_restore", "Tamper restore"), "TT": ("trouble", "Tamper trouble"), "TU": ("unbypass", "Tamper unbypass"),
    "ES": ("tamper", "Expansion device tamper"), "EJ": ("tamper_restore", "Expansion device tamper restore"),
    # closing (arming)
    "CL": ("arm_away", "Closing report"), "CG": ("arm_away", "Close area"), "CQ": ("arm_away", "Remote closing"),
    "CA": ("arm_away", "Automatic closing"), "CS": ("arm_away", "Closing keyswitch"), "CW": ("arm_away", "Was force armed"),
    "CJ": ("arm_away", "Late close"), "CK": ("arm_away", "Early close"), "CR": ("arm_away", "Recent closing"),
    "CZ": ("arm_away", "Point closing"), "CF": ("arm_home", "Forced closing (partial)"), "CP": ("arm_home", "Automatic closing (partial)"),
    "CE": ("info", "Closing extend"), "CI": ("trouble", "Fail to close"), "CT": ("trouble", "Late to open"),
    "NL": ("arm_night", "Perimeter armed"), "NF": ("arm_night", "Forced perimeter arm"),
    # opening (disarming)
    "OP": ("disarm", "Opening report"), "OG": ("disarm", "Open area"), "OQ": ("disarm", "Remote opening"),
    "OA": ("disarm", "Automatic opening"), "OS": ("disarm", "Opening keyswitch"), "OR": ("disarm", "Disarm from alarm"),
    "OK": ("disarm", "Early open"), "OJ": ("disarm", "Late open"), "OZ": ("disarm", "Point opening"),
    "OC": ("restore", "Cancel report"), "OT": ("trouble", "Late to close"),
    # power / battery
    "AT": ("ac_loss", "AC trouble"), "AR": ("ac_restore", "AC restore"),
    "YP": ("ac_loss", "Power supply trouble"), "YQ": ("ac_restore", "Power supply restore"),
    "YT": ("battery_low", "System battery trouble"), "YR": ("battery_ok", "System battery restore"),
    "YM": ("battery_low", "System battery missing"), "XT": ("battery_low", "Transmitter battery trouble"),
    "XR": ("battery_ok", "Transmitter battery restore"),
    # communications / system
    "YC": ("trouble", "Communications fail"), "YK": ("trouble_restore", "Communications restore"),
    "YS": ("trouble", "Communications trouble"), "YX": ("trouble", "Service required"), "YZ": ("trouble_restore", "Service completed"),
    "YA": ("trouble", "Bell fault"), "YH": ("trouble_restore", "Bell restored"), "YI": ("trouble", "Overcurrent trouble"),
    "YF": ("trouble", "Parameter checksum fail"), "YG": ("info", "Parameter changed"),
    "LT": ("trouble", "Phone line trouble"), "LR": ("trouble_restore", "Phone line restore"),
    "ET": ("trouble", "Expansion device trouble"), "ER": ("trouble_restore", "Expansion device restore"),
    "NA": ("trouble", "No activity"), "NC": ("trouble", "Network condition"), "NR": ("trouble_restore", "Network restore"),
    "RR": ("info", "Power up"), "RS": ("info", "Remote program success"), "RU": ("trouble", "Remote program fail"),
    "JL": ("info", "Log threshold"), "JO": ("info", "Log overflow"), "JT": ("info", "Time changed"),
    "JD": ("info", "Date changed"), "JV": ("info", "User code changed"),
    "LB": ("info", "Local program begin"), "LX": ("info", "Local program ended"), "LS": ("info", "Local program success"),
    "LU": ("info", "Local program fail"), "DG": ("info", "Access granted"), "DD": ("info", "Access denied"), "DK": ("info", "Access lockout"),
    # tests
    "RP": ("test", "Automatic test"), "RX": ("test", "Manual test"), "RY": ("test", "Test off normal"),
    "TS": ("test", "Test start"), "TE": ("test", "Test end"), "TX": ("test", "Test report"),
}

# Heuristic for two-letter codes missing from the table (SIA second-letter conventions)
SIA_SUFFIX_CATEGORIES: Dict[str, Tuple[str, str]] = {
    "A": ("burglary", "Alarm"), "R": ("restore", "Restore"), "H": ("restore", "Alarm restore"),
    "T": ("trouble", "Trouble"), "J": ("trouble_restore", "Trouble restore"), "B": ("bypass", "Bypass"),
    "U": ("unbypass", "Unbypass"), "X": ("test", "Test"),
}

# --- Contact ID -> (category when new/status, category when restore/closing, description) --------
CID_EVENTS: Dict[int, Tuple[str, str, str]] = {
    100: ("medical", "restore", "Medical"), 101: ("medical", "restore", "Personal emergency"),
    110: ("fire", "restore", "Fire alarm"), 111: ("fire", "restore", "Smoke"), 112: ("fire", "restore", "Combustion"),
    113: ("water", "restore", "Water flow"), 114: ("fire", "restore", "Heat"), 115: ("fire", "restore", "Pull station"),
    116: ("fire", "restore", "Duct"), 117: ("fire", "restore", "Flame"), 118: ("fire", "restore", "Near alarm"),
    120: ("panic", "restore", "Panic alarm"), 121: ("panic", "restore", "Duress"), 122: ("panic", "restore", "Silent panic"),
    123: ("panic", "restore", "Audible panic"), 124: ("panic", "restore", "Duress - access granted"),
    125: ("panic", "restore", "Duress - egress granted"),
    130: ("burglary", "restore", "Burglary"), 131: ("burglary", "restore", "Perimeter"), 132: ("burglary", "restore", "Interior"),
    133: ("burglary", "restore", "24 hour burglary"), 134: ("burglary", "restore", "Entry/exit"), 135: ("burglary", "restore", "Day/night"),
    136: ("burglary", "restore", "Outdoor"), 137: ("tamper", "tamper_restore", "Tamper"), 138: ("burglary", "restore", "Near alarm"),
    139: ("burglary", "restore", "Intrusion verifier"), 140: ("burglary", "restore", "General alarm"),
    143: ("trouble", "trouble_restore", "Expansion module failure"), 144: ("tamper", "tamper_restore", "Sensor tamper"),
    145: ("tamper", "tamper_restore", "Expansion module tamper"), 146: ("burglary", "restore", "Silent burglary"),
    147: ("trouble", "trouble_restore", "Sensor supervision failure"),
    150: ("burglary", "restore", "24 hour non-burglary"), 151: ("gas", "restore", "Gas detected"),
    152: ("environment", "restore", "Refrigeration"), 153: ("environment", "restore", "Loss of heat"),
    154: ("water", "restore", "Water leakage"), 155: ("trouble", "trouble_restore", "Foil break"),
    156: ("trouble", "trouble_restore", "Day trouble"), 157: ("gas", "restore", "Low bottled gas level"),
    158: ("environment", "restore", "High temperature"), 159: ("environment", "restore", "Low temperature"),
    161: ("trouble", "trouble_restore", "Loss of air flow"), 162: ("co", "restore", "Carbon monoxide detected"),
    163: ("environment", "restore", "Tank level"),
    200: ("fire", "restore", "Fire supervisory"), 201: ("trouble", "trouble_restore", "Low water pressure"),
    202: ("trouble", "trouble_restore", "Low CO2"), 203: ("trouble", "trouble_restore", "Gate valve sensor"),
    204: ("trouble", "trouble_restore", "Low water level"), 205: ("trouble", "trouble_restore", "Pump activated"),
    206: ("trouble", "trouble_restore", "Pump failure"),
    300: ("trouble", "trouble_restore", "System trouble"), 301: ("ac_loss", "ac_restore", "AC loss"),
    302: ("battery_low", "battery_ok", "Low system battery"), 303: ("trouble", "trouble_restore", "RAM checksum bad"),
    305: ("info", "info", "System reset"), 306: ("info", "info", "Panel programming changed"),
    307: ("trouble", "trouble_restore", "Self-test failure"), 308: ("info", "info", "System shutdown"),
    309: ("battery_low", "battery_ok", "Battery test failure"), 310: ("trouble", "trouble_restore", "Ground fault"),
    311: ("battery_low", "battery_ok", "Battery missing"), 312: ("trouble", "trouble_restore", "Power supply overcurrent"),
    313: ("info", "info", "Engineer reset"), 320: ("trouble", "trouble_restore", "Sounder/relay"),
    321: ("trouble", "trouble_restore", "Bell 1"), 322: ("trouble", "trouble_restore", "Bell 2"),
    323: ("trouble", "trouble_restore", "Alarm relay"), 324: ("trouble", "trouble_restore", "Trouble relay"),
    330: ("trouble", "trouble_restore", "System peripheral trouble"), 333: ("trouble", "trouble_restore", "Expansion module failure"),
    337: ("ac_loss", "ac_restore", "Expansion module DC loss"), 338: ("battery_low", "battery_ok", "Expansion module low battery"),
    339: ("info", "info", "Expansion module reset"), 341: ("tamper", "tamper_restore", "Expansion module tamper"),
    342: ("ac_loss", "ac_restore", "Expansion module AC loss"), 344: ("trouble", "trouble_restore", "RF receiver jam detect"),
    350: ("trouble", "trouble_restore", "Communication trouble"), 351: ("trouble", "trouble_restore", "Telco 1 fault"),
    352: ("trouble", "trouble_restore", "Telco 2 fault"), 353: ("trouble", "trouble_restore", "Radio transmitter fault"),
    354: ("trouble", "trouble_restore", "Failure to communicate"), 355: ("trouble", "trouble_restore", "Loss of radio supervision"),
    356: ("trouble", "trouble_restore", "Loss of central polling"),
    370: ("trouble", "trouble_restore", "Protection loop"), 371: ("trouble", "trouble_restore", "Protection loop open"),
    372: ("trouble", "trouble_restore", "Protection loop short"), 373: ("trouble", "trouble_restore", "Fire trouble"),
    374: ("trouble", "trouble_restore", "Exit error"), 375: ("trouble", "trouble_restore", "Panic zone trouble"),
    376: ("trouble", "trouble_restore", "Hold-up zone trouble"), 377: ("trouble", "trouble_restore", "Swinger trouble"),
    378: ("trouble", "trouble_restore", "Cross-zone trouble"),
    380: ("trouble", "trouble_restore", "Sensor trouble"), 381: ("trouble", "trouble_restore", "Loss of supervision - RF"),
    382: ("trouble", "trouble_restore", "Loss of supervision - RPM"), 383: ("tamper", "tamper_restore", "Sensor tamper"),
    384: ("battery_low", "battery_ok", "RF low battery"), 385: ("trouble", "trouble_restore", "Smoke detector high sensitivity"),
    386: ("trouble", "trouble_restore", "Smoke detector low sensitivity"), 389: ("trouble", "trouble_restore", "Sensor self-test failure"),
    391: ("trouble", "trouble_restore", "Sensor watch trouble"), 393: ("trouble", "trouble_restore", "Maintenance alert"),
    400: ("disarm", "arm_away", "Open/close"), 401: ("disarm", "arm_away", "Open/close by user"),
    402: ("disarm", "arm_away", "Group open/close"), 403: ("disarm", "arm_away", "Automatic open/close"),
    404: ("disarm", "arm_away", "Late to open/close"), 405: ("disarm", "arm_away", "Deferred open/close"),
    406: ("restore", "restore", "Cancel"), 407: ("disarm", "arm_away", "Remote arm/disarm"),
    408: ("disarm", "arm_away", "Quick arm"), 409: ("disarm", "arm_away", "Keyswitch open/close"),
    411: ("info", "info", "Callback request made"), 412: ("info", "info", "Successful download/access"),
    413: ("info", "info", "Unsuccessful access"), 421: ("info", "info", "Access denied"),
    422: ("info", "info", "Access report by user"), 423: ("panic", "restore", "Forced access"),
    441: ("disarm", "arm_home", "Armed stay"), 442: ("disarm", "arm_home", "Keyswitch armed stay"),
    450: ("disarm", "arm_away", "Exception open/close"), 451: ("disarm", "arm_away", "Early open/close"),
    452: ("disarm", "arm_away", "Late open/close"), 453: ("trouble", "trouble_restore", "Failed to open"),
    454: ("trouble", "trouble_restore", "Failed to close"), 455: ("trouble", "trouble_restore", "Auto-arm failed"),
    456: ("disarm", "arm_home", "Partial arm"), 457: ("info", "info", "Exit error (user)"),
    458: ("info", "info", "User on premises"), 459: ("info", "info", "Recent close"),
    461: ("info", "info", "Wrong code entry"), 462: ("info", "info", "Legal code entry"),
    463: ("info", "info", "Re-arm after alarm"), 464: ("info", "info", "Auto-arm time extended"),
    465: ("restore", "restore", "Panic alarm reset"), 466: ("info", "info", "Service on/off premises"),
    520: ("info", "info", "Sounder/relay disable"), 521: ("info", "info", "Bell 1 disable"), 522: ("info", "info", "Bell 2 disable"),
    531: ("info", "info", "Module added"), 532: ("info", "info", "Module removed"), 551: ("info", "info", "Dialer disabled"),
    552: ("info", "info", "Radio transmitter disabled"), 553: ("info", "info", "Remote upload/download disabled"),
    570: ("bypass", "unbypass", "Zone/sensor bypass"), 571: ("bypass", "unbypass", "Fire bypass"),
    572: ("bypass", "unbypass", "24 hour zone bypass"), 573: ("bypass", "unbypass", "Burglary bypass"),
    574: ("bypass", "unbypass", "Group bypass"), 575: ("bypass", "unbypass", "Swinger bypass"),
    576: ("bypass", "unbypass", "Access zone shunt"), 577: ("bypass", "unbypass", "Access point bypass"),
    601: ("test", "test", "Manual trigger test"), 602: ("test", "test", "Periodic test report"),
    603: ("test", "test", "Periodic RF transmission"), 604: ("test", "test", "Fire test"),
    605: ("info", "info", "Status report to follow"), 606: ("info", "info", "Listen-in to follow"),
    607: ("test", "test", "Walk test mode"), 608: ("trouble", "trouble_restore", "Periodic test - system trouble present"),
    609: ("info", "info", "Video transmitter active"), 611: ("test", "test", "Point tested OK"),
    612: ("test", "test", "Point not tested"), 613: ("test", "test", "Intrusion zone walk tested"),
    614: ("test", "test", "Fire zone walk tested"), 615: ("test", "test", "Panic zone walk tested"),
    616: ("info", "info", "Service request"), 621: ("info", "info", "Event log reset"),
    622: ("info", "info", "Event log 50% full"), 623: ("info", "info", "Event log 90% full"),
    624: ("info", "info", "Event log overflow"), 625: ("info", "info", "Time/date reset"),
    626: ("trouble", "trouble_restore", "Time/date inaccurate"), 627: ("info", "info", "Program mode entry"),
    628: ("info", "info", "Program mode exit"), 629: ("info", "info", "32 hour event log marker"),
    630: ("info", "info", "Schedule change"), 631: ("info", "info", "Exception schedule change"),
    632: ("info", "info", "Access schedule change"), 641: ("trouble", "trouble_restore", "Senior watch trouble"),
    642: ("info", "info", "Latch-key supervision"), 654: ("trouble", "trouble_restore", "System inactivity"),
}

ALARM_CATEGORIES = frozenset({"burglary", "fire", "panic", "medical", "gas", "water", "co", "environment"})
ARM_CATEGORIES = {"arm_away": "armed_away", "arm_home": "armed_home", "arm_night": "armed_night"}
EVENT_ONLY_CATEGORIES = frozenset({
    "bypass", "unbypass", "trouble", "trouble_restore", "battery_low", "battery_ok", "ac_loss", "ac_restore", "info",
})


def sia_category(code: str) -> Tuple[str, str]:
    """(category, description) of a SIA two-letter code (heuristic for unknown codes)."""
    code = (code or "").upper()
    if code in SIA_CODES:
        return SIA_CODES[code]
    if len(code) == 2 and code[1] in SIA_SUFFIX_CATEGORIES:
        category, label = SIA_SUFFIX_CATEGORIES[code[1]]
        return category, f"{label} ({code})"
    return "unknown", f"SIA code {code}"


def cid_category(code: str, qualifier: str) -> Tuple[str, str]:
    """(category, description) of a Contact ID event given its qualifier (1 new / 3 restore / 6 status)."""
    try:
        number = int(code)
    except (TypeError, ValueError):
        return "unknown", f"Contact ID event {code}"
    entry = CID_EVENTS.get(number)
    if entry is None:
        if 100 <= number < 200:
            entry = ("burglary", "restore", f"Alarm {number}")
        elif 200 <= number < 300:
            entry = ("fire", "restore", f"Supervisory {number}")
        elif 300 <= number < 400:
            entry = ("trouble", "trouble_restore", f"Trouble {number}")
        elif 400 <= number < 500:
            entry = ("disarm", "arm_away", f"Open/close {number}")
        elif 570 <= number < 580:
            entry = ("bypass", "unbypass", f"Bypass {number}")
        elif 600 <= number < 700:
            entry = ("test", "test", f"Test {number}")
        else:
            entry = ("info", "info", f"Contact ID event {number}")
    new_category, restore_category, description = entry
    return (restore_category if qualifier == "3" else new_category), description


def _zone_label(event: SiaEvent) -> str:
    if event.text:
        return event.text
    if event.zone:
        label = (event.zone.lstrip("0") or "0") if event.zone.isdigit() else event.zone
        return f"Zone {label}"
    return ""


def map_event(event: SiaEvent) -> SiaUpdate:
    """Translate one parsed event into panel state + hub events."""
    if event.protocol == "cid":
        category, description = cid_category(event.code, event.qualifier)
    else:
        category, description = sia_category(event.code)
    detail: Dict[str, Any] = {
        "code": event.code, "protocol": event.protocol, "qualifier": event.qualifier, "zone": event.zone,
        "area": event.area, "user": event.user, "text": event.text, "description": description, "category": category,
    }
    update = SiaUpdate(code=event.code, category=category, description=description)
    if category in ALARM_CATEGORIES:
        update.state = {"alarm": True, "triggered_zone": _zone_label(event)}
        update.events = [{"type": category, **detail}]
    elif category == "restore":
        update.state = {"alarm": False}
        update.events = [{"type": "restore", **detail}]
    elif category == "tamper":
        update.state = {"tamper": True}
        update.events = [{"type": "tamper", **detail}]
    elif category == "tamper_restore":
        update.state = {"tamper": False}
        update.events = [{"type": "tamper_restore", **detail}]
    elif category in ARM_CATEGORIES:
        update.state = {"arm_mode": ARM_CATEGORIES[category]}
    elif category == "disarm":
        update.state = {"arm_mode": "disarmed", "alarm": False}
    elif category in EVENT_ONLY_CATEGORIES:
        update.events = [{"type": category, **detail}]
    elif category == "test":
        update.ignored = True
    else:
        update.events = [{"type": "sia", **detail}]
    return update


def map_sia_code(code: str, zone: str = "", text: str = "", qualifier: str = "N") -> SiaUpdate:
    """Convenience: hub update for a bare SIA code (used by the Ajax webhook handler)."""
    return map_event(SiaEvent("sia", code.upper(), qualifier, zone=zone, text=text))


# =============================================================================== server
class SiaReceiver:
    """Async TCP receiver applying SIA DC-09 reports to hub devices.

    ``port=None`` reads ``settings.HUB_SIA_PORT``; ``port=0`` binds an ephemeral port (tests) that
    ``bound_port`` reports once started.
    """

    def __init__(
        self,
        runtime: Any,
        port: Optional[int] = None,
        host: str = DEFAULT_HOST,
        brand: str = DEFAULT_BRAND,
        idle_timeout: float = IDLE_TIMEOUT,
    ):
        self.runtime = runtime
        settings = getattr(runtime, "settings", None)
        self.port = int(port if port is not None else (getattr(settings, "HUB_SIA_PORT", 0) or 0))
        self.host = host
        self.brand = brand
        self.idle_timeout = idle_timeout
        self._server: Optional[asyncio.AbstractServer] = None
        self._writers: Set[asyncio.StreamWriter] = set()
        self.stats: Dict[str, int] = {"frames": 0, "ack": 0, "nak": 0, "duh": 0, "events": 0}
        self.last_seen: Dict[str, datetime] = {}

    # ------------------------------------------------------------------ properties
    @property
    def allowed_accounts(self) -> Set[str]:
        """Accounts from ``HUB_SIA_ACCOUNTS`` (empty set = accept every account)."""
        settings = getattr(self.runtime, "settings", None)
        accounts = getattr(settings, "sia_accounts", None) or {}
        return {str(account).upper() for account in accounts}

    @property
    def running(self) -> bool:
        """True while the TCP server is listening."""
        return self._server is not None and self._server.is_serving()

    @property
    def bound_port(self) -> int:
        """Port actually bound (differs from ``port`` when 0 was requested)."""
        if self._server is None or not self._server.sockets:
            return self.port
        return int(self._server.sockets[0].getsockname()[1])

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        """Start listening (idempotent)."""
        if self._server is not None:
            return
        self._server = await asyncio.start_server(self._serve, self.host, self.port, limit=MAX_FRAME_BYTES)
        logger.info("SIA DC-09 receiver listening on %s:%s", self.host, self.bound_port)

    async def stop(self) -> None:
        """Close client connections and the listening socket."""
        server, self._server = self._server, None
        for writer in list(self._writers):
            writer.close()
        self._writers.clear()
        if server is not None:
            server.close()
            try:
                await asyncio.wait_for(server.wait_closed(), timeout=5.0)
            except asyncio.TimeoutError:  # pragma: no cover - defensive
                logger.warning("SIA receiver: timeout while closing the server")
        logger.info("SIA DC-09 receiver stopped")

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        self._writers.add(writer)
        logger.debug("SIA connection from %s", peer)
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(reader.readuntil(b"\r"), timeout=self.idle_timeout)
                except asyncio.IncompleteReadError as exc:
                    if exc.partial.strip():  # frame without trailing CR before EOF
                        writer.write(await self.handle_line(exc.partial))
                        await writer.drain()
                    break
                except asyncio.LimitOverrunError:
                    logger.warning("SIA connection from %s sent an oversized frame; closing", peer)
                    break
                except asyncio.TimeoutError:
                    logger.debug("SIA connection from %s idle; closing", peer)
                    break
                if not raw.strip():
                    continue
                writer.write(await self.handle_line(raw))
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            pass
        except Exception:  # pylint: disable=broad-except
            logger.exception("SIA connection from %s failed", peer)
        finally:
            self._writers.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # pylint: disable=broad-except
                pass

    # ------------------------------------------------------------------ processing
    async def handle_line(self, raw: bytes) -> bytes:
        """Process one frame and return the reply bytes (ACK/NAK/DUH). Never raises."""
        self.stats["frames"] += 1
        try:
            frame = parse_frame(raw)
        except SiaFrameError as exc:
            logger.warning("SIA: rejected frame (%s): %r", exc, raw[:80])
            self.stats["nak"] += 1
            return build_nak()
        if not frame.crc_ok:
            logger.warning("SIA: CRC mismatch (got %04X, expected %04X) for %r", frame.crc, frame.crc_expected, frame.body[:60])
            self.stats["nak"] += 1
            return build_nak()
        if not frame.length_ok:
            logger.debug("SIA: length mismatch (declared %s, actual %s) - tolerated", frame.length, len(frame.body))
        if frame.encrypted:
            logger.warning("SIA: encrypted frame from account %s not supported (use plain mode)", frame.account or "?")
            self.stats["duh"] += 1
            return build_duh(frame)
        account = frame.account or split_account(frame.data)[0]
        allowed = self.allowed_accounts
        if allowed and account not in allowed:
            logger.warning("SIA: unknown account %r rejected", account)
            self.stats["nak"] += 1
            return build_nak()
        if account:
            self.last_seen[account] = datetime.now(timezone.utc)
        if frame.msg_type == NULL:
            await self.apply_keepalive(account)
        elif frame.msg_type in (SIA_DCS, ADM_CID):
            events = parse_events(frame)
            if not events:
                logger.info("SIA: no event found in %s data %r", frame.msg_type, frame.data)
            for event in events:
                try:
                    await self.apply_update(event.account or account, map_event(event))
                except Exception:  # pylint: disable=broad-except
                    logger.exception("SIA: failed applying %s %s", event.protocol, event.code)
        else:
            logger.warning("SIA: unsupported message id %r", frame.msg_type)
            self.stats["duh"] += 1
            return build_duh(frame)
        self.stats["ack"] += 1
        return build_ack(frame)

    def _devices(self) -> Any:
        services = getattr(self.runtime, "services", None) or {}
        return services.get("devices")

    @staticmethod
    def external_id(account: str) -> str:
        """External id of the panel device for an account."""
        return f"sia:{(account or '').upper()}"

    async def apply_keepalive(self, account: str) -> None:
        """A NULL frame proves the panel is alive: refresh its online flag."""
        devices = self._devices()
        if devices is None or not account:
            return
        await devices.handle_push(self.brand, self.external_id(account), "state", {"state": {}, "online": True})

    async def apply_update(self, account: str, update: SiaUpdate) -> None:
        """Push a mapped event to the device service (state first, then events)."""
        if update.ignored:
            logger.debug("SIA: %s ignored (%s)", update.code, update.description)
            return
        devices = self._devices()
        if devices is None:
            logger.warning("SIA: device service not available; dropping %s", update.code)
            return
        if not account:
            logger.warning("SIA: event %s without account; dropping", update.code)
            return
        external_id = self.external_id(account)
        self.stats["events"] += 1
        logger.info("SIA %s: %s -> %s %s", account, update.code, update.description, update.state or "")
        if update.state:
            await devices.handle_push(self.brand, external_id, "state", {"state": dict(update.state), "online": True})
        for event in update.events:
            await devices.handle_push(self.brand, external_id, "event", dict(event))
