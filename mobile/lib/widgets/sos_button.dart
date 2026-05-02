import 'package:flutter/material.dart';

/// The main SOS panic button widget.
/// Large, accessible, impossible to accidentally miss.
class SOSButton extends StatelessWidget {
  final VoidCallback onPressed;
  final bool isLoading;
  final bool isActivated;

  const SOSButton({
    super.key,
    required this.onPressed,
    this.isLoading = false,
    this.isActivated = false,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: isLoading || isActivated ? null : onPressed,
      child: Container(
        width: 220,
        height: 220,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: isActivated
                ? [Colors.green.shade400, Colors.green.shade800]
                : [Colors.red.shade400, Colors.red.shade900],
          ),
          boxShadow: [
            BoxShadow(
              color: (isActivated ? Colors.green : Colors.red).withOpacity(0.6),
              blurRadius: 40,
              spreadRadius: 10,
            ),
          ],
        ),
        child: Center(
          child: isLoading
              ? const CircularProgressIndicator(
                  color: Colors.white, strokeWidth: 4)
              : Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      isActivated ? Icons.check_circle : Icons.warning_rounded,
                      color: Colors.white,
                      size: 64,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      isActivated ? 'ENVOYÉ' : 'SOS',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 32,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 4,
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}
