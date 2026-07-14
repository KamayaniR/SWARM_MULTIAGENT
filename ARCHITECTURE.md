# Architecture

## Directory structure

```
swarm-control/
│
├── README.md
├── ARCHITECTURE.md                    ← this file
├── PLAN.md                            ← build schedule, team split, demo script
├── .env.example
├── .gitignore
├── requirements.txt
├── docker-compose.yml
├── Makefile
│
├── agents/                            # Track A: core agents
│   ├── __init__.py
│   ├── planner.py                     # Spec → typed steps
│   ├── coder.py                       # Step → code in sandbox
│   ├── critic.py                      # LLM-as-judge verdicts
│   └── prompts/
│       ├── planner_system.md
│       ├── coder_system.md
│       └── critic_system.md
│
├── scheduler/                         # Track B: routing + instrumentation
│   ├── __init__.py
│   ├── models.py                      # MODEL_PRICES, TIER_LADDER, CallRecord
│   ├── router.py                      # Hybrid LLM + history router
│   ├── cost_tracker.py                # SQLite cost aggregation
│   ├── latency_tracker.py             # Timing stats
│   ├── trace_logger.py                # JSONL audit trail
│   ├── tracked_client.py             # Multi-provider LLM wrapper
│   └── budget_guard.py                # Spend circuit breaker
│
├── orchestrator/                      # Orchestration: state machine + API
│   ├── __init__.py
│   ├── state.py                       # SwarmState TypedDict
│   ├── graph.py                       # LangGraph StateGraph
│   ├── loop.py                        # Node functions
│   ├── server.py                      # FastAPI + WebSocket + REST
│   └── events.py                      # Event emitter
│
├── sandbox/                           # Track B: execution sandbox
│   ├── __init__.py
│   ├── manager.py                     # Container lifecycle
│   ├── Dockerfile
│   └── entrypoint.sh
│
├── dashboard/                         # Track C: frontend
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   └── useRunState.ts
│   │   ├── components/
│   │   │   ├── AgentGrid.tsx
│   │   │   ├── RoutingPanel.tsx
│   │   │   ├── CostMeter.tsx
│   │   │   ├── ComparisonChart.tsx
│   │   │   ├── ScoreTimeline.tsx
│   │   │   ├── DecisionLog.tsx
│   │   │   ├── TraceViewer.tsx
│   │   │   ├── InterveneModal.tsx
│   │   │   └── RunControls.tsx
│   │   ├── types/
│   │   │   └── events.ts
│   │   └── styles/
│   │       └── globals.css
│   └── mock/
│       └── mock_events.json
│
├── data/                              ← gitignored, created at runtime
│   ├── costs.db
│   ├── scheduler.db
│   └── traces/
│
├── demo/
│   ├── tasks/
│   │   ├── csv_dedup.md
│   │   └── flask_api.md
│   ├── pitch.md
│   └── backup_video/
│
├── tests/
│   ├── test_router.py
│   ├── test_cost_tracker.py
│   ├── test_sandbox.py
│   └── test_loop.py
│
└── docs/
    ├── EVENT_SCHEMA.md
    ├── GITHUB_WORKFLOW.md
    └── JUDGE_QA.md
```

---

## System flow: what happens when a user hits Run

### Step 0: Setup
```
User pastes spec in dashboard → clicks Run
Dashboard sends POST /run to FastAPI server
Server creates:
  - run_id (uuid)
  - Docker container (sandbox for code execution)
  - LangGraph state machine with empty SwarmState
  - WebSocket connection to dashboard
```

### Step 1: Planner (Sonnet)
```
Input:  spec text
Model:  Claude Sonnet 5 (always — planning is high-leverage, only runs once)
Output: list of PlanStep objects, each with:
  - id: "s1"
  - description: "set up argparse with input/output/key flags"
  - step_class: "cli_wiring"
  - est_loc: 25
  - deps: []
  - acceptance: ["--input flag reads CSV path", "--key flag accepts column names"]

Why Sonnet: a bad plan poisons everything downstream. One expensive
call here saves many wasted cheap calls later.

Event emitted: {agent: "planner", action: "plan_created", steps: [...]}
```

### Step 2: Router classifies the step
```
Input:  step description from Planner
Model:  GPT-4.1 nano ($0.10/$0.40 per 1M — basically free)

Prompt:
  "You are a task difficulty classifier for code generation.
   Given a task description, respond with exactly one word:
   EASY, MEDIUM, or HARD.
   Task: {step_description}"

Response: "EASY" (one token, ~$0.000022, 200-500ms)

Mapping:
  EASY   → gpt-4.1-mini   ($0.40/$1.60)
  MEDIUM → claude-haiku    ($1.00/$5.00)
  HARD   → claude-sonnet   ($2.00/$10.00)

History enhancement (optional, kicks in after a few runs):
  If history shows a cheaper tier passes this step_class reliably,
  override the LLM classification downward to save more money.

Event emitted: {agent: "router", action: "classify", difficulty: "EASY",
               model: "gpt-4.1-mini", routing_reason: "nano classified as EASY"}
```

