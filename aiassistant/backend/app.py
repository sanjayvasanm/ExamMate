import os
import time
import json
import datetime
import uuid
import tempfile
from functools import wraps
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from supabase import create_client, Client
from postgrest.exceptions import APIError
from storage import STORAGE_BUCKET, delete_document, download_document, upload_document

# ── Pipeline imports ──────────────────────────────────────────────────────────
from pipeline.extractor import extract_text_hybrid, chunk_content
from pipeline.retriever import retriever_instance, get_context
from pipeline.generator import generate_exam_answer, generate_quiz, generate_flashcards, detect_keywords, fix_mermaid_diagram

# ── App config ────────────────────────────────────────────────────────────────
app = Flask(__name__)

# Keep local development convenient, but fail closed in explicitly configured
# production environments when the deployed frontend origin is missing.
environment = os.environ.get("ENVIRONMENT", "development").lower()
cors_value = os.environ.get("CORS_ORIGINS", "").strip()
if environment == "production" and not cors_value:
    raise RuntimeError("CORS_ORIGINS must be set in production.")
cors_origins = (
    [origin.strip() for origin in cors_value.split(",") if origin.strip()]
    if cors_value
    else "*"
)
CORS(app, resources={r"/api/*": {"origins": cors_origins}}, supports_credentials=False)

SECRET_KEY = os.environ.get("JWT_SECRET")
if not SECRET_KEY:
    # Print clearly to stderr for cloud deployment logs
    import sys
    print("FATAL: JWT_SECRET environment variable is required for deployment.", file=sys.stderr)
    print("Please set JWT_SECRET in your Render/Cloud environment variables.", file=sys.stderr)
    sys.exit(1)
ALLOWED_EXTENSIONS = {"pdf", "pptx", "ppt", "docx", "txt", "png", "jpg", "jpeg"}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DOCUMENT_CHUNKS_TABLE = os.environ.get("DOCUMENT_CHUNKS_TABLE", "document_chunks")

if not SUPABASE_URL or not SUPABASE_KEY:
    import sys
    print("FATAL: SUPABASE_URL and SUPABASE_KEY environment variables are required.", file=sys.stderr)
    sys.exit(1)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    # Simple ping to verify connection
    supabase.table("users").select("id").limit(1).execute()
    print(f"[Supabase] Connected and verified: {SUPABASE_URL}")
except APIError as e:
    print(f"[Supabase] Connection error (APIError): {e}")
    if "521" in str(e):
        print("CRITICAL: Supabase project seems to be PAUSED or DOWN (521). Please check the Supabase dashboard.")
except Exception as exc:
    print(f"[Supabase] Connection failed: {exc}")


# ── Global Error Handlers ─────────────────────────────────────────────────────
@app.errorhandler(APIError)
def handle_supabase_error(e):
    """
    Handle Supabase/PostgREST API errors globally.
    Specifically detects 521 (Project Down/Paused) and returns a friendly message.
    """
    import traceback
    traceback.print_exc()
    
    error_msg = str(e)
    # 521 is the code for "Web server is down" from Cloudflare/Supabase
    if "521" in error_msg or "JSON could not be generated" in error_msg:
        return jsonify({
            "status": "error",
            "error": "Database Service Unavailable",
            "message": "The database project is currently paused or down. Please go to the Supabase Dashboard and 'Restore' your project.",
            "hint": "Check if your Supabase project is active and not paused due to inactivity."
        }), 503
    
    return jsonify({
        "status": "error",
        "error": "Database Error",
        "message": "An error occurred while communicating with the database.",
    }), 500


# ── Helpers ───────────────────────────────────────────────────────────────────
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _storage_path(user_id: str, document_id: str, filename: str) -> str:
    return f"{user_id}/{document_id}/{filename}"


def _load_persistent_context(user_id: str, document_id: str | None = None) -> None:
    query = supabase.table(DOCUMENT_CHUNKS_TABLE).select("document_id,chunk_index,content").eq("user_id", user_id)
    if document_id:
        query = query.eq("document_id", document_id)
    rows = query.order("document_id").order("chunk_index").execute().data or []
    if document_id:
        retriever_instance.sync(
            [{"text": row["content"]} for row in rows if row.get("content")],
            user_id=user_id,
            document_id=document_id,
        )
    else:
        retriever_instance.sync_records(
            [row for row in rows if row.get("content")],
            user_id=user_id,
        )


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
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        request.user_id = payload["sub"]
        request.user_email = payload["email"]
        return f(*args, **kwargs)
    return decorated


