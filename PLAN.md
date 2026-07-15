# Build plan

## Team assignments

| Track | Role | Owns | Days 1-2 focus | Days 3-4 focus |
|-------|------|------|----------------|----------------|
| **Track A** | Core loop + agents | `agents/`, `orchestrator/state.py`, `orchestrator/graph.py`, `orchestrator/loop.py` | LangGraph state machine, Planner/Coder/Critic prompts, loop convergence | Integration with router + sandbox, intervene feature, second demo task |
| **Track B** | Scheduler + infra | `scheduler/`, `sandbox/`, `orchestrator/server.py`, `orchestrator/events.py` | Docker sandbox, hybrid router, cost/latency tracking, TrackedLLMClient | FastAPI + WebSocket, API endpoints, reset endpoint, reliability |
| **Track C** | Frontend + demo | `dashboard/`, `demo/`, `docs/` | React scaffold, mock event stream, agent grid, decision log | Real WebSocket integration, cost meter, comparison chart, pitch, video |

### Contract: freeze the event schema (Day 1, first thing, all tracks)
All three tracks code against the event schema in `docs/EVENT_SCHEMA.md`.
Agree on it before anyone writes code. Takes 30 minutes.

---

## Day-by-day schedule

### Day 1 — Core loop + scaffold (highest risk first)

**Track A (agents):**
- [ ] Define SwarmState TypedDict in `orchestrator/state.py`
- [ ] Build LangGraph StateGraph: planner → coder → tester → critic nodes
- [ ] Write Planner system prompt (must output typed steps with step_class)
- [ ] Write Coder system prompt
- [ ] Write Critic system prompt with rubric (structured JSON via tool_use)
- [ ] Hardcode all calls to Sonnet (no router yet)
- [ ] Get loop converging end-to-end on demo task #1 (CSV dedup CLI)
- [ ] Print events to stdout in schema format
- **Exit criteria:** loop runs spec → passing build with ≥ 2 self-corrections, unattended

**Track B (scheduler):**
- [ ] Build Docker sandbox: Dockerfile, SandboxManager class
- [ ] `create_container()`, `inject_files()`, `run_tests()`, `cleanup()`
- [ ] Build `scheduler/models.py`: MODEL_PRICES, TIER_LADDER, CallRecord
- [ ] Build `scheduler/tracked_client.py`: wrap Anthropic + OpenAI SDKs
- [ ] Test: inject a Python file + test file into container, run pytest, get results
- **Exit criteria:** sandbox works reliably, TrackedLLMClient calls both providers

**Track C (frontend):**
- [ ] Initialize React + Vite project in `dashboard/`
- [ ] Create mock event stream from `mock/mock_events.json`
- [ ] Build layout shell: header, agent grid area, log area, cost area
- [ ] Build AgentGrid component rendering mock events
- [ ] Build DecisionLog component (scrolling event feed)
- **Exit criteria:** dashboard renders mock events, agents light up

**All tracks together (first thing):**
- [ ] Freeze event schema in `docs/EVENT_SCHEMA.md`
- [ ] Agree on SwarmState fields
- [ ] Create all GitHub issues (see below)

---

### Day 2 — Router + cost tracking + dashboard components

**Track A (agents):**
- [ ] Wire TrackedLLMClient into all agent calls (replace direct SDK calls)
- [ ] Test loop with tracked calls → verify events print correctly
- [ ] Add max iteration cap (8) with escalation-to-human message
- [ ] Add LangGraph checkpointing (SqliteSaver)
- **Exit criteria:** loop converges with full event logging and checkpoints

**Track B (scheduler):**
- [ ] Build hybrid router: GPT-4.1 nano classification + history table
- [ ] Build `classify_with_nano()` function
- [ ] Build history table in SQLite (rolling window, last 10 per class/model)
- [ ] Build `record_outcome()` → updates history after Critic verdict
- [ ] Build reset endpoint: `POST /scheduler/reset`
- [ ] Build CostTracker with SQLite + dashboard query methods
- [ ] Build LatencyTracker + TraceLogger
- [ ] Build BudgetGuard (per-run + daily limits)
- **Exit criteria:** router classifies steps, history accumulates, cost tracks

**Track C (frontend):**
- [ ] Build ScoreTimeline (Recharts line chart, pass threshold line at 8.5)
- [ ] Build RoutingPanel (per-step cards: step_class, difficulty, model, reason)
- [ ] Build CostMeter (running total, updates on each event)
- [ ] All components work against mock events
- **Exit criteria:** all dashboard panels render mock data correctly

---

### Day 3 — Integration (connect everything)

