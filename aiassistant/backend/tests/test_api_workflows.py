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


if __name__ == "__main__":
    unittest.main()