def update_user_streak(user_id):
    """
    Increments or resets user study streak based on last activity.
    Logic:
    - Today already active: No change to streak count, but update last_active
    - Last active yesterday: Streak + 1
    - Last active before yesterday: Streak = 1
    """
    try:
        res = supabase.table("users").select("study_streak", "last_active").eq("id", user_id).execute()
        if not res.data:
            return
        
        user = res.data[0]
        streak = user.get("study_streak", 0)
        last_active_str = user.get("last_active")
        
        now = datetime.datetime.utcnow()
        today = now.date()
        
        if not last_active_str:
            new_streak = 1
        else:
            # Parse ISO timestamp from Supabase
            try:
                # Handle both 'Z' and offset formats
                ts = last_active_str.replace("Z", "+00:00")
                last_active = datetime.datetime.fromisoformat(ts)
                # Ensure it's UTC-comparable
                if last_active.tzinfo:
                    last_active = last_active.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            except Exception:
                last_active = now - datetime.timedelta(days=2) # Default to break streak
                
            last_active_date = last_active.date()
            diff = (today - last_active_date).days
            
            if diff <= 0:
                new_streak = max(streak, 1) # Already active today (or future clock skew)
            elif diff == 1:
                new_streak = streak + 1 # Consecutive day
            else:
                new_streak = 1 # Streak broken
                
        supabase.table("users").update({
            "study_streak": new_streak,
            "last_active": now.isoformat()
        }).eq("id", user_id).execute()
        print(f"[Streak] Updated for {user_id}: {streak} -> {new_streak}")
        
    except Exception as e:
        print(f"[Streak Warning] Failed to update streak for {user_id}: {e}")


def serialize_doc(doc: dict) -> dict:
    """Supabase returns JSON-serializable data by default."""
    return doc


# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({"error": "name, email and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    # Check if exists
    existing = supabase.table("users").select("id").eq("email", email).execute()
    if existing.data:
        return jsonify({"error": "Email already registered"}), 409

    user_doc = {
        "name": name,
        "email": email,
        "password": generate_password_hash(password),
        "created_at": datetime.datetime.utcnow().isoformat(),
        "study_streak": 0,
        "total_questions": 0,
        "documents_uploaded": 0,
        "last_active": datetime.datetime.utcnow().isoformat(),
    }
    result = supabase.table("users").insert(user_doc).execute()
    if not result.data:
        # Check if error exists in response if the SDK version returns it
        err = getattr(result, 'error', None)
        print(f"[Supabase Error] Registration failed: {err}")
        return jsonify({"error": "Account creation failed. Please try again."}), 500
        
    user_id = result.data[0]["id"]
    token = make_token(str(user_id), email)

    return jsonify({
        "message": "Account created successfully",
        "token": token,
        "user": {"id": str(user_id), "name": name, "email": email},
    }), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user_res = supabase.table("users").select("*").eq("email", email).execute()
    user = user_res.data[0] if user_res.data else None
    
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    user_id = str(user["id"])
    token = make_token(user_id, email)

    # Update last_active and streak
    update_user_streak(user_id)

    return jsonify({
        "message": "Login successful",
        "token": token,
        "user": {"id": user_id, "name": user.get("name", ""), "email": email},
    })


# ── Profile ───────────────────────────────────────────────────────────────────
@app.route("/api/profile", methods=["GET"])
@token_required
def get_profile():
    user_res = supabase.table("users").select("*").eq("id", request.user_id).execute()
    user = user_res.data[0] if user_res.data else None
    if not user:
        return jsonify({"error": "User not found"}), 404

    q_res = supabase.table("questions").select("id", count="exact").eq("user_id", request.user_id).execute()
    q_count = q_res.count if q_res.count is not None else 0
    
    d_res = supabase.table("documents").select("id", count="exact").eq("user_id", request.user_id).execute()
    d_count = d_res.count if d_res.count is not None else 0

    return jsonify({
        "id": str(user["id"]),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "study_streak": user.get("study_streak", 0),
        "total_questions": q_count,
        "documents_uploaded": d_count,
        "avg_score": user.get("avg_score", 0),
        "created_at": user.get("created_at"),
    })


@app.route("/api/profile/update", methods=["PUT"])
@token_required
def update_profile():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    supabase.table("users").update({"name": name}).eq("id", request.user_id).execute()
    return jsonify({"message": "Profile updated"})


