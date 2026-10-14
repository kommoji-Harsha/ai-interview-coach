import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import OnboardingPage from "@/app/onboarding/page";
import * as api from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

describe("Onboarding Flow (Role selection, Resume upload, JD paste)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty states when no resumes or JDs exist, and supports role selection, resume upload, JD paste, and session start", async () => {
    const user = userEvent.setup();

    vi.spyOn(api, "listResumes").mockResolvedValueOnce({
      items: [],
      next_cursor: null,
    });
    vi.spyOn(api, "listJobDescriptions").mockResolvedValueOnce({
      items: [],
      next_cursor: null,
    });

    vi.spyOn(api, "uploadResume").mockResolvedValueOnce({
      id: "res-1",
      label: "My SWE Resume",
      filename: "resume.pdf",
      char_count: 3500,
      created_at: "2026-10-13T10:00:00Z",
    });

    vi.spyOn(api, "createJobDescription").mockResolvedValueOnce({
      id: "jd-1",
      company: "Acme Corp",
      role_title: "Frontend Software Engineer",
      char_count: 1800,
      created_at: "2026-10-13T10:01:00Z",
    });

    vi.spyOn(api, "createSession").mockResolvedValueOnce({
      id: "sess-99",
      status: "active",
      resume_id: "res-1",
      jd_id: "jd-1",
      config: {
        difficulty: "auto",
        max_turns: 10,
        focus_topics: ["frontend-architecture", "accessibility", "behavioral"],
      },
      first_question: {
        turn_number: 1,
        content: "Tell me about your frontend experience.",
        topic: "frontend-architecture",
        difficulty: 2,
      },
      started_at: "2026-10-13T10:02:00Z",
    });

    render(<OnboardingPage />);

    // Wait for empty states to appear
    expect(
      await screen.findByText(/no resumes uploaded/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/no job descriptions saved/i)).toBeInTheDocument();

    // 1. Select Frontend role preset
    const frontendRadio = screen.getByRole("radio", {
      name: /frontend software engineer/i,
    });
    await user.click(frontendRadio);
    expect(frontendRadio).toHaveAttribute("aria-checked", "true");

    // 2. Upload resume file
    const file = new File(["dummy pdf content"], "resume.pdf", {
      type: "application/pdf",
    });
    const fileInput = screen.getByLabelText(/resume file/i);
    await user.upload(fileInput, file);
    await user.type(screen.getByLabelText(/resume label/i), "My SWE Resume");
    await user.click(screen.getByRole("button", { name: /upload resume/i }));

    await waitFor(() => {
      expect(api.uploadResume).toHaveBeenCalled();
    });

    // 3. Paste and save Job Description
    const jdTextarea = screen.getByLabelText(/job description text/i);
    await user.type(
      jdTextarea,
      "We need a passionate Frontend Software Engineer experienced in React and TypeScript."
    );
    await user.click(
      screen.getByRole("button", { name: /save job description/i })
    );

    await waitFor(() => {
      expect(api.createJobDescription).toHaveBeenCalledWith({
        company: "Acme Corp",
        role_title: "Frontend Software Engineer",
        raw_text:
          "We need a passionate Frontend Software Engineer experienced in React and TypeScript.",
      });
    });

    // 4. Start Mock Interview
    const startBtn = screen.getByRole("button", {
      name: /start mock interview/i,
    });
    expect(startBtn).not.toBeDisabled();
    await user.click(startBtn);

    await waitFor(() => {
      expect(api.createSession).toHaveBeenCalledWith({
        resume_id: "res-1",
        jd_id: "jd-1",
        config: {
          difficulty: "auto",
          max_turns: 10,
          focus_topics: ["frontend-architecture", "accessibility", "behavioral"],
        },
      });
      expect(pushMock).toHaveBeenCalledWith("/sessions/sess-99");
    });
  });
});
