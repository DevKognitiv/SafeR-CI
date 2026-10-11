/// Error raised by the hub client with the HTTP status and hub error code.
class ApiException implements Exception {
  ApiException(this.message, {this.status, this.code, this.retryAfter});

  final String message;
  final int? status;
  final String? code;

  /// Seconds to wait before retrying (`429 rate_limited`, `423 account_locked`), when the hub says.
  final int? retryAfter;

  bool get isUnauthorized => status == 401;
  bool get isNetwork => status == null;

  @override
  String toString() => 'ApiException($status, $code): $message';
}
