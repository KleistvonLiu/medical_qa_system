import type { QARequest, QAResponse, SourceDetail } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function handleJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function submitQuestion(payload: QARequest): Promise<QAResponse> {
  return handleJson<QAResponse>(
    await fetch(`${API_BASE}/api/qa`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function fetchSourceDetail(
  sourceType: string,
  sourceId: string,
): Promise<SourceDetail> {
  return handleJson<SourceDetail>(
    await fetch(`${API_BASE}/api/sources/${sourceType}/${sourceId}`),
  );
}

