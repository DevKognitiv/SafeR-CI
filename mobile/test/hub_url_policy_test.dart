import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:safer_ci/core/api/api_exception.dart';
import 'package:safer_ci/core/api/hub_client.dart';
import 'package:safer_ci/core/config.dart';
import 'package:safer_ci/core/hub_url_policy.dart';
import 'package:safer_ci/features/auth/widgets/auth_validators.dart';
import 'package:flutter/material.dart';

import 'helpers/pump_app.dart';

/// Adapter that never touches the network: records the request and answers 200.
class _RecordingAdapter implements HttpClientAdapter {
  final List<RequestOptions> requests = [];

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? requestStream, Future<void>? cancelFuture) async {
    requests.add(options);
    return ResponseBody.fromString('{"ok": true}', 200, headers: {
      Headers.contentTypeHeader: [Headers.jsonContentType],
    });
  }

  @override
  void close({bool force = false}) {}
}

({HubClient client, _RecordingAdapter adapter}) _clientFor(String baseUrl, {String? token = 'secret-token'}) {
  final adapter = _RecordingAdapter();
  final dio = Dio()..httpClientAdapter = adapter;
  return (client: HubClient(baseUrl: baseUrl, tokenProvider: () => token, dio: dio), adapter: adapter);
}

final Matcher throwsInsecureHubUrl = throwsA(isA<ApiException>()
    .having((e) => e.code, 'code', kInsecureHubUrlCode)
    .having((e) => e.message, 'message', kInsecureHubUrlMessageFr)
    .having((e) => e.status, 'status', isNull));

