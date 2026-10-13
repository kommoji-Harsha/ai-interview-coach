"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  endSession,
  getSession,
  getSessionScores,
  respondToSessionStream,
} from "@/lib/api";
import { SessionDetail, SessionTurn, TurnScoreRecord } from "@/lib/types";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";

export default function InterviewChatPage(): React.ReactElement {
  const params = useParams<{ id: string }>();
  const sessionId = params?.id || "";
  const router = useRouter();

  const [session, setSession] = useState<SessionDetail | null>(null);
  const [turns, setTurns] = useState<SessionTurn[]>([]);
  const [turnScores, setTurnScores] = useState<Record<number, TurnScoreRecord>>(
    {}
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Streaming & input states
  const [answerText, setAnswerText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [turnsRemaining, setTurnsRemaining] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [endingSession, setEndingSession] = useState(false);

  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const loadSessionData = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const detail = await getSession(sessionId);
      setSession(detail);
      setTurns(detail.turns || []);

      try {
        const scoresRes = await getSessionScores(sessionId);
        const scoreMap: Record<number, TurnScoreRecord> = {};
        for (const t of scoresRes.turns) {
          scoreMap[t.turn_number] = t;
        }
        setTurnScores(scoreMap);
      } catch {
        // Scores may not be ready yet
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load interview session."
      );
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadSessionData();
  }, [loadSessionData]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, streamingContent]);

  const handleSendAnswer = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const trimmed = answerText.trim();
    if (!trimmed || isStreaming || !session) return;

    setActionError(null);
    const candidateTurnNumber = turns.length + 1;
    const candidateTurn: SessionTurn = {
      turn_number: candidateTurnNumber,
      role: "candidate",
      content: trimmed,
      created_at: new Date().toISOString(),
    };

    setTurns((prev) => [...prev, candidateTurn]);
    setAnswerText("");
    setIsStreaming(true);
    setStreamingContent("");

    let accumulated = "";
    try {
      await respondToSessionStream(
        sessionId,
        { content: trimmed, audio_url: null },
        {
          onToken: (tokenText) => {
            accumulated += tokenText;
            setStreamingContent(accumulated);
          },
          onDone: (meta) => {
            const interviewerTurn: SessionTurn = {
              turn_number: meta.turn_number,
              role: "interviewer",
              content: accumulated,
              topic: meta.topic,
              difficulty: meta.difficulty,
              created_at: new Date().toISOString(),
            };
            setTurns((prev) => [...prev, interviewerTurn]);
            setStreamingContent("");
            setTurnsRemaining(meta.turns_remaining);
          },
        }
      );

      // Refresh per-turn scores quietly after turn completes
      try {
        const scoresRes = await getSessionScores(sessionId);
        const scoreMap: Record<number, TurnScoreRecord> = {};
        for (const t of scoresRes.turns) {
          scoreMap[t.turn_number] = t;
        }
        setTurnScores(scoreMap);
      } catch {
        // Ignore if async scoring is still running
      }
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : "Failed to submit answer or stream response."
      );
    } finally {
      setIsStreaming(false);
    }
  };

  const handleEndSession = async () => {
    if (!sessionId || endingSession) return;
    setActionError(null);
    setEndingSession(true);
    try {
      await endSession(sessionId);
      router.push(`/sessions/${sessionId}/results`);
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to end session."
      );
      setEndingSession(false);
    }
  };

  if (loading) {
    return <LoadingState message="Loading interview conversation..." />;
  }

  if (error || !session) {
    return (
      <ErrorState
        title="Unable to load interview session"
        message={error || "Session not found"}
        onRetry={loadSessionData}
      />
    );
  }

  const isCompleted = session.status !== "active";

  return (
    <div className="flex flex-col space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-bold text-slate-900">
              Live Mock Interview
            </h1>
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${
                session.status === "active"
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-slate-100 text-slate-700"
              }`}
            >
              {session.status}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Difficulty: <strong className="capitalize">{session.config.difficulty}</strong>{" "}
            • Max Turns: <strong>{session.config.max_turns}</strong>
            {turnsRemaining !== null && (
              <>
                {" "}
                • Remaining: <strong>{turnsRemaining}</strong>
              </>
            )}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {isCompleted ? (
            <Link
              href={`/sessions/${sessionId}/results`}
              className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
            >
              View Session Results
            </Link>
          ) : (
            <button
              type="button"
              onClick={handleEndSession}
              disabled={endingSession || isStreaming}
              className="rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-700 transition hover:bg-red-100 disabled:opacity-50"
            >
              {endingSession ? "Ending Interview..." : "End Session & Score"}
            </button>
          )}
        </div>
      </div>

      {actionError && (
        <ErrorState title="Interview Error" message={actionError} />
      )}

      {/* Conversation Transcript */}
      <section
        aria-label="Interview Transcript"
        aria-live="polite"
        className="flex min-h-[380px] max-h-[560px] flex-col space-y-4 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        {turns.length === 0 && !isStreaming ? (
          <EmptyState
            title="No messages in this session yet"
            description="Your interviewer's first question will appear here once the session begins."
          />
        ) : (
          turns.map((turn) => {
            const isInterviewer = turn.role === "interviewer";
            const scoreRecord = turnScores[turn.turn_number];
            return (
              <div
                key={turn.turn_number}
                className={`flex flex-col ${
                  isInterviewer ? "items-start" : "items-end"
                }`}
              >
                <div
                  className={`max-w-2xl rounded-2xl px-4 py-3 text-sm shadow-sm ${
                    isInterviewer
                      ? "border border-slate-200 bg-slate-50 text-slate-900"
                      : "bg-indigo-600 text-white"
                  }`}
                >
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-xs opacity-80">
                    <span className="font-semibold">
                      {isInterviewer ? "AI Interviewer" : "You"}
                    </span>
                    {turn.topic && (
                      <span className="rounded bg-indigo-100 px-2 py-0.5 text-[11px] font-medium text-indigo-800">
                        {turn.topic}
                      </span>
                    )}
                    {turn.difficulty !== undefined && (
                      <span className="text-[11px]">
                        Level {turn.difficulty}
                      </span>
                    )}
                  </div>
                  <p className="whitespace-pre-wrap leading-relaxed">
                    {turn.content}
                  </p>
                </div>

                {/* Inline per-turn score badges if scored */}
                {scoreRecord && scoreRecord.scores.length > 0 && (
                  <div
                    aria-label={`Turn ${turn.turn_number} rubric scores`}
                    className="mt-1.5 flex flex-wrap gap-1.5"
                  >
                    {scoreRecord.scores.map((s) => (
                      <span
                        key={s.dimension}
                        className="inline-flex items-center rounded-md border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-800"
                      >
                        {s.dimension}: {s.score}/5
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}

        {/* Active SSE Streaming Bubble */}
        {isStreaming && (
          <div
            role="status"
            aria-label="Interviewer is responding"
            className="flex flex-col items-start"
          >
            <div className="max-w-2xl rounded-2xl border border-indigo-200 bg-indigo-50/50 px-4 py-3 text-sm text-slate-900 shadow-sm">
              <div className="mb-1 flex items-center gap-2 text-xs font-semibold text-indigo-700">
                <span>AI Interviewer</span>
                <span className="inline-block h-2 w-2 animate-ping rounded-full bg-indigo-600" />
              </div>
              <p className="whitespace-pre-wrap leading-relaxed">
                {streamingContent || "Thinking..."}
              </p>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </section>

      {/* Answer Input Form */}
      {!isCompleted && (
        <form
          onSubmit={handleSendAnswer}
          className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
        >
          <label htmlFor="candidate-answer-input" className="sr-only">
            Your Interview Answer
          </label>
          <textarea
            id="candidate-answer-input"
            rows={3}
            disabled={isStreaming}
            value={answerText}
            onChange={(e) => setAnswerText(e.target.value)}
            placeholder="Structure your response clearly (e.g., Context, Action, Result)..."
            className="block w-full resize-none rounded-xl border border-slate-300 p-3 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
          />
          <div className="mt-3 flex items-center justify-between">
            <span className="text-xs text-slate-500">
              {isStreaming
                ? "Receiving live streaming response..."
                : "Press Send Answer when ready."}
            </span>
            <button
              type="submit"
              disabled={isStreaming || !answerText.trim()}
              className="rounded-xl bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isStreaming ? "Streaming..." : "Send Answer"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
