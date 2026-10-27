import os
import sys
import time
import json
import uuid
import datetime
from functools import wraps
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import jwt

# ── Local imports ─────────────────────────────────────────────────────────────
from db import DatabaseManager
from pipeline.extractor import process_document, prepare_chunks_for_storage
from pipeline.retriever import PrecisionRetriever
from pipeline.generator import (
    generate_exam_answer,
    generate_flashcards_from_chunks,
    generate_quiz_from_chunks,
    detect_keywords,
    get_groq_client
)

# ── App configuration ─────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)

SECRET_KEY = os.environ.get("JWT_SECRET", "exam_mate_academic_secret_key_2026")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXTENSIONS = {"pdf", "pptx", "ppt", "docx", "txt", "md"}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Auth & Helper Middleware ──────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def make_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            request.user_id = payload["sub"]
            request.user_email = payload["email"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

# ── 1. Authentication Endpoints ───────────────────────────────────────────────

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    existing = DatabaseManager.get_user_by_email(email)
    if existing:
        return jsonify({"error": "Email is already registered"}), 409

    user = DatabaseManager.create_user(name, email, password)
    if not user:
        return jsonify({"error": "Failed to create user account"}), 500

    token = make_token(user["id"], email)
    return jsonify({
        "message": "Account created successfully",
        "token": token,
        "user": user
    }), 201

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = DatabaseManager.get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    token = make_token(user["id"], email)
    DatabaseManager.update_streak(user["id"])

    return jsonify({
        "message": "Login successful",
        "token": token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "study_streak": user.get("study_streak", 1)
        }
    })

# ── 2. Profile & Dashboard ────────────────────────────────────────────────────

@app.route("/api/profile", methods=["GET"])
@token_required
def get_profile():
    user = DatabaseManager.get_user_by_id(request.user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    analytics = DatabaseManager.get_analytics(request.user_id)
    return jsonify({
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "university": user.get("university", "Academic Institution"),
        "study_streak": analytics["study_streak"],
        "total_documents": analytics["total_documents"],
        "total_questions": analytics["total_questions"],
        "total_focus_hours": analytics["total_focus_hours"],
        "average_quiz_score": analytics["average_quiz_score"],
        "created_at": user.get("created_at")
    })

@app.route("/api/dashboard", methods=["GET"])
@token_required
def get_dashboard():
    user = DatabaseManager.get_user_by_id(request.user_id)
    analytics = DatabaseManager.get_analytics(request.user_id)
    recent_docs = DatabaseManager.get_documents_by_user(request.user_id)[:4]
    recent_q = DatabaseManager.get_questions_by_user(request.user_id)[:4]
    upcoming_exams = DatabaseManager.get_exams(request.user_id)[:3]
    pending_tasks = [t for t in DatabaseManager.get_tasks(request.user_id) if not t.get("is_completed")][:5]

    return jsonify({
        "user_name": user["name"] if user else "Student",
        "study_streak": analytics["study_streak"],
        "analytics": analytics,
        "recent_documents": recent_docs,
        "recent_questions": recent_q,
        "upcoming_exams": upcoming_exams,
        "pending_tasks": pending_tasks
    })

# ── 3. Precision Document Upload & Extraction ─────────────────────────────────

@app.route("/api/upload", methods=["POST"])
@token_required
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded in multipart request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    safe_name = secure_filename(file.filename)
    unique_name = f"{request.user_id[:8]}_{int(time.time())}_{safe_name}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
    file.save(filepath)

    doc_id = str(uuid.uuid4())
    file_size = os.path.getsize(filepath)

    try:
        # Run precision extraction pipeline
        ext_result = process_document(filepath)
        chunks = prepare_chunks_for_storage(doc_id, request.user_id, ext_result["blocks"])

        # Create quick summary from first blocks
        first_few = " ".join([b["chunk_text"] for b in ext_result["blocks"][:2]])
        summary = first_few[:250] + "..." if len(first_few) > 250 else first_few

        # Save document metadata
        doc_record = {
            "id": doc_id,
            "user_id": request.user_id,
            "filename": safe_name,
            "stored_path": filepath,
            "file_type": ext_result["file_type"],
            "file_size_bytes": file_size,
            "page_count": ext_result["page_count"],
            "processed_pages": ext_result["processed_pages"],
            "ocr_used": ext_result["ocr_used"],
            "extraction_method": ext_result["extraction_method"],
            "confidence_score": ext_result["confidence_score"],
            "warnings": ext_result["warnings"],
            "summary": summary,
            "status": "completed" if ext_result["confidence_score"] >= 20.0 else "warning"
        }
        DatabaseManager.save_document(doc_record)
        DatabaseManager.save_document_chunks(chunks)

        return jsonify({
            "message": "Document uploaded and extracted successfully",
            "document": doc_record,
            "chunks_count": len(chunks)
        }), 201

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": f"Extraction failed: {str(e)}"
        }), 500

