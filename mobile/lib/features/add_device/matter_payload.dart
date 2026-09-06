/// Pure Dart port of the Matter onboarding payload codec.
///
/// Two representations exist for the same commissioning information:
///
/// * the QR code payload `MT:<base-38>` — 88 bits packed little-endian
///   (version 3, vendorId 16, productId 16, commissioningFlow 2,
///   discoveryCapabilities 8, discriminator 12, passcode 27, padding 4);
/// * the manual pairing code — 11 digits (or 21 when the vendor/product ids
///   are included) protected by a Verhoeff check digit.
///
/// This file has no Flutter dependency so it can be unit-tested directly.
library;

/// Thrown when a code cannot be decoded.
class MatterPayloadException implements Exception {
  const MatterPayloadException(this.message);

  final String message;

  @override
  String toString() => 'MatterPayloadException: $message';
}

/// Decoded onboarding information.
class MatterPayload {
  const MatterPayload({
    required this.discriminator,
    required this.passcode,
    this.version = 0,
    this.vendorId = 0,
    this.productId = 0,
    this.commissioningFlow = 0,
    this.discoveryCapabilities = 0,
    this.isShortDiscriminator = false,
  });

  /// Payload version (always 0 today).
  final int version;
  final int vendorId;
  final int productId;

  /// 0 = standard, 1 = user-intent, 2 = custom.
  final int commissioningFlow;

  /// Bit mask: 1 = Soft-AP, 2 = BLE, 4 = on IP network.
  final int discoveryCapabilities;

  /// 12-bit discriminator, or the 4-bit "short" one for manual codes
  /// (see [isShortDiscriminator]).
  final int discriminator;

  /// 27-bit setup passcode.
  final int passcode;

  /// True when [discriminator] only carries the 4 most significant bits
  /// (manual pairing codes do not transport the full 12-bit value).
  final bool isShortDiscriminator;

  /// The 4-bit short discriminator (upper bits of the 12-bit one).
  int get shortDiscriminator => isShortDiscriminator ? discriminator & 0xF : (discriminator >> 8) & 0xF;

  bool get hasVendorProduct => vendorId != 0 || productId != 0;
  bool get supportsSoftAp => discoveryCapabilities & 0x01 != 0;
  bool get supportsBle => discoveryCapabilities & 0x02 != 0;
  bool get supportsOnNetwork => discoveryCapabilities & 0x04 != 0;

  String get vendorIdHex => _hex4(vendorId);
  String get productIdHex => _hex4(productId);

  Map<String, dynamic> toJson() => {
        'version': version,
        'vendor_id': vendorId,
        'product_id': productId,
        'commissioning_flow': commissioningFlow,
        'discovery_capabilities': discoveryCapabilities,
        'discriminator': discriminator,
        'short_discriminator': shortDiscriminator,
        'passcode': passcode,
        'is_short_discriminator': isShortDiscriminator,
      };

  MatterPayload copyWith({
    int? version,
    int? vendorId,
    int? productId,
    int? commissioningFlow,
    int? discoveryCapabilities,
    int? discriminator,
    int? passcode,
    bool? isShortDiscriminator,
  }) =>
      MatterPayload(
        version: version ?? this.version,
        vendorId: vendorId ?? this.vendorId,
        productId: productId ?? this.productId,
        commissioningFlow: commissioningFlow ?? this.commissioningFlow,
        discoveryCapabilities: discoveryCapabilities ?? this.discoveryCapabilities,
        discriminator: discriminator ?? this.discriminator,
        passcode: passcode ?? this.passcode,
        isShortDiscriminator: isShortDiscriminator ?? this.isShortDiscriminator,
      );

  @override
  bool operator ==(Object other) =>
      other is MatterPayload &&
      other.version == version &&
      other.vendorId == vendorId &&
      other.productId == productId &&
      other.commissioningFlow == commissioningFlow &&
      other.discoveryCapabilities == discoveryCapabilities &&
      other.discriminator == discriminator &&
      other.passcode == passcode &&
      other.isShortDiscriminator == isShortDiscriminator;

  @override
  int get hashCode => Object.hash(version, vendorId, productId, commissioningFlow, discoveryCapabilities, discriminator, passcode, isShortDiscriminator);

  @override
  String toString() =>
      'MatterPayload(vendor: $vendorIdHex, product: $productIdHex, discriminator: $discriminator${isShortDiscriminator ? ' (short)' : ''}, passcode: $passcode, caps: $discoveryCapabilities)';
}

String _hex4(int value) => '0x${value.toRadixString(16).toUpperCase().padLeft(4, '0')}';

