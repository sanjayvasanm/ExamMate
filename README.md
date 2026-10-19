# Exam Mate AI (SAIS++)

![Header Image](https://socialify.git.ci/username/exam-mate/image?description=AI-Powered%20Academic%20Assistant%20with%20Visual%20Logic%20Generation&font=Inter&name=1&owner=1&pattern=Plus&theme=Dark)

**Exam Mate** is a state-of-the-art AI-powered academic platform designed to revolutionize how students interact with educational materials. It combines a sophisticated RAG (Retrieval-Augmented Generation) pipeline with high-fidelity visual rendering and a premium mobile experience.

## 🚀 Key Features

- **🧠 Intelligent RAG Engine:** Upload PDFs, DOCX, and PPTX files to create a personal knowledge base. The AI retrieves context from your documents to provide fact-grounded exam-style answers.
- **🎨 Self-Correcting Visual Logic:** Automated Mermaid.js diagram generation for technical concepts, flowcharts, and architectural designs, featuring an autonomous syntax validation and refactoring loop.
- **📱 Mobile-Optimized (PWA & APK):** High-performance mobile experience with a custom Service Worker caching layer for instant loading and offline capability.
- **💎 Premium UI/UX:** A stunning interface featuring glassmorphism, smooth micro-animations, and a curated dark-mode aesthetic.
- **📊 Study Analytics:** Track your progress with study streaks, average scores, and comprehensive document history.

## 🛠️ Tech Stack

- **Backend:** Python (Flask), supabase, Groq API (LLM), JWT Authentication.
- **Frontend:** HTML5, Vanilla JavaScript, CSS3 (Modern Glassmorphism), Mermaid.js.
- **Mobile:** Flutter (WebView Hybrid Architecture), PWA (Service Workers).
- **Tooling:** Ripgrep, Shell Scripting, Git.

## 🏗️ Project Structure

```text
├── backend/            # Flask API & AI Pipeline
│   ├── pipeline/       # RAG logic, Extraction, and Diagram refactoring
│   └── uploads/        # Storage for processed academic documents
├── frontend/           # Flutter & Web Content
│   ├── assets/         # HTML/JS/CSS source for the platforms
│   ├── lib/            # Flutter wrapper logic
│   └── android/        # Android Native configuration (PWA/Manifest)
└── README.md
```

## ⚙️ Installation & Setup

### 1. Prerequisites
- Python 3.10+
- Flutter SDK (for APK building)
- MongoDB Instance
- Groq API Key

### 2. Backend Setup
```bash
cd backend
pip install -r requirements.txt
# Set your environment variables in a .env file:
# JWT_SECRET=your_secret
# GROQ_API_KEY=your_key
python app.py
```

The backend exposes `GET /api/health` for Render health checks. Set
`CORS_ORIGINS` to the exact deployed frontend origin in production (a
comma-separated list is supported by Flask-CORS), and keep `JWT_SECRET`,
`SUPABASE_URL`, `SUPABASE_KEY`, and `GROQ_API_KEY` in Render environment
variables rather than source control.

### 3. Frontend / Mobile Setup
To connect your physical phone to your local PC:
1. Find your PC's IP (`ipconfig` on Windows).
2. Update `DEFAULT_PC_IP` in `frontend/assets/api-utils.js`.
3. Open Port 5000 in your Firewall (PowerShell Admin):
   ```powershell
   New-NetFirewallRule -DisplayName "Allow Flask" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
   ```
4. Build the APK:
   ```bash
   cd frontend
   flutter build apk
   ```

### 4. Web deployment

The supported web frontend is the static HTML application bundled under
`frontend/assets/`. Deploy `frontend/` to Vercel; `frontend/vercel.json`
rewrites the public routes to those assets. Set `window.EXAM_MATE_API_URL` (or
use the existing `em_api_override` developer setting) when a deployment needs a
different API origin. Deploy the Flask service with the checked-in
`aiassistant/render.yaml`; the Dockerfile uses Render's `$PORT` and Gunicorn.

After applying `backend/schema.sql` to the existing Supabase project, the
planner is available at `/api/plans`. The migration is additive and does not
replace existing tables or data.

### 5. Flashcards and analytics migration

Review and run `backend/migrations/20261019_flashcards_and_tasks.sql` manually
in the Supabase SQL editor, then run the read-only checks in
`backend/migrations/verify_flashcards_and_tasks.sql`. This migration adds
server-managed flashcards/review scheduling and optional planner metadata; it
does not drop or rewrite existing records. The API routes are `/api/flashcards`, `/api/flashcards/<id>/review`,
`/api/analytics`, `/api/tasks`, `/api/quizzes/attempts/<id>/retry-wrong`, and
`/api/focus-sessions`. The focus page is bundled at
`frontend/assets/focus_exam_mate/code.html`.

For a production schema preflight, run
`backend/migrations/verify_exam_mate_schema.sql`. If it reports only
`document_chunks` (and not `document_chunk`), the backend is already aligned
with the required relation. If it reports only `document_chunk`, review and
run `backend/migrations/20261019_reconcile_document_chunks.sql`, then run the
verification script again and confirm the PostgREST schema cache reload.

## 📜 License
This project is licensed under the MIT License - see the LICENSE file for details.

---
*Built with ❤️ by the Exam Mate Team*
