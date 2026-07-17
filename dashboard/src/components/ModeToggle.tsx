export type Mode = "agent" | "daily";

interface ModeToggleProps {
  mode: Mode;
  onChange: (mode: Mode) => void;
}

export function ModeToggle({ mode, onChange }: ModeToggleProps) {
  return (
    <div className="mode-toggle" role="tablist" aria-label="Mode">
      <button
        role="tab"
        aria-selected={mode === "agent"}
        className={`mode-tab${mode === "agent" ? " active" : ""}`}
        onClick={() => onChange("agent")}
      >
        Agent mode
      </button>
      <button
        role="tab"
        aria-selected={mode === "daily"}
        className={`mode-tab${mode === "daily" ? " active" : ""}`}
        onClick={() => onChange("daily")}
      >
        Daily use
      </button>
    </div>
  );
}
