import os
from typing import BinaryIO


STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "exam-documents")


def upload_document(storage, path: str, file: BinaryIO, content_type: str, bucket: str = STORAGE_BUCKET) -> None:
    payload = file.read()
    storage.from_(bucket).upload(
        path,
        payload,
        {"content-type": content_type, "upsert": False},
    )


def download_document(storage, path: str, bucket: str = STORAGE_BUCKET) -> bytes:
    return storage.from_(bucket).download(path)


def delete_document(storage, path: str, bucket: str = STORAGE_BUCKET) -> None:
    storage.from_(bucket).remove([path])