### Step 3: Coder implements the step
```
Input:  step description + acceptance criteria + workspace files
        + (on retry: Critic feedback from last attempt)
Model:  whatever the router picked (could be any tier)

Output: generated code files

Code is injected into the Docker container via sandbox.inject_files()

Event emitted: {agent: "coder", action: "implement", model: "gpt-4.1-mini",
               cost_usd: 0.0004, latency_ms: 890}
```

### Step 4: Tests run in sandbox
```
Executes: docker exec <container> pytest -v
Returns:  {exit_code, stdout, stderr, tests_passed, tests_total}

NOT an LLM call. Deterministic. No cost. No latency concern.
Tests come from two sources:
  - Tests the Coder wrote
  - Tests the Critic generates from acceptance criteria

Event emitted: {agent: "tester", action: "run_tests",
               tests_passed: 11, tests_total: 14}
```

### Step 5: Critic judges the output
```
Input:  spec + current code + test results
Model:  Claude Sonnet 5 (always — judging needs strong reasoning)

Output: structured JSON via tool_use:
  {
    correctness: 6.2,
    spec_fidelity: 7.0,
    code_quality: 5.8,
    coverage: 6.5,
    overall: 6.1,
    feedback: ["parser fails on quoted commas"],
    failure_type: "step_level"
  }

Pass condition: overall >= 8.5 AND all tests green (both required)

Event emitted: {agent: "critic", action: "verdict", score: 6.1,
               outcome: "fail"}
```

### Step 6: What happens after the verdict
```
IF pass (score >= 8.5 AND tests green):
  ├── Record outcome: router.record_outcome(step_class, model, passed=True)
  ├── If more steps → go to Step 2 for next step
  └── If last step → RUN COMPLETE, show cost comparison chart

IF step-level fail:
  ├── Record outcome: router.record_outcome(step_class, model, passed=False)
  ├── If iteration < 8 → go to Step 2 (router may escalate model)
  └── If iteration >= 8 → ESCALATE TO HUMAN with specific question

IF plan-level fail:
  └── Go to Step 1 (Planner re-plans from current state)
```

### Step 7: Human intervention (optional)
```
User clicks plan step in dashboard → types correction
POST /intervene {run_id, step_id, correction_text}
Server loads checkpoint → Planner re-plans downstream → loop resumes
```

---

## The hybrid router (detailed design)

### Why hybrid (LLM + history) instead of just one

**LLM-only router:**
- Smart from Run 1 (no learning period)
- Never corrupts
- But never improves — cost curve is flat
- Small per-call cost ($0.000022)

**History-only router (dictionary):**
- Free and instant
- Improves over time (cost curve goes down)
- But Run 1 is dumb (just guessing)
- History can corrupt

**Hybrid = best of both:**
- Smart from Run 1 (LLM handles cold start)
- Improves over time (history finds cheaper options)
- If history corrupts, LLM fallback keeps working
- Cost curve goes down (the demo chart still works)

### Router logic (pseudocode)

```python
async def route(step_description: str, step_class: str) -> tuple[str, str]:
    """
    Returns (model_name, routing_reason)
    """
    # Step 1: LLM classification (always runs)
    difficulty = await classify_with_nano(step_description)
    llm_model = DIFFICULTY_TO_MODEL[difficulty]
    # difficulty is "EASY", "MEDIUM", or "HARD"
    # maps to gpt-mini, haiku, or sonnet

    # Step 2: Check history (enhancement layer)
    history = get_history(step_class)

    if history and history.total_attempts >= 3:
        # Enough data to consider
        cheapest_passing = find_cheapest_tier_with_pass_rate_above_70(step_class)

        if cheapest_passing and tier_cost(cheapest_passing) < tier_cost(llm_model):
            # History found a cheaper option that works
            return (cheapest_passing,
                    f"nano said {difficulty}, but history shows "
                    f"{cheapest_passing} passes {step_class} at "
                    f"{history.pass_rate:.0%}")

    # No useful history — trust LLM classification
    return (llm_model, f"nano classified as {difficulty}")
```

### Router classification prompt

