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

- **Backend:** Python (Flask), Supabase/Postgres, Groq API (LLM), JWT Authentication.
- **Frontend:** HTML5, Vanilla JavaScript, CSS3 (Modern Glassmorphism), Mermaid.js.
- **Mobile:** Flutter (WebView Hybrid Architecture), PWA (Service Workers).
- **Tooling:** Ripgrep, Shell Scripting, Git.

## 🏗️ Project Structure

```text
├── backend/            # Flask API & AI Pipeline
│   ├── pipeline/       # RAG logic, Extraction, and Diagram refactoring
│   ├── migrations/     # Additive Supabase migrations
│   └── tests/          # Focused backend workflow tests
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
- Supabase project (review and manually run `backend/migrations/20261019_persistent_documents.sql`)
- Groq API Key

### 2. Backend Setup
```bash
cd backend
pip install -r requirements.txt
# Set your environment variables in a .env file:
# JWT_SECRET=your_secret
# SUPABASE_URL=https://your-project.supabase.co
# SUPABASE_KEY=your_service_role_key
# SUPABASE_STORAGE_BUCKET=exam-documents
# GROQ_API_KEY=your_key
python app.py
```

The migration is additive and must be reviewed before running against any
production Supabase project. It creates a private Storage bucket and the
`document_chunks` table. The Flask backend stores uploaded documents in that
bucket and reconstructs its in-memory TF-IDF index from persisted chunks after
restart. No browser code receives the service-role key.

Run focused backend tests with:

```bash
cd backend
python -m unittest discover -s tests -v
```

These tests mock Supabase, Storage, document extraction, and Groq quiz
generation. Live Supabase migration/storage checks and live Groq generation
still require deployment credentials.

### 3. Frontend / Mobile Setup
The active browser UI is served from `frontend/assets` and can be deployed as
static files to Vercel. Set the Vercel project root to `aiassistant/frontend`;
the checked-in `vercel.json` routes `/` to the login page. The Flutter shell
also builds independently:

```bash
cd frontend
flutter build web --release \
  --dart-define=EXAM_MATE_API_URL=https://exam-mate-backend-w5t6.onrender.com/api
```

For the native Flutter API service, use the same compile-time variable for
production and pass a local URL explicitly during local development, for
example `--dart-define=EXAM_MATE_API_URL=http://10.0.2.2:5000/api`. Do not put
backend secrets in Flutter or Vercel variables.

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

For Render, use the repository root `aiassistant`, Docker context `backend`,
and `backend/Dockerfile`. Set `ENVIRONMENT=production`,
`CORS_ORIGINS` to the exact deployed Vercel origin, and keep
`SUPABASE_KEY`, `JWT_SECRET`, and `GROQ_API_KEY` as Render secrets. Health is
available at both `/health` and `/api/health`.

## 📜 License
This project is licensed under the MIT License - see the LICENSE file for details.

---
*Built with ❤️ by the Exam Mate Team*
