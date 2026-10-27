import 'dart:async';
import 'package:flutter/material.dart';
import '../services/api_service.dart';

class FocusScreen extends StatefulWidget {
  const FocusScreen({super.key});

  @override
  State<FocusScreen> createState() => _FocusScreenState();
}

class _FocusScreenState extends State<FocusScreen> {
  final ApiService _api = ApiService();

  int _selectedMinutes = 25;
  int _secondsLeft = 25 * 60;
  bool _isRunning = false;
  Timer? _timer;
  final TextEditingController _subjectController = TextEditingController(text: 'General Study');

  @override
  void dispose() {
    _timer?.cancel();
    _subjectController.dispose();
    super.dispose();
  }

  void _startTimer() {
    _timer?.cancel();
    setState(() => _isRunning = true);

    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (_secondsLeft > 0) {
        setState(() => _secondsLeft--);
      } else {
        _timer?.cancel();
        setState(() => _isRunning = false);
        _completeSession();
      }
    });
  }

  void _pauseTimer() {
    _timer?.cancel();
    setState(() => _isRunning = false);
  }

  void _resetTimer() {
    _timer?.cancel();
    setState(() {
      _isRunning = false;
      _secondsLeft = _selectedMinutes * 60;
    });
  }

  void _selectMinutes(int mins) {
    if (_isRunning) return;
    setState(() {
      _selectedMinutes = mins;
      _secondsLeft = mins * 60;
    });
  }

  Future<void> _completeSession() async {
    try {
      await _api.logFocusSession(
        durationMinutes: _selectedMinutes,
        subject: _subjectController.text.trim(),
      );
      if (mounted) {
        showDialog(
          context: context,
          builder: (ctx) => AlertDialog(
            backgroundColor: const Color(0xFF16152B),
            title: const Text('Focus Session Completed! 🎯', style: TextStyle(color: Colors.white)),
            content: Text('Awesome effort! You logged $_selectedMinutes minutes of concentrated study.', style: const TextStyle(color: Color(0xFF94A3B8))),
            actions: [
              ElevatedButton(
                onPressed: () => Navigator.pop(ctx),
                style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F)),
                child: const Text('Continue', style: TextStyle(color: Colors.white)),
              ),
            ],
          ),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed to log session: $e')));
    }
  }

  String _formatTime() {
    final mins = _secondsLeft ~/ 60;
    final secs = _secondsLeft % 60;
    return '${mins.toString().padLeft(2, '0')}:${secs.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final progress = 1.0 - (_secondsLeft / (_selectedMinutes * 60));

    return Scaffold(
      backgroundColor: const Color(0xFF0D0C22),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0C22),
        elevation: 0,
        title: const Text('Focus & Pomodoro', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 20.0),
        child: Column(
          children: [
            // Mode Selectors
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _buildModeChip('25m Focus', 25),
                const SizedBox(width: 12),
                _buildModeChip('50m Deep', 50),
                const SizedBox(width: 12),
                _buildModeChip('10m Break', 10),
              ],
            ),
            const SizedBox(height: 36),

            // Circular Timer
            Stack(
              alignment: Alignment.center,
              children: [
                SizedBox(
                  width: 240,
                  height: 240,
                  child: CircularProgressIndicator(
                    value: progress,
                    strokeWidth: 10,
                    backgroundColor: const Color(0xFF16152B),
                    color: const Color(0xFF10B981),
                  ),
                ),
                Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(_formatTime(), style: const TextStyle(fontSize: 48, fontWeight: FontWeight.bold, color: Colors.white, letterSpacing: 2)),
                    const SizedBox(height: 6),
                    Text(_isRunning ? 'FOCUSING' : 'READY', style: const TextStyle(color: Color(0xFF94A3B8), letterSpacing: 1.5, fontSize: 13, fontWeight: FontWeight.bold)),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 36),

            // Subject field
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              decoration: BoxDecoration(color: const Color(0xFF16152B), borderRadius: BorderRadius.circular(14)),
              child: TextField(
                controller: _subjectController,
                style: const TextStyle(color: Colors.white, fontSize: 14),
                decoration: const InputDecoration(
                  labelText: 'Study Subject / Topic',
                  labelStyle: TextStyle(color: Color(0xFF94A3B8), fontSize: 13),
                  border: InputBorder.none,
                ),
              ),
            ),
            const SizedBox(height: 28),

            // Controls
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                OutlinedButton(
                  onPressed: _resetTimer,
                  style: OutlinedButton.styleFrom(
                    side: const BorderSide(color: Colors.white24),
                    shape: const CircleBorder(),
                    padding: const EdgeInsets.all(18),
                  ),
                  child: const Icon(Icons.refresh, color: Colors.white, size: 24),
                ),
                const SizedBox(width: 24),
                ElevatedButton(
                  onPressed: _isRunning ? _pauseTimer : _startTimer,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF008A3F),
                    shape: const CircleBorder(),
                    padding: const EdgeInsets.all(26),
                  ),
                  child: Icon(_isRunning ? Icons.pause : Icons.play_arrow, color: Colors.white, size: 36),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildModeChip(String label, int mins) {
    final isSel = _selectedMinutes == mins;
    return GestureDetector(
      onTap: () => _selectMinutes(mins),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isSel ? const Color(0xFF008A3F) : const Color(0xFF16152B),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: isSel ? const Color(0xFF10B981) : Colors.white.withOpacity(0.08)),
        ),
        child: Text(label, style: TextStyle(color: isSel ? Colors.white : const Color(0xFF94A3B8), fontWeight: FontWeight.bold, fontSize: 13)),
      ),
    );
  }
}
