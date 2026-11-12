from google.adk.tools import ToolContext


def ask_human(question: str, tool_context: ToolContext) -> dict:
    """
    Ask the human for missing information during an investigation.

    Args:
        question: A specific question about the test failure.

    Returns:
        The human's answer when the investigation resumes.
    """

    if not question.strip():
        return {
            "status": "error",
            "message": "Question cannot be empty"
        }

    confirmation = tool_context.tool_confirmation

    # First call: pause and request human input.
    if confirmation is None:
        tool_context.request_confirmation(
            hint=question,
            payload={"answer": ""}
        )

        return {
            "status": "awaiting_input",
            "question": question
        }

    # Called again when the human responds.
    if not confirmation.confirmed:
        return {
            "status": "declined",
            "message": "Human declined to provide an answer"
        }

    payload = confirmation.payload or {}
    answer = payload.get("answer", "")

    if not isinstance(answer, str) or not answer.strip():
        return {
            "status": "error",
            "message": "Human answer is empty"
        }

    return {
        "status": "answered",
        "question": question,
        "answer": answer.strip()
    }
