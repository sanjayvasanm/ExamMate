import 'package:flutter/material.dart';
import '../services/api_service.dart';

class HomeScreen extends StatefulWidget {
  final Function(int) onNavigate;
  const HomeScreen({super.key, required this.onNavigate});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ApiService _api = ApiService();
  bool _isLoading = true;
  Map<String, dynamic>? _dashboardData;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadDashboard();
  }

  Future<void> _loadDashboard() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final data = await _api.getDashboard();
      if (mounted) {
        setState(() {
          _dashboardData = data;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString().replaceAll('Exception: ', '');
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator(color: Color(0xFF008A3F)));
    }

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.cloud_off, size: 48, color: Color(0xFF94A3B8)),
            const SizedBox(height: 12),
            Text('Could not load dashboard: $_error', style: const TextStyle(color: Color(0xFF94A3B8))),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loadDashboard,
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F)),
              child: const Text('Retry', style: TextStyle(color: Colors.white)),
            ),
          ],
        ),
      );
    }

    final userName = _dashboardData?['user_name'] ?? 'Student';
    final streak = _dashboardData?['study_streak'] ?? 1;
    final analytics = _dashboardData?['analytics'] ?? {};
    final recentDocs = (_dashboardData?['recent_documents'] as List?) ?? [];
    final upcomingExams = (_dashboardData?['upcoming_exams'] as List?) ?? [];
    final pendingTasks = (_dashboardData?['pending_tasks'] as List?) ?? [];

    return RefreshIndicator(
      onRefresh: _loadDashboard,
      color: const Color(0xFF008A3F),
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Greeting & Streak
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Hello, $userName 👋', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Colors.white)),
                    const Text('Ready to master your exam topics?', style: TextStyle(fontSize: 13, color: Color(0xFF94A3B8))),
                  ],
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: const Color(0xFF16152B),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: const Color(0xFF008A3F).withOpacity(0.4)),
                  ),
                  child: Row(
                    children: [
                      const Text('🔥', style: TextStyle(fontSize: 18)),
                      const SizedBox(width: 6),
                      Text('$streak Day Streak', style: const TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF10B981))),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),

            // Hero Priorities Card
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF008A3F), Color(0xFF064E3B)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(20),
                boxShadow: [
                  BoxShadow(color: const Color(0xFF008A3F).withOpacity(0.3), blurRadius: 15, offset: const Offset(0, 8)),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('TODAY\'S FOCUS', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.white70, letterSpacing: 1.2)),
                  const SizedBox(height: 6),
                  Text(
                    pendingTasks.isNotEmpty ? pendingTasks.first['title'] : 'All tasks cleared for today!',
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      ElevatedButton.icon(
                        onPressed: () => widget.onNavigate(2), // AI Tutor
                        icon: const Icon(Icons.bolt, size: 16, color: Color(0xFF064E3B)),
                        label: const Text('Start AI Tutor', style: TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF064E3B))),
                        style: ElevatedButton.styleFrom(backgroundColor: Colors.white, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10))),
                      ),
                      const SizedBox(width: 10),
                      OutlinedButton(
                        onPressed: () => widget.onNavigate(3), // Study Workspace
                        style: OutlinedButton.styleFrom(
                          side: const BorderSide(color: Colors.white70),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                        ),
                        child: const Text('Practice Quiz', style: TextStyle(color: Colors.white)),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // Quick Actions Row
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                _buildQuickAction('Ask AI', Icons.psychology, () => widget.onNavigate(2)),
                _buildQuickAction('Upload', Icons.upload_file, () => widget.onNavigate(1)),
                _buildQuickAction('Cards', Icons.style, () => widget.onNavigate(3)),
                _buildQuickAction('Planner', Icons.calendar_today, () => widget.onNavigate(4)),
              ],
            ),
            const SizedBox(height: 28),

            // Upcoming Exams section
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Upcoming Exams', style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: Colors.white)),
                TextButton(
                  onPressed: () => widget.onNavigate(4),
                  child: const Text('View All', style: TextStyle(color: Color(0xFF10B981))),
                ),
              ],
            ),
            if (upcomingExams.isEmpty)
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(color: const Color(0xFF16152B), borderRadius: BorderRadius.circular(12)),
                child: const Row(
                  children: [
                    Icon(Icons.info_outline, color: Color(0xFF94A3B8), size: 20),
                    SizedBox(width: 10),
                    Text('No exams scheduled. Add one in Planner!', style: TextStyle(color: Color(0xFF94A3B8))),
                  ],
                ),
              )
            else
              ...upcomingExams.map((exam) {
                final days = exam['days_left'] ?? 0;
                final isUrgent = days <= 7;
                return Container(
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                  decoration: BoxDecoration(
                    color: const Color(0xFF16152B),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: Colors.white.withOpacity(0.06)),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(exam['title'] ?? 'Exam', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 15)),
                          const SizedBox(height: 4),
                          Text('${exam['subject']} • Target: ${exam['target_score']}%', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                        ],
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: isUrgent ? Colors.red.withOpacity(0.2) : const Color(0xFF008A3F).withOpacity(0.2),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(
                          days <= 0 ? 'Today!' : '$days days left',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: isUrgent ? Colors.redAccent : const Color(0xFF10B981),
                            fontSize: 12,
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              }),

            const SizedBox(height: 24),

            // Recently Uploaded Materials
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Recent Study Materials', style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: Colors.white)),
                TextButton(
                  onPressed: () => widget.onNavigate(1),
                  child: const Text('Library', style: TextStyle(color: Color(0xFF10B981))),
                ),
              ],
            ),
            if (recentDocs.isEmpty)
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(color: const Color(0xFF16152B), borderRadius: BorderRadius.circular(12)),
                child: const Row(
                  children: [
                    Icon(Icons.folder_open, color: Color(0xFF94A3B8), size: 20),
                    SizedBox(width: 10),
                    Text('No documents uploaded yet.', style: TextStyle(color: Color(0xFF94A3B8))),
                  ],
                ),
              )
            else
              ...recentDocs.map((doc) {
                final score = doc['confidence_score'] ?? 0.0;
                return Container(
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: const Color(0xFF16152B),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: Colors.white.withOpacity(0.06)),
                  ),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: const Color(0xFF0D0C22),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Icon(
                          doc['file_type'] == 'PDF' ? Icons.picture_as_pdf : Icons.slideshow,
                          color: const Color(0xFF10B981),
                          size: 24,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(doc['filename'] ?? 'Document', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
                            const SizedBox(height: 3),
                            Text('${doc['page_count']} pages • ${doc['file_type']}', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: const Color(0xFF008A3F).withOpacity(0.15),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          '$score%',
                          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Color(0xFF10B981)),
                        ),
                      ),
                    ],
                  ),
                );
              }),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Widget _buildQuickAction(String label, IconData icon, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        children: [
          Container(
            width: 60,
            height: 60,
            decoration: BoxDecoration(
              color: const Color(0xFF16152B),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Colors.white.withOpacity(0.08)),
            ),
            child: Icon(icon, color: const Color(0xFF10B981), size: 26),
          ),
          const SizedBox(height: 8),
          Text(label, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}