```
You are a task difficulty classifier for code generation.

Given a task description, respond with exactly one word:
- EASY: boilerplate, config, CLI wiring, simple file I/O, test scaffolding,
  string formatting, logging setup, basic CRUD
- MEDIUM: file parsing with edge cases, data transformation, API integration,
  error handling, input validation, database queries
- HARD: complex algorithms, multi-step logic, performance optimization,
  concurrency, state machines, mathematical computation

Task: "{step_description}"

Difficulty:
```

### History table structure

```sql
CREATE TABLE routing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    step_class TEXT NOT NULL,
    model TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    critic_score REAL,
    timestamp TEXT NOT NULL
);

-- Rolling window: only last 10 per (step_class, model)
-- Reset endpoint: DELETE FROM routing_history
```

### Escalation (when the routed model fails)

```
Router picks gpt-mini → Coder fails → Critic says step_level fail
  ├── Record: routing_history INSERT (step_class, "gpt-mini", false)
  ├── Router re-classifies: nano might say MEDIUM now (same step, but
  │   the description now includes "previous attempt failed on: ...")
  └── Or: history override kicks in ("gpt-mini fails this class → try haiku")

This creates a natural escalation without hardcoded tier ladders.
The LLM re-classifies with failure context, and history accumulates
data about which models fail which task types.
```

---

## Multi-provider client

The TrackedLLMClient wraps both Anthropic and OpenAI SDKs behind one interface.
Agents call `client.call(model="haiku", ...)` or `client.call(model="gpt-mini", ...)`
and the client routes to the right SDK automatically.

```
client.call(model="gpt-mini", messages=[...])
  │
  ├── resolve_model("gpt-mini") → "gpt-4.1-mini"
  ├── get_provider("gpt-4.1-mini") → "openai"
  │
  ├── if openai:  self.openai_client.chat.completions.create(...)
  ├── if anthropic: self.anthropic_client.messages.stream(...)
  │
  ├── measure latency + time-to-first-token
  ├── compute_cost(model, input_tokens, output_tokens)
  │
  ├── cost_tracker.record(...)      → SQLite
  ├── latency_tracker.record(...)   → memory
  ├── trace_logger.log(...)         → JSONL
  │
  └── return (response_text, metrics_dict)
```

### Model registry

```python
MODEL_PRICES = {
    # Anthropic
    "claude-haiku-4-5":  {"provider": "anthropic", "input": 1.00/1M, "output": 5.00/1M,  "tier": 2},
    "claude-sonnet-5":   {"provider": "anthropic", "input": 2.00/1M, "output": 10.00/1M, "tier": 3},
    "claude-opus-4-8":   {"provider": "anthropic", "input": 5.00/1M, "output": 25.00/1M, "tier": 4},

    # OpenAI
    "gpt-4.1-nano":      {"provider": "openai", "input": 0.10/1M, "output": 0.40/1M,  "tier": 0},
    "gpt-4.1-mini":      {"provider": "openai", "input": 0.40/1M, "output": 1.60/1M,  "tier": 1},
    "gpt-5":             {"provider": "openai", "input": 1.25/1M, "output": 10.00/1M, "tier": 2},
    "gpt-5.4":           {"provider": "openai", "input": 2.50/1M, "output": 15.00/1M, "tier": 3},
    "gpt-5.5":           {"provider": "openai", "input": 5.00/1M, "output": 30.00/1M, "tier": 4},
}

DIFFICULTY_TO_MODEL = {
    "EASY":   "gpt-4.1-mini",       # $0.40/$1.60
    "MEDIUM": "claude-haiku-4-5",    # $1.00/$5.00
    "HARD":   "claude-sonnet-5",     # $2.00/$10.00
}
```

---

## Recording layer (fires on every action)

Every LLM call automatically records to 4 places:

```
TrackedLLMClient.call() completes
  │
  ├── CostTracker (SQLite)
  │     Stores: model, tokens, cost_usd, per run/step/model
  │     Powers: cost meter, comparison chart, learning curve
  │
  ├── LatencyTracker (in-memory)
  │     Stores: latency_ms, time_to_first_token
  │     Powers: agent grid animation timing, latency breakdown
  │
  ├── TraceLogger (JSONL file per run)
  │     Stores: full prompt, full response, cost, timing
  │     Powers: trace viewer (click any event → see everything)
  │
  └── EventEmitter (WebSocket → dashboard)
        Stores: nothing (streams live)
        Powers: all dashboard components in real time
```

---

## Event schema (contract between backend and frontend)

Freeze this on Day 1. All three tracks code against it.

