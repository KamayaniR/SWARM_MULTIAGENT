interface Props {
  runIds: string[];
  selected: string | null; // null = collective
  onChange: (runId: string | null) => void;
}

export function RunSelector({ runIds, selected, onChange }: Props) {
  return (
    <div className="run-selector">
      <label htmlFor="run-select">Scope</label>
      <select
        id="run-select"
        value={selected ?? "__collective__"}
        onChange={(e) => onChange(e.target.value === "__collective__" ? null : e.target.value)}
      >
        <option value="__collective__">Collective (all prompts)</option>
        {runIds.map((id) => (
          <option key={id} value={id}>
            {id.slice(0, 8)}
          </option>
        ))}
      </select>
    </div>
  );
}
