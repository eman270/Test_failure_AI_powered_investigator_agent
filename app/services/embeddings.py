"""Turn text into vectors with OpenAI text-embedding-3-small.

The OpenAI key is read from the environment. Callers pass a list of
strings and get one 1536-dimension vector per string, in the same order.
"""

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = "text-embedding-3-small"


def generate_embeddings(
    texts: list[str]
) -> list[list[float]]:
    """Embed each text and keep the result aligned with the input.

    An empty list or a blank string is rejected before the API is called.
    The response is sorted by the index OpenAI sends back, so a vector
    at position 0 always belongs to the first text.
    """

    if not texts or any(not text.strip() for text in texts):
        raise ValueError("Non-empty chunks are required")

    client = OpenAI()

    response = client.embeddings.create(
        model=MODEL,
        input=texts,
        encoding_format="float"
    )

    # Preserve the order of the input chunks.
    # The embedding API accepts an array of strings in one request.
    ordered = sorted(
        response.data,
        key=lambda item: item.index
    )

    return [item.embedding for item in ordered]
