"""Agent-mode deliberation: pick TWO candidate models for a step, not one.

Three fixed participants discuss which of the five execution candidates
(scheduler/models.py::DELIBERATION_MODEL_POOL) suit a step:

  - PLANNER VOICE (claude-sonnet-4-6) — argues from the plan's perspective:
    what the step actually needs, where cheap models suffice.
  - DEBATE VOICE  (claude-opus-4-8)   — the counterweight: stress-tests the
    planner voice's pick against complexity and failure history.
  - JUDGE         (claude-opus-4-6)   — reads the whole exchange and selects
    the final two candidates, each with a stated rationale.

GPT-5 and GPT-4.1 mini are execution candidates only — they can be *chosen*
but never speak.

Round structure: each round is one planner-voice turn followed by one
debate-voice turn, each proposing a candidate pair + rationale. After round 2,
if both voices' latest pairs agree, discussion stops early; otherwise one more
round runs (hard cap MAX_ROUNDS = 3). The judge then always makes the final
call — even on agreement, so the selection is always the judge's.

The output is intentionally two candidates: downstream, Agent mode builds the
step with BOTH models in separate sandboxes and compares real cost / latency /
critic accuracy (orchestrator/loop.py), rather than trusting the discussion's
guess about which would win.

Grounding: all three participants see the historical pass rates per model for
this step_class (router._stats — the same data every other router layer uses).
"""

from scheduler import router
from scheduler.models import DELIBERATION_MODEL_POOL, MODEL_PRICES, resolve_model

PLANNER_VOICE_MODEL = "claude-sonnet-4-6"
DEBATE_VOICE_MODEL = "claude-opus-4-8"
JUDGE_MODEL = "claude-opus-4-6"

MIN_ROUNDS = 2   # always at least two full rounds of discussion
MAX_ROUNDS = 3   # hard cap


def _pool_menu() -> str:
    lines = []
    for model in DELIBERATION_MODEL_POOL:
        p = MODEL_PRICES[model]
        lines.append(
            f"  - {model} (${p['input'] * 1_000_000:.2f}/"
            f"${p['output'] * 1_000_000:.2f} per 1M in/out tokens)"
        )
    return "\n".join(lines)


def _history_evidence(step_class: str) -> str:
    lines = []
    for model in DELIBERATION_MODEL_POOL:
        stats = router._stats(step_class, model)
        if stats["total_attempts"]:
            lines.append(
                f"  - {model}: passed {stats['pass_rate']:.0%} of "
                f"{stats['total_attempts']} past '{step_class}' step(s)"
            )
    if not lines:
        return "  (no history yet for this step class — argue from the description alone)"
    return "\n".join(lines)


PLANNER_VOICE_SYSTEM = """You are the PLANNER'S VOICE in a model-selection discussion.

You planned this step, so argue from what the step actually needs: its real
complexity, its edge cases, and how it fits the surrounding plan. Favor the
cheapest candidates that can genuinely pass — an over-powered model wastes
money — but never talk down real complexity just to save cost.

Each turn, propose the TWO candidate models you believe should be built and
compared for this step, with a one-sentence rationale. Both candidates will
actually be run, so a good pair is a genuine question worth answering (e.g.
"is the cheap one enough?"), not two safe picks."""

DEBATE_VOICE_SYSTEM = """You are the DEBATE VOICE in a model-selection discussion.

Stress-test the planner's proposal. Where is the step riskier than it looks —
tricky parsing, algorithmic subtlety, concurrency, edge cases? Where does the
historical pass-rate evidence contradict the planner's optimism? Push the pair
toward stronger candidates when failure looks likely, and toward cheaper ones
when the planner is over-buying.

Each turn, propose the TWO candidate models you believe should be built and
compared, with a one-sentence rationale. If the planner's current pair is
genuinely right, propose the same pair — agreement ends the discussion."""

JUDGE_SYSTEM = """You are the JUDGE of a model-selection discussion.

Two voices have discussed which models suit this step. Read the exchange and
the historical evidence, then select the FINAL two candidate models to build
and compare. You are not bound by either voice's pairs — pick the two that
make the comparison most worth running: typically one candidate that is
probably sufficient and one that answers the question the discussion left
open. Give a one-sentence rationale per candidate."""


