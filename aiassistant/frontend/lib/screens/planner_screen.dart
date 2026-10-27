import 'package:flutter/material.dart';
import '../services/api_service.dart';

class PlannerScreen extends StatefulWidget {
  const PlannerScreen({super.key});

  @override
  State<PlannerScreen> createState() => _PlannerScreenState();
}

class _PlannerScreenState extends State<PlannerScreen> {
  final ApiService _api = ApiService();
  bool _isLoading = true;
  List<dynamic> _exams = [];
  List<dynamic> _tasks = [];
  String _taskFilter = 'ALL'; // ALL, PENDING, COMPLETED

  @override
  void initState() {
    super.initState();
    _loadPlannerData();
  }

  Future<void> _loadPlannerData() async {
    setState(() => _isLoading = true);
    try {
      final exams = await _api.getExams();
      final tasks = await _api.getTasks();
      if (mounted) {
        setState(() {
          _exams = exams;
          _tasks = tasks;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _toggleTask(String taskId) async {
    try {
      await _api.toggleTask(taskId);
      _loadPlannerData();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error updating task: $e')));
    }
  }

  Future<void> _deleteTask(String taskId) async {
    try {
      await _api.deleteTask(taskId);
      _loadPlannerData();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error deleting task: $e')));
    }
  }

  Future<void> _deleteExam(String examId) async {
    try {
      await _api.deleteExam(examId);
      _loadPlannerData();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error deleting exam: $e')));
    }
  }

  void _showAddExamDialog() {
    final titleCtrl = TextEditingController();
    final subjectCtrl = TextEditingController();
    final syllabusCtrl = TextEditingController();
    DateTime selectedDate = DateTime.now().add(const Duration(days: 14));

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          backgroundColor: const Color(0xFF16152B),
          title: const Text('Schedule Upcoming Exam', style: TextStyle(color: Colors.white, fontSize: 18)),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: titleCtrl,
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(labelText: 'Exam Title (e.g. Midterm)', labelStyle: TextStyle(color: Color(0xFF94A3B8))),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: subjectCtrl,
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(labelText: 'Subject', labelStyle: TextStyle(color: Color(0xFF94A3B8))),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: syllabusCtrl,
                  style: const TextStyle(color: Colors.white),
                  decoration: const InputDecoration(labelText: 'Key Syllabus Modules', labelStyle: TextStyle(color: Color(0xFF94A3B8))),
                ),
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Date: ${selectedDate.year}-${selectedDate.month.toString().padLeft(2, '0')}-${selectedDate.day.toString().padLeft(2, '0')}', style: const TextStyle(color: Colors.white)),
                    TextButton(
                      onPressed: () async {
                        final picked = await showDatePicker(
                          context: context,
                          initialDate: selectedDate,
                          firstDate: DateTime.now(),
                          lastDate: DateTime.now().add(const Duration(days: 365)),
                        );
                        if (picked != null) {
                          setDialogState(() => selectedDate = picked);
                        }
                      },
                      child: const Text('Change Date', style: TextStyle(color: Color(0xFF10B981))),
                    ),
                  ],
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel', style: TextStyle(color: Color(0xFF94A3B8)))),
            ElevatedButton(
              onPressed: () async {
                if (titleCtrl.text.isEmpty || subjectCtrl.text.isEmpty) return;
                Navigator.pop(ctx);
                try {
                  await _api.createExam(
                    title: titleCtrl.text.trim(),
                    subject: subjectCtrl.text.trim(),
                    examDate: selectedDate.toIso8601String(),
                    syllabus: syllabusCtrl.text.trim(),
                  );
                  _loadPlannerData();
                } catch (e) {
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
                }
              },
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F)),
              child: const Text('Schedule', style: TextStyle(color: Colors.white)),
            ),
          ],
        ),
      ),
    );
  }

  void _showAddTaskDialog() {
    final titleCtrl = TextEditingController();
    String priority = 'medium';

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          backgroundColor: const Color(0xFF16152B),
          title: const Text('Create Study Task', style: TextStyle(color: Colors.white, fontSize: 18)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: titleCtrl,
                style: const TextStyle(color: Colors.white),
                decoration: const InputDecoration(labelText: 'Task Description', labelStyle: TextStyle(color: Color(0xFF94A3B8))),
              ),
              const SizedBox(height: 14),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Priority:', style: TextStyle(color: Color(0xFF94A3B8))),
                  DropdownButton<String>(
                    value: priority,
                    dropdownColor: const Color(0xFF16152B),
                    style: const TextStyle(color: Colors.white),
                    items: ['low', 'medium', 'high'].map((p) => DropdownMenuItem(value: p, child: Text(p.toUpperCase()))).toList(),
                    onChanged: (val) => setDialogState(() => priority = val!),
                  ),
                ],
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel', style: TextStyle(color: Color(0xFF94A3B8)))),
            ElevatedButton(
              onPressed: () async {
                if (titleCtrl.text.isEmpty) return;
                Navigator.pop(ctx);
                try {
                  await _api.createTask(
                    title: titleCtrl.text.trim(),
                    priority: priority,
                  );
                  _loadPlannerData();
                } catch (e) {
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
                }
              },
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F)),
              child: const Text('Add Task', style: TextStyle(color: Colors.white)),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final filteredTasks = _tasks.where((t) {
      if (_taskFilter == 'PENDING') return t['is_completed'] != 1;
      if (_taskFilter == 'COMPLETED') return t['is_completed'] == 1;
      return true;
    }).toList();

    return Scaffold(
      backgroundColor: const Color(0xFF0D0C22),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0C22),
        elevation: 0,
        title: const Text('Study Planner', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh, color: Color(0xFF10B981)), onPressed: _loadPlannerData),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFF008A3F)))
          : SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 12.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Upcoming Exams Header
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Examination Schedule', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white)),
                      ElevatedButton.icon(
                        onPressed: _showAddExamDialog,
                        icon: const Icon(Icons.add, size: 16, color: Colors.white),
                        label: const Text('Add Exam', style: TextStyle(color: Colors.white, fontSize: 13)),
                        style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10))),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (_exams.isEmpty)
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(color: const Color(0xFF16152B), borderRadius: BorderRadius.circular(12)),
                      child: const Text('No exams scheduled yet. Tap "Add Exam" to track upcoming tests.', style: TextStyle(color: Color(0xFF94A3B8))),
                    )
                  else
                    ..._exams.map((ex) {
                      final days = ex['days_left'] ?? 0;
                      return Container(
                        margin: const EdgeInsets.only(bottom: 10),
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: const Color(0xFF16152B),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: Colors.white.withOpacity(0.06)),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(ex['title'] ?? 'Exam', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 16)),
                                  const SizedBox(height: 4),
                                  Text('${ex['subject']} • Target Score: ${ex['target_score']}%', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                                  if ((ex['syllabus'] ?? '').isNotEmpty)
                                    Padding(
                                      padding: const EdgeInsets.only(top: 4.0),
                                      child: Text('Syllabus: ${ex['syllabus']}', style: const TextStyle(color: Color(0xFF64748B), fontSize: 11)),
                                    ),
                                ],
                              ),
                            ),
                            Row(
                              children: [
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                  decoration: BoxDecoration(
                                    color: days <= 7 ? Colors.red.withOpacity(0.2) : const Color(0xFF008A3F).withOpacity(0.2),
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  child: Text(
                                    days <= 0 ? 'Today!' : '$days days left',
                                    style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      color: days <= 7 ? Colors.redAccent : const Color(0xFF10B981),
                                      fontSize: 12,
                                    ),
                                  ),
                                ),
                                IconButton(
                                  icon: const Icon(Icons.delete_outline, color: Color(0xFF94A3B8), size: 18),
                                  onPressed: () => _deleteExam(ex['id']),
                                ),
                              ],
                            ),
                          ],
                        ),
                      );
                    }),

                  const SizedBox(height: 28),

                  // Tasks Header & Filter
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Study Tasks', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white)),
                      ElevatedButton.icon(
                        onPressed: _showAddTaskDialog,
                        icon: const Icon(Icons.add_task, size: 16, color: Colors.white),
                        label: const Text('Add Task', style: TextStyle(color: Colors.white, fontSize: 13)),
                        style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF008A3F), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10))),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: ['ALL', 'PENDING', 'COMPLETED'].map((f) {
                      final isSel = _taskFilter == f;
                      return Padding(
                        padding: const EdgeInsets.only(right: 8.0),
                        child: ChoiceChip(
                          label: Text(f),
                          selected: isSel,
                          onSelected: (_) => setState(() => _taskFilter = f),
                          selectedColor: const Color(0xFF008A3F),
                          backgroundColor: const Color(0xFF16152B),
                          labelStyle: TextStyle(color: isSel ? Colors.white : const Color(0xFF94A3B8), fontWeight: FontWeight.bold, fontSize: 11),
                        ),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 12),
                  if (filteredTasks.isEmpty)
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(color: const Color(0xFF16152B), borderRadius: BorderRadius.circular(12)),
                      child: const Text('No tasks in this category.', style: TextStyle(color: Color(0xFF94A3B8))),
                    )
                  else
                    ...filteredTasks.map((t) {
                      final isDone = t['is_completed'] == 1;
                      final priority = t['priority'] ?? 'medium';

                      return Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        decoration: BoxDecoration(
                          color: const Color(0xFF16152B),
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: Colors.white.withOpacity(0.06)),
                        ),
                        child: ListTile(
                          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                          leading: Checkbox(
                            value: isDone,
                            activeColor: const Color(0xFF008A3F),
                            checkColor: Colors.white,
                            onChanged: (_) => _toggleTask(t['id']),
                          ),
                          title: Text(
                            t['title'] ?? '',
                            style: TextStyle(
                              color: isDone ? const Color(0xFF64748B) : Colors.white,
                              decoration: isDone ? TextDecoration.lineThrough : null,
                              fontWeight: FontWeight.w500,
                              fontSize: 14,
                            ),
                          ),
                          subtitle: Text(
                            'Priority: ${priority.toUpperCase()}',
                            style: TextStyle(
                              color: priority == 'high' ? Colors.redAccent : const Color(0xFF94A3B8),
                              fontSize: 11,
                            ),
                          ),
                          trailing: IconButton(
                            icon: const Icon(Icons.close, color: Color(0xFF64748B), size: 18),
                            onPressed: () => _deleteTask(t['id']),
                          ),
                        ),
                      );
                    }),
                  const SizedBox(height: 24),
                ],
              ),
            ),
    );
  }
}
