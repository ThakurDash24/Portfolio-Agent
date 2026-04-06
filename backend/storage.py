"""
Supabase Storage helper.
Handles file uploads to the 'uploads' bucket and returns public URLs.
"""
import uuid
from supabase_client import supabase

BUCKET = "uploads"


def upload_file(file_bytes: bytes, filename: str, content_type: str) -> dict | None:
    """
    Upload raw bytes to the Supabase 'uploads' bucket.
    Returns {"path": unique_name, "url": public_url} or None on failure.
    """
    unique_name = f"{uuid.uuid4().hex}_{filename}"

    try:
        supabase.storage.from_(BUCKET).upload(
            path=unique_name,
            file=file_bytes,
            file_options={"content-type": content_type},
        )

        url = supabase.storage.from_(BUCKET).get_public_url(unique_name)
        print(f"[Storage] Uploaded → {url}")
        return {"path": unique_name, "url": url}

    except Exception as e:
        print(f"[Storage] Upload failed for '{filename}': {e}")
        return None
