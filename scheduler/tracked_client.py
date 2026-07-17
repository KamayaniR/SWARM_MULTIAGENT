import os
import time

import anthropic
import openai
from dotenv import load_dotenv

load_dotenv()

from scheduler.budget_guard import BudgetGuard
from scheduler.cost_tracker import CostTracker
from scheduler.latency_tracker import LatencyTracker
from scheduler.models import CallRecord, compute_cost, get_provider, resolve_model
from scheduler.trace_logger import TraceLogger


class TrackedLLMClient:
    """Wraps Anthropic + OpenAI behind one interface. Every call() is
    automatically recorded to CostTracker, LatencyTracker, and TraceLogger,
    and checked against BudgetGuard.

    A BudgetGuard is always active by default (reading BUDGET_PER_RUN /
    BUDGET_DAILY from the environment) rather than only when a caller
    remembers to pass one — pass budget_guard explicitly to override
    (e.g. in tests) or to disable enforcement by setting very high limits."""

    def __init__(self, budget_guard: BudgetGuard | None = None):
        self.anthropic_client = anthropic.Anthropic()
        self.openai_client = openai.OpenAI()
        self.cost_tracker = CostTracker()
        self.latency_tracker = LatencyTracker()
        self.trace_logger = TraceLogger()
        if budget_guard is None:
            budget_per_run = float(os.environ.get("BUDGET_PER_RUN", "0.50"))
            budget_daily = float(os.environ.get("BUDGET_DAILY", "10.00"))
            budget_guard = BudgetGuard(self.cost_tracker, budget_per_run, budget_daily)
        self.budget_guard = budget_guard

    def _call_anthropic(self, model: str, system: str, messages: list[dict], tool: dict, max_tokens: int):
        response = self.anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=messages,
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        return tool_use.input, response.usage.input_tokens, response.usage.output_tokens

    def _call_openai(self, model: str, system: str, messages: list[dict], tool: dict, max_tokens: int):
        import json

        oa_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool["input_schema"],
            },
        }
        response = self.openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}] + messages,
            tools=[oa_tool],
            tool_choice={"type": "function", "function": {"name": tool["name"]}},
            max_tokens=max_tokens,
        )
        message = response.choices[0].message
        call = message.tool_calls[0]
        result = json.loads(call.function.arguments)
        return result, response.usage.prompt_tokens, response.usage.completion_tokens

    def call(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        tool: dict,
        run_id: str,
        agent: str,
        step_id: str = "",
        step_class: str = "",
        iteration: int = 0,
        max_tokens: int = 4096,
    ) -> tuple[dict, dict]:
        resolved = resolve_model(model)
        provider = get_provider(resolved)

        start = time.monotonic()
        if provider == "anthropic":
            result, input_tokens, output_tokens = self._call_anthropic(
                resolved, system, messages, tool, max_tokens
            )
        elif provider == "openai":
            result, input_tokens, output_tokens = self._call_openai(
                resolved, system, messages, tool, max_tokens
            )
        else:
            raise ValueError(f"unknown provider for model {resolved}: {provider}")
        latency_ms = (time.monotonic() - start) * 1000

        cost_usd = compute_cost(resolved, input_tokens, output_tokens)

        self.cost_tracker.record(CallRecord(
            run_id=run_id, step_id=step_id, step_class=step_class, agent=agent,
            model=resolved, provider=provider, input_tokens=input_tokens,
            output_tokens=output_tokens, cost_usd=cost_usd, latency_ms=latency_ms,
            iteration=iteration,
        ))
        self.latency_tracker.record(run_id, agent, resolved, latency_ms)
        self.trace_logger.log(run_id, {
            "agent": agent, "step_id": step_id, "step_class": step_class,
            "model": resolved, "provider": provider, "iteration": iteration,
            "system": system, "messages": messages, "response": result,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost_usd": cost_usd, "latency_ms": latency_ms,
        })

        if self.budget_guard:
            self.budget_guard.check(run_id)

        metrics = {
            "model": resolved, "provider": provider,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost_usd": cost_usd, "latency_ms": latency_ms,
        }
        return result, metrics

    def embed(
        self,
        *,
        text: str,
        run_id: str,
        agent: str = "router",
        step_id: str = "",
        step_class: str = "",
        model: str = "text-embedding-3-small",
    ) -> list[float]:
        """Embed one text and return its vector. Recorded to the cost tracker
        like any other call (embeddings are cheap but not free), but not to the
        trace log — a 1536-float vector isn't useful trace content."""
        resolved = resolve_model(model)
        provider = get_provider(resolved)

        start = time.monotonic()
        response = self.openai_client.embeddings.create(model=resolved, input=text)
        latency_ms = (time.monotonic() - start) * 1000

        input_tokens = response.usage.prompt_tokens
        cost_usd = compute_cost(resolved, input_tokens, 0)
        self.cost_tracker.record(CallRecord(
            run_id=run_id, step_id=step_id, step_class=step_class, agent=agent,
            model=resolved, provider=provider, input_tokens=input_tokens,
            output_tokens=0, cost_usd=cost_usd, latency_ms=latency_ms,
            iteration=0,
        ))
        self.latency_tracker.record(run_id, agent, resolved, latency_ms)
        return response.data[0].embedding


if __name__ == "__main__":
    # Exercises the recording pipeline without hitting a real API —
    # stubs both provider call methods so cost/latency/trace wiring can be
    # verified without spending money or needing live keys.
    import os
    from pathlib import Path
    from unittest.mock import patch

    tmp_db = Path(__file__).parent.parent / "data" / "tracked_client_test.db"
    if tmp_db.exists():
        os.remove(tmp_db)

    with patch.object(anthropic, "Anthropic"), patch.object(openai, "OpenAI"):
        client = TrackedLLMClient()
    client.cost_tracker = CostTracker(tmp_db)
    # Rebind the guard to the swapped tracker — otherwise it'd still check
    # against the real data/costs.db, which may already have unrelated
    # historical spend recorded under this same test run_id.
    client.budget_guard = BudgetGuard(client.cost_tracker, budget_per_run=999, budget_daily=999)

    fake_tool = {"name": "submit_x", "description": "test", "input_schema": {"type": "object", "properties": {}}}

    with patch.object(client, "_call_anthropic", return_value=({"ok": True}, 1000, 500)):
        result, metrics = client.call(
            model="sonnet", system="sys", messages=[{"role": "user", "content": "hi"}],
            tool=fake_tool, run_id="test-run", agent="planner",
        )
    print(result, metrics)
    assert result == {"ok": True}
    assert metrics["provider"] == "anthropic"
    assert abs(metrics["cost_usd"] - (1000 * 2.00 / 1_000_000 + 500 * 10.00 / 1_000_000)) < 1e-9

    total = client.cost_tracker.total_cost("test-run")
    assert abs(total - metrics["cost_usd"]) < 1e-9
    print(f"recorded cost: {total}")

    trace = client.trace_logger.read("test-run")
    assert len(trace) == 1 and trace[0]["agent"] == "planner"
    print(f"recorded trace entries: {len(trace)}")

    latency_summary = client.latency_tracker.summary("test-run")
    assert "planner" in latency_summary
    print(f"recorded latency: {latency_summary}")

    os.remove(tmp_db)
    trace_path = client.trace_logger._path("test-run")
    if trace_path.exists():
        os.remove(trace_path)
    print("ok")
