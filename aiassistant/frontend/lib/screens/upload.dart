import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart' as fp;
import '../services/api_service.dart';

class UploadScreen extends StatefulWidget {
  const UploadScreen({Key? key}) : super(key: key);

  @override
  State<UploadScreen> createState() => _UploadScreenState();
}

class _UploadScreenState extends State<UploadScreen> {
  final ApiService _apiService = ApiService();
  bool _isUploading = false;
  String? _uploadStatus;

  Future<void> _pickAndUploadFile() async {
    FilePickerResult? result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['pdf', 'doc', 'docx', 'ppt', 'pptx'],
    );

    if (result != null) {
      setState(() {
        _isUploading = true;
        _uploadStatus = 'Uploading and processing document...';
      });

      try {
        var response = await _apiService.uploadDocument(result.files.first);
        if (!mounted) return;
        setState(() {
          _uploadStatus = 'Success! Document ID: ${response['document_id']}';
        });

        // Simulating immediate transition
        Future.delayed(const Duration(seconds: 2), () {
          if (!mounted) return;
          Navigator.pushReplacementNamed(context, '/ask');
        });
      } catch (e) {
        if (mounted) {
          setState(() {
            _uploadStatus = 'Failed to upload: $e';
          });
        }
      } finally {
        if (mounted) {
          setState(() {
            _isUploading = false;
          });
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    bool isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Upload Document'),
        centerTitle: true,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              GestureDetector(
                onTap: _isUploading ? null : _pickAndUploadFile,
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(48),
                  decoration: BoxDecoration(
                    color:
                        isDark ? const Color(0xFF1A1935) : Colors.green.shade50,
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(
                      color: Theme.of(context)
                          .colorScheme
                          .primary
                          .withValues(alpha: 0.5),
                      width: 2,
                      style: BorderStyle.solid,
                    ),
                  ),
                  child: Column(
                    children: [
                      Icon(
                        Icons.cloud_upload_outlined,
                        size: 64,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                      const SizedBox(height: 16),
                      Text(
                        'Tap to Browse Files',
                        style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Supported formats: .pdf, .docx, .pptx',
                        style: TextStyle(color: Colors.grey),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 32),
              if (_isUploading) const CircularProgressIndicator(),
              if (_uploadStatus != null)
                Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Text(
                    _uploadStatus!,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

// Compatibility shim for file_picker versions that expose pickFiles statically.
typedef FilePickerResult = fp.FilePickerResult;
typedef FileType = fp.FileType;

class FilePicker {
  static FilePickerCompat get platform => FilePickerCompat();
}

class FilePickerCompat {
  Future<fp.FilePickerResult?> pickFiles({
    fp.FileType type = fp.FileType.any,
    List<String>? allowedExtensions,
  }) {
    return fp.FilePicker.pickFiles(
      type: type,
      allowedExtensions: allowedExtensions,
    );
  }
}
