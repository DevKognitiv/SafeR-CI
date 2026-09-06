import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:media_kit/media_kit.dart';
import 'package:media_kit_video/media_kit_video.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/providers/providers.dart';
import '../../../core/widgets/widgets.dart';
import 'device_providers.dart';

/// What the camera surface has to render.
class CameraSurfaceRequest {
  const CameraSurfaceRequest({required this.snapshotUrl, required this.headers, this.info, this.loading = false});

  /// Stream descriptor; null while it is being fetched (or failed).
  final StreamInfo? info;
  final String snapshotUrl;
  final Map<String, String> headers;
  final bool loading;
}

typedef CameraSurfaceBuilder = Widget Function(BuildContext context, CameraSurfaceRequest request);

/// Builds the live video surface. The default uses media_kit; widget tests override it
/// with a placeholder so the native player is never initialised.
final cameraSurfaceBuilderProvider = Provider<CameraSurfaceBuilder>((_) => (context, request) => MediaKitCameraSurface(request: request));

/// 16:9 player area: fetches the stream descriptor for [quality] and delegates rendering
/// to [cameraSurfaceBuilderProvider]; shows an error overlay with retry when the hub
/// cannot provide a stream.
class StreamPlayer extends ConsumerWidget {
  const StreamPlayer({super.key, required this.device, required this.quality});

  final Device device;
  final String quality;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final client = ref.watch(hubClientProvider);
    final token = ref.watch(tokenProvider);
    final headers = <String, String>{if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token'};
    final snapshotUrl = client.snapshotUrl(device.id);
    final builder = ref.watch(cameraSurfaceBuilderProvider);
    final key = (deviceId: device.id, quality: quality);
    final stream = ref.watch(cameraStreamProvider(key));
    return AspectRatio(
      aspectRatio: 16 / 9,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: ColoredBox(
          color: Colors.black,
          child: stream.when(
            loading: () => builder(context, CameraSurfaceRequest(snapshotUrl: snapshotUrl, headers: headers, loading: true)),
            error: (error, _) => Stack(
              fit: StackFit.expand,
              children: [
                builder(context, CameraSurfaceRequest(snapshotUrl: snapshotUrl, headers: headers)),
                _StreamErrorOverlay(error: error, onRetry: () => ref.invalidate(cameraStreamProvider(key))),
              ],
            ),
            data: (info) => builder(context, CameraSurfaceRequest(snapshotUrl: snapshotUrl, headers: headers, info: info)),
          ),
        ),
      ),
    );
  }
}

class _StreamErrorOverlay extends StatelessWidget {
  const _StreamErrorOverlay({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final message = error.toString().replaceFirst(RegExp(r'^ApiException\([^)]*\): '), '');
    return ColoredBox(
      color: Colors.black54,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.videocam_off_outlined, color: Colors.white70, size: 36),
            const SizedBox(height: 8),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Text(message,
                  style: const TextStyle(color: Colors.white70, fontSize: 12), textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis),
            ),
            const SizedBox(height: 8),
            TextButton.icon(
              onPressed: onRetry,
              style: TextButton.styleFrom(foregroundColor: Colors.white),
              icon: const Icon(Icons.refresh, size: 18),
              label: Text(context.tr(fr: 'Réessayer', en: 'Retry')),
            ),
          ],
        ),
      ),
    );
  }
}

/// Poster / fallback image fetched from the hub snapshot endpoint (bearer header).
/// With [refreshInterval] the image is re-fetched periodically (MJPEG-like fallback).
class SnapshotImage extends StatefulWidget {
  const SnapshotImage({super.key, required this.url, required this.headers, this.refreshInterval, this.fit = BoxFit.contain});

  final String url;
  final Map<String, String> headers;
  final Duration? refreshInterval;
  final BoxFit fit;

  @override
  State<SnapshotImage> createState() => _SnapshotImageState();
}

class _SnapshotImageState extends State<SnapshotImage> {
  Timer? _timer;
  int _tick = 0;

  @override
  void initState() {
    super.initState();
    _schedule();
  }

  @override
  void didUpdateWidget(SnapshotImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.refreshInterval != widget.refreshInterval) _schedule();
  }

  void _schedule() {
    _timer?.cancel();
    final interval = widget.refreshInterval;
    if (interval != null) _timer = Timer.periodic(interval, (_) => setState(() => _tick++));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final separator = widget.url.contains('?') ? '&' : '?';
    final url = _tick == 0 ? widget.url : '${widget.url}${separator}t=$_tick';
    return Image.network(
      url,
      headers: widget.headers,
      fit: widget.fit,
      gaplessPlayback: true,
      errorBuilder: (_, __, ___) => const Center(child: Icon(Icons.videocam_off_outlined, color: Colors.white38, size: 40)),
    );
  }
}

/// Default surface: snapshot poster underneath, media_kit video on top for RTSP/HLS/HTTP streams.
class MediaKitCameraSurface extends StatelessWidget {
  const MediaKitCameraSurface({super.key, required this.request});

  final CameraSurfaceRequest request;

  @override
  Widget build(BuildContext context) {
    final info = request.info;
    final mjpeg = info != null && (info.type == 'mjpeg' || info.url.toLowerCase().contains('.mjp'));
    final playable = info != null && !mjpeg && info.type != 'webrtc';
    return Stack(
      fit: StackFit.expand,
      children: [
        SnapshotImage(url: request.snapshotUrl, headers: request.headers, refreshInterval: mjpeg ? const Duration(seconds: 2) : null),
        if (playable) _MediaKitVideo(info: info),
        if (request.loading) const Center(child: CircularProgressIndicator(color: Colors.white70)),
        if (info != null && info.type == 'webrtc')
          Positioned(
            left: 12,
            bottom: 12,
            child: StateChip(label: context.tr(fr: 'WebRTC non pris en charge', en: 'WebRTC not supported'), color: Colors.white),
          ),
      ],
    );
  }
}

class _MediaKitVideo extends StatefulWidget {
  const _MediaKitVideo({required this.info});

  final StreamInfo info;

  @override
  State<_MediaKitVideo> createState() => _MediaKitVideoState();
}

class _MediaKitVideoState extends State<_MediaKitVideo> {
  Player? _player;
  VideoController? _controller;
  Object? _error;

  @override
  void initState() {
    super.initState();
    try {
      final player = Player();
      _player = player;
      _controller = VideoController(player);
      _open();
    } catch (e) {
      _error = e;
    }
  }

  @override
  void didUpdateWidget(_MediaKitVideo oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.info.authenticatedUrl != widget.info.authenticatedUrl) _open();
  }

  void _open() {
    final player = _player;
    if (player == null) return;
    final headers = widget.info.headers;
    unawaited(player.open(Media(widget.info.authenticatedUrl, httpHeaders: headers.isEmpty ? null : headers)).catchError((Object e) {
      if (mounted) setState(() => _error = e);
    }));
  }

  @override
  void dispose() {
    unawaited(_player?.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    if (_error != null || controller == null) {
      return Align(
        alignment: Alignment.bottomLeft,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: StateChip(
              label: context.tr(fr: 'Lecture vidéo indisponible', en: 'Video playback unavailable'), color: Colors.white, icon: Icons.videocam_off_outlined),
        ),
      );
    }
    return Video(controller: controller, controls: NoVideoControls, fit: BoxFit.contain, fill: Colors.transparent);
  }
}
