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
├── test_loop.py                       # Manual smoke test: Task mode end-to-end
├── test_agent_mode.py                 # Manual smoke test: Agent mode bake-off
│
├── agents/                            # Core agents (shared by both modes)
│   ├── __init__.py
│   ├── planner.py                     # Spec → typed steps (claude-sonnet-4-6)
│   ├── coder.py                       # Step → code in sandbox (routed model)
│   ├── critic.py                      # LLM-as-judge verdicts (claude-sonnet-4-6)
│   ├── team_planner.py                # Agent mode: spec → agent roles (claude-sonnet-4-6)
│   └── prompts/
│       ├── planner_system.md
│       ├── coder_system.md
│       ├── critic_system.md
│       └── team_planner_system.md
│
├── scheduler/                         # Routing + instrumentation
│   ├── __init__.py
│   ├── models.py                      # MODEL_PRICES, TIER_LADDER, DELIBERATION_MODEL_POOL, CallRecord
│   ├── router.py                      # Task mode: hybrid LLM + history router
│   ├── debate.py                      # Cost-Advocate-vs-Quality-Skeptic debate (Task mode's optional debate_mode)
│   ├── deliberation.py                # Agent mode: Planner voice + Debate voice + Judge → 2 candidates
│   ├── similarity.py                  # Agent mode: embedding-based similarity-skip cache
│   ├── team.py                        # Old Agent Mode (team bake-off): candidate selection
│   ├── cost_tracker.py                # SQLite cost + latency aggregation
│   ├── latency_tracker.py             # In-memory timing stats
│   ├── trace_logger.py                # JSONL audit trail
│   ├── tracked_client.py              # Multi-provider LLM wrapper + embed()
│   └── budget_guard.py                # Spend circuit breaker
│
├── orchestrator/                      # Orchestration: state machine + API
│   ├── __init__.py
│   ├── state.py                       # SwarmState TypedDict (mode, candidates, similarity, etc.)
│   ├── graph.py                       # LangGraph StateGraph (+ comparison_gate node)
│   ├── loop.py                        # Node functions for both modes
│   ├── server.py                      # FastAPI + WebSocket + REST (+ commit-preference)
│   ├── events.py                      # Event emitter
│   ├── agent_mode.py                  # Old Agent Mode: team composition + per-role bake-off
│   └── artifacts.py                   # Run artifact handling
│
├── sandbox/                           # Execution sandbox — local or remote
│   ├── __init__.py
│   ├── manager.py                     # Local Docker container lifecycle
│   ├── factory.py                     # Picks docker vs akash backend from env
│   ├── akash.py                       # HTTP client for pooled Akash sandbox pods
│   ├── agent_server.py                # In-container HTTP agent (runs on Akash)
│   └── Dockerfile
│
├── akash/                             # Akash Network deployment (decentralized compute)
│   ├── deploy-sandbox.yaml            # SDL: sandbox-agent pods
│   ├── deploy-sandbox-pomerium.yaml   # SDL: sandbox-agent + Pomerium ingress
│   ├── deploy-proof.yaml              # SDL: nginx proof-of-path test
│   ├── env.sandbox.sh                 # Akash testnet chain config
│   └── pomerium/                      # Zero-trust ingress image for the sandbox mesh
│       ├── config.yaml
│       ├── Dockerfile
│       └── README.md
│
├── pomerium/                          # Zero-trust proxy in front of the dashboard
│   ├── config.yaml                    # Route :8000 behind GitHub login
│   ├── docker-compose.pomerium.yml
│   ├── gen-certs.sh                   # Local TLS certs for *.localhost.pomerium.io
│   ├── .env.pomerium.example
│   └── README.md
│
├── dashboard/                         # Frontend (React + Vite)
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/                           # Components, hooks, and types — see dashboard/README.md
│
├── data/                              ← gitignored, created at runtime
│   ├── costs.db                       # Every LLM call: tokens, cost, latency
│   ├── scheduler.db                   # Task mode's routing_history (pass rate + critic_score)
│   ├── similarity.db                  # Agent mode's step-similarity cache
│   ├── checkpoints.db                 # LangGraph SqliteSaver — resumable run state
│   └── traces/{run_id}.jsonl          # Full prompt/response per call, one file per run
│
├── demo/
│   └── tasks/
│
├── tests/
│
└── docs/
    └── EVENT_SCHEMA.md                # Backend/frontend event contract
