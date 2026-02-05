# AI Tool Prompts Used During Development

This document tracks all AI tool prompts used during the development of the Revenue Leakage Agent.

## Tool: Cursor AI Assistant (Claude)

### Prompt 1: Initial Project Planning

**Prompt**:

```
Using @AI Engineer Technical Challenge – The Revenue Leakage Agent.pdf documentation try plan a application. All is described in the document. Application will be prototype, can be not production grate. The code need to be clean, you need to keep folder structure. Use Langgraph and python, as forntend please use something lightwieght, maybe chatlint. the Backend should be fastpi.
```

**Result**: Created implementation plan with LangGraph agent flow, folder structure (agents/, graphs/, tools/, schemas/, services/), and technology stack (LangGraph, FastAPI, Chainlit).

---

### Prompt 2: Implementation Execution

**Prompt**: (Implicit - execute the planned implementation)

**Result**: Generated complete codebase with Pydantic schemas, 8 LangChain tools, LangGraph state machine, FastAPI backend, Chainlit frontend, and sample data.

---

### Prompt 3: Deterministic Analysis vs LLM-Only Reasoning

**Prompt**:

```
What to you think to add a calculations or investigations based on the python not only 
on the rely on the LLMs. f.e the billing plan suggest invoice every month. In case below, 
LLMs suggest to add one invoice - october. But today is February 2026 - this is current 
month. So maybe that should be adjusted and do not rely on the LLMs. Use datatime module to calculate current date, add logic to make a basic calculations and after that connect it with LLMs.
```

**Result**: Created `services/analysis.py` for deterministic date calculations and `services/preprocessor.py` to inject Python-computed analysis before LLM sees the message. LLM now interprets pre-computed results instead of calculating gaps itself.


| Aspect                | Before (LLM-only)    | After (Hybrid)              |
| ----------------------- | ---------------------- | ----------------------------- |
| Missing periods found | 1 (October only)     | 17 (all months to Feb 2026) |
| Calculation method    | LLM pattern matching | Python date math            |
| Reliability           | Prone to oversight   | Deterministic               |

---

### Prompt 4: Socket.IO 404 Errors — Two-Server Architecture Bug

**Prompt**:

```
I facing the problem [terminal output showing 404s] when i run scripts/run_all.py
```

**Result**: Fixed by using Chainlit's `mount_chainlit()` to embed UI inside FastAPI app. Everything now runs on single port (8000): API at `/api/*`, Chat UI at `/chat`, Socket.IO at `/chat/ws/socket.io`. Eliminated two-process management and port confusion.

---

### Prompt 5: Replace Customer ID with Customer Name

**Prompt**:

```
Change the looking for @src/revenue_agent/tools/invoice_tools.py function. Customer need to 
be queried by customer name not id. also change customer id into customer name
```

**Result**: Replaced `customer_id` with `customer_name` across the invoice pipeline. Updated the `Invoice` schema, `invoices.json` data (mapped IDs to actual names like "Acme Corporation"), `query_invoices` tool (now accepts `customer_name` with case-insensitive partial matching), data loader index, and system prompt. Billing plans and credit memos retain `customer_id` as those are separate entities.


| File                       | Change                                                                                 |
| ---------------------------- | ---------------------------------------------------------------------------------------- |
| `schemas/billing.py`       | `Invoice.customer_id` → `Invoice.customer_name`                                       |
| `data/invoices.json`       | `"customer_id": "CUST-001"` → `"customer_name": "Acme Corporation"` (all 14 invoices) |
| `tools/invoice_tools.py`   | Filter + serialize by`customer_name` (case-insensitive partial match)                  |
| `services/data_loader.py`  | Index`_invoice_by_customer_name` replaces `_invoice_by_customer_id`                    |
| `agents/prompts/system.py` | Tool docs updated to reference`customer_name`                                          |

---

### Prompt 6: Reasoning Trace Implementation

**Prompt**:

Add reasoning and trace it. Add displaying the resoning to chainlit.

Followed by:

```
Add layer 1 and layer 2
```

**Result**: Implemented a two-layer reasoning trace that captures every step of the agent's decision process:

- **Layer 1 (State-persisted trace)**: Added `reasoning_trace` field to `AgentState` using `Annotated[list, operator.add]` so each graph node automatically concatenates its trace entries. `agent_node` emits `llm_decision` steps (which tools the LLM chose or final response), `tool_node` emits paired `tool_call` + `tool_result` steps. The preprocessor emits a `pre_analysis` step when Python analysis runs.
- **Layer 2 (Exposed via API + UI)**: `run_agent` now returns an `AgentResult` object containing both `response` and `reasoning_trace`. The `/chat` API endpoint includes the trace in `ChatResponse`. Chainlit renders each trace step as an expandable `cl.Step` in the chat UI.


| File                      | Change                                                                                 |
| --------------------------- | ---------------------------------------------------------------------------------------- |
| `schemas/state.py`        | Added`ReasoningStep` model, `reasoning_trace` field with `operator.add` reducer        |
| `graphs/nodes.py`         | `agent_node` and `tool_node` append trace entries with timestamps, tool args, previews |
| `graphs/revenue_graph.py` | New`AgentResult` class, `run_agent` returns trace alongside response                   |
| `api/routes.py`           | `ChatResponse` includes `reasoning_trace` list                                         |
| `frontend/app.py`         | Renders trace as expandable Chainlit`cl.Step` elements                                 |

---

### Prompt 7: Human-Friendly Approval Messages

**Prompt**:

