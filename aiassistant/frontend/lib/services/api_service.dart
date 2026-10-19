import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:file_picker/file_picker.dart';

class ApiService {
  static const String baseUrl = String.fromEnvironment(
    'EXAM_MATE_API_URL',
    defaultValue: 'https://exam-mate-backend-w5t6.onrender.com/api',
  );

  String? _authToken;

  ApiService({String? authToken}) : _authToken = authToken;

  void setAuthToken(String? token) {
    _authToken = token;
  }

  Map<String, String> _headers({bool json = false}) {
    return {
      if (json) 'Content-Type': 'application/json',
      if (_authToken != null && _authToken!.isNotEmpty)
        'Authorization': 'Bearer $_authToken',
    };
  }

  Exception _requestError(http.Response response, String fallback) {
    try {
      final body = json.decode(response.body);
      if (body is Map<String, dynamic> && body['message'] is String) {
        return Exception(body['message']);
      }
    } on FormatException {
      // Use the endpoint-specific fallback for non-JSON error responses.
    }
    return Exception('$fallback (${response.statusCode})');
  }

  Future<Map<String, dynamic>> uploadDocument(PlatformFile file) async {
    var request = http.MultipartRequest('POST', Uri.parse('$baseUrl/upload'));
    request.headers.addAll(_headers());

    if (file.bytes != null) {
      request.files.add(http.MultipartFile.fromBytes('file', file.bytes!,
          filename: file.name));
    } else if (file.path != null) {
      request.files.add(await http.MultipartFile.fromPath('file', file.path!));
    }

    var response = await request.send();
    var responseData = await response.stream.bytesToString();

    if (response.statusCode == 200) {
      return json.decode(responseData);
    } else {
      try {
        final body = json.decode(responseData);
        if (body is Map<String, dynamic> && body['message'] is String) {
          throw Exception(body['message']);
        }
      } on FormatException {
        // Use the endpoint-specific fallback for non-JSON error responses.
      }
      throw Exception('Failed to upload file (${response.statusCode})');
    }
  }

  Future<Map<String, dynamic>> askQuestion(
      String question, String docId, String mode) async {
    final response = await http.post(
      Uri.parse('$baseUrl/ask'),
      headers: _headers(json: true),
      body: json.encode({
        'question': question,
        'document_id': docId,
        'mode': mode,
      }),
    );

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw _requestError(response, 'Failed to get answer');
    }
  }
}
