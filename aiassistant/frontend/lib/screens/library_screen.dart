import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import '../services/api_service.dart';

class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key});

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  final ApiService _api = ApiService();
  bool _isLoading = true;
  bool _isUploading = false;
  List<dynamic> _documents = [];
  String _searchQuery = '';
  String _selectedFilter = 'ALL';

  @override
  void initState() {
    super.initState();
    _loadDocuments();
  }

  Future<void> _loadDocuments() async {
    setState(() => _isLoading = true);
    try {
      final docs = await _api.getDocuments();
      if (mounted) {
        setState(() {
          _documents = docs;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isLoading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to load library: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  Future<void> _pickAndUploadFile() async {
    try {
      FilePickerResult? result = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['pdf', 'pptx', 'ppt', 'docx', 'txt', 'md'],
      );

      if (result != null && result.files.isNotEmpty) {
        final file = result.files.first;
        setState(() => _isUploading = true);

        final res = await _api.uploadDocument(file);
        if (mounted) {
          setState(() => _isUploading = false);
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Uploaded & Extracted: ${file.name} (${res['chunks_count']} passages)'),
              backgroundColor: const Color(0xFF008A3F),
            ),
          );
          _loadDocuments();
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isUploading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Upload error: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  Future<void> _deleteDocument(String docId, String filename) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF16152B),
        title: const Text('Delete Document?', style: TextStyle(color: Colors.white)),
        content: Text('Are you sure you want to delete "$filename" and all associated study chunks?', style: const TextStyle(color: Color(0xFF94A3B8))),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel', style: TextStyle(color: Color(0xFF94A3B8)))),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Delete', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );

    if (confirm == true) {
      try {
        await _api.deleteDocument(docId);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Document deleted'), backgroundColor: Color(0xFF008A3F)),
        );
        _loadDocuments();
      } catch (e) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Delete failed: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  void _showDocumentDetail(Map<String, dynamic> doc) async {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF16152B),
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => FutureBuilder<Map<String, dynamic>>(
        future: _api.getDocumentDetail(doc['id']),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const SizedBox(height: 300, child: Center(child: CircularProgressIndicator(color: Color(0xFF008A3F))));
          }
          final detail = snapshot.data ?? doc;
          final chunks = (detail['chunks'] as List?) ?? [];
          final warnings = (detail['warnings'] as List?) ?? [];

          return DraggableScrollableSheet(
            initialChildSize: 0.75,
            maxChildSize: 0.95,
            minChildSize: 0.5,
            expand: false,
            builder: (_, scrollController) => Padding(
              padding: const EdgeInsets.all(20.0),
              child: ListView(
                controller: scrollController,
                children: [
                  Center(child: Container(width: 40, height: 4, decoration: BoxDecoration(color: Colors.white24, borderRadius: BorderRadius.circular(2)))),
                  const SizedBox(height: 16),
                  Text(detail['filename'] ?? 'Document', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white)),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    children: [
                      Chip(
                        backgroundColor: const Color(0xFF008A3F).withOpacity(0.2),
                        label: Text('Confidence: ${detail['confidence_score']}%', style: const TextStyle(color: Color(0xFF10B981), fontSize: 12)),
                      ),
                      Chip(
                        backgroundColor: const Color(0xFF0D0C22),
                        label: Text('${detail['page_count']} Pages', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                      ),
                      Chip(
                        backgroundColor: const Color(0xFF0D0C22),
                        label: Text('${detail['file_type']}', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (warnings.isNotEmpty) ...[
                    const Text('Extraction Diagnostics:', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.amberAccent, fontSize: 14)),
                    const SizedBox(height: 6),
                    ...warnings.map((w) => Padding(
                      padding: const EdgeInsets.only(bottom: 4.0),
                      child: Text('• $w', style: const TextStyle(color: Colors.amber, fontSize: 12)),
                    )),
                    const SizedBox(height: 16),
                  ],
                  const Text('Extracted Structured Passages:', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white)),
                  const SizedBox(height: 10),
                  ...chunks.map((c) => Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFF0D0C22),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.white.withOpacity(0.05)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text('Page ${c['page_number']} • ${c['section_title']}', style: const TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF10B981), fontSize: 12)),
                            Text('${c['token_count']} words', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11)),
                          ],
                        ),
                        const SizedBox(height: 6),
                        Text(c['chunk_text'] ?? '', style: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 13, height: 1.4)),
                      ],
                    ),
                  )),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _documents.where((d) {
      final name = (d['filename'] ?? '').toString().toLowerCase();
      final type = (d['file_type'] ?? '').toString().toUpperCase();
      final matchesQuery = name.contains(_searchQuery.toLowerCase());
      final matchesType = _selectedFilter == 'ALL' || type == _selectedFilter;
      return matchesQuery && matchesType;
    }).toList();

    return Scaffold(
      backgroundColor: const Color(0xFF0D0C22),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0C22),
        elevation: 0,
        title: const Text('Study Library', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: Color(0xFF10B981)),
            onPressed: _loadDocuments,
          )
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _isUploading ? null : _pickAndUploadFile,
        backgroundColor: const Color(0xFF008A3F),
        icon: _isUploading
            ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
            : const Icon(Icons.add, color: Colors.white),
        label: Text(_isUploading ? 'Extracting...' : 'Upload Document', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
      ),
      body: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20.0),
        child: Column(
          children: [
            // Search field
            TextField(
              onChanged: (val) => setState(() => _searchQuery = val),
              style: const TextStyle(color: Colors.white),
              decoration: InputDecoration(
                hintText: 'Search study documents...',
                hintStyle: const TextStyle(color: Color(0xFF94A3B8)),
                prefixIcon: const Icon(Icons.search, color: Color(0xFF10B981)),
                filled: true,
                fillColor: const Color(0xFF16152B),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
              ),
            ),
            const SizedBox(height: 12),

            // Format filter chips
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: ['ALL', 'PDF', 'PPTX', 'DOCX', 'TXT'].map((f) {
                  final isSelected = _selectedFilter == f;
                  return Padding(
                    padding: const EdgeInsets.only(right: 8.0),
                    child: ChoiceChip(
                      label: Text(f),
                      selected: isSelected,
                      onSelected: (selected) => setState(() => _selectedFilter = f),
                      selectedColor: const Color(0xFF008A3F),
                      backgroundColor: const Color(0xFF16152B),
                      labelStyle: TextStyle(
                        color: isSelected ? Colors.white : const Color(0xFF94A3B8),
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
            const SizedBox(height: 16),

            // Document list
            Expanded(
              child: _isLoading
                  ? const Center(child: CircularProgressIndicator(color: Color(0xFF008A3F)))
                  : filtered.isEmpty
                      ? Center(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const Icon(Icons.folder_open, size: 54, color: Color(0xFF94A3B8)),
                              const SizedBox(height: 12),
                              const Text('No documents found.', style: TextStyle(color: Color(0xFF94A3B8), fontSize: 16)),
                              const SizedBox(height: 6),
                              const Text('Upload PDFs, PPTX or DOCX files to begin.', style: TextStyle(color: Color(0xFF64748B), fontSize: 13)),
                            ],
                          ),
                        )
                      : ListView.builder(
                          itemCount: filtered.length,
                          itemBuilder: (ctx, idx) {
                            final doc = filtered[idx];
                            final score = doc['confidence_score'] ?? 0.0;
                            final hasWarnings = (doc['warnings'] as List?)?.isNotEmpty ?? false;

                            return Card(
                              margin: const EdgeInsets.only(bottom: 12),
                              color: const Color(0xFF16152B),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                                side: BorderSide(color: Colors.white.withOpacity(0.06)),
                              ),
                              child: ListTile(
                                onTap: () => _showDocumentDetail(doc),
                                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                                leading: Container(
                                  padding: const EdgeInsets.all(10),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF0D0C22),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: Icon(
                                    doc['file_type'] == 'PDF' ? Icons.picture_as_pdf : Icons.slideshow,
                                    color: const Color(0xFF10B981),
                                  ),
                                ),
                                title: Text(
                                  doc['filename'] ?? 'Document',
                                  style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 15),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                subtitle: Padding(
                                  padding: const EdgeInsets.only(top: 4.0),
                                  child: Row(
                                    children: [
                                      Text('${doc['page_count']} Pages • ${doc['file_type']}', style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 12)),
                                      const SizedBox(width: 8),
                                      if (hasWarnings)
                                        const Icon(Icons.warning_amber_rounded, color: Colors.amber, size: 16),
                                    ],
                                  ),
                                ),
                                trailing: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                      decoration: BoxDecoration(
                                        color: const Color(0xFF008A3F).withOpacity(0.15),
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      child: Text('$score%', style: const TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF10B981), fontSize: 11)),
                                    ),
                                    IconButton(
                                      icon: const Icon(Icons.delete_outline, color: Colors.redAccent, size: 20),
                                      onPressed: () => _deleteDocument(doc['id'], doc['filename']),
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
      ),
    );
  }
}
