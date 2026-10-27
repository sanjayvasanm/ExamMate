import os
import sqlite3
import json
import uuid
import datetime
from typing import Dict, Any, List, Optional
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "exam_mate.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the relational schema with full support for precision learning."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT,
        university TEXT,
        study_streak INTEGER DEFAULT 0,
        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Documents
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        stored_path TEXT NOT NULL,
        file_type TEXT,
        file_size_bytes INTEGER DEFAULT 0,
        page_count INTEGER DEFAULT 0,
        processed_pages INTEGER DEFAULT 0,
        ocr_used BOOLEAN DEFAULT 0,
        extraction_method TEXT,
        confidence_score REAL DEFAULT 0.0,
        warnings TEXT DEFAULT '[]',
        summary TEXT,
        status TEXT DEFAULT 'uploaded',
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 3. Document Chunks (Structured Extraction Storage)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS document_chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        section_title TEXT DEFAULT 'General',
        chunk_text TEXT NOT NULL,
        chunk_type TEXT DEFAULT 'text',
        token_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 4. Questions & Exam Answers
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        document_id TEXT,
        question TEXT NOT NULL,
        mode TEXT DEFAULT 'detailed',
        marks INTEGER DEFAULT 5,
        answer_text TEXT NOT NULL,
        structured_answer TEXT,
        citations TEXT DEFAULT '[]',
        is_grounded BOOLEAN DEFAULT 1,
        confidence REAL DEFAULT 1.0,
        asked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 5. Flashcard Decks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS flashcard_decks (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        document_id TEXT,
        title TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 6. Flashcards with Spaced Repetition (SM-2)
    cursor.execute("""
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
        next_review TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_reviewed TIMESTAMP,
        last_rating TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (deck_id) REFERENCES flashcard_decks(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 7. Quizzes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS quizzes (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        document_id TEXT,
        title TEXT NOT NULL,
        subject TEXT DEFAULT 'General',
        total_questions INTEGER DEFAULT 5,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 8. Quiz Questions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS quiz_questions (
        id TEXT PRIMARY KEY,
        quiz_id TEXT NOT NULL,
        question_text TEXT NOT NULL,
        options TEXT NOT NULL, -- JSON array of 4 strings
        correct_option_index INTEGER NOT NULL,
        explanation TEXT,
        source_page INTEGER,
        source_snippet TEXT,
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
    );
    """)

    # 9. Quiz Attempts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS quiz_attempts (
        id TEXT PRIMARY KEY,
        quiz_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        score INTEGER NOT NULL,
        total INTEGER NOT NULL,
        percentage REAL NOT NULL,
        user_answers TEXT, -- JSON array of selected indices
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 10. Exams
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS exams (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        subject TEXT NOT NULL,
        exam_date TIMESTAMP NOT NULL,
        target_score INTEGER DEFAULT 90,
        syllabus TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 11. Study Tasks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        exam_id TEXT,
        title TEXT NOT NULL,
        due_date TIMESTAMP,
        is_completed BOOLEAN DEFAULT 0,
        priority TEXT DEFAULT 'medium',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE SET NULL
    );
    """)

    # 12. Focus Sessions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS focus_sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        duration_minutes INTEGER NOT NULL,
        subject TEXT DEFAULT 'General Study',
        notes TEXT,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()

# Initialize tables immediately on module load
init_db()

# ── Database Service Operations ───────────────────────────────────────────────

class DatabaseManager:
    @staticmethod
    def create_user(name: str, email: str, password: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            user_id = str(uuid.uuid4())
            pw_hash = generate_password_hash(password)
            cursor.execute("""
                INSERT INTO users (id, name, email, password_hash, study_streak, last_active)
                VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            """, (user_id, name, email.lower().strip(), pw_hash))
            conn.commit()
            return {"id": user_id, "name": name, "email": email.lower().strip()}
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()

    @staticmethod
    def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def update_streak(user_id: str) -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT study_streak, last_active FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return 0
        streak = row["study_streak"] or 0
        last_active = row["last_active"]
        now = datetime.datetime.utcnow()
        new_streak = streak

        if last_active:
            try:
                last_dt = datetime.datetime.fromisoformat(str(last_active).replace("Z", "+00:00"))
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

        cursor.execute("UPDATE users SET study_streak = ?, last_active = CURRENT_TIMESTAMP WHERE id = ?", (new_streak, user_id))
        conn.commit()
        conn.close()
        return new_streak

    # Documents
    @staticmethod
    def save_document(doc_data: Dict[str, Any]) -> str:
        conn = get_db_connection()
        cursor = conn.cursor()
        doc_id = doc_data.get("id") or str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO documents (
                id, user_id, filename, stored_path, file_type, file_size_bytes,
                page_count, processed_pages, ocr_used, extraction_method,
                confidence_score, warnings, summary, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc_id,
            doc_data["user_id"],
            doc_data["filename"],
            doc_data["stored_path"],
            doc_data.get("file_type", "UNKNOWN"),
            doc_data.get("file_size_bytes", 0),
            doc_data.get("page_count", 0),
            doc_data.get("processed_pages", 0),
            1 if doc_data.get("ocr_used") else 0,
            doc_data.get("extraction_method", "hybrid"),
            doc_data.get("confidence_score", 0.0),
            json.dumps(doc_data.get("warnings", [])),
            doc_data.get("summary", ""),
            doc_data.get("status", "completed")
        ))
        conn.commit()
        conn.close()
        return doc_id

    @staticmethod
    def save_document_chunks(chunks: List[Dict[str, Any]]):
        if not chunks:
            return
        conn = get_db_connection()
        cursor = conn.cursor()
        for c in chunks:
            c_id = c.get("id") or str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO document_chunks (
                    id, document_id, user_id, page_number, section_title, chunk_text, chunk_type, token_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c_id,
                c["document_id"],
                c["user_id"],
                c.get("page_number", 1),
                c.get("section_title", "General"),
                c["chunk_text"],
                c.get("chunk_type", "text"),
                c.get("token_count", len(c["chunk_text"].split()))
            ))
        conn.commit()
        conn.close()

    @staticmethod
    def get_documents_by_user(user_id: str) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, filename, file_type, file_size_bytes, page_count,
                   processed_pages, ocr_used, extraction_method, confidence_score,
                   warnings, summary, status, uploaded_at
            FROM documents WHERE user_id = ? ORDER BY uploaded_at DESC
        """, (user_id,))
        rows = cursor.fetchall()
        docs = []
        for r in rows:
            d = dict(r)
            try:
                d["warnings"] = json.loads(d["warnings"]) if d["warnings"] else []
            except Exception:
                d["warnings"] = []
            docs.append(d)
        conn.close()
        return docs

    @staticmethod
    def get_document_by_id(doc_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        d = dict(row)
        try:
            d["warnings"] = json.loads(d["warnings"]) if d["warnings"] else []
        except Exception:
            d["warnings"] = []
        conn.close()
        return d

    @staticmethod
    def get_document_chunks(doc_id: str, user_id: str) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, document_id, user_id, page_number, section_title, chunk_text, chunk_type, token_count
            FROM document_chunks
            WHERE document_id = ? AND user_id = ?
            ORDER BY page_number ASC, rowid ASC
        """, (doc_id, user_id))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def delete_document(doc_id: str, user_id: str) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT stored_path FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        stored_path = row["stored_path"]
        if os.path.exists(stored_path):
            try:
                os.remove(stored_path)
            except Exception:
                pass
        cursor.execute("DELETE FROM document_chunks WHERE document_id = ? AND user_id = ?", (doc_id, user_id))
        cursor.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
        conn.commit()
        conn.close()
        return True

    # Questions & Grounded Answers
    @staticmethod
    def save_question(q_data: Dict[str, Any]) -> str:
        conn = get_db_connection()
        cursor = conn.cursor()
        q_id = q_data.get("id") or str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO questions (
                id, user_id, document_id, question, mode, marks, answer_text,
                structured_answer, citations, is_grounded, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            q_id,
            q_data["user_id"],
            q_data.get("document_id"),
            q_data["question"],
            q_data.get("mode", "detailed"),
            q_data.get("marks", 5),
            q_data["answer_text"],
            json.dumps(q_data.get("structured_answer", {})),
            json.dumps(q_data.get("citations", [])),
            1 if q_data.get("is_grounded", True) else 0,
            q_data.get("confidence", 1.0)
        ))
        conn.commit()
        conn.close()
        return q_id

    @staticmethod
    def get_questions_by_user(user_id: str, query_filter: str = "") -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        if query_filter:
            cursor.execute("""
                SELECT * FROM questions
                WHERE user_id = ? AND question LIKE ?
                ORDER BY asked_at DESC LIMIT 50
            """, (user_id, f"%{query_filter}%"))
        else:
            cursor.execute("""
                SELECT * FROM questions
                WHERE user_id = ?
                ORDER BY asked_at DESC LIMIT 50
            """, (user_id,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            item = dict(r)
            try:
                item["structured_answer"] = json.loads(item["structured_answer"]) if item["structured_answer"] else {}
            except Exception:
                item["structured_answer"] = {}
            try:
                item["citations"] = json.loads(item["citations"]) if item["citations"] else []
            except Exception:
                item["citations"] = []
            result.append(item)
        conn.close()
        return result

    # Flashcards & Spaced Repetition
    @staticmethod
    def create_deck(user_id: str, title: str, description: str = "", document_id: Optional[str] = None) -> str:
        conn = get_db_connection()
        cursor = conn.cursor()
        deck_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO flashcard_decks (id, user_id, document_id, title, description)
            VALUES (?, ?, ?, ?, ?)
        """, (deck_id, user_id, document_id, title, description))
        conn.commit()
        conn.close()
        return deck_id

    @staticmethod
    def get_decks(user_id: str) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.*, 
                   COUNT(f.id) as total_cards,
                   SUM(CASE WHEN f.next_review <= CURRENT_TIMESTAMP THEN 1 ELSE 0 END) as due_cards
            FROM flashcard_decks d
            LEFT JOIN flashcards f ON d.id = f.deck_id
            WHERE d.user_id = ?
            GROUP BY d.id
            ORDER BY d.created_at DESC
        """, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def add_card(deck_id: str, user_id: str, front: str, back: str, 
                 document_id: Optional[str] = None, source_page: Optional[int] = None, 
                 source_snippet: Optional[str] = None) -> str:
        conn = get_db_connection()
        cursor = conn.cursor()
        card_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO flashcards (
                id, deck_id, user_id, document_id, front, back, source_page, source_snippet
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (card_id, deck_id, user_id, document_id, front, back, source_page, source_snippet))
        conn.commit()
        conn.close()
        return card_id

    @staticmethod
    def get_cards_for_deck(deck_id: str, user_id: str) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM flashcards WHERE deck_id = ? AND user_id = ? ORDER BY next_review ASC
        """, (deck_id, user_id))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def review_card(card_id: str, user_id: str, rating: str) -> Dict[str, Any]:
        """
        Implements SuperMemo SM-2 Spaced Repetition:
        Ratings:
        - 'Again' (1): reset repetitions to 0, interval 1 day
        - 'Hard' (2): interval * 1.2, ease factor -0.15
        - 'Good' (3): standard interval progression, unchanged ease
        - 'Easy' (4): interval * 1.3, ease factor +0.15
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM flashcards WHERE id = ? AND user_id = ?", (card_id, user_id))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return {"error": "Card not found"}

        card = dict(row)
        ease = float(card.get("ease_factor") or 2.5)
        interval = int(card.get("interval_days") or 0)
        reps = int(card.get("repetition_count") or 0)

        rating_lower = rating.lower().strip()
        now = datetime.datetime.utcnow()

        if rating_lower == "again":
            reps = 0
            interval = 1
            ease = max(1.3, ease - 0.2)
        elif rating_lower == "hard":
            reps += 1
            interval = max(1, int(interval * 1.2)) if interval > 0 else 1
            ease = max(1.3, ease - 0.15)
        elif rating_lower == "good":
            reps += 1
            if reps == 1:
                interval = 1
            elif reps == 2:
                interval = 6
            else:
                interval = max(1, int(interval * ease))
        elif rating_lower == "easy":
            reps += 1
            if reps == 1:
                interval = 4
            elif reps == 2:
                interval = 10
            else:
                interval = max(1, int(interval * ease * 1.3))
            ease = min(3.0, ease + 0.15)
        else:
            reps += 1
            interval = max(1, interval + 1)

        next_review = now + datetime.timedelta(days=interval)

        cursor.execute("""
            UPDATE flashcards SET
                ease_factor = ?,
                interval_days = ?,
                repetition_count = ?,
                next_review = ?,
                last_reviewed = CURRENT_TIMESTAMP,
                last_rating = ?
            WHERE id = ? AND user_id = ?
        """, (ease, interval, reps, next_review.isoformat(), rating, card_id, user_id))
        conn.commit()
        conn.close()

        return {
            "card_id": card_id,
            "next_review": next_review.isoformat(),
            "interval_days": interval,
            "repetition_count": reps,
            "ease_factor": round(ease, 2)
        }

    @staticmethod
    def delete_deck(deck_id: str, user_id: str) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM flashcards WHERE deck_id = ? AND user_id = ?", (deck_id, user_id))
        cursor.execute("DELETE FROM flashcard_decks WHERE id = ? AND user_id = ?", (deck_id, user_id))
        conn.commit()
        conn.close()
        return True

    # Quizzes
    @staticmethod
    def create_quiz(user_id: str, title: str, subject: str, document_id: Optional[str], 
                    questions_list: List[Dict[str, Any]]) -> str:
        conn = get_db_connection()
        cursor = conn.cursor()
        quiz_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO quizzes (id, user_id, document_id, title, subject, total_questions)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (quiz_id, user_id, document_id, title, subject, len(questions_list)))

        for q in questions_list:
            q_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO quiz_questions (
                    id, quiz_id, question_text, options, correct_option_index, explanation, source_page, source_snippet
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                q_id,
                quiz_id,
                q["question_text"],
                json.dumps(q["options"]),
                int(q["correct_option_index"]),
                q.get("explanation", ""),
                q.get("source_page"),
                q.get("source_snippet")
            ))
        conn.commit()
        conn.close()
        return quiz_id

    @staticmethod
    def get_quizzes(user_id: str) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT q.*, 
                   (SELECT COUNT(*) FROM quiz_attempts a WHERE a.quiz_id = q.id AND a.user_id = q.user_id) as attempts_count,
                   (SELECT MAX(a.percentage) FROM quiz_attempts a WHERE a.quiz_id = q.id AND a.user_id = q.user_id) as best_score
            FROM quizzes q
            WHERE q.user_id = ?
            ORDER BY q.created_at DESC
        """, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_quiz_detail(quiz_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM quizzes WHERE id = ? AND user_id = ?", (quiz_id, user_id))
        q_row = cursor.fetchone()
        if not q_row:
            conn.close()
            return None
        quiz = dict(q_row)

        cursor.execute("SELECT * FROM quiz_questions WHERE quiz_id = ?", (quiz_id,))
        q_rows = cursor.fetchall()
        questions = []
        for r in q_rows:
            item = dict(r)
            try:
                item["options"] = json.loads(item["options"])
            except Exception:
                item["options"] = []
            questions.append(item)
        quiz["questions"] = questions
        conn.close()
        return quiz

    @staticmethod
    def submit_quiz_attempt(quiz_id: str, user_id: str, user_answers: List[int]) -> Dict[str, Any]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM quiz_questions WHERE quiz_id = ?", (quiz_id,))
        questions = cursor.fetchall()
        if not questions:
            conn.close()
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
                "explanation": q["explanation"],
                "source_page": q["source_page"]
            })

        percentage = round((score / total) * 100, 1) if total > 0 else 0.0
        attempt_id = str(uuid.uuid4())

        cursor.execute("""
            INSERT INTO quiz_attempts (id, quiz_id, user_id, score, total, percentage, user_answers)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (attempt_id, quiz_id, user_id, score, total, percentage, json.dumps(user_answers)))
        conn.commit()
        conn.close()

        return {
            "attempt_id": attempt_id,
            "score": score,
            "total": total,
            "percentage": percentage,
            "breakdown": breakdown
        }

    # Exams & Tasks
    @staticmethod
    def create_exam(user_id: str, title: str, subject: str, exam_date: str, target_score: int = 90, syllabus: str = "") -> str:
        conn = get_db_connection()
        cursor = conn.cursor()
        exam_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO exams (id, user_id, title, subject, exam_date, target_score, syllabus)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (exam_id, user_id, title, subject, exam_date, target_score, syllabus))
        conn.commit()
        conn.close()
        return exam_id

    @staticmethod
    def get_exams(user_id: str) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM exams WHERE user_id = ? ORDER BY exam_date ASC", (user_id,))
        rows = cursor.fetchall()
        now = datetime.datetime.utcnow().date()
        exams = []
        for r in rows:
            ex = dict(r)
            try:
                ex_date = datetime.datetime.fromisoformat(str(ex["exam_date"]).replace("Z", "")).date()
                days_left = (ex_date - now).days
            except Exception:
                days_left = 0
            ex["days_left"] = days_left
            exams.append(ex)
        conn.close()
        return exams

    @staticmethod
    def delete_exam(exam_id: str, user_id: str) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM exams WHERE id = ? AND user_id = ?", (exam_id, user_id))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def create_task(user_id: str, title: str, due_date: Optional[str] = None, 
                    exam_id: Optional[str] = None, priority: str = "medium") -> str:
        conn = get_db_connection()
        cursor = conn.cursor()
        task_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO tasks (id, user_id, exam_id, title, due_date, is_completed, priority)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (task_id, user_id, exam_id, title, due_date, priority))
        conn.commit()
        conn.close()
        return task_id

    @staticmethod
    def get_tasks(user_id: str) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.*, e.title as exam_title 
            FROM tasks t
            LEFT JOIN exams e ON t.exam_id = e.id
            WHERE t.user_id = ?
            ORDER BY t.is_completed ASC, t.due_date ASC, t.created_at DESC
        """, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def toggle_task(task_id: str, user_id: str) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_completed FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        new_val = 0 if row["is_completed"] else 1
        cursor.execute("UPDATE tasks SET is_completed = ? WHERE id = ? AND user_id = ?", (new_val, task_id, user_id))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def delete_task(task_id: str, user_id: str) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
        conn.commit()
        conn.close()
        return True

    # Focus Sessions & Analytics
    @staticmethod
    def log_focus_session(user_id: str, duration_minutes: int, subject: str = "General", notes: str = "") -> str:
        conn = get_db_connection()
        cursor = conn.cursor()
        session_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO focus_sessions (id, user_id, duration_minutes, subject, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, user_id, duration_minutes, subject, notes))
        conn.commit()
        conn.close()
        return session_id

    @staticmethod
    def get_analytics(user_id: str) -> Dict[str, Any]:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Total focus time
        cursor.execute("SELECT COALESCE(SUM(duration_minutes), 0) as total_focus_min FROM focus_sessions WHERE user_id = ?", (user_id,))
        total_focus = cursor.fetchone()["total_focus_min"]

        # Total questions answered
        cursor.execute("SELECT COUNT(*) as q_count FROM questions WHERE user_id = ?", (user_id,))
        total_questions = cursor.fetchone()["q_count"]

        # Total documents uploaded
        cursor.execute("SELECT COUNT(*) as d_count FROM documents WHERE user_id = ?", (user_id,))
        total_docs = cursor.fetchone()["d_count"]

        # Quiz stats
        cursor.execute("SELECT COUNT(*) as attempts, COALESCE(AVG(percentage), 0) as avg_score FROM quiz_attempts WHERE user_id = ?", (user_id,))
        quiz_row = cursor.fetchone()
        quiz_attempts = quiz_row["attempts"]
        avg_quiz_score = round(quiz_row["avg_score"], 1)

        # Flashcards mastered vs due
        cursor.execute("""
            SELECT COUNT(*) as total_cards,
                   SUM(CASE WHEN repetition_count >= 3 THEN 1 ELSE 0 END) as mastered_cards,
                   SUM(CASE WHEN next_review <= CURRENT_TIMESTAMP THEN 1 ELSE 0 END) as due_cards
            FROM flashcards WHERE user_id = ?
        """, (user_id,))
        fc_row = cursor.fetchone()

        # Task completion
        cursor.execute("""
            SELECT COUNT(*) as total_tasks,
                   SUM(CASE WHEN is_completed = 1 THEN 1 ELSE 0 END) as done_tasks
            FROM tasks WHERE user_id = ?
        """, (user_id,))
        task_row = cursor.fetchone()

        # Study streak
        cursor.execute("SELECT study_streak FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        streak = user_row["study_streak"] if user_row else 0

        conn.close()

        return {
            "study_streak": streak,
            "total_focus_minutes": total_focus,
            "total_focus_hours": round(total_focus / 60, 1),
            "total_documents": total_docs,
            "total_questions": total_questions,
            "quiz_attempts": quiz_attempts,
            "average_quiz_score": avg_quiz_score,
            "total_flashcards": fc_row["total_cards"] or 0,
            "mastered_flashcards": fc_row["mastered_cards"] or 0,
            "due_flashcards": fc_row["due_cards"] or 0,
            "total_tasks": task_row["total_tasks"] or 0,
            "completed_tasks": task_row["done_tasks"] or 0
        }
