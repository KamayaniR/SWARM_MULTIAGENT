# Swarm Control

A self-directing agent swarm (Planner, Coder, Critic) that builds software from a spec,
gated by a Critic rubric, with a cost-aware scheduler routing each step to the cheapest
model tier that can pass it.

See [`PLAN.md`](./PLAN.md) for the full implementation plan: architecture, module layout,
interface contracts, team split, and day-by-day sequencing.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY
docker run hello-world # confirm Docker is working before Day 1
```

## Layout

```
swarm-control/
  agents/         # Planner, Coder, Critic + the shared LLM-call wrapper
  scheduler/      # routing policy (cost-aware model tier selection) + cost ledger
  sandbox/        # Docker sandbox: workspace, patch apply, test run
  orchestrator/   # the plan -> act -> observe -> self-correct loop, trace, checkpoint
  specs/          # spec_trivial.md, spec_escalation.md, spec_demo.md
  config.py       # per-model pricing table, pass threshold, escalation ceiling
  cli.py          # entrypoint: run.py --mode=baseline|scheduled --spec=...
```
