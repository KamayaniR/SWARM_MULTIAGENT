"""Debate-based model router.

Instead of a single nano classification (see router.route), two cheap agents
argue about which model tier should code a step, then converge on one:

  - COST ADVOCATE  — pushes for the cheapest model that can plausibly pass.
  - QUALITY SKEPTIC — pushes for a stronger model when the step (or history)
    shows real risk of failure.

They take turns. Each turn an agent either ACCEPTS the proposal currently on
the table (debate converges) or COUNTERS with a different model + reason. If
they never agree within MAX_TURNS, the skeptic speaks last, so the standing
proposal is the safer one — we take it and flag non-convergence.

The debaters run on the strongest model (Opus 4.6) on purpose: choosing the
right agent/model for a step is a high-leverage decision that shapes every
downstream call, so it's worth spending real reasoning on. Every debate turn is
a real tracked LLM call, so the cost of the discussion shows up honestly in the
cost meter.

Grounding: both debaters are handed the historical pass rates per model for
this step_class (the same data router.py learns from), so the argument is
evidence-based, not pure speculation.
"""

from scheduler import router
from scheduler.models import MODEL_PRICES, TIER_LADDER, resolve_model

# Opus 4.6 is the "discussion" model — it arbitrates which agent/model fits.
DEBATE_MODEL = "claude-opus-4-6"
MAX_TURNS = 4  # advocate, skeptic, advocate, skeptic


def _tier_menu(tier_ladder: list[str]) -> str:
    lines = []
    for model in tier_ladder:
        p = MODEL_PRICES[model]
        lines.append(
            f"  - {model} (tier {p['tier']}, ${p['input'] * 1_000_000:.2f}/"
            f"${p['output'] * 1_000_000:.2f} per 1M in/out tokens)"
        )
    return "\n".join(lines)


def _history_evidence(step_class: str, tier_ladder: list[str]) -> str:
    lines = []
    for model in tier_ladder:
        stats = router._stats(step_class, model)
        if stats["total_attempts"]:
            lines.append(
                f"  - {model}: passed {stats['pass_rate']:.0%} of "
                f"{stats['total_attempts']} past '{step_class}' step(s)"
            )
    if not lines:
        return "  (no history yet for this step class — argue from the description alone)"
    return "\n".join(lines)


ADVOCATE_SYSTEM = """You are the COST ADVOCATE in a two-agent routing debate.

Your goal: get this coding step done on the CHEAPEST model that can still
succeed. Money spent on an over-powered model is money wasted. Default to the
lowest tier and only move up when the QUALITY SKEPTIC gives a concrete,
believable reason the cheap model will actually fail this step.

You are handed the tier menu (cheapest first) and the historical pass rates
for this kind of step. Lean on that history: if a cheap model has a strong
track record on this step_class, cite it and hold your ground.

When you genuinely agree the current proposal on the table is right, ACCEPT it."""

SKEPTIC_SYSTEM = """You are the QUALITY SKEPTIC in a two-agent routing debate.

Your goal: make sure the chosen model is actually strong enough to PASS this
step on the first try — a failed attempt wastes a whole code+test+judge cycle,
which costs far more than picking one tier up front. Push for a higher tier
when the step involves real complexity (algorithms, edge cases, concurrency,
tricky parsing) or when history shows cheap models failing this step_class.

But do not inflate the tier for simple wiring or boilerplate — that just burns
money for no benefit. When the advocate's cheaper choice is genuinely safe,
ACCEPT it. A good skeptic knows when to stop arguing."""


