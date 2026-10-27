import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:file_picker/file_picker.dart';

class ApiService {
  // Singleton pattern
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;
  ApiService._internal();

  // Configurable base URL
  // Default to the host PC's Wi-Fi / LAN IP so real devices can connect immediately
  String baseUrl = 'http://10.47.19.103:5000/api';
  String? token;
  Map<String, dynamic>? currentUser;

  Map<String, String> get _headers {
    final headers = {'Content-Type': 'application/json'};
    if (token != null && token!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  // ── Authentication ──────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> login(String email, String password) async {
    final response = await http.post(
      Uri.parse('$baseUrl/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'email': email, 'password': password}),
    );
    final data = json.decode(response.body);
    if (response.statusCode == 200) {
      token = data['token'];
      currentUser = data['user'];
      return data;
    } else {
      throw Exception(data['error'] ?? 'Login failed');
    }
  }

  Future<Map<String, dynamic>> register(String name, String email, String password) async {
    final response = await http.post(
      Uri.parse('$baseUrl/auth/register'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'name': name, 'email': email, 'password': password}),
    );
    final data = json.decode(response.body);
    if (response.statusCode == 201) {
      token = data['token'];
      currentUser = data['user'];
      return data;
    } else {
      throw Exception(data['error'] ?? 'Registration failed');
    }
  }

  void logout() {
    token = null;
    currentUser = null;
  }

  // ── Dashboard & Profile ─────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getDashboard() async {
    final response = await http.get(Uri.parse('$baseUrl/dashboard'), headers: _headers);
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load dashboard: ${response.statusCode}');
  }

  Future<Map<String, dynamic>> getProfile() async {
    final response = await http.get(Uri.parse('$baseUrl/profile'), headers: _headers);
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load profile');
  }

  // ── Documents ───────────────────────────────────────────────────────────────