```typescript
interface SwarmEvent {
  timestamp: string;
  run_id: string;
  agent: "planner" | "coder" | "critic" | "tester" | "router";
  action: string;
  step_id: string;
  step_class: string;
  model: string | null;
  provider: string | null;
  routing_reason: string;
  difficulty: string | null;       // "EASY" | "MEDIUM" | "HARD" (from nano)
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number;
  latency_ms: number;
  iteration: number;
  outcome: "pass" | "fail" | "error" | null;
  critic_score: number | null;
  tests_passed: number | null;
  tests_total: number | null;
  detail: string;
}
```

---

## Dashboard layout

```
┌─────────────────────────────────────────────────────────────────┐
│  SWARM CONTROL                              [Run] [Baseline]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─── Agent grid ───────────────────────────────────────────┐   │
│  │  ┌──────────┐  ┌──────────────┐  ┌──────────┐           │   │
│  │  │ Planner  │  │    Coder     │  │  Critic  │           │   │
│  │  │ (Sonnet) │  │ gpt-4.1-mini │  │ (Sonnet) │           │   │
│  │  │   idle   │  │  writing...  │  │   idle   │           │   │
│  │  └──────────┘  └──────────────┘  └──────────┘           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─── Routing panel ──────────┐  ┌─── Cost meter ───────────┐  │
│  │  s1: cli_wiring            │  │  This run: $0.0043        │  │
│  │     nano: EASY → gpt-mini  │  │                           │  │
│  │     ✓ passed               │  │  Baseline:  $0.187        │  │
│  │                            │  │  Scheduler: $0.043        │  │
│  │  s2: io_parsing            │  │  Savings:   77%           │  │
│  │     nano: MEDIUM → haiku   │  │                           │  │
│  │     ✗ failed → sonnet ✓    │  │  [Learning curve chart]   │  │
│  └────────────────────────────┘  └───────────────────────────┘  │
│                                                                 │
│  ┌─── Score timeline ──────────────────────────────────────-┐   │
│  │  10 ┤                                          ● ✓       │   │
│  │   8 ┤─ ─ ─ ─ ─ ─ ─ ─ ─ pass threshold ─ ─ ─ ─ ─ ─ ─ ─│   │
│  │   6 ┤        ●                   ●                       │   │
│  │   4 ┤   ●                                                │   │
│  │     └────────────────────────────────────────────────────│   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─── Decision log ────────────────────────────────────────-┐   │
│  │  14:02:11  router   s1 → nano: EASY → gpt-4.1-mini      │   │
│  │  14:02:13  coder    implement s1 (gpt-mini) ✓            │   │
│  │  14:02:16  tester   13/13 passed                         │   │
│  │  14:02:20  critic   score 9.1 → PASS                     │   │
│  │  14:02:21  router   s2 → nano: MEDIUM → haiku            │   │
│  │  14:02:24  coder    implement s2 (haiku) ✗               │   │
│  │  14:02:27  critic   score 5.2 → FAIL                     │   │
│  │  14:02:28  router   s2 retry → escalate to sonnet        │   │
│  │  ▼ auto-scrolls                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [Intervene]                              [Trace Viewer]        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Dependency graph (who imports whom)

```
scheduler/models.py          ← imported by everything, imports nothing
    │
    ├── scheduler/router.py              (imports models + openai for nano)
    ├── scheduler/cost_tracker.py        (imports models)
    ├── scheduler/latency_tracker.py     (imports models)
    ├── scheduler/trace_logger.py        (imports models)
    ├── scheduler/budget_guard.py        (imports cost_tracker)
    │
    └── scheduler/tracked_client.py      (imports all above + anthropic + openai)
                │
                ├── agents/planner.py    (imports tracked_client only)
                ├── agents/coder.py      (imports tracked_client only)
                └── agents/critic.py     (imports tracked_client only)
                        │
                        └── orchestrator/loop.py    (imports agents + router)
                                │
                                └── orchestrator/graph.py   (imports loop + state)
                                        │
                                        └── orchestrator/server.py  (mounts everything)
```

Key rules:
- Arrows only point downward. No circular imports.
- Agents never import cost_tracker, router, or scheduler directly.
- Agents receive TrackedLLMClient as a dependency — instrumentation is automatic.
- The orchestrator is the only module that wires everything together.
- The dashboard is completely decoupled — it only consumes WebSocket events.

---

## Environment

### .env.example
```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
BUDGET_PER_RUN=0.50
BUDGET_DAILY=10.00
API_PORT=8000
DASHBOARD_PORT=5173
SANDBOX_IMAGE=swarm-sandbox:latest
SANDBOX_TIMEOUT=120
```

### requirements.txt
```
anthropic>=0.30.0
openai>=1.30.0
langgraph>=0.2.0
langchain-core>=0.3.0
fastapi>=0.115.0
uvicorn>=0.30.0
websockets>=12.0
docker>=7.0.0
pydantic>=2.0
```
