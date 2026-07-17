# Event Schema

Contract between the backend (orchestrator/agents/scheduler) and the frontend
(dashboard). Every event emitted by the loop and every event rendered by the
dashboard follows this exact shape. Freeze this — all tracks code against it.

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

## Field notes

- `agent` — which node in the loop emitted this event.
- `action` — free-form action name scoped to the agent, e.g. `plan_created`,
  `classify`, `implement`, `run_tests`, `verdict`.
- `step_id` — the `PlanStep.id` this event relates to (e.g. `"s1"`). Empty
  string for run-level events (e.g. the initial `plan_created`).
- `step_class` — the `PlanStep.step_class` this event relates to. Empty
  string when not applicable.
- `model` / `provider` — set on router/coder/critic events that involve an
  LLM call; `null` for the tester (deterministic, no LLM).
- `routing_reason` — human-readable string explaining why the router picked
  this model (e.g. `"nano classified as EASY"`). Empty string when not a
  routing event.
- `cost_usd` / `latency_ms` — `0` for non-LLM events (e.g. tester events),
  never `null`, so the cost meter can sum blindly without null checks.
- `outcome` — `null` until the event represents a completed attempt.
- `agent: "debate"` — Agent-mode deliberation turns (`deliberation_turn`):
  the planner voice / debate voice / judge exchange that selects the two
  candidate models. `model` is the voice speaking, `candidates` its proposal.
- `agent: "evaluator"` — Agent-mode comparison results: `candidate_result`
  (one per candidate, carries real cost/latency/critic_score) and
  `winner_selected` (`model` = winner, `candidates` = the pair compared).
- `similarity_skip` (agent `"router"`) — the step matched a historical step
  above the similarity threshold; deliberation was skipped and the stored
  winning model reused. Carries `similarity_score` + `matched_step_id`.
  Execution still runs in full — only the deliberation is skipped.

## Python mirror

The backend emits events as plain dicts matching this shape (see
`orchestrator/events.py`). Keep the TypeScript interface and the Python
dict-builder in sync manually — there is no shared codegen step.