```

---

## System flow — Task mode: what happens when a user hits Run

Task mode is `POST /run` with `mode: "task"` (the default). This is the original, unchanged loop — one model per step, picked by the classic router.

### Step 0: Setup
```
User pastes spec in dashboard → clicks Run
Dashboard sends POST /run to FastAPI server
Server creates:
  - run_id (uuid)
  - Sandbox container (local Docker, or a pooled Akash pod — see sandbox/factory.py)
  - LangGraph state machine with empty SwarmState
  - WebSocket connection to dashboard
```

### Step 1: Planner (Sonnet 4.6)
```
Input:  spec text
Model:  claude-sonnet-4-6 (always — planning is high-leverage, only runs once)
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
Model:  claude-sonnet-4-6 (always — judging needs strong reasoning)

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

## System flow — Agent mode: deliberation + empirical comparison

Agent mode is `POST /run` with `mode: "agent"`. Same Planner → Coder → Tester → Critic
skeleton, but `router_node` takes a completely different path per step, and the graph
gains one extra pause point.

### Step 2 (agent mode): similarity check → deliberation

```
1. Similarity check (scheduler/similarity.py)
   Embed "{step_class}: {step_description}" with text-embedding-3-small.
   Cosine-compare against every past step's embedding (data/similarity.db).

   score >= SIMILARITY_THRESHOLD (0.60, placeholder — not yet calibrated):
     → skip deliberation entirely, reuse the historical winning model.
     → Event: {agent: "router", action: "similarity_skip",
                similarity_score: 0.91, matched_step_id: "42"}
     → Execution (Coder → Tester → Critic) still runs in FULL — only the
       deliberation is skipped, never the actual work.

   score < threshold, OR this is a retry (iteration > 0):
     → deliberate (retries always re-deliberate — reusing a just-failed
       winner via similarity would lock the failure in).

2. Deliberation (scheduler/deliberation.py) — three fixed voices:
     Planner voice   claude-sonnet-4-6   argues from what the step needs
     Debate voice    claude-opus-4-8     stress-tests against complexity/history
     Judge           claude-opus-4-6     always makes the final call

   2 rounds minimum (1 planner-voice turn + 1 debate-voice turn each), early
   stop if both voices' pairs agree, hard cap 3 rounds. The judge then picks
   the final TWO candidates (not one) from DELIBERATION_MODEL_POOL — a
   degenerate same-model pick auto-substitutes an adjacent pool model.

   Event per turn: {agent: "debate", action: "deliberation_turn",
                     model: "claude-opus-4-8", candidates: [...], detail: "..."}
```

### Step 3 (agent mode): dual-candidate sandbox comparison

```
Both candidates are ACTUALLY BUILT — concurrently, each in its own isolated
sandbox: real Coder call → real pytest → real, independent Critic verdict.
No simulation, no lightweight check — full judging on both.

Per-candidate cost is isolated under a sub-run-id (run_id::step_id::model) so
overlapping models never pollute each other's cost, and both outcomes feed
routing history so future deliberations argue from real evidence.

Event per candidate: {agent: "evaluator", action: "candidate_result",
                       model, critic_score, tests_passed, tests_total,
                       cost_usd, latency_ms}
```

### Step 3.5: the pause — awaiting_preference

