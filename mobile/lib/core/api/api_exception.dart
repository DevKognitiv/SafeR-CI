/// Error raised by the hub client with the HTTP status and hub error code.
class ApiException implements Exception {
  ApiException(this.message, {this.status, this.code});

  final String message;
  final int? status;
  final String? code;

  bool get isUnauthorized => status == 401;
  bool get isNetwork => status == null;

  @override
  String toString() => 'ApiException($status, $code): $message';
}
