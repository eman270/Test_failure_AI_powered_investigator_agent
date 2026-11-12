import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()


def save_investigation(report: str) -> str:
    """Save an agent report and return its investigation ID."""

    if not report.strip():
        raise ValueError("Investigation report cannot be empty")

    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ["SUPABASE_KEY"]
    client = create_client(
        os.environ["SUPABASE_URL"],
        key,
    )

    response = (
        client.table("investigations")
        .insert({
            "report": report
        })
        .select("id")
        .execute()
    )

    if not response.data:
        raise RuntimeError("Investigation was not saved")

    return response.data[0]["id"]
