# Test Failure Investigation Agent

This app investigates a pytest failure. It parses the log, groups related failures, searches stored project notes, and returns a short report. The report is a hypothesis grounded in those notes. A similar past error does not prove the current root cause.

## Request path

The investigation path is:

```text
POST /api/investigate
        |
        v
FastAPI validates the body with Pydantic
        |
        v
run_investigation()
        |
        v
ADK session + Runner
        |
        v
SequentialAgent (gpt-4o-mini through LiteLLM)
        |
        +-- 1. identify_failures
        |       parse_test_failure() -> parse_pytest_log()
        |
        +-- 2. group_failures
        |       groups tests that share an exception and message
        |
        +-- 3. diagnose_failures
        |       search_project_docs() -> search_knowledge()
        |       embeddings -> Supabase RPC match_knowledge_chunks
        |
        +-- 4. recommend_fixes
        |       a next check based on the retrieved evidence
        |
        +-- 5. write_report
                final report: tests, error, hypothesis, evidence,
                recommended check, confidence, missing information
        |
        v
FastAPI returns {"answer": "..."}
```

Grouping runs before diagnosis so related failures are searched once, as a group, instead of one lookup per test.

`main.py` exposes this as `POST /api/investigate` with body `{"log": "..."}`. An empty log is rejected with HTTP 400. `run_investigation` in `agent.py` creates an in-memory ADK session, starts a `Runner` on `root_agent`, and keeps the final text from `write_report`. The runner allows at most 12 model calls.

## Folder layout

```text
main.py                         FastAPI routes
agent.py                        ADK SequentialAgent and run_investigation
pytest_parser.py                parse_pytest_log
chunking.py                     chunk_knowledge_document
app/
├── tools/
│   └── knowledge_tools.py      tools the agents call
└── services/
    ├── embeddings.py           OpenAI text-embedding-3-small
    ├── knowledge_search.py     similarity search
    └── knowledge_store.py      save a document and its chunk vectors
```

Tools are the functions an agent is allowed to call. Services are the code those tools use. Agents do not talk to Supabase or the embedding API directly.

| Layer | File | Responsibility |
| --- | --- | --- |
| API | `main.py` | Validate the request and call `run_investigation` |
| Agent | `agent.py` | Run the five specialists in order |
| Tool | `knowledge_tools.py` | `parse_test_failure`, `search_project_docs` |
| Parser | `pytest_parser.py` | Read the FAILED line, exception type, and message |
| Search | `knowledge_search.py` | Embed the query and call `match_knowledge_chunks` |
| Store | `knowledge_store.py` | Insert `knowledge_documents`, then `knowledge_chunks` |
| Embeddings | `embeddings.py` | `text-embedding-3-small`, 1536 dimensions |

Google ADK wraps each Python function in an agent's `tools` list as a callable tool. The model sees the function name, docstring, and arguments.

## What each specialist does

1. **identify_failures** calls `parse_test_failure`. That function calls `parse_pytest_log` and returns `failed_test`, `exception_type`, and `error_message`. A missing field stays null. This step does not guess a cause.

2. **group_failures** puts tests with the same exception and message into one group. One failure is one group. It does not decide a root cause.

3. **diagnose_failures** calls `search_project_docs` with the exception type and error message. The tool returns `matches`, each with `document_id`, `chunk_index`, `content`, and `similarity`. A cause is stated only when a match supports it, and the `document_id` is cited. An empty `matches` list means no relevant knowledge was found. Every diagnosis stays a hypothesis.

4. **recommend_fixes** suggests what to check next from the log, the diagnosis, and the retrieved chunks. It does not invent file names or code that were not in those chunks.

5. **write_report** writes the report from the earlier steps only.

## Other routes

These routes do not run the agent.

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/v1/health` | Returns `{"status": "ok"}` |
| POST | `/api/knowledge/documents` | Accepts a `.md` or `.txt` file up to 1 MB, plus `document_type` (`known_issue`, `runbook`, or `technical_reference`). Chunks the text, embeds the chunks, and stores them. |

`/ask` and `/summarize` are commented out in `main.py`.

## How a document becomes searchable

1. The upload route calls `chunk_knowledge_document`.
2. `known_issue` stays one chunk and is rejected above 5000 characters.
3. `runbook` and `technical_reference` split on `##` headings, then into chunks of about 1800 characters with a 180-character overlap.
4. `save_knowledge_chunks` embeds each chunk and inserts a `knowledge_documents` row first, because `knowledge_chunks.document_id` points at it.
5. Chunk embeddings are stored in Supabase. Search uses the same embedding model, then the `match_knowledge_chunks` database function.

## What is in place

- Pytest parsing, chunking, embeddings, and Supabase storage.
- Knowledge search through `search_project_docs`.
- The five-step ADK investigator on `POST /api/investigate`.
- Checks in `test_chunking.py`, `test_embeddings.py`, `test_knowledge_search.py`, and `test_knowledge_tool.py`.

The React page in `frontend/src/demo.tsx` posts the pasted log to `POST /api/investigate` and shows the returned `answer`.

## Configuration

The API reads these environment variables from `.env`:

- `OPENAI_API_KEY` for chat (`gpt-4o-mini` through LiteLLM) and embeddings.
- `SUPABASE_URL` and `SUPABASE_KEY` for the knowledge tables.

The app is packaged with the `test-failure-investigator` Docker image. The host port used for Swagger has been `8001` when `8000` is already taken.