**Track A (agents):**
- [ ] Integrate router into loop: before Coder, call router.route()
- [ ] After Critic verdict, call router.record_outcome()
- [ ] Run baseline mode (all GPT-5.5) and scheduler mode on demo task #1
- [ ] Capture cost numbers → verify scheduler is cheaper
- [ ] If margin is thin, tune task or router priors
- **Exit criteria:** scheduler mode converges cheaper than baseline

**Track B (scheduler):**
- [ ] Build FastAPI server: POST /run, POST /run/baseline, POST /intervene
- [ ] Build WebSocket /ws/events → stream events as they happen
- [ ] Build REST endpoints: /api/costs/{id}, /api/compare/..., /api/traces/{id}
- [ ] Connect loop to the server (run loop in background task)
- **Exit criteria:** full run watchable live via WebSocket, API endpoints return data

**Track C (frontend):**
- [ ] Swap mock event stream for real WebSocket connection
- [ ] Verify all components render real data from a live run
- [ ] Build ComparisonChart (baseline vs scheduler bar chart from API)
- [ ] Add model badge on Coder agent card (shows which model is mounted)
- **Exit criteria:** full run watchable in the browser with real data

---

### Day 4 — Polish features + second demo task

**Track A (agents):**
- [ ] Build intervene feature: POST /intervene → rollback checkpoint → re-plan
- [ ] Prepare demo task #2 (e.g. small Flask API) with different step_class mix
- [ ] Run task #1 twice, then task #2 → verify history transfers across tasks
- [ ] Rehearse the loop: does it converge reliably on both tasks?
- **Exit criteria:** intervention works, two demo tasks ready, learning transfers

**Track B (scheduler):**
- [ ] Build trace endpoint: GET /api/traces/{run_id}
- [ ] Test reset endpoint: corrupt history → reset → verify LLM router still works
- [ ] Load test: run 5 consecutive runs, verify cost curve trends down
- [ ] Stress test BudgetGuard: verify it stops runaway loops
- **Exit criteria:** all endpoints reliable, reset tested, cost curve validated

**Track C (frontend):**
- [ ] Build InterveneModal (click step → correction → submit)
- [ ] Build TraceViewer (click event → full prompt/response/cost detail)
- [ ] Visual polish: animations, colors, projector-friendly contrast
- [ ] Build learning curve chart (cost per run trending down)
- **Exit criteria:** all UI features working, looks good on projector

---

### Day 5 — Demo prep + insurance

**All tracks:**
- [ ] Record screen capture of perfect run (backup video)
- [ ] Rehearse 2-minute pitch 3+ times
- [ ] Test on projector resolution
- [ ] Prepare chaos scenarios: API slow? WiFi down? Run doesn't converge?
- [ ] Script sponsor mentions: AWS (infra), Pomerium (security)
- [ ] If time: swap nano API for DistilBERT (stretch goal)
- **Exit criteria:** video recorded, pitch rehearsed, backup plans ready

### Hackathon day (July 17)
- [ ] Re-scaffold per event rules (check with organizers about pre-built code)
- [ ] Do one visible new feature during event hours (e.g. Bedrock tier)
- [ ] Demo rehearsal before judging
- [ ] Mobile hotspot ready as WiFi backup

---

## GitHub issues (copy-paste into GitHub)

### Day 1

**#1: Freeze event schema** · P0 · all tracks · day-1
Agree on JSON schema for events. Define in docs/EVENT_SCHEMA.md.
Include sample events for planner, router, coder, tester, critic.
Both TypeScript and Python versions.

**#2: LangGraph state machine** · P0 · track-a · day-1
SwarmState TypedDict, StateGraph with planner/coder/tester/critic nodes.
Conditional edges: pass → END, step_fail → coder, plan_fail → planner.
Hardcoded Sonnet, events printed to stdout.

**#3: Planner agent prompt** · P0 · track-a · day-1
System prompt that produces typed steps with step_class labels.
Structured JSON via tool_use. Test on 2+ specs.

**#4: Critic agent prompt + rubric** · P0 · track-a · day-1
Structured JSON verdict via tool_use. Scores 0-10.
Failure classification: step_level vs plan_level. Test with good and bad code.

**#5: Docker sandbox** · P0 · track-b · day-1
Dockerfile, SandboxManager: create/inject/run_tests/cleanup.
Returns structured test results.

**#6: TrackedLLMClient** · P0 · track-b · day-1
Multi-provider wrapper. Anthropic + OpenAI behind one interface.
Auto-records cost, latency, trace on every call.