```
The graph does NOT pick a winner automatically. It routes through a dedicated
comparison_gate node — the ONLY node besides "critic" in interrupt_after — and
stops there. Task mode never visits this node, so it's completely unaffected.

Event: {agent: "evaluator", action: "awaiting_preference", candidates: [...]}

Two ways out of the pause:
  1. POST /run/{run_id}/commit-preference {"dimension": "cost"|"accuracy"|"latency"}
     → resolve_comparison() picks the winner along that axis, resumes the run.
  2. 2-minute timeout watchdog (server.py) — if nobody answers, auto-applies
     the default rule (highest accuracy, tie broken by lowest cost) and
     resumes automatically. A run can never hang forever.

A passing candidate always outranks a failing one, regardless of dimension.
The winner's test_results + Critic verdict flow forward into tester_node/
critic_node as a pass-through — no third Critic call. The winner's files
become the run's workspace so later steps build on it, same as Task mode.
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

`scheduler/models.py` is the single source of truth for pricing and pools. Task mode and
Agent mode deliberately use **separate pools** — they never share a tier list, so tuning
one can't silently change the other's cost or behavior (this was a real bug once — see
PR #10, "Separate Agent Mode's model tiers from Daily Task's").

```python
MODEL_PRICES = {
    # Anthropic
    "claude-haiku-4-5":  {"provider": "anthropic", "input": 1.00/1M, "output": 5.00/1M,  "tier": 2},
    "claude-sonnet-4-6": {"provider": "anthropic", "input": 3.00/1M, "output": 15.00/1M, "tier": 3},
    "claude-sonnet-5":   {"provider": "anthropic", "input": 2.00/1M, "output": 10.00/1M, "tier": 3},
    "claude-opus-4-6":   {"provider": "anthropic", "input": 5.00/1M, "output": 25.00/1M, "tier": 4},
    "claude-opus-4-8":   {"provider": "anthropic", "input": 5.00/1M, "output": 25.00/1M, "tier": 4},

    # OpenAI
    "gpt-4.1-nano":      {"provider": "openai", "input": 0.10/1M, "output": 0.40/1M,  "tier": 0},
    "gpt-4.1-mini":      {"provider": "openai", "input": 0.40/1M, "output": 1.60/1M,  "tier": 1},
    "gpt-5":             {"provider": "openai", "input": 1.25/1M, "output": 10.00/1M, "tier": 2},
    "gpt-5.4":           {"provider": "openai", "input": 2.50/1M, "output": 15.00/1M, "tier": 3},
    "gpt-5.5":           {"provider": "openai", "input": 5.00/1M, "output": 30.00/1M, "tier": 4},

    # Embeddings (Agent mode's similarity-skip cache) — no output tokens
    "text-embedding-3-small": {"provider": "openai", "input": 0.02/1M, "output": 0.0, "tier": 0},
}

# Task mode's classic (non-debate) router.
DIFFICULTY_TO_MODEL = {
    "EASY":   "gpt-4.1-mini",       # $0.40/$1.60
    "MEDIUM": "claude-haiku-4-5",    # $1.00/$5.00
    "HARD":   "claude-sonnet-5",     # $2.00/$10.00
}

# Task mode's escalation ladder, cheapest -> most expensive.
TIER_LADDER = ["gpt-4.1-mini", "claude-haiku-4-5", "claude-sonnet-5", "gpt-5.5"]

# Old Agent Mode's bake-off pool (orchestrator/agent_mode.py, scheduler/team.py) —
# a full sandbox per candidate, so it stays to two genuinely strong models.
AGENT_MODE_TIER_LADDER = ["claude-sonnet-4-6", "claude-opus-4-6"]

