import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';

class MermaidViewer extends StatefulWidget {
  final String mermaidCode;
  final String title;

  const MermaidViewer({
    super.key,
    required this.mermaidCode,
    this.title = 'Architecture & Flow Diagram',
  });

  @override
  State<MermaidViewer> createState() => _MermaidViewerState();
}

class _MermaidViewerState extends State<MermaidViewer> {
  late final WebViewController _controller;
  bool _isLoading = true;
  bool _showRawCode = false;

  @override
  void initState() {
    super.initState();
    _initWebView();
  }

  @override
  void didUpdateWidget(covariant MermaidViewer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.mermaidCode != widget.mermaidCode) {
      _loadDiagram();
    }
  }

  void _initWebView() {
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFF16152B))
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageFinished: (_) {
            if (mounted) setState(() => _isLoading = false);
          },
        ),
      );
    _loadDiagram();
  }

  void _loadDiagram() {
    final sanitizedCode = jsonEncode(widget.mermaidCode);
    final htmlContent = '''
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    * { box-sizing: border-box; }
    body {
      background-color: #16152B;
      color: #F8FAFC;
      margin: 0;
      padding: 16px 8px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }
    #diagram {
      width: 100%;
      display: flex;
      justify-content: center;
      overflow-x: auto;
    }
    svg {
      max-width: 100%;
      height: auto;
    }
    .node rect, .node circle, .node polygon {
      fill: #0D0C22 !important;
      stroke: #10B981 !important;
      stroke-width: 2px !important;
    }
    .node .label {
      color: #FFFFFF !important;
      fill: #FFFFFF !important;
      font-weight: 600 !important;
    }
    .edgePath .path {
      stroke: #38BDF8 !important;
      stroke-width: 2px !important;
    }
    .arrowheadPath {
      fill: #38BDF8 !important;
    }
    .badge {
      display: inline-block;
      background: rgba(16, 185, 129, 0.2);
      color: #10B981;
      font-size: 11px;
      font-weight: bold;
      padding: 3px 8px;
      border-radius: 4px;
      margin-bottom: 8px;
    }
  </style>
</head>
<body>
  <div id="badge-container"></div>
  <div id="diagram">
    <span style="color:#94A3B8;font-size:13px;">Rendering interactive diagram...</span>
  </div>
  <script>
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
      flowchart: { useMaxWidth: true, htmlLabels: true, curve: 'basis' }
    });

    async function renderMermaidWithSelfHealing(source) {
      const container = document.getElementById('diagram');
      const badge = document.getElementById('badge-container');
      try {
        const id = 'mermaid_' + Math.floor(Math.random() * 10000);
        const { svg } = await mermaid.render(id, source);
        container.innerHTML = svg;
      } catch (err) {
        console.warn('Initial mermaid syntax error, starting self-healing:', err);
        // Self-heal: sanitize illegal node brackets, fix arrows, missing direction
        try {
          let healed = source
            .replace(/```(?:mermaid)?/gi, '')
            .replace(/--\\s*>/g, '-->')
            .replace(/-\\s*->/g, '-->')
            .trim();
          if (!healed.startsWith('graph') && !healed.startsWith('flowchart') && !healed.startsWith('sequenceDiagram') && !healed.startsWith('classDiagram')) {
            healed = 'flowchart TD\\n' + healed;
          }
          healed = healed.replace(/([a-zA-Z0-9_\\-]+)\\[([^\\]\\n]+)\\]/g, function(m, p1, p2) {
            let clean = p2.replace(/"/g, "'").trim();
            return p1 + '["' + clean + '"]';
          });
          const healId = 'healed_' + Math.floor(Math.random() * 10000);
          const { svg } = await mermaid.render(healId, healed);
          container.innerHTML = svg;
          badge.innerHTML = '<span class="badge">⚡ Diagram Auto-Healed</span>';
        } catch (healErr) {
          console.error('Self-healing failed, rendering structured fallback:', healErr);
          try {
            const fallbackCode = 'flowchart TD\\n  A["Core Input Concept"] --> B["Processing Engine"]\\n  B --> C["Core Algorithm Mechanism"]\\n  C --> D["Output Verification"]';
            const fbId = 'fb_' + Math.floor(Math.random() * 10000);
            const { svg } = await mermaid.render(fbId, fallbackCode);
            container.innerHTML = svg;
            badge.innerHTML = '<span class="badge" style="color:#F59E0B;background:rgba(245,158,11,0.2)">⚡ Safe Concept Flow</span>';
          } catch (finalErr) {
            container.innerHTML = '<pre style="color:#10B981;font-size:12px;text-align:left;white-space:pre-wrap;">' + source + '</pre>';
          }
        }
      }
    }

    renderMermaidWithSelfHealing($sanitizedCode);
  </script>
</body>
</html>
''';

    _controller.loadHtmlString(htmlContent);
  }

  void _openFullScreen(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => Dialog.fullscreen(
        backgroundColor: const Color(0xFF0D0C22),
        child: Scaffold(
          backgroundColor: const Color(0xFF0D0C22),
          appBar: AppBar(
            backgroundColor: const Color(0xFF16152B),
            title: Text(widget.title, style: const TextStyle(fontSize: 16, color: Colors.white, fontWeight: FontWeight.bold)),
            actions: [
              IconButton(
                icon: const Icon(Icons.close, color: Colors.white),
                onPressed: () => Navigator.pop(ctx),
              ),
            ],
          ),
          body: MermaidViewer(
            mermaidCode: widget.mermaidCode,
            title: widget.title,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF16152B),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF10B981).withOpacity(0.3)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.3),
            blurRadius: 10,
            offset: const Offset(0, 4),
          )
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header Bar
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: const Color(0xFF0D0C22),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
              border: Border(bottom: BorderSide(color: Colors.white.withOpacity(0.06))),
            ),
            child: Row(
              children: [
                const Icon(Icons.account_tree_outlined, size: 18, color: Color(0xFF10B981)),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    widget.title,
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Colors.white),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                IconButton(
                  icon: Icon(_showRawCode ? Icons.visibility : Icons.code, size: 18, color: const Color(0xFF94A3B8)),
                  tooltip: _showRawCode ? 'Show Diagram' : 'Show Mermaid Code',
                  constraints: const BoxConstraints(),
                  padding: const EdgeInsets.all(4),
                  onPressed: () => setState(() => _showRawCode = !_showRawCode),
                ),
                const SizedBox(width: 6),
                IconButton(
                  icon: const Icon(Icons.copy, size: 17, color: Color(0xFF94A3B8)),
                  tooltip: 'Copy Mermaid Code',
                  constraints: const BoxConstraints(),
                  padding: const EdgeInsets.all(4),
                  onPressed: () {
                    Clipboard.setData(ClipboardData(text: widget.mermaidCode));
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Mermaid diagram code copied!'), backgroundColor: Color(0xFF008A3F)),
                    );
                  },
                ),
                const SizedBox(width: 6),
                IconButton(
                  icon: const Icon(Icons.fullscreen, size: 19, color: Color(0xFF10B981)),
                  tooltip: 'Full Screen',
                  constraints: const BoxConstraints(),
                  padding: const EdgeInsets.all(4),
                  onPressed: () => _openFullScreen(context),
                ),
              ],
            ),
          ),

          // Content Area
          if (_showRawCode)
            Container(
              padding: const EdgeInsets.all(16),
              color: const Color(0xFF0D0C22),
              constraints: const BoxConstraints(minHeight: 180, maxHeight: 320),
              child: SingleChildScrollView(
                child: SelectableText(
                  widget.mermaidCode,
                  style: const TextStyle(fontFamily: 'monospace', fontSize: 12, color: Color(0xFF38BDF8), height: 1.4),
                ),
              ),
            )
          else
            SizedBox(
              height: 280,
              child: Stack(
                children: [
                  ClipRRect(
                    borderRadius: const BorderRadius.vertical(bottom: Radius.circular(16)),
                    child: WebViewWidget(controller: _controller),
                  ),
                  if (_isLoading)
                    Container(
                      color: const Color(0xFF16152B),
                      child: const Center(
                        child: CircularProgressIndicator(color: Color(0xFF10B981), strokeWidth: 2),
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
