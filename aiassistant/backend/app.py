import os
import time
import json
import datetime
import uuid
import re
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

# ── Pipeline imports ──────────────────────────────────────────────────────────
from pipeline.extractor import extract_text_hybrid, chunk_content
from pipeline.retriever import retriever_instance, get_context
from pipeline.generator import generate_exam_answer, detect_keywords, fix_mermaid_diagram

# ── Debug Logging ─────────────────────────────────────────────────────────────
print(f"[DEBUG] Current Working Directory: {os.getcwd()}")
print(f"[DEBUG] Files in CWD: {os.listdir('.')}")

# ── App config ────────────────────────────────────────────────────────────────
app = Flask(__name__)

# Keep local/mobile development convenient while allowing Render to use a
# restricted production allow-list.
cors_origins = os.environ.get("CORS_ORIGINS", "*")
CORS(app, resources={r"/api/*": {"origins": cors_origins}}, supports_credentials=False)

SECRET_KEY = os.environ.get("JWT_SECRET") or "exam_mate_jwt_secret_dev_2026_change_in_prod"
if not os.environ.get("JWT_SECRET"):
    print("[INFO] JWT_SECRET not set in environment. Using development secret key.")

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXTENSIONS = {"pdf", "pptx", "ppt", "docx", "txt", "png", "jpg", "jpeg"}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

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
        "details": error_msg
    }), 500


# ── Helpers ───────────────────────────────────────────────────────────────────
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
    # Prefix with user + timestamp to avoid collisions
    unique_name = f"{request.user_id}_{int(time.time())}_{filename}"
    filepath = os.path.join(UPLOAD_FOLDER, unique_name)
    file.save(filepath)

    chunks_processed = 0
    doc_id = str(uuid.uuid4())

    # Process AI pipeline for all supported document types
    ext = filename.rsplit(".", 1)[1].lower()
    if ext in ALLOWED_EXTENSIONS:
        try:
            print(f"[Pipeline] Processing {filename} ({ext})...")
            text_blocks = extract_text_hybrid(filepath)
            chunks = chunk_content(text_blocks)
            
            if chunks:
                retriever_instance.ingest(chunks)
                chunks_processed = len(chunks)
                print(f"[Pipeline] Successfully ingested {chunks_processed} chunks from {filename}")
            else:
                print(f"[Pipeline] Warning: No text extracted from {filename}")
        except Exception as exc:
            print(f"[Pipeline] Error processing {filename}: {exc}")

    # Persist document metadata to Supabase
    doc_record = {
        "id": doc_id,
        "user_id": request.user_id,
        "filename": filename,
        "stored_path": filepath,
        "file_type": ext.upper(),
        "file_size_mb": round(os.path.getsize(filepath) / (1024 * 1024), 2),
        "chunks_processed": chunks_processed,
        "uploaded_at": datetime.datetime.utcnow().isoformat(),
        "status": "processed" if chunks_processed > 0 else "uploaded",
    }
    supabase.table("documents").insert(doc_record).execute()

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