// ----------------------------------------------------------------------------
// Constants
// ----------------------------------------------------------------------------

/// Prefix of every Matter QR payload.
const String kMatterQrPrefix = 'MT:';

/// Base-38 alphabet used by the QR payload.
const String kBase38Alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-.';

const int _kVersionBits = 3;
const int _kVendorIdBits = 16;
const int _kProductIdBits = 16;
const int _kCommissioningFlowBits = 2;
const int _kDiscoveryCapabilitiesBits = 8;
const int _kDiscriminatorBits = 12;
const int _kPasscodeBits = 27;
const int _kPaddingBits = 4;
const int _kTotalBits = _kVersionBits +
    _kVendorIdBits +
    _kProductIdBits +
    _kCommissioningFlowBits +
    _kDiscoveryCapabilitiesBits +
    _kDiscriminatorBits +
    _kPasscodeBits +
    _kPaddingBits; // 88
const int _kTotalBytes = _kTotalBits ~/ 8; // 11

const int kMaxPasscode = 99999998;
const Set<int> _kForbiddenPasscodes = {
  11111111,
  22222222,
  33333333,
  44444444,
  55555555,
  66666666,
  77777777,
  88888888,
  12345678,
  87654321,
};

/// Passcodes must be in 1..99999998 and not one of the trivial sequences.
bool isValidPasscode(int passcode) => passcode >= 1 && passcode <= kMaxPasscode && !_kForbiddenPasscodes.contains(passcode);

// ----------------------------------------------------------------------------
// Base-38
// ----------------------------------------------------------------------------

/// Decode a base-38 string (chunks of 5 chars -> 3 bytes, 4 -> 2, 2 -> 1).
List<int> base38Decode(String input) {
  final bytes = <int>[];
  var index = 0;
  while (index < input.length) {
    final remaining = input.length - index;
    final int chars;
    final int byteCount;
    if (remaining >= 5) {
      chars = 5;
      byteCount = 3;
    } else if (remaining == 4) {
      chars = 4;
      byteCount = 2;
    } else if (remaining == 2) {
      chars = 2;
      byteCount = 1;
    } else {
      throw const MatterPayloadException('Invalid base-38 length');
    }
    var value = 0;
    var multiplier = 1;
    for (var i = 0; i < chars; i++) {
      final digit = kBase38Alphabet.indexOf(input[index + i]);
      if (digit < 0) throw MatterPayloadException("Invalid base-38 character '${input[index + i]}'");
      value += digit * multiplier;
      multiplier *= 38;
    }
    if (value >= (1 << (8 * byteCount))) throw const MatterPayloadException('Base-38 chunk overflow');
    for (var i = 0; i < byteCount; i++) {
      bytes.add((value >> (8 * i)) & 0xFF);
    }
    index += chars;
  }
  return bytes;
}

/// Encode bytes to base-38 (3 bytes -> 5 chars, 2 -> 4, 1 -> 2).
String base38Encode(List<int> bytes) {
  final out = StringBuffer();
  var index = 0;
  while (index < bytes.length) {
    final remaining = bytes.length - index;
    final byteCount = remaining >= 3 ? 3 : remaining;
    final chars = byteCount == 3 ? 5 : (byteCount == 2 ? 4 : 2);
    var value = 0;
    for (var i = 0; i < byteCount; i++) {
      value |= (bytes[index + i] & 0xFF) << (8 * i);
    }
    for (var i = 0; i < chars; i++) {
      out.write(kBase38Alphabet[value % 38]);
      value ~/= 38;
    }
    index += byteCount;
  }
  return out.toString();
}

// ----------------------------------------------------------------------------
// Bit helpers (little-endian bit order, LSB first)
// ----------------------------------------------------------------------------

int _readBits(List<int> bytes, int offset, int count) {
  var value = 0;
  for (var i = 0; i < count; i++) {
    final bitIndex = offset + i;
    final bit = (bytes[bitIndex >> 3] >> (bitIndex & 7)) & 1;
    value |= bit << i;
  }
  return value;
}

void _writeBits(List<int> bytes, int offset, int count, int value) {
  for (var i = 0; i < count; i++) {
    if ((value >> i) & 1 == 1) {
      final bitIndex = offset + i;
      bytes[bitIndex >> 3] |= 1 << (bitIndex & 7);
    }
  }
}

// ----------------------------------------------------------------------------
// QR payload
// ----------------------------------------------------------------------------

/// True when [raw] looks like a Matter QR payload.
bool isMatterQr(String raw) => raw.trim().toUpperCase().startsWith(kMatterQrPrefix);

