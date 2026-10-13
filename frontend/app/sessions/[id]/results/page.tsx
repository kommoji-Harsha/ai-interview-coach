"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getSessionFeedback, getSessionScores } from "@/lib/api";
import { SessionFeedbackResponse, SessionScoresResponse } from "@/lib/types";
import { RadarChart, RadarDimension } from "@/components/RadarChart";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";

export default function SessionResultsPage(): React.ReactElement {
  const params = useParams<{ id: string }>();
  const sessionId = params?.id || "";

  const [scoresData, setScoresData] = useState<SessionScoresResponse | null>(
    null
  );
  const [feedbackData, setFeedbackData] =
    useState<SessionFeedbackResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadResults = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const [scoresRes, feedbackRes] = await Promise.all([
        getSessionScores(sessionId),
        getSessionFeedback(sessionId),
      ]);
      setScoresData(scoresRes);
      setFeedbackData(feedbackRes);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load session results and feedback."
      );
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadResults();
  }, [loadResults]);

  if (loading) {
    return (
      <LoadingState message="Analyzing rubric scores and generating session feedback..." />
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Unable to load session results"
        message={error}
        onRetry={loadResults}
      />
    );
  }

  if (
    !scoresData ||
    (scoresData.turns.length === 0 && !feedbackData?.feedback)
  ) {
    return (
      <EmptyState
        title="No rubric results available yet"
        description="Complete at least one interview turn to view rubric scores, radar chart, and evidence quotes."
        actionLabel="Return to Interview Session"
        onAction={() => {
          window.location.href = `/sessions/${sessionId}`;
        }}
      />
    );
  }

  const radarDimensions: RadarDimension[] = Object.entries(
    scoresData.aggregate || {}
  )
    .filter(([key, val]) => key !== "overall" && typeof val === "number")
    .map(([key, val]) => ({
      label: key,
      score: val as number,
    }));

  const overallScore = scoresData.aggregate?.overall;
  const feedback = feedbackData?.feedback;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">
            Interview Session Results
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Rubric evaluation, dimension radar chart, and direct evidence quotes
            from your responses.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/dashboard"
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Progress Dashboard
          </Link>
          <Link
            href="/onboarding"
            className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
          >
            New Mock Interview
          </Link>
        </div>
      </div>

      {/* Top Grid: Radar Chart + Aggregate Overview */}
      <div className="grid gap-6 lg:grid-cols-2">
        <section
          aria-labelledby="radar-chart-heading"
          className="flex flex-col items-center justify-between rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <div className="w-full text-left">
            <h2
              id="radar-chart-heading"
              className="text-lg font-bold text-slate-900"
            >
              Rubric Dimension Radar
            </h2>
            <p className="text-xs text-slate-500">
              Visual breakdown across scored rubric dimensions (0–5 scale).
            </p>
          </div>
          <div className="my-4">
            {radarDimensions.length > 0 ? (
              <RadarChart dimensions={radarDimensions} />
            ) : (
              <p className="text-sm text-slate-500">
                No aggregate dimension scores available.
              </p>
            )}
          </div>
          {typeof overallScore === "number" && (
            <div className="w-full rounded-xl bg-indigo-50 p-3 text-center">
              <span className="text-xs font-medium uppercase tracking-wider text-indigo-700">
                Overall Session Score
              </span>
              <p className="text-2xl font-extrabold text-indigo-900">
                {overallScore.toFixed(1)} / 5.0
              </p>
            </div>
          )}
        </section>

        {/* Feedback Summary Card */}
        <section
          aria-labelledby="coaching-feedback-heading"
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <div className="flex items-center justify-between">
            <h2
              id="coaching-feedback-heading"
              className="text-lg font-bold text-slate-900"
            >
              Executive Coaching Feedback
            </h2>
            {feedbackData?.status === "generating" && (
              <button
                type="button"
                onClick={loadResults}
                className="rounded-lg bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800 hover:bg-amber-200"
              >
                Generating... Refresh
              </button>
            )}
          </div>

          {!feedback ? (
            <div className="mt-4">
              <EmptyState
                title={
                  feedbackData?.status === "generating"
                    ? "Feedback is still generating"
                    : "Feedback unavailable"
                }
                description="Click Refresh to check if your personalized coaching summary is ready."
                actionLabel="Refresh Feedback"
                onAction={loadResults}
              />
            </div>
          ) : (
            <div className="mt-4 space-y-4 text-sm">
              <p className="rounded-xl bg-slate-50 p-3.5 text-slate-800 leading-relaxed">
                {feedback.summary}
              </p>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <h3 className="font-semibold text-emerald-700">Strengths</h3>
                  <ul className="mt-1.5 list-inside list-disc space-y-1 text-slate-700">
                    {feedback.strengths.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>

                <div>
                  <h3 className="font-semibold text-amber-700">
                    Areas for Improvement
                  </h3>
                  <ul className="mt-1.5 list-inside list-disc space-y-1 text-slate-700">
                    {feedback.improvements.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>

              {feedback.action_items.length > 0 && (
                <div>
                  <h3 className="font-semibold text-indigo-700">
                    Action Items
                  </h3>
                  <ul className="mt-1.5 list-inside list-disc space-y-1 text-slate-700">
                    {feedback.action_items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {feedback.recommended_topics.length > 0 && (
                <div className="pt-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Recommended Topics to Practice:
                  </span>
                  <div className="mt-1.5 flex flex-wrap gap-2">
                    {feedback.recommended_topics.map((topic) => (
                      <span
                        key={topic}
                        className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700"
                      >
                        {topic}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {/* Turn-by-Turn Evidence Quotes & Rubric Scores */}
      <section
        aria-labelledby="evidence-quotes-heading"
        className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <div>
          <h2
            id="evidence-quotes-heading"
            className="text-lg font-bold text-slate-900"
          >
            Turn-by-Turn Rubric Scores & Evidence Quotes
          </h2>
          <p className="text-xs text-slate-500">
            Every rubric score is grounded in specific evidence from your
            submitted answers.
          </p>
        </div>

        <div className="space-y-4">
          {scoresData.turns.map((turn) => (
            <article
              key={turn.turn_number}
              aria-label={`Turn ${turn.turn_number} evaluation`}
              className="rounded-xl border border-slate-200 p-4"
            >
              <div className="mb-3 flex items-center justify-between border-b border-slate-100 pb-2">
                <h3 className="text-sm font-bold text-slate-900">
                  Turn #{turn.turn_number}
                </h3>
                <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium capitalize text-slate-700">
                  Answer Type: {turn.answer_type}
                </span>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                {turn.scores.map((s) => (
                  <div
                    key={s.dimension}
                    className="rounded-lg bg-slate-50 p-3.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold capitalize text-slate-900">
                        {s.dimension.replace(/_/g, " ")}
                      </span>
                      <span className="rounded-md bg-indigo-600 px-2 py-0.5 text-xs font-bold text-white">
                        {s.score} / 5
                      </span>
                    </div>

                    <blockquote className="mt-2 border-l-4 border-indigo-400 pl-3 text-xs italic text-slate-700">
                      &ldquo;{s.evidence}&rdquo;
                    </blockquote>

                    <p className="mt-1.5 text-[11px] text-slate-500">
                      Confidence: {Math.round(s.confidence * 100)}%
                    </p>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
