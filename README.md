# Yield

A self-directing agent swarm (Planner, Coder, Tester, Critic) that builds software from a spec — with two ways to run it: a fast **Task mode** that routes each step to the cheapest model tier that can handle it, and a deliberative **Agent mode** where two Claude voices debate the model choice, then empirically bake off two candidates in parallel sandboxes before picking a winner.

**Event:** Loop Engineering Hackathon · AWS Builder Loft, SF · July 17, 2026
**Theme:** Self-directing agent loops — plan, act, observe, self-correct

See [ARCHITECTURE.md](ARCHITECTURE.md) for full system design and flow.
See [PLAN.md](PLAN.md) for build schedule, team split, and demo script.

---

## Quick start

```bash
# Clone and setup
git clone https://github.com/KamayaniR/SWARM_MULTIAGENT.git
cd SWARM_MULTIAGENT
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd dashboard && npm install && cd ..

# Add API keys
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY, OPENAI_API_KEY

# Build the local sandbox (or set SANDBOX_BACKEND=akash to use remote pods instead)
docker build -t swarm-sandbox sandbox/

# Run
uvicorn orchestrator.server:app --port 8000 --reload &
cd dashboard && npm run dev
```

Optional: put [Pomerium](pomerium/README.md) in front of the dashboard for zero-trust login before you demo it to anyone else.

---

## What it does

**Task mode** (default): you give it a spec ("build a CSV deduplication CLI"). A Planner breaks it into typed steps. A hybrid router (GPT-4.1 nano classification + historical pass/fail data) picks one model per step from a cheap-to-expensive ladder spanning OpenAI and Anthropic. A Coder implements the step in a sandbox, tests run automatically, a Critic scores the result against a rubric, and a failing step retries — possibly on a stronger model — until it passes or escalates to a human.

**Agent mode**: same loop, but the routing decision is a genuine deliberation. A Planner voice and a Debate voice (both Claude) argue over which of five candidate models suits the step, grounded in real historical pass rates; a judge picks two finalists. Both candidates are then actually built — concurrently, in isolated sandboxes, each fully tested and Critic-judged — and the run **pauses** waiting for you to pick a winner by cost, latency, or accuracy (or it auto-applies the best-accuracy rule after a timeout, so a run never hangs forever). A similarity cache remembers past steps by embedding, so near-duplicate steps skip the deliberation and reuse the model that already won — execution still always runs in full.

A live dashboard shows every routing decision, every dollar spent, and — in Agent mode — the full debate transcript and the side-by-side candidate comparison, in real time.

---

## Why this matters

Every company running AI agents today sends every task to their most expensive model. That's like hiring a senior engineer at $300/hour to rename variables. We built a system that matches task difficulty to model capability automatically — and where it's genuinely unsure, it doesn't guess: it runs the experiment and measures the answer.

---

## Core architecture

```
User → Dashboard → POST /run {mode: "task" | "agent"} → FastAPI server
                                        │
                                        ▼
                                  LangGraph loop
                                        │
                        ┌───────────────┼────────────────────┐
                        ▼               ▼                    ▼
                    Planner          Router               Coder
                  (Sonnet 4.6)   task: nano + history    (routed model)
                                 agent: similarity cache
                                 → deliberation → 2 candidates
                        │               │                    │
                        └────────► Sandbox tests ◄───────────┘
                                  (local Docker or Akash pods)
                                        │
                                        ▼
                                Critic (Sonnet 4.6)
                                        │
                             ┌──────────┼──────────┐
                             ▼          ▼          ▼
                           Pass    Step fail    Plan fail
                           Done    → retry     → re-plan

  Agent mode only: after both candidates are built + judged, the run pauses
  (awaiting_preference) until you pick cost / latency / accuracy — or a
  2-minute timeout auto-applies the default rule.
```

---

## The routers

**Task mode — hybrid LLM + history.** GPT-4.1 nano classifies each step as EASY/MEDIUM/HARD ($0.000022/call). If historical pass/fail data shows a cheaper model reliably handles this step's class, the router overrides downward. Reset the history anytime — the LLM classifier keeps working independently.

**Agent mode — deliberation + empirical comparison.** A Planner voice (Sonnet 4.6) and a Debate voice (Opus 4.8) argue over the model pool for 2–3 rounds; a judge (Opus 4.6) always makes the final call, naming two distinct candidates. Both get built in parallel, fully tested and Critic-scored, and the run waits for a preference before picking a winner. A `text-embedding-3-small` similarity cache skips the deliberation entirely for steps that closely match one already solved.

Task mode and Agent mode use **separate model pools on purpose** — they never share a tier list, so tuning one can't silently change the other's cost or behavior.

---

## Model registry

| Pool | Models | Used by |
|------|--------|---------|
| Task mode ladder | `gpt-4.1-mini` → `claude-haiku-4-5` → `claude-sonnet-5` → `gpt-5.5` | Classic router, baseline mode |
| Agent mode deliberation pool | `gpt-4.1-mini`, `gpt-5`, `claude-sonnet-4-6`, `claude-opus-4-6`, `claude-opus-4-8` | Deliberation's two execution candidates |
| Fixed roles | `claude-sonnet-4-6` (Planner, Critic, Team Planner, deliberation's Planner voice) · `claude-opus-4-8` (Debate voice) · `claude-opus-4-6` (deliberation judge, debate router) | Every mode |
| Routing-only | `gpt-4.1-nano` (difficulty classifier) · `text-embedding-3-small` (similarity cache) | Both modes |

---

## Sandbox execution — local or decentralized

Code runs in a sandboxed container either way — `SANDBOX_BACKEND=docker` (default, local) or `SANDBOX_BACKEND=akash` (pooled containers on [Akash Network](https://akash.network), a decentralized compute marketplace). Same interface either way (`sandbox/factory.py` picks the backend from env); the orchestrator doesn't know or care which one it's talking to.

---

## Zero-trust access — Pomerium

[Pomerium](https://www.pomerium.com) sits in front of two different surfaces:
- **The dashboard** ([pomerium/](pomerium/README.md)) — forces a GitHub login before any browser reaches the FastAPI server; the app code itself is unchanged.
- **The Akash sandbox mesh** ([akash/pomerium/](akash/pomerium/README.md)) — the only public entry point to the remote sandbox pods, currently fail-closed (deny-all) pending the orchestrator's own service-identity auth.

---

## Human in the loop

`POST /intervene` rolls back to a checkpoint and lets you correct the plan mid-run. In Agent mode, `POST /run/{run_id}/commit-preference` lets you pick the winning candidate by hand instead of the default rule — both use LangGraph's checkpointing to pause and resume a live run without losing state.

---

## Team

Three-track parallel development: core loop + agents, scheduler + infrastructure, frontend + demo. See [PLAN.md](PLAN.md) for build schedule.
