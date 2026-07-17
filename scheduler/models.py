from dataclasses import dataclass, field
from datetime import datetime, timezone

MODEL_PRICES = {
    # Anthropic
    "claude-haiku-4-5": {"provider": "anthropic", "input": 1.00 / 1_000_000, "output": 5.00 / 1_000_000, "tier": 2},
    "claude-sonnet-4-6": {"provider": "anthropic", "input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000, "tier": 3},
    "claude-sonnet-5": {"provider": "anthropic", "input": 2.00 / 1_000_000, "output": 10.00 / 1_000_000, "tier": 3},
    "claude-opus-4-6": {"provider": "anthropic", "input": 5.00 / 1_000_000, "output": 25.00 / 1_000_000, "tier": 4},
    "claude-opus-4-8": {"provider": "anthropic", "input": 5.00 / 1_000_000, "output": 25.00 / 1_000_000, "tier": 4},

    # OpenAI
    "gpt-4.1-nano": {"provider": "openai", "input": 0.10 / 1_000_000, "output": 0.40 / 1_000_000, "tier": 0},
    "gpt-4.1-mini": {"provider": "openai", "input": 0.40 / 1_000_000, "output": 1.60 / 1_000_000, "tier": 1},
    "gpt-5": {"provider": "openai", "input": 1.25 / 1_000_000, "output": 10.00 / 1_000_000, "tier": 2},
    "gpt-5.4": {"provider": "openai", "input": 2.50 / 1_000_000, "output": 15.00 / 1_000_000, "tier": 3},
    "gpt-5.5": {"provider": "openai", "input": 5.00 / 1_000_000, "output": 30.00 / 1_000_000, "tier": 4},

    # Embeddings (similarity-skip layer) — output price is 0: embeddings have no output tokens
    "text-embedding-3-small": {"provider": "openai", "input": 0.02 / 1_000_000, "output": 0.0, "tier": 0},
}

MODEL_ALIASES = {
    "nano": "gpt-4.1-nano",
    "gpt-mini": "gpt-4.1-mini",
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-5",
    "sonnet4.6": "claude-sonnet-4-6",
    "opus": "claude-opus-4-8",
    "opus4.6": "claude-opus-4-6",
    "gpt5": "gpt-5",
    "gpt5.4": "gpt-5.4",
    "gpt5.5": "gpt-5.5",
}

# Daily Task's classic (non-debate) router: nano-classified difficulty maps
# straight to a tier, spanning cheap-OpenAI through mid-Anthropic.
DIFFICULTY_TO_MODEL = {
    "EASY": "gpt-4.1-mini",
    "MEDIUM": "claude-haiku-4-5",
    "HARD": "claude-sonnet-5",
}

# Daily Task's escalation ladder, cheapest -> most expensive, used when a tier
# fails and by the history-override mechanism in scheduler/router.py.
TIER_LADDER = ["gpt-4.1-mini", "claude-haiku-4-5", "claude-sonnet-5", "gpt-5.5"]

# Agent Mode's bake-off pool — separate from Daily Task's TIER_LADDER on
# purpose. Agent Mode spins up a full sandbox per candidate, so its bake-off
# stays to two genuinely strong models rather than spanning Daily Task's
# cheap-to-expensive spread.
AGENT_MODE_TIER_LADDER = ["claude-sonnet-4-6", "claude-opus-4-6"]

# The five execution candidates the Agent-mode deliberation (Planner voice +
# Debate voice + Opus judge, scheduler/deliberation.py) chooses between,
# cheapest first. GPT-5 and GPT-4.1 mini are execution candidates only — they
# never speak in the deliberation itself.
DELIBERATION_MODEL_POOL = [
    "gpt-4.1-mini",
    "gpt-5",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-opus-4-8",
]


def resolve_model(name: str) -> str:
    """Resolve a short alias (e.g. "haiku") to its full model id."""
    if name in MODEL_PRICES:
        return name
    if name in MODEL_ALIASES:
        return MODEL_ALIASES[name]
    raise ValueError(f"Unknown model or alias: {name}")


def get_provider(model: str) -> str:
    model = resolve_model(model)
    return MODEL_PRICES[model]["provider"]


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    model = resolve_model(model)
    prices = MODEL_PRICES[model]
    return input_tokens * prices["input"] + output_tokens * prices["output"]


@dataclass
class CallRecord:
    run_id: str
    step_id: str
    step_class: str
    agent: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    iteration: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