# ── Upload ────────────────────────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
@token_required
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": f"File type not allowed. Supported: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    filename = secure_filename(file.filename)
    doc_id = str(uuid.uuid4())
    ext = filename.rsplit(".", 1)[1].lower()
    storage_path = _storage_path(request.user_id, doc_id, filename)
    temp_path = None
    chunks = []
    file_size_bytes = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as temp_file:
            file.save(temp_file)
            temp_path = temp_file.name
        file_size_bytes = os.path.getsize(temp_path)

        with open(temp_path, "rb") as stored_file:
            upload_document(
                supabase.storage,
                storage_path,
                stored_file,
                file.mimetype or "application/octet-stream",
            )
        print(f"[Storage] Uploaded {filename} to {STORAGE_BUCKET}/{storage_path}")
        text_blocks = extract_text_hybrid(temp_path)
        chunks = chunk_content(text_blocks)
    except Exception as exc:
        if storage_path:
            try:
                delete_document(supabase.storage, storage_path)
            except Exception as cleanup_error:
                print(f"[Storage Warning] Cleanup failed for {storage_path}: {cleanup_error}")
        print(f"[Upload Error] {filename}: {exc}")
        return jsonify({"error": "Document upload or processing failed"}), 502
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError as cleanup_error:
                print(f"[Upload Warning] Temporary file cleanup failed: {cleanup_error}")

    chunks_processed = len(chunks)
    chunk_records = [
        {
            "document_id": doc_id,
            "user_id": request.user_id,
            "chunk_index": index,
            "content": chunk.get("text", chunk.get("chunk", "")) if isinstance(chunk, dict) else str(chunk),
        }
        for index, chunk in enumerate(chunks)
        if (chunk.get("text", chunk.get("chunk", "")) if isinstance(chunk, dict) else str(chunk)).strip()
    ]
    doc_record = {
        "id": doc_id,
        "user_id": request.user_id,
        "filename": filename,
        "stored_path": storage_path,
        "storage_bucket": STORAGE_BUCKET,
        "storage_path": storage_path,
        "file_type": ext.upper(),
        "file_size_mb": round(file_size_bytes / (1024 * 1024), 2) if file_size_bytes is not None else None,
        "chunks_processed": chunks_processed,
        "uploaded_at": datetime.datetime.utcnow().isoformat(),
        "status": "processed" if chunks_processed > 0 else "uploaded",
    }
    try:
        supabase.table("documents").insert(doc_record).execute()
        if chunk_records:
            supabase.table(DOCUMENT_CHUNKS_TABLE).insert(chunk_records).execute()
            retriever_instance.sync(
                [{"text": row["content"]} for row in chunk_records],
                user_id=request.user_id,
                document_id=doc_id,
            )
    except Exception:
        try:
            delete_document(supabase.storage, storage_path)
        except Exception as cleanup_error:
            print(f"[Storage Warning] Database rollback cleanup failed: {cleanup_error}")
        try:
            supabase.table(DOCUMENT_CHUNKS_TABLE).delete().eq("document_id", doc_id).eq("user_id", request.user_id).execute()
            supabase.table("documents").delete().eq("id", doc_id).eq("user_id", request.user_id).execute()
        except Exception as cleanup_error:
            print(f"[Database Warning] Upload rollback cleanup failed: {cleanup_error}")
        raise

    # Increment user's document count atomically via Supabase RPC
    # NOTE: You must create this function in Supabase SQL Editor (see summary)
    try:
        supabase.rpc("increment_documents_uploaded", {"row_id": request.user_id}).execute()
    except Exception as e:
        print(f"[Supabase Warning] Atomic increment failed (ensure RPC exists): {e}")

    return jsonify({
        "message": "File uploaded and processed successfully",
        "document_id": doc_id,
        "filename": filename,
        "chunks_processed": chunks_processed,
        "status": doc_record["status"],
    })


