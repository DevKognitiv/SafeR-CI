import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';

/// A WGS84 coordinate pair.
typedef GeoPoint = ({double lat, double lon});

/// Thin wrapper over geolocator so the SOS flow can be tested with a fixed position.
///
/// Never throws: when location services are off, the permission is denied or the
/// fix times out, [currentPosition] resolves to `null` and the alert is sent
/// without coordinates.
class LocationService {
  const LocationService({this.timeout = const Duration(seconds: 8)});

  final Duration timeout;

  Future<GeoPoint?> currentPosition() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) return null;
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) return null;
      final position = await Geolocator.getCurrentPosition(
        locationSettings: LocationSettings(accuracy: LocationAccuracy.high, timeLimit: timeout),
      );
      return (lat: position.latitude, lon: position.longitude);
    } catch (_) {
      return null;
    }
  }
}

/// Location service returning a fixed point (tests, previews). `null` mimics a denied permission.
class FixedLocationService extends LocationService {
  const FixedLocationService(this.point);

  final GeoPoint? point;

  @override
  Future<GeoPoint?> currentPosition() async => point;
}

/// Overridable in tests to avoid touching the platform location plugin.
final locationServiceProvider = Provider<LocationService>((_) => const LocationService());