def _voice_tool() -> dict:
    return {
        "name": "propose_candidates",
        "description": "Propose the two candidate models to build and compare for this step.",
        "input_schema": {
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(DELIBERATION_MODEL_POOL)},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "Exactly two distinct models from the pool.",
                },
                "rationale": {
                    "type": "string",
                    "description": "One sentence: why this pair for this step.",
                },
            },
            "required": ["candidates", "rationale"],
        },
    }


def _judge_tool() -> dict:
    return {
        "name": "select_candidates",
        "description": "Select the final two candidate models and give a rationale for each.",
        "input_schema": {
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(DELIBERATION_MODEL_POOL)},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "Exactly two distinct models from the pool.",
                },
                "rationales": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "One rationale per candidate, same order.",
                },
            },
            "required": ["candidates", "rationales"],
        },
    }


def _context(step_description: str, step_class: str) -> str:
    return (
        f"Step to implement: {step_description}\n"
        f"Step class: {step_class}\n\n"
        f"Candidate pool (cheapest first):\n{_pool_menu()}\n\n"
        f"History for '{step_class}':\n{_history_evidence(step_class)}"
    )


def _transcript_text(transcript: list[dict]) -> str:
    if not transcript:
        return "No proposals yet. You open the discussion."
    lines = []
    for t in transcript:
        pair = " + ".join(t["candidates"])
        lines.append(f"[round {t['round']}] {t['speaker'].upper()} proposes {pair}: {t['rationale']}")
    return "\n".join(lines)


def _pair_key(candidates: list[str]) -> frozenset:
    return frozenset(resolve_model(c) for c in candidates)


def deliberate(
    client, step_description: str, step_class: str, run_id: str,
) -> tuple[list[str], list[str], list[dict], str]:
    """Run the full deliberation and return (candidates, rationales, transcript, reason).

    candidates — the judge's final two model ids.
    rationales — one per candidate, same order.
    transcript — every turn: {round, speaker, voice_model, candidates, rationale},
                 with the judge's decision appended as the last entry.
    reason     — one line summarizing how the discussion resolved.
    """
    context = _context(step_description, step_class)
    transcript: list[dict] = []

    rounds_run = 0
    for round_no in range(1, MAX_ROUNDS + 1):
        rounds_run = round_no
        for speaker, voice_model, system in (
            ("planner_voice", PLANNER_VOICE_MODEL, PLANNER_VOICE_SYSTEM),
            ("debate_voice", DEBATE_VOICE_MODEL, DEBATE_VOICE_SYSTEM),
        ):
            user = (
                f"{context}\n\n"
                f"--- Discussion so far ---\n{_transcript_text(transcript)}\n\n"
                f"Round {round_no}: take your turn."
            )
            result, _metrics = client.call(
                model=voice_model,
                system=system,
                messages=[{"role": "user", "content": user}],
                tool=_voice_tool(),
                run_id=run_id,
                agent="debate",
                max_tokens=300,
            )
            transcript.append({
                "round": round_no,
                "speaker": speaker,
                "voice_model": voice_model,
                "candidates": [resolve_model(c) for c in result["candidates"]],
                "rationale": result["rationale"],
            })

        # Early stop after the minimum rounds when the two voices agree.
        if round_no >= MIN_ROUNDS:
            planner_pair = _pair_key(transcript[-2]["candidates"])
            debate_pair = _pair_key(transcript[-1]["candidates"])
            if planner_pair == debate_pair:
                break

    # The judge always makes the final call.
    judge_user = (
        f"{context}\n\n"
        f"--- Full discussion ---\n{_transcript_text(transcript)}\n\n"
        f"Select the final two candidates."
    )
    verdict, _metrics = client.call(
        model=JUDGE_MODEL,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": judge_user}],
        tool=_judge_tool(),
        run_id=run_id,
        agent="debate",
        max_tokens=300,
    )
    candidates = [resolve_model(c) for c in verdict["candidates"]]
    rationales = list(verdict["rationales"])
    if candidates[0] == candidates[1]:
        # Judge degenerate case: fall back to the pool's adjacent model so the
        # comparison still compares two different things.
        idx = DELIBERATION_MODEL_POOL.index(candidates[0])
        alt = DELIBERATION_MODEL_POOL[idx - 1] if idx > 0 else DELIBERATION_MODEL_POOL[idx + 1]
        candidates[1] = alt
        rationales[1] = f"(auto-substituted distinct contrast candidate) {rationales[1]}"

    transcript.append({
        "round": rounds_run,
        "speaker": "judge",
        "voice_model": JUDGE_MODEL,
        "candidates": candidates,
        "rationale": " / ".join(rationales),
    })
    reason = (
        f"deliberation ({rounds_run} round(s)) selected "
        f"{candidates[0]} vs {candidates[1]}"
    )
    return candidates, rationales, transcript, reason


