import { API_BASE } from "../api";

// Downloads a run's generated code as a .zip from the backend
// (GET /api/runs/{id}/code.zip).
export function DownloadCodeButton({ runId }: { runId: string }) {
  return (
    <a className="download-code-btn" href={`${API_BASE}/api/runs/${runId}/code.zip`} download>
      ⬇ Download all (.zip)
    </a>
  );
}
