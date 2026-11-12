import json
import os
from pathlib import Path

import pytest
import requests

BASE_URL = os.getenv("EVAL_BASE_URL", "http://localhost:8001")
DATASET_PATH = Path(__file__).with_name("golden_cases.json")

golden_cases = json.loads(
    DATASET_PATH.read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    "case",
    golden_cases,
    ids=[case["id"] for case in golden_cases],
)
def test_investigation_e2e(case):
    response = requests.post(
        f"{BASE_URL}/api/investigate",
        json={"log": case["input_log"]},
        timeout=180,
    )

    clarifications = 0
    max_clarifications = 3

    while True:
        assert response.status_code == 200, response.text
        result = response.json()

        if result.get("status") != "awaiting_input":
            break

        assert clarifications < max_clarifications, (
            "Agent requested too many clarifications"
        )

        assert result.get("question")
        assert result.get("adk_session_id")
        assert result.get("confirmation_call_id")

        print(f"\nAgent question: {result['question']}")

        human_answer = case.get(
            "clarification_answer",
            "No additional details are available. "
            "Please continue using the provided log "
            "and clearly state any uncertainty.",
        )

        response = requests.post(
            f"{BASE_URL}/api/investigate/respond",
            json={
                "adk_session_id": result["adk_session_id"],
                "confirmation_call_id": result["confirmation_call_id"],
                "answer": human_answer,
            },
            timeout=180,
        )

        clarifications += 1

    assert result.get("investigation_id")
    assert result.get("review_status") == "pending"
    assert result.get("answer", "").strip()

    # Evaluate diagnosis quality using the golden dataset
    expected = case["expected"]
    report = result["answer"].lower()

    # Check 1: Root-cause category
    assert any(
        keyword.lower() in report
        for keyword in expected["diagnosis_keywords"]
    ), f"{case['id']}: Wrong or missing diagnosis"

    # Check 2: Evidence
    for evidence in expected["required_evidence"]:
        assert evidence.lower() in report, (
            f"{case['id']}: Missing evidence: {evidence}"
        )

    print(f"QUALITY PASSED: {case['id']}")

    print(
        f"\nPASSED: {case['id']} "
        f"(clarifications: {clarifications})"
    )