@app.route("/api/documents", methods=["GET"])
@token_required
def list_documents():
    docs = DatabaseManager.get_documents_by_user(request.user_id)
    return jsonify({"documents": docs})

@app.route("/api/documents/<doc_id>", methods=["GET"])
@token_required
def get_document(doc_id):
    doc = DatabaseManager.get_document_by_id(doc_id, request.user_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    chunks = DatabaseManager.get_document_chunks(doc_id, request.user_id)
    doc["chunks"] = chunks
    return jsonify(doc)

@app.route("/api/documents/<doc_id>", methods=["DELETE"])
@token_required
def delete_document(doc_id):
    success = DatabaseManager.delete_document(doc_id, request.user_id)
    if not success:
        return jsonify({"error": "Document not found or permission denied"}), 404
    return jsonify({"message": "Document and all associated chunks deleted successfully"})

# ── 4. Grounded AI Tutor & Exam Answers ───────────────────────────────────────

@app.route("/api/ask", methods=["POST"])
@token_required
def ask_ai():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    doc_id = data.get("document_id")
    mode = data.get("mode", "detailed")
    marks = int(data.get("marks", 5))

    if not question:
        return jsonify({"error": "Question is required"}), 400

    # Retrieve grounded context with evidence sufficiency check
    retrieval = PrecisionRetriever.retrieve(query=question, user_id=request.user_id, document_id=doc_id)
    
    # Generate structured, verifiable answer
    result = generate_exam_answer(question, retrieval, mode=mode, marks=marks)
    keywords = detect_keywords(result["answer_text"])

    # Persist in question history
    q_data = {
        "user_id": request.user_id,
        "document_id": doc_id,
        "question": question,
        "mode": mode,
        "marks": marks,
        "answer_text": result["answer_text"],
        "structured_answer": result["structured_answer"],
        "citations": result["citations"],
        "is_grounded": result["is_grounded"],
        "confidence": result["confidence"]
    }
    q_id = DatabaseManager.save_question(q_data)
    DatabaseManager.update_streak(request.user_id)

    return jsonify({
        "id": q_id,
        "question": question,
        "answer_text": result["answer_text"],
        "structured_answer": result["structured_answer"],
        "citations": result["citations"],
        "is_grounded": result["is_grounded"],
        "confidence": result["confidence"],
        "keywords": keywords
    })

@app.route("/api/history", methods=["GET"])
@token_required
def get_history():
    q_filter = request.args.get("q", "").strip()
    history = DatabaseManager.get_questions_by_user(request.user_id, q_filter)
    return jsonify({"history": history})

# ── 5. Flashcards & Spaced Repetition ─────────────────────────────────────────

@app.route("/api/flashcards/decks", methods=["GET"])
@token_required
def get_decks():
    decks = DatabaseManager.get_decks(request.user_id)
    return jsonify({"decks": decks})

@app.route("/api/flashcards/decks", methods=["POST"])
@token_required
def create_deck():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    desc = data.get("description", "")
    doc_id = data.get("document_id")

    if not title:
        return jsonify({"error": "Deck title is required"}), 400

    deck_id = DatabaseManager.create_deck(request.user_id, title, desc, doc_id)
    return jsonify({"id": deck_id, "title": title, "message": "Deck created successfully"}), 201

@app.route("/api/flashcards/decks/<deck_id>/cards", methods=["GET"])
@token_required
def get_deck_cards(deck_id):
    cards = DatabaseManager.get_cards_for_deck(deck_id, request.user_id)
    return jsonify({"cards": cards})

@app.route("/api/flashcards/generate", methods=["POST"])
@token_required
def generate_flashcards():
    data = request.get_json(silent=True) or {}
    doc_id = data.get("document_id")
    deck_title = (data.get("deck_title") or "").strip()
    count = int(data.get("count", 5))

    if not doc_id:
        return jsonify({"error": "document_id is required"}), 400

    chunks = DatabaseManager.get_document_chunks(doc_id, request.user_id)
    if not chunks:
        return jsonify({"error": "No extracted text found for this document"}), 404

    generated = generate_flashcards_from_chunks(chunks, count=count)
    if not generated:
        return jsonify({"error": "Could not extract concepts to form flashcards"}), 400

    # Auto-create deck if requested or use default
    if not deck_title:
        doc = DatabaseManager.get_document_by_id(doc_id, request.user_id)
        deck_title = f"{doc['filename']} Deck" if doc else "Document Flashcards"

    deck_id = DatabaseManager.create_deck(request.user_id, deck_title, f"Generated from document", doc_id)
    for c in generated:
        DatabaseManager.add_card(
            deck_id=deck_id,
            user_id=request.user_id,
            front=c["front"],
            back=c["back"],
            document_id=doc_id,
            source_page=c.get("source_page"),
            source_snippet=c.get("source_snippet")
        )

    cards = DatabaseManager.get_cards_for_deck(deck_id, request.user_id)
    return jsonify({
        "message": f"Generated {len(cards)} cards in deck '{deck_title}'",
        "deck_id": deck_id,
        "cards": cards
    }), 201

@app.route("/api/flashcards/review", methods=["POST"])
@token_required
def review_flashcard():
    data = request.get_json(silent=True) or {}
    card_id = data.get("card_id")
    rating = data.get("rating")  # Again, Hard, Good, Easy

    if not card_id or not rating:
        return jsonify({"error": "card_id and rating are required"}), 400

    res = DatabaseManager.review_card(card_id, request.user_id, rating)
    if "error" in res:
        return jsonify(res), 404

    DatabaseManager.update_streak(request.user_id)
    return jsonify(res)

@app.route("/api/flashcards/decks/<deck_id>", methods=["DELETE"])
@token_required
def delete_deck(deck_id):
    success = DatabaseManager.delete_deck(deck_id, request.user_id)
    return jsonify({"message": "Deck deleted successfully"})

# ── 6. Quizzes & Self-Assessment ──────────────────────────────────────────────

@app.route("/api/quizzes", methods=["GET"])
@token_required
def get_quizzes():
    quizzes = DatabaseManager.get_quizzes(request.user_id)
    return jsonify({"quizzes": quizzes})

@app.route("/api/quizzes/<quiz_id>", methods=["GET"])
@token_required
def get_quiz_detail(quiz_id):
    quiz = DatabaseManager.get_quiz_detail(quiz_id, request.user_id)
    if not quiz:
        return jsonify({"error": "Quiz not found"}), 404
    return jsonify(quiz)

@app.route("/api/quizzes/generate", methods=["POST"])
@token_required
def generate_quiz():
    data = request.get_json(silent=True) or {}
    doc_id = data.get("document_id")
    title = (data.get("title") or "").strip()
    count = int(data.get("count", 5))

    if not doc_id:
        return jsonify({"error": "document_id is required"}), 400

    chunks = DatabaseManager.get_document_chunks(doc_id, request.user_id)
    if not chunks:
        return jsonify({"error": "No extracted text found for this document"}), 404

    doc = DatabaseManager.get_document_by_id(doc_id, request.user_id)
    if not title:
        title = f"{doc['filename']} Quiz" if doc else "Exam Prep Quiz"

    questions_list = generate_quiz_from_chunks(chunks, count=count)
    if not questions_list:
        return jsonify({"error": "Could not generate questions from document content"}), 400

    quiz_id = DatabaseManager.create_quiz(
        user_id=request.user_id,
        title=title,
        subject=doc.get("file_type", "General") if doc else "General",
        document_id=doc_id,
        questions_list=questions_list
    )

    full_quiz = DatabaseManager.get_quiz_detail(quiz_id, request.user_id)
    return jsonify({
        "message": f"Generated quiz with {len(questions_list)} questions",
        "quiz": full_quiz
    }), 201

@app.route("/api/quizzes/<quiz_id>/submit", methods=["POST"])
@token_required
def submit_quiz(quiz_id):
    data = request.get_json(silent=True) or {}
    answers = data.get("answers", [])  # list of int indices

    result = DatabaseManager.submit_quiz_attempt(quiz_id, request.user_id, answers)
    if "error" in result:
        return jsonify(result), 404

    DatabaseManager.update_streak(request.user_id)
    return jsonify(result)

# ── 7. Study Planner, Exams & Tasks ───────────────────────────────────────────

@app.route("/api/exams", methods=["GET"])
@token_required
def list_exams():
    exams = DatabaseManager.get_exams(request.user_id)
    return jsonify({"exams": exams})

@app.route("/api/exams", methods=["POST"])
@token_required
def create_exam():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    subject = (data.get("subject") or "").strip()
    exam_date = data.get("exam_date")
    target_score = int(data.get("target_score", 90))
    syllabus = data.get("syllabus", "")

    if not title or not subject or not exam_date:
        return jsonify({"error": "Title, subject, and exam_date are required"}), 400

    exam_id = DatabaseManager.create_exam(
        user_id=request.user_id,
        title=title,
        subject=subject,
        exam_date=exam_date,
        target_score=target_score,
        syllabus=syllabus
    )
    return jsonify({"id": exam_id, "message": "Exam scheduled successfully"}), 201

@app.route("/api/exams/<exam_id>", methods=["DELETE"])
@token_required
def delete_exam(exam_id):
    DatabaseManager.delete_exam(exam_id, request.user_id)
    return jsonify({"message": "Exam deleted successfully"})

@app.route("/api/tasks", methods=["GET"])
@token_required
def list_tasks():
    tasks = DatabaseManager.get_tasks(request.user_id)
    return jsonify({"tasks": tasks})

@app.route("/api/tasks", methods=["POST"])
@token_required
def create_task():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    due_date = data.get("due_date")
    exam_id = data.get("exam_id")
    priority = data.get("priority", "medium")

    if not title:
        return jsonify({"error": "Task title is required"}), 400

    task_id = DatabaseManager.create_task(
        user_id=request.user_id,
        title=title,
        due_date=due_date,
        exam_id=exam_id,
        priority=priority
    )
    return jsonify({"id": task_id, "message": "Task created successfully"}), 201

@app.route("/api/tasks/<task_id>/toggle", methods=["POST"])
@token_required
def toggle_task(task_id):
    success = DatabaseManager.toggle_task(task_id, request.user_id)
    if not success:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({"message": "Task status updated"})

@app.route("/api/tasks/<task_id>", methods=["DELETE"])
@token_required
def delete_task(task_id):
    DatabaseManager.delete_task(task_id, request.user_id)
    return jsonify({"message": "Task deleted successfully"})

# ── 8. Focus Sessions & Analytics ─────────────────────────────────────────────

@app.route("/api/focus", methods=["POST"])
@token_required
def log_focus():
    data = request.get_json(silent=True) or {}
    duration = int(data.get("duration_minutes", 25))
    subject = data.get("subject", "General Study")
    notes = data.get("notes", "")

    session_id = DatabaseManager.log_focus_session(request.user_id, duration, subject, notes)
    DatabaseManager.update_streak(request.user_id)
    return jsonify({"id": session_id, "message": f"Logged {duration} minutes of focus time!"}), 201

@app.route("/api/analytics", methods=["GET"])
@token_required
def get_analytics():
    analytics = DatabaseManager.get_analytics(request.user_id)
    return jsonify(analytics)

# ── 9. System Health & Diagnostics ────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health_check():
    groq_active = get_groq_client() is not None
    return jsonify({
        "status": "healthy",
        "app": "Exam Mate AI",
        "version": "2.0.0-precision",
        "database": "sqlite_relational_active",
        "ai_engine": "groq_active" if groq_active else "local_grounded_active",
        "supported_formats": list(ALLOWED_EXTENSIONS)
    })

# ── Main Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Exam Mate AI Backend running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
