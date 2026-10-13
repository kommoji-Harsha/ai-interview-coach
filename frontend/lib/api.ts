import {
  ApiErrorDetail,
  ApiErrorResponse,
  CreateJobDescriptionRequest,
  CreateSessionRequest,
  CreateSessionResponse,
  EndSessionResponse,
  JobDescriptionDetail,
  JobDescriptionMetadata,
  LoginRequest,
  LoginResponse,
  PaginatedResponse,
  ProgressAnalyticsResponse,
  RefreshResponse,
  RegisterRequest,
  RegisterResponse,
  RespondRequest,
  RespondResponse,
  ResumeDetail,
  ResumeMetadata,
  ReviewScheduleResponse,
  SessionDetail,
  SessionFeedbackResponse,
  SessionScoresResponse,
  SessionSummary,
  StreamDoneEvent,
  TranscribeResponse,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

const TOKEN_STORAGE_KEY = "coach_access_token";
const REFRESH_STORAGE_KEY = "coach_refresh_token";
const USER_STORAGE_KEY = "coach_user";

export class ApiClientError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly details?: ApiErrorDetail[];

  constructor(
    message: string,
    status: number,
    code: string = "INTERNAL_ERROR",
    details?: ApiErrorDetail[]
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setAuthTokens(
  accessToken: string,
  refreshToken: string,
  user?: { user_id: string; email?: string; display_name?: string }
): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
  window.localStorage.setItem(REFRESH_STORAGE_KEY, refreshToken);
  if (user) {
    window.localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
  }
}

export function clearAuthTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  window.localStorage.removeItem(REFRESH_STORAGE_KEY);
  window.localStorage.removeItem(USER_STORAGE_KEY);
}

export function getStoredUser(): {
  user_id: string;
  email?: string;
  display_name?: string;
} | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

async function parseErrorResponse(response: Response): Promise<ApiClientError> {
  try {
    const body = (await response.json()) as Partial<ApiErrorResponse>;
    if (body?.error) {
      return new ApiClientError(
        body.error.message || `Request failed with status ${response.status}`,
        response.status,
        body.error.code || "INTERNAL_ERROR",
        body.error.details
      );
    }
  } catch {
    // Fallback if body is not JSON
  }
  return new ApiClientError(
    `Request failed with status ${response.status}`,
    response.status,
    "INTERNAL_ERROR"
  );
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  requiresAuth: boolean = true
): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (
    !headers.has("Content-Type") &&
    !(options.body instanceof FormData) &&
    options.body !== undefined
  ) {
    headers.set("Content-Type", "application/json");
  }

  if (requiresAuth) {
    const token = getAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

// --- Auth ---

export async function registerUser(
  payload: RegisterRequest
): Promise<RegisterResponse> {
  const res = await request<RegisterResponse>(
    "/auth/register",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    false
  );
  setAuthTokens(res.access_token, res.refresh_token, {
    user_id: res.user_id,
    email: res.email,
    display_name: res.display_name,
  });
  return res;
}

export async function loginUser(payload: LoginRequest): Promise<LoginResponse> {
  const res = await request<LoginResponse>(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    false
  );
  setAuthTokens(res.access_token, res.refresh_token, {
    user_id: res.user_id,
    email: payload.email,
  });
  return res;
}

export async function refreshAuthToken(
  refreshToken: string
): Promise<RefreshResponse> {
  const res = await request<RefreshResponse>(
    "/auth/refresh",
    {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    },
    false
  );
  setAuthTokens(res.access_token, res.refresh_token);
  return res;
}

export async function deleteAccount(password: string): Promise<void> {
  await request<void>("/auth/me", {
    method: "DELETE",
    body: JSON.stringify({ password }),
  });
  clearAuthTokens();
}

// --- Resumes ---

export async function uploadResume(
  file: File,
  label?: string
): Promise<ResumeMetadata> {
  const formData = new FormData();
  formData.append("file", file);
  if (label && label.trim().length > 0) {
    formData.append("label", label.trim());
  }
  return request<ResumeMetadata>("/resumes", {
    method: "POST",
    body: formData,
  });
}

export async function listResumes(
  cursor?: string,
  limit: number = 20
): Promise<PaginatedResponse<ResumeMetadata>> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return request<PaginatedResponse<ResumeMetadata>>(
    `/resumes?${params.toString()}`
  );
}

export async function getResume(id: string): Promise<ResumeDetail> {
  return request<ResumeDetail>(`/resumes/${encodeURIComponent(id)}`);
}

