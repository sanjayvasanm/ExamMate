import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ExamMateApp());
}

class ExamMateApp extends StatelessWidget {
  const ExamMateApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Exam Mate',
      theme: ThemeData(
        scaffoldBackgroundColor: const Color(0xFF0D0C22),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF008A3F),
          brightness: Brightness.dark,
        ),
      ),
      home: const ExamMateWebHost(),
    );
  }
}

class ExamMateWebHost extends StatefulWidget {
  const ExamMateWebHost({super.key});

  @override
  State<ExamMateWebHost> createState() => _ExamMateWebHostState();
}

class _ExamMateWebHostState extends State<ExamMateWebHost> {
  /// Serves the entire `assets/` folder on localhost.
  /// Navigate to any HTML page under assets/ via the web view.
  static const List<int> _candidatePorts = [8080, 8081, 8082, 8083];
  InAppLocalhostServer? _localhostServer;
  int _serverPort = _candidatePorts.first;

  bool _serverReady = false;
  bool _serverError = false;

  @override
  void initState() {
    super.initState();
    _startServer();
  }

  Future<void> _startServer() async {
    if (mounted) {
      setState(() {
        _serverReady = false;
        _serverError = false;
      });
    }

    for (final port in _candidatePorts) {
      final server = InAppLocalhostServer(port: port, documentRoot: 'assets');
      try {
        await server.start();
        if (!mounted) {
          await server.close();
          return;
        }
        _localhostServer?.close();
        _localhostServer = server;
        _serverPort = port;
        setState(() => _serverReady = true);
        return;
      } catch (e) {
        debugPrint('Localhost server error on port $port: $e');
        await server.close();
      }
    }

    if (mounted) {
      setState(() => _serverError = true);
    }
  }

  @override
  void dispose() {
    _localhostServer?.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Loading state
    if (!_serverReady && !_serverError) {
      return const Scaffold(
        backgroundColor: Color(0xFF0D0C22),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircularProgressIndicator(
                  color: Color(0xFF008A3F), strokeWidth: 3),
              SizedBox(height: 20),
              Text(
                'Starting Exam Mate…',
                style: TextStyle(
                    color: Color(0xFF008A3F), fontWeight: FontWeight.bold),
              ),
            ],
          ),
        ),
      );
    }

    // Error state
    if (_serverError) {
      return Scaffold(
        backgroundColor: const Color(0xFF0D0C22),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: Colors.red, size: 48),
              const SizedBox(height: 16),
              const Text('Failed to start local server',
                  style: TextStyle(
                      color: Colors.white, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () {
                  setState(() {
                    _serverError = false;
                  });
                  _startServer();
                },
                child: const Text('Retry',
                    style: TextStyle(color: Color(0xFF008A3F))),
              ),
            ],
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: const Color(0xFF0D0C22),
      body: SafeArea(
        child: InAppWebView(
          // Always start at the login page.
          // If the user is already logged in, the login page's JS will redirect
          // them to the dashboard automatically via localStorage.
          initialUrlRequest: URLRequest(
            url: WebUri(
                'http://localhost:$_serverPort/login_exam_mate/code.html'),
          ),
          initialSettings: InAppWebViewSettings(
            javaScriptEnabled: true,
            domStorageEnabled: true,
            databaseEnabled: true,
            transparentBackground: true,
            useShouldOverrideUrlLoading: false,
            mediaPlaybackRequiresUserGesture: false,
            allowFileAccessFromFileURLs: false,
            allowUniversalAccessFromFileURLs: false,
            // Keep mixed content blocked; localhost is loaded over HTTP already.
            mixedContentMode: MixedContentMode.MIXED_CONTENT_NEVER_ALLOW,
          ),
          onLoadStart: (controller, url) {
            debugPrint('[WebView] Loading: $url');
          },
          onLoadStop: (controller, url) {
            debugPrint('[WebView] Loaded: $url');
          },
          onConsoleMessage: (controller, msg) {
            debugPrint('[WebView Console] ${msg.messageLevel}: ${msg.message}');
          },
          onReceivedHttpError: (controller, req, resp) {
            debugPrint('[WebView HTTP Error] ${resp.statusCode} - ${req.url}');
          },
        ),
      ),
    );
  }
}
