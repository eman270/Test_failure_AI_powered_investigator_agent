from app.tools.knowledge_tools import search_project_docs

result = search_project_docs(
    "Login test failed because of an HTTP 401 authentication error"
)

print("Status:", result["status"])

for match in result["matches"]:
    print("Document ID:", match["document_id"])
    print("Similarity:", match["similarity"])
    print("Content:", match["content"])
    print("-" * 40)

assert result["status"] == "success"
assert len(result["matches"]) > 0

print("Knowledge Tool: PASS")
