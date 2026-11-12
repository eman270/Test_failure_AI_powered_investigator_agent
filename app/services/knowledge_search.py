"""Search stored knowledge chunks by meaning.

The query is embedded with the same model used at upload time, then
matched through the Supabase function match_knowledge_chunks.
"""

import os

from dotenv import load_dotenv
from supabase import create_client

from app.services.embeddings import generate_embeddings

load_dotenv()

MIN_SIMILARITY = 0.40


def search_knowledge(
    query: str,
    limit: int = 3
) -> list[dict]:
    """Return the closest stored chunks for a query.

    Each result includes document_id, chunk_index, similarity, and content.
    An empty query is rejected before the embedding API is called.
    """

    if not query.strip():
        raise ValueError("Search query cannot be empty")

    query_embedding = generate_embeddings([query])[0]

    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"]
    )

    response = client.rpc(
        "match_knowledge_chunks",
        {
            "p_query_embedding": query_embedding,
            "p_match_count": limit
        }
    ).execute()

    results = response.data or []

    relevant_results = [
        row for row in results
        if row["similarity"] >= MIN_SIMILARITY
    ]

    return relevant_results
