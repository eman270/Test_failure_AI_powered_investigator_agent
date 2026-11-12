import json
from pathlib import Path

from app.services.knowledge_store import save_knowledge_chunks

chunk_files = list(Path("data/chunks").glob("*.json"))

if not chunk_files:
    raise SystemExit("No chunk files found. Upload a document first.")

data = json.loads(chunk_files[0].read_text(encoding="utf-8"))

chunks = data["chunks"]

vectors = save_knowledge_chunks(
    chunks,
    filename=data["filename"],
    content="\n\n".join(chunk["content"] for chunk in chunks),
)

print("Document:", data["filename"])
print("Number of chunks:", len(chunks))
print("Number of embeddings:", len(vectors))
print("Dimensions per embedding:", len(vectors[0]))

assert len(vectors) == len(chunks)
assert all(len(vector) == 1536 for vector in vectors)

print("Embedding test: PASS")
