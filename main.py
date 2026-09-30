import os
from collections.abc import Iterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.sse import EventSourceResponse, ServerSentEvent
from openai import (
    APIError,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
    OpenAI,
)
from pydantic import BaseModel, Field, ValidationError

from analyze_tests import iter_summary_events

load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1)


class AskResponse(BaseModel):
    answer: str


@app.post("/ask")
def ask(body: AskRequest) -> AskResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")

    client = OpenAI()
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": question}],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Failed to get an answer") from exc

    answer = completion.choices[0].message.content or ""
    return AskResponse(answer=answer)


class SummarizeRequest(BaseModel):
    test_results: str = Field(min_length=1)


def _event_data(payload: object) -> object:
    if isinstance(payload, BaseModel):
        return payload.model_dump()
    return payload


@app.post("/summarize", response_class=EventSourceResponse)
def summarize(body: SummarizeRequest) -> Iterator[ServerSentEvent]:
    test_results = body.test_results.strip()
    if not test_results:
        raise HTTPException(status_code=400, detail="Test results cannot be empty")

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")

    try:
        for kind, payload in iter_summary_events(test_results):
            yield ServerSentEvent(event=kind, data=_event_data(payload))
    except APIError as exc:
        yield ServerSentEvent(event="error", data={"detail": "Failed to summarize the test results"})
    except (ValidationError, LengthFinishReasonError, ContentFilterFinishReasonError, ValueError) as exc:
        yield ServerSentEvent(
            event="error",
            data={"detail": "The structured output could not be validated"},
        )

frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount(
        "/",
        StaticFiles(directory=frontend_dist, html=True),
        name="frontend",
    )