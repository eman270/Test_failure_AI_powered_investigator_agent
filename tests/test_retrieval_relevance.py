from app.services.knowledge_search import search_knowledge

test_cases = {
    "TC-01 Authentication": (
        "Login test failed with HTTP 401 authentication error"
    ),
    "TC-02 Inventory": (
        "Expected stock count 15, but got 12"
    ),
}

for test_name, query in test_cases.items():
    print(f"\n{test_name}")
    print("-" * 50)

    results = search_knowledge(query, limit=3)

    for result in results:
        print(
            "Similarity:",
            round(result["similarity"], 3)
        )
        print(
            "Content:",
            result["content"][:150]
        )
        print("-" * 30)
