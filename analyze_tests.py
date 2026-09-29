import os
import sys
from collections.abc import Iterator

from dotenv import load_dotenv
from openai import (
    APIError,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
    OpenAI,
)
from pydantic import BaseModel, Field, ValidationError

# Paste JUnit or pytest output between the quotes, then run this file.
TEST_RESULTS = """
"""

PROMPT = """You are a software test failure analyst.

Analyze the provided JUnit or pytest test results.

For each failed or errored test:
- Identify the test name.
- Identify the error type.
- Extract the error message.
- Extract the expected result if available.
- Extract the actual result if available.

Do not determine the root cause.
Do not suggest fixes.
Do not invent information that is not present in the test results.

Return the result using the required structured output."""


class TestFailure(BaseModel):
    test_name: str = Field(description="Name of the failed or errored test.")
    error_type: str = Field(description="Exception or error type from the results.")
    message: str = Field(description="Error message copied from the results.")
    expected: str | None = Field(
        default=None,
        description="Expected value if the results include one. Otherwise null.",
    )
    actual: str | None = Field(
        default=None,
        description="Actual value if the results include one. Otherwise null.",
    )


class TestSummary(BaseModel):
    total_tests: int = Field(description="Total number of tests reported.")
    failures: int = Field(description="Number of failed tests.")
    errors: int = Field(description="Number of errored tests.")
    failed_tests: list[TestFailure] = Field(
        description="One entry for each failed or errored test."
    )


def iter_summary_events(test_results: str) -> Iterator[tuple[str, object]]:
    """Yield partial objects while the model writes, then the validated summary."""
    client = OpenAI()
    saw_summary = False
    previous_partial = None
    with client.chat.completions.stream(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": test_results},
        ],
        response_format=TestSummary,
    ) as stream:
        for event in stream:
            if event.type == "content.delta" and event.parsed and event.parsed != previous_partial:
                previous_partial = event.parsed
                yield "delta", event.parsed
            elif event.type == "content.done":
                if not isinstance(event.parsed, TestSummary):
                    raise ValueError("The model did not return a valid TestSummary.")
                saw_summary = True
                yield "summary", event.parsed
            elif event.type == "refusal.done":
                raise ValueError(f"The model refused the request: {event.refusal}")

    if not saw_summary:
        raise ValueError("The model did not return a valid TestSummary.")


def summarize_tests(test_results: str) -> TestSummary:
    summary = None
    for kind, payload in iter_summary_events(test_results):
        if kind == "summary":
            summary = payload
    if not isinstance(summary, TestSummary):
        raise ValueError("The model did not return a valid TestSummary.")
    return summary


if __name__ == "__main__":
    load_dotenv()

    if not os.getenv("OPENAI_API_KEY"):
        print(
            "Error: OPENAI_API_KEY is not set. Add it to a .env file in this folder.",
            file=sys.stderr,
        )
        sys.exit(1)

    test_results = TEST_RESULTS.strip()
    if not test_results:
        print(
            "Error: test results are empty. Paste them into TEST_RESULTS in analyze_tests.py.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        summary = summarize_tests(test_results)
    except APIError as exc:
        print(f"Error: the OpenAI API request failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except (ValidationError, LengthFinishReasonError, ContentFilterFinishReasonError, ValueError) as exc:
        print(f"Error: the structured output could not be validated: {exc}", file=sys.stderr)
        sys.exit(1)

    print(summary.model_dump_json(indent=2))
