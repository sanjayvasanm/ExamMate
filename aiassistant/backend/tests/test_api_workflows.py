import io
import os
import sys
import types
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

dotenv_module = types.ModuleType("dotenv")
dotenv_module.load_dotenv = lambda: None
sys.modules.setdefault("dotenv", dotenv_module)


class BootstrapQuery:
    def select(self, *_args, **_kwargs):
        return self

    def limit(self, _value):
        return self

    def execute(self):
        return types.SimpleNamespace(data=[])


class BootstrapClient:
    def table(self, _name):
        return BootstrapQuery()


supabase_module = types.ModuleType("supabase")
supabase_module.Client = object
supabase_module.create_client = lambda *_args, **_kwargs: BootstrapClient()
sys.modules.setdefault("supabase", supabase_module)

postgrest_module = types.ModuleType("postgrest")
postgrest_exceptions = types.ModuleType("postgrest.exceptions")
postgrest_exceptions.APIError = Exception
postgrest_module.exceptions = postgrest_exceptions
sys.modules.setdefault("postgrest", postgrest_module)
sys.modules.setdefault("postgrest.exceptions", postgrest_exceptions)

import app as app_module


class Result:
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count


class Query:
    def __init__(self, db, table):
        self.db = db
        self.table = table
        self.filters = []
        self.operation = "select"
        self.payload = None

    def select(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def limit(self, _value):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        rows = self.db.rows.setdefault(self.table, [])
        matches = [
            row for row in rows
            if all(str(row.get(key)) == str(value) for key, value in self.filters)
        ]
        if self.operation == "insert":
            values = self.payload if isinstance(self.payload, list) else [self.payload]
            for value in values:
                value.setdefault("id", str(uuid.uuid4()))
            rows.extend(values)
            return Result(values)
        if self.operation == "delete":
            self.db.rows[self.table] = [row for row in rows if row not in matches]
            return Result(matches)
        if self.operation == "update":
            for row in matches:
                row.update(self.payload)
            return Result(matches)
        return Result(matches, len(matches))


class FakeStorage:
    def __init__(self):
        self.deleted = []

    def from_(self, _bucket):
        return self

    def upload(self, *_args, **_kwargs):
        return None

    def remove(self, paths):
        self.deleted.extend(paths)


class FakeDatabase:
    def __init__(self):
        self.rows = {
            "users": [],
            "documents": [],
            "document_chunks": [],
            "questions": [],
            "quiz_sessions": [],
            "quiz_attempts": [],
            "study_plans": [],
            "flashcards": [],
            "study_tasks": [],
            "focus_sessions": [],
        }
        self.storage = FakeStorage()

    def table(self, name):
        return Query(self, name)

    def rpc(self, *_args, **_kwargs):
        return Query(self, "rpc")


class ApiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        app_module.supabase = self.db
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.token = app_module.make_token("user-a", "a@example.com")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_authentication_is_required(self):
        response = self.client.get("/api/documents")
        self.assertEqual(response.status_code, 401)

    def test_document_ownership_is_enforced(self):
        document_id = str(uuid.uuid4())
        self.db.rows["documents"].append({"id": document_id, "user_id": "user-b"})
        response = self.client.post(
            "/api/ask",
            headers=self.headers,
            json={"question": "Explain this", "document_id": document_id},
        )
        self.assertEqual(response.status_code, 404)

    @patch.object(app_module, "extract_text_hybrid", return_value=[{"content": "algebra equations"}])
    @patch.object(app_module, "chunk_content", return_value=["algebra equations"])
    def test_upload_persists_storage_metadata_and_chunks(self, _chunk, _extract):
        response = self.client.post(
            "/api/upload",
            headers=self.headers,
            data={"file": (io.BytesIO(b"notes"), "notes.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.db.rows["documents"]), 1)
        self.assertEqual(len(self.db.rows["document_chunks"]), 1)
        self.assertTrue(self.db.rows["documents"][0]["storage_path"].startswith("user-a/"))

    def test_document_delete_requires_ownership_and_removes_storage(self):
        document_id = str(uuid.uuid4())
        self.db.rows["documents"].append({
            "id": document_id,
            "user_id": "user-a",
            "storage_path": "user-a/doc/file.txt",
        })
        response = self.client.delete(f"/api/documents/{document_id}", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.storage.deleted, ["user-a/doc/file.txt"])
        self.assertEqual(self.db.rows["documents"], [])

    def test_document_chunk_queries_use_plural_relation(self):
        self.assertEqual(app_module.DOCUMENT_CHUNKS_TABLE, "document_chunks")
        self.db.rows["document_chunks"].append({
            "document_id": "doc-a",
            "user_id": "user-a",
            "chunk_index": 0,
            "content": "algebra equations",
        })
        app_module._load_persistent_context("user-a", "doc-a")
        self.assertEqual(len(self.db.rows["document_chunks"]), 1)

    @patch.object(app_module, "generate_quiz", return_value={
        "title": "Algebra",
        "questions": [{
            "question": "What is x?",
            "options": ["1", "2", "3", "4"],
            "answer": "B",
            "explanation": "x is 2",
        }],
    })
    def test_quiz_generation_scoring_and_attempt_history(self, _generate):
        response = self.client.post(
            "/api/quizzes/generate",
            headers=self.headers,
            json={"topic": "algebra", "count": 3},
        )
        self.assertEqual(response.status_code, 200)
        session_id = response.json["session_id"]
        response = self.client.post(
            "/api/quizzes/attempt",
            headers=self.headers,
            json={"session_id": session_id, "answers": ["B"]},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["score"], 1)
        response = self.client.get("/api/quizzes/attempts", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["attempts"]), 1)

    def test_study_plan_update_validates_ownership_and_fields(self):
        plan_id = str(uuid.uuid4())
        self.db.rows["study_plans"].append({
            "id": plan_id, "user_id": "user-a", "title": "Old",
            "subject": "Math", "exam_date": "2026-11-01",
            "completed": False,
        })
        response = self.client.patch(
            f"/api/plans/{plan_id}",
            headers=self.headers,
            json={"title": "New plan", "subject": "Physics", "exam_date": "2026-11-03"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.rows["study_plans"][0]["title"], "New plan")
        response = self.client.patch(
            f"/api/plans/{plan_id}",
            headers={"Authorization": f"Bearer {app_module.make_token('user-b', 'b@example.com')}"},
            json={"completed": True},
        )
        self.assertEqual(response.status_code, 404)

    @patch.object(app_module, "generate_flashcards", return_value={
        "cards": [{"front": "What is a vector?", "back": "A quantity with magnitude and direction."}],
    })
    def test_flashcard_generation_and_review_require_ownership(self, _generate):
        response = self.client.post(
            "/api/flashcards",
            headers=self.headers,
            json={"topic": "Vectors", "count": 3},
        )
        self.assertEqual(response.status_code, 201)
        card_id = response.json["cards"][0]["id"]
        response = self.client.post(
            f"/api/flashcards/{card_id}/review",
            headers=self.headers,
            json={"rating": "good"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.rows["flashcards"][0]["last_rating"], "good")

        other_token = app_module.make_token("user-b", "b@example.com")
        response = self.client.post(
            f"/api/flashcards/{card_id}/review",
            headers={"Authorization": f"Bearer {other_token}"},
            json={"rating": "easy"},
        )
        self.assertEqual(response.status_code, 404)

    def test_analytics_reports_real_attempts_only(self):
        self.db.rows["quiz_attempts"].extend([
            {"user_id": "user-a", "score": 1, "total": 2, "quiz": {"title": "Algebra"}},
            {"user_id": "user-a", "score": 2, "total": 2, "quiz": {"title": "Algebra"}},
            {"user_id": "user-b", "score": 0, "total": 2, "quiz": {"title": "Other"}},
        ])
        response = self.client.get("/api/analytics", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["attempts"], 2)
        self.assertEqual(response.json["average_score"], 75)
        self.assertEqual(response.json["weak_topics"][0]["topic"], "Algebra")

    def test_study_tasks_can_be_completed_and_are_user_scoped(self):
        response = self.client.post(
            "/api/tasks",
            headers=self.headers,
            json={"title": "Review vectors", "due_date": "2026-11-01", "priority": "high"},
        )
        self.assertEqual(response.status_code, 201)
        task_id = response.json["task"]["id"]
        response = self.client.patch(
            f"/api/tasks/{task_id}",
            headers=self.headers,
            json={"completed": True},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.db.rows["study_tasks"][0]["completed"])
        other_token = app_module.make_token("user-b", "b@example.com")
        response = self.client.delete(
            f"/api/tasks/{task_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(response.status_code, 404)

    def test_focus_session_is_saved_only_through_authenticated_api(self):
        response = self.client.post(
            "/api/focus-sessions",
            headers=self.headers,
            json={"subject": "Physics", "work_minutes": 25},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.db.rows["focus_sessions"][0]["work_minutes"], 25)
        response = self.client.get("/api/focus-sessions", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["sessions"]), 1)

    def test_retry_wrong_questions_creates_owned_session(self):
        attempt_id = str(uuid.uuid4())
        self.db.rows["quiz_attempts"].append({
            "id": attempt_id,
            "user_id": "user-a",
            "quiz": {"title": "Algebra", "questions": [
                {"question": "1+1?", "options": ["1", "2", "3", "4"], "answer": "B", "explanation": "Two."},
                {"question": "2+2?", "options": ["2", "3", "4", "5"], "answer": "C", "explanation": "Four."},
            ]},
            "answers": ["B", "A"],
        })
        response = self.client.post(
            f"/api/quizzes/attempts/{attempt_id}/retry-wrong",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["quiz"]["questions"]), 1)


if __name__ == "__main__":
    unittest.main()
