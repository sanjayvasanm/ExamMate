import 'package:flutter/material.dart';
import '../services/api_service.dart';

class ProfileScreen extends StatefulWidget {
  final VoidCallback onLogout;
  const ProfileScreen({super.key, required this.onLogout});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final ApiService _api = ApiService();
  final TextEditingController _urlController = TextEditingController();
  Map<String, dynamic>? _healthInfo;
  bool _isCheckingHealth = false;

  @override
  void initState() {
    super.initState();
    _urlController.text = _api.baseUrl;
    _checkServer();
  }

  Future<void> _checkServer() async {
    setState(() => _isCheckingHealth = true);
    final h = await _api.checkHealth();
    if (mounted) setState(() { _healthInfo = h; _isCheckingHealth = false; });
  }

  void _saveUrl() {
    final newUrl = _urlController.text.trim();
    if (newUrl.isNotEmpty) {
      _api.baseUrl = newUrl;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('API URL updated: $newUrl'), backgroundColor: const Color(0xFF008A3F)),
      );
      _checkServer();
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = _api.currentUser;
    final isHealthy = _healthInfo?['status'] == 'healthy';

    return Scaffold(
      backgroundColor: const Color(0xFF0D0C22),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0C22),
        elevation: 0,
        title: const Text('Profile & Settings', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 16.0),
        child: Column(
          children: [
            // User Avatar Card
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF16152B),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: Colors.white.withOpacity(0.06)),
              ),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 32,
                    backgroundColor: const Color(0xFF008A3F).withOpacity(0.2),
                    child: Text(
                      (user?['name'] ?? 'S')[0].toUpperCase(),
                      style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold, color: Color(0xFF10B981)),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(user?['name'] ?? 'Student User', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white)),
                        const SizedBox(height: 4),
                        Text(user?['email'] ?? 'student@exam.ai', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                        const SizedBox(height: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(color: const Color(0xFF008A3F).withOpacity(0.15), borderRadius: BorderRadius.circular(6)),
                          child: const Text('Exam Mate AI Student', style: TextStyle(color: Color(0xFF10B981), fontSize: 11, fontWeight: FontWeight.bold)),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // Server Configuration Card
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF16152B),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: Colors.white.withOpacity(0.06)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Backend Connection URL', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 15)),
                  const SizedBox(height: 6),
                  const Text(
                    'Use "http://10.0.2.2:5000/api" for Android Emulator, or your Render backend URL for cloud.',
                    style: TextStyle(color: Color(0xFF94A3B8), fontSize: 12),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _urlController,
                    style: const TextStyle(color: Colors.white, fontSize: 13),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: const Color(0xFF0D0C22),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
                      suffixIcon: IconButton(
                        icon: const Icon(Icons.check, color: Color(0xFF10B981)),
                        onPressed: _saveUrl,
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          Icon(
                            isHealthy ? Icons.check_circle : Icons.error_outline,
                            color: isHealthy ? const Color(0xFF10B981) : Colors.redAccent,
                            size: 18,
                          ),
                          const SizedBox(width: 8),
                          Text(
                            isHealthy ? 'Connected & Verified' : 'Server Unreachable',
                            style: TextStyle(
                              color: isHealthy ? const Color(0xFF10B981) : Colors.redAccent,
                              fontSize: 13,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                      TextButton(
                        onPressed: _isCheckingHealth ? null : _checkServer,
                        child: Text(_isCheckingHealth ? 'Testing...' : 'Test Connection', style: const TextStyle(color: Color(0xFF38BDF8), fontSize: 12)),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // Sign Out Button
            SizedBox(
              width: double.infinity,
              height: 48,
              child: ElevatedButton.icon(
                onPressed: () {
                  _api.logout();
                  widget.onLogout();
                },
                icon: const Icon(Icons.logout, color: Colors.redAccent, size: 20),
                label: const Text('Sign Out', style: TextStyle(color: Colors.redAccent, fontWeight: FontWeight.bold)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.red.withOpacity(0.12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: BorderSide(color: Colors.red.withOpacity(0.3))),
                  elevation: 0,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