def _debate_tool(tier_ladder: list[str]) -> dict:
    return {
        "name": "debate_turn",
        "description": "Take your turn in the model-routing debate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "accept": {
                    "type": "boolean",
                    "description": "true to accept the proposal currently on the table (ends the debate). Ignored if there is no proposal yet.",
                },
                "model": {
                    "type": "string",
                    "enum": list(tier_ladder),
                    "description": "The model you propose (or the one you are accepting).",
                },
                "rationale": {
                    "type": "string",
                    "description": "One sentence: why this model for this step.",
                },
            },
            "required": ["accept", "model", "rationale"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _context(step_description: str, step_class: str, tier_ladder: list[str]) -> str:
    return (
        f"Step to implement: {step_description}\n"
        f"Step class: {step_class}\n\n"
        f"Available models (cheapest first):\n{_tier_menu(tier_ladder)}\n\n"
        f"History for '{step_class}':\n{_history_evidence(step_class, tier_ladder)}"
    )


def _transcript_text(transcript: list[dict], current: str | None) -> str:
    if not transcript:
        return "No proposals yet. You open the debate."
    lines = []
    for t in transcript:
        verb = "ACCEPTS" if t["accepted"] else "proposes"
        lines.append(f"{t['speaker'].upper()} {verb} {t['proposal']}: {t['rationale']}")
    lines.append(f"\nProposal currently on the table: {current}")
    return "\n".join(lines)


def _ask(
    client, speaker: str, context: str, transcript: list[dict], current: str | None,
    run_id: str, tier_ladder: list[str],
) -> dict:
    system = ADVOCATE_SYSTEM if speaker == "advocate" else SKEPTIC_SYSTEM
    user = (
        f"{context}\n\n"
        f"--- Debate so far ---\n{_transcript_text(transcript, current)}\n\n"
        f"Take your turn."
    )
    result, _metrics = client.call(
        model=DEBATE_MODEL,
        system=system,
        messages=[{"role": "user", "content": user}],
        tool=_debate_tool(tier_ladder),
        run_id=run_id,
        agent="router",
        max_tokens=200,
    )
    return result


def route_debate(
    client, step_description: str, step_class: str, run_id: str,
    tier_ladder: list[str] = TIER_LADDER,
) -> tuple[str, str, list[dict]]:
    """Run the two-agent debate and return (model, reason, transcript).

    transcript is a list of {speaker, accepted, proposal, rationale} dicts,
    one per turn, so callers can surface the back-and-forth in the UI.

    tier_ladder defaults to Daily Task's full cheap-to-expensive TIER_LADDER;
    Agent Mode passes its own AGENT_MODE_TIER_LADDER instead (see
    scheduler/team.py) so the two features never share a candidate pool.
    """
    context = _context(step_description, step_class, tier_ladder)
    transcript: list[dict] = []
    current: str | None = None

    for turn in range(MAX_TURNS):
        speaker = "advocate" if turn % 2 == 0 else "skeptic"
        result = _ask(client, speaker, context, transcript, current, run_id, tier_ladder)
        proposal = resolve_model(result["model"])
        # "accept" only means something once there's a standing proposal.
        accepted = bool(result["accept"]) and current is not None

        transcript.append({
            "speaker": speaker,
            "accepted": accepted,
            "proposal": current if accepted else proposal,
            "rationale": result["rationale"],
        })

        if accepted:
            return current, f"debate converged: {speaker} accepted {current}", transcript

        current = proposal

    # No acceptance within MAX_TURNS. The skeptic spoke last, so `current` is
    # already the safer standing proposal; take it and flag non-convergence.
    return current, f"debate did not converge in {MAX_TURNS} turns; taking standing proposal {current}", transcript


if __name__ == "__main__":
    # Exercises the debate flow with a scripted client — no API key, no spend.
    # Each FakeClient turn returns the next canned tool result in sequence.
    class FakeClient:
        def __init__(self, script):
            self.script = list(script)
            self.i = 0

        def call(self, **kwargs):
            r = self.script[self.i]
            self.i += 1
            return r, {}

    print("--- converges: advocate proposes cheap, skeptic accepts ---")
    client = FakeClient([
        {"accept": False, "model": "gpt-4.1-mini", "rationale": "simple CLI wiring"},
        {"accept": True, "model": "gpt-4.1-mini", "rationale": "agreed, low risk"},
    ])
    model, reason, transcript = route_debate(client, "add argparse flags", "cli_wiring", "test")
    print(model, "|", reason)
    assert model == "gpt-4.1-mini"
    assert transcript[-1]["accepted"] and transcript[-1]["speaker"] == "skeptic"

    print("\n--- escalates: skeptic counters up, advocate concedes ---")
    client = FakeClient([
        {"accept": False, "model": "gpt-4.1-mini", "rationale": "try cheap first"},
        {"accept": False, "model": "claude-sonnet-5", "rationale": "quoted-comma parsing is tricky"},
        {"accept": True, "model": "claude-sonnet-5", "rationale": "fair, edge cases are real"},
    ])
    model, reason, transcript = route_debate(client, "parse CSV with quoted commas", "io_parsing", "test")
    print(model, "|", reason)
    assert model == "claude-sonnet-5"
    assert transcript[-1]["speaker"] == "advocate" and transcript[-1]["accepted"]

    print("\n--- no convergence: skeptic's standing proposal wins (safety) ---")
    client = FakeClient([
        {"accept": False, "model": "gpt-4.1-mini", "rationale": "cheap"},
        {"accept": False, "model": "claude-sonnet-5", "rationale": "risky"},
        {"accept": False, "model": "gpt-4.1-mini", "rationale": "still cheap"},
        {"accept": False, "model": "claude-sonnet-5", "rationale": "still risky"},
    ])
    model, reason, transcript = route_debate(client, "implement dedup", "algorithm", "test")
    print(model, "|", reason)
    assert model == "claude-sonnet-5"
    assert "did not converge" in reason
    assert len(transcript) == MAX_TURNS

    print("\nok")
