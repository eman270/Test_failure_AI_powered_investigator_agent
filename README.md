# AI Test Failure Investigation Agent
**AI Engineering Bootcamp Capstone — Release 1**

**Project:** AI-Powered Test Failure Investigator  
**Live application:** https://test-failure-ai-powered-investigator.onrender.com/  
**Status:** Deployed proof of concept

### Problem
Investigating automated test failures is time-consuming. Developers must review logs, identify related failures, search technical documentation, and determine possible root causes. Repeated failures can lead to duplicated investigation effort.

### Solution
I built an AI-powered investigation application that analyzes pytest failure logs, groups related failures, retrieves supporting evidence, suggests root-cause hypotheses, and recommends troubleshooting steps.

### Architecture and Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript |
| Backend | Python, FastAPI |
| Agent orchestration | Google ADK SequentialAgent |
| LLM | GPT-4o mini |
| Document RAG | Supabase PostgreSQL / pgvector |
| Embeddings | OpenAI text-embedding-3-small |
| Episodic memory | Supabase semantic search |
| Observability | Langfuse |
| Automated evaluations | pytest |
| Deployment | Render |

### Multi-Agent Workflow
Five specialized agents execute sequentially:

1. **Identify Failures:** Extract failing tests and error details.
2. **Group Failures:** Group failures by shared characteristics.
3. **Diagnose Failures:** Investigate possible causes using logs, documents, and historical cases.
4. **Recommend Fixes:** Suggest actionable troubleshooting steps.
5. **Write Report:** Produce an investigation report with hypotheses, evidence, confidence, and recommendations.

### Advanced AI Capabilities
- **RAG:** Retrieves relevant technical documentation to ground investigations.
- **Episodic memory:** Stores development-stage failure-group memories and retrieves similar historical cases.
- **Human-on-Demand:** Pauses the workflow for clarification and resumes with the user's response.
- **Evaluations:** Uses golden test cases and pytest to check end-to-end execution and basic diagnosis relevance.
- **Observability:** Langfuse records agent execution, tool calls, latency, tokens, and estimated cost.

### Validation and Evidence
The deployed application processes test failure logs and generates investigation reports. A demonstrated scenario grouped two payment API timeouts separately from a login assertion failure. Historical memory searches returned matching cases with similarity scores. Automated E2E tests validate the workflow and basic expected diagnosis indicators.

Langfuse provides execution evidence. One captured trace recorded approximately 20.45 seconds, 19K tokens, and $0.003 in estimated cost.

### Scope and Limitations
Release 1 is a learning proof of concept. The agent proposes hypotheses rather than confirming root causes. Episodic memories are saved in development mode and are not human-verified. Automated evaluations cover basic behavior, not comprehensive semantic correctness. Final-result human verification, trusted memory promotion, and duplicate handling are deferred to a future release.

### Outcome
The capstone demonstrates an end-to-end agentic AI system combining multi-agent orchestration, retrieval-augmented generation, persistent memory, human interaction, automated evaluation, observability, and cloud deployment.
