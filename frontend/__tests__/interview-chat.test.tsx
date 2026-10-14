import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import InterviewChatPage from "@/app/sessions/[id]/page";
import * as api from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "sess-101" }),
  useRouter: () => ({
    push: pushMock,
  }),
}));

describe("Interview Chat with Streaming Responses", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders initial question, streams interviewer tokens on answer submit, and ends session", async () => {
    const user = userEvent.setup();

    vi.spyOn(api, "getSession").mockResolvedValueOnce({
      id: "sess-101",
      status: "active",
      resume_id: "res-1",
      jd_id: "jd-1",
      config: { difficulty: "auto", max_turns: 5 },
      turns: [
        {
          turn_number: 1,
          role: "interviewer",
          content: "Tell me about a time you led a project under tight deadlines.",
          topic: "behavioral",
          difficulty: 2,
          created_at: "2026-10-13T10:00:00Z",
        },
      ],
      started_at: "2026-10-13T10:00:00Z",
      ended_at: null,
    });

    vi.spyOn(api, "getSessionScores").mockResolvedValue({
      session_id: "sess-101",
      turns: [],
      aggregate: {
        communication: null,
        relevance: null,
        technical_depth: null,
        overall: null,
      },
    });

    vi.spyOn(api, "respondToSessionStream").mockImplementationOnce(
      async (_sessionId, _payload, callbacks) => {
        callbacks.onToken("Interesting. ");
        callbacks.onToken("How did you handle disagreements?");
        callbacks.onDone({
          turn_number: 3,
          topic: "behavioral",
          difficulty: 3,
          topics_covered: ["behavioral"],
          turns_remaining: 3,
        });
      }
    );

    vi.spyOn(api, "endSession").mockResolvedValueOnce({
      status: "completed",
      ended_at: "2026-10-13T10:15:00Z",
      feedback_status: "generating",
    });

    render(<InterviewChatPage />);

    expect(
      await screen.findByText(
        /tell me about a time you led a project under tight deadlines/i
      )
    ).toBeInTheDocument();

    // Type candidate answer and send
    const answerBox = screen.getByLabelText(/your interview answer/i);
    await user.type(
      answerBox,
      "At Acme Corp, I led a 5-engineer migration project and delivered two days early."
    );
    await user.click(screen.getByRole("button", { name: /send answer/i }));

    // Verify candidate turn and streamed interviewer response appear
    expect(
      await screen.findByText(
        /at acme corp, i led a 5-engineer migration project/i
      )
    ).toBeInTheDocument();
    expect(
      await screen.findByText(
        /interesting\. how did you handle disagreements\?/i
      )
    ).toBeInTheDocument();

    // End session
    const endBtn = screen.getByRole("button", { name: /end session & score/i });
    await user.click(endBtn);

    await waitFor(() => {
      expect(api.endSession).toHaveBeenCalledWith("sess-101");
      expect(pushMock).toHaveBeenCalledWith("/sessions/sess-101/results");
    });
  });
});
