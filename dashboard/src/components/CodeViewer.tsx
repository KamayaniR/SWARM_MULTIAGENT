import { useState } from "react";

interface CodeViewerProps {
  files: Record<string, string>;
}

function download(path: string, content: string) {
  const blob = new Blob([content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = path.split("/").pop() ?? "file.txt";
  a.click();
  URL.revokeObjectURL(url);
}

export function CodeViewer({ files }: CodeViewerProps) {
  const paths = Object.keys(files);
  const [active, setActive] = useState(paths[0] ?? "");
  const activePath = files[active] !== undefined ? active : paths[0] ?? "";

  if (paths.length === 0) {
    return <div className="code-viewer empty">No code produced.</div>;
  }

  const content = files[activePath] ?? "";

  return (
    <div className="code-viewer">
      <div className="code-tabs">
        {paths.map((path) => (
          <button
            key={path}
            className={`code-tab${path === activePath ? " active" : ""}`}
            onClick={() => setActive(path)}
          >
            {path}
          </button>
        ))}
        <div className="code-actions">
          <button className="btn" onClick={() => navigator.clipboard?.writeText(content)}>
            Copy
          </button>
          <button className="btn" onClick={() => download(activePath, content)}>
            Download
          </button>
        </div>
      </div>
      <pre className="code-body">
        <code>{content}</code>
      </pre>
    </div>
  );
}