export async function deleteResume(id: string): Promise<void> {
  return request<void>(`/resumes/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// --- Job Descriptions ---

export async function createJobDescription(
  payload: CreateJobDescriptionRequest
): Promise<JobDescriptionMetadata> {
  return request<JobDescriptionMetadata>("/job-descriptions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listJobDescriptions(
  cursor?: string,
  limit: number = 20
): Promise<PaginatedResponse<JobDescriptionMetadata>> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return request<PaginatedResponse<JobDescriptionMetadata>>(
    `/job-descriptions?${params.toString()}`
  );
}

export async function getJobDescription(
  id: string
): Promise<JobDescriptionDetail> {
  return request<JobDescriptionDetail>(
    `/job-descriptions/${encodeURIComponent(id)}`
  );
}

export async function deleteJobDescription(id: string): Promise<void> {
  return request<void>(`/job-descriptions/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// --- Sessions ---

export async function createSession(
  payload: CreateSessionRequest
): Promise<CreateSessionResponse> {
  return request<CreateSessionResponse>("/sessions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listSessions(
  cursor?: string,
  limit: number = 20
): Promise<PaginatedResponse<SessionSummary>> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return request<PaginatedResponse<SessionSummary>>(
    `/sessions?${params.toString()}`
  );
}

export async function getSession(id: string): Promise<SessionDetail> {
  return request<SessionDetail>(`/sessions/${encodeURIComponent(id)}`);
}

export async function respondToSession(
  sessionId: string,
  payload: RespondRequest
): Promise<RespondResponse> {
  return request<RespondResponse>(
    `/sessions/${encodeURIComponent(sessionId)}/respond`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );
}

export interface StreamCallbacks {
  onToken: (text: string) => void;
  onDone: (meta: StreamDoneEvent) => void;
}

export async function respondToSessionStream(
  sessionId: string,
  payload: RespondRequest,
  callbacks: StreamCallbacks
): Promise<void> {
  const headers = new Headers({
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  });
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(
    `${BASE_URL}/sessions/${encodeURIComponent(sessionId)}/respond`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    }
  );

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  const contentType = response.headers.get("Content-Type") || "";
  if (contentType.includes("application/json")) {
    // Fallback if server responds with non-streaming JSON
    const json = (await response.json()) as RespondResponse;
    callbacks.onToken(json.content);
    callbacks.onDone({
      turn_number: json.turn_number,
      topic: json.topic,
      difficulty: json.difficulty,
      topics_covered: json.topics_covered,
      turns_remaining: json.turns_remaining,
    });
    return;
  }

  if (!response.body) {
    throw new ApiClientError(
      "Streaming response body is unavailable",
      500,
      "INTERNAL_ERROR"
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      if (!block.trim()) continue;
      let eventType = "message";
      let dataStr = "";

      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith("event:")) {
          eventType = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataStr += line.slice(5).trim();
        }
      }

      if (!dataStr) continue;
      try {
        const parsed = JSON.parse(dataStr);
        if (eventType === "token" && typeof parsed.text === "string") {
          callbacks.onToken(parsed.text);
        } else if (eventType === "done") {
          callbacks.onDone(parsed as StreamDoneEvent);
        }
      } catch {
        // Ignore malformed event frame
      }
    }
  }
}

export async function endSession(
  sessionId: string
): Promise<EndSessionResponse> {
  return request<EndSessionResponse>(
    `/sessions/${encodeURIComponent(sessionId)}/end`,
    {
      method: "POST",
    }
  );
}

export async function getSessionScores(
  sessionId: string
): Promise<SessionScoresResponse> {
  return request<SessionScoresResponse>(
    `/sessions/${encodeURIComponent(sessionId)}/scores`
  );
}

export async function getSessionFeedback(
  sessionId: string
): Promise<SessionFeedbackResponse> {
  return request<SessionFeedbackResponse>(
    `/sessions/${encodeURIComponent(sessionId)}/feedback`
  );
}

// --- Analytics ---

export async function getProgressAnalytics(
  days: number = 30
): Promise<ProgressAnalyticsResponse> {
  return request<ProgressAnalyticsResponse>(
    `/analytics/progress?days=${encodeURIComponent(String(days))}`
  );
}

export async function getReviewSchedule(): Promise<ReviewScheduleResponse> {
  return request<ReviewScheduleResponse>("/analytics/review-schedule");
}

// --- Voice ---

export async function transcribeAudio(file: Blob): Promise<TranscribeResponse> {
  const formData = new FormData();
  formData.append("audio", file, "recording.webm");
  return request<TranscribeResponse>("/voice/transcribe", {
    method: "POST",
    body: formData,
  });
}