/// Decode a `MT:` QR payload. Throws [MatterPayloadException] on invalid input.
MatterPayload parseMatterQr(String raw) {
  var code = raw.trim();
  if (!code.toUpperCase().startsWith(kMatterQrPrefix)) {
    throw const MatterPayloadException('Missing MT: prefix');
  }
  code = code.substring(kMatterQrPrefix.length);
  // Concatenated payloads ("MT:...*MT:...") — keep the first one.
  final star = code.indexOf('*');
  if (star >= 0) code = code.substring(0, star);
  code = code.toUpperCase();
  if (code.isEmpty) throw const MatterPayloadException('Empty payload');

  final bytes = base38Decode(code);
  if (bytes.length < _kTotalBytes) throw const MatterPayloadException('Payload too short');

  var offset = 0;
  int read(int bits) {
    final value = _readBits(bytes, offset, bits);
    offset += bits;
    return value;
  }

  final version = read(_kVersionBits);
  final vendorId = read(_kVendorIdBits);
  final productId = read(_kProductIdBits);
  final commissioningFlow = read(_kCommissioningFlowBits);
  final discoveryCapabilities = read(_kDiscoveryCapabilitiesBits);
  final discriminator = read(_kDiscriminatorBits);
  final passcode = read(_kPasscodeBits);
  final padding = read(_kPaddingBits);

  if (version != 0) throw MatterPayloadException('Unsupported payload version $version');
  if (padding != 0) throw const MatterPayloadException('Invalid padding');
  if (!isValidPasscode(passcode)) throw const MatterPayloadException('Invalid passcode');

  return MatterPayload(
    version: version,
    vendorId: vendorId,
    productId: productId,
    commissioningFlow: commissioningFlow,
    discoveryCapabilities: discoveryCapabilities,
    discriminator: discriminator,
    passcode: passcode,
  );
}

/// Encode a payload as a `MT:` QR string.
String encodeMatterQr(MatterPayload payload) {
  if (payload.isShortDiscriminator) throw const MatterPayloadException('A QR payload needs the full 12-bit discriminator');
  if (!isValidPasscode(payload.passcode)) throw const MatterPayloadException('Invalid passcode');
  final bytes = List<int>.filled(_kTotalBytes, 0);
  var offset = 0;
  void write(int bits, int value) {
    if (value < 0 || value >= (1 << bits)) throw MatterPayloadException('Value $value does not fit in $bits bits');
    _writeBits(bytes, offset, bits, value);
    offset += bits;
  }

  write(_kVersionBits, payload.version);
  write(_kVendorIdBits, payload.vendorId);
  write(_kProductIdBits, payload.productId);
  write(_kCommissioningFlowBits, payload.commissioningFlow);
  write(_kDiscoveryCapabilitiesBits, payload.discoveryCapabilities);
  write(_kDiscriminatorBits, payload.discriminator);
  write(_kPasscodeBits, payload.passcode);
  write(_kPaddingBits, 0);
  return '$kMatterQrPrefix${base38Encode(bytes)}';
}

// ----------------------------------------------------------------------------
// Verhoeff check digit
// ----------------------------------------------------------------------------

