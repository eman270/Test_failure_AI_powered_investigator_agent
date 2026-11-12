from app.services.knowledge_search import search_knowledge

# TC-01: Relevant documentation exists
auth_results = search_knowledge(
    "Login test failed with HTTP 401 authentication error"
)

assert len(auth_results) > 0
print("TC-01: PASS - Relevant knowledge found")

# TC-02: No relevant documentation exists
inventory_results = search_knowledge(
    "Expected stock count 15, but got 12"
)

assert len(inventory_results) == 0
print("TC-02: PASS - Unrelated knowledge rejected")
