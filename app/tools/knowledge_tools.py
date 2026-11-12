
import logging

from app.services.knowledge_search import search_knowledge
from pytest_parser import parse_pytest_failures

logger = logging.getLogger(__name__)


def parse_test_failure(log: str) -> dict:
    """
    Extract all failed tests and their errors from a pytest log.

    Args:
        log: Raw pytest test failure log.

    Returns:
        Parsing status and a list of detected failures.
    """

    if not log.strip():
        return {
            "status": "error",
            "message": "Test log cannot be empty",
            "failures": [],
        }

    failures = parse_pytest_failures(log)
    return {
        "status": "success" if failures else "no_failures_found",
        "count": len(failures),
        "failures": failures,
    }


def search_project_docs(query: str) -> dict:
    """
    Search project reference documents for known errors,
    troubleshooting instructions, root causes, and solutions.

    Use this tool when investigating a test failure that
    may be explained by existing project documentation.

    Args:
        query: The error message or failure description.

    Returns:
        A dictionary containing search status and matching
        document chunks with their source IDs and similarity scores.
    """

    if not query.strip():
        return {
            "status": "error",
            "message": "Search query cannot be empty",
            "matches": []
        }

    try:
        results = search_knowledge(query.strip(), limit=3)

        matches = [
            {
                "document_id": row["document_id"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "similarity": row["similarity"]
            }
            for row in results
        ]

        return {
            "status": "success" if matches else "no_matches",
            "matches": matches
        }

    except Exception:
        logger.exception("Knowledge search failed")
        return {
            "status": "error",
            "message": "Knowledge search is unavailable",
            "matches": []
        }
