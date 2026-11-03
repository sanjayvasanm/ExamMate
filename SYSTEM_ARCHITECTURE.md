# ExamMate AI — System Architecture Specification

## 1. High-Level Architecture Overview

ExamMate AI follows a **4-Tier Cloud-Native Architecture** designed for high availability, low-memory footprint, sub-second AI inference, and persistent data storage.

```
+-----------------------------------------------------------------------------------+
|                           1. CLIENT TIER (Flutter Mobile)                         |
|  - UI Views (Library, Quiz, Flashcards, Chat, Analytics)                         |
|  - State & Auth Management (shared_preferences, ApiService)                       |
|  - Native Device Layer (file_picker, local secure cache, in-app webview)          |
+-----------------------------------------------------------------------------------+
                                       |
                                       | HTTPS / REST (JSON + Multipart)
                                       | Authorization: Bearer <JWT>
                                       v
+-----------------------------------------------------------------------------------+
|                       2. APPLICATION & API TIER (Render PaaS)                      |
|  - WSGI Server: Gunicorn (gthread workers, worker recycling, OOM guard)          |
|  - Application Framework: Flask REST API (CORS, JWT Authentication)               |
|  - Ingestion Engine: PyMuPDF (PDF), python-pptx (PPTX), python-docx (DOCX)        |
|  - Chunking Pipeline: Semantic window chunking (500-1000 tokens) with overlap     |
|  - RAG Engine: Scikit-learn TF-IDF Vectorizer + Cosine Similarity Top-K Retrieval |
+-----------------------------------------------------------------------------------+
                     |                                       |
                     | Sub-second AI Queries                 | PostgREST / Storage
                     v                                       v
+----------------------------------------+   +--------------------------------------+
|        3. AI INFERENCE TIER            |   |     4. DATA PERSISTENCE TIER         |
|             (Groq Cloud)               |   |            (Supabase)                |
|  - Model: LLaMA-3.3-70B-Versatile      |   |  - PostgreSQL Database:              |
|  - Groq LPU Hardware Acceleration     |   |    users, documents, chunks,         |
|  - Sub-second dynamic token generation |   |    quizzes, flashcards, analytics    |
|  - Tasks: Flashcards, Quizzes, Chat    |   |  - Object Storage:                   |
|                                        |   |    exam-documents bucket (raw files) |
+----------------------------------------+   +--------------------------------------+
```

---

## 2. Detailed Component Architecture

### Tier 1: Client Application (Mobile Frontend)
- **Framework**: Flutter 3.x (Dart 3.x), compiled to native Android APK.
- **Key Modules**:
  - `LibraryScreen`: Document upload, progress monitoring, and structured passage viewing.
  - `QuizScreen`: Interactive timed assessments with real-time score calculation.
  - `FlashcardScreen`: Spaced repetition flashcards with flip animations.
  - `ChatScreen`: Document-grounded conversational AI assistant with source citations.
  - `AnalyticsScreen`: Study streak counter, exam countdowns, and performance metrics.
  - `ApiService`: Centralized HTTP service with automatic bearer token attachment, error interception, and resilient timeouts.
  - `SharedPreferences`: Caches user credentials, session tokens, and user profile locally to persist logins across restarts.

### Tier 2: Backend Application & API (Render Cloud)
- **Container**: Docker image based on `python:3.10-slim`.
- **Process Manager**: Gunicorn WSGI configured with:
  - Worker Model: `gthread` (1 worker, 2 threads).
  - Memory Safeguard: Automatic worker restart after 50 requests (`--max-requests 50 --max-requests-jitter 10`) and manual `gc.collect()` to guarantee operation under Render's 512 MB memory limit.
- **REST API Endpoints**:
  - `POST /api/auth/register` & `POST /api/auth/login`: User creation, authentication, and JWT issuing.
  - `POST /api/documents/upload`: Multipart upload, file extraction, chunk creation, and cloud storage upload.
  - `GET /api/documents`: List user documents with processing status and stats.
  - `GET /api/documents/<id>`: Retrieve specific document details and extracted structured chunks.
  - `POST /api/quiz/generate`: Generates customized multiple-choice quizzes using context chunks and Groq LLM.
  - `POST /api/chat`: Performs RAG retrieval over document chunks and streams answers back with source citations.
  - `GET /api/flashcards`: Fetches and generates topic-based spaced repetition decks.

