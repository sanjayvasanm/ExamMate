# Exam Mate AI — Otto Academic Study System

![Exam Mate AI Banner](https://img.shields.io/badge/Exam%20Mate%20AI-Otto%20Design%20System-656DE2?style=for-the-badge&logo=flutter&logoColor=white)
![Build Status](https://img.shields.io/badge/Android%20APK-Release%20Ready-059669?style=for-the-badge&logo=android&logoColor=white)
![Backend](https://img.shields.io/badge/Backend-Flask%20%7C%20Render%20Docker-121ECC?style=for-the-badge&logo=docker&logoColor=white)
![Database](https://img.shields.io/badge/Database-Supabase%20Postgres%20RLS-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![Frontend](https://img.shields.io/badge/Web-Vercel%20Production-EC9205?style=for-the-badge&logo=vercel&logoColor=white)

**Exam Mate AI** is a complete, production-ready AI notetaker and academic examination preparation platform inspired by the **Otto** study app design system (*Dribbble 27637592*). It delivers an interconnected, zero-dead-end study experience across 11 synchronized screens, backed by Groq LLM, TF-IDF document context retrieval, PostgreSQL on Supabase with Row Level Security (RLS), and a hybrid Flutter Android container.

---

## 🎨 Otto Design System & Visual Palette

Exam Mate AI adheres strictly to the Otto design tokens:
- **Canvas Background:** `#EFF0FA` (Soft lilac-tinted periwinkle)
- **Borders & Dividers:** `#BCC2F3` (Delicate periwinkle border line)
- **Secondary Iris Accent:** `#656DE2` (Electric lavender)
- **Primary Action Amber:** `#EC9205` (High-contrast, vibrant call-to-action)
- **Deep Onyx:** `#09090A` (Typography and selected states)
- **Warm Slate:** `#A6908B` (Secondary labels and metadata)
- **Electric Royal Blue:** `#121ECC` (Primary brand accent, audio cards, mascot)
- **Typography:** Plus Jakarta Sans & Inter, 28px border-radius containers, smooth micro-interactions.

---

## 📱 Complete Screen Architecture & User Flow

The application features a seamless, cohesive user journey where data flows continuously between all 11 modules:

```mermaid
flowchart TD
    Splash[index.html: Session Check] -->|No Token| Login[login_exam_mate: Auth / Quick Demo]
    Login <-->|Toggle| Signup[signup_exam_mate: Register]
    Splash -->|Active Token| Dash[dashboard_exam_mate: Main Library]
    Login --> Dash
    Signup --> Dash

    Dash -->|Create / Upload| Upload[upload_document_exam_mate: Ingestion]
    Upload -->|Ingest Doc| Flashcards[flashcards_exam_mate: 3D Flip & Spaced Repetition]
    Upload -->|Ask AI with Doc| Ask[ask_question_exam_mate: Question Composer]
    
    Dash -->|Practice| Flashcards
    Dash -->|Quick Ask| Ask
    Dash -->|Study Planner| Planner[planner_exam_mate: Timeline & Milestones]
    Dash -->|Focus Timer| Timer[timer_exam_mate: Pomodoro & Synthesizer]

    Ask -->|Submit Question| Workspace[answer_exam_mate: Notes, Flowcharts & Podcast]
    Workspace -->|Follow-up Question| Ask
    Workspace -->|Resource Tabs| Flashcards
    Flashcards -->|Resource Tabs| Quiz[quiz_exam_mate: Assessment & Scoring]
    Quiz -->|Review Score| Dash

    Dash -->|Analytics / History| History[history_exam_mate: Study Archive & Metrics]
    Dash -->|You / Settings| Profile[profile_exam_mate: Account & API Settings]
    Profile -->|Sign Out| Login
```

---

## 🗄️ Database Setup (Supabase)

The database schema is fully defined in [`backend/schema.sql`](file:///d:/projects/saais/aiassistant/backend/schema.sql).

### Steps to Apply:
1. Log into your [Supabase Dashboard](https://supabase.com/dashboard).
2. Open the **SQL Editor** in your project (`cxhxgtmedbldfmofortm`).
3. Paste and run the contents of `backend/schema.sql`.
4. The script creates:
   - `users`: Accounts, study streaks, document & question counts, last active timestamps.
   - `documents`: Uploaded file records, file types, summaries, chunk counts.
   - `questions`: History of queries, structured answers, Mermaid code.
   - `study_plans`: Upcoming exams, target dates, completion status.
   - `flashcards`: Spaced repetition cards, review counts, status.
   - `quizzes`: Quiz attempts, score percentages, questions JSONB.
   - `increment_documents_uploaded` & `increment_total_questions` RPCs.
   - RLS enabled with full client and backend access policies.

---

## 🚀 Local Development & Testing

### 1. Run the Web Application
Simply double-click:
```bat
start_web.bat
```
- Spins up a local HTTP server on `http://localhost:8080`.
- Automatically opens your default browser at `http://localhost:8080/index.html`.
- Works out-of-the-box with both live cloud APIs and intelligent demo fallbacks!

### 2. Run the Local Python Backend
Double-click:
```bat
backend\start_backend.bat
```
- Activates virtual environment, installs dependencies from `requirements.txt`.
- Starts the Flask API on `http://0.0.0.0:5000`.

### 3. Build the Release Android APK
Double-click from repository root:
```bat
..\build_apk.bat
```
- Automatically configures OpenJDK 17 (`C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot`).
- Links Gradle 8.7 and AGP 8.5.2.
- Executes `flutter build apk --release`.
- Generates the optimized APK at:
  `frontend/build/app/outputs/flutter-apk/app-release.apk`

---

## 🌐 Public Deployment Guide

### A. Backend Deployment (Render)
1. Fork or push this repository to GitHub.
2. Log into [Render](https://render.com) and click **New > Blueprint**.
3. Select your repository. Render will automatically detect [`render.yaml`](file:///d:/projects/saais/render.yaml).
4. Configure the environment variables in the Render dashboard:
   - `SUPABASE_URL`: `https://cxhxgtmedbldfmofortm.supabase.co`
   - `SUPABASE_KEY`: Your Supabase anon or service key.
   - `JWT_SECRET`: A secure random secret key.
   - `GROQ_API_KEY`: Your Groq API key from [console.groq.com](https://console.groq.com).
   - `CORS_ORIGINS`: `*` (or your Vercel public URL).
5. Render builds the Docker container with Gunicorn memory optimization.

### B. Web Deployment (Vercel)
1. Log into [Vercel](https://vercel.com) and click **Add New > Project**.
2. Import this repository.
3. Keep the Root Directory as `.` (or set to `aiassistant`). Both configurations are fully supported via the synchronized `vercel.json` rewrite rules.
4. Click **Deploy**.
5. Your web app is instantly live with zero 404 errors!
