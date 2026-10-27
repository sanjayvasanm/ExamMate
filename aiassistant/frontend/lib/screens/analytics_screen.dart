import 'package:flutter/material.dart';
import '../services/api_service.dart';

class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen> {
  final ApiService _api = ApiService();
  bool _isLoading = true;
  Map<String, dynamic>? _analytics;

  @override
  void initState() {
    super.initState();
    _loadAnalytics();
  }

  Future<void> _loadAnalytics() async {
    setState(() => _isLoading = true);
    try {
      final data = await _api.getAnalytics();
      if (mounted) setState(() { _analytics = data; _isLoading = false; });
    } catch (_) {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D0C22),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0C22),
        elevation: 0,
        title: const Text('Study Analytics', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh, color: Color(0xFF10B981)), onPressed: _loadAnalytics),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFF008A3F)))
          : SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Streak Card
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(colors: [Color(0xFF008A3F), Color(0xFF064E3B)]),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('ACADEMIC STREAK', style: TextStyle(color: Colors.white70, fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 1.2)),
                            const SizedBox(height: 6),
                            Text('${_analytics?['study_streak'] ?? 1} Days Active', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Colors.white)),
                            const SizedBox(height: 4),
                            const Text('Consistency drives exam excellence.', style: TextStyle(color: Colors.white70, fontSize: 12)),
                          ],
                        ),
                        const Text('🔥', style: TextStyle(fontSize: 44)),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),

                  // Metrics Grid
                  const Text('Learning Metrics', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white)),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      _buildMetricCard('Focus Time', '${_analytics?['total_focus_hours'] ?? 0} hrs', Icons.timer, const Color(0xFF10B981)),
                      const SizedBox(width: 12),
                      _buildMetricCard('Documents', '${_analytics?['total_documents'] ?? 0}', Icons.folder, const Color(0xFF38BDF8)),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      _buildMetricCard('Quiz Average', '${_analytics?['average_quiz_score'] ?? 0}%', Icons.analytics, const Color(0xFFA855F7)),
                      const SizedBox(width: 12),
                      _buildMetricCard('Flashcards', '${_analytics?['total_flashcards'] ?? 0}', Icons.style, const Color(0xFFF59E0B)),
                    ],
                  ),
                  const SizedBox(height: 24),

                  // Tasks and Retention breakdown
                  const Text('Task & Memory Retention', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white)),
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: const Color(0xFF16152B),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: Colors.white.withOpacity(0.06)),
                    ),
                    child: Column(
                      children: [
                        _buildProgressRow(
                          'Tasks Completed',
                          '${_analytics?['completed_tasks'] ?? 0}/${_analytics?['total_tasks'] ?? 0}',
                          (_analytics?['total_tasks'] ?? 0) > 0 ? (_analytics?['completed_tasks'] / _analytics?['total_tasks']) : 0.0,
                          const Color(0xFF10B981),
                        ),
                        const Divider(color: Colors.white10, height: 24),
                        _buildProgressRow(
                          'Mastered Flashcards (Rep 3+)',
                          '${_analytics?['mastered_flashcards'] ?? 0}/${_analytics?['total_flashcards'] ?? 0}',
                          (_analytics?['total_flashcards'] ?? 0) > 0 ? (_analytics?['mastered_flashcards'] / _analytics?['total_flashcards']) : 0.0,
                          const Color(0xFF38BDF8),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
    );
  }

  Widget _buildMetricCard(String title, String val, IconData icon, Color color) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF16152B),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.white.withOpacity(0.06)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: color.withOpacity(0.15), borderRadius: BorderRadius.circular(10)),
              child: Icon(icon, color: color, size: 20),
            ),
            const SizedBox(height: 12),
            Text(val, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white)),
            const SizedBox(height: 4),
            Text(title, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
          ],
        ),
      ),
    );
  }

  Widget _buildProgressRow(String label, String countStr, double progress, Color color) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 13)),
            Text(countStr, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 13)),
          ],
        ),
        const SizedBox(height: 8),
        LinearProgressIndicator(
          value: progress.clamp(0.0, 1.0),
          backgroundColor: const Color(0xFF0D0C22),
          color: color,
          minHeight: 6,
          borderRadius: BorderRadius.circular(3),
        ),
      ],
    );
  }
}
