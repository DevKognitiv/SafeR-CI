import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_exception.dart';
import '../models/user.dart';
import 'app_providers.dart';

enum AuthStatus { unknown, authenticated, unauthenticated }

class AuthState {
  const AuthState({this.status = AuthStatus.unknown, this.user, this.token, this.error});

  final AuthStatus status;
  final User? user;
  final String? token;
  final String? error;

  bool get isAuthenticated => status == AuthStatus.authenticated;

  AuthState copyWith({AuthStatus? status, User? user, String? token, String? error, bool clearError = false}) => AuthState(
        status: status ?? this.status,
        user: user ?? this.user,
        token: token ?? this.token,
        error: clearError ? null : (error ?? this.error),
      );
}

class AuthNotifier extends Notifier<AuthState> {
  @override
  AuthState build() {
    final token = ref.read(tokenProvider);
    return AuthState(status: token == null ? AuthStatus.unauthenticated : AuthStatus.unknown, token: token);
  }

  /// Validate the stored token against the hub (called once at startup).
  Future<void> restore() async {
    final token = ref.read(tokenProvider);
    if (token == null) {
      state = const AuthState(status: AuthStatus.unauthenticated);
      return;
    }
    try {
      final user = await ref.read(hubClientProvider).me();
      state = AuthState(status: AuthStatus.authenticated, user: user, token: token);
    } on ApiException catch (e) {
      if (e.isUnauthorized) {
        await ref.read(tokenProvider.notifier).set(null);
        state = const AuthState(status: AuthStatus.unauthenticated);
      } else {
        // Offline: keep the session, the UI shows a banner.
        state = AuthState(status: AuthStatus.authenticated, token: token, user: state.user, error: e.message);
      }
    }
  }

  Future<bool> login(String email, String password) async {
    try {
      final result = await ref.read(hubClientProvider).login(email: email, password: password);
      await _apply(result);
      return true;
    } on ApiException catch (e) {
      state = state.copyWith(status: AuthStatus.unauthenticated, error: e.message);
      return false;
    }
  }

  Future<bool> register({required String email, required String password, required String name, String? phone, String locale = 'fr'}) async {
    try {
      final result = await ref.read(hubClientProvider).register(email: email, password: password, name: name, phone: phone, locale: locale);
      await _apply(result);
      return true;
    } on ApiException catch (e) {
      state = state.copyWith(status: AuthStatus.unauthenticated, error: e.message);
      return false;
    }
  }

  Future<void> _apply(AuthResult result) async {
    await ref.read(tokenProvider.notifier).set(result.token);
    state = AuthState(status: AuthStatus.authenticated, user: result.user, token: result.token);
  }

  Future<void> updateProfile({String? name, String? phone, String? locale, String? avatarUrl}) async {
    final user = await ref.read(hubClientProvider).updateMe(name: name, phone: phone, locale: locale, avatarUrl: avatarUrl);
    state = state.copyWith(user: user, clearError: true);
  }

  Future<void> logout() async {
    await ref.read(tokenProvider.notifier).set(null);
    await ref.read(storageProvider).clearSession();
    state = const AuthState(status: AuthStatus.unauthenticated);
  }

  void clearError() => state = state.copyWith(clearError: true);
}

final authProvider = NotifierProvider<AuthNotifier, AuthState>(AuthNotifier.new);
