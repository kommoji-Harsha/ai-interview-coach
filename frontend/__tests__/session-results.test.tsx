import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import SessionResultsPage from "@/app/sessions/[id]/results/page";
import * as api from "@/lib/api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "sess-101" }),
}));

describe("Session Results Page (Radar Chart & Evidence Quotes)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders rubric radar chart, evidence quotes, and executive feedback", async () => {
    vi.spyOn(api, "getSessionScores").mockResolvedValueOnce({
      session_id: "sess-101",
      turns: [
        {
          turn_number: 2,
          answer_type: "attempted",
          scores: [
            {
              dimension: "communication",
              score: 4,
              evidence: "Candidate structured response using STAR method",
              confidence: 0.85,
            },
            {
              dimension: "relevance",
              score: 3,
              evidence: "Answer addressed the question but lacked specifics",
              confidence: 0.78,
            },
          ],
        },
      ],
      aggregate: {
        communication: 4.0,
        relevance: 3.0,
        technical_depth: 3.5,
        overall: 3.5,
      },
    });

    vi.spyOn(api, "getSessionFeedback").mockResolvedValueOnce({
      session_id: "sess-101",
      status: "ready",
      feedback: {
        summary: "Strong communication skills with room for deeper metrics.",
        strengths: ["Clear STAR-method responses"],
        improvements: ["Provide more technical depth in system design answers"],
        action_items: ["Practice system design with a 5-minute timer"],
        recommended_topics: ["system-design", "trade-offs"],
      },
    });

    render(<SessionResultsPage />);

    // Verify Radar Chart is rendered with accessible label
    expect(
      await screen.findByRole("img", { name: /rubric dimension radar chart/i })
    ).toBeInTheDocument();

    // Verify overall score
    expect(screen.getByText("3.5 / 5.0")).toBeInTheDocument();

    // Verify Evidence Quotes
    expect(
      screen.getByText(/candidate structured response using star method/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/answer addressed the question but lacked specifics/i)
    ).toBeInTheDocument();

    // Verify Executive Coaching Feedback
    expect(
      screen.getByText(
        /strong communication skills with room for deeper metrics/i
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(/clear star-method responses/i)
    ).toBeInTheDocument();
  });
});
