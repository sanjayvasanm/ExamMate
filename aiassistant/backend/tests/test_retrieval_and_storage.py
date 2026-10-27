import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pipeline.retriever import HybridRetriever
from storage import delete_document, download_document, upload_document


class FakeBucket:
    def __init__(self):
        self.uploads = []
        self.downloads = {}
        self.deletions = []

    def upload(self, path, payload, options):
        self.uploads.append((path, payload, options))

    def download(self, path):
        return self.downloads[path]

    def remove(self, paths):
        self.deletions.append(paths)


class FakeStorage:
    def __init__(self):
        self.bucket = FakeBucket()

    def from_(self, bucket):
        self.bucket_name = bucket
        return self.bucket


class RetrievalAndStorageTests(unittest.TestCase):
    def test_retrieval_isolated_by_user_and_document(self):
        retriever = HybridRetriever()
        retriever.ingest(["algebra equations"], user_id="user-a", document_id="doc-a")
        retriever.ingest(["mitochondria cells"], user_id="user-b", document_id="doc-b")

        self.assertTrue(retriever.retrieve("equations", user_id="user-a", document_id="doc-a"))
        self.assertEqual(
            retriever.retrieve("mitochondria", user_id="user-a", document_id="doc-a"),
            [],
        )

    def test_sync_records_preserves_document_scope_after_rebuild(self):
        retriever = HybridRetriever()
        retriever.sync_records(
            [
                {"document_id": "doc-a", "content": "algebra equations"},
                {"document_id": "doc-b", "content": "mitochondria cells"},
            ],
            user_id="user-a",
        )
        self.assertTrue(retriever.retrieve("equations", user_id="user-a", document_id="doc-a"))
        self.assertEqual(
            retriever.retrieve("mitochondria", user_id="user-a", document_id="doc-a"),
            [],
        )

    def test_storage_adapter_uploads_downloads_and_deletes(self):
        storage = FakeStorage()
        upload_document(storage, "user-a/doc-a/notes.txt", io.BytesIO(b"notes"), "text/plain")
        self.assertEqual(storage.bucket.uploads[0][1], b"notes")
        self.assertEqual(storage.bucket.uploads[0][2]["content-type"], "text/plain")

        storage.bucket.downloads["user-a/doc-a/notes.txt"] = b"notes"
        self.assertEqual(download_document(storage, "user-a/doc-a/notes.txt"), b"notes")
        delete_document(storage, "user-a/doc-a/notes.txt")
        self.assertEqual(storage.bucket.deletions, [["user-a/doc-a/notes.txt"]])


if __name__ == "__main__":
    unittest.main()
