import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/features/add_device/matter_payload.dart';

void main() {
  group('Matter QR payload', () {
    // Reference vector of the Matter SDK lighting sample (VID 0xFFF1 / PID 0x8000, BLE).
    // Raw bytes after base-38: 88 FF 07 00 44 00 E0 4B 84 68 02.
    test('decodes the reference vector MT:Y.K9042C00KA0648G00', () {
      final payload = parseMatterQr('MT:Y.K9042C00KA0648G00');
      expect(payload.version, 0);
      expect(payload.vendorId, 65521);
      expect(payload.vendorIdHex, '0xFFF1');
      expect(payload.productId, 0x8000);
      expect(payload.productIdHex, '0x8000');
      expect(payload.commissioningFlow, 0);
      expect(payload.discoveryCapabilities, 2);
      expect(payload.supportsBle, isTrue);
      expect(payload.supportsOnNetwork, isFalse);
      expect(payload.discriminator, 3840);
      expect(payload.shortDiscriminator, 15);
      expect(payload.passcode, 20202021);
      expect(payload.isShortDiscriminator, isFalse);
    });

    // Same discriminator/passcode with PID 0x8001 and on-network discovery.
    test('decodes MT:-24J0AFN00KA0648G00 (vendor 0xFFF1, product 0x8001, on-network)', () {
      final payload = parseMatterQr('MT:-24J0AFN00KA0648G00');
      expect(payload.vendorId, 65521);
      expect(payload.productId, 32769);
      expect(payload.productIdHex, '0x8001');
      expect(payload.discoveryCapabilities, 4);
      expect(payload.supportsOnNetwork, isTrue);
      expect(payload.discriminator, 3840);
      expect(payload.passcode, 20202021);
      expect(encodeMatterQr(payload), 'MT:-24J0AFN00KA0648G00');
    });

    test('accepts lowercase prefix, surrounding spaces and concatenated payloads', () {
      expect(parseMatterQr('  mt:Y.K9042C00KA0648G00  ').passcode, 20202021);
      expect(parseMatterQr('MT:Y.K9042C00KA0648G00*MT:Y.K9042C00KA0648G00').discriminator, 3840);
    });

    test('round-trips through encode/decode', () {
      const original = MatterPayload(vendorId: 0x1234, productId: 0xABCD, commissioningFlow: 1, discoveryCapabilities: 6, discriminator: 2345, passcode: 12341234);
      final encoded = encodeMatterQr(original);
      expect(encoded, startsWith('MT:'));
      expect(encoded.length, 3 + 19);
      expect(parseMatterQr(encoded), original);
      // The reference vector re-encodes byte-for-byte.
      expect(encodeMatterQr(parseMatterQr('MT:Y.K9042C00KA0648G00')), 'MT:Y.K9042C00KA0648G00');
    });

    test('rejects malformed payloads', () {
      expect(() => parseMatterQr('Y.K9042C00KA0648G00'), throwsA(isA<MatterPayloadException>()));
      expect(() => parseMatterQr('MT:'), throwsA(isA<MatterPayloadException>()));
      expect(() => parseMatterQr('MT:Y.K9042C00KA0648G0a'), throwsA(isA<MatterPayloadException>()));
      expect(() => parseMatterQr('MT:Y.K9042C00'), throwsA(isA<MatterPayloadException>()));
      expect(() => parseMatterQr('MT:Y.K9042C00KA0648G0'), throwsA(isA<MatterPayloadException>()));
      expect(() => encodeMatterQr(const MatterPayload(discriminator: 5000, passcode: 20202021)), throwsA(isA<MatterPayloadException>()));
      expect(() => encodeMatterQr(const MatterPayload(discriminator: 15, passcode: 20202021, isShortDiscriminator: true)), throwsA(isA<MatterPayloadException>()));
    });

    test('rejects invalid passcodes embedded in a QR payload', () {
      expect(isValidPasscode(0), isFalse);
      expect(() => parseMatterQr(_rawEncode(const MatterPayload(discriminator: 3840, passcode: 11111111))), throwsA(isA<MatterPayloadException>()));
    });
  });

  group('base-38', () {
    test('encodes and decodes every chunk size', () {
      for (final bytes in [
        [0x01],
        [0x01, 0x02],
        [0x01, 0x02, 0x03],
        [0xFF, 0xFF, 0xFF, 0xFF],
        List<int>.generate(11, (i) => (i * 37) & 0xFF),
      ]) {
        expect(base38Decode(base38Encode(bytes)), bytes);
      }
    });

    test('rejects invalid lengths and characters', () {
      expect(() => base38Decode('A'), throwsA(isA<MatterPayloadException>()));
      expect(() => base38Decode('ABC'), throwsA(isA<MatterPayloadException>()));
      expect(() => base38Decode('ab'), throwsA(isA<MatterPayloadException>()));
      expect(() => base38Decode('.....'), throwsA(isA<MatterPayloadException>()));
    });
  });

  group('Matter manual pairing code', () {
    test('decodes the reference vector 34970112332', () {
      final payload = parseManualCode('34970112332');
      expect(payload.isShortDiscriminator, isTrue);
      expect(payload.shortDiscriminator, 15);
      expect(payload.discriminator, 15);
      expect(payload.passcode, 20202021);
      expect(payload.hasVendorProduct, isFalse);
      expect(verhoeffValidate('34970112332'), isTrue);
    });

    test('accepts dashes and spaces', () {
      expect(parseManualCode('3497-011-2332').passcode, 20202021);
      expect(parseManualCode(' 3497 011 2332 ').shortDiscriminator, 15);
      expect(formatManualCode('34970112332'), '3497-011-2332');
    });

    test('rejects a wrong Verhoeff check digit', () {
      expect(verhoeffValidate('34970112331'), isFalse);
      expect(() => parseManualCode('34970112331'), throwsA(predicate((e) => e is MatterPayloadException && e.message.contains('check digit'))));
      for (var digit = 0; digit < 10; digit++) {
        final code = '3497011233$digit';
        if (digit == 2) continue;
        expect(verhoeffValidate(code), isFalse, reason: code);
      }
    });

    test('rejects malformed codes', () {
      expect(() => parseManualCode('3497011233'), throwsA(isA<MatterPayloadException>()));
      expect(() => parseManualCode('3497O112332'), throwsA(isA<MatterPayloadException>()));
      expect(() => parseManualCode(''), throwsA(isA<MatterPayloadException>()));
    });

    test('computes Verhoeff check digits', () {
      expect(verhoeffCheckDigit('3497011233'), 2);
      expect(verhoeffCheckDigit('236'), 3);
      expect(verhoeffValidate('2363'), isTrue);
    });

    test('round-trips 11 and 21 digit codes', () {
      final short = parseManualCode('34970112332');
      expect(encodeManualCode(short), '34970112332');
      // From a full payload the short discriminator is derived from the 12-bit one.
      final full = parseMatterQr('MT:Y.K9042C00KA0648G00');
      expect(encodeManualCode(full), '34970112332');

      final long = encodeManualCode(full, includeVendorProduct: true);
      expect(long.length, 21);
      expect(verhoeffValidate(long), isTrue);
      final decoded = parseManualCode(long);
      expect(decoded.vendorId, 65521);
      expect(decoded.productId, 0x8000);
      expect(decoded.passcode, 20202021);
      expect(decoded.shortDiscriminator, 15);
      expect(decoded.hasVendorProduct, isTrue);
      expect(looksLikeManualCode(long), isTrue);
    });
  });

  group('helpers', () {
    test('isValidPasscode enforces the Matter rules', () {
      expect(isValidPasscode(20202021), isTrue);
      expect(isValidPasscode(1), isTrue);
      expect(isValidPasscode(99999998), isTrue);
      expect(isValidPasscode(99999999), isFalse);
      expect(isValidPasscode(0), isFalse);
      expect(isValidPasscode(12345678), isFalse);
      expect(isValidPasscode(87654321), isFalse);
      for (var d = 1; d <= 8; d++) {
        expect(isValidPasscode(d * 11111111), isFalse);
      }
    });

    test('tryParseMatterCode dispatches on the shape of the code', () {
      expect(tryParseMatterCode('MT:Y.K9042C00KA0648G00')?.discriminator, 3840);
      expect(tryParseMatterCode('34970112332')?.shortDiscriminator, 15);
      expect(tryParseMatterCode('34970112331'), isNull);
      expect(tryParseMatterCode('hello'), isNull);
      expect(tryParseMatterCode(''), isNull);
      expect(looksLikeMatterCode('MT:abc'), isTrue);
      expect(looksLikeMatterCode('34970112332'), isTrue);
      expect(looksLikeMatterCode('https://example.com'), isFalse);
    });
  });
}

/// Encode without the passcode guard (to build an invalid payload for the decoder test).
String _rawEncode(MatterPayload p) {
  final bytes = List<int>.filled(11, 0);
  var offset = 0;
  void write(int bits, int value) {
    for (var i = 0; i < bits; i++) {
      if ((value >> i) & 1 == 1) bytes[(offset + i) >> 3] |= 1 << ((offset + i) & 7);
    }
    offset += bits;
  }

  write(3, p.version);
  write(16, p.vendorId);
  write(16, p.productId);
  write(2, p.commissioningFlow);
  write(8, p.discoveryCapabilities);
  write(12, p.discriminator);
  write(27, p.passcode);
  write(4, 0);
  return 'MT:${base38Encode(bytes)}';
}