if __name__ == "__main__":
    # Exercises the deliberation flow with a scripted client — no API, no spend.
    class FakeClient:
        def __init__(self, script):
            self.script = list(script)
            self.i = 0
            self.models_called = []

        def call(self, **kwargs):
            self.models_called.append(kwargs["model"])
            r = self.script[self.i]
            self.i += 1
            return r, {}

    print("--- voices agree after round 2: early stop, judge confirms ---")
    client = FakeClient([
        # round 1
        {"candidates": ["gpt-4.1-mini", "claude-sonnet-4-6"], "rationale": "cheap probably fine"},
        {"candidates": ["claude-sonnet-4-6", "claude-opus-4-6"], "rationale": "parsing risk"},
        # round 2 — both land on the same pair
        {"candidates": ["gpt-4.1-mini", "claude-sonnet-4-6"], "rationale": "history favors cheap"},
        {"candidates": ["claude-sonnet-4-6", "gpt-4.1-mini"], "rationale": "fair, agreed"},
        # judge
        {"candidates": ["gpt-4.1-mini", "claude-sonnet-4-6"], "rationales": ["probably enough", "the open question"]},
    ])
    candidates, rationales, transcript, reason = deliberate(client, "add argparse flags", "cli_wiring", "test")
    print(candidates, "|", reason)
    assert candidates == ["gpt-4.1-mini", "claude-sonnet-4-6"]
    assert len(transcript) == 5  # 2 rounds x 2 voices + judge
    assert transcript[-1]["speaker"] == "judge"
    assert client.models_called == [
        "claude-sonnet-4-6", "claude-opus-4-8",
        "claude-sonnet-4-6", "claude-opus-4-8",
        "claude-opus-4-6",
    ]

    print("\n--- voices never agree: hard cap at 3 rounds, judge decides ---")
    client = FakeClient([
        {"candidates": ["gpt-4.1-mini", "gpt-5"], "rationale": "cheap"},
        {"candidates": ["claude-opus-4-6", "claude-opus-4-8"], "rationale": "risky"},
        {"candidates": ["gpt-4.1-mini", "gpt-5"], "rationale": "still cheap"},
        {"candidates": ["claude-opus-4-6", "claude-opus-4-8"], "rationale": "still risky"},
        {"candidates": ["gpt-4.1-mini", "gpt-5"], "rationale": "cheap"},
        {"candidates": ["claude-opus-4-6", "claude-opus-4-8"], "rationale": "risky"},
        {"candidates": ["gpt-5", "claude-opus-4-6"], "rationales": ["middle ground", "covers the risk"]},
    ])
    candidates, rationales, transcript, reason = deliberate(client, "implement dedup", "algorithm", "test")
    print(candidates, "|", reason)
    assert candidates == ["gpt-5", "claude-opus-4-6"]
    assert len(transcript) == 7  # 3 rounds x 2 voices + judge
    assert "3 round(s)" in reason

    print("\n--- degenerate judge pick: auto-substitutes a distinct contrast ---")
    client = FakeClient([
        {"candidates": ["claude-sonnet-4-6", "claude-opus-4-6"], "rationale": "a"},
        {"candidates": ["claude-sonnet-4-6", "claude-opus-4-6"], "rationale": "b"},
        {"candidates": ["claude-sonnet-4-6", "claude-opus-4-6"], "rationale": "c"},
        {"candidates": ["claude-sonnet-4-6", "claude-opus-4-6"], "rationale": "d"},
        {"candidates": ["claude-opus-4-8", "claude-opus-4-8"], "rationales": ["strong", "strong"]},
    ])
    candidates, rationales, transcript, reason = deliberate(client, "x", "algorithm", "test")
    print(candidates)
    assert candidates[0] == "claude-opus-4-8"
    assert candidates[1] == "claude-opus-4-6"  # adjacent distinct fallback
    assert candidates[0] != candidates[1]

    print("\nok")
