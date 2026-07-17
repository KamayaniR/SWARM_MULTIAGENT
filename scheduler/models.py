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

# Sonnet 4.6 is the base worker for all tasks; Opus 4.6 is the premium model the
# per-prompt bake-off escalates to when a step genuinely needs it.
DIFFICULTY_TO_MODEL = {
    "EASY": "claude-sonnet-4-6",
    "MEDIUM": "claude-sonnet-4-6",
    "HARD": "claude-opus-4-6",
}

# Ordered cheapest → most expensive, used for escalation when a tier fails and
# as the candidate pool the debate/bake-off chooses between per prompt.
TIER_LADDER = ["claude-sonnet-4-6", "claude-opus-4-6"]


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