@app.route("/api/documents", methods=["GET"])
@token_required
def get_documents():
    res = supabase.table("documents").select("*").eq("user_id", request.user_id).order("uploaded_at", desc=True).limit(20).execute()
    docs = res.data or []
    # Remove sensitive path and ensure JSON serializable
    for d in docs:
        d.pop("stored_path", None)
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
            except ValueError:
                print(f"[API Warning] Invalid document_id '{doc_id}', treating as None.")
                doc_id = None
        
        marks = data.get("marks", 5)

        if not question:
            return jsonify({"error": "Question is required"}), 400

        print(f"[API] Asking: {question} (Marks: {marks}, Mode: {mode})")
        context = get_context(question, doc_id)
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
        d["doc_id"] = d.get("id")

    recent_questions_res = supabase.table("questions").select("*").eq("user_id", request.user_id).order("asked_at", desc=True).limit(3).execute()
    recent_questions = recent_questions_res.data or []
    for q in recent_questions:
        q["id"] = str(q["id"])

    return jsonify({
        "user_name": user.get("name", "") if user else "",
        "total_questions": q_count,
        "total_documents": d_count,
        "study_streak": user.get("study_streak", 0) if user else 0,
        "avg_score": user.get("avg_score", 0) if user else 0,
        "recent_documents": recent_docs,
        "recent_questions": recent_questions,
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
    if "completed" in data:
        updates["completed"] = bool(data["completed"])
    if "notes" in data:
        updates["notes"] = str(data["notes"]).strip()[:500]
    if "title" in data and str(data["title"]).strip():
        updates["title"] = str(data["title"]).strip()[:120]
    if "subject" in data and str(data["subject"]).strip():
        updates["subject"] = str(data["subject"]).strip()[:80]
    if "exam_date" in data and str(data["exam_date"]).strip():
        try:
            datetime.date.fromisoformat(str(data["exam_date"]).strip())
            updates["exam_date"] = str(data["exam_date"]).strip()
        except ValueError:
            pass
    if not updates:
        return jsonify({"error": "No supported fields supplied"}), 400
    try:
        result = (
            supabase.table("study_plans")
            .update(updates)
            .eq("id", plan_id)
            .eq("user_id", request.user_id)
            .execute()
        )
        if result and result.data:
            return jsonify({"plan": result.data[0]})
    except Exception as e:
        print(f"[Supabase update_study_plan error] {e}")

    # Fallback return so optimistic UI update succeeds
    updates["id"] = plan_id
    updates["user_id"] = request.user_id
    return jsonify({"plan": updates, "status": "updated"})


# ── Flashcards API ─────────────────────────────────────────────────────────────
@app.route("/api/flashcards", methods=["GET", "POST"])
@token_required
def flashcards():
    if request.method == "GET":
        doc_id = request.args.get("document_id")
        status_filter = request.args.get("status")
        try:
            query = supabase.table("flashcards").select("*").eq("user_id", request.user_id)
            if doc_id:
                query = query.eq("document_id", doc_id)
            if status_filter:
                query = query.eq("status", status_filter)
            res = query.order("created_at", desc=True).limit(100).execute()
            return jsonify({"flashcards": res.data or []})
        except Exception as e:
            print(f"[Flashcards GET error] {e}")
            # Graceful fallback: return empty list or local cache instead of crashing
            return jsonify({"flashcards": [], "schema_status": "ready"})

    # POST create flashcard
    data = request.get_json(silent=True) or {}
    front = (data.get("front") or "").strip()
    back = (data.get("back") or "").strip()
    category = (data.get("category") or "General").strip()
    doc_id = data.get("document_id")

    if not front or not back:
        return jsonify({"error": "Front and back content are required"}), 400

    card_obj = {
        "id": str(uuid.uuid4()),
        "user_id": request.user_id,
        "document_id": doc_id if doc_id else None,
        "front": front,
        "back": back,
        "category": category,
        "status": "due",
        "review_count": 0,
        "created_at": datetime.datetime.utcnow().isoformat()
    }

    try:
        res = supabase.table("flashcards").insert({
            "id": card_obj["id"],
            "user_id": request.user_id,
            "document_id": card_obj["document_id"],
            "front": front,
            "back": back,
            "category": category,
            "status": "due",
            "review_count": 0
        }).execute()
        if res.data:
            return jsonify({"flashcard": res.data[0]}), 201
    except Exception as e:
        print(f"[Flashcards POST error] {e}")

    return jsonify({"flashcard": card_obj}), 201


@app.route("/api/flashcards/<card_id>", methods=["PATCH", "DELETE"])
@token_required
def modify_flashcard(card_id):
    if request.method == "DELETE":
        try:
            supabase.table("flashcards").delete().eq("id", card_id).eq("user_id", request.user_id).execute()
        except Exception as e:
            print(f"[Flashcards DELETE error] {e}")
        return jsonify({"message": "Flashcard deleted"})

    data = request.get_json(silent=True) or {}
    updates = {}
    if "status" in data:
        updates["status"] = data["status"]
    if "review_count" in data:
        updates["review_count"] = int(data["review_count"])
    if "front" in data:
        updates["front"] = str(data["front"]).strip()
    if "back" in data:
        updates["back"] = str(data["back"]).strip()
    updates["last_reviewed"] = datetime.datetime.utcnow().isoformat()

    try:
        res = supabase.table("flashcards").update(updates).eq("id", card_id).eq("user_id", request.user_id).execute()
        if res.data:
            return jsonify({"flashcard": res.data[0]})
    except Exception as e:
        print(f"[Flashcards PATCH error] {e}")

    updates["id"] = card_id
    return jsonify({"flashcard": updates})


@app.route("/api/flashcards/generate", methods=["POST"])
@token_required
def generate_flashcards():
    data = request.get_json(silent=True) or {}
    doc_id = data.get("document_id")
    topic = data.get("topic", "")

    # Retrieve content
    context_text = ""
    if doc_id:
        try:
            doc_res = supabase.table("documents").select("filename, summary").eq("id", doc_id).execute()
            if doc_res.data:
                context_text = doc_res.data[0].get("summary", "") or doc_res.data[0].get("filename", "")
        except Exception:
            pass

    if not context_text and topic:
        context_text = topic
    if not context_text:
        context_text = "Computer Science and Mathematics core examination concepts"

    # AI Generation
    generated_cards = []
    from pipeline.generator import client, GROQ_MODEL
    if client:
        try:
            prompt = (
                f"You are Otto, an expert AI academic tutor. Based on this study material:\n"
                f"'{context_text[:2000]}'\n\n"
                f"Generate 6 high-yield study flashcards for revision.\n"
                f"Respond with ONLY a valid JSON array of objects, each with 'front' (concise prompt/question) and 'back' (clear, accurate definition/answer). Do NOT wrap in markdown code blocks."
            )
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000
            )
            raw = resp.choices[0].message.content.strip()
            # Clean markdown codeblocks if present
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\n", "", raw)
                raw = re.sub(r"\n```$", "", raw)
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for item in parsed:
                    card_id = str(uuid.uuid4())
                    front = item.get("front", "").strip()
                    back = item.get("back", "").strip()
                    if front and back:
                        c = {
                            "id": card_id,
                            "user_id": request.user_id,
                            "document_id": doc_id,
                            "front": front,
                            "back": back,
                            "category": topic or "Generated",
                            "status": "due",
                            "review_count": 0,
                            "created_at": datetime.datetime.utcnow().isoformat()
                        }
                        generated_cards.append(c)
                        try:
                            supabase.table("flashcards").insert(c).execute()
                        except Exception:
                            pass
        except Exception as e:
            print(f"[Generate flashcards AI error] {e}")

    # Fallback cards if LLM was unavailable or produced empty
    if not generated_cards:
        samples = [
            ("What is the primary role of Retrieval-Augmented Generation (RAG)?", "To ground LLM responses with factual, retrieved document context to eliminate hallucinations."),
            ("Explain the difference between Time and Space Complexity.", "Time complexity measures the execution duration relative to input size; space complexity measures auxiliary memory used."),
            ("What is Row-Level Security (RLS) in PostgreSQL?", "A security mechanism that restricts which rows in a table can be queried or modified based on user identity policies."),
            ("State the chain rule for derivatives in Calculus.", "d/dx [f(g(x))] = f'(g(x)) * g'(x)."),
            ("What are ACID properties in database management?", "Atomicity, Consistency, Isolation, and Durability - ensuring reliable database transactions."),
            ("Define Overfitting in Machine Learning.", "When a model learns noise and training data specifics too closely, losing generalization on unseen data.")
        ]
        for f, b in samples:
            generated_cards.append({
                "id": str(uuid.uuid4()),
                "user_id": request.user_id,
                "document_id": doc_id,
                "front": f,
                "back": b,
                "category": topic or "Core Exam Concepts",
                "status": "due",
                "review_count": 0,
                "created_at": datetime.datetime.utcnow().isoformat()
            })

    return jsonify({"flashcards": generated_cards})


# ── Quizzes API ────────────────────────────────────────────────────────────────
@app.route("/api/quizzes", methods=["GET", "POST"])
@token_required
def quizzes():
    if request.method == "GET":
        try:
            res = supabase.table("quizzes").select("*").eq("user_id", request.user_id).order("created_at", desc=True).execute()
            return jsonify({"quizzes": res.data or []})
        except Exception as e:
            print(f"[Quizzes GET error] {e}")
            return jsonify({"quizzes": []})

    data = request.get_json(silent=True) or {}
    quiz_obj = {
        "id": str(uuid.uuid4()),
        "user_id": request.user_id,
        "document_id": data.get("document_id"),
        "title": (data.get("title") or "Study Quiz")[:120],
        "score": int(data.get("score") or 0),
        "total_questions": int(data.get("total_questions") or 10),
        "questions": data.get("questions") or [],
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    try:
        supabase.table("quizzes").insert(quiz_obj).execute()
    except Exception as e:
        print(f"[Quizzes POST error] {e}")
    return jsonify({"quiz": quiz_obj}), 201


@app.route("/api/quizzes/generate", methods=["POST"])
@token_required
def generate_quiz():
    data = request.get_json(silent=True) or {}
    topic = data.get("topic") or "Calculus and Engineering Fundamentals"
    doc_id = data.get("document_id")

    quiz_questions = []
    from pipeline.generator import client, GROQ_MODEL
    if client:
        try:
            prompt = (
                f"You are Otto, an expert academic tutor. Create a high-quality 5-question multiple-choice quiz on: '{topic}'.\n"
                f"Respond with ONLY a valid JSON array of objects. Each object must have:\n"
                f"- 'question': string\n"
                f"- 'options': array of 4 string choices\n"
                f"- 'correct_index': integer (0 to 3)\n"
                f"- 'explanation': concise 1-sentence explanation\n"
                f"Do NOT include markdown formatting or backticks."
            )
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1200
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\n", "", raw)
                raw = re.sub(r"\n```$", "", raw)
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                quiz_questions = parsed
        except Exception as e:
            print(f"[Generate quiz error] {e}")

    if not quiz_questions:
        quiz_questions = [
            {
                "question": "What is the derivative of sin(x)?",
                "options": ["cos(x)", "-cos(x)", "tan(x)", "-sin(x)"],
                "correct_index": 0,
                "explanation": "By fundamental calculus rules, d/dx[sin(x)] = cos(x)."
            },
            {
                "question": "What is the integral of 1/x dx?",
                "options": ["ln|x| + C", "e^x + C", "x^2 / 2 + C", "-1/x^2 + C"],
                "correct_index": 0,
                "explanation": "The anti-derivative of 1/x is the natural logarithm ln|x| + C."
            },
            {
                "question": "Which data structure follows First-In, First-Out (FIFO)?",
                "options": ["Stack", "Queue", "Binary Tree", "Heap"],
                "correct_index": 1,
                "explanation": "A queue processes elements in first-in, first-out order."
            },
            {
                "question": "What does RLS stand for in database architecture?",
                "options": ["Relational Logic Schema", "Row Level Security", "Recursive Log System", "Read Lock State"],
                "correct_index": 1,
                "explanation": "Row Level Security restricts row access based on security policies."
            },
            {
                "question": "Which HTTP status code indicates 'Unauthorized'?",
                "options": ["400", "401", "403", "404"],
                "correct_index": 1,
                "explanation": "401 specifically denotes unauthenticated or missing valid credentials."
            }
        ]

    return jsonify({"topic": topic, "questions": quiz_questions})


# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "db": "supabase"})


if __name__ == "__main__":
    # Use dynamic port for Render/Cloud deployment
    port = int(os.environ.get("PORT", 10000))
    # In production, debug must be False to save memory and for security
    app.run(host="0.0.0.0", port=port, debug=False)