# Agent mode's deliberation pool (scheduler/deliberation.py) — the 5 execution
# candidates the Planner voice + Debate voice + Judge choose between.
DELIBERATION_MODEL_POOL = [
    "gpt-4.1-mini", "gpt-5", "claude-sonnet-4-6", "claude-opus-4-6", "claude-opus-4-8",
]
```

Fixed roles, same across both modes: Planner, Critic, and Team Planner always run on
`claude-sonnet-4-6`; the deliberation's Debate voice always runs on `claude-opus-4-8`;
the deliberation's Judge and the debate router (`scheduler/debate.py`) always run on
`claude-opus-4-6`.

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

Frozen at `docs/EVENT_SCHEMA.md` — the actual source of truth, kept manually in sync with
the TypeScript types in `dashboard/src/types.ts`. Current shape:

```typescript
interface SwarmEvent {
  timestamp: string;
  run_id: string;
  agent: "planner" | "coder" | "critic" | "tester" | "router" | "debate" | "evaluator" | "team_planner";
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
  candidates: string[] | null;      // Agent mode: the candidate model pair in play
  similarity_score: number | null;  // Agent mode: cosine score on similarity_skip events
  matched_step_id: string | null;   // Agent mode: history row id the step matched
  detail: string;
}
```

`agent: "debate"` carries deliberation turns (`deliberation_turn`) — the planner voice /
debate voice / judge exchange. `agent: "evaluator"` carries Agent mode's comparison
results (`candidate_result`, `awaiting_preference`, `winner_selected`).

---

## Dashboard layout

This is the **original Day-1 wireframe** — useful for understanding the intent (agent
grid, routing panel, cost meter, score timeline, decision log), but the actual
implementation has since evolved under a different component structure
(`CostDashboard`, `EventFeed`, `ModelCards`, `RunSelector`, `RunStatusBanner`,
`RoutingDecisionsList`, etc. — see `dashboard/src/components/`). Treat this diagram as
the concept, not the current file names.

```
┌─────────────────────────────────────────────────────────────────┐
│  YIELD                                      [Run] [Baseline]    │
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

## Sandbox execution: local Docker or Akash Network

`sandbox/factory.py` picks the backend from `SANDBOX_BACKEND` at startup — the
orchestrator calls the same interface (`create`, `inject_files`, `run_tests`, `cleanup`)
either way and never knows which one it's talking to.

```
SANDBOX_BACKEND=docker (default)          SANDBOX_BACKEND=akash
  sandbox/manager.py                        sandbox/akash.py
  local `docker run` containers             HTTP calls to pooled pods on
                                             Akash Network (decentralized
                                             compute marketplace)
                                                 │
                                                 ▼
                                        sandbox/agent_server.py runs INSIDE
                                        each pod — stdlib-only HTTP server
                                        exposing GET /health, POST /inject,
                                        POST /run_tests, POST /reset (no
                                        Docker socket available on Akash, so
                                        these replace exec_run/put_archive)
```

Every mutating endpoint on the Akash agent requires a bearer token
(`SANDBOX_AGENT_TOKEN`) since the pod is reachable from the public internet.
`akash/deploy-sandbox.yaml` is the SDL that deploys the pool; `akash/env.sandbox.sh`
holds the testnet chain config for `provider-services`.

---

## Zero-trust access: Pomerium

Two independent Pomerium deployments, fronting two different surfaces:

**1. The dashboard (`pomerium/`)** — an identity-aware reverse proxy in front of
`orchestrator/server.py` (`:8000`). Forces a GitHub login before any browser reaches the
app; `server.py` itself is completely unchanged, since anything that reaches it is
already authenticated.

```
browser ──https──▶ Pomerium ──▶ GitHub login ──▶ policy check ──▶ uvicorn :8000
```

Runs locally against `*.localhost.pomerium.io` (resolves to 127.0.0.1 — no DNS or
`/etc/hosts` changes needed) via `pomerium/docker-compose.pomerium.yml`. The dashboard's
`/ws/events` WebSocket works behind the proxy because the route sets
`allow_websocket_upgrade: true`.

**2. The Akash sandbox mesh (`akash/pomerium/`)** — the *only* public entry point to the
remote sandbox pods; the `agent` service itself moves to the internal Akash mesh
(no longer directly exposed).

