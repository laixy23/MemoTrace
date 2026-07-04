import type {
  AskResponse,
  CardInfo,
  HealthReviewResponse,
  PreferenceCandidate,
  StagingItemInfo,
  SystemLogInfo,
  UploadResponse,
  UserProfile,
  WikiPageInfo
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function healthCheck() {
  return request<{ status: string }>("/health");
}

export async function uploadDocument(file: File) {
  const form = new FormData();
  form.append("file", file);
  return request<UploadResponse>("/api/documents/upload", {
    method: "POST",
    body: form
  });
}

export async function listCards() {
  return request<CardInfo[]>("/api/wiki/cards");
}

export async function getWikiIndex() {
  return request<WikiPageInfo>("/api/wiki/index");
}

export async function getWikiLog() {
  return request<WikiPageInfo>("/api/wiki/log");
}

export async function askQuestion(question: string, topK = 5) {
  return request<AskResponse>("/api/qa/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, top_k: topK })
  });
}

export async function reviewHealth() {
  return request<HealthReviewResponse>("/api/health/review");
}

export async function runWebCompletion(query: string, limit = 3) {
  return request<StagingItemInfo[]>("/api/completion/web", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, limit })
  });
}

export async function listStaging() {
  return request<StagingItemInfo[]>("/api/completion/staging");
}

export async function mergeStaging(stagingId: string) {
  return request<CardInfo>(`/api/completion/staging/${stagingId}/merge`, { method: "POST" });
}

export async function listSystemLogs() {
  return request<SystemLogInfo[]>("/api/logs/system");
}

export async function getProfile() {
  return request<UserProfile>("/api/preferences/profile");
}

export async function saveFeedback(payload: {
  question: string;
  answer_summary: string;
  answer_type: string;
  user_feedback: string;
  user_action: string;
  accepted: boolean;
}) {
  return request<{ status: string }>("/api/preferences/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function distillPreferences() {
  return request<PreferenceCandidate[]>("/api/preferences/distill", { method: "POST" });
}

export async function listCandidates() {
  return request<PreferenceCandidate[]>("/api/preferences/candidates");
}

export async function acceptCandidate(candidateId: string) {
  return request<{ status: string }>(`/api/preferences/candidates/${candidateId}/accept`, { method: "POST" });
}

export async function rejectCandidate(candidateId: string) {
  return request<{ status: string }>(`/api/preferences/candidates/${candidateId}/reject`, { method: "POST" });
}

export async function generateContent(kind: "note" | "report" | "ppt" | "mindmap") {
  return request<{ kind: string; content: string }>(`/api/generate/${kind}`);
}