@app.route("/api/documents/<document_id>", methods=["DELETE"])
@token_required
def delete_document_route(document_id):
    try:
        uuid.UUID(str(document_id))
    except ValueError:
        return jsonify({"error": "Invalid document ID"}), 400

    result = (
        supabase.table("documents")
        .select("id,storage_bucket,storage_path,stored_path")
        .eq("id", document_id)
        .eq("user_id", request.user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return jsonify({"error": "Document not found"}), 404

    document = result.data[0]
    storage_path = document.get("storage_path") or document.get("stored_path")
    storage_bucket = document.get("storage_bucket") or STORAGE_BUCKET
    if storage_path:
        try:
            delete_document(supabase.storage, storage_path, bucket=storage_bucket)
        except Exception as exc:
            print(f"[Storage Error] Delete failed for {storage_path}: {exc}")
            return jsonify({"error": "Document storage deletion failed"}), 502

    deleted = (
        supabase.table("documents")
        .delete()
        .eq("id", document_id)
        .eq("user_id", request.user_id)
        .execute()
    )
    if not deleted.data:
        return jsonify({"error": "Document could not be deleted"}), 500
    retriever_instance.sync([], user_id=request.user_id, document_id=document_id)
    return jsonify({"message": "Document deleted"})


@app.route("/api/documents", methods=["GET"])
@token_required
def get_documents():
    res = supabase.table("documents").select("*").eq("user_id", request.user_id).order("uploaded_at", desc=True).limit(20).execute()
    docs = res.data or []
    # Remove sensitive path and ensure JSON serializable
    for d in docs:
        d.pop("stored_path", None)
        d.pop("storage_path", None)
        d.pop("storage_bucket", None)
        d["doc_id"] = d.get("id")
        # SUPABASE returns ISO strings, no need to call .isoformat() manually

    return jsonify({"documents": docs})


# ── Ask / Q&A ──────────────────────────────────────────────────────────────────
@app.route("/api/ask", methods=["POST"])
@token_required
def ask_question():
    try:
        data = request.get_json(silent=True) or {}
        question = (data.get("question") or "").strip()
        mode = data.get("mode", "detailed")
        doc_id = data.get("document_id")
        if doc_id:
            try:
                uuid.UUID(str(doc_id))
                owned_doc = (supabase.table("documents").select("id").eq("id", str(doc_id)).eq("user_id", request.user_id).limit(1).execute())
                if not owned_doc.data:
                    return jsonify({"error": "Document not found"}), 404
            except ValueError:
                print(f"[API Warning] Invalid document_id '{doc_id}', treating as None.")
                doc_id = None
        
        marks = data.get("marks", 5)

        if not question:
            return jsonify({"error": "Question is required"}), 400

        print(f"[API] Asking: {question} (Marks: {marks}, Mode: {mode})")
        _load_persistent_context(request.user_id, doc_id)
        context = get_context(question, user_id=request.user_id, document_id=doc_id)
        answer, diagrams = generate_exam_answer(question, context, mode, marks)
        
        all_text = answer.get("explanation", "") + " ".join(answer.get("points", []))
        keywords = detect_keywords(all_text)

        # Persist question to Supabase
        q_record = {
            "user_id": request.user_id,
            "document_id": doc_id,
            "question": question,
            "mode": mode,
            "marks": marks,
            "answer": answer,
            "diagrams": diagrams,
            "keywords": keywords,
            "asked_at": datetime.datetime.utcnow().isoformat(),
            "subject": data.get("subject", "General"),
        }
        res = supabase.table("questions").insert(q_record).execute()

        # Increment user question counter and streak
        try:
            supabase.rpc("increment_total_questions", {"row_id": request.user_id}).execute()
            update_user_streak(request.user_id)
        except Exception as e:
            print(f"[Supabase Warning] Post-ask updates failed: {e}")

        return jsonify({
            "status": "success",
            "question_id": str(res.data[0]["id"]) if res.data else "unknown",
            "question": question,
            "answer": answer,
            "diagrams": diagrams,
            "keywords": keywords
        })
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[API Error] Exception in /api/ask: {error_msg}")
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "error": "Internal AI Processing Error. Please check backend logs or try again."
        }), 500




# ── Mermaid Self-Correction ────────────────────────────────────────────────────
# Quiz generation and persisted attempts.
@app.route("/api/quizzes/generate", methods=["POST"])
@token_required
def generate_quiz_route():
    data=request.get_json(silent=True) or {}; document_id=data.get("document_id")
    try:
        if document_id:
            uuid.UUID(str(document_id)); owned=supabase.table("documents").select("id").eq("id",str(document_id)).eq("user_id",request.user_id).limit(1).execute()
            if not owned.data:return jsonify({"error":"Document not found"}),404
        count=max(3,min(int(data.get("count",5)),10))
    except (TypeError,ValueError):return jsonify({"error":"Invalid quiz count or document_id"}),400
    topic=(data.get("topic") or "General revision").strip()[:160]
    try:
        _load_persistent_context(request.user_id, document_id)
        quiz=generate_quiz(topic,get_context(topic,user_id=request.user_id,document_id=document_id),count)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    session=supabase.table("quiz_sessions").insert({"user_id":request.user_id,"document_id":document_id or None,"quiz":quiz}).execute()
    session_id=str(session.data[0]["id"]) if session.data else None
    return jsonify({"quiz":quiz,"document_id":document_id,"session_id":session_id})

@app.route("/api/quizzes/attempt", methods=["POST"])
@token_required
def submit_quiz_attempt():
    data=request.get_json(silent=True) or {}; answers=data.get("answers") or []; session_id=data.get("session_id")
    if not session_id or not isinstance(answers,list):return jsonify({"error":"A quiz session and answers are required"}),400
    try: uuid.UUID(str(session_id))
    except ValueError:return jsonify({"error":"Invalid quiz session"}),400
    session=supabase.table("quiz_sessions").select("quiz,document_id").eq("id",session_id).eq("user_id",request.user_id).limit(1).execute()
    if not session.data:return jsonify({"error":"Quiz session not found"}),404
    quiz=session.data[0]["quiz"]; questions=quiz.get("questions") or []
    if not questions or len(answers)!=len(questions):return jsonify({"error":"A complete quiz and one answer per question are required"}),400
    score=sum(1 for q,a in zip(questions,answers) if str(a).upper()==str(q.get("answer","")).upper())
    record={"user_id":request.user_id,"quiz":quiz,"answers":answers,"score":score,"total":len(questions),"document_id":session.data[0].get("document_id")}
    result=supabase.table("quiz_attempts").insert(record).execute()
    return jsonify({"attempt":result.data[0] if result.data else record,"score":score,"total":len(questions)}),201

@app.route("/api/quizzes/attempts", methods=["GET"])
@token_required
def list_quiz_attempts():
    result=supabase.table("quiz_attempts").select("id,score,total,created_at,document_id,quiz,answers").eq("user_id",request.user_id).order("created_at",desc=True).limit(20).execute()
    return jsonify({"attempts":result.data or []})

