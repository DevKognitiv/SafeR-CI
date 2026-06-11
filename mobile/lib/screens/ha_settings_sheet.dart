import 'package:flutter/material.dart';

import '../services/ha_client.dart';
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
  bool _testing = false;
  String? _error;
  bool? _testResult;

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

  String? _validate() {
    final url = _urlCtrl.text.trim();
    final token = _tokenCtrl.text.trim();
    if (url.isEmpty || token.isEmpty) {
      return 'URL and token are required.';
    }
    final parsed = Uri.tryParse(url);
    if (parsed == null || !parsed.hasScheme || parsed.host.isEmpty) {
      return 'Invalid URL (use https://host:8123).';
    }
    return null;
  }

  Future<void> _testConnection() async {
    final invalid = _validate();
    if (invalid != null) {
      setState(() {
        _error = invalid;
        _testResult = null;
      });
      return;
    }
    setState(() {
      _testing = true;
      _error = null;
      _testResult = null;
    });
    final settings = HaConnectionSettings(
      baseUrl: _urlCtrl.text.trim(),
      token: _tokenCtrl.text.trim(),
    );
    final ok = await HaClient.testConnection(settings.restBase, settings.token);
    if (!mounted) return;
    setState(() {
      _testing = false;
      _testResult = ok;
    });
  }

  Future<void> _save() async {
    final invalid = _validate();
    if (invalid != null) {
      setState(() => _error = invalid);
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final settings = HaConnectionSettings(
      baseUrl: _urlCtrl.text.trim(),
      token: _tokenCtrl.text.trim(),
    );
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
              if (_testResult != null) ...[
                const SizedBox(height: 8),
                Row(
                  children: [
                    Icon(
                      _testResult! ? Icons.check_circle : Icons.error,
                      size: 18,
                      color: _testResult! ? Colors.green : Colors.red,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      _testResult!
                          ? 'Connected — token accepted.'
                          : 'Unreachable or token rejected.',
                      style: TextStyle(
                        color: _testResult! ? Colors.green : Colors.red,
                      ),
                    ),
                  ],
                ),
              ],
              const SizedBox(height: 16),
              Row(
                children: [
                  TextButton(
                    onPressed:
                        _saving ? null : () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                  const Spacer(),
                  OutlinedButton(
                    onPressed: _saving || _testing ? null : _testConnection,
                    child: _testing
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Test'),
                  ),
                  const SizedBox(width: 12),
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
