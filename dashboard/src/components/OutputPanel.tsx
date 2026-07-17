import { useState } from "react";
import type { CompletedFiles } from "../types";
import { DownloadCodeButton } from "./DownloadCodeButton";

interface Props {
  completedFiles: CompletedFiles;
  runId: string | null;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="copy-btn"
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? "copied!" : "copy"}
    </button>
  );
}

export function OutputPanel({ completedFiles, runId }: Props) {
  const stepIds = Object.keys(completedFiles);

  if (stepIds.length === 0) {
    return (
      <div className="panel output-panel">
        <h2>Output</h2>
        <p className="empty-note">No completed code yet -- appears here once a step passes.</p>
      </div>
    );
  }

  return (
    <div className="panel output-panel">
      <div className="output-panel-header">
        <h2>Output -- generated code</h2>
        {runId && <DownloadCodeButton runId={runId} />}
      </div>
      {stepIds.map((stepId) => (
        <div key={stepId} className="output-step">
          <div className="output-step-header">{stepId}</div>
          {Object.entries(completedFiles[stepId]).map(([path, content]) => (
            <div key={path} className="output-file">
              <div className="output-file-header">
                <span className="output-file-path">{path}</span>
                <CopyButton text={content} />
              </div>
              <pre className="output-file-code">{content}</pre>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
