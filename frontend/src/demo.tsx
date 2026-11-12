import { FormEvent, useRef, useState } from "react";
import PromptComposer from "@/components/ui/prompt-composer";

type InvestigationResult =
  | {
      status: "awaiting_input";
      question: string;
      adk_session_id: string;
      confirmation_call_id: string;
    }
  | {
      status: "completed";
      investigation_id: string;
      review_status: "pending";
      answer: string;
    };

type ApiBody = {
  detail?: unknown;
  status?: unknown;
  question?: unknown;
  adk_session_id?: unknown;
  confirmation_call_id?: unknown;
  investigation_id?: unknown;
  answer?: unknown;
};

function parseInvestigation(data: ApiBody): InvestigationResult | null {
  if (
    data.status === "awaiting_input" &&
    typeof data.question === "string" &&
    data.question.trim() &&
    typeof data.adk_session_id === "string" &&
    data.adk_session_id.trim() &&
    typeof data.confirmation_call_id === "string" &&
    data.confirmation_call_id.trim()
  ) {
    return {
      status: "awaiting_input",
      question: data.question,
      adk_session_id: data.adk_session_id,
      confirmation_call_id: data.confirmation_call_id,
    };
  }

  // /api/investigate omits status when the report is already finished.
  if (typeof data.answer === "string" && data.answer.trim()) {
    return {
      status: "completed",
      investigation_id:
        typeof data.investigation_id === "string" ? data.investigation_id : "",
      review_status: "pending",
      answer: data.answer,
    };
  }

  return null;
}

function failureMessage(caught: unknown): string {
  if (caught instanceof TypeError) return "Could not reach the API.";
  if (caught instanceof Error && caught.message) return caught.message;
  return "Could not reach the API.";
}

async function postJson(path: string, body: object): Promise<ApiBody> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data: ApiBody = {};
  try {
    data = (await response.json()) as ApiBody;
  } catch {
    data = {};
  }
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail : "The investigation failed");
  }
  return data;
}

const DemoOne = () => {
  const [result, setResult] = useState<InvestigationResult | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [humanAnswer, setHumanAnswer] = useState("");
  const loadingRef = useRef(false);

  const applyResponse = (data: ApiBody) => {
    const next = parseInvestigation(data);
    if (!next) {
      setError("The investigation failed");
      return;
    }
    setResult(next);
    if (next.status === "awaiting_input") {
      setHumanAnswer("");
    }
  };

  const handleSendMessage = async (message: string) => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    setIsLoading(true);
    setError("");
    setResult(null);
    setHumanAnswer("");
    try {
      const data = await postJson("/api/investigate", { log: message });
      applyResponse(data);
    } catch (caught) {
      setError(failureMessage(caught));
    } finally {
      loadingRef.current = false;
      setIsLoading(false);
    }
  };

  const handleHumanAnswer = async (event: FormEvent) => {
    event.preventDefault();
    if (loadingRef.current || result?.status !== "awaiting_input") return;
    const answer = humanAnswer.trim();
    if (!answer) return;

    loadingRef.current = true;
    setIsLoading(true);
    setError("");
    try {
      const data = await postJson("/api/investigate/respond", {
        adk_session_id: result.adk_session_id,
        confirmation_call_id: result.confirmation_call_id,
        answer,
      });
      applyResponse(data);
    } catch (caught) {
      setError(failureMessage(caught));
    } finally {
      loadingRef.current = false;
      setIsLoading(false);
    }
  };

  const pending = result?.status === "awaiting_input" ? result : null;
  const completed = result?.status === "completed" ? result : null;

  return (
    <div
      style={{
        width: "100%",
        minHeight: "100svh",
        display: "grid",
        placeItems: "center",
        padding: "48px 20px",
        background:
          "radial-gradient(40% 35% at 30% 35%, rgba(95,178,242,.28), transparent 70%), radial-gradient(35% 30% at 72% 65%, rgba(196,140,255,.22), transparent 70%), #08080a",
      }}
    >
      <div className="flex w-full max-w-[720px] flex-col items-center gap-4">
        <PromptComposer
          simulate={false}
          placeholder="Paste JUnit or pytest output..."
          prompts={[
            "Pytest: 2 failed. test_checkout AssertionError expected 200, got 500...",
            "JUnit: OrderServiceTest.testRefund failed. Expected PAID but was REFUNDED...",
            "Jest: Cart.test.ts TypeError Cannot read properties of undefined (reading total)...",
            "Go: TestChargeCard failed. Expected nil error, got context deadline exceeded...",
          ]}
          platforms={[
            { label: "Pytest", icon: "code" },
            { label: "JUnit", icon: "window" },
            { label: "Jest", icon: "bolt" },
            { label: "Go", icon: "bars" },
          ]}
          models={["gpt-4o-mini"]}
          modelNotes={["Structured failure summary"]}
          onSubmit={(submission) => {
            void handleSendMessage(submission.prompt);
          }}
        />
        {(isLoading || error || completed) && (
          <div
            className={`max-h-96 w-full overflow-auto whitespace-pre-wrap rounded-[26px] bg-[rgba(32,32,36,0.62)] p-5 text-sm shadow-[inset_0_0_0_1px_rgba(214,228,255,0.13)] ${error ? "text-red-300" : "text-[#f5f5f6]"}`}
          >
            {completed?.investigation_id
              ? `Investigation ${completed.investigation_id}\nReview ${completed.review_status}\n\n`
              : ""}
            {error ||
              completed?.answer ||
              (pending ? "Continuing the investigation..." : "Investigating the failure...")}
          </div>
        )}
        {pending && (
          <form
            onSubmit={(event) => {
              void handleHumanAnswer(event);
            }}
            className="flex w-full flex-col gap-3 rounded-[26px] bg-[rgba(32,32,36,0.62)] p-5 shadow-[inset_0_0_0_1px_rgba(214,228,255,0.13)]"
          >
            <label htmlFor="human-answer" className="text-sm text-[#f5f5f6]">
              {pending.question}
            </label>
            <textarea
              id="human-answer"
              value={humanAnswer}
              onChange={(event) => setHumanAnswer(event.target.value)}
              placeholder="Your answer"
              rows={3}
              disabled={isLoading}
              className="w-full resize-y rounded-2xl bg-black/30 px-4 py-3 text-sm text-[#f5f5f6] outline-none placeholder:text-white/40"
            />
            <button
              type="submit"
              disabled={isLoading || !humanAnswer.trim()}
              className="self-end rounded-full bg-[#f5f5f6] px-4 py-2 text-sm text-[#08080a] disabled:opacity-40"
            >
              {isLoading ? "Sending..." : "Send answer"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

export { DemoOne };
