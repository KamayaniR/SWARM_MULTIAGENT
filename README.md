# Swarm Control

A self-directing agent swarm (Planner, Coder, Critic) that builds software from a spec, gated by a Critic rubric, with a **hybrid LLM + history router** that classifies each step's difficulty and routes it to the cheapest model tier that can handle it.

**Event:** Loop Engineering Hackathon · AWS Builder Loft, SF · July 17, 2026
**Theme:** Self-directing agent loops — plan, act, observe, self-correct

See [ARCHITECTURE.md](ARCHITECTURE.md) for full system design and flow.
See [PLAN.md](PLAN.md) for build schedule, team split, and demo script.

---

## Quick start

```bash
# Clone and setup
git clone git@github.com:ayushitomar03/swarm-control.git
cd swarm-control
pip install -r requirements.txt
cd dashboard && npm install && cd ..

# Add API keys
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY, OPENAI_API_KEY

# Build sandbox
docker build -t swarm-sandbox sandbox/

# Run
uvicorn orchestrator.server:app --port 8000 --reload &
cd dashboard && npm run dev
```

---

## What it does (one paragraph)

You give it a task spec ("build a CSV deduplication CLI"). A Planner breaks the spec into typed steps. A hybrid router (GPT-4.1 nano LLM classification + historical pass/fail data) picks the cheapest model for each step. A Coder implements each step in a Docker sandbox. Tests run automatically. A Critic scores the output against a rubric. If it fails, the router may escalate to a stronger model and the Coder retries with the Critic's feedback. A live dashboard shows every decision, every cost, and every routing choice in real time.

---

## Why this matters

Every company running AI agents today sends every task to their most expensive model. That's like hiring a senior engineer at $300/hour to rename variables. We built the system that automatically matches task difficulty to model capability, saving 40-70% on agent costs while maintaining the same output quality.

---

## Core architecture

```
User → Dashboard → POST /run → FastAPI server
                                    │
                                    ▼
                              LangGraph loop
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
                Planner         Router          Coder
               (Sonnet)     (nano + history)   (routed model)
                    │               │               │
                    └───────► Sandbox tests ◄───────┘
                                    │
                                    ▼
                              Critic (Sonnet)
                                    │
                         ┌──────────┼──────────┐
                         ▼          ▼          ▼
                       Pass    Step fail    Plan fail
                       Done    → retry     → re-plan
```

---

## The router (hybrid LLM + history)

**Primary:** GPT-4.1 nano classifies each step as EASY/MEDIUM/HARD ($0.000022 per call, 200-500ms). Always works, never corrupts.

**Enhancement:** Historical pass/fail data per step class. If history shows a cheaper model works for this task type, override the LLM classification downward. If history is corrupted, reset it — the LLM router keeps working independently.

**Production path:** Swap GPT-4.1 nano for a self-hosted DistilBERT (50ms, $0.00 per call). Same interface, zero changes to the rest of the system.

---

## Model tiers

| Tier | Model | Input $/1M | Output $/1M | Used for |
|------|-------|-----------|------------|----------|
| 1 | GPT-4.1 mini | $0.40 | $1.60 | Easy tasks: CLI wiring, test scaffolding |
| 2 | Claude Haiku 4.5 | $1.00 | $5.00 | Medium tasks: file parsing, I/O |
| 3 | Claude Sonnet 5 | $2.00 | $10.00 | Hard tasks: algorithms, complex logic |
| 4 | GPT-5.5 | $5.00 | $30.00 | Hardest tasks: fallback for everything |
| Router | GPT-4.1 nano | $0.10 | $0.40 | Routing classification only |

---

## Team

Three-track parallel development: core loop + agents, scheduler + infrastructure, frontend + demo. See [PLAN.md](PLAN.md) for build schedule.
