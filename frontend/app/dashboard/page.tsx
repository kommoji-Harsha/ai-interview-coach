"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getProgressAnalytics, getReviewSchedule } from "@/lib/api";
import {
  ProgressAnalyticsResponse,
  ReviewScheduleResponse,
} from "@/lib/types";
import { TrendChart } from "@/components/TrendChart";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";

export default function ProgressDashboardPage(): React.ReactElement {
  const [days, setDays] = useState<number>(30);
  const [progress, setProgress] = useState<ProgressAnalyticsResponse | null>(
    null
  );
  const [schedule, setSchedule] = useState<ReviewScheduleResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAnalytics = useCallback(async (selectedDays: number) => {
    setLoading(true);
    setError(null);
    try {
      const [progressRes, scheduleRes] = await Promise.all([
        getProgressAnalytics(selectedDays),
        getReviewSchedule(),
      ]);
      setProgress(progressRes);
      setSchedule(scheduleRes);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load progress analytics."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAnalytics(days);
  }, [days, loadAnalytics]);

  if (loading) {
    return (
      <LoadingState message="Loading your progress analytics and review schedule..." />
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Unable to load progress dashboard"
        message={error}
        onRetry={() => loadAnalytics(days)}
      />
    );
  }

  if (!progress || progress.total_sessions === 0) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">
              Progress Dashboard
            </h1>
            <p className="mt-1 text-sm text-slate-600">
              Track your rubric score trends, weak topics, and upcoming reviews.
            </p>
          </div>
        </div>
        <EmptyState
          title="No interview analytics yet"
          description="Complete your first mock interview session to unlock score trends, weak topic identification, and spaced-repetition review schedules."
          actionLabel="Start First Mock Interview"
          onAction={() => {
            window.location.href = "/onboarding";
          }}
        />
      </div>
    );
  }

  const dimensionEntries = Object.entries(progress.dimension_averages || {});
  const upcomingReviews = schedule?.upcoming || [];

  return (
    <div className="space-y-8">
      {/* Header & Time Range Filter */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">
            Progress Dashboard
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Track your score trends, focus on weak topics, and stay on top of
            spaced-repetition reviews.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <label
            htmlFor="analytics-days-select"
            className="text-sm font-medium text-slate-700"
          >
            Timeframe:
          </label>
          <select
            id="analytics-days-select"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value={30}>Last 30 days</option>
            <option value={60}>Last 60 days</option>
            <option value={90}>Last 90 days</option>
            <option value={180}>Last 180 days</option>
          </select>
        </div>
      </div>

      {/* KPI Cards */}
      <section
        aria-label="Key Performance Metrics"
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Total Sessions
          </p>
          <p className="mt-2 text-3xl font-extrabold text-slate-900">
            {progress.total_sessions}
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Sessions ({days}d)
          </p>
          <p className="mt-2 text-3xl font-extrabold text-indigo-600">
            {progress.sessions_this_period}
          </p>
        </div>

        <div className="rounded-2xl border border-emerald-200 bg-emerald-50/50 p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
            Strongest Topic
          </p>
          <p className="mt-2 text-xl font-bold capitalize text-emerald-900">
            {progress.strongest_topic || "N/A"}
          </p>
        </div>

        <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-amber-800">
            Weakest Topic (Focus Area)
          </p>
          <div className="mt-2 flex items-center justify-between gap-2">
            <p
              data-testid="weakest-topic-value"
              className="text-xl font-bold capitalize text-amber-900"
            >
              {progress.weakest_topic || "N/A"}
            </p>
            <Link
              href="/onboarding"
              className="rounded-lg bg-amber-700 px-2.5 py-1 text-xs font-semibold text-white hover:bg-amber-800"
            >
              Practice
            </Link>
          </div>
        </div>
      </section>

      {/* Score Trend & Dimension Averages */}
      <div className="grid gap-6 lg:grid-cols-3">
        <section
          aria-labelledby="score-trend-heading"
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2"
        >
          <h2
            id="score-trend-heading"
            className="text-lg font-bold text-slate-900"
          >
            Overall Score Trend
          </h2>
          <p className="mb-4 text-xs text-slate-500">
            Average session rubric score progression over the selected period.
          </p>
          <TrendChart data={progress.score_trend} />
        </section>

        <section
          aria-labelledby="dimension-averages-heading"
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <h2
            id="dimension-averages-heading"
            className="text-lg font-bold text-slate-900"
          >
            Rubric Dimension Averages
          </h2>
          <p className="mb-4 text-xs text-slate-500">
            Mean score across each rubric dimension (out of 5.0).
          </p>

          {dimensionEntries.length === 0 ? (
            <p className="text-sm text-slate-500">
              No dimension averages recorded yet.
            </p>
          ) : (
            <div className="space-y-4">
              {dimensionEntries.map(([dimension, avg]) => {
                const pct = Math.min(100, Math.max(0, (avg / 5) * 100));
                return (
                  <div key={dimension}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium capitalize text-slate-700">
                        {dimension.replace(/_/g, " ")}
                      </span>
                      <span className="font-bold text-slate-900">
                        {avg.toFixed(1)} / 5.0
                      </span>
                    </div>
                    <div className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                      <div
                        role="progressbar"
                        aria-label={`${dimension} average`}
                        aria-valuenow={avg}
                        aria-valuemin={0}
                        aria-valuemax={5}
                        style={{ width: `${pct}%` }}
                        className="h-full rounded-full bg-indigo-600"
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      {/* Spaced Repetition Review Schedule */}
      <section
        aria-labelledby="review-schedule-heading"
        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <div className="mb-4 flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
          <div>
            <h2
              id="review-schedule-heading"
              className="text-lg font-bold text-slate-900"
            >
              Spaced-Repetition Review Schedule
            </h2>
            <p className="text-xs text-slate-500">
              Recommended follow-up practice sessions based on past weak topic
              scores.
            </p>
          </div>
          <Link
            href="/onboarding"
            className="text-sm font-semibold text-indigo-600 hover:text-indigo-700"
          >
            + Start Targeted Practice
          </Link>
        </div>

        {upcomingReviews.length === 0 ? (
          <EmptyState
            title="No upcoming reviews scheduled"
            description="You are caught up on all spaced-repetition topic reviews!"
          />
        ) : (
          <ul className="divide-y divide-slate-200">
            {upcomingReviews.map((item) => (
              <li
                key={`${item.session_id}-${item.scheduled_at}`}
                className="flex flex-col justify-between gap-3 py-4 sm:flex-row sm:items-center"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold capitalize text-amber-800">
                      {item.topic}
                    </span>
                    <span className="text-xs text-slate-500">
                      Scheduled:{" "}
                      {new Date(item.scheduled_at).toLocaleDateString()}
                    </span>
                  </div>
                  <p className="mt-1 text-sm font-medium text-slate-800">
                    {item.reason}
                  </p>
                </div>

                <Link
                  href="/onboarding"
                  className="inline-flex items-center justify-center rounded-lg border border-indigo-200 bg-indigo-50 px-3.5 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100"
                >
                  Practice {item.topic}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
