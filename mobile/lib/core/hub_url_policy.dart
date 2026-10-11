/// Transport policy for the hub base URL.
///
/// SafeR talks to a hub that is either on the local network (Raspberry Pi,
/// `safer-hub.local`, a LAN IP) or reachable publicly through a relay. Secrets
/// (the session token, the login password) must never travel in cleartext to a
/// public host, so plain `http://` is only accepted for addresses that cannot
/// leave the local network. Everything else has to use `https://`.
///
/// Pure Dart, no Flutter imports: it is used by the form validators, by
/// [HubClient] as a last line of defence and by the realtime socket.
library;

/// Result of [HubUrlPolicy.check].
import 'package:flutter/foundation.dart' show TargetPlatform, defaultTargetPlatform, kDebugMode, kIsWeb;

enum HubUrlVerdict {
  /// Usable as a hub base URL.
  ok,

  /// Not an `http(s)://host[:port]` URL.
  invalid,

  /// `http://` to a host that is not private: credentials would travel in cleartext.
  insecurePublic,
}

/// Error code carried by the `ApiException` raised when a request carrying a
/// secret targets an [HubUrlVerdict.insecurePublic] base URL.
const String kInsecureHubUrlCode = 'insecure_hub_url';

/// French message of that `ApiException` (French is the default language of
/// the hub client; the UI picks the locale through `localizedErrorMessage`).
const String kInsecureHubUrlMessageFr = 'Connexion non sécurisée refusée : utilisez https';

/// English counterpart of [kInsecureHubUrlMessageFr].
const String kInsecureHubUrlMessageEn = 'Insecure connection refused: use https';

/// Decides whether a hub URL may be used, and over which transport.
class HubUrlPolicy {
  /// True when the platform itself refuses cleartext to a raw IP address: Android release and
  /// profile builds carry a network security config that allows `http://` only for localhost,
  /// the emulator host and `*.local` names (debug builds have a permissive overlay). Android
  /// cannot express RFC 1918 ranges in that file, so a LAN hub on a raw IP must be reached by
  /// its `.local` name or over https in those builds.
  static bool get cleartextToRawIpBlockedByPlatform =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android && !kDebugMode;

  /// `http://` to an IP literal the Android config does not list (anything but loopback and
  /// the emulator host). Such a URL passes [check] (no secret is at risk on a private network)
  /// but cannot connect in a release build; the validators explain that instead of letting the
  /// user discover an unreachable hub.
  static bool isCleartextRawIp(String url) {
    final uri = Uri.tryParse(url.trim());
    if (uri == null || uri.scheme.toLowerCase() != 'http') return false;
    final host = uri.host.toLowerCase();
    if (host.isEmpty) return false;
    if (host.contains(':')) return true; // IPv6 literal
    final v4 = _parseIPv4(host);
    if (v4 == null) return false;
    if (v4[0] == 127) return false;
    if (host == '10.0.2.2') return false;
    return true;
  }

  HubUrlPolicy._();

  /// `https` is always fine. `http` is only fine for loopback, the Android
  /// emulator host, RFC 1918 ranges, link-local ranges and mDNS `.local` names.
  static HubUrlVerdict check(String url) {
    final uri = Uri.tryParse(url.trim());
    if (uri == null || !uri.hasAuthority || uri.host.isEmpty) return HubUrlVerdict.invalid;
    switch (uri.scheme) {
      case 'https':
        return HubUrlVerdict.ok;
      case 'http':
        return isPrivateHost(uri.host) ? HubUrlVerdict.ok : HubUrlVerdict.insecurePublic;
      default:
        return HubUrlVerdict.invalid;
    }
  }

  /// True when [host] cannot be routed on the public internet:
  /// `localhost` / `*.localhost`, `127.0.0.0/8`, `::1`, the emulator host
  /// `10.0.2.2`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`,
  /// `169.254.0.0/16`, IPv6 link-local (`fe80::/10`) and unique-local
  /// (`fc00::/7`) addresses, and mDNS `*.local` names.
  static bool isPrivateHost(String host) {
    var h = host.trim().toLowerCase();
    if (h.endsWith('.')) h = h.substring(0, h.length - 1);
    if (h.isEmpty) return false;
    if (h == 'localhost' || h.endsWith('.localhost')) return true;
    if (h.endsWith('.local')) return true;
    final v4 = _parseIPv4(h);
    if (v4 != null) return _isPrivateIPv4(v4);
    return _isPrivateIPv6(h);
  }

  static List<int>? _parseIPv4(String host) {
    final parts = host.split('.');
    if (parts.length != 4) return null;
    final octets = <int>[];
    for (final part in parts) {
      if (part.isEmpty || part.length > 3 || !_digits.hasMatch(part)) return null;
      // Only canonical decimal parts: browsers read `010` as octal (8), so a leading zero would
      // make the policy and the wire disagree about which address receives the secret.
      if (part.length > 1 && part.startsWith('0')) return null;
      final value = int.parse(part);
      if (value > 255) return null;
      octets.add(value);
    }
    return octets;
  }

  static final RegExp _digits = RegExp(r'^[0-9]+$');

  static bool _isPrivateIPv4(List<int> o) {
    if (o[0] == 127) return true; // loopback
    if (o[0] == 10) return true; // RFC 1918 (includes the emulator host 10.0.2.2)
    if (o[0] == 172 && o[1] >= 16 && o[1] <= 31) return true; // RFC 1918
    if (o[0] == 192 && o[1] == 168) return true; // RFC 1918
    if (o[0] == 169 && o[1] == 254) return true; // link-local
    return false;
  }

  static bool _isPrivateIPv6(String host) {
    // `Uri.host` strips the brackets; a zone id may follow a percent sign.
    final zoneIndex = host.indexOf('%');
    final address = zoneIndex == -1 ? host : host.substring(0, zoneIndex);
    if (!address.contains(':')) return false;
    if (address == '::1' || address == '0:0:0:0:0:0:0:1') return true;
    final firstGroup = address.split(':').first;
    if (firstGroup.isEmpty) return false;
    final value = int.tryParse(firstGroup, radix: 16);
    if (value == null) return false;
    if ((value & 0xffc0) == 0xfe80) return true; // link-local fe80::/10
    if ((value & 0xfe00) == 0xfc00) return true; // unique local fc00::/7
    return false;
  }
}
