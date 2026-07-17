import { useMemo } from "react";
import type { SwarmEvent } from "../types/events";

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
};

interface CostMeterProps {
  events: SwarmEvent[];
}

export function CostMeter({ events }: CostMeterProps) {
  const { total, byProvider } = useMemo(() => {
    const byProvider: Record<string, number> = {};
    let total = 0;
    for (const e of events) {
      const cost = e.cost_usd ?? 0;
      total += cost;
      if (e.provider) byProvider[e.provider] = (byProvider[e.provider] ?? 0) + cost;
    }
    return { total, byProvider };
  }, [events]);

  const providers = Object.entries(byProvider);

  return (
    <div className="cost-area">
      <span className="label">This run</span>
      <span className="value">${total.toFixed(4)}</span>
      {providers.length > 0 && (
        <span className="cost-split">
          {providers.map(([provider, cost]) => (
            <span key={provider} className="cost-split-item">
              {PROVIDER_LABELS[provider] ?? provider} <strong>${cost.toFixed(4)}</strong>
            </span>
          ))}
        </span>
      )}
    </div>
  );
}
