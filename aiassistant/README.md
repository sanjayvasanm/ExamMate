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

- **Backend:** Python (Flask), MongoDB, Groq API (LLM), JWT Authentication.
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

## 📜 License
This project is licensed under the MIT License - see the LICENSE file for details.

---
*Built with ❤️ by the Exam Mate Team*
