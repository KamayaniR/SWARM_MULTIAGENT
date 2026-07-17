import type { ModelInfo } from "./types";

// Display metadata for the three real tiers this system routes across
// (config.py's ESCALATION_LADDER) -- purely cosmetic, never used for any
// routing or cost logic, which all comes from the server.
const KNOWN_MODELS: Record<string, ModelInfo> = {
  "claude-sonnet-5": { label: "Sonnet", emoji: "⚖️", color: "#6366f1" },
  "claude-sonnet-4-6": { label: "Sonnet 4.6", emoji: "⚖️", color: "#818cf8" },
  "claude-opus-4-8": { label: "Opus 4.8", emoji: "🧠", color: "#f59e0b" },
  "claude-opus-4-6": { label: "Opus 4.6", emoji: "🧠", color: "#fb923c" },
};

const FALLBACK_COLORS = ["#ec4899", "#14b8a6", "#8b5cf6", "#f97316"];

export function modelInfo(model: string): ModelInfo {
  if (KNOWN_MODELS[model]) return KNOWN_MODELS[model];
  // Any model this dashboard hasn't seen before (a new tier added to
  // config.py) still gets a stable-looking card instead of breaking.
  let hash = 0;
  for (let i = 0; i < model.length; i++) hash = (hash * 31 + model.charCodeAt(i)) | 0;
  const color = FALLBACK_COLORS[Math.abs(hash) % FALLBACK_COLORS.length];
  return { label: model, emoji: "🤖", color };
}
