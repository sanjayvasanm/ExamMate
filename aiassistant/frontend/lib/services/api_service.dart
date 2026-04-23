import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:file_picker/file_picker.dart';

class ApiService {
  static const String baseUrl = 'http://10.174.238.113:5000/api';

  Future<Map<String, dynamic>> uploadDocument(PlatformFile file) async {
    var request = http.MultipartRequest('POST', Uri.parse('$baseUrl/upload'));

    // Depending on platform (web vs desktop/mobile)
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
      throw Exception('Failed to upload file');
    }
  }

  Future<Map<String, dynamic>> askQuestion(
      String question, String docId, String mode) async {
    final response = await http.post(
      Uri.parse('$baseUrl/ask'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({
        'question': question,
        'document_id': docId,
        'mode': mode,
      }),
    );

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('Failed to get answer');
    }
  }
}
