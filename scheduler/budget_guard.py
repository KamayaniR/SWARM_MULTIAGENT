from datetime import datetime, timezone

from scheduler.cost_tracker import CostTracker


class BudgetExceeded(Exception):
    pass


class BudgetGuard:
    def __init__(self, cost_tracker: CostTracker, budget_per_run: float, budget_daily: float):
        self.cost_tracker = cost_tracker
        self.budget_per_run = budget_per_run
        self.budget_daily = budget_daily

    def check(self, run_id: str) -> None:
        """Raise BudgetExceeded if this run or today's total spend is over budget."""
        run_cost = self.cost_tracker.total_cost(run_id)
        if run_cost >= self.budget_per_run:
            raise BudgetExceeded(
                f"run {run_id} spent ${run_cost:.4f}, over per-run budget ${self.budget_per_run:.4f}"
            )

        today = datetime.now(timezone.utc).date().isoformat()
        daily_cost = self.cost_tracker.total_cost_today(today)
        if daily_cost >= self.budget_daily:
            raise BudgetExceeded(
                f"today's spend ${daily_cost:.4f} is over daily budget ${self.budget_daily:.4f}"
            )


if __name__ == "__main__":
    import os
    from pathlib import Path

    from scheduler.models import CallRecord

    tmp_db = Path(__file__).parent.parent / "data" / "budget_test.db"
    if tmp_db.exists():
        os.remove(tmp_db)

    tracker = CostTracker(tmp_db)
    guard = BudgetGuard(tracker, budget_per_run=0.01, budget_daily=10.00)

    guard.check("run-1")  # should not raise, no spend yet
    print("no spend: ok")

    tracker.record(CallRecord(
        run_id="run-1", step_id="s1", step_class="cli_wiring", agent="coder",
        model="claude-sonnet-5", provider="anthropic", input_tokens=2000, output_tokens=1000,
        cost_usd=0.014, latency_ms=1200, iteration=0,
    ))

    try:
        guard.check("run-1")
        raise SystemExit("expected BudgetExceeded, got none")
    except BudgetExceeded as e:
        print(f"correctly raised: {e}")

    os.remove(tmp_db)
    print("ok")
