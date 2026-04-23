import os
import time
import json
import datetime
import uuid
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

# ── Pipeline imports ──────────────────────────────────────────────────────────
from pipeline.extractor import extract_text_hybrid, chunk_content
from pipeline.retriever import retriever_instance, get_context
from pipeline.generator import generate_exam_answer, detect_keywords, fix_mermaid_diagram

# ── Debug Logging ─────────────────────────────────────────────────────────────
print(f"[DEBUG] Current Working Directory: {os.getcwd()}")
print(f"[DEBUG] Files in CWD: {os.listdir('.')}")

# ── App config ────────────────────────────────────────────────────────────────
app = Flask(__name__)

# Allow all origins in development to facilitate mobile APK connectivity
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)

SECRET_KEY = os.environ.get("JWT_SECRET")
if not SECRET_KEY:
    # Print clearly to stderr for cloud deployment logs
    import sys
    print("FATAL: JWT_SECRET environment variable is required for deployment.", file=sys.stderr)
    print("Please set JWT_SECRET in your Render/Cloud environment variables.", file=sys.stderr)
    sys.exit(1)
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
    print(f"[Supabase] Connected to {SUPABASE_URL}")
except Exception as exc:
    print(f"[Supabase] Connection failed: {exc}")


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

    # Update last_active
    try:
        supabase.table("users").update({"last_active": datetime.datetime.utcnow().isoformat()}).eq("id", user["id"]).execute()
    except Exception as e:
        print(f"[Supabase Warning] Failed to update last_active: {e}")

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

        # Increment user question counter atomically via Supabase RPC
        try:
            supabase.rpc("increment_total_questions", {"row_id": request.user_id}).execute()
        except Exception as e:
            print(f"[Supabase Warning] Atomic increment failed (ensure RPC exists): {e}")

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


# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "db": "supabase"})


if __name__ == "__main__":
    # Use dynamic port for Render/Cloud deployment
    port = int(os.environ.get("PORT", 10000))
    # In production, debug must be False to save memory and for security
    app.run(host="0.0.0.0", port=port, debug=False)
