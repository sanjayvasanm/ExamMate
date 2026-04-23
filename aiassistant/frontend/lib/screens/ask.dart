import 'package:flutter/material.dart';
import '../services/api_service.dart';

class AskScreen extends StatefulWidget {
  const AskScreen({Key? key}) : super(key: key);

  @override
  State<AskScreen> createState() => _AskScreenState();
}

class _AskScreenState extends State<AskScreen> {
  final TextEditingController _questionController = TextEditingController();
  final ApiService _apiService = ApiService();
  bool _isLoading = false;
  Map<String, dynamic>? _answerData;
  String _mode = 'detailed';

  Future<void> _askQuestion() async {
    if (_questionController.text.trim().isEmpty) return;

    setState(() {
      _isLoading = true;
    });

    try {
      var response = await _apiService.askQuestion(
        _questionController.text.trim(),
        'doc_mock_id', // Would be passed from context in real app
        _mode,
      );
      if (!mounted) return;
      setState(() {
        _answerData = response;
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    bool isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Ask AI Tutor'),
        centerTitle: true,
      ),
      body: Column(
        children: [
          // Chat output
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _answerData == null
                    ? const Center(
                        child: Text('Ask a question about your materials.',
                            style: TextStyle(color: Colors.grey)))
                    : _buildAnswerView(_answerData!, isDark),
          ),
          // Input Area
          Container(
            padding: const EdgeInsets.all(16.0),
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF1A1935) : Colors.white,
              border: Border(
                top: BorderSide(color: Colors.grey.withValues(alpha: 0.2)),
              ),
            ),
            child: Row(
              children: [
                DropdownButton<String>(
                  value: _mode,
                  items: const [
                    DropdownMenuItem(
                        value: 'beginner', child: Text('Beginner')),
                    DropdownMenuItem(value: 'exam', child: Text('Exam')),
                    DropdownMenuItem(
                        value: 'detailed', child: Text('Detailed')),
                  ],
                  onChanged: (val) {
                    if (val != null) setState(() => _mode = val);
                  },
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    controller: _questionController,
                    decoration: InputDecoration(
                      hintText: 'Ask your question...',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(24),
                        borderSide: BorderSide.none,
                      ),
                      filled: true,
                      fillColor: isDark
                          ? const Color(0xFF0D0C22)
                          : Colors.grey.shade100,
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 20, vertical: 14),
                    ),
                    onSubmitted: (_) => _askQuestion(),
                  ),
                ),
                const SizedBox(width: 8),
                FloatingActionButton(
                  onPressed: _askQuestion,
                  backgroundColor: Theme.of(context).colorScheme.primary,
                  mini: true,
                  elevation: 0,
                  child: const Icon(Icons.send, color: Colors.white),
                )
              ],
            ),
          )
        ],
      ),
    );
  }

  Widget _buildAnswerView(Map<String, dynamic> data, bool isDark) {
    final answer = data['answer'] ?? {};
    final keywords = List<String>.from(data['keywords'] ?? []);
    final diagrams = List<Map<String, dynamic>>.from(data['diagrams'] ?? []);

    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Text(
          answer['title'] ?? 'Answer',
          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 16),
        _buildSectionCard('Definition', answer['definition'], isDark, keywords),
        const SizedBox(height: 16),
        _buildSectionCard(
            'Explanation', answer['explanation'], isDark, keywords),
        const SizedBox(height: 16),
        if (diagrams.isNotEmpty)
          _buildDiagramCard(diagrams.first['code'], isDark),
        const SizedBox(height: 16),
        const Text('Key Points',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        ...(answer['points'] as List).map((point) => Padding(
              padding: const EdgeInsets.only(bottom: 8.0),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('• ',
                      style: TextStyle(fontSize: 18, color: Colors.green)),
                  Expanded(child: _highlightKeywords(point, keywords)),
                ],
              ),
            )),
        const SizedBox(height: 16),
        _buildSectionCard('Conclusion', answer['conclusion'], isDark, []),
      ],
    );
  }

  Widget _buildSectionCard(
      String title, String? content, bool isDark, List<String> keywords) {
    if (content == null || content.isEmpty) return const SizedBox();
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1A1935) : Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.05),
            blurRadius: 10,
            offset: const Offset(0, 4),
          )
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: const TextStyle(
                  fontSize: 14,
                  color: Colors.green,
                  fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          _highlightKeywords(content, keywords),
        ],
      ),
    );
  }

  Widget _highlightKeywords(String text, List<String> keywords) {
    // Basic text highlight mapping for demo purposes
    return Text(text, style: const TextStyle(fontSize: 16, height: 1.5));
  }

  Widget _buildDiagramCard(String mermaidCode, bool isDark) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF0D0C22) : Colors.grey.shade50,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.green.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.schema, color: Colors.green),
              SizedBox(width: 8),
              Text('Generated Diagram',
                  style: TextStyle(fontWeight: FontWeight.bold)),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            mermaidCode,
            style: const TextStyle(fontFamily: 'Courier', fontSize: 12),
          ),
          // In a real app, use flutter_inappwebview to render MermaidJS or a native mermaid renderer.
        ],
      ),
    );
  }
}
