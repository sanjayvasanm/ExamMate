import 'package:flutter/material.dart';
import 'services/api_service.dart';
import 'screens/auth_screen.dart';
import 'screens/home_screen.dart';
import 'screens/library_screen.dart';
import 'screens/ai_tutor_screen.dart';
import 'screens/study_screen.dart';
import 'screens/planner_screen.dart';
import 'screens/focus_screen.dart';
import 'screens/analytics_screen.dart';
import 'screens/profile_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ExamMateApp());
}

class ExamMateApp extends StatelessWidget {
  const ExamMateApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Exam Mate AI',
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0D0C22),
        primaryColor: const Color(0xFF008A3F),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF008A3F),
          secondary: Color(0xFF10B981),
          surface: Color(0xFF16152B),
          background: Color(0xFF0D0C22),
        ),
        cardColor: const Color(0xFF16152B),
        fontFamily: 'Roboto',
      ),
      home: const RootGate(),
    );

  }
}

class RootGate extends StatefulWidget {
  const RootGate({super.key});

  @override
  State<RootGate> createState() => _RootGateState();
}

class _RootGateState extends State<RootGate> {
  final ApiService _api = ApiService();
  bool _isAuthenticated = false;

  @override
  void initState() {
    super.initState();
    _checkAuth();
  }

  void _checkAuth() {
    setState(() {
      _isAuthenticated = _api.token != null;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!_isAuthenticated) {
      return AuthScreen(
        onLoginSuccess: () => setState(() => _isAuthenticated = true),
      );
    }
    return MainShell(
      onLogout: () => setState(() => _isAuthenticated = false),
    );
  }
}

class MainShell extends StatefulWidget {
  final VoidCallback onLogout;
  const MainShell({super.key, required this.onLogout});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _currentIndex = 0;

  void _navigateToIndex(int index) {
    setState(() {
      _currentIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    final List<Widget> screens = [
      HomeScreen(onNavigate: _navigateToIndex),
      const LibraryScreen(),
      const AiTutorScreen(),
      const StudyScreen(),
      const PlannerScreen(),
    ];

    return Scaffold(
      backgroundColor: const Color(0xFF0D0C22),
      appBar: PreferredSize(
        preferredSize: const Size.fromHeight(60),
        child: AppBar(
          backgroundColor: const Color(0xFF0D0C22),
          elevation: 0,
          title: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: const Color(0xFF008A3F).withOpacity(0.2),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(Icons.auto_awesome, color: Color(0xFF10B981), size: 18),
              ),
              const SizedBox(width: 10),
              const Text(
                'Exam Mate AI',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18, color: Colors.white, letterSpacing: -0.3),
              ),
            ],
          ),
          actions: [
            // Focus session quick action
            IconButton(
              icon: const Icon(Icons.timer_outlined, color: Color(0xFF38BDF8), size: 22),
              tooltip: 'Focus Timer',
              onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const FocusScreen())),
            ),
            // Analytics quick action
            IconButton(
              icon: const Icon(Icons.bar_chart_rounded, color: Color(0xFFA855F7), size: 22),
              tooltip: 'Analytics',
              onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const AnalyticsScreen())),
            ),
            // Profile quick action
            IconButton(
              icon: const Icon(Icons.account_circle_outlined, color: Color(0xFF10B981), size: 22),
              tooltip: 'Profile & Settings',
              onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ProfileScreen(onLogout: widget.onLogout))),
            ),
            const SizedBox(width: 4),
          ],
        ),
      ),
      body: IndexedStack(
        index: _currentIndex,
        children: screens,
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF16152B),
          border: Border(top: BorderSide(color: Colors.white.withOpacity(0.06))),
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: _navigateToIndex,
          type: BottomNavigationBarType.fixed,
          backgroundColor: const Color(0xFF16152B),
          selectedItemColor: const Color(0xFF10B981),
          unselectedItemColor: const Color(0xFF94A3B8),
          selectedFontSize: 11,
          unselectedFontSize: 11,
          selectedLabelStyle: const TextStyle(fontWeight: FontWeight.bold),
          items: const [
            BottomNavigationBarItem(
              icon: Icon(Icons.home_outlined),
              activeIcon: Icon(Icons.home),
              label: 'Home',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.folder_outlined),
              activeIcon: Icon(Icons.folder),
              label: 'Library',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.psychology_outlined),
              activeIcon: Icon(Icons.psychology),
              label: 'AI Tutor',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.style_outlined),
              activeIcon: Icon(Icons.style),
              label: 'Study',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.calendar_today_outlined),
              activeIcon: Icon(Icons.calendar_today),
              label: 'Planner',
            ),
          ],
        ),
      ),
    );
  }
}
