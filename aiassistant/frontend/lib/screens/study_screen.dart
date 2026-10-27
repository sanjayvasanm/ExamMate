import 'package:flutter/material.dart';
import '../services/api_service.dart';

class StudyScreen extends StatefulWidget {
  const StudyScreen({super.key});

  @override
  State<StudyScreen> createState() => _StudyScreenState();
}

class _StudyScreenState extends State<StudyScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final ApiService _api = ApiService();

  // Flashcards state
  List<dynamic> _decks = [];
  bool _isLoadingDecks = true;
  List<dynamic> _activeCards = [];
  int _activeCardIndex = 0;
  bool _isFlipped = false;
  String? _activeDeckTitle;

  // Quiz state
  List<dynamic> _quizzes = [];
  bool _isLoadingQuizzes = true;
  Map<String, dynamic>? _activeQuiz;
  int _activeQuestionIndex = 0;
  List<int> _selectedAnswers = [];
  Map<String, dynamic>? _quizResult;

  // Documents available for generation
  List<dynamic> _documents = [];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _loadAll();
  }

  Future<void> _loadAll() async {
    _loadDecks();
    _loadQuizzes();
    _loadDocuments();
  }

  Future<void> _loadDocuments() async {
    try {
      final docs = await _api.getDocuments();
      if (mounted) setState(() => _documents = docs);
    } catch (_) {}
  }

  Future<void> _loadDecks() async {
    setState(() => _isLoadingDecks = true);
    try {
      final decks = await _api.getDecks();
      if (mounted) setState(() { _decks = decks; _isLoadingDecks = false; });
    } catch (e) {
      if (mounted) setState(() => _isLoadingDecks = false);
    }
  }

  Future<void> _loadQuizzes() async {
    setState(() => _isLoadingQuizzes = true);
    try {
      final qs = await _api.getQuizzes();
      if (mounted) setState(() { _quizzes = qs; _isLoadingQuizzes = false; });
    } catch (e) {
      if (mounted) setState(() => _isLoadingQuizzes = false);
    }
  }

  // ── Flashcard Review Methods ───────────────────────────────────────────────

  Future<void> _startDeckReview(String deckId, String title) async {
    try {
      final cards = await _api.getDeckCards(deckId);
      if (cards.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('This deck has no cards.')),
        );
        return;
      }
      setState(() {
        _activeCards = cards;
        _activeCardIndex = 0;
        _isFlipped = false;
        _activeDeckTitle = title;
      });
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error loading cards: $e')));
    }
  }

  Future<void> _rateCard(String rating) async {
    if (_activeCardIndex >= _activeCards.length) return;
    final cardId = _activeCards[_activeCardIndex]['id'];
    try {
      await _api.reviewCard(cardId, rating);
    } catch (_) {}

    setState(() {
      _isFlipped = false;
      if (_activeCardIndex + 1 < _activeCards.length) {
        _activeCardIndex++;
      } else {
        // Finished deck
        _activeCards = [];
        _activeDeckTitle = null;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Deck review session complete! 🎉'), backgroundColor: Color(0xFF008A3F)),
        );
        _loadDecks();
      }
    });
  }

  void _showGenerateDeckDialog() {
    String? selectedDoc = _documents.isNotEmpty ? _documents.first['id'] : null;
    final titleController = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          backgroundColor: const Color(0xFF16152B),
          title: const Text('Generate Flashcards from Material', style: TextStyle(color: Colors.white, fontSize: 18)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_documents.isEmpty)
                const Text('No uploaded documents available. Please upload in Library first.', style: TextStyle(color: Color(0xFF94A3B8)))
              else ...[
                DropdownButtonFormField<String>(
                  value: selectedDoc,
                  dropdownColor: const Color(0xFF16152B),
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                  decoration: const InputDecoration(labelText: 'Source Material', labelStyle: TextStyle(color: Color(0xFF94A3B8))),
                  items: _documents.map<DropdownMenuItem<String>>((d) => DropdownMenuItem(value: d['id'].toString(), child: Text(d['filename'], overflow: TextOverflow.ellipsis))).toList(),
                  onChanged: (val) => setDialogState(() => selectedDoc = val),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: titleController,
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(labelText: 'Deck Title (Optional)', labelStyle: TextStyle(color: Color(0xFF94A3B8))),
                ),
              ],
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel', style: TextStyle(color: Color(0xFF94A3B8)))),
            if (_documents.isNotEmpty)
              ElevatedButton(
                onPressed: () async {
                  Navigator.pop(ctx);
                  if (selectedDoc == null) return;
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Extracting flashcards from document...')));
                  try {
                    await _api.generateFlashcards(documentId: selectedDoc!, deckTitle: titleController.text.trim());
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Flashcard deck generated!'), backgroundColor: Color(0xFF008A3F)));
                    _loadDecks();
                  } catch (e) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Generation failed: $e'), backgroundColor: Colors.red));
                  }
                },
                style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F)),
                child: const Text('Generate', style: TextStyle(color: Colors.white)),
              ),
          ],
        ),
      ),
    );
  }

  // ── Quiz Methods ───────────────────────────────────────────────────────────

  Future<void> _startQuiz(String quizId) async {
    try {
      final quiz = await _api.getQuizDetail(quizId);
      final questions = (quiz['questions'] as List?) ?? [];
      if (questions.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('This quiz has no questions.')));
        return;
      }
      setState(() {
        _activeQuiz = quiz;
        _activeQuestionIndex = 0;
        _selectedAnswers = List.filled(questions.length, -1);
        _quizResult = null;
      });
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error loading quiz: $e')));
    }
  }

  Future<void> _submitQuiz() async {
    if (_activeQuiz == null) return;
    try {
      final res = await _api.submitQuiz(_activeQuiz!['id'], _selectedAnswers);
      setState(() {
        _quizResult = res;
      });
      _loadQuizzes();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed to submit quiz: $e')));
    }
  }

  void _showGenerateQuizDialog() {
    String? selectedDoc = _documents.isNotEmpty ? _documents.first['id'] : null;
    final titleController = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          backgroundColor: const Color(0xFF16152B),
          title: const Text('Generate Practice Quiz', style: TextStyle(color: Colors.white, fontSize: 18)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_documents.isEmpty)
                const Text('No uploaded documents available. Upload in Library first.', style: TextStyle(color: Color(0xFF94A3B8)))
              else ...[
                DropdownButtonFormField<String>(
                  value: selectedDoc,
                  dropdownColor: const Color(0xFF16152B),
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                  decoration: const InputDecoration(labelText: 'Source Material', labelStyle: TextStyle(color: Color(0xFF94A3B8))),
                  items: _documents.map<DropdownMenuItem<String>>((d) => DropdownMenuItem(value: d['id'].toString(), child: Text(d['filename'], overflow: TextOverflow.ellipsis))).toList(),
                  onChanged: (val) => setDialogState(() => selectedDoc = val),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: titleController,
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(labelText: 'Quiz Title (Optional)', labelStyle: TextStyle(color: Color(0xFF94A3B8))),
                ),
              ],
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel', style: TextStyle(color: Color(0xFF94A3B8)))),
            if (_documents.isNotEmpty)
              ElevatedButton(
                onPressed: () async {
                  Navigator.pop(ctx);
                  if (selectedDoc == null) return;
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Generating questions from source material...')));
                  try {
                    await _api.generateQuiz(documentId: selectedDoc!, title: titleController.text.trim());
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Practice Quiz ready!'), backgroundColor: Color(0xFF008A3F)));
                    _loadQuizzes();
                  } catch (e) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Quiz generation failed: $e'), backgroundColor: Colors.red));
                  }
                },
                style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F)),
                child: const Text('Generate', style: TextStyle(color: Colors.white)),
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D0C22),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0C22),
        elevation: 0,
        title: const Text('Study Workspace', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: const Color(0xFF10B981),
          labelColor: const Color(0xFF10B981),
          unselectedLabelColor: const Color(0xFF94A3B8),
          tabs: const [
            Tab(icon: Icon(Icons.style), text: 'Flashcards (SM-2)'),
            Tab(icon: Icon(Icons.quiz), text: 'Practice Quizzes'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          // ── Tab 1: Flashcards ──────────────────────────────────────────────
          _activeCards.isNotEmpty ? _buildFlashcardReviewer() : _buildDecksList(),

          // ── Tab 2: Quizzes ─────────────────────────────────────────────────
          _activeQuiz != null ? _buildQuizRunner() : _buildQuizzesList(),
        ],
      ),
    );
  }

  // ── Flashcard Subviews ─────────────────────────────────────────────────────

  Widget _buildDecksList() {
    return Padding(
      padding: const EdgeInsets.all(20.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Revision Decks', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white)),
              ElevatedButton.icon(
                onPressed: _showGenerateDeckDialog,
                icon: const Icon(Icons.add, size: 18, color: Colors.white),
                label: const Text('New Deck', style: TextStyle(color: Colors.white)),
                style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10))),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Expanded(
            child: _isLoadingDecks
                ? const Center(child: CircularProgressIndicator(color: Color(0xFF008A3F)))
                : _decks.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.style_outlined, size: 48, color: Color(0xFF94A3B8)),
                            const SizedBox(height: 12),
                            const Text('No flashcard decks yet.', style: TextStyle(color: Color(0xFF94A3B8))),
                            const SizedBox(height: 8),
                            const Text('Tap "New Deck" to generate cards from your material.', style: TextStyle(color: Color(0xFF64748B), fontSize: 13)),
                          ],
                        ),
                      )
                    : ListView.builder(
                        itemCount: _decks.length,
                        itemBuilder: (ctx, idx) {
                          final deck = _decks[idx];
                          final total = deck['total_cards'] ?? 0;
                          final due = deck['due_cards'] ?? 0;

                          return Card(
                            margin: const EdgeInsets.only(bottom: 12),
                            color: const Color(0xFF16152B),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: Colors.white.withOpacity(0.06))),
                            child: ListTile(
                              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                              leading: Container(
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(color: const Color(0xFF008A3F).withOpacity(0.15), borderRadius: BorderRadius.circular(12)),
                                child: const Icon(Icons.style, color: Color(0xFF10B981)),
                              ),
                              title: Text(deck['title'] ?? 'Deck', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
                              subtitle: Text('$total Cards • $due Due for Review', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                              trailing: ElevatedButton(
                                onPressed: () => _startDeckReview(deck['id'], deck['title']),
                                style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))),
                                child: const Text('Study', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                              ),
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }

  Widget _buildFlashcardReviewer() {
    final card = _activeCards[_activeCardIndex];
    final total = _activeCards.length;
    final current = _activeCardIndex + 1;

    return Padding(
      padding: const EdgeInsets.all(20.0),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              IconButton(
                icon: const Icon(Icons.close, color: Colors.white),
                onPressed: () => setState(() => _activeCards = []),
              ),
              Text('Card $current of $total', style: const TextStyle(color: Color(0xFF94A3B8), fontWeight: FontWeight.bold)),
              if (card['source_page'] != null)
                Text('Ref: Page ${card['source_page']}', style: const TextStyle(color: Color(0xFF10B981), fontSize: 12)),
            ],
          ),
          const SizedBox(height: 12),
          LinearProgressIndicator(
            value: current / total,
            backgroundColor: const Color(0xFF16152B),
            color: const Color(0xFF10B981),
          ),
          const SizedBox(height: 24),

          // Flip card
          Expanded(
            child: GestureDetector(
              onTap: () => setState(() => _isFlipped = !_isFlipped),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                width: double.infinity,
                padding: const EdgeInsets.all(28),
                decoration: BoxDecoration(
                  color: _isFlipped ? const Color(0xFF1E1D3A) : const Color(0xFF16152B),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(color: _isFlipped ? const Color(0xFF10B981).withOpacity(0.5) : Colors.white.withOpacity(0.08)),
                  boxShadow: [
                    BoxShadow(color: Colors.black.withOpacity(0.4), blurRadius: 20, offset: const Offset(0, 8)),
                  ],
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      _isFlipped ? 'ANSWER' : 'QUESTION / PROMPT',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 1.5,
                        color: _isFlipped ? const Color(0xFF10B981) : const Color(0xFF94A3B8),
                      ),
                    ),
                    const SizedBox(height: 20),
                    Text(
                      _isFlipped ? (card['back'] ?? '') : (card['front'] ?? ''),
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: Colors.white, height: 1.4),
                    ),
                    const SizedBox(height: 24),
                    Text(
                      _isFlipped ? 'Tap to flip back' : 'Tap to reveal answer',
                      style: const TextStyle(fontSize: 12, color: Color(0xFF64748B)),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 24),

          // Spaced Repetition (SM-2) action buttons
          if (_isFlipped)
            Row(
              children: [
                _buildSm2Btn('Again', Colors.redAccent, () => _rateCard('Again')),
                const SizedBox(width: 8),
                _buildSm2Btn('Hard', Colors.amber, () => _rateCard('Hard')),
                const SizedBox(width: 8),
                _buildSm2Btn('Good', const Color(0xFF10B981), () => _rateCard('Good')),
                const SizedBox(width: 8),
                _buildSm2Btn('Easy', Colors.blueAccent, () => _rateCard('Easy')),
              ],
            )
          else
            SizedBox(
              width: double.infinity,
              height: 50,
              child: ElevatedButton(
                onPressed: () => setState(() => _isFlipped = true),
                style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
                child: const Text('Reveal Answer', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white)),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildSm2Btn(String label, Color color, VoidCallback onTap) {
    return Expanded(
      child: ElevatedButton(
        onPressed: onTap,
        style: ElevatedButton.styleFrom(
          backgroundColor: color.withOpacity(0.2),
          side: BorderSide(color: color.withOpacity(0.5)),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          padding: const EdgeInsets.symmetric(vertical: 12),
        ),
        child: Text(label, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 13)),
      ),
    );
  }

  // ── Quiz Subviews ──────────────────────────────────────────────────────────

  Widget _buildQuizzesList() {
    return Padding(
      padding: const EdgeInsets.all(20.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Practice Quizzes', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white)),
              ElevatedButton.icon(
                onPressed: _showGenerateQuizDialog,
                icon: const Icon(Icons.add, size: 18, color: Colors.white),
                label: const Text('New Quiz', style: TextStyle(color: Colors.white)),
                style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10))),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Expanded(
            child: _isLoadingQuizzes
                ? const Center(child: CircularProgressIndicator(color: Color(0xFF008A3F)))
                : _quizzes.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.quiz_outlined, size: 48, color: Color(0xFF94A3B8)),
                            const SizedBox(height: 12),
                            const Text('No quizzes created yet.', style: TextStyle(color: Color(0xFF94A3B8))),
                            const SizedBox(height: 8),
                            const Text('Tap "New Quiz" to generate MCQ practice questions.', style: TextStyle(color: Color(0xFF64748B), fontSize: 13)),
                          ],
                        ),
                      )
                    : ListView.builder(
                        itemCount: _quizzes.length,
                        itemBuilder: (ctx, idx) {
                          final q = _quizzes[idx];
                          final best = q['best_score'];

                          return Card(
                            margin: const EdgeInsets.only(bottom: 12),
                            color: const Color(0xFF16152B),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: Colors.white.withOpacity(0.06))),
                            child: ListTile(
                              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                              leading: Container(
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(color: const Color(0xFF008A3F).withOpacity(0.15), borderRadius: BorderRadius.circular(12)),
                                child: const Icon(Icons.quiz, color: Color(0xFF10B981)),
                              ),
                              title: Text(q['title'] ?? 'Quiz', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
                              subtitle: Text('${q['total_questions']} Questions • ${q['subject']}', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                              trailing: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  if (best != null)
                                    Container(
                                      margin: const EdgeInsets.only(right: 8),
                                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                      decoration: BoxDecoration(color: const Color(0xFF008A3F).withOpacity(0.2), borderRadius: BorderRadius.circular(8)),
                                      child: Text('$best%', style: const TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF10B981), fontSize: 12)),
                                    ),
                                  ElevatedButton(
                                    onPressed: () => _startQuiz(q['id']),
                                    style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))),
                                    child: const Text('Start', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }

  Widget _buildQuizRunner() {
    final questions = (_activeQuiz!['questions'] as List);
    final total = questions.length;

    // If quiz completed and scored
    if (_quizResult != null) {
      final score = _quizResult!['score'];
      final pct = _quizResult!['percentage'];
      final breakdown = (_quizResult!['breakdown'] as List?) ?? [];

      return Padding(
        padding: const EdgeInsets.all(20.0),
        child: ListView(
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Quiz Results', style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Colors.white)),
                IconButton(icon: const Icon(Icons.close, color: Colors.white), onPressed: () => setState(() => _activeQuiz = null)),
              ],
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                gradient: const LinearGradient(colors: [Color(0xFF008A3F), Color(0xFF064E3B)]),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Column(
                children: [
                  Text('$pct%', style: const TextStyle(fontSize: 44, fontWeight: FontWeight.bold, color: Colors.white)),
                  const SizedBox(height: 6),
                  Text('Score: $score out of $total correct', style: const TextStyle(fontSize: 16, color: Colors.white70)),
                ],
              ),
            ),
            const SizedBox(height: 24),
            const Text('Detailed Question Breakdown:', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 16)),
            const SizedBox(height: 12),
            ...breakdown.map((item) {
              final isCor = item['is_correct'] == true;
              return Container(
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: const Color(0xFF16152B),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: isCor ? const Color(0xFF10B981).withOpacity(0.4) : Colors.redAccent.withOpacity(0.4)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(isCor ? Icons.check_circle : Icons.cancel, color: isCor ? const Color(0xFF10B981) : Colors.redAccent, size: 18),
                        const SizedBox(width: 8),
                        Expanded(child: Text(item['question_text'] ?? '', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 13))),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(item['explanation'] ?? '', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                  ],
                ),
              );
            }),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () => setState(() => _activeQuiz = null),
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F), minimumSize: const Size(double.infinity, 48)),
              child: const Text('Back to Quizzes', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),
          ],
        ),
      );
    }

    // Active question step
    final q = questions[_activeQuestionIndex];
    final options = (q['options'] as List);
    final curAnswer = _selectedAnswers[_activeQuestionIndex];

    return Padding(
      padding: const EdgeInsets.all(20.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              IconButton(icon: const Icon(Icons.close, color: Colors.white), onPressed: () => setState(() => _activeQuiz = null)),
              Text('Question ${_activeQuestionIndex + 1} of $total', style: const TextStyle(color: Color(0xFF94A3B8), fontWeight: FontWeight.bold)),
              if (q['source_page'] != null) Text('Page ${q['source_page']}', style: const TextStyle(color: Color(0xFF10B981), fontSize: 12)),
            ],
          ),
          const SizedBox(height: 12),
          LinearProgressIndicator(value: (_activeQuestionIndex + 1) / total, color: const Color(0xFF10B981), backgroundColor: const Color(0xFF16152B)),
          const SizedBox(height: 24),
          Text(q['question_text'] ?? '', style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: Colors.white, height: 1.4)),
          const SizedBox(height: 24),
          Expanded(
            child: ListView.builder(
              itemCount: options.length,
              itemBuilder: (ctx, optIdx) {
                final isSelected = curAnswer == optIdx;
                return GestureDetector(
                  onTap: () => setState(() => _selectedAnswers[_activeQuestionIndex] = optIdx),
                  child: Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: isSelected ? const Color(0xFF008A3F).withOpacity(0.2) : const Color(0xFF16152B),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: isSelected ? const Color(0xFF10B981) : Colors.white.withOpacity(0.08)),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 28,
                          height: 28,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: isSelected ? const Color(0xFF008A3F) : const Color(0xFF0D0C22),
                          ),
                          child: Center(
                            child: Text(
                              String.fromCharCode(65 + optIdx),
                              style: TextStyle(fontWeight: FontWeight.bold, color: isSelected ? Colors.white : const Color(0xFF94A3B8)),
                            ),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(child: Text(options[optIdx].toString(), style: const TextStyle(color: Colors.white, fontSize: 14, height: 1.3))),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          Row(
            children: [
              if (_activeQuestionIndex > 0)
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => setState(() => _activeQuestionIndex--),
                    style: OutlinedButton.styleFrom(side: const BorderSide(color: Colors.white24), padding: const EdgeInsets.symmetric(vertical: 14)),
                    child: const Text('Previous', style: TextStyle(color: Colors.white)),
                  ),
                ),
              if (_activeQuestionIndex > 0) const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton(
                  onPressed: () {
                    if (_activeQuestionIndex + 1 < total) {
                      setState(() => _activeQuestionIndex++);
                    } else {
                      _submitQuiz();
                    }
                  },
                  style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F), padding: const EdgeInsets.symmetric(vertical: 14)),
                  child: Text(_activeQuestionIndex + 1 < total ? 'Next Question' : 'Submit Quiz', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