@app.route("/api/quizzes/attempts/<attempt_id>/retry-wrong", methods=["POST"])
@token_required
def retry_wrong_questions(attempt_id):
    try:
        uuid.UUID(str(attempt_id))
    except ValueError:
        return jsonify({"error": "Invalid quiz attempt"}), 400
    result = (
        supabase.table("quiz_attempts")
        .select("quiz,answers,document_id")
        .eq("id", attempt_id)
        .eq("user_id", request.user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return jsonify({"error": "Quiz attempt not found"}), 404
    attempt = result.data[0]
    questions = attempt.get("quiz", {}).get("questions") or []
    answers = attempt.get("answers") or []
    wrong = [
        question for question, answer in zip(questions, answers)
        if str(answer).upper() != str(question.get("answer", "")).upper()
    ]
    if not wrong:
        return jsonify({"error": "This attempt has no incorrect answers to retry"}), 400
    quiz = {"title": "Retry incorrect answers", "questions": wrong}
    session = supabase.table("quiz_sessions").insert({
        "user_id": request.user_id,
        "document_id": attempt.get("document_id"),
        "quiz": quiz,
    }).execute()
    return jsonify({
        "quiz": quiz,
        "document_id": attempt.get("document_id"),
        "session_id": str(session.data[0]["id"]) if session.data else None,
    })


@app.route("/api/analytics", methods=["GET"])
@token_required
def get_analytics():
    attempts = supabase.table("quiz_attempts").select("score,total,quiz,created_at").eq("user_id", request.user_id).order("created_at", desc=True).limit(100).execute().data or []
    total_questions = sum(int(attempt.get("total") or 0) for attempt in attempts)
    total_score = sum(int(attempt.get("score") or 0) for attempt in attempts)
    topic_stats = {}
    for attempt in attempts:
        quiz = attempt.get("quiz") or {}
        topic = str(quiz.get("title") or "General revision")
        stat = topic_stats.setdefault(topic, {"topic": topic, "score": 0, "total": 0, "attempts": 0})
        stat["score"] += int(attempt.get("score") or 0)
        stat["total"] += int(attempt.get("total") or 0)
        stat["attempts"] += 1
    topics = [
        {**stat, "percentage": round(stat["score"] / stat["total"] * 100) if stat["total"] else 0}
        for stat in topic_stats.values()
    ]
    topics.sort(key=lambda item: (item["percentage"], -item["attempts"]))
    return jsonify({
        "attempts": len(attempts),
        "average_score": round(total_score / total_questions * 100) if total_questions else None,
        "weak_topics": topics[:5],
        "has_enough_data": len(attempts) >= 2,
    })


@app.route("/api/flashcards", methods=["GET", "POST"])
@token_required
def flashcards():
    if request.method == "GET":
        result = (
            supabase.table("flashcards")
            .select("*")
            .eq("user_id", request.user_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        return jsonify({"cards": result.data or []})

    data = request.get_json(silent=True) or {}
    document_id = data.get("document_id")
    topic = (data.get("topic") or "General revision").strip()[:160]
    try:
        count = max(3, min(int(data.get("count", 10)), 20))
        if document_id:
            uuid.UUID(str(document_id))
            owned = supabase.table("documents").select("id").eq("id", str(document_id)).eq("user_id", request.user_id).limit(1).execute()
            if not owned.data:
                return jsonify({"error": "Document not found"}), 404
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid flashcard count or document ID"}), 400

    _load_persistent_context(request.user_id, document_id)
    context = get_context(topic, user_id=request.user_id, document_id=document_id)
    try:
        generated = generate_flashcards(topic, context, count)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    records = [{
        "user_id": request.user_id,
        "document_id": document_id or None,
        "front": card["front"],
        "back": card["back"],
        "topic": topic,
        "next_review_at": datetime.datetime.utcnow().isoformat(),
        "interval_days": 0,
        "ease_factor": 2.5,
    } for card in generated["cards"]]
    result = supabase.table("flashcards").insert(records).execute()
    return jsonify({"cards": result.data or records}), 201


@app.route("/api/flashcards/<card_id>/review", methods=["POST"])
@token_required
def review_flashcard(card_id):
    try:
        uuid.UUID(str(card_id))
    except ValueError:
        return jsonify({"error": "Invalid flashcard ID"}), 400
    rating = (request.get_json(silent=True) or {}).get("rating")
    if rating not in {"again", "hard", "good", "easy"}:
        return jsonify({"error": "Rating must be again, hard, good, or easy"}), 400
    card_result = supabase.table("flashcards").select("interval_days,ease_factor").eq("id", card_id).eq("user_id", request.user_id).limit(1).execute()
    if not card_result.data:
        return jsonify({"error": "Flashcard not found"}), 404
    card = card_result.data[0]
    interval = int(card.get("interval_days") or 0)
    ease = float(card.get("ease_factor") or 2.5)
    if rating == "again":
        interval = 0
        ease = max(1.3, ease - 0.2)
    else:
        multipliers = {"hard": 1.2, "good": ease, "easy": ease + 0.3}
        interval = max(1, round(max(interval, 1) * multipliers[rating]))
        ease = max(1.3, ease + (0.15 if rating == "easy" else -0.05 if rating == "hard" else 0))
    next_review = datetime.datetime.utcnow() + datetime.timedelta(days=interval)
    updated = supabase.table("flashcards").update({
        "interval_days": interval,
        "ease_factor": ease,
        "last_rating": rating,
        "next_review_at": next_review.isoformat(),
        "reviewed_at": datetime.datetime.utcnow().isoformat(),
    }).eq("id", card_id).eq("user_id", request.user_id).execute()
    if not updated.data:
        return jsonify({"error": "Flashcard could not be updated"}), 500
    return jsonify({"card": updated.data[0]})


@app.route("/api/focus-sessions", methods=["GET", "POST"])
@token_required
def focus_sessions():
    if request.method == "GET":
        result = (
            supabase.table("focus_sessions")
            .select("id,subject,task_id,work_minutes,completed_at")
            .eq("user_id", request.user_id)
            .order("completed_at", desc=True)
            .limit(50)
            .execute()
        )
        return jsonify({"sessions": result.data or []})
    data = request.get_json(silent=True) or {}
    try:
        work_minutes = max(1, min(int(data.get("work_minutes", 25)), 120))
    except (TypeError, ValueError):
        return jsonify({"error": "Work duration must be a valid number"}), 400
    result = supabase.table("focus_sessions").insert({
        "user_id": request.user_id,
        "subject": (data.get("subject") or "").strip()[:80],
        "task_id": data.get("task_id") or None,
        "work_minutes": work_minutes,
        "completed_at": datetime.datetime.utcnow().isoformat(),
    }).execute()
    return jsonify({"session": result.data[0]}), 201


@app.route("/api/fix-diagram", methods=["POST"])
@token_required
def fix_diagram():
    """
    Accepts a broken Mermaid code + parse error and returns AI-corrected Mermaid syntax.
    The frontend calls this in an auto-retry loop (max 3 attempts).
    """
    try:
        data = request.get_json(silent=True) or {}
        broken_code = (data.get("code") or "").strip()
        error_message = (data.get("error") or "Syntax error").strip()
        diagram_type = (data.get("diagram_type") or "graph").strip()

        if not broken_code:
            return jsonify({"error": "code is required"}), 400

        fixed_code = fix_mermaid_diagram(broken_code, error_message, diagram_type)
        return jsonify({
            "status": "fixed",
            "code": fixed_code,
            "diagram_type": diagram_type,
        })
    except Exception as exc:
        import traceback as tb
        print(f"[API Error] /api/fix-diagram: {exc}")
        tb.print_exc()
        return jsonify({"error": "Failed to fix diagram", "detail": str(exc)}), 500


# ── History ───────────────────────────────────────────────────────────────────

@app.route("/api/history", methods=["GET"])
@token_required
def get_history():
    search = request.args.get("q", "").strip()
    query = supabase.table("questions").select("*").eq("user_id", request.user_id)
    if search:
        query = query.ilike("question", f"%{search}%")

    res = query.order("asked_at", desc=True).limit(50).execute()
    items = res.data or []
    results = []
    for item in items:
        asked_at = item.get("asked_at")
        # Parse ISO string back to datetime object
        if isinstance(asked_at, str):
            try:
                asked_at = datetime.datetime.fromisoformat(asked_at.replace("Z", "+00:00"))
            except ValueError:
                asked_at = datetime.datetime.now(datetime.timezone.utc)
        
        # Ensure asked_at is timezone-aware for comparison
        if asked_at.tzinfo is None:
            asked_at = asked_at.replace(tzinfo=datetime.timezone.utc)
            
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = now - asked_at
        if diff.days == 0:
            time_label = f"{int(diff.seconds/3600)}h ago" if diff.seconds >= 3600 else "Just now"
        elif diff.days == 1:
            time_label = "Yesterday"
        else:
            time_label = asked_at.strftime("%d %b %Y")

        results.append({
            "id": str(item["id"]),
            "question": item.get("question", ""),
            "subject": item.get("subject", "General"),
            "mode": item.get("mode", "detailed"),
            "marks": item.get("marks", 5),
            "time_label": time_label,
            "asked_at": item.get("asked_at"),
        })

    return jsonify({"history": results})


@app.route("/api/history/<question_id>", methods=["GET"])
@token_required
def get_question_detail(question_id):
    try:
        res = supabase.table("questions").select("*").eq("id", question_id).eq("user_id", request.user_id).execute()
        item = res.data[0] if res.data else None
    except Exception:
        return jsonify({"error": "Invalid question ID"}), 400

    if not item:
        return jsonify({"error": "Question not found"}), 404

    item["id"] = str(item["id"])
    return jsonify(item)


@app.route("/api/history/<question_id>", methods=["DELETE"])
@token_required
def delete_question(question_id):
    try:
        result = supabase.table("questions").delete().eq("id", question_id).eq("user_id", request.user_id).execute()
    except Exception:
        return jsonify({"error": "Invalid question ID"}), 400

    if not result.data:
        return jsonify({"error": "Question not found or already deleted"}), 404

    return jsonify({"message": "Deleted successfully"})


# ── Dashboard stats ───────────────────────────────────────────────────────────
@app.route("/api/dashboard", methods=["GET"])
@token_required
def get_dashboard():
    user_res = supabase.table("users").select("*").eq("id", request.user_id).execute()
    user = user_res.data[0] if user_res.data else None
    
    q_res = supabase.table("questions").select("id", count="exact").eq("user_id", request.user_id).execute()
    q_count = q_res.count if q_res.count is not None else 0
    
    d_res = supabase.table("documents").select("id", count="exact").eq("user_id", request.user_id).execute()
    d_count = d_res.count if d_res.count is not None else 0

    recent_docs_res = supabase.table("documents").select("*").eq("user_id", request.user_id).order("uploaded_at", desc=True).limit(3).execute()
    recent_docs = recent_docs_res.data or []
    for d in recent_docs:
        d.pop("stored_path", None)
        d.pop("storage_path", None)
        d.pop("storage_bucket", None)
        d["doc_id"] = d.get("id")

    recent_questions_res = supabase.table("questions").select("*").eq("user_id", request.user_id).order("asked_at", desc=True).limit(3).execute()
    recent_questions = recent_questions_res.data or []
    for q in recent_questions:
        q["id"] = str(q["id"])
    recent_plans, recent_attempts = [], []
    try:
        recent_plans_res = supabase.table("study_plans").select("id,title,subject,exam_date,completed").eq("user_id", request.user_id).order("exam_date").limit(3).execute()
        recent_plans = recent_plans_res.data or []
    except APIError:
        app.logger.warning("Dashboard planner summary unavailable", exc_info=True)
    try:
        recent_attempts_res = supabase.table("quiz_attempts").select("id,score,total,created_at,document_id").eq("user_id", request.user_id).order("created_at", desc=True).limit(3).execute()
        recent_attempts = recent_attempts_res.data or []
    except APIError:
        app.logger.warning("Dashboard quiz summary unavailable", exc_info=True)
    attempt_totals = supabase.table("quiz_attempts").select("score,total").eq("user_id", request.user_id).limit(100).execute().data or []
    attempted_questions = sum(int(attempt.get("total") or 0) for attempt in attempt_totals)
    earned_questions = sum(int(attempt.get("score") or 0) for attempt in attempt_totals)
    actual_avg_score = round(earned_questions / attempted_questions * 100) if attempted_questions else None

    return jsonify({
        "user_name": user.get("name", "") if user else "",
        "total_questions": q_count,
        "total_documents": d_count,
        "study_streak": user.get("study_streak", 0) if user else 0,
        "avg_score": actual_avg_score,
        "completed_quizzes": len(attempt_totals),
        "recent_documents": recent_docs,
        "recent_questions": recent_questions,
        "upcoming_plans": recent_plans,
        "recent_quiz_attempts": recent_attempts,
    })


# ── Study planner ────────────────────────────────────────────────────────────
@app.route("/api/plans", methods=["GET", "POST"])
@token_required
def study_plans():
    if request.method == "GET":
        result = (
            supabase.table("study_plans")
            .select("*")
            .eq("user_id", request.user_id)
            .order("exam_date")
            .limit(50)
            .execute()
        )
        return jsonify({"plans": result.data or []})

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    subject = (data.get("subject") or "").strip()
    exam_date = (data.get("exam_date") or "").strip()
    if not title or not subject or not exam_date:
        return jsonify({"error": "Title, subject, and exam date are required"}), 400
    try:
        datetime.date.fromisoformat(exam_date)
    except ValueError:
        return jsonify({"error": "Exam date must use YYYY-MM-DD format"}), 400

    result = supabase.table("study_plans").insert({
        "user_id": request.user_id,
        "title": title[:120],
        "subject": subject[:80],
        "exam_date": exam_date,
        "notes": (data.get("notes") or "").strip()[:500],
    }).execute()
    return jsonify({"plan": result.data[0]}), 201


@app.route("/api/plans/<plan_id>", methods=["PATCH", "DELETE"])
@token_required
def update_study_plan(plan_id):
    try:
        uuid.UUID(str(plan_id))
    except ValueError:
        return jsonify({"error": "Invalid plan ID"}), 400

    if request.method == "DELETE":
        result = (
            supabase.table("study_plans")
            .delete()
            .eq("id", plan_id)
            .eq("user_id", request.user_id)
            .execute()
        )
        if not result.data:
            return jsonify({"error": "Plan not found"}), 404
        return jsonify({"message": "Plan deleted"})

    data = request.get_json(silent=True) or {}
    updates = {}
    if "title" in data:
        title = str(data["title"]).strip()[:120]
        if not title:
            return jsonify({"error": "Title cannot be empty"}), 400
        updates["title"] = title
    if "subject" in data:
        subject = str(data["subject"]).strip()[:80]
        if not subject:
            return jsonify({"error": "Subject cannot be empty"}), 400
        updates["subject"] = subject
    if "exam_date" in data:
        exam_date = str(data["exam_date"]).strip()
        try:
            datetime.date.fromisoformat(exam_date)
        except ValueError:
            return jsonify({"error": "Exam date must use YYYY-MM-DD format"}), 400
        updates["exam_date"] = exam_date
    if "completed" in data:
        updates["completed"] = bool(data["completed"])
        updates["completed_at"] = datetime.datetime.utcnow().isoformat() if updates["completed"] else None
    if "notes" in data:
        updates["notes"] = str(data["notes"]).strip()[:500]
    if not updates:
        return jsonify({"error": "No supported fields supplied"}), 400
    result = (
        supabase.table("study_plans")
        .update(updates)
        .eq("id", plan_id)
        .eq("user_id", request.user_id)
        .execute()
    )
    if not result.data:
        return jsonify({"error": "Plan not found"}), 404
    return jsonify({"plan": result.data[0]})


@app.route("/api/tasks", methods=["GET", "POST"])
@token_required
def study_tasks():
    if request.method == "GET":
        result = (
            supabase.table("study_tasks")
            .select("*")
            .eq("user_id", request.user_id)
            .order("due_date")
            .limit(100)
            .execute()
        )
        return jsonify({"tasks": result.data or []})

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    due_date = (data.get("due_date") or "").strip()
    if not title or not due_date:
        return jsonify({"error": "Task title and due date are required"}), 400
    try:
        datetime.date.fromisoformat(due_date)
        estimated_minutes = max(5, min(int(data.get("estimated_minutes", 30)), 480))
    except (TypeError, ValueError):
        return jsonify({"error": "Due date must use YYYY-MM-DD and duration must be valid"}), 400
    priority = data.get("priority", "medium")
    if priority not in {"low", "medium", "high"}:
        return jsonify({"error": "Priority must be low, medium, or high"}), 400
    result = supabase.table("study_tasks").insert({
        "user_id": request.user_id,
        "plan_id": data.get("plan_id") or None,
        "title": title[:160],
        "subject": (data.get("subject") or "").strip()[:80],
        "topic": (data.get("topic") or "").strip()[:160],
        "due_date": due_date,
        "priority": priority,
        "estimated_minutes": estimated_minutes,
    }).execute()
    return jsonify({"task": result.data[0]}), 201


@app.route("/api/tasks/<task_id>", methods=["PATCH", "DELETE"])
@token_required
def update_study_task(task_id):
    try:
        uuid.UUID(str(task_id))
    except ValueError:
        return jsonify({"error": "Invalid task ID"}), 400
    if request.method == "DELETE":
        result = supabase.table("study_tasks").delete().eq("id", task_id).eq("user_id", request.user_id).execute()
        if not result.data:
            return jsonify({"error": "Task not found"}), 404
        return jsonify({"message": "Task deleted"})

    data = request.get_json(silent=True) or {}
    updates = {}
    for field, limit in (("title", 160), ("subject", 80), ("topic", 160)):
        if field in data:
            value = str(data[field]).strip()[:limit]
            if field == "title" and not value:
                return jsonify({"error": "Task title cannot be empty"}), 400
            updates[field] = value
    if "due_date" in data:
        try:
            datetime.date.fromisoformat(str(data["due_date"]))
        except ValueError:
            return jsonify({"error": "Due date must use YYYY-MM-DD format"}), 400
        updates["due_date"] = str(data["due_date"])
    if "completed" in data:
        updates["completed"] = bool(data["completed"])
    if "priority" in data:
        if data["priority"] not in {"low", "medium", "high"}:
            return jsonify({"error": "Priority must be low, medium, or high"}), 400
        updates["priority"] = data["priority"]
    if "estimated_minutes" in data:
        try:
            updates["estimated_minutes"] = max(5, min(int(data["estimated_minutes"]), 480))
        except (TypeError, ValueError):
            return jsonify({"error": "Duration must be a valid number"}), 400
    if not updates:
        return jsonify({"error": "No supported fields supplied"}), 400
    result = supabase.table("study_tasks").update(updates).eq("id", task_id).eq("user_id", request.user_id).execute()
    if not result.data:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({"task": result.data[0]})


# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "db": "supabase"})


if __name__ == "__main__":
    # Use dynamic port for Render/Cloud deployment
    port = int(os.environ.get("PORT", 10000))
    # In production, debug must be False to save memory and for security
    app.run(host="0.0.0.0", port=port, debug=False)