```
Change that sentence and related to more human grade. "To apply this credit memo, please use 
the apply_action function with the action ID ACT-46FA0F26." I mean, do we need that word 
apply_action and ID of ACT?
```

**Result**: Removed all internal function names and action IDs from user-facing messages. Updated three proposal tools to use natural language ("Please confirm if you'd like to apply this") instead of exposing `apply_action(action_id='ACT-...')`. Added explicit communication rules to the system prompt instructing the LLM to never mention function names, action IDs, or technical tool syntax — just speak in plain professional language and silently call tools when the user approves.


| File                       | Change                                                                         |
| ---------------------------- | -------------------------------------------------------------------------------- |
| `tools/proposal_tools.py`  | All three`message` fields rewritten to natural language                        |
| `agents/prompts/system.py` | Added "Communication Style" rules: never expose internal IDs or function names |
| `tools/sandbox_tools.py`   | Cleaned up error message that referenced`apply_action()`                       |

---

### Prompt 8: Collapse Reasoning Trace Steps

**Prompt**:
```
Reasoning part now shoing all steps in separate rows, colapse it with expaning possibility. Do it for tools usage and llm decisions.
```

**Result**: Collapsed all tool activity into a single expandable "Tool Usage" block and all LLM decisions into a single "LLM Decisions" block in Chainlit. This keeps the reasoning trace readable while still exposing full detail when expanded.

| File | Change |
| --- | --- |
| `frontend/app.py` | Grouped tool_call/tool_result into one step and llm_decision into another |

---
### Prompt 9: Add Human-in-the-Loop Interrupt with `interrupt_before`

**Prompt**:

```
The human in the loop are based on the prompt rule based. Make a hard-stop based on interrupt_before before using a tool functions.
```

**Result**: Implemented LangGraph's `interrupt()` mechanism to enforce hard human approval gates before sandbox-modifying tools (`apply_action`, `rollback_action`) execute. This replaces the soft prompt-based approval with a graph-level checkpoint that pauses execution and requires explicit user approval or rejection.

**Changes**:

| File | Change |
| --- | --- |
| `graphs/nodes.py` | Added `SANDBOX_TOOL_NAMES`, `human_review_node` (uses `interrupt()` to pause), `after_human_review` routing function; updated `should_continue` to route sandbox tools through `"human_review"` |
| `graphs/revenue_graph.py` | Updated graph structure with `human_review` node and conditional edges; added `_get_interrupt_details` to inspect pending interrupts; extended `AgentResult` with `needs_approval` and `pending_actions` fields; added `resume_agent` function to resume with `Command(resume="approve"|"reject")`; `run_agent` now auto-rejects stale interrupts before processing new messages |
| `graphs/__init__.py` | Exported `resume_agent` |
| `api/routes.py` | Extended `ChatRequest` with optional `approve: bool` field; extended `ChatResponse` with `needs_approval` and `pending_actions` fields; updated `chat` endpoint to route to `resume_agent` when `approve` is set |
| `frontend/app.py` | Added approval UI using `cl.AskActionMessage` with **Approve / Reject** buttons; when `needs_approval=True`, displays pending actions and waits for user decision; calls resume API with user's choice and displays the result |

**Architecture**:

```
┌──────────┐
│  agent   │ ← entry point
└────┬─────┘
     │ should_continue
     ├─── "tools" ──────────► tools ──► agent (loop)
     ├─── "human_review" ──► human_review (interrupt here)
     │                         │ after_human_review
     │                         ├── "tools" ──► tools ──► agent (approved)
     │                         └── "agent" ──► agent (rejected)
     └─── "end" ──────────► END
```

**Key Benefits**:
- **Hard enforcement**: Graph execution pauses at `interrupt()` — tools cannot execute without explicit approval
- **Stateful**: Approval state persists in the checkpointer; user can approve/reject in a separate API call
- **Clean separation**: Approval logic is in the graph structure, not just in prompt instructions
- **Better UX**: Frontend shows action details with clear Approve/Reject buttons

---

### Prompt 10: Audit Log Viewer Endpoint + Chainlit Subpage

**Prompt**:

```
Add the log viewer endpotin and maybe subpage to chainlint. The endpoint for audit is already created in @src/revenue_agent/api/routes.py @routes.py (109-119) 

Make simple log viewer subpage, that can be dataframe/table or some different readable form for human. 
Also add that prompt to @candidate_prompts.md
```

**Result**: Added an HTML audit-log viewer endpoint and a simple Chainlit audit log viewer flow. The HTML endpoint renders a readable table for humans, and the chat UI now supports a `/audit` command plus a quick link in the welcome message.

**Changes**:

| File | Change |
| --- | --- |
| `api/routes.py` | Added `/api/audit-log/view` HTML endpoint that renders a basic table; added `_render_audit_log_html()` helper |
| `frontend/app.py` | Added `/audit` command to render a markdown table; added welcome link to `/api/audit-log/view` |

---


### Prompt 11: Senior Architect Code Review and Refactor

**Prompt**:

```
Review this code as a Senior Architect. Audit for:

SOLID & DRY: Fix violations and remove redundancy.
KISS: Simplify over-engineered logic or deep nesting.
Performance: Identify bottlenecks or inefficient patterns.
Naming: Improve clarity of variables/function - do not change the function names if folder @src/revenue_agent/tools/

Output: Briefly list the "Why," then provide the refactored, clean-code version.
```

**Result**: Refactored shared helpers, reduced duplication, improved filtering/indexing, and clarified internal naming without changing tool function names.

---




