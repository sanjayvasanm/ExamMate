import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:exam_mate/main.dart';
import 'package:exam_mate/services/api_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('ExamMateApp can be instantiated', () {
    expect(const ExamMateApp(), isA<Widget>());
  });

  group('Authentication Persistence Flow', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('restoreSession returns false when no saved token exists', () async {
      final api = ApiService();
      final restored = await api.restoreSession();
      expect(restored, isFalse);
      expect(api.token, isNull);
      expect(api.currentUser, isNull);
    });

    test('restoreSession restores token and user when preferences exist', () async {
      SharedPreferences.setMockInitialValues({
        'em_auth_token': 'mock_valid_jwt_token_2026',
        'em_current_user': json.encode({
          'id': 'user_123',
          'name': 'Test Student',
          'email': 'student@university.edu',
        }),
      });

      final api = ApiService();
      final restored = await api.restoreSession();
      expect(restored, isTrue);
      expect(api.token, equals('mock_valid_jwt_token_2026'));
      expect(api.currentUser?['name'], equals('Test Student'));
    });

    test('logout purges token, user and preferences', () async {
      SharedPreferences.setMockInitialValues({
        'em_auth_token': 'mock_token',
        'em_current_user': json.encode({'name': 'Test Student'}),
      });

      final api = ApiService();
      await api.restoreSession();
      expect(api.token, isNotNull);

      await api.logout();
      expect(api.token, isNull);
      expect(api.currentUser, isNull);

      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('em_auth_token'), isNull);
      expect(prefs.getString('em_current_user'), isNull);
    });
  });
}