void main() {
  group('HubUrlPolicy.check', () {
    const cases = <String, HubUrlVerdict>{
      // https: always fine.
      'https://hub.example.com': HubUrlVerdict.ok,
      'https://api.safer-ci.app/safer': HubUrlVerdict.ok,
      'https://203.0.113.10:8443': HubUrlVerdict.ok,
      // http on the local network.
      'http://localhost:8000': HubUrlVerdict.ok,
      'http://LOCALHOST:8000/': HubUrlVerdict.ok,
      'http://hub.localhost:8000': HubUrlVerdict.ok,
      'http://127.0.0.1:8000': HubUrlVerdict.ok,
      'http://127.42.0.1': HubUrlVerdict.ok,
      'http://[::1]:8000': HubUrlVerdict.ok,
      'http://10.0.2.2:8000': HubUrlVerdict.ok,
      'http://10.1.2.3': HubUrlVerdict.ok,
      'http://172.16.0.1:8000': HubUrlVerdict.ok,
      'http://172.31.255.254': HubUrlVerdict.ok,
      'http://192.168.1.20:8000': HubUrlVerdict.ok,
      'http://169.254.10.10': HubUrlVerdict.ok,
      'http://[fe80::1]:8000': HubUrlVerdict.ok,
      'http://[fe80::1%25wlan0]:8000': HubUrlVerdict.ok,
      'http://[fd12:3456::1]:8000': HubUrlVerdict.ok,
      'http://safer-hub.local:8000': HubUrlVerdict.ok,
      'http://Safer-Hub.LOCAL.': HubUrlVerdict.ok,
      'http://cam.garage.local': HubUrlVerdict.ok,
      ' http://192.168.1.20:8000/ ': HubUrlVerdict.ok,
      // http to anything routable.
      'http://hub.example.com': HubUrlVerdict.insecurePublic,
      'http://hub.example.com:8000/api': HubUrlVerdict.insecurePublic,
      'http://203.0.113.10:8000': HubUrlVerdict.insecurePublic,
      'http://172.15.0.1': HubUrlVerdict.insecurePublic,
      'http://172.32.0.1': HubUrlVerdict.insecurePublic,
      'http://192.169.1.1': HubUrlVerdict.insecurePublic,
      'http://11.0.0.1': HubUrlVerdict.insecurePublic,
      'http://[2001:db8::1]:8000': HubUrlVerdict.insecurePublic,
      'http://safer-hub.localdomain': HubUrlVerdict.insecurePublic,
      'http://notlocal.example': HubUrlVerdict.insecurePublic,
      'http://10.0.0.256': HubUrlVerdict.insecurePublic,
      // not a hub URL at all.
      '': HubUrlVerdict.invalid,
      'not a url': HubUrlVerdict.invalid,
      'hub.example.com:8000': HubUrlVerdict.invalid,
      '//hub.example.com': HubUrlVerdict.invalid,
      'http://': HubUrlVerdict.invalid,
      'ftp://192.168.1.20': HubUrlVerdict.invalid,
      'ws://192.168.1.20:8000': HubUrlVerdict.invalid,
      'javascript:alert(1)': HubUrlVerdict.invalid,
    };

    for (final entry in cases.entries) {
      test('"${entry.key}" -> ${entry.value.name}', () => expect(HubUrlPolicy.check(entry.key), entry.value));
    }

    test('the build-time default hub URL is valid', () {
      expect(HubUrlPolicy.check(AppConfig.defaultHubUrl), HubUrlVerdict.ok);
      expect(HubUrlPolicy.check('http://localhost:8000'), HubUrlVerdict.ok);
    });

    test('isPrivateHost handles bare hosts', () {
      expect(HubUrlPolicy.isPrivateHost('localhost'), isTrue);
      expect(HubUrlPolicy.isPrivateHost('safer-hub.local'), isTrue);
      expect(HubUrlPolicy.isPrivateHost('192.168.0.1'), isTrue);
      expect(HubUrlPolicy.isPrivateHost('::1'), isTrue);
      expect(HubUrlPolicy.isPrivateHost('hub.example.com'), isFalse);
      expect(HubUrlPolicy.isPrivateHost('8.8.8.8'), isFalse);
      expect(HubUrlPolicy.isPrivateHost(''), isFalse);
    });
  });

  group('HubClient transport guard', () {
    test('refuses to send the bearer token over http to a public host', () async {
      final c = _clientFor('http://hub.example.com');
      await expectLater(c.client.me(), throwsInsecureHubUrl);
      await expectLater(c.client.homes(), throwsInsecureHubUrl);
      expect(await c.client.health(), isFalse);
      expect(c.adapter.requests, isEmpty);
    });

    test('refuses to send the login or registration password over http to a public host', () async {
      final c = _clientFor('http://hub.example.com:8000', token: null);
      await expectLater(c.client.login(email: 'alice@safer.ci', password: 'secret'), throwsInsecureHubUrl);
      await expectLater(c.client.register(email: 'alice@safer.ci', password: 'secret', name: 'Alice'), throwsInsecureHubUrl);
      expect(c.adapter.requests, isEmpty);
    });

    test('still allows secret-free reachability checks of a public http hub', () async {
      final c = _clientFor('http://hub.example.com', token: null);
      expect(await c.client.health(), isTrue);
      expect(c.adapter.requests.single.headers.containsKey('Authorization'), isFalse);
      expect(c.adapter.requests.single.uri.toString(), 'http://hub.example.com/api/v1/hub/health');
    });

    test('sends the bearer token over https and over http on the local network', () async {
      for (final base in ['https://hub.example.com', 'http://192.168.1.20:8000', 'http://safer-hub.local:8000', 'http://localhost:8000', 'http://10.0.2.2:8000']) {
        final c = _clientFor(base);
        expect(await c.client.health(), isTrue, reason: base);
        expect(c.adapter.requests.single.headers['Authorization'], 'Bearer secret-token', reason: base);
        expect(c.adapter.requests.single.uri.toString(), startsWith('$base/api/v1/hub/'), reason: base);
      }
    });

    test('the guard follows the base URL when it changes at runtime', () async {
      final c = _clientFor('https://hub.example.com');
      expect(await c.client.health(), isTrue);
      c.client.baseUrl = 'http://hub.example.com';
      expect(await c.client.health(), isFalse);
      expect(c.adapter.requests, hasLength(1));
      c.client.baseUrl = 'http://192.168.1.20:8000/';
      expect(await c.client.health(), isTrue);
      expect(c.adapter.requests, hasLength(2));
    });
  });

  group('HubUrlPolicy canonical IPv4 and the platform cleartext rule', () {
    test('leading-zero octets are not private: browsers read them as octal', () {
      expect(HubUrlPolicy.check('http://010.0.0.1'), HubUrlVerdict.insecurePublic);
      expect(HubUrlPolicy.check('http://192.168.01.1'), HubUrlVerdict.insecurePublic);
      expect(HubUrlPolicy.check('http://0177.0.0.1'), HubUrlVerdict.insecurePublic);
      expect(HubUrlPolicy.check('http://192.168.0.1'), HubUrlVerdict.ok);
      expect(HubUrlPolicy.check('http://10.0.0.1'), HubUrlVerdict.ok);
    });

    test('isCleartextRawIp flags http to an IP literal the Android config does not allow', () {
      expect(HubUrlPolicy.isCleartextRawIp('http://192.168.1.20:8000'), isTrue);
      expect(HubUrlPolicy.isCleartextRawIp('http://10.1.2.3'), isTrue);
      expect(HubUrlPolicy.isCleartextRawIp('http://[fe80::1]:8000'), isTrue);
      expect(HubUrlPolicy.isCleartextRawIp('http://127.0.0.1:8000'), isFalse);
      expect(HubUrlPolicy.isCleartextRawIp('http://localhost:8000'), isFalse);
      expect(HubUrlPolicy.isCleartextRawIp('http://10.0.2.2:8000'), isFalse);
      expect(HubUrlPolicy.isCleartextRawIp('http://safer-hub.local:8000'), isFalse);
      expect(HubUrlPolicy.isCleartextRawIp('https://192.168.1.20'), isFalse);
      expect(HubUrlPolicy.isCleartextRawIp('not a url'), isFalse);
    });

    testWidgets('the validator explains the Android release rule instead of accepting an unreachable URL', (tester) async {
      late BuildContext ctx;
      await pumpApp(tester, Builder(builder: (context) {
        ctx = context;
        return const SizedBox();
      }));
      expect(AuthValidators.hubUrl(ctx, 'http://192.168.1.20:8000', cleartextToRawIpBlocked: false), isNull);
      expect(AuthValidators.hubUrl(ctx, 'http://192.168.1.20:8000', cleartextToRawIpBlocked: true), contains('safer-hub.local'));
      expect(AuthValidators.hubUrl(ctx, 'http://safer-hub.local:8000', cleartextToRawIpBlocked: true), isNull);
      expect(AuthValidators.hubUrl(ctx, 'https://192.168.1.20', cleartextToRawIpBlocked: true), isNull);
      expect(AuthValidators.hubUrl(ctx, 'http://10.0.2.2:8000', cleartextToRawIpBlocked: true), isNull);
      // in tests (a debug build) the platform rule is off, so the LAN example stays accepted
      expect(AuthValidators.hubUrl(ctx, 'http://192.168.1.20:8000'), isNull);
    });
  });

  group('HubClient.authHeaders', () {
    test('carries the bearer token only where the interceptor would send it', () {
      expect(_clientFor('https://hub.example.com').client.authHeaders(), {'Authorization': 'Bearer secret-token'});
      expect(_clientFor('http://192.168.1.20:8000').client.authHeaders(), {'Authorization': 'Bearer secret-token'});
      expect(_clientFor('http://hub.example.com').client.authHeaders(), isEmpty);
      expect(_clientFor('https://hub.example.com', token: null).client.authHeaders(), isEmpty);
    });
  });
}
