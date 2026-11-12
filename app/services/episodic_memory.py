"""Save episodic memory: one verified_failure_cases row per failure group.

EpisodicMemory.save_groups handles one group or many. Each row gets an
embedding of that group's tests, error, cause, and solution. The full ADK
report stays in the investigations table.

mode="verified" stores a human-confirmed cause and solution.
mode="development" is allowed only when EPISODIC_DEV_MODE=true. It labels
the text as an unverified AI hypothesis so it is not treated as trusted.
"""

import os
from uuid import UUID

from dotenv import load_dotenv
from supabase import create_client

from app.services.embeddings import generate_embeddings

load_dotenv()


class EpisodicMemory:
    """Insert confirmed failure groups into verified_failure_cases."""

    def __init__(self) -> None:
        key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ["SUPABASE_KEY"]
        self.client = create_client(
            os.environ["SUPABASE_URL"],
            key,
        )

    def save_groups(
        self,
        investigation_id: str,
        groups: list[dict],
        mode: str,
    ) -> list[dict]:
        """Embed and insert one row per failure group."""

        if mode not in {"verified", "development"}:
            raise ValueError("Invalid episodic memory mode")

        if mode == "development" and not _development_mode_enabled():
            raise ValueError("Development episodic memory is disabled")

        try:
            investigation_id = str(UUID(str(investigation_id)))
        except ValueError:
            raise ValueError("Invalid investigation ID")

        if not groups:
            return []

        rows = []
        seen_group_numbers = set()

        for group in groups:
            number = group["group_number"]
            tests = group["affected_tests"]
            error = group["error_signature"].strip()
            cause = group["confirmed_root_cause"].strip()
            solution = group["verified_solution"].strip()
            notes = (group.get("verification_notes") or "").strip()

            if not isinstance(number, int) or number < 1:
                raise ValueError("Invalid group number")

            if number in seen_group_numbers:
                raise ValueError("Duplicate group number")

            seen_group_numbers.add(number)

            if (
                not isinstance(tests, list)
                or not tests
                or not all(isinstance(test, str) and test.strip() for test in tests)
            ):
                raise ValueError("Affected tests are required")

            if not error or not cause or not solution:
                raise ValueError("Root cause, error and solution are required")

            tests = [test.strip() for test in tests]

            if mode == "development":
                cause = "[UNVERIFIED AI HYPOTHESIS] " + cause
                solution = "[UNVERIFIED AI SUGGESTION] " + solution
                notes = "DEV_SIMULATED_NOT_VERIFIED. " + notes

            memory_text = (
                f"Tests: {', '.join(tests)}\n"
                f"Error: {error}\n"
                f"Root cause: {cause}\n"
                f"Solution: {solution}"
            )

            rows.append({
                "investigation_id": investigation_id,
                "group_number": number,
                "affected_tests": tests,
                "error_signature": error,
                "confirmed_root_cause": cause,
                "verified_solution": solution,
                "verification_notes": notes or None,
                "_memory_text": memory_text,
            })

        embeddings = generate_embeddings([
            row["_memory_text"][:12000]
            for row in rows
        ])

        if len(embeddings) != len(rows):
            raise RuntimeError("Embedding count mismatch")

        for row, embedding in zip(rows, embeddings):
            row.pop("_memory_text")
            row["embedding"] = embedding

        response = (
            self.client.table("verified_failure_cases")
            .insert(rows)
            .execute()
        )

        return response.data or []

    def search_similar_failures(
        self,
        query: str,
        limit: int = 3,
    ) -> list[dict]:
        """Search past failure groups using vector similarity."""

        if not query.strip():
            return []

        query_embedding = generate_embeddings([query])[0]

        response = (
            self.client.rpc(
                "match_failure_memories",
                {
                    "query_embedding": query_embedding,
                    "match_count": limit,
                },
            )
            .execute()
        )

        return response.data or []


def _development_mode_enabled() -> bool:
    return os.environ.get("EPISODIC_DEV_MODE", "").strip().lower() == "true"
