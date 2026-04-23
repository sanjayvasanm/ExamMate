import os
import time
import json
import datetime
from functools import wraps
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from pymongo import MongoClient
from bson import ObjectId

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

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    # Allow localhost for local dev but warn strongly
    print("[WARNING] MONGO_URI not found. Defaulting to localhost:27017 (this will likely fail in production).")
    MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "exammate"

try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo_client.server_info()  # trigger connection test
    db = mongo_client[DB_NAME]
    users_col = db["users"]
    questions_col = db["questions"]
    documents_col = db["documents"]

    # Unique index on email
    users_col.create_index("email", unique=True)
    print(f"[MongoDB] Connected → {MONGO_URI}{DB_NAME}")
except Exception as exc:
    print(f"[MongoDB] Connection failed: {exc}")
    raise SystemExit(1) from exc


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
    """Convert ObjectId fields to strings for JSON serialisation."""
    if doc is None:
        return {}
    doc["_id"] = str(doc["_id"])
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

    if users_col.find_one({"email": email}):
        return jsonify({"error": "Email already registered"}), 409

    user_doc = {
        "name": name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "created_at": datetime.datetime.utcnow(),
        "study_streak": 0,
        "total_questions": 0,
        "avg_score": 0,
        "documents_uploaded": 0,
        "last_active": datetime.datetime.utcnow(),
    }
    result = users_col.insert_one(user_doc)
    user_id = str(result.inserted_id)
    token = make_token(user_id, email)

    return jsonify({
        "message": "Account created successfully",
        "token": token,
        "user": {"id": user_id, "name": name, "email": email},
    }), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = users_col.find_one({"email": email})
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    user_id = str(user["_id"])
    token = make_token(user_id, email)

    # Update last_active
    users_col.update_one({"_id": user["_id"]}, {"$set": {"last_active": datetime.datetime.utcnow()}})

    return jsonify({
        "message": "Login successful",
        "token": token,
        "user": {"id": user_id, "name": user.get("name", ""), "email": email},
    })


# ── Profile ───────────────────────────────────────────────────────────────────
@app.route("/api/profile", methods=["GET"])
@token_required
def get_profile():
    from bson import ObjectId as ObjId
    user = users_col.find_one({"_id": ObjId(request.user_id)})
    if not user:
        return jsonify({"error": "User not found"}), 404

    q_count = questions_col.count_documents({"user_id": request.user_id})
    d_count = documents_col.count_documents({"user_id": request.user_id})

    return jsonify({
        "id": str(user["_id"]),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "study_streak": user.get("study_streak", 0),
        "total_questions": q_count,
        "documents_uploaded": d_count,
        "avg_score": user.get("avg_score", 0),
              "created_at": user.get("created_at", datetime.datetime.now(datetime.timezone.utc)).isoformat(),
    })


@app.route("/api/profile/update", methods=["PUT"])
@token_required
def update_profile():
    from bson import ObjectId as ObjId
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    users_col.update_one({"_id": ObjId(request.user_id)}, {"$set": {"name": name}})
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
    doc_id = f"doc_{int(time.time())}"

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

    # Persist document metadata to MongoDB
    doc_record = {
        "doc_id": doc_id,
        "user_id": request.user_id,
        "filename": filename,
        "stored_path": filepath,
        "file_type": ext.upper(),
        "file_size_mb": round(os.path.getsize(filepath) / (1024 * 1024), 2),
        "chunks_processed": chunks_processed,
              "uploaded_at": datetime.datetime.now(datetime.timezone.utc),
        "status": "processed" if chunks_processed > 0 else "uploaded",
    }
    documents_col.insert_one(doc_record)

    # Increment user's document count
    from bson import ObjectId as ObjId
    users_col.update_one(
        {"_id": ObjId(request.user_id)},
        {"$inc": {"documents_uploaded": 1}},
    )

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
    docs = list(documents_col.find(
        {"user_id": request.user_id},
        {"_id": 0, "stored_path": 0},
    ).sort("uploaded_at", -1).limit(20))

    for d in docs:
        if "uploaded_at" in d:
            d["uploaded_at"] = d["uploaded_at"].isoformat()

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

        # Persist question to DB
        q_record = {
            "user_id": request.user_id,
            "document_id": doc_id,
            "question": question,
            "mode": mode,
            "marks": marks,
            "answer": answer,
            "diagrams": diagrams,
            "keywords": keywords,
            "asked_at": datetime.datetime.now(datetime.timezone.utc),
            "subject": data.get("subject", "General"),
        }
        result = questions_col.insert_one(q_record)

        # Increment user question counter
        from bson import ObjectId as ObjId
        users_col.update_one(
            {"_id": ObjId(request.user_id)},
            {"$inc": {"total_questions": 1}},
        )

        return jsonify({
            "status": "success",
            "question_id": str(result.inserted_id),
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
    query: dict = {"user_id": request.user_id}
    if search:
        query["question"] = {"$regex": search, "$options": "i"}

    items = list(questions_col.find(query).sort("asked_at", -1).limit(50))
    results = []
    for item in items:
        asked_at = item.get("asked_at")
        if not asked_at:
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
            "id": str(item["_id"]),
            "question": item.get("question", ""),
            "subject": item.get("subject", "General"),
            "mode": item.get("mode", "detailed"),
            "marks": item.get("marks", 5),
            "time_label": time_label,
            "asked_at": asked_at.isoformat(),
        })

    return jsonify({"history": results})


@app.route("/api/history/<question_id>", methods=["GET"])
@token_required
def get_question_detail(question_id):
    from bson import ObjectId as ObjId
    try:
        item = questions_col.find_one({
            "_id": ObjId(question_id),
            "user_id": request.user_id,
        })
    except Exception:
        return jsonify({"error": "Invalid question ID"}), 400

    if not item:
        return jsonify({"error": "Question not found"}), 404

    item["_id"] = str(item["_id"])
    if "asked_at" in item:
        item["asked_at"] = item["asked_at"].isoformat()

    return jsonify(item)


@app.route("/api/history/<question_id>", methods=["DELETE"])
@token_required
def delete_question(question_id):
    from bson import ObjectId as ObjId
    try:
        result = questions_col.delete_one({
            "_id": ObjId(question_id),
            "user_id": request.user_id,
        })
    except Exception:
        return jsonify({"error": "Invalid question ID"}), 400

    if result.deleted_count == 0:
        return jsonify({"error": "Question not found"}), 404

    return jsonify({"message": "Deleted successfully"})


# ── Dashboard stats ───────────────────────────────────────────────────────────
@app.route("/api/dashboard", methods=["GET"])
@token_required
def get_dashboard():
    from bson import ObjectId as ObjId

    user = users_col.find_one({"_id": ObjId(request.user_id)})
    q_count = questions_col.count_documents({"user_id": request.user_id})
    d_count = documents_col.count_documents({"user_id": request.user_id})

    recent_docs = list(documents_col.find(
        {"user_id": request.user_id},
        {"_id": 0, "stored_path": 0},
    ).sort("uploaded_at", -1).limit(3))
    for d in recent_docs:
        if "uploaded_at" in d:
            d["uploaded_at"] = d["uploaded_at"].isoformat()

    recent_questions = list(questions_col.find(
        {"user_id": request.user_id},
        {"stored_path": 0},
    ).sort("asked_at", -1).limit(3))
    for q in recent_questions:
        q["_id"] = str(q["_id"])
        if "asked_at" in q:
            q["asked_at"] = q["asked_at"].isoformat()

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
    return jsonify({"status": "ok", "db": DB_NAME})


if __name__ == "__main__":
    # Use dynamic port for Render/Cloud deployment
    port = int(os.environ.get("PORT", 5000))
    # use_reloader=False is required for Python 3.13 on Windows to avoid WinError 10038
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
