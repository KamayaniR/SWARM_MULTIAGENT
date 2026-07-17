import { useState } from "react";
import { AgentModeView } from "./components/AgentModeView";
import { DailyUseView } from "./components/DailyUseView";
import { ModeToggle, type Mode } from "./components/ModeToggle";

const MODE_KEY = "swarm.mode";

function App() {
  const [mode, setMode] = useState<Mode>(
    () => (localStorage.getItem(MODE_KEY) as Mode | null) ?? "agent",
  );

  function changeMode(next: Mode) {
    setMode(next);
    localStorage.setItem(MODE_KEY, next);
  }

  return (
    <>
      <header className="app-header">
        <h1>Swarm Control</h1>
        <ModeToggle mode={mode} onChange={changeMode} />
      </header>

      {mode === "agent" ? <AgentModeView /> : <DailyUseView />}
    </>
  );
}

export default App;