### Tier 3: External AI Inference (Groq Cloud)
- **Engine**: Groq Language Processing Units (LPUs).
- **Model**: `llama-3.3-70b-versatile`.
- **Role**:
  - High-throughput, low-latency natural language understanding and text generation.
  - Evaluates user questions against document passages.
  - Outputs structured JSON arrays for quizzes and flashcard sets.

### Tier 4: Database & Cloud Storage (Supabase)
- **PostgreSQL Database**:
  - Central relational storage replacing ephemeral local SQLite files.
  - Tables:
    - `users`: Identity, authentication credentials, study streaks, last active timestamps.
    - `documents`: Document metadata, original filename, storage bucket path, chunk counts, processing status.
    - `document_chunks`: Structured text passages mapped by UUID foreign keys to documents.
    - `quizzes`, `quiz_questions`, `quiz_attempts`: Assessment history, answer keys, and student scores.
    - `flashcard_decks`, `flashcards`: Spaced repetition cards and review intervals.
    - `questions`: History of questions asked and AI answers.
- **Cloud Object Storage**:
  - S3-compatible private storage bucket (`exam-documents`).
  - Stores uploaded original document files (`.pdf`, `.pptx`, `.docx`).

---

## 3. End-to-End Ingestion & Query Pipelines

### A. Document Ingestion Pipeline
1. **Selection**: User picks a `.pdf`, `.pptx`, or `.docx` file in the Flutter mobile app.
2. **Transfer**: The app uploads the file to the `/api/documents/upload` endpoint using multipart form data.
3. **Backup**: Backend uploads the raw file directly into Supabase Storage (`exam-documents/{user_id}/{doc_id}/{filename}`).
4. **Extraction**:
   - PDFs: PyMuPDF (`fitz`) parses text blocks and tables using fast C-level bindings.
   - PPTX: `python-pptx` iterates through slides, text frames, shapes, and presenter notes.
   - DOCX: `python-docx` extracts paragraphs, headers, and bullet structures.
5. **Chunking**: Text is partitioned into chunks of 500–1000 characters with 100-character overlaps.
6. **Persistence**: Extracted chunks are bulk-inserted with unique UUIDs into Supabase PostgreSQL `document_chunks` table.

### B. Retrieval-Augmented Generation (RAG) Pipeline
1. **Query**: User submits a question or requests a quiz based on an uploaded document.
2. **Fetch**: Backend retrieves all chunks associated with the document from Supabase.
3. **Vectorize & Score**:
   - `scikit-learn`'s `TfidfVectorizer` constructs an in-memory sparse matrix of document chunks and the query.
   - `cosine_similarity` scores all chunks against the query vector to pick the top-K highest-ranking passages.
4. **Prompt Assembly**: The top passages are injected into a system prompt instructing the model to rely strictly on provided content.
5. **Inference**: Groq LPU evaluates the prompt with `llama-3.3-70b-versatile` and produces a structured response in under 2 seconds.
6. **Delivery**: The response is returned via JSON to the Flutter client for instant display.

---

## 4. Key Architectural Attributes

| Attribute | Implementation | Benefit |
| :--- | :--- | :--- |
| **Persistence** | Supabase PostgreSQL & Object Storage | No data or file loss when backend server restarts or redeploys |
| **Low-Memory Footprint** | PyMuPDF + Gunicorn worker recycling + gc.collect() | Prevents SIGKILL OOM crashes on 512 MB Render instance |
| **Speed & Latency** | Groq LPU acceleration + TF-IDF ranking | Generates comprehensive quizzes & answers in under 2 seconds |
| **Mobile Stability** | Persistent local session state (`shared_preferences`) | Prevents unexpected logout prompts across app reboots |