**#7: Dashboard scaffold + mock stream** · P0 · track-c · day-1
React + Vite, mock WebSocket, layout shell, AgentGrid, DecisionLog.

### Day 2

**#8: Hybrid router** · P0 · track-b · day-2
GPT-4.1 nano classification + SQLite history table.
classify_with_nano(), record_outcome(), find_cheapest_passing_tier().
Rolling window (last 10). Reset endpoint.

**#9: Cost + latency tracking** · P0 · track-b · day-2
CostTracker (SQLite), LatencyTracker (memory), TraceLogger (JSONL).
BudgetGuard with per-run and daily limits.

**#10: Wire TrackedLLMClient into loop** · P0 · track-a · day-2
Replace direct SDK calls. Verify events print correctly.
Add checkpointing (SqliteSaver). Max iteration cap.

**#11: Dashboard panels** · P0 · track-c · day-2
ScoreTimeline, RoutingPanel, CostMeter. All against mock events.

### Day 3

**#12: Integrate router into loop** · P0 · track-a · day-3
Router.route() before Coder. record_outcome() after Critic.
Baseline vs scheduler comparison with real numbers.

**#13: FastAPI + WebSocket server** · P0 · track-b · day-3
POST /run, /run/baseline, /intervene. WS /ws/events. REST cost endpoints.

**#14: Dashboard real integration** · P0 · track-c · day-3
Swap mock → real WebSocket. ComparisonChart. Model badge on Coder card.

### Day 4

**#15: Intervene feature** · P1 · track-a · day-4
POST /intervene → checkpoint rollback → re-plan → resume.

**#16: Second demo task** · P1 · track-a · day-4
Flask API task. Verify history transfers. Learning curve data.

**#17: Trace + reset + stress test** · P1 · track-b · day-4
GET /api/traces. Reset tested. 5 consecutive runs. Budget guard tested.

**#18: InterveneModal + TraceViewer + polish** · P1 · track-c · day-4
Intervene UI, trace detail modal, learning curve chart, visual polish.

### Day 5

**#19: Demo video + rehearsal** · P0 · all tracks · day-5
Screen recording, 3+ pitch rehearsals, projector test, backup plans.

**#20: DistilBERT router (stretch)** · P2 · track-b · day-5
Only if everything else is done. Swap nano API for self-hosted classifier.

---

## Demo script (2 minutes)

**Hook (15s):**
"Every agent loop in production today runs its most expensive model on every step. That's like hiring a senior engineer to rename variables. We built the router that fixes this."

**Baseline (15s):**
Show the all-GPT-5.5 run's cost. "Same task, all-flagship: $X."

**Scheduler run (60s):**
Kick off live. Narrate the routing panel: "Watch — nano classifies this step as EASY, sends it to GPT-4.1 mini at 40 cents per million. Now this step is HARD, it goes to Sonnet. Each routing decision costs two hundredths of a cent."
Point at the cost meter running under baseline.

**Learning (15s):**
Show the cross-run chart. "Run 1 explored. Run 3 already skips the wasted attempts. It gets cheaper every time."

**Trust close (15s):**
Open trace viewer on one decision. "Every call, every dollar, every routing choice — auditable. If the history corrupts, one API call resets it and the LLM router keeps working. Loops you can actually put in production."

---

## Anticipated judge questions

**"How is this different from LangGraph Studio / AgentOps?"**
Those are passive observability. We actively optimize routing and costs. Observability is a feature, not the product.

**"Why three agents, not five?"**
Critic must be separate from Coder (self-grading bias). Every other role is collapsed. We removed complexity on purpose.

**"Why not RL for routing?"**
Sample efficiency and explainability. The nano classifier works from Run 1. RL needs hundreds of episodes. And every routing decision is one sentence.

**"What if the nano classifier is wrong?"**
History data corrects it over time. If nano says MEDIUM but the cheap model consistently passes, history overrides downward. And the Critic catches bad outputs regardless.

**"What if history corrupts?"**
One API call resets it. The nano classifier keeps working independently. No downtime.

**"Does this generalize beyond coding?"**
The router only needs a task description and pass/fail signals. Any workflow with a verifier fits: data pipelines, document processing, QA.

---

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Nano misclassifies steps | History corrects over time; Critic catches bad output |
| Scheduler shows no cost win | Pick tasks with easy/hard mix; tune in rehearsal |
| Loop doesn't converge live | Well-scoped tasks, iteration cap, backup video |
| API rate limits at event | Local sandbox; mobile hotspot; cached warm run |
| History corruption | Reset endpoint + LLM router fallback |
| Pre-build rules strict | Ask organizers this week |
| Live demo failure | Pre-recorded video backup |
