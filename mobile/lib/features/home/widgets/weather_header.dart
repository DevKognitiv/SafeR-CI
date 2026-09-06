import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/i18n.dart';
import '../../../core/models/device.dart';
import '../../../core/models/home.dart';
import '../../../core/providers/providers.dart';
import '../../../core/routes.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

/// Human label for a weather condition code sent by the hub.
String weatherConditionLabel(BuildContext context, String condition) {
  switch (condition) {
    case 'clear':
    case 'sunny':
      return context.tr(fr: 'Ensoleillé', en: 'Clear');
    case 'partly_cloudy':
      return context.tr(fr: 'Partiellement nuageux', en: 'Partly cloudy');
    case 'cloudy':
      return context.tr(fr: 'Nuageux', en: 'Cloudy');
    case 'overcast':
      return context.tr(fr: 'Couvert', en: 'Overcast');
    case 'fog':
    case 'foggy':
      return context.tr(fr: 'Brouillard', en: 'Fog');
    case 'drizzle':
      return context.tr(fr: 'Bruine', en: 'Drizzle');
    case 'rain':
    case 'rainy':
      return context.tr(fr: 'Pluie', en: 'Rain');
    case 'showers':
      return context.tr(fr: 'Averses', en: 'Showers');
    case 'snow':
      return context.tr(fr: 'Neige', en: 'Snow');
    case 'thunderstorm':
    case 'storm':
      return context.tr(fr: 'Orage', en: 'Thunderstorm');
    default:
      return context.tr(fr: 'Météo', en: 'Weather');
  }
}

String _formatTemperature(double value) => value == value.roundToDouble() ? '${value.round()}°C' : '${value.toStringAsFixed(1)}°C';

/// Status card at the top of the Home tab: weather (or device counts) + security mode chip.
class WeatherHeaderCard extends ConsumerWidget {
  const WeatherHeaderCard({super.key, required this.home, this.devices});

  final Home home;

  /// Loaded devices (null while loading) used as a fallback when weather is unavailable.
  final List<Device>? devices;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final weather = ref.watch(weatherProvider(home.id));
    final data = weather.value;
    final Widget summary = data != null && data.available ? _WeatherSummary(weather: data) : _DeviceCountSummary(devices: devices);
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Expanded(child: summary),
              const SizedBox(width: 12),
              SecurityModeChip(mode: home.securityMode),
            ],
          ),
        ),
      ),
    );
  }
}

class _WeatherSummary extends StatelessWidget {
  const _WeatherSummary({required this.weather});

  final Weather weather;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final temperature = weather.temperature;
    final humidity = weather.humidity;
    final details = [
      weatherConditionLabel(context, weather.condition),
      if (humidity != null) '${context.tr(fr: 'Humidité', en: 'Humidity')} ${humidity.round()}%',
    ].join(' · ');
    return Row(
      children: [
        _IconBox(icon: iconFromName(weather.icon, fallback: Icons.wb_sunny_outlined)),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                temperature == null ? '--' : _formatTemperature(temperature),
                style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 2),
              Text(details, maxLines: 2, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
            ],
          ),
        ),
      ],
    );
  }
}

class _DeviceCountSummary extends StatelessWidget {
  const _DeviceCountSummary({this.devices});

  final List<Device>? devices;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final list = devices;
    final total = list?.length;
    final online = list?.where((d) => d.online).length ?? 0;
    final offline = (total ?? 0) - online;
    final title = total == null
        ? context.tr(fr: 'Chargement…', en: 'Loading…')
        : context.tr(fr: total == 1 ? '1 appareil' : '$total appareils', en: total == 1 ? '1 device' : '$total devices');
    final subtitle = total == null
        ? context.tr(fr: 'Météo indisponible', en: 'Weather unavailable')
        : '${context.tr(fr: '$online en ligne', en: '$online online')} · ${context.tr(fr: '$offline hors ligne', en: '$offline offline')}';
    return Row(
      children: [
        const _IconBox(icon: Icons.devices_other),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 2),
              Text(subtitle, maxLines: 2, overflow: TextOverflow.ellipsis, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
            ],
          ),
        ),
      ],
    );
  }
}

class _IconBox extends StatelessWidget {
  const _IconBox({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) => Container(
        width: 52,
        height: 52,
        decoration: BoxDecoration(color: SafeRColors.primary.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(16)),
        child: Icon(icon, color: SafeRColors.primary, size: 28),
      );
}

/// Tinted chip showing the current security mode; opens the Security tab.
class SecurityModeChip extends StatelessWidget {
  const SecurityModeChip({super.key, required this.mode});

  final String mode;

  @override
  Widget build(BuildContext context) {
    final color = SafeRColors.forSecurityMode(mode);
    final label = securityModeLabel(context, mode);
    return Semantics(
      button: true,
      label: '${context.tr(fr: 'Mode de sécurité', en: 'Security mode')}: $label',
      child: InkWell(
        borderRadius: BorderRadius.circular(24),
        onTap: () => context.go(Routes.security),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(20)),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(mode == 'disarmed' ? Icons.shield_outlined : Icons.shield, size: 16, color: color),
                const SizedBox(width: 6),
                Text(label, style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w700)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
