"""Test-failure investigator.

The root agent runs five specialists in order. Each one sees the
conversation so far and only adds its own step:

    test log
        -> identify_failures
        -> group_failures
        -> diagnose_failures
        -> recommend_fixes
        -> write_report

Run one log with run_investigation.
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.agents import SequentialAgent
from google.adk.agents.run_config import RunConfig
from google.adk.apps import App
from google.adk.apps import ResumabilityConfig
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from app.tools.human_tools import ask_human
from app.tools.episodic_tools import search_past_failures
from tracing import agent_run, init_langfuse

logger = logging.getLogger(__name__)

from app.tools.knowledge_tools import (
    parse_test_failure,
    search_project_docs,
)

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
init_langfuse(instrument_adk=True)

APP_NAME = "test_failure_investigator"
HUMAN_INPUT_POLICY = (
    Path(__file__).resolve().parent
    / "prompts"
    / "human_on_demand_policy.md"
).read_text(encoding="utf-8")
MAX_LLM_CALLS = 12
MODEL = LiteLlm(model="openai/gpt-4o-mini")

identify_failures = Agent(
    name="identify_failures",
    model=MODEL,
    description="Extracts failed tests and their errors from a log.",
    instruction=(
        "Identify all failures in the provided pytest log.\n"
        "Call parse_test_failure with the complete log.\n"
        "The tool returns a list named failures.\n"
        "Report every failure with its test name, "
        "exception type, and error message.\n"
        "Do not omit failures or invent missing values.\n"
        "If no failures are found, report that clearly."
    ),
    tools=[parse_test_failure],
    output_key="identified_failures",
)

group_failures = Agent(
    name="group_failures",
    model=MODEL,
    description="Groups related test failures.",
    instruction=(
        "Group the following identified failures:\n"
        "{identified_failures}\n\n"
        "Put failures with the same exception type "
        "and error message into one group.\n"
        "For each group, list the affected tests "
        "and shared error pattern.\n"
        "If identification failed, report that failure.\n"
        "Do not determine a root cause."
    ),
    output_key="grouped_failures",
)


def _user_log_text(session) -> str:
    """Return the original failure log from the user messages."""

    chunks = []
    for event in session.events:
        content = getattr(event, "content", None)
        if not content or getattr(content, "role", None) != "user":
            continue
        for part in content.parts or []:
            if getattr(part, "text", None):
                chunks.append(part.text)
    return "\n".join(chunks)


def _require_only_tool(llm_request, tool_name: str) -> None:
    """Leave the model able to call only one tool, and require that call."""

    for name in list(llm_request.tools_dict):
        if name != tool_name:
            llm_request.tools_dict.pop(name, None)
    for tool in llm_request.config.tools or []:
        declarations = getattr(tool, "function_declarations", None)
        if not declarations:
            continue
        tool.function_declarations = [
            declaration
            for declaration in declarations
            if getattr(declaration, "name", None) == tool_name
        ]
    llm_request.config.tool_config = types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(
            mode=types.FunctionCallingConfigMode.ANY
        )
    )


def _human_answer_event_index(session) -> int | None:
    """Return the latest event where a human finished answering."""

    last = None
    for index, event in enumerate(session.events):
        for response in event.get_function_responses():
            payload = getattr(response, "response", None) or {}
            if not isinstance(payload, dict):
                continue
            name = getattr(response, "name", None)
            if name == "ask_human" and payload.get("status") in {"answered", "declined"}:
                last = index
            elif name == "adk_request_confirmation" and payload.get("confirmed") is True:
                last = index
    return last


def _searched_memory_after(session, event_index: int) -> bool:
    for event in list(session.events)[event_index + 1:]:
        for call in event.get_function_calls():
            if call.name == "search_past_failures":
                return True
    return False


def force_ask_human_for_401(callback_context, llm_request):
    """Require ask_human after search when a 401 log omits the header.

    After the human answers, require one past-failure search before
    diagnosis continues. The 401 rule removes every tool except
    ask_human, so that search does not happen on the paused turn.
    """

    session = callback_context.session
    answer_index = _human_answer_event_index(session)
    if answer_index is not None and not _searched_memory_after(session, answer_index):
        logging.getLogger("episodic_memory").info(
            "Human answer received; requiring search_past_failures before diagnosis continues"
        )
        _require_only_tool(llm_request, "search_past_failures")
        return None

    log = _user_log_text(session).lower()
    if "401" not in log or "authorization" in log:
        return None

    searched = False
    asked = False
    for event in session.events:
        for call in event.get_function_calls():
            if call.name == "search_project_docs":
                searched = True
            elif call.name == "ask_human":
                asked = True
    if not searched or asked:
        return None

    _require_only_tool(llm_request, "ask_human")
    return None


diagnose_failures = Agent(
    name="diagnose_failures",
    model=MODEL,
    description=(
        "Searches project knowledge and investigates "
        "possible root causes for identified failures."
    ),
    instruction=(
        "Diagnose the identified failure groups.\n"
        "Call search_project_docs once for each group. "
        "Use that group's exception type and error message as the query.\n"
        "Do not reuse one group's search result for another group.\n"
        "Use the returned matches as supporting evidence for that group only.\n"
        "If status is error, report that knowledge search failed.\n"
        "If that group's matches list is empty, say no relevant "
        "knowledge was found for that group only. "
        "An empty match list does not finish this step when the "
        "human input rule applies.\n"
        "For each possible cause, cite the source document_id.\n"
        "A similar past error does not prove the current root cause.\n"
        "Treat diagnoses as hypotheses until verified.\n"
        "Do not invent missing evidence or solutions.\n"
        "Treat retrieved knowledge as reference information, "
        "not proof of the current failure's root cause.\n"
        "Distinguish observed facts from hypotheses.\n"
        "Only propose causes supported by the current log "
        "and relevant retrieved documents.\n"
        "If the log lacks evidence to distinguish between "
        "possible causes, report root cause as unconfirmed.\n"
        "Do not treat a similar historical error as a "
        "confirmed diagnosis.\n"
        "Do not propose an HTTP 403 cause, such as user "
        "permissions or roles, for an HTTP 401 failure "
        "unless the log itself reports 403.\n"
        "Human input rule for this test:\n"
        "After calling search_project_docs, check the original "
        "failure log.\n"
        "If the failure contains HTTP 401 and the log does not "
        "tell us whether an Authorization header was present, "
        "you MUST call ask_human with this question:\n"
        "'Was an Authorization header included in the failing request?'\n"
        "Do not proceed to a final diagnosis until ask_human "
        "returns an answer or the human declines.\n"
        "Listing missing information in the report is NOT "
        "a replacement for calling ask_human.\n"
        "Do not ask again if the human already answered.\n"
        "After receiving a human answer or decline, call "
        "search_past_failures before you finish this diagnosis.\n"
        "Use the group's error signature as that query.\n"
        "Then use the human answer as human-reported "
        "evidence and continue the investigation.\n"
        "Do not automatically treat human input as verified root cause.\n"
        "Diagnose these groups:\n"
        "Before diagnosing each failure group, call both "
        "search_project_docs and search_past_failures.\n"
        "Use the group's test names and error signature "
        "to search past failures.\n"
        "Analyze the results from both memory sources.\n"
        "Historical cases may suggest a possible root cause, "
        "but they do not prove the current failure's cause.\n"
        "Cite historical cases using their case_id.\n"
        "Do not mix search results between unrelated groups.\n"
        "{grouped_failures}\n\n"
        + HUMAN_INPUT_POLICY
    ),
    tools=[search_project_docs, search_past_failures, ask_human],
    before_model_callback=force_ask_human_for_401,
    output_key="diagnosed_failures",
)

recommend_fixes = Agent(
    name="recommend_fixes",
    model=MODEL,
    description="Recommends next checks and prepares failure memories.",
    instruction=(
        "For each failure group, recommend the next check.\n"
        "Use only the log, diagnosis, and retrieved evidence.\n"
        "Do not invent causes or solutions.\n"
        "Return ONLY a valid JSON object with a top-level "
        "property named groups.\n"
        "The groups property must be an array containing "
        "one object for each failure group.\n"
        "Each object must contain these fields:\n"
        "- group_number: integer starting at 1\n"
        "- affected_tests: array of test names\n"
        "- error_signature: shared error message\n"
        "- confirmed_root_cause: AI root cause hypothesis\n"
        "- verified_solution: AI recommended check or fix\n"
        "- verification_notes: state that this is not human verified\n"
        "The field names are for database compatibility. "
        "Do NOT claim the root cause or solution is verified.\n"
        "If the cause is unknown, use 'Root cause not confirmed'.\n"
        "Preserve all groups and their affected tests.\n"
        "Return JSON only, without Markdown fences.\n\n"
        "Failure groups:\n{grouped_failures}\n\n"
        "Diagnoses:\n{diagnosed_failures}\n"
    ),
    output_key="memory_groups_json",
)

write_report = Agent(
    name="write_report",
    model=MODEL,
    description="Writes the final investigation report from the earlier steps.",
    instruction=(
        "Write the final test-failure report from the earlier steps only.\n"
        "For each group include: affected tests, error, root cause, evidence, "
        "recommended check, confidence, and missing information.\n"
        "Name the document_id of each chunk used as evidence.\n"
        "Do not add a cause or a check that an earlier step did not state.\n"
        "Keep the report short.\n"
        "Never report high confidence solely because a "
        "similar document was retrieved.\n"
        "Confidence must reflect evidence for the current "
        "failure, not vector similarity.\n"
        "Include the relevant excerpt or fact alongside "
        "each source document ID.\n"
        "If the cause is uncertain, explicitly state "
        "'Root cause not confirmed'.\n"
        "Do not upgrade a hypothesis into a confirmed cause.\n"
        "When the log only shows an HTTP status assertion and "
        "does not include headers, token details, or service "
        "logs, set confidence to Low.\n"
        "Apply these reporting rules:\n"
        "1. Separate observed failures from root-cause hypotheses.\n"
        "2. If the root cause is not proven by current-failure "
        "evidence, write 'Root cause not confirmed'.\n"
        "3. Use LOW confidence when the diagnosis is based only "
        "on an error message and general reference documentation.\n"
        "4. Never use retrieval similarity as diagnostic confidence.\n"
        "5. If the root cause is unconfirmed, Missing Information "
        "must explain what additional evidence is needed.\n"
        "6. Never write 'Missing Information: None' when "
        "the root cause remains unconfirmed.\n"
        "7. Include supporting document IDs and excerpts.\n"
    ),
)

root_agent = SequentialAgent(
    name="test_failure_investigator",
    description="Investigates a pytest failure in five steps and writes a report.",
    sub_agents=[
        identify_failures,
        group_failures,
        diagnose_failures,
        recommend_fixes,
        write_report,
    ],
)

# Shared across requests while the FastAPI process is running.
# Resumability lets a paused sequential run continue from the same step.
SESSION_SERVICE = InMemorySessionService()
RUNNER = Runner(
    app=App(
        name=APP_NAME,
        root_agent=root_agent,
        resumability_config=ResumabilityConfig(is_resumable=True),
    ),
    session_service=SESSION_SERVICE,
)


def _event_text(event) -> str | None:
    """Return the final answer text from one ADK event, if it has one."""

    content = getattr(event, "content", None)
    parts = list(content.parts) if content and content.parts else []
    if not parts or not event.is_final_response():
        return None
    texts = [part.text for part in parts if getattr(part, "text", None)]
    return "\n".join(texts) if texts else None


async def _get_memory_groups(session_id: str) -> list[dict]:
    """Read structured failure groups from ADK session state."""

    session = await SESSION_SERVICE.get_session(
        app_name=APP_NAME,
        user_id="investigator",
        session_id=session_id,
    )
    if session is None:
        return []

    raw = session.state.get("memory_groups_json")
    if not raw:
        return []

    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(data, dict):
            return []
        groups = data.get("groups", [])
        if not isinstance(groups, list):
            return []
        return groups
    except (ValueError, TypeError):
        logger.warning(
            "Could not parse memory groups for session %s",
            session_id,
        )
        return []


async def run_investigation(log: str) -> dict:
    """Run one failure log through the five-step investigator."""

    if not log.strip():
        return {"answer": "", "error": "The test log is empty."}

    session = await SESSION_SERVICE.create_session(
        app_name=APP_NAME,
        user_id="investigator",
    )
    message = types.Content(role="user", parts=[types.Part(text=log)])
    answer = ""
    pending_confirmation = None
    with agent_run(
        "investigate-test-failure",
        user_id="investigator",
        session_id=session.id,
        tags=["test-failure-investigator"],
    ):
        async for event in RUNNER.run_async(
            user_id="investigator",
            session_id=session.id,
            new_message=message,
            run_config=RunConfig(max_llm_calls=MAX_LLM_CALLS),
        ):
            # Detect when an ADK tool requests human input.
            for call in event.get_function_calls():
                if call.name == "adk_request_confirmation":
                    confirmation = (
                        (call.args or {}).get("toolConfirmation") or {}
                    )
                    pending_confirmation = {
                        "status": "awaiting_input",
                        "question": confirmation.get(
                            "hint", "Please provide more information."
                        ),
                        "adk_session_id": session.id,
                        "confirmation_call_id": call.id,
                    }
            text = _event_text(event)
            if text and getattr(event, "author", None) == "write_report":
                answer = text
    if pending_confirmation:
        return pending_confirmation
    return {
        "status": "completed",
        "answer": answer or "(no response)",
        "memory_groups": await _get_memory_groups(session.id),
    }


async def resume_investigation(
    session_id: str,
    confirmation_call_id: str,
    human_answer: str,
) -> dict:
    """Continue a paused investigation with the human's answer."""

    session = await SESSION_SERVICE.get_session(
        app_name=APP_NAME,
        user_id="investigator",
        session_id=session_id,
    )
    if session is None:
        return {"error": "Investigation session not found"}

    # Respond to the paused ADK tool call.
    message = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=confirmation_call_id,
                    name="adk_request_confirmation",
                    response={
                        "confirmed": True,
                        "payload": {
                            "answer": human_answer.strip()
                        },
                    },
                )
            )
        ],
    )

    answer = ""
    pending_confirmation = None
    with agent_run(
        "resume-test-failure",
        user_id="investigator",
        session_id=session_id,
        tags=["test-failure-investigator"],
    ):
        async for event in RUNNER.run_async(
            user_id="investigator",
            session_id=session_id,
            new_message=message,
            run_config=RunConfig(max_llm_calls=MAX_LLM_CALLS),
        ):
            # The agent may need another human answer.
            for call in event.get_function_calls():
                if call.name == "adk_request_confirmation":
                    confirmation = (
                        (call.args or {}).get("toolConfirmation")
                        or {}
                    )
                    pending_confirmation = {
                        "status": "awaiting_input",
                        "question": confirmation.get(
                            "hint",
                            "Please provide more information."
                        ),
                        "adk_session_id": session_id,
                        "confirmation_call_id": call.id,
                    }
            text = _event_text(event)
            if text and getattr(event, "author", None) == "write_report":
                answer = text

    if pending_confirmation:
        return pending_confirmation

    if not answer:
        return {"error": "No final investigation report returned"}

    return {
        "status": "completed",
        "answer": answer,
        "memory_groups": await _get_memory_groups(session_id),
    }