  Future<List<dynamic>> getDocuments() async {
    final response = await http.get(Uri.parse('$baseUrl/documents'), headers: _headers);
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return data['documents'] ?? [];
    }
    throw Exception('Failed to load documents');
  }

  Future<Map<String, dynamic>> getDocumentDetail(String docId) async {
    final response = await http.get(Uri.parse('$baseUrl/documents/$docId'), headers: _headers);
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load document details');
  }

  Future<Map<String, dynamic>> uploadDocument(PlatformFile file) async {
    var request = http.MultipartRequest('POST', Uri.parse('$baseUrl/upload'));
    if (token != null) {
      request.headers['Authorization'] = 'Bearer $token';
    }

    if (file.bytes != null) {
      request.files.add(http.MultipartFile.fromBytes('file', file.bytes!, filename: file.name));
    } else if (file.path != null) {
      request.files.add(await http.MultipartFile.fromPath('file', file.path!));
    } else {
      throw Exception('Selected file has no data');
    }

    var streamedResponse = await request.send();
    var responseData = await streamedResponse.stream.bytesToString();
    var data = json.decode(responseData);

    if (streamedResponse.statusCode == 201) {
      return data;
    } else {
      throw Exception(data['error'] ?? 'Upload and extraction failed');
    }
  }

  Future<void> deleteDocument(String docId) async {
    final response = await http.delete(Uri.parse('$baseUrl/documents/$docId'), headers: _headers);
    if (response.statusCode != 200) {
      throw Exception('Failed to delete document');
    }
  }

  // ── AI Tutor & Exam Answers ─────────────────────────────────────────────────

  Future<Map<String, dynamic>> askAi({
    required String question,
    String? documentId,
    String mode = 'detailed',
    int marks = 5,
  }) async {
    final body = {
      'question': question,
      'document_id': documentId,
      'mode': mode,
      'marks': marks,
    };
    final response = await http.post(
      Uri.parse('$baseUrl/ask'),
      headers: _headers,
      body: json.encode(body),
    );
    final data = json.decode(response.body);
    if (response.statusCode == 200) {
      return data;
    }
    throw Exception(data['error'] ?? 'AI request failed');
  }

  Future<List<dynamic>> getHistory() async {
    final response = await http.get(Uri.parse('$baseUrl/history'), headers: _headers);
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return data['history'] ?? [];
    }
    throw Exception('Failed to load history');
  }

  // ── Flashcards ──────────────────────────────────────────────────────────────

  Future<List<dynamic>> getDecks() async {
    final response = await http.get(Uri.parse('$baseUrl/flashcards/decks'), headers: _headers);
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return data['decks'] ?? [];
    }
    throw Exception('Failed to load decks');
  }

  Future<List<dynamic>> getDeckCards(String deckId) async {
    final response = await http.get(Uri.parse('$baseUrl/flashcards/decks/$deckId/cards'), headers: _headers);
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return data['cards'] ?? [];
    }
    throw Exception('Failed to load cards');
  }

  Future<Map<String, dynamic>> generateFlashcards({
    required String documentId,
    String? deckTitle,
    int count = 5,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/flashcards/generate'),
      headers: _headers,
      body: json.encode({
        'document_id': documentId,
        'deck_title': deckTitle,
        'count': count,
      }),
    );
    final data = json.decode(response.body);
    if (response.statusCode == 201) {
      return data;
    }
    throw Exception(data['error'] ?? 'Failed to generate flashcards');
  }

  Future<Map<String, dynamic>> reviewCard(String cardId, String rating) async {
    final response = await http.post(
      Uri.parse('$baseUrl/flashcards/review'),
      headers: _headers,
      body: json.encode({'card_id': cardId, 'rating': rating}),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to record card review');
  }

  Future<void> deleteDeck(String deckId) async {
    await http.delete(Uri.parse('$baseUrl/flashcards/decks/$deckId'), headers: _headers);
  }

  // ── Quizzes ─────────────────────────────────────────────────────────────────

  Future<List<dynamic>> getQuizzes() async {
    final response = await http.get(Uri.parse('$baseUrl/quizzes'), headers: _headers);
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return data['quizzes'] ?? [];
    }
    throw Exception('Failed to load quizzes');
  }

  Future<Map<String, dynamic>> getQuizDetail(String quizId) async {
    final response = await http.get(Uri.parse('$baseUrl/quizzes/$quizId'), headers: _headers);
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load quiz');
  }

  Future<Map<String, dynamic>> generateQuiz({
    required String documentId,
    String? title,
    int count = 5,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/quizzes/generate'),
      headers: _headers,
      body: json.encode({
        'document_id': documentId,
        'title': title,
        'count': count,
      }),
    );
    final data = json.decode(response.body);
    if (response.statusCode == 201) {
      return data;
    }
    throw Exception(data['error'] ?? 'Failed to generate quiz');
  }

  Future<Map<String, dynamic>> submitQuiz(String quizId, List<int> answers) async {
    final response = await http.post(
      Uri.parse('$baseUrl/quizzes/$quizId/submit'),
      headers: _headers,
      body: json.encode({'answers': answers}),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to submit quiz');
  }

  // ── Planner & Tasks ─────────────────────────────────────────────────────────

  Future<List<dynamic>> getExams() async {
    final response = await http.get(Uri.parse('$baseUrl/exams'), headers: _headers);
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return data['exams'] ?? [];
    }
    throw Exception('Failed to load exams');
  }

  Future<void> createExam({
    required String title,
    required String subject,
    required String examDate,
    int targetScore = 90,
    String syllabus = '',
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/exams'),
      headers: _headers,
      body: json.encode({
        'title': title,
        'subject': subject,
        'exam_date': examDate,
        'target_score': targetScore,
        'syllabus': syllabus,
      }),
    );
    if (response.statusCode != 201) {
      throw Exception('Failed to schedule exam');
    }
  }

  Future<void> deleteExam(String examId) async {
    await http.delete(Uri.parse('$baseUrl/exams/$examId'), headers: _headers);
  }

  Future<List<dynamic>> getTasks() async {
    final response = await http.get(Uri.parse('$baseUrl/tasks'), headers: _headers);
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return data['tasks'] ?? [];
    }
    throw Exception('Failed to load tasks');
  }

  Future<void> createTask({
    required String title,
    String? dueDate,
    String? examId,
    String priority = 'medium',
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/tasks'),
      headers: _headers,
      body: json.encode({
        'title': title,
        'due_date': dueDate,
        'exam_id': examId,
        'priority': priority,
      }),
    );
    if (response.statusCode != 201) {
      throw Exception('Failed to create task');
    }
  }

  Future<void> toggleTask(String taskId) async {
    final response = await http.post(Uri.parse('$baseUrl/tasks/$taskId/toggle'), headers: _headers);
    if (response.statusCode != 200) {
      throw Exception('Failed to toggle task');
    }
  }

  Future<void> deleteTask(String taskId) async {
    await http.delete(Uri.parse('$baseUrl/tasks/$taskId'), headers: _headers);
  }

  // ── Focus & Analytics ───────────────────────────────────────────────────────

  Future<void> logFocusSession({
    required int durationMinutes,
    String subject = 'General Study',
    String notes = '',
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/focus'),
      headers: _headers,
      body: json.encode({
        'duration_minutes': durationMinutes,
        'subject': subject,
        'notes': notes,
      }),
    );
    if (response.statusCode != 201) {
      throw Exception('Failed to log focus session');
    }
  }

  Future<Map<String, dynamic>> getAnalytics() async {
    final response = await http.get(Uri.parse('$baseUrl/analytics'), headers: _headers);
    if (response.statusCode == 200) {
      return json.decode(response.body);
    }
    throw Exception('Failed to load analytics');
  }

  Future<Map<String, dynamic>> checkHealth() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/health')).timeout(const Duration(seconds: 3));
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
      return {'status': 'unreachable', 'code': response.statusCode};
    } catch (e) {
      return {'status': 'error', 'detail': e.toString()};
    }
  }
}
