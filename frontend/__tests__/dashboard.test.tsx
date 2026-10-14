import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ProgressDashboardPage from "@/app/dashboard/page";
import * as api from "@/lib/api";

describe("Progress Dashboard Page (Score Trends & Weak Topics)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders score trends chart, strongest/weakest topics, dimension averages, and review schedule", async () => {
    vi.spyOn(api, "getProgressAnalytics").mockResolvedValueOnce({
      total_sessions: 12,
      sessions_this_period: 5,
      score_trend: [
        { date: "2026-10-01", overall: 3.2 },
        { date: "2026-10-08", overall: 3.5 },
        { date: "2026-10-13", overall: 3.9 },
      ],
      dimension_averages: {
        communication: 4.1,
        relevance: 3.7,
        technical_depth: 3.2,
      },
      strongest_topic: "behavioral",
      weakest_topic: "system-design",
    });

    vi.spyOn(api, "getReviewSchedule").mockResolvedValueOnce({
      upcoming: [
        {
          session_id: "sess-12",
          scheduled_at: "2026-10-18T09:00:00Z",
          topic: "system-design",
          reason: "Scored 2.5 — review recommended",
        },
      ],
    });

    render(<ProgressDashboardPage />);

    // Verify KPI metrics & weakest topic
    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(screen.getByTestId("weakest-topic-value")).toHaveTextContent(
      "system-design"
    );

    // Verify Score Trend SVG chart
    expect(
      screen.getByRole("img", { name: /overall score trend over time/i })
    ).toBeInTheDocument();

    // Verify Spaced-Repetition Review Schedule
    expect(
      screen.getByText(/scored 2\.5 — review recommended/i)
    ).toBeInTheDocument();
  });

  it("renders empty state when user has 0 completed sessions", async () => {
    vi.spyOn(api, "getProgressAnalytics").mockResolvedValueOnce({
      total_sessions: 0,
      sessions_this_period: 0,
      score_trend: [],
      dimension_averages: {},
      strongest_topic: null,
      weakest_topic: null,
    });

    vi.spyOn(api, "getReviewSchedule").mockResolvedValueOnce({
      upcoming: [],
    });

    render(<ProgressDashboardPage />);

    expect(
      await screen.findByText(/no interview analytics yet/i)
    ).toBeInTheDocument();
  });
});
