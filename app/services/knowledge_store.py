"""Save a knowledge document and its chunk embeddings in Supabase.

SUPABASE_URL and SUPABASE_KEY come from the environment. The document
row is written first because knowledge_chunks.document_id points at it.
"""

import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv

from app.services.embeddings import generate_embeddings

load_dotenv()

DOCUMENTS_TABLE = "knowledge_documents"
CHUNKS_TABLE = "knowledge_chunks"


class SupabaseError(RuntimeError):
    """Supabase rejected the insert or is not configured."""


def _supabase_insert(table: str, payload: object) -> None:
    """Insert one object or a list of rows through the Supabase REST API."""

    base_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not base_url or not key:
        raise SupabaseError("SUPABASE_URL or SUPABASE_KEY is not set")

    request = urllib.request.Request(
        f"{base_url}/rest/v1/{table}",
        data=json.dumps(payload).encode(),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise SupabaseError(f"Supabase returned HTTP {exc.code}: {body}") from exc


def save_knowledge_chunks(
    chunks: list[dict],
    *,
    filename: str,
    content: str,
) -> list[list[float]]:
    """Store the source document, then embed and insert its chunks.

    Each chunk needs document_id, chunk_index, and content. The chunk id
    is left for the database.
    """

    if not chunks:
        raise ValueError("Non-empty chunks are required")
    if not filename.strip() or not content.strip():
        raise ValueError("Document filename and content are required")

    document_id = chunks[0]["document_id"]
    vectors = generate_embeddings([chunk["content"] for chunk in chunks])
    _supabase_insert(
        DOCUMENTS_TABLE,
        {
            "id": document_id,
            "filename": filename,
            "content": content,
            "status": "embedded",
        },
    )
    _supabase_insert(
        CHUNKS_TABLE,
        [
            {
                "document_id": chunk["document_id"],
                "chunk_index": chunk["chunk_index"],
                "content": chunk["content"],
                "embedding": json.dumps(vector),
            }
            for chunk, vector in zip(chunks, vectors)
        ],
    )
    return vectors
