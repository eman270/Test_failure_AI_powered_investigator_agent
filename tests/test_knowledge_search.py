from app.services.knowledge_search import search_knowledge

query = "Login test returns HTTP 401 because the authentication token expired"

results = search_knowledge(query, limit=3)

print(f"Found {len(results)} results\n")

for result in results:
    print("Document ID:", result["document_id"])
    print("Chunk:", result["chunk_index"])
    print("Similarity:", round(result["similarity"], 3))
    print("Content:", result["content"])
    print("-" * 40)