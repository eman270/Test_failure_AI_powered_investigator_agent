import logging

from app.services.episodic_memory import EpisodicMemory

logger = logging.getLogger("episodic_memory")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)
logger.propagate = False


def search_past_failures(query: str) -> dict:
    """Search similar failures from previous investigations."""

    logger.info("search_past_failures called query=%r", query)

    memory = EpisodicMemory()

    matches = memory.search_similar_failures(
        query=query,
        limit=3,
    )

    if not matches:
        logger.info("search_past_failures returned no matches")
    else:
        summary = "; ".join(
            "case_id=%s similarity=%s error=%r"
            % (
                match.get("case_id"),
                match.get("similarity"),
                match.get("error_signature"),
            )
            for match in matches
        )
        logger.info(
            "search_past_failures returned %s match(es): %s",
            len(matches),
            summary,
        )

    return {
        "status": "success",
        "matches": matches,
    }
