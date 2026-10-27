import 'package:flutter/material.dart';
import '../services/api_service.dart';

class AiTutorScreen extends StatefulWidget {
  const AiTutorScreen({super.key});

  @override
  State<AiTutorScreen> createState() => _AiTutorScreenState();
}

class _AiTutorScreenState extends State<AiTutorScreen> {
  final ApiService _api = ApiService();
  final TextEditingController _questionController = TextEditingController();

  List<dynamic> _documents = [];
  String? _selectedDocId;
  int _selectedMarks = 5;
  String _selectedMode = 'detailed';

  bool _isLoadingDocs = true;
  bool _isGenerating = false;
  Map<String, dynamic>? _answerData;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _loadDocuments();
  }

  Future<void> _loadDocuments() async {
    try {
      final docs = await _api.getDocuments();
      if (mounted) {
        setState(() {
          _documents = docs;
          _isLoadingDocs = false;
          if (docs.isNotEmpty) {
            _selectedDocId = docs.first['id'];
          }
        });
      }
    } catch (e) {
      if (mounted) setState(() => _isLoadingDocs = false);
    }
  }

  Future<void> _askQuestion() async {
    final question = _questionController.text.trim();
    if (question.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter an exam question or topic.')),
      );
      return;
    }

    setState(() {
      _isGenerating = true;
      _errorMessage = null;
      _answerData = null;
    });

    try {
      final res = await _api.askAi(
        question: question,
        documentId: _selectedDocId,
        mode: _selectedMode,
        marks: _selectedMarks,
      );
      if (mounted) {
        setState(() {
          _answerData = res;
          _isGenerating = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = e.toString().replaceAll('Exception: ', '');
          _isGenerating = false;
        });
      }
    }
  }

  void _showCitationModal(Map<String, dynamic> citation) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF16152B),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.verified, color: Color(0xFF10B981), size: 22),
                const SizedBox(width: 8),
                Text('Source Citation: Page ${citation['page']}', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 18)),
              ],
            ),
            const SizedBox(height: 6),
            Text('Section: ${citation['section'] ?? "General"}', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFF0D0C22),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.white.withOpacity(0.08)),
              ),
              child: Text(
                citation['snippet'] ?? '',
                style: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 14, height: 1.5, fontStyle: FontStyle.italic),
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () => Navigator.pop(ctx),
                style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F)),
                child: const Text('Close Verification', style: TextStyle(color: Colors.white)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final structured = _answerData?['structured_answer'] as Map<String, dynamic>?;
    final citations = (_answerData?['citations'] as List?) ?? [];
    final isGrounded = _answerData?['is_grounded'] ?? true;
    final keywords = (_answerData?['keywords'] as List?) ?? [];

    return Scaffold(
      backgroundColor: const Color(0xFF0D0C22),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0C22),
        elevation: 0,
        title: const Text('AI Exam Tutor', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 12.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Target document selector
            if (!_isLoadingDocs && _documents.isNotEmpty) ...[
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF16152B),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.white.withOpacity(0.08)),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    value: _selectedDocId,
                    isExpanded: true,
                    dropdownColor: const Color(0xFF16152B),
                    icon: const Icon(Icons.arrow_drop_down, color: Color(0xFF10B981)),
                    items: _documents.map((d) {
                      return DropdownMenuItem<String>(
                        value: d['id'].toString(),
                        child: Text(
                          'Source: ${d['filename']}',
                          style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500),
                          overflow: TextOverflow.ellipsis,
                        ),
                      );
                    }).toList(),
                    onChanged: (val) => setState(() => _selectedDocId = val),
                  ),
                ),
              ),
              const SizedBox(height: 12),
            ],

            // Marks and Style selection
            Row(
              children: [
                // Marks selector
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF16152B),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      children: [
                        const Text('Marks: ', style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                        ...[2, 5, 10].map((m) {
                          final isSel = _selectedMarks == m;
                          return Padding(
                            padding: const EdgeInsets.only(left: 6.0),
                            child: GestureDetector(
                              onTap: () => setState(() => _selectedMarks = m),
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                decoration: BoxDecoration(
                                  color: isSel ? const Color(0xFF008A3F) : const Color(0xFF0D0C22),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text('$m', style: TextStyle(color: isSel ? Colors.white : const Color(0xFF94A3B8), fontSize: 12, fontWeight: FontWeight.bold)),
                              ),
                            ),
                          );
                        }),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                // Mode selector
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF16152B),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceAround,
                      children: ['detailed', 'concise'].map((mod) {
                        final isSel = _selectedMode == mod;
                        return GestureDetector(
                          onTap: () => setState(() => _selectedMode = mod),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(
                              color: isSel ? const Color(0xFF008A3F) : const Color(0xFF0D0C22),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(mod.capitalize(), style: TextStyle(color: isSel ? Colors.white : const Color(0xFF94A3B8), fontSize: 12, fontWeight: FontWeight.bold)),
                          ),
                        );
                      }).toList(),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),

            // Question composer
            TextField(
              controller: _questionController,
              maxLines: 3,
              style: const TextStyle(color: Colors.white),
              decoration: InputDecoration(
                hintText: 'Enter your exam question (e.g., Explain the phases of a compiler with diagram)...',
                hintStyle: const TextStyle(color: Color(0xFF94A3B8), fontSize: 13),
                filled: true,
                fillColor: const Color(0xFF16152B),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
              ),
            ),
            const SizedBox(height: 12),

            // Generate button
            SizedBox(
              width: double.infinity,
              height: 48,
              child: ElevatedButton.icon(
                onPressed: _isGenerating ? null : _askQuestion,
                icon: _isGenerating
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                    : const Icon(Icons.auto_awesome, color: Colors.white, size: 20),
                label: Text(_isGenerating ? 'Synthesizing Source Material...' : 'Generate Exam Answer', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
                style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
              ),
            ),
            const SizedBox(height: 20),

            // Error display
            if (_errorMessage != null)
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(color: Colors.red.withOpacity(0.15), borderRadius: BorderRadius.circular(12)),
                child: Row(
                  children: [
                    const Icon(Icons.error_outline, color: Colors.redAccent),
                    const SizedBox(width: 8),
                    Expanded(child: Text(_errorMessage!, style: const TextStyle(color: Colors.redAccent, fontSize: 13))),
                  ],
                ),
              ),

            // Answer Result Card
            if (_answerData != null) ...[
              if (!isGrounded)
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.amber.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: Colors.amber.withOpacity(0.3)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Row(
                        children: [
                          Icon(Icons.shield_outlined, color: Colors.amber),
                          SizedBox(width: 8),
                          Text('Insufficient Source Evidence', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.amber, fontSize: 15)),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        _answerData!['answer_text'] ?? '',
                        style: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 13, height: 1.4),
                      ),
                    ],
                  ),
                )
              else ...[
                // Grounded Exam Answer Header
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: const Color(0xFF16152B),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: Colors.white.withOpacity(0.08)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Row(
                            children: [
                              Icon(Icons.verified, color: Color(0xFF10B981), size: 20),
                              SizedBox(width: 6),
                              Text('Grounded Academic Answer', style: TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF10B981), fontSize: 14)),
                            ],
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(color: const Color(0xFF008A3F).withOpacity(0.15), borderRadius: BorderRadius.circular(8)),
                            child: Text('$_selectedMarks Marks', style: const TextStyle(color: Color(0xFF10B981), fontWeight: FontWeight.bold, fontSize: 12)),
                          ),
                        ],
                      ),
                      const Divider(color: Colors.white10, height: 24),

                      // Definition
                      if (structured?['definition'] != null) ...[
                        const Text('1. Core Concept / Definition', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 14)),
                        const SizedBox(height: 6),
                        Text(structured!['definition'], style: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 13, height: 1.4)),
                        const SizedBox(height: 16),
                      ],

                      // Explanation
                      if (structured?['explanation'] != null) ...[
                        const Text('2. Detailed Explanation', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 14)),
                        const SizedBox(height: 6),
                        Text(structured!['explanation'], style: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 13, height: 1.4)),
                        const SizedBox(height: 16),
                      ],

                      // Key Points
                      if (structured?['points'] != null && (structured!['points'] as List).isNotEmpty) ...[
                        const Text('3. Key Examination Points', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 14)),
                        const SizedBox(height: 6),
                        ...(structured!['points'] as List).map((pt) => Padding(
                          padding: const EdgeInsets.only(bottom: 6.0),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('• ', style: TextStyle(color: Color(0xFF10B981), fontWeight: FontWeight.bold)),
                              Expanded(child: Text(pt.toString(), style: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 13, height: 1.35))),
                            ],
                          ),
                        )),
                        const SizedBox(height: 16),
                      ],

                      // Examples
                      if (structured?['examples'] != null && (structured!['examples'] as List).isNotEmpty) ...[
                        const Text('4. Source Examples', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 14)),
                        const SizedBox(height: 6),
                        ...(structured!['examples'] as List).map((ex) => Padding(
                          padding: const EdgeInsets.only(bottom: 4.0),
                          child: Text('→ $ex', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12, fontStyle: FontStyle.italic)),
                        )),
                        const SizedBox(height: 16),
                      ],

                      // Conclusion
                      if (structured?['conclusion'] != null) ...[
                        const Text('5. Conclusion', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 14)),
                        const SizedBox(height: 6),
                        Text(structured!['conclusion'], style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12, height: 1.4)),
                      ],

                      // Verifiable Citations
                      if (citations.isNotEmpty) ...[
                        const Divider(color: Colors.white10, height: 28),
                        const Text('Source Page Citations (Tap to inspect source text):', style: TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF10B981), fontSize: 13)),
                        const SizedBox(height: 10),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: citations.map((c) => ActionChip(
                            avatar: const Icon(Icons.menu_book, size: 14, color: Color(0xFF10B981)),
                            backgroundColor: const Color(0xFF0D0C22),
                            label: Text('Page ${c['page']} (${c['section'] ?? "Section"})', style: const TextStyle(color: Colors.white, fontSize: 11)),
                            onPressed: () => _showCitationModal(Map<String, dynamic>.from(c)),
                          )).toList(),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ],
            const SizedBox(height: 30),
          ],
        ),
      ),
    );
  }
}

extension StringExtension on String {
  String capitalize() => "${this[0].toUpperCase()}${substring(1)}";
}
