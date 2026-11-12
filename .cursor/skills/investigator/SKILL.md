---
name: investigator
description: Connect the React prompt composer to the test-failure investigator API. Use when changing frontend/src/demo.tsx, the Vite proxy, POST /api/investigate, or when the user asks how React connects to the agent.
---

# Investigator React connection

The browser sends one pytest log. FastAPI validates it and `run_investigation` returns the report.

## Current wiring

`PromptComposer` calls `onSubmit` with `submission.prompt`. `DemoOne` in `frontend/src/demo.tsx` passes that string to `handleSendMessage`, which posts it to `POST /api/investigate`.

## Target request

```ts
const response = await fetch("/api/investigate", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ log: message }),
});
```

Success body is `{ "answer": string }`. Show `answer` in the result panel. An HTTP error uses `detail` from the JSON body. A network failure keeps the existing "Could not reach the API" message.

Do not send `test_name` or `test_results`. Do not parse an event stream for this route.

## Proxy

`frontend/vite.config.ts` proxies only `/api` to `http://127.0.0.1:8010`. A fetch path must start with `/api` or the dev server will not forward it. Ports 8000 and 8001 are already taken by other containers, so the local API for this app runs on 8010.
