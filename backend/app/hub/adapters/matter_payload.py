"""Matter onboarding payload codec (pure functions, no I/O).

Two representations of the *setup payload* exist (Matter Core Specification, chapter 5.1):

QR code (``MT:`` prefix)
    88 bits packed little-endian, least significant field first::

        version(3) vendor_id(16) product_id(16) commissioning_flow(2)
        discovery_capabilities(8) discriminator(12) passcode(27) padding(4)

    The 11 resulting bytes are encoded in base-38 (alphabet ``0-9 A-Z - .``): every group of
    3 bytes becomes a 24-bit little-endian integer written as 5 base-38 digits (least significant
    digit first); a trailing group of 2 bytes becomes 4 digits and 1 byte becomes 2 digits.
    Optional TLV data (serial number, vendor extensions) may follow the 11-byte header.

Manual pairing code (11 or 21 decimal digits)
    ``digit1 = (vid_pid_present << 2) | (short_discriminator >> 2)``,
    ``digits 2-6 = ((short_discriminator & 0x3) << 14) | (passcode & 0x3FFF)``,
    ``digits 7-10 = passcode >> 14``, then (21-digit form only) 5-digit vendor id + 5-digit
    product id, and a Verhoeff check digit. ``short_discriminator`` is the 4 most significant
    bits of the 12-bit discriminator.

Both parsers return plain dictionaries so the API layer can serialise them directly.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("safer.hub.matter")

QR_PREFIX = "MT:"
BASE38_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-."
_BASE38_INDEX: Dict[str, int] = {ch: i for i, ch in enumerate(BASE38_ALPHABET)}

# (name, bit length) in packing order (least significant first)
QR_FIELDS = (
    ("version", 3),
    ("vendor_id", 16),
    ("product_id", 16),
    ("commissioning_flow", 2),
    ("discovery_capabilities", 8),
    ("discriminator", 12),
    ("passcode", 27),
    ("padding", 4),
)
QR_HEADER_BITS = sum(bits for _, bits in QR_FIELDS)  # 88
QR_HEADER_BYTES = QR_HEADER_BITS // 8  # 11

DISCOVERY_SOFT_AP = 1 << 0
DISCOVERY_BLE = 1 << 1
DISCOVERY_ON_NETWORK = 1 << 2

MANUAL_CODE_SHORT_LENGTH = 11
MANUAL_CODE_LONG_LENGTH = 21
MAX_PASSCODE = (1 << 27) - 1
MAX_DISCRIMINATOR = (1 << 12) - 1

# Passcodes the specification forbids (5.1.7.1): trivial and sequential values.
INVALID_PASSCODES = frozenset(
    {0, 11111111, 22222222, 33333333, 44444444, 55555555, 66666666, 77777777, 88888888, 12345678, 87654321}
)

# A few well-known Connectivity Standards Alliance vendor ids.
VENDOR_NAMES: Dict[int, str] = {
    0xFFF1: "Test Vendor",
    0xFFF2: "Test Vendor",
    0xFFF3: "Test Vendor",
    0xFFF4: "Test Vendor",
    0x1349: "Nanoleaf",
    0x115F: "Aqara",
    0x130A: "Eve Systems",
    0x100B: "Signify (Philips Hue)",
    0x117C: "IKEA",
    0x6006: "Google",
}

# Verhoeff tables (multiplication, permutation, inverse).
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_VERHOEFF_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


class PayloadError(ValueError):
    """Raised when an onboarding payload is malformed."""


# ----------------------------------------------------------------------------- helpers
def vendor_name(vendor_id: Optional[int]) -> Optional[str]:
    """Human readable vendor for a CSA vendor id (only a few well-known ids are known)."""
    if vendor_id is None:
        return None
    return VENDOR_NAMES.get(int(vendor_id))


def is_valid_passcode(passcode: int) -> bool:
    """True when ``passcode`` is in range and not one of the forbidden trivial values."""
    return 0 < passcode <= MAX_PASSCODE and passcode not in INVALID_PASSCODES


def check_passcode(passcode: int) -> None:
    """Raise ``PayloadError`` for an invalid passcode."""
    if not is_valid_passcode(passcode):
        raise PayloadError(f"Invalid Matter passcode {passcode}")


def discovery_capabilities(bitmap: int) -> Dict[str, bool]:
    """Expand the discovery capabilities bitmap."""
    return {
        "ble": bool(bitmap & DISCOVERY_BLE),
        "on_network": bool(bitmap & DISCOVERY_ON_NETWORK),
        "soft_ap": bool(bitmap & DISCOVERY_SOFT_AP),
    }


# ----------------------------------------------------------------------------- Verhoeff
def verhoeff_checksum(digits: str) -> int:
    """Verhoeff check digit for a string of decimal digits."""
    checksum = 0
    for index, char in enumerate(reversed(digits)):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[(index + 1) % 8][int(char)]]
    return _VERHOEFF_INV[checksum]


def verhoeff_validate(digits_with_check: str) -> bool:
    """Validate a digit string whose last digit is a Verhoeff check digit."""
    checksum = 0
    for index, char in enumerate(reversed(digits_with_check)):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[index % 8][int(char)]]
    return checksum == 0


# ----------------------------------------------------------------------------- base-38
def base38_decode(text: str) -> bytes:
    """Decode a base-38 string (groups of 5/4/2 characters -> 3/2/1 bytes)."""
    text = text.upper()
    out = bytearray()
    for start in range(0, len(text), 5):
        chunk = text[start:start + 5]
        try:
            length = {5: 3, 4: 2, 2: 1}[len(chunk)]
        except KeyError as exc:
            raise PayloadError(f"Invalid base-38 chunk length {len(chunk)}") from exc
        value = 0
        for char in reversed(chunk):
            if char not in _BASE38_INDEX:
                raise PayloadError(f"Invalid base-38 character {char!r}")
            value = value * 38 + _BASE38_INDEX[char]
        if value >= 1 << (8 * length):
            raise PayloadError("Base-38 chunk overflow")
        out += value.to_bytes(length, "little")
    return bytes(out)


def base38_encode(data: bytes) -> str:
    """Encode bytes in base-38 (inverse of :func:`base38_decode`)."""
    out: List[str] = []
    for start in range(0, len(data), 3):
        chunk = data[start:start + 3]
        digits = {3: 5, 2: 4, 1: 2}[len(chunk)]
        value = int.from_bytes(chunk, "little")
        for _ in range(digits):
            out.append(BASE38_ALPHABET[value % 38])
            value //= 38
    return "".join(out)


# ----------------------------------------------------------------------------- QR code
def _split_qr(code: str) -> str:
    text = code.strip()
    if text.upper().startswith(QR_PREFIX):
        text = text[len(QR_PREFIX):]
    else:
        raise PayloadError("Not a Matter QR payload (missing MT: prefix)")
    # Concatenated payloads (multi-device products) are separated by '*'; use the first one.
    text = text.split("*", 1)[0].strip()
    if not text:
        raise PayloadError("Empty Matter QR payload")
    return text


def parse_qr(code: str) -> Dict[str, Any]:
    """Decode an ``MT:`` onboarding payload into its fields.

    Raises ``PayloadError`` on malformed input or an invalid passcode.
    """
    raw = base38_decode(_split_qr(code))
    if len(raw) < QR_HEADER_BYTES:
        raise PayloadError(f"Matter QR payload too short ({len(raw)} bytes)")
    value = int.from_bytes(raw[:QR_HEADER_BYTES], "little")
    fields: Dict[str, int] = {}
    for name, bits in QR_FIELDS:
        fields[name] = value & ((1 << bits) - 1)
        value >>= bits
    if fields["version"] != 0:
        raise PayloadError(f"Unsupported Matter payload version {fields['version']}")
    if fields["padding"] != 0:
        raise PayloadError("Invalid Matter QR payload (non-zero padding)")
    check_passcode(fields["passcode"])
    result: Dict[str, Any] = {
        "version": fields["version"],
        "vendor_id": fields["vendor_id"],
        "product_id": fields["product_id"],
        "commissioning_flow": fields["commissioning_flow"],
        "discovery_capabilities": fields["discovery_capabilities"],
        "discriminator": fields["discriminator"],
        "short_discriminator": fields["discriminator"] >> 8,
        "passcode": fields["passcode"],
    }
    extra = raw[QR_HEADER_BYTES:]
    if extra:
        result["tlv"] = extra.hex()
    return result


def encode_qr(
    vendor_id: int,
    product_id: int,
    discriminator: int,
    passcode: int,
    commissioning_flow: int = 0,
    discovery_capabilities: int = DISCOVERY_ON_NETWORK,
    version: int = 0,
) -> str:
    """Build an ``MT:`` payload (exact inverse of :func:`parse_qr`)."""
    values = {
        "version": version,
        "vendor_id": vendor_id,
        "product_id": product_id,
        "commissioning_flow": commissioning_flow,
        "discovery_capabilities": discovery_capabilities,
        "discriminator": discriminator,
        "passcode": passcode,
        "padding": 0,
    }
    packed = 0
    shift = 0
    for name, bits in QR_FIELDS:
        value = int(values[name])
        if not 0 <= value < (1 << bits):
            raise PayloadError(f"{name} out of range for {bits} bits: {value}")
        packed |= value << shift
        shift += bits
    check_passcode(passcode)
    return QR_PREFIX + base38_encode(packed.to_bytes(QR_HEADER_BYTES, "little"))


# ----------------------------------------------------------------------------- manual code
def normalize_manual_code(code: str) -> str:
    """Strip separators (spaces, dashes, dots) from a manual pairing code."""
    return re.sub(r"[\s\-.]", "", code or "")


def parse_manual_code(code: str) -> Dict[str, Any]:
    """Decode an 11- or 21-digit manual pairing code (Verhoeff protected).

    The full 12-bit discriminator is not present in the manual code; only its 4 upper bits
    (``short_discriminator``) are. ``discriminator`` is exposed as ``short_discriminator << 8``.
    """
    digits = normalize_manual_code(code)
    if not digits.isdigit():
        raise PayloadError("Manual pairing code must contain digits only")
    if len(digits) not in (MANUAL_CODE_SHORT_LENGTH, MANUAL_CODE_LONG_LENGTH):
        raise PayloadError(f"Manual pairing code must be {MANUAL_CODE_SHORT_LENGTH} or {MANUAL_CODE_LONG_LENGTH} digits")
    if not verhoeff_validate(digits):
        raise PayloadError("Invalid manual pairing code (check digit mismatch)")
    digit1 = int(digits[0])
    chunk2 = int(digits[1:6])
    chunk3 = int(digits[6:10])
    if digit1 > 7 or chunk2 >= 1 << 16 or chunk3 >= 1 << 13:
        raise PayloadError("Invalid manual pairing code (field out of range)")
    vid_pid_present = bool(digit1 & 0x4)
    short_discriminator = ((digit1 & 0x3) << 2) | (chunk2 >> 14)
    passcode = (chunk3 << 14) | (chunk2 & 0x3FFF)
    check_passcode(passcode)
    vendor_id: Optional[int] = None
    product_id: Optional[int] = None
    if len(digits) == MANUAL_CODE_LONG_LENGTH:
        if not vid_pid_present:
            raise PayloadError("21-digit code without vendor/product flag")
        vendor_id = int(digits[10:15])
        product_id = int(digits[15:20])
        if vendor_id > 0xFFFF or product_id > 0xFFFF:
            raise PayloadError("Vendor/product id out of range")
    elif vid_pid_present:
        raise PayloadError("Vendor/product flag set on an 11-digit code")
    return {
        "version": 0,
        "vendor_id": vendor_id,
        "product_id": product_id,
        # Manual codes are only valid for the standard flow (custom flows require the QR code).
        "commissioning_flow": 0,
        "discovery_capabilities": 0,
        "discriminator": short_discriminator << 8,
        "short_discriminator": short_discriminator,
        "passcode": passcode,
        "vid_pid_present": vid_pid_present,
    }


def encode_manual_code(
    discriminator: int, passcode: int, vendor_id: Optional[int] = None, product_id: Optional[int] = None
) -> str:
    """Build a manual pairing code. ``discriminator`` may be the full 12-bit or the short 4-bit value."""
    check_passcode(passcode)
    if not 0 <= discriminator <= MAX_DISCRIMINATOR:
        raise PayloadError("Discriminator out of range")
    short = discriminator >> 8 if discriminator > 0xF else discriminator
    with_vid_pid = vendor_id is not None and product_id is not None
    digit1 = (int(with_vid_pid) << 2) | (short >> 2)
    chunk2 = ((short & 0x3) << 14) | (passcode & 0x3FFF)
    chunk3 = passcode >> 14
    body = f"{digit1}{chunk2:05d}{chunk3:04d}"
    if with_vid_pid:
        if not (0 <= int(vendor_id) <= 0xFFFF and 0 <= int(product_id) <= 0xFFFF):
            raise PayloadError("Vendor/product id out of range")
        body += f"{int(vendor_id):05d}{int(product_id):05d}"
    return body + str(verhoeff_checksum(body))


def format_manual_code(code: str) -> str:
    """Pretty print a manual code as ``3497-011-2332`` / ``6361-8757-5350-1111-1112-2``."""
    digits = normalize_manual_code(code)
    if len(digits) == MANUAL_CODE_SHORT_LENGTH:
        return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"
    if len(digits) == MANUAL_CODE_LONG_LENGTH:
        return "-".join(digits[i:i + 4] for i in range(0, 20, 4)) + f"-{digits[20]}"
    return digits


# ----------------------------------------------------------------------------- dispatcher
def looks_like_qr(code: str) -> bool:
    """True when the string starts with the ``MT:`` prefix."""
    return (code or "").strip().upper().startswith(QR_PREFIX)


def looks_like_manual_code(code: str) -> bool:
    """True when the string has the shape of a manual pairing code (11 or 21 digits)."""
    digits = normalize_manual_code(code)
    return digits.isdigit() and len(digits) in (MANUAL_CODE_SHORT_LENGTH, MANUAL_CODE_LONG_LENGTH)


def parse_onboarding_code(code: str) -> Optional[Dict[str, Any]]:
    """Parse either payload form into a normalised dict, or return ``None`` when it is neither.

    Result keys: ``kind`` (``matter_qr`` | ``matter_manual``), ``vendor_id``, ``product_id``,
    ``discriminator``, ``short_discriminator``, ``passcode``, ``commissioning_flow``,
    ``discovery_capabilities`` ({ble, on_network, soft_ap}), ``version``, ``vendor_name`` and
    ``code`` (the normalised code to hand to the commissioner).
    """
    if not code or not isinstance(code, str):
        return None
    text = code.strip()
    try:
        if looks_like_qr(text):
            parsed = parse_qr(text)
            kind = "matter_qr"
            normalised = QR_PREFIX + _split_qr(text)
        elif looks_like_manual_code(text):
            parsed = parse_manual_code(text)
            kind = "matter_manual"
            normalised = normalize_manual_code(text)
        else:
            return None
    except PayloadError as exc:
        logger.debug("Rejected Matter onboarding code: %s", exc)
        return None
    return {
        "kind": kind,
        "code": normalised,
        "vendor_id": parsed["vendor_id"],
        "product_id": parsed["product_id"],
        "vendor_name": vendor_name(parsed["vendor_id"]),
        "discriminator": parsed["discriminator"],
        "short_discriminator": parsed["short_discriminator"],
        "passcode": parsed["passcode"],
        "commissioning_flow": parsed["commissioning_flow"],
        "discovery_capabilities": discovery_capabilities(parsed["discovery_capabilities"]),
        "version": parsed["version"],
    }