```
internet ──https──▶ Akash edge (TLS) ──http──▶ Pomerium ──http──▶ agent:8080
                                                   │ authenticates the orchestrator
                                                   ▼ (fail-closed until auth wired)
```

**Currently fail-closed by design** — the route's policy is `[]` (deny-all) until the
orchestrator's own service identity (JWT or mTLS) is wired in to replace the plain
shared-bearer-token scheme `sandbox/agent_server.py` uses today. See
`akash/pomerium/README.md` for the two remaining steps.

---

## Dependency graph (who imports whom)

```
scheduler/models.py          ← imported by everything, imports nothing
    │
    ├── scheduler/router.py              (imports models + openai for nano)
    │       │
    │       ├── scheduler/debate.py      (imports router for _stats + models)
    │       └── scheduler/similarity.py  (imports models for embed model id)
    │               │
    │               └── scheduler/deliberation.py  (imports router + models)
    │                       │
    │                       └── scheduler/team.py   (imports debate + models — old Agent Mode)
    │
    ├── scheduler/cost_tracker.py        (imports models)
    ├── scheduler/latency_tracker.py     (imports models)
    ├── scheduler/trace_logger.py        (imports models)
    ├── scheduler/budget_guard.py        (imports cost_tracker)
    │
    └── scheduler/tracked_client.py      (imports all above + anthropic + openai; embed() too)
                │
                ├── agents/planner.py       (imports tracked_client only)
                ├── agents/coder.py         (imports tracked_client only)
                ├── agents/critic.py        (imports tracked_client only)
                └── agents/team_planner.py  (imports tracked_client only)
                        │
                        └── orchestrator/loop.py    (imports agents + router + debate +
                                │                     deliberation + similarity)
                                ├── orchestrator/graph.py    (imports loop + state)
                                │       │
                                │       └── orchestrator/server.py  (mounts everything)
                                │
                                └── orchestrator/agent_mode.py  (old Agent Mode — reuses
                                                                  _get_client/_get_sandbox
                                                                  from loop.py, but its own
                                                                  fan-out orchestration,
                                                                  not the LangGraph loop)

sandbox/manager.py  ─┐
sandbox/akash.py    ─┴─→ sandbox/factory.py  (picks backend from SANDBOX_BACKEND env)
                              → consumed by orchestrator/loop.py's _get_sandbox()
```

Key rules:
- Arrows only point downward. No circular imports.
- Agents never import cost_tracker, router, or scheduler directly.
- Agents receive TrackedLLMClient as a dependency — instrumentation is automatic.
- The orchestrator is the only module that wires everything together.
- The dashboard is completely decoupled — it only consumes WebSocket events + REST.
- Task mode and Agent mode (deliberation) share every agent, the sandbox factory, and
  the recording layer — they diverge only in `router_node`'s branch and which model
  pool/constants they read from `scheduler/models.py`.

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

# Sandbox backend: "docker" (local, default) or "akash" (pooled Akash pods).
SANDBOX_BACKEND=docker
# When SANDBOX_BACKEND=akash: comma-separated public sandbox URIs from Akash
# Console (or the Pomerium URI once fronted). Bearer token the pods deploy with.
SANDBOX_AKASH_URLS=
SANDBOX_AGENT_TOKEN=
```

See `pomerium/.env.pomerium.example` for the dashboard proxy's separate secrets
(`POMERIUM_SHARED_SECRET`, `POMERIUM_COOKIE_SECRET`, GitHub OAuth client id/secret).

### requirements.txt
```
anthropic>=0.30.0
openai>=1.30.0
langgraph>=0.2.0
langgraph-checkpoint-sqlite>=2.0.0
langchain-core>=0.3.0
fastapi>=0.115.0
uvicorn>=0.30.0
websockets>=12.0
docker>=7.0.0
pydantic>=2.0
python-dotenv>=1.0.0
pytest>=8.0.0
```
