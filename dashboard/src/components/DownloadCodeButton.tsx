const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

// Downloads a run's generated code as a .zip from the backend
// (GET /api/runs/{id}/code.zip). Shared by the agent and task views.
export function DownloadCodeButton({ runId }: { runId: string }) {
  return (
    <div className="download-bar">
      <a className="btn" href={`${API}/api/runs/${runId}/code.zip`} download>
        ⬇ Download all code (.zip)
      </a>
    </div>
  );
}
