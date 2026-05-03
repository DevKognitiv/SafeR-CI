import 'package:flutter/material.dart';

import '../services/ha_connection_settings.dart';

/// Modal sheet for entering the HA base URL and a long-lived access token.
/// Returns the saved settings on confirm, or `null` if the user cancels.
class HaSettingsSheet extends StatefulWidget {
  final HaConnectionSettings initial;
  const HaSettingsSheet({super.key, required this.initial});

  @override
  State<HaSettingsSheet> createState() => _HaSettingsSheetState();
}

class _HaSettingsSheetState extends State<HaSettingsSheet> {
  late final TextEditingController _urlCtrl;
  late final TextEditingController _tokenCtrl;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _urlCtrl = TextEditingController(text: widget.initial.baseUrl);
    _tokenCtrl = TextEditingController(text: widget.initial.token);
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
    _tokenCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final url = _urlCtrl.text.trim();
    final token = _tokenCtrl.text.trim();
    if (url.isEmpty || token.isEmpty) {
      setState(() => _error = 'URL and token are required.');
      return;
    }
    final parsed = Uri.tryParse(url);
    if (parsed == null || !parsed.hasScheme || parsed.host.isEmpty) {
      setState(() => _error = 'Invalid URL (use https://host:8123).');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final settings = HaConnectionSettings(baseUrl: url, token: token);
    await settings.save();
    if (!mounted) return;
    Navigator.of(context).pop(settings);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('Home Assistant connection',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              const Text(
                'Enter your HA base URL and a long-lived access token '
                '(Profile → Security in HA).',
                style: TextStyle(color: Colors.black54),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _urlCtrl,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: 'Base URL',
                  hintText: 'https://homeassistant.local:8123',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _tokenCtrl,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'Long-lived access token',
                  border: OutlineInputBorder(),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 8),
                Text(_error!, style: const TextStyle(color: Colors.red)),
              ],
              const SizedBox(height: 16),
              Row(
                children: [
                  TextButton(
                    onPressed: _saving
                        ? null
                        : () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  const Spacer(),
                  FilledButton(
                    onPressed: _saving ? null : _save,
                    child: _saving
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Save & connect'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