const List<List<int>> _verhoeffD = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
  [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
  [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
  [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
  [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
  [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
  [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
  [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
  [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
];

const List<List<int>> _verhoeffP = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
  [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
  [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
  [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
  [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
  [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
  [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
];

const List<int> _verhoeffInv = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9];

int _digitAt(String digits, int index) {
  final code = digits.codeUnitAt(index) - 0x30;
  if (code < 0 || code > 9) throw MatterPayloadException("Invalid digit '${digits[index]}'");
  return code;
}

/// Compute the Verhoeff check digit for [digits].
int verhoeffCheckDigit(String digits) {
  var c = 0;
  final n = digits.length;
  for (var i = 0; i < n; i++) {
    final digit = _digitAt(digits, n - 1 - i);
    c = _verhoeffD[c][_verhoeffP[(i + 1) % 8][digit]];
  }
  return _verhoeffInv[c];
}

/// Validate a number whose last digit is a Verhoeff check digit.
bool verhoeffValidate(String digits) {
  if (digits.isEmpty) return false;
  var c = 0;
  final n = digits.length;
  for (var i = 0; i < n; i++) {
    final digit = _digitAt(digits, n - 1 - i);
    c = _verhoeffD[c][_verhoeffP[i % 8][digit]];
  }
  return c == 0;
}

// ----------------------------------------------------------------------------
// Manual pairing code
// ----------------------------------------------------------------------------

/// Keep only the digits of a manual code ("3497-011-2332" -> "34970112332").
String normalizeManualCode(String raw) => raw.replaceAll(RegExp(r'[\s\-]'), '');

/// True when [raw] has the shape of a manual pairing code (11 or 21 digits).
bool looksLikeManualCode(String raw) {
  final digits = normalizeManualCode(raw);
  return (digits.length == 11 || digits.length == 21) && RegExp(r'^\d+$').hasMatch(digits);
}

/// Decode an 11/21-digit manual pairing code (Verhoeff protected).
MatterPayload parseManualCode(String raw) {
  final code = normalizeManualCode(raw);
  if (!RegExp(r'^\d+$').hasMatch(code)) throw const MatterPayloadException('Manual code must contain digits only');
  if (code.length != 11 && code.length != 21) throw const MatterPayloadException('Manual code must have 11 or 21 digits');
  if (!verhoeffValidate(code)) throw const MatterPayloadException('Invalid check digit');

  final digit1 = _digitAt(code, 0);
  final vidPidPresent = (digit1 >> 2) & 1 == 1;
  final discriminatorHigh = digit1 & 0x3; // bits 11..10
  final chunk2 = int.parse(code.substring(1, 6));
  final chunk3 = int.parse(code.substring(6, 10));
  final discriminatorLow = (chunk2 >> 14) & 0x3; // bits 9..8
  final passcode = (chunk3 << 14) | (chunk2 & 0x3FFF);
  final shortDiscriminator = (discriminatorHigh << 2) | discriminatorLow;

  if (vidPidPresent && code.length != 21) throw const MatterPayloadException('Vendor/product ids announced but missing');
  if (!vidPidPresent && code.length != 11) throw const MatterPayloadException('Unexpected vendor/product ids');
  if (!isValidPasscode(passcode)) throw const MatterPayloadException('Invalid passcode');

  final vendorId = vidPidPresent ? int.parse(code.substring(10, 15)) : 0;
  final productId = vidPidPresent ? int.parse(code.substring(15, 20)) : 0;
  if (vendorId > 0xFFFF || productId > 0xFFFF) throw const MatterPayloadException('Vendor/product id out of range');

  return MatterPayload(
    vendorId: vendorId,
    productId: productId,
    commissioningFlow: vidPidPresent ? 2 : 0,
    discriminator: shortDiscriminator,
    passcode: passcode,
    isShortDiscriminator: true,
  );
}

/// Encode a manual pairing code (11 digits, or 21 with [includeVendorProduct]).
String encodeManualCode(MatterPayload payload, {bool includeVendorProduct = false}) {
  if (!isValidPasscode(payload.passcode)) throw const MatterPayloadException('Invalid passcode');
  final short = payload.shortDiscriminator;
  final digit1 = ((includeVendorProduct ? 1 : 0) << 2) | ((short >> 2) & 0x3);
  final chunk2 = ((short & 0x3) << 14) | (payload.passcode & 0x3FFF);
  final chunk3 = payload.passcode >> 14;
  final buffer = StringBuffer()
    ..write(digit1)
    ..write(chunk2.toString().padLeft(5, '0'))
    ..write(chunk3.toString().padLeft(4, '0'));
  if (includeVendorProduct) {
    buffer
      ..write(payload.vendorId.toString().padLeft(5, '0'))
      ..write(payload.productId.toString().padLeft(5, '0'));
  }
  final body = buffer.toString();
  return '$body${verhoeffCheckDigit(body)}';
}

/// Pretty manual code ("3497-011-2332").
String formatManualCode(String raw) {
  final digits = normalizeManualCode(raw);
  if (digits.length == 11) return '${digits.substring(0, 4)}-${digits.substring(4, 7)}-${digits.substring(7)}';
  if (digits.length == 21) {
    return '${digits.substring(0, 4)}-${digits.substring(4, 7)}-${digits.substring(7, 10)}-${digits.substring(10, 15)}-${digits.substring(15, 20)}-${digits.substring(20)}';
  }
  return raw;
}

// ----------------------------------------------------------------------------
// Convenience
// ----------------------------------------------------------------------------

/// Decode either a QR payload or a manual code.
MatterPayload parseMatterCode(String raw) => isMatterQr(raw) ? parseMatterQr(raw) : parseManualCode(raw);

/// Like [parseMatterCode] but returns null instead of throwing.
MatterPayload? tryParseMatterCode(String raw) {
  if (raw.trim().isEmpty) return null;
  try {
    return parseMatterCode(raw);
  } on MatterPayloadException {
    return null;
  }
}

/// True when [raw] could be a Matter code (QR or manual).
bool looksLikeMatterCode(String raw) => isMatterQr(raw) || looksLikeManualCode(raw);
