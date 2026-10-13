"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { listSessions } from "@/lib/api";
import { SessionSummary } from "@/lib/types";
import { EmptyState, ErrorState, LoadingState } from "@/components/StateViews";

export default function HomePage(): React.ReactElement {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [recentSessions, setRecentSessions] = useState<SessionSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRecent = async () => {
    setLoadingSessions(true);
    setError(null);
    try {
      const res = await listSessions(undefined, 5);
      setRecentSessions(res.items);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load recent sessions"
      );
    } finally {
      setLoadingSessions(false);
    }
  };

  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      fetchRecent();
    }
  }, [authLoading, isAuthenticated]);

  if (authLoading) {
    return <LoadingState message="Checking authentication..." />;
  }

  return (
    <div className="space-y-8">
      <section
        aria-labelledby="hero-heading"
        className="rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-700 p-8 text-white shadow-md sm:p-12"
      >
        <h1
          id="hero-heading"
          className="text-3xl font-extrabold tracking-tight sm:text-4xl"
        >
          Master Your Next Technical & Behavioral Interview
        </h1>
        <p className="mt-3 max-w-2xl text-base text-indigo-100 sm:text-lg">
          Practice adaptive mock interviews tailored to your resume and target
          job description. Receive rubric-scored feedback backed by direct
          evidence quotes and track your progress over time.
        </p>
        <div className="mt-6 flex flex-wrap gap-4">
          {isAuthenticated ? (
            <>
              <Link
                href="/onboarding"
                className="rounded-xl bg-white px-5 py-2.5 text-sm font-semibold text-indigo-700 shadow-sm transition hover:bg-indigo-50"
              >
                Start Mock Interview
              </Link>
              <Link
                href="/dashboard"
                className="rounded-xl border border-indigo-300 bg-indigo-700/40 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700/60"
              >
                View Progress Dashboard
              </Link>
            </>
          ) : (
            <>
              <Link
                href="/auth/register"
                className="rounded-xl bg-white px-5 py-2.5 text-sm font-semibold text-indigo-700 shadow-sm transition hover:bg-indigo-50"
              >
                Get Started Free
              </Link>
              <Link
                href="/auth/login"
                className="rounded-xl border border-indigo-300 bg-indigo-700/40 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700/60"
              >
                Sign In
              </Link>
            </>
          )}
        </div>
      </section>

      {isAuthenticated && (
        <section aria-labelledby="recent-sessions-heading" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2
              id="recent-sessions-heading"
              className="text-xl font-bold text-slate-900"
            >
              Recent Interview Sessions
            </h2>
            <Link
              href="/onboarding"
              className="text-sm font-semibold text-indigo-600 hover:text-indigo-700"
            >
              + New Session
            </Link>
          </div>

          {loadingSessions ? (
            <LoadingState message="Loading your recent interview sessions..." />
          ) : error ? (
            <ErrorState
              title="Unable to load sessions"
              message={error}
              onRetry={fetchRecent}
            />
          ) : recentSessions.length === 0 ? (
            <EmptyState
              title="No interview sessions yet"
              description="Upload your resume and paste a job description to begin your first tailored mock interview."
              actionLabel="Set Up First Interview"
              onAction={() => {
                window.location.href = "/onboarding";
              }}
            />
          ) : (
            <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white shadow-sm">
              {recentSessions.map((s) => (
                <li
                  key={s.id}
                  className="flex flex-col justify-between gap-3 p-4 sm:flex-row sm:items-center"
                >
                  <div>
                    <p className="text-sm font-semibold text-slate-900">
                      Session {s.id.slice(0, 8)}
                    </p>
                    <p className="text-xs text-slate-500">
                      Started: {new Date(s.started_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${
                        s.status === "completed"
                          ? "bg-emerald-50 text-emerald-700"
                          : s.status === "active"
                          ? "bg-amber-50 text-amber-700"
                          : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {s.status}
                    </span>
                    <Link
                      href={
                        s.status === "completed"
                          ? `/sessions/${s.id}/results`
                          : `/sessions/${s.id}`
                      }
                      className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-indigo-600 hover:bg-indigo-50"
                    >
                      {s.status === "completed" ? "View Results" : "Resume Chat"}
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
