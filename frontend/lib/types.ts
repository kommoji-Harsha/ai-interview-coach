export interface ApiErrorDetail {
  field: string;
  reason: string;
}

export interface ApiErrorResponse {
  error: {
    code:
      | "VALIDATION_ERROR"
      | "UNAUTHORIZED"
      | "FORBIDDEN"
      | "NOT_FOUND"
      | "CONFLICT"
      | "UNPROCESSABLE"
      | "RATE_LIMITED"
      | "INTERNAL_ERROR"
      | "LLM_UNAVAILABLE"
      | string;
    message: string;
    details?: ApiErrorDetail[];
  };
}

export interface PaginatedResponse<T> {
  items: T[];
  next_cursor: string | null;
}

// Auth
export interface RegisterRequest {
  email: string;
  password: string;
  display_name: string;
}

export interface RegisterResponse {
  user_id: string;
  email: string;
  display_name: string;
  access_token: string;
  refresh_token: string;
  expires_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  user_id: string;
  access_token: string;
  refresh_token: string;
  expires_at: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface RefreshResponse {
  access_token: string;
  refresh_token: string;
  expires_at: string;
}

// Resumes
export interface ResumeMetadata {
  id: string;
  label?: string | null;
  filename: string;
  char_count: number;
  created_at: string;
}

export interface ResumeDetail extends ResumeMetadata {
  raw_text: string;
}

// Job Descriptions
export interface CreateJobDescriptionRequest {
  company: string;
  role_title: string;
  raw_text: string;
}

export interface JobDescriptionMetadata {
  id: string;
  company: string;
  role_title: string;
  char_count: number;
  created_at: string;
}

export interface JobDescriptionDetail extends JobDescriptionMetadata {
  raw_text?: string;
}

// Sessions
export type SessionDifficulty = "auto" | "easy" | "medium" | "hard";
export type SessionStatus = "active" | "completed" | "abandoned";

export interface SessionConfig {
  difficulty: SessionDifficulty;
  max_turns: number;
  focus_topics?: string[];
}

export interface CreateSessionRequest {
  resume_id: string;
  jd_id: string;
  config: SessionConfig;
}

export interface FirstQuestion {
  turn_number: number;
  content: string;
  topic: string;
  difficulty: number;
}

export interface CreateSessionResponse {
  id: string;
  status: SessionStatus;
  resume_id: string;
  jd_id: string;
  config: SessionConfig;
  first_question: FirstQuestion;
  started_at: string;
}

export interface SessionTurn {
  turn_number: number;
  role: "interviewer" | "candidate";
  content: string;
  topic?: string;
  difficulty?: number;
  created_at: string;
}

export interface SessionDetail {
  id: string;
  status: SessionStatus;
  resume_id: string;
  jd_id: string;
  config: SessionConfig;
  turns: SessionTurn[];
  started_at: string;
  ended_at: string | null;
}

export interface SessionSummary {
  id: string;
  status: SessionStatus;
  overall_score?: number | null;
  started_at: string;
  ended_at?: string | null;
}

export interface RespondRequest {
  content: string;
  audio_url?: string | null;
}

export interface RespondResponse {
  turn_number: number;
  role: "interviewer";
  content: string;
  topic: string;
  difficulty: number;
  topics_covered: string[];
  turns_remaining: number;
}

export interface StreamTokenEvent {
  text: string;
}

export interface StreamDoneEvent {
  turn_number: number;
  topic: string;
  difficulty: number;
  topics_covered: string[];
  turns_remaining: number;
}

export interface EndSessionResponse {
  status: SessionStatus;
  ended_at: string;
  feedback_status: "generating" | "ready" | "failed";
}

// Scores & Feedback
export interface DimensionScore {
  dimension: string;
  score: number;
  evidence: string;
  confidence: number;
}

export interface TurnScoreRecord {
  turn_number: number;
  answer_type: string;
  scores: DimensionScore[];
}

export interface AggregateScores {
  communication: number | null;
  relevance: number | null;
  technical_depth: number | null;
  overall: number | null;
  [key: string]: number | null;
}

export interface SessionScoresResponse {
  session_id: string;
  turns: TurnScoreRecord[];
  aggregate: AggregateScores;
}

export interface SessionFeedbackData {
  summary: string;
  strengths: string[];
  improvements: string[];
  action_items: string[];
  recommended_topics: string[];
}

export interface SessionFeedbackResponse {
  session_id: string;
  status: "ready" | "generating" | "failed";
  feedback: SessionFeedbackData | null;
}

// Analytics
export interface ScoreTrendPoint {
  date: string;
  overall: number;
}

export interface ProgressAnalyticsResponse {
  total_sessions: number;
  sessions_this_period: number;
  score_trend: ScoreTrendPoint[];
  dimension_averages: Record<string, number>;
  strongest_topic: string | null;
  weakest_topic: string | null;
}

export interface UpcomingReviewItem {
  session_id: string;
  scheduled_at: string;
  topic: string;
  reason: string;
}

export interface ReviewScheduleResponse {
  upcoming: UpcomingReviewItem[];
}

// Voice
export interface TranscribeResponse {
  text: string;
  duration_seconds: number;
  language: string;
}
