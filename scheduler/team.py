"""Per-role candidate selection for Agent mode.

Agent mode doesn't route a step to a single model — it bakes off two candidate
models per role and lets the evidence (cost + critic score from a real sandbox
run) decide. This module picks those two candidates:

  1. Run the existing two-agent routing debate (scheduler/debate.py) to get the
     model it recommends for the role.
  2. Pick a *contrast* candidate one tier away on TIER_LADDER — one tier cheaper
     if the debate's pick isn't already the cheapest, otherwise one tier pricier.

That gives every role a deliberate "cheap vs. quality" matchup, which is exactly
the comparison Agent mode presents to the user. The debate transcript is passed
back so the UI can show the back-and-forth in the decision log.
"""

from scheduler import debate
from scheduler.models import AGENT_MODE_TIER_LADDER, resolve_model


def _contrast(pick: str) -> str:
    """The adjacent tier to bake off against `pick`: one cheaper if possible,
    else one pricier. `pick` is always a full model id from
    AGENT_MODE_TIER_LADDER."""
    idx = AGENT_MODE_TIER_LADDER.index(pick)
    if idx > 0:
        return AGENT_MODE_TIER_LADDER[idx - 1]
    return AGENT_MODE_TIER_LADDER[idx + 1]


def select_candidates(
    client, step_description: str, step_class: str, run_id: str
) -> tuple[list[str], str, list[dict]]:
    """Return (candidates, reason, transcript) for a role.

    candidates is [debate_pick, contrast] — two distinct model ids from
    AGENT_MODE_TIER_LADDER to bake off. reason + transcript come from the
    routing debate, run over Agent Mode's own tier pool (not Daily Task's).
    """
    pick, reason, transcript = debate.route_debate(
        client, step_description, step_class, run_id, tier_ladder=AGENT_MODE_TIER_LADDER
    )
    pick = resolve_model(pick)
    contrast = _contrast(pick)
    return [pick, contrast], reason, transcript


if __name__ == "__main__":
    # Exercises candidate selection with a scripted client — no API key, no spend.
    class FakeClient:
        def __init__(self, script):
            self.script = list(script)
            self.i = 0

        def call(self, **kwargs):
            r = self.script[self.i]
            self.i += 1
            return r, {}

    print("--- debate picks the premium tier: contrast is the base model ---")
    client = FakeClient([
        {"accept": False, "model": "claude-opus-4-6", "rationale": "tricky edge cases"},
        {"accept": True, "model": "claude-opus-4-6", "rationale": "agreed"},
    ])
    candidates, reason, transcript = select_candidates(
        client, "parse CSV with quoted commas", "io_parsing", "test"
    )
    print(candidates, "|", reason)
    assert candidates == ["claude-opus-4-6", "claude-sonnet-4-6"], candidates
    assert len(set(candidates)) == 2

    print("\n--- debate picks the base tier: contrast is the premium model ---")
    client = FakeClient([
        {"accept": False, "model": "claude-sonnet-4-6", "rationale": "simple wiring"},
        {"accept": True, "model": "claude-sonnet-4-6", "rationale": "low risk"},
    ])
    candidates, reason, transcript = select_candidates(
        client, "add argparse flags", "cli_wiring", "test"
    )
    print(candidates, "|", reason)
    assert candidates == ["claude-sonnet-4-6", "claude-opus-4-6"], candidates
    assert len(set(candidates)) == 2

    print("\nok")
