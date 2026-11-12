from chunking import chunk_knowledge_document


chunks = chunk_knowledge_document(
    text="""
Error: HTTP 401
Evidence: Authentication token expired
Root Cause: Expired token
Solution: Refresh token
""",
    document_id="KB-001",
    document_type="known_issue"
)

print(chunks)