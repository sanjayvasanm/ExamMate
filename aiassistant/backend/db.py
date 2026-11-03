"""
ExamMate AI – db.py (Phase 2 Migration: Supabase-First Storage)
================================================================
All production data operations now route to Supabase PostgreSQL.
SQLite is initialised ONLY for local development fallback (not used on Render).
"""
import os
import json
import uuid
import datetime
import logging
from typing import Dict, Any, List, Optional
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger(__name__)

# ── Supabase Client (singleton) ───────────────────────────────────────────────

_sb = None

def _get_sb():
    """Return a Supabase service-role client (initialised once)."""
    global _sb
    if _sb is not None:
        return _sb
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    # Prefer service-role key; fall back to anon key
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")
    _sb = create_client(url, key)
    logger.info("[DB] Supabase client initialised (service-role)")
    return _sb


# ── Compatibility shim – keep SQLite init for local dev ──────────────────────

import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "exam_mate.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create local SQLite schema for dev environments."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password TEXT,
        name TEXT,
        university TEXT,
        study_streak INTEGER DEFAULT 0,
        documents_uploaded INTEGER DEFAULT 0,
        total_questions INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_active TEXT DEFAULT CURRENT_TIMESTAMP,
        avg_score REAL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        stored_path TEXT NOT NULL,
        file_type TEXT,
        file_size_bytes INTEGER DEFAULT 0,
        file_size_mb REAL DEFAULT 0,
        page_count INTEGER DEFAULT 0,
        processed_pages INTEGER DEFAULT 0,
        chunks_processed INTEGER DEFAULT 0,
        ocr_used INTEGER DEFAULT 0,
        extraction_method TEXT,
        confidence_score REAL DEFAULT 0.0,
        warnings TEXT DEFAULT '[]',
        summary TEXT,
        status TEXT DEFAULT 'uploaded',
        storage_bucket TEXT DEFAULT 'exam-documents',
        storage_path TEXT,
        doc_id TEXT,
        uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS document_chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        section_title TEXT DEFAULT 'General',
        chunk_text TEXT NOT NULL,
        chunk_type TEXT DEFAULT 'text',
        token_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS questions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        document_id TEXT,
        question TEXT NOT NULL,
        answer TEXT,
        answer_text TEXT,
        mode TEXT DEFAULT 'detailed',
        marks INTEGER DEFAULT 5,
        keywords TEXT,
        subject TEXT,
        diagrams TEXT,
        mermaid_code TEXT,
        structured_answer TEXT,
        citations TEXT DEFAULT '[]',
        is_grounded INTEGER DEFAULT 1,
        confidence REAL DEFAULT 1.0,
        asked_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS flashcard_decks (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        document_id TEXT,
        title TEXT NOT NULL,
        description TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS flashcards (
        id TEXT PRIMARY KEY,
        deck_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        document_id TEXT,
        front TEXT NOT NULL,
        back TEXT NOT NULL,
        source_page INTEGER,
        source_snippet TEXT,
        ease_factor REAL DEFAULT 2.5,
        interval_days INTEGER DEFAULT 0,
        repetition_count INTEGER DEFAULT 0,
        next_review TEXT DEFAULT CURRENT_TIMESTAMP,
        last_reviewed TEXT,
        last_rating TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS quizzes (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        document_id TEXT,
        title TEXT NOT NULL,
        subject TEXT DEFAULT 'General',
        total_questions INTEGER DEFAULT 5,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS quiz_questions (
        id TEXT PRIMARY KEY,
        quiz_id TEXT NOT NULL,
        question_text TEXT NOT NULL,
        options TEXT NOT NULL,
        correct_option_index INTEGER NOT NULL,
        explanation TEXT,
        source_page INTEGER,
        source_snippet TEXT
    );
    CREATE TABLE IF NOT EXISTS quiz_attempts (
        id TEXT PRIMARY KEY,
        quiz_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        score INTEGER NOT NULL,
        total INTEGER NOT NULL,
        percentage REAL NOT NULL,
        user_answers TEXT,
        completed_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS exams (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        subject TEXT NOT NULL,
        exam_date TEXT NOT NULL,
        target_score INTEGER DEFAULT 90,
        syllabus TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        exam_id TEXT,
        title TEXT NOT NULL,
        due_date TEXT,
        is_completed INTEGER DEFAULT 0,
        priority TEXT DEFAULT 'medium',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS focus_sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        duration_minutes INTEGER NOT NULL,
        subject TEXT DEFAULT 'General Study',
        notes TEXT,
        completed_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    conn.close()

# Initialise SQLite schema on load (no-op on Render since data lives in Supabase)
try:
    init_db()
except Exception as _e:
    logger.warning(f"[DB] SQLite init skipped: {_e}")


# ── Helper: upload file to Supabase Storage ───────────────────────────────────

def upload_to_storage(local_path: str, storage_path: str, bucket: str = "exam-documents") -> Optional[str]:
    """
    Upload a local file to Supabase Storage.
    Returns the storage_path on success, None on failure.
    Skips upload if a file already exists at that path.
    """
    sb = _get_sb()
    try:
        # Check if file already exists by trying to get its URL
        existing = sb.storage.from_(bucket).list(storage_path.rsplit("/", 1)[0] if "/" in storage_path else "")
        if existing:
            names = [f.get("name") for f in existing if isinstance(f, dict)]
            if storage_path.rsplit("/", 1)[-1] in names:
                logger.info(f"[STORAGE] File already exists at {storage_path}, skipping upload")
                return storage_path
    except Exception:
        pass  # Listing may fail for empty paths – proceed with upload

    if not os.path.exists(local_path):
        logger.warning(f"[STORAGE] Local file not found: {local_path}")
        return None

    try:
        with open(local_path, "rb") as fh:
            data = fh.read()
        sb.storage.from_(bucket).upload(storage_path, data)
        logger.info(f"[STORAGE] Uploaded {local_path} -> {bucket}/{storage_path}")
        return storage_path
    except Exception as exc:
        logger.error(f"[STORAGE] Upload failed for {local_path}: {exc}")
        return None


def get_storage_signed_url(storage_path: str, bucket: str = "exam-documents", expires: int = 3600) -> Optional[str]:
    """Return a signed URL for a private Supabase Storage file."""
    try:
        sb = _get_sb()
        res = sb.storage.from_(bucket).create_signed_url(storage_path, expires)
        return res.get("signedURL") or res.get("signedUrl")
    except Exception as exc:
        logger.error(f"[STORAGE] Signed URL failed for {storage_path}: {exc}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# DatabaseManager – all methods route to Supabase PostgreSQL
# ══════════════════════════════════════════════════════════════════════════════

class DatabaseManager:

    # ── Users ─────────────────────────────────────────────────────────────────

    @staticmethod
    def create_user(name: str, email: str, password: str) -> Optional[Dict[str, Any]]:
        sb = _get_sb()
        email = email.lower().strip()
        # Check for duplicate
        existing = sb.table("users").select("id").eq("email", email).execute()
        if existing.data:
            return None
        user_id = str(uuid.uuid4())
        pw_hash = generate_password_hash(password)
        row = {
            "id": user_id,
            "email": email,
            "password": pw_hash,
            "name": name,
            "study_streak": 1,
            "documents_uploaded": 0,
            "total_questions": 0,
            "avg_score": 0,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "last_active": datetime.datetime.utcnow().isoformat(),
        }
        try:
            sb.table("users").insert(row).execute()
            logger.info(f"[DB] User created: {email} ({user_id})")
            return {"id": user_id, "name": name, "email": email}
        except Exception as exc:
            logger.error(f"[DB] create_user failed: {exc}")
            return None

    @staticmethod
    def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
        sb = _get_sb()
        try:
            res = sb.table("users").select("*").eq("email", email.lower().strip()).execute()
            return res.data[0] if res.data else None
        except Exception as exc:
            logger.error(f"[DB] get_user_by_email failed: {exc}")
            return None

    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
        sb = _get_sb()
        try:
            res = sb.table("users").select("*").eq("id", user_id).execute()
            return res.data[0] if res.data else None
        except Exception as exc:
            logger.error(f"[DB] get_user_by_id failed: {exc}")
            return None

    @staticmethod
    def update_streak(user_id: str) -> int:
        sb = _get_sb()
        try:
            res = sb.table("users").select("study_streak,last_active").eq("id", user_id).execute()
            if not res.data:
                return 0
            row = res.data[0]
            streak = row.get("study_streak") or 0
            last_active = row.get("last_active")
            now = datetime.datetime.utcnow()
            new_streak = streak

            if last_active:
                try:
                    last_dt = datetime.datetime.fromisoformat(str(last_active).replace("Z", "+00:00"))
                    if last_dt.tzinfo:
                        last_dt = last_dt.replace(tzinfo=None)
                    diff_days = (now.date() - last_dt.date()).days
                    if diff_days == 1:
                        new_streak += 1
                    elif diff_days > 1:
                        new_streak = 1
                    elif diff_days == 0 and new_streak == 0:
                        new_streak = 1
                except Exception:
                    new_streak = 1
            else:
                new_streak = 1

            sb.table("users").update({
                "study_streak": new_streak,
                "last_active": now.isoformat()
            }).eq("id", user_id).execute()
            return new_streak
        except Exception as exc:
            logger.error(f"[DB] update_streak failed: {exc}")
            return 0

    # ── Documents ─────────────────────────────────────────────────────────────

    @staticmethod
    def save_document(doc_data: Dict[str, Any]) -> str:
        sb = _get_sb()
        doc_id = doc_data.get("id") or str(uuid.uuid4())
        file_size_bytes = doc_data.get("file_size_bytes", 0)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 4) if file_size_bytes else 0

        row = {
            "id": doc_id,
            "user_id": doc_data["user_id"],
            "filename": doc_data["filename"],
            "stored_path": doc_data.get("stored_path", ""),
            "file_type": doc_data.get("file_type", "UNKNOWN"),
            "file_size_mb": doc_data.get("file_size_mb", file_size_mb),
            "chunks_processed": doc_data.get("chunks_processed", 0),
            "status": doc_data.get("status", "uploaded"),
            "storage_bucket": "exam-documents",
            "storage_path": doc_data.get("storage_path"),
            "doc_id": doc_data.get("doc_id"),
            "uploaded_at": datetime.datetime.utcnow().isoformat(),
        }

        # summary is optional
        if doc_data.get("summary"):
            row["summary"] = doc_data["summary"]

        try:
            sb.table("documents").insert(row).execute()
            logger.info(f"[DB] Document saved: {doc_data['filename']} ({doc_id})")
        except Exception as exc:
            err = str(exc)
            if "duplicate" in err.lower() or "23505" in err:
                logger.warning(f"[DB] Document {doc_id} already exists, skipping insert")
            else:
                logger.error(f"[DB] save_document failed: {exc}")
        return doc_id

    @staticmethod
    def update_document_status(doc_id: str, status: str, chunks_processed: int = 0, storage_path: str = None):
        sb = _get_sb()
        try:
            updates = {"status": status, "chunks_processed": chunks_processed}
            if storage_path:
                updates["storage_path"] = storage_path
            sb.table("documents").update(updates).eq("id", doc_id).execute()
        except Exception as exc:
            logger.error(f"[DB] update_document_status failed: {exc}")

    @staticmethod
    def save_document_chunks(chunks: List[Dict[str, Any]]):
        if not chunks:
            return
        sb = _get_sb()
        rows = []
        for idx, c in enumerate(chunks):
            # Guarantee valid UUID v4 for Supabase Postgres UUID column
            c_id = str(uuid.uuid4())
            if c.get("id"):
                try:
                    uuid.UUID(str(c["id"]))
                    c_id = str(c["id"])
                except (ValueError, TypeError):
                    c_id = str(uuid.uuid4())

            rows.append({
                "id": c_id,
                "document_id": c["document_id"],
                "user_id": c["user_id"],
                "chunk_index": c.get("page_number", idx + 1),  # Supabase uses chunk_index
                "content": c["chunk_text"],                     # Supabase uses content
                "created_at": datetime.datetime.utcnow().isoformat(),
            })
        try:
            # Insert in batches of 100 to avoid request size limits
            for i in range(0, len(rows), 100):
                batch = rows[i:i+100]
                sb.table("document_chunks").upsert(batch, on_conflict="id").execute()
            logger.info(f"[DB] Saved {len(rows)} document chunks")
        except Exception as exc:
            logger.error(f"[DB] save_document_chunks failed: {exc}")

    @staticmethod
    def get_documents_by_user(user_id: str) -> List[Dict[str, Any]]:
        sb = _get_sb()
        try:
            res = sb.table("documents").select(
                "id,user_id,filename,file_type,file_size_mb,chunks_processed,"
                "status,storage_bucket,storage_path,doc_id,uploaded_at,summary"
            ).eq("user_id", user_id).order("uploaded_at", desc=True).execute()
            docs = []
            for d in res.data:
                d["file_size_bytes"] = int((d.get("file_size_mb") or 0) * 1024 * 1024)
                d["warnings"] = []
                d["confidence_score"] = d.get("confidence_score") or (95.0 if d.get("status") == "processed" else 85.0)
                d["page_count"] = d.get("page_count") or d.get("chunks_processed") or 1
                docs.append(d)
            return docs
        except Exception as exc:
            logger.error(f"[DB] get_documents_by_user failed: {exc}")
            return []

    @staticmethod
    def get_document_by_id(doc_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        sb = _get_sb()
        try:
            res = sb.table("documents").select("*").eq("id", doc_id).eq("user_id", user_id).execute()
            if not res.data:
                return None
            d = res.data[0]
            d["file_size_bytes"] = int((d.get("file_size_mb") or 0) * 1024 * 1024)
            d["warnings"] = []
            d["confidence_score"] = d.get("confidence_score") or (95.0 if d.get("status") == "processed" else 85.0)
            d["page_count"] = d.get("page_count") or d.get("chunks_processed") or 1
            return d
        except Exception as exc:
            logger.error(f"[DB] get_document_by_id failed: {exc}")
            return None

    @staticmethod
    def get_document_chunks(doc_id: str, user_id: str) -> List[Dict[str, Any]]:
        sb = _get_sb()
        try:
            res = sb.table("document_chunks").select(
                "id,document_id,user_id,chunk_index,content"
            ).eq("document_id", doc_id).eq("user_id", user_id).order("chunk_index").execute()
            # Normalise to internal field names expected by retriever/generator
            result = []
            for r in (res.data or []):
                r["page_number"] = r.get("chunk_index", 1)
                r["chunk_text"] = r.get("content", "")
                r["section_title"] = r.get("section_title", "General")
                r["chunk_type"] = r.get("chunk_type", "text")
                r["token_count"] = r.get("token_count", len(r["chunk_text"].split()))
                result.append(r)
            return result
        except Exception as exc:
            logger.error(f"[DB] get_document_chunks failed: {exc}")
            return []

    @staticmethod
    def delete_document(doc_id: str, user_id: str) -> bool:
        sb = _get_sb()
        try:
            # Get storage_path before deleting
            res = sb.table("documents").select("stored_path,storage_path,storage_bucket").eq("id", doc_id).eq("user_id", user_id).execute()
            if not res.data:
                return False
            doc = res.data[0]

            # Remove local file if present
            stored_path = doc.get("stored_path", "")
            if stored_path and os.path.exists(stored_path):
                try:
                    os.remove(stored_path)
                except Exception:
                    pass

            # Delete chunks then document
            sb.table("document_chunks").delete().eq("document_id", doc_id).eq("user_id", user_id).execute()
            sb.table("documents").delete().eq("id", doc_id).eq("user_id", user_id).execute()
            logger.info(f"[DB] Deleted document {doc_id}")
            return True
        except Exception as exc:
            logger.error(f"[DB] delete_document failed: {exc}")
            return False

    # ── Questions ─────────────────────────────────────────────────────────────

    @staticmethod
    def save_question(q_data: Dict[str, Any]) -> str:
        sb = _get_sb()
        q_id = q_data.get("id") or str(uuid.uuid4())
        row = {
            "id": q_id,
            "user_id": q_data["user_id"],
            "document_id": q_data.get("document_id"),
            "question": q_data["question"],
            "answer": q_data.get("answer_text") or q_data.get("answer", ""),
            "mode": q_data.get("mode", "detailed"),
            "marks": q_data.get("marks", 5),
            "keywords": json.dumps(q_data.get("keywords", [])) if isinstance(q_data.get("keywords"), list) else (q_data.get("keywords") or ""),
            "subject": q_data.get("subject", ""),
            "asked_at": datetime.datetime.utcnow().isoformat(),
        }
        # Store structured data in diagrams column if present
        if q_data.get("structured_answer"):
            row["diagrams"] = json.dumps(q_data["structured_answer"])
        try:
            sb.table("questions").insert(row).execute()
        except Exception as exc:
            logger.error(f"[DB] save_question failed: {exc}")
        return q_id

    @staticmethod
    def get_questions_by_user(user_id: str, query_filter: str = "") -> List[Dict[str, Any]]:
        sb = _get_sb()
        try:
            query = sb.table("questions").select("*").eq("user_id", user_id).order("asked_at", desc=True).limit(50)
            res = query.execute()
            result = []
            for r in res.data:
                # Normalise field names for backward compat
                r["answer_text"] = r.get("answer") or r.get("answer_text", "")
                r["structured_answer"] = {}
                r["citations"] = []
                if query_filter and query_filter.lower() not in (r.get("question") or "").lower():
                    continue
                result.append(r)
            return result
        except Exception as exc:
            logger.error(f"[DB] get_questions_by_user failed: {exc}")
            return []

    # ── Flashcards ─────────────────────────────────────────────────────────────

    @staticmethod
    def create_deck(user_id: str, title: str, description: str = "", document_id: Optional[str] = None) -> str:
        sb = _get_sb()
        deck_id = str(uuid.uuid4())
        row = {
            "id": deck_id,
            "user_id": user_id,
            "document_id": document_id,
            "title": title,
            "description": description,
            "created_at": datetime.datetime.utcnow().isoformat(),
        }
        try:
            sb.table("flashcard_decks").insert(row).execute()
        except Exception as exc:
            logger.error(f"[DB] create_deck failed: {exc}")
        return deck_id

    @staticmethod
    def get_decks(user_id: str) -> List[Dict[str, Any]]:
        sb = _get_sb()
        try:
            decks_res = sb.table("flashcard_decks").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
            decks = decks_res.data or []
            # Attach card counts
            for deck in decks:
                cards_res = sb.table("flashcards").select("id,next_review").eq("deck_id", deck["id"]).execute()
                cards = cards_res.data or []
                deck["total_cards"] = len(cards)
                now_iso = datetime.datetime.utcnow().isoformat()
                deck["due_cards"] = sum(1 for c in cards if (c.get("next_review") or "") <= now_iso)
            return decks
        except Exception as exc:
            logger.error(f"[DB] get_decks failed: {exc}")
            return []

    @staticmethod
    def add_card(deck_id: str, user_id: str, front: str, back: str,
                 document_id: Optional[str] = None, source_page: Optional[int] = None,
                 source_snippet: Optional[str] = None) -> str:
        sb = _get_sb()
        card_id = str(uuid.uuid4())
        row = {
            "id": card_id,
            "deck_id": deck_id,
            "user_id": user_id,
            "document_id": document_id,
            "front": front,
            "back": back,
            "source_page": source_page,
            "source_snippet": source_snippet,
            "ease_factor": 2.5,
            "interval_days": 0,
            "repetition_count": 0,
            "next_review": datetime.datetime.utcnow().isoformat(),
            "created_at": datetime.datetime.utcnow().isoformat(),
        }
        try:
            sb.table("flashcards").insert(row).execute()
        except Exception as exc:
            logger.error(f"[DB] add_card failed: {exc}")
        return card_id

    @staticmethod
    def get_cards_for_deck(deck_id: str, user_id: str) -> List[Dict[str, Any]]:
        sb = _get_sb()
        try:
            res = sb.table("flashcards").select("*").eq("deck_id", deck_id).eq("user_id", user_id).order("next_review").execute()
            return res.data or []
        except Exception as exc:
            logger.error(f"[DB] get_cards_for_deck failed: {exc}")
            return []

    @staticmethod
    def review_card(card_id: str, user_id: str, rating: str) -> Dict[str, Any]:
        sb = _get_sb()
        try:
            res = sb.table("flashcards").select("*").eq("id", card_id).eq("user_id", user_id).execute()
            if not res.data:
                return {"error": "Card not found"}
            card = res.data[0]
            ease = float(card.get("ease_factor") or 2.5)
            interval = int(card.get("interval_days") or 0)
            reps = int(card.get("repetition_count") or 0)
            rating_lower = (rating or "").lower().strip()
            now = datetime.datetime.utcnow()

            if rating_lower == "again":
                reps = 0; interval = 1; ease = max(1.3, ease - 0.2)
            elif rating_lower == "hard":
                reps += 1; interval = max(1, int(interval * 1.2)) if interval > 0 else 1; ease = max(1.3, ease - 0.15)
            elif rating_lower == "good":
                reps += 1
                interval = 1 if reps == 1 else 6 if reps == 2 else max(1, int(interval * ease))
            elif rating_lower == "easy":
                reps += 1
                interval = 4 if reps == 1 else 10 if reps == 2 else max(1, int(interval * ease * 1.3))
                ease = min(3.0, ease + 0.15)
            else:
                reps += 1; interval = max(1, interval + 1)

            next_review = (now + datetime.timedelta(days=interval)).isoformat()
            sb.table("flashcards").update({
                "ease_factor": ease,
                "interval_days": interval,
                "repetition_count": reps,
                "next_review": next_review,
                "last_reviewed": now.isoformat(),
                "last_rating": rating,
            }).eq("id", card_id).eq("user_id", user_id).execute()

            return {
                "card_id": card_id,
                "next_review": next_review,
                "interval_days": interval,
                "repetition_count": reps,
                "ease_factor": round(ease, 2),
            }
        except Exception as exc:
            logger.error(f"[DB] review_card failed: {exc}")
            return {"error": str(exc)}

    @staticmethod
    def delete_deck(deck_id: str, user_id: str) -> bool:
        sb = _get_sb()
        try:
            sb.table("flashcards").delete().eq("deck_id", deck_id).eq("user_id", user_id).execute()
            sb.table("flashcard_decks").delete().eq("id", deck_id).eq("user_id", user_id).execute()
            return True
        except Exception as exc:
            logger.error(f"[DB] delete_deck failed: {exc}")
            return False

    # ── Quizzes ───────────────────────────────────────────────────────────────

    @staticmethod
    def create_quiz(user_id: str, title: str, subject: str, document_id: Optional[str],
                    questions_list: List[Dict[str, Any]]) -> str:
        sb = _get_sb()
        quiz_id = str(uuid.uuid4())
        try:
            sb.table("quizzes").insert({
                "id": quiz_id,
                "user_id": user_id,
                "document_id": document_id,
                "title": title,
                "subject": subject,
                "total_questions": len(questions_list),
                "created_at": datetime.datetime.utcnow().isoformat(),
            }).execute()

            qq_rows = []
            for q in questions_list:
                qq_rows.append({
                    "id": str(uuid.uuid4()),
                    "quiz_id": quiz_id,
                    "question_text": q["question_text"],
                    "options": json.dumps(q["options"]) if isinstance(q["options"], list) else q["options"],
                    "correct_option_index": int(q["correct_option_index"]),
                    "explanation": q.get("explanation", ""),
                    "source_page": q.get("source_page"),
                    "source_snippet": q.get("source_snippet"),
                })
            if qq_rows:
                sb.table("quiz_questions").insert(qq_rows).execute()
        except Exception as exc:
            logger.error(f"[DB] create_quiz failed: {exc}")
        return quiz_id

    @staticmethod
    def get_quizzes(user_id: str) -> List[Dict[str, Any]]:
        sb = _get_sb()
        try:
            res = sb.table("quizzes").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
            quizzes = res.data or []
            for quiz in quizzes:
                # quiz_attempts uses 'quiz' column (not quiz_id) and 'score','total'
                att_res = sb.table("quiz_attempts").select("score,total").eq("quiz", quiz["id"]).eq("user_id", user_id).execute()
                atts = att_res.data or []
                quiz["attempts_count"] = len(atts)
                percentages = [round((a["score"] / a["total"]) * 100, 1) for a in atts if a.get("total")]
                quiz["best_score"] = max(percentages) if percentages else None
            return quizzes
        except Exception as exc:
            logger.error(f"[DB] get_quizzes failed: {exc}")
            return []

    @staticmethod
    def get_quiz_detail(quiz_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        sb = _get_sb()
        try:
            qr = sb.table("quizzes").select("*").eq("id", quiz_id).eq("user_id", user_id).execute()
            if not qr.data:
                return None
            quiz = qr.data[0]
            qqr = sb.table("quiz_questions").select("*").eq("quiz_id", quiz_id).execute()
            questions = []
            for r in (qqr.data or []):
                try:
                    r["options"] = json.loads(r["options"]) if isinstance(r["options"], str) else r["options"]
                except Exception:
                    r["options"] = []
                questions.append(r)
            quiz["questions"] = questions
            return quiz
        except Exception as exc:
            logger.error(f"[DB] get_quiz_detail failed: {exc}")
            return None

    @staticmethod
    def submit_quiz_attempt(quiz_id: str, user_id: str, user_answers: List[int]) -> Dict[str, Any]:
        sb = _get_sb()
        try:
            qqr = sb.table("quiz_questions").select("*").eq("quiz_id", quiz_id).execute()
            questions = qqr.data or []
            if not questions:
                return {"error": "Quiz not found"}

            score = 0
            total = len(questions)
            breakdown = []
            for i, q in enumerate(questions):
                ans = user_answers[i] if i < len(user_answers) else -1
                is_correct = (ans == q["correct_option_index"])
                if is_correct:
                    score += 1
                breakdown.append({
                    "question_id": q["id"],
                    "question_text": q["question_text"],
                    "user_answer": ans,
                    "correct_option_index": q["correct_option_index"],
                    "is_correct": is_correct,
                    "explanation": q.get("explanation"),
                    "source_page": q.get("source_page"),
                })

            percentage = round((score / total) * 100, 1) if total > 0 else 0.0
            attempt_id = str(uuid.uuid4())
            # Supabase quiz_attempts columns: id, user_id, document_id, quiz, answers, score, total, created_at
            sb.table("quiz_attempts").insert({
                "id": attempt_id,
                "user_id": user_id,
                "quiz": quiz_id,                          # Supabase uses 'quiz' not 'quiz_id'
                "answers": json.dumps(user_answers),       # Supabase uses 'answers'
                "score": score,
                "total": total,
                "created_at": datetime.datetime.utcnow().isoformat(),
            }).execute()

            return {
                "attempt_id": attempt_id,
                "score": score,
                "total": total,
                "percentage": percentage,
                "breakdown": breakdown,
            }
        except Exception as exc:
            logger.error(f"[DB] submit_quiz_attempt failed: {exc}")
            return {"error": str(exc)}

    # ── Exams & Tasks ─────────────────────────────────────────────────────────

    @staticmethod
    def create_exam(user_id: str, title: str, subject: str, exam_date: str,
                    target_score: int = 90, syllabus: str = "") -> str:
        sb = _get_sb()
        exam_id = str(uuid.uuid4())
        try:
            sb.table("exams").insert({
                "id": exam_id,
                "user_id": user_id,
                "title": title,
                "subject": subject,
                "exam_date": exam_date,
                "target_score": target_score,
                "syllabus": syllabus,
                "created_at": datetime.datetime.utcnow().isoformat(),
            }).execute()
        except Exception as exc:
            logger.error(f"[DB] create_exam failed: {exc}")
        return exam_id

    @staticmethod
    def get_exams(user_id: str) -> List[Dict[str, Any]]:
        sb = _get_sb()
        try:
            res = sb.table("exams").select("*").eq("user_id", user_id).order("exam_date").execute()
            now = datetime.datetime.utcnow().date()
            exams = []
            for ex in (res.data or []):
                try:
                    ex_date = datetime.datetime.fromisoformat(str(ex["exam_date"]).replace("Z", "")).date()
                    ex["days_left"] = (ex_date - now).days
                except Exception:
                    ex["days_left"] = 0
                exams.append(ex)
            return exams
        except Exception as exc:
            logger.error(f"[DB] get_exams failed: {exc}")
            return []

    @staticmethod
    def delete_exam(exam_id: str, user_id: str) -> bool:
        sb = _get_sb()
        try:
            sb.table("exams").delete().eq("id", exam_id).eq("user_id", user_id).execute()
            return True
        except Exception as exc:
            logger.error(f"[DB] delete_exam failed: {exc}")
            return False

    @staticmethod
    def create_task(user_id: str, title: str, due_date: Optional[str] = None,
                    exam_id: Optional[str] = None, priority: str = "medium") -> str:
        sb = _get_sb()
        task_id = str(uuid.uuid4())
        try:
            sb.table("tasks").insert({
                "id": task_id,
                "user_id": user_id,
                "exam_id": exam_id,
                "title": title,
                "due_date": due_date,
                "is_completed": False,
                "priority": priority,
                "created_at": datetime.datetime.utcnow().isoformat(),
            }).execute()
        except Exception as exc:
            logger.error(f"[DB] create_task failed: {exc}")
        return task_id

    @staticmethod
    def get_tasks(user_id: str) -> List[Dict[str, Any]]:
        sb = _get_sb()
        try:
            res = sb.table("tasks").select("*").eq("user_id", user_id).order("is_completed").order("created_at", desc=True).execute()
            tasks = res.data or []
            for t in tasks:
                t["exam_title"] = None  # no join in PostgREST simple select
            return tasks
        except Exception as exc:
            logger.error(f"[DB] get_tasks failed: {exc}")
            return []

    @staticmethod
    def toggle_task(task_id: str, user_id: str) -> bool:
        sb = _get_sb()
        try:
            res = sb.table("tasks").select("is_completed").eq("id", task_id).eq("user_id", user_id).execute()
            if not res.data:
                return False
            new_val = not bool(res.data[0]["is_completed"])
            sb.table("tasks").update({"is_completed": new_val}).eq("id", task_id).eq("user_id", user_id).execute()
            return True
        except Exception as exc:
            logger.error(f"[DB] toggle_task failed: {exc}")
            return False

    @staticmethod
    def delete_task(task_id: str, user_id: str) -> bool:
        sb = _get_sb()
        try:
            sb.table("tasks").delete().eq("id", task_id).eq("user_id", user_id).execute()
            return True
        except Exception as exc:
            logger.error(f"[DB] delete_task failed: {exc}")
            return False

    # ── Focus Sessions ────────────────────────────────────────────────────────

    @staticmethod
    def log_focus_session(user_id: str, duration_minutes: int,
                          subject: str = "General", notes: str = "") -> str:
        sb = _get_sb()
        session_id = str(uuid.uuid4())
        try:
            sb.table("focus_sessions").insert({
                "id": session_id,
                "user_id": user_id,
                "duration_minutes": duration_minutes,
                "subject": subject,
                "notes": notes,
                "completed_at": datetime.datetime.utcnow().isoformat(),
            }).execute()
        except Exception as exc:
            logger.error(f"[DB] log_focus_session failed: {exc}")
        return session_id

    # ── Analytics ─────────────────────────────────────────────────────────────

    @staticmethod
    def get_analytics(user_id: str) -> Dict[str, Any]:
        sb = _get_sb()
        try:
            focus_res = sb.table("focus_sessions").select("duration_minutes").eq("user_id", user_id).execute()
            total_focus = sum(f["duration_minutes"] for f in (focus_res.data or []))

            q_res = sb.table("questions").select("id", count="exact").eq("user_id", user_id).execute()
            total_questions = q_res.count or len(q_res.data or [])

            d_res = sb.table("documents").select("id", count="exact").eq("user_id", user_id).execute()
            total_docs = d_res.count or len(d_res.data or [])

            att_res = sb.table("quiz_attempts").select("score,total").eq("user_id", user_id).execute()
            atts = att_res.data or []
            quiz_attempts = len(atts)
            percentages = [round((a["score"] / a["total"]) * 100, 1) for a in atts if a.get("total")]
            avg_quiz_score = round(sum(percentages) / len(percentages), 1) if percentages else 0.0

            fc_res = sb.table("flashcards").select("repetition_count,next_review").eq("user_id", user_id).execute()
            cards = fc_res.data or []
            now_iso = datetime.datetime.utcnow().isoformat()
            mastered = sum(1 for c in cards if (c.get("repetition_count") or 0) >= 3)
            due = sum(1 for c in cards if (c.get("next_review") or "") <= now_iso)

            task_res = sb.table("tasks").select("is_completed").eq("user_id", user_id).execute()
            tasks = task_res.data or []
            done_tasks = sum(1 for t in tasks if t.get("is_completed"))

            user_res = sb.table("users").select("study_streak").eq("id", user_id).execute()
            streak = (user_res.data[0].get("study_streak") or 0) if user_res.data else 0

            return {
                "study_streak": streak,
                "total_focus_minutes": total_focus,
                "total_focus_hours": round(total_focus / 60, 1),
                "total_documents": total_docs,
                "total_questions": total_questions,
                "quiz_attempts": quiz_attempts,
                "average_quiz_score": avg_quiz_score,
                "total_flashcards": len(cards),
                "mastered_flashcards": mastered,
                "due_flashcards": due,
                "total_tasks": len(tasks),
                "completed_tasks": done_tasks,
            }
        except Exception as exc:
            logger.error(f"[DB] get_analytics failed: {exc}")
            return {
                "study_streak": 0, "total_focus_minutes": 0, "total_focus_hours": 0,
                "total_documents": 0, "total_questions": 0, "quiz_attempts": 0,
                "average_quiz_score": 0, "total_flashcards": 0, "mastered_flashcards": 0,
                "due_flashcards": 0, "total_tasks": 0, "completed_tasks": 0,
            }
