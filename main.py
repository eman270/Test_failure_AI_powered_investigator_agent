import logging
import os
from pathlib import Path
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent import resume_investigation, run_investigation
from app.services.investigation_store import save_investigation
from chunking import chunk_knowledge_document
from app.services.knowledge_store import SupabaseError, save_knowledge_chunks
from app.services.episodic_memory import EpisodicMemory

logger = logging.getLogger(__name__)

# from collections.abc import Iterator
#
# from fastapi.sse import EventSourceResponse, ServerSentEvent
# from openai import (
#     APIError,
#     ContentFilterFinishReasonError,
#     LengthFinishReasonError,
#     OpenAI,
# )
# from pydantic import ValidationError
#
# from analyze_tests import iter_summary_events

load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class HealthResponse(BaseModel):
    status: str


@app.get("/api/v1/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok")


class InvestigateRequest(BaseModel):
    log: str = Field(min_length=1)


async def save_completed_investigation(result: dict) -> str:
    """Save completed report and available failure-group memories."""

    report = result["answer"].strip()

    # 1. Save the complete report
    investigation_id = await run_in_threadpool(
        save_investigation,
        report,
    )

    # 2. Get structured groups returned by ADK
    memory_groups = result.get("memory_groups")

    if not memory_groups:
        logger.warning(
            "Investigation %s: memory groups not available yet",
            investigation_id,
        )
        return str(investigation_id)

    # 3. Save development-only episodic memories.
    # A failure here keeps the report that was already saved.
    try:
        memory = EpisodicMemory()
        await run_in_threadpool(
            memory.save_groups,
            investigation_id=str(investigation_id),
            groups=memory_groups,
            mode="development",
        )
    except Exception:
        logger.exception(
            "Report %s saved, but episodic memory failed",
            investigation_id,
        )

    return str(investigation_id)


@app.post("/api/investigate")
async def investigate(body: InvestigateRequest) -> dict:
    log = body.log.strip()
    if not log:
        raise HTTPException(
            status_code=400,
            detail="The test log cannot be empty"
        )

    result = await run_investigation(log)
    
    # The agent paused because it needs human input.
    if result.get("status") == "awaiting_input":
        return {
            "status": "awaiting_input",
            "question": result["question"],
            "adk_session_id": result["adk_session_id"],
            "confirmation_call_id": result["confirmation_call_id"],
        }

    if result.get("error"):
        raise HTTPException(
            status_code=502,
            detail=result["error"]
        )

    report = result.get("answer", "").strip()
    if not report or report == "(no response)":
        raise HTTPException(
            status_code=502,
            detail="Agent did not generate a report"
        )

    try:
        investigation_id = await save_completed_investigation(result)
    except Exception:
        logger.exception("Failed to save investigation")
        raise HTTPException(
            status_code=502,
            detail="Investigation generated but could not be saved"
        )

    return {
        "investigation_id": investigation_id,
        "review_status": "pending",
        "answer": report
    }


class HumanAnswerRequest(BaseModel):
    adk_session_id: str = Field(min_length=1)
    confirmation_call_id: str = Field(min_length=1)
    answer: str = Field(min_length=1)


@app.post("/api/investigate/respond")
async def respond_to_human(body: HumanAnswerRequest) -> dict:
    # 1. Resume the paused ADK session
    result = await resume_investigation(
        session_id=body.adk_session_id,
        confirmation_call_id=body.confirmation_call_id,
        human_answer=body.answer.strip(),
    )

    if result.get("error"):
        raise HTTPException(
            status_code=400,
            detail=result["error"]
        )

    # 2. The agent may ask another question
    if result.get("status") == "awaiting_input":
        return result

    if result.get("status") != "completed":
        raise HTTPException(
            status_code=502,
            detail="Investigation did not complete"
        )

    # 3. Save the completed report
    report = result["answer"]
    try:
        investigation_id = await save_completed_investigation(result)
    except Exception:
        logger.exception("Failed to save resumed investigation")
        raise HTTPException(
            status_code=502,
            detail="Investigation generated but could not be saved"
        )

    return {
        "investigation_id": investigation_id,
        "status": "completed",
        "review_status": "pending",
        "answer": report,
    }


UPLOAD_DIR = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "uploads"
)

MAX_FILE_SIZE = 1024 * 1024  # 1 MB
ALLOWED_EXTENSIONS = {".md", ".txt"}


@app.post("/api/knowledge/documents", status_code=201)
async def upload_knowledge_document(
    file: UploadFile = File(...),
    document_type: Literal[
        "known_issue",
        "runbook",
        "technical_reference"
    ] = Form(...)
):
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only Markdown and TXT files are supported"
        )

    content = await file.read(MAX_FILE_SIZE + 1)
    await file.close()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File is too large"
        )

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="File must contain UTF-8 text"
        )

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="Document cannot be empty"
        )

    document_id = str(uuid4())

    # Apply our structure-aware chunking
    try:
        chunks = chunk_knowledge_document(
            text=text,
            document_id=document_id,
            document_type=document_type
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )

    try:
        save_knowledge_chunks(chunks, filename=filename, content=text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except SupabaseError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = UPLOAD_DIR / f"{document_id}{extension}"
    saved_path.write_text(text, encoding="utf-8")

    return {
        "document_id": document_id,
        "filename": filename,
        "document_type": document_type,
        "chunk_count": len(chunks),
        "status": "embedded"
    }


# class AskRequest(BaseModel):
#     question: str = Field(min_length=1)
#
#
# class AskResponse(BaseModel):
#     answer: str
#
#
# @app.post("/ask")
# def ask(body: AskRequest) -> AskResponse:
#     question = body.question.strip()
#     if not question:
#         raise HTTPException(status_code=400, detail="Question cannot be empty")
#
#     if not os.getenv("OPENAI_API_KEY"):
#         raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")
#
#     client = OpenAI()
#     try:
#         completion = client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[{"role": "user", "content": question}],
#         )
#     except Exception as exc:
#         raise HTTPException(status_code=502, detail="Failed to get an answer") from exc
#
#     answer = completion.choices[0].message.content or ""
#     return AskResponse(answer=answer)
#
#
# class SummarizeRequest(BaseModel):
#     test_results: str = Field(min_length=1)
#
#
# def _event_data(payload: object) -> object:
#     if isinstance(payload, BaseModel):
#         return payload.model_dump()
#     return payload
#
#
# @app.post("/summarize", response_class=EventSourceResponse)
# def summarize(body: SummarizeRequest) -> Iterator[ServerSentEvent]:
#     test_results = body.test_results.strip()
#     if not test_results:
#         raise HTTPException(status_code=400, detail="Test results cannot be empty")
#
#     if not os.getenv("OPENAI_API_KEY"):
#         raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")
#
#     try:
#         for kind, payload in iter_summary_events(test_results):
#             yield ServerSentEvent(event=kind, data=_event_data(payload))
#     except APIError as exc:
#         yield ServerSentEvent(event="error", data={"detail": "Failed to summarize the test results"})
#     except (ValidationError, LengthFinishReasonError, ContentFilterFinishReasonError, ValueError) as exc:
#         yield ServerSentEvent(
#             event="error",
#             data={"detail": "The structured output could not be validated"},
#         )


frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount(
        "/",
        StaticFiles(directory=frontend_dist, html=True),
        name="frontend",
    )
