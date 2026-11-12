# Human input policy

Ask a human only when the failure log and retrieved project knowledge cannot answer a fact the diagnosis depends on. Use the `ask_human` tool for that question. Writing "missing information" in the diagnosis is not a substitute for calling `ask_human`.

## When to ask

- Ask when one missing fact would distinguish between otherwise plausible causes.
- Ask when the log shows an HTTP 401 and does not say whether an Authorization header was present.
- Do not ask for a cause the log or a retrieved document already states.
- Do not ask about an HTTP 403 permission or role problem unless the log itself reports 403.
- Do not ask if the human has already answered or declined.

## How to choose the question

- Ask one specific question.
- Name the fact you need, not a general request for "more context."
- For an HTTP 401 failure with no header details, ask: "Was an Authorization header included in the failing request?"
- Do not ask a second question in the same step.

## Avoid unnecessary interruptions

- Search project knowledge before asking a human.
- Skip the question when the log or the human's earlier answer already supplies the fact.
- Do not pause for information that would not change the diagnosis.
- Do not ask again after the human has answered.

## After the human answers

- Continue the investigation. Do not stop at the question.
- Treat the answer as human-reported evidence.
- Do not treat the answer as a verified root cause by itself.
- If the human declines, report that the needed fact is still missing and leave the root cause unconfirmed.
