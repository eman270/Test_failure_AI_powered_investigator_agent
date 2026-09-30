import { useState } from "react";
import { PromptInputBox } from "@/components/ui/ai-prompt-box";

function applySseChunk(
  chunk: string,
  onEvent: (event: string, data: unknown) => void,
) {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return;
  onEvent(event, JSON.parse(dataLines.join("\n")));
}

const DemoOne = () => {
  const [summary, setSummary] = useState<unknown>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSendMessage = async (message: string) => {
    setIsLoading(true);
    setError("");
    setSummary(null);
    try {
      const response = await fetch("/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ test_results: message }),
      });
      if (!response.ok) {
        const data = await response.json();
        const detail = data.detail;
        setError(typeof detail === "string" ? detail : "The API request failed");
        return;
      }
      if (!response.body) {
        setError("The API returned an empty stream.");
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          applySseChunk(chunk, (event, data) => {
            if (event === "error") {
              const detail = (data as { detail?: unknown }).detail;
              setError(typeof detail === "string" ? detail : "The API request failed");
              return;
            }
            if (event === "delta" || event === "summary") setSummary(data);
          });
        }
      }
    } catch {
      setError("Could not reach the API. Start it with uvicorn on port 8000.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full items-center justify-center bg-[radial-gradient(125%_125%_at_50%_101%,rgba(245,87,2,1)_10.5%,rgba(245,120,2,1)_16%,rgba(245,140,2,1)_17.5%,rgba(245,170,100,1)_25%,rgba(238,174,202,1)_40%,rgba(202,179,214,1)_65%,rgba(148,201,233,1)_100%)]">
      <div className="w-[500px] p-4">
        <PromptInputBox
          onSend={handleSendMessage}
          isLoading={isLoading}
          placeholder="Paste test results..."
        />
        {(summary || error) && (
          <div
            className={`mt-4 max-h-60 overflow-auto whitespace-pre-wrap rounded-3xl bg-[#1F2023] p-4 text-sm ${error ? "text-red-300" : "text-gray-100"}`}
          >
            {error || JSON.stringify(summary, null, 2)}
          </div>
        )}
      </div>
    </div>
  );
};

export { DemoOne };
