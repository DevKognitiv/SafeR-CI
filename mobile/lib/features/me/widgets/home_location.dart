import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';

/// A WGS84 coordinate pair for a home position.
typedef HomeGeoPoint = ({double lat, double lon});

/// Wrapper over geolocator used by "Utiliser ma position" when creating a home.
///
/// Never throws: when location services are off, the permission is denied or
/// the fix times out, [currentPosition] resolves to `null`.
class HomeLocationService {
  const HomeLocationService({this.timeout = const Duration(seconds: 8)});

  final Duration timeout;

  Future<HomeGeoPoint?> currentPosition() async {
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

/// Location service returning a fixed point (tests). `null` mimics a denied permission.
class FixedHomeLocationService extends HomeLocationService {
  const FixedHomeLocationService(this.point);

  final HomeGeoPoint? point;

  @override
  Future<HomeGeoPoint?> currentPosition() async => point;
}

/// Overridable in tests to avoid touching the platform location plugin.
final homeLocationServiceProvider = Provider<HomeLocationService>((_) => const HomeLocationService());
