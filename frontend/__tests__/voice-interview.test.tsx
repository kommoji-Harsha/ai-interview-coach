import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import InterviewChatPage from "@/app/sessions/[id]/page";
import * as api from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "sess-voice-1" }),
  useRouter: () => ({
    push: pushMock,
  }),
}));

describe("Voice Interview Integration (Web Speech STT, Fallback Transcription, Review & TTS)", () => {
  const originalSpeechRecognition = window.SpeechRecognition;
  const originalWebkitSpeechRecognition = window.webkitSpeechRecognition;
  const originalMediaDevices = navigator.mediaDevices;
  const originalSpeechSynthesis = window.speechSynthesis;
  const originalMediaRecorder = window.MediaRecorder;

  beforeEach(() => {
    vi.clearAllMocks();

    vi.spyOn(api, "getSession").mockResolvedValue({
      id: "sess-voice-1",
      status: "active",
      resume_id: "res-1",
      jd_id: "jd-1",
      config: { difficulty: "medium", max_turns: 5 },
      turns: [
        {
          turn_number: 1,
          role: "interviewer",
          content: "Can you describe how you scale microservices under heavy load?",
          topic: "system-design",
          difficulty: 3,
          created_at: "2026-10-14T10:00:00Z",
        },
      ],
      started_at: "2026-10-14T10:00:00Z",
      ended_at: null,
    });

    vi.spyOn(api, "getSessionScores").mockResolvedValue({
      session_id: "sess-voice-1",
      turns: [],
      aggregate: {
        communication: null,
        relevance: null,
        technical_depth: null,
        overall: null,
      },
    });

    // Mock speech synthesis
    window.speechSynthesis = {
      speak: vi.fn(),
      cancel: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
      getVoices: vi.fn().mockReturnValue([]),
      paused: false,
      pending: false,
      speaking: false,
      onvoiceschanged: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    } as unknown as SpeechSynthesis;

    (global as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance = vi.fn().mockImplementation((text: string) => ({
      text,
      lang: "en-US",
      pitch: 1.0,
      rate: 1.0,
      volume: 1.0,
      voice: null,
      onstart: null,
      onend: null,
      onerror: null,
      onpause: null,
      onresume: null,
      onmark: null,
      onboundary: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  afterEach(() => {
    window.SpeechRecognition = originalSpeechRecognition;
    window.webkitSpeechRecognition = originalWebkitSpeechRecognition;
    Object.defineProperty(navigator, "mediaDevices", {
      value: originalMediaDevices,
      writable: true,
      configurable: true,
    });
    window.speechSynthesis = originalSpeechSynthesis;
    window.MediaRecorder = originalMediaRecorder;
  });

  it("handles Web Speech API speech-to-text, lets candidate review and edit transcript before sending", async () => {
    const user = userEvent.setup();

    interface RecognitionMock {
      continuous: boolean;
      interimResults: boolean;
      lang: string;
      onresult: ((event: unknown) => void) | null;
      onerror: ((event: unknown) => void) | null;
      onend: (() => void) | null;
      start: ReturnType<typeof vi.fn>;
      stop: ReturnType<typeof vi.fn>;
      abort: ReturnType<typeof vi.fn>;
    }

    let recognitionInstance: RecognitionMock | null = null;

    const MockRecognition = vi.fn().mockImplementation(function () {
      recognitionInstance = {
        continuous: false,
        interimResults: false,
        lang: "",
        onresult: null,
        onerror: null,
        onend: null,
        start: vi.fn(),
        stop: vi.fn().mockImplementation(() => {
          if (recognitionInstance?.onend) {
            recognitionInstance.onend();
          }
        }),
        abort: vi.fn(),
      };
      return recognitionInstance;
    });

    window.SpeechRecognition = MockRecognition as unknown as typeof window.SpeechRecognition;

    vi.spyOn(api, "respondToSessionStream").mockImplementationOnce(
      async (_sessionId, payload, callbacks) => {
        expect(payload.content).toBe(
          "I scale microservices using Redis caching and auto-scaling groups."
        );
        callbacks.onToken("Excellent approach.");
        callbacks.onDone({
          turn_number: 3,
          topic: "system-design",
          difficulty: 3,
          topics_covered: ["system-design"],
          turns_remaining: 3,
        });
      }
    );

    render(<InterviewChatPage />);

    expect(
      await screen.findByText(/can you describe how you scale microservices/i)
    ).toBeInTheDocument();

    const recordBtn = screen.getByRole("button", { name: /record answer/i });
    await user.click(recordBtn);

    expect(MockRecognition).toHaveBeenCalled();
    expect((recognitionInstance as RecognitionMock | null)?.start).toHaveBeenCalled();


    // Simulate speech recognition returning recognized text with noise
    act(() => {
      recognitionInstance?.onresult?.({
        resultIndex: 0,
        results: [
          [
            {
              transcript: "I scale microservices [inaudible] using Redis caching",
            },
          ],
        ],
      });
    });

    // Check that transcribed text appeared in the textarea and noise marker was cleaned
    const textarea = screen.getByLabelText(/your interview answer/i) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(textarea.value).toContain("I scale microservices using Redis caching");
    });

    // Review & edit: user adds more context before submitting
    await user.type(textarea, " and auto-scaling groups.");

    expect(textarea.value).toBe(
      "I scale microservices using Redis caching and auto-scaling groups."
    );

    // Stop recording and send answer
    const stopBtn = screen.getByRole("button", { name: /stop voice recording/i });
    await user.click(stopBtn);

    const sendBtn = screen.getByRole("button", { name: /send answer/i });
    await user.click(sendBtn);

    await waitFor(() => {
      expect(api.respondToSessionStream).toHaveBeenCalled();
      expect(screen.getByText(/excellent approach\./i)).toBeInTheDocument();
    });
  });

  it("falls back to server-side transcription when Web Speech API is unavailable", async () => {
    const user = userEvent.setup();

    // Ensure Web Speech API is unavailable
    delete (window as { SpeechRecognition?: unknown }).SpeechRecognition;
    delete (window as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition;

    // Mock mediaDevices & MediaRecorder
    let recorderInstance: {
      ondataavailable: ((event: { data: Blob }) => void) | null;
      onstop: (() => void) | null;
      start: ReturnType<typeof vi.fn>;
      stop: ReturnType<typeof vi.fn>;
      state: string;
      mimeType: string;
    } | null = null;

    const stopMock = vi.fn().mockImplementation(() => {
      if (recorderInstance) {
        recorderInstance.state = "inactive";
        if (recorderInstance.ondataavailable) {
          recorderInstance.ondataavailable({
            data: new Blob(["dummy audio data"], { type: "audio/webm" }),
          });
        }
        if (recorderInstance.onstop) {
          recorderInstance.onstop();
        }
      }
    });

    const MockMediaRecorder = Object.assign(
      vi.fn().mockImplementation(function () {
        recorderInstance = {
          ondataavailable: null,
          onstop: null,
          start: vi.fn().mockImplementation(() => {
            if (recorderInstance) recorderInstance.state = "recording";
          }),
          stop: stopMock,
          state: "inactive",
          mimeType: "audio/webm",
        };
        return recorderInstance;
      }),
      {
        isTypeSupported: vi.fn().mockReturnValue(true),
      }
    );

    window.MediaRecorder = MockMediaRecorder as unknown as typeof MediaRecorder;


    const mockTrack = { stop: vi.fn() };
    const mockStream = {
      getTracks: vi.fn().mockReturnValue([mockTrack]),
    };

    Object.defineProperty(navigator, "mediaDevices", {
      value: {
        getUserMedia: vi.fn().mockResolvedValue(mockStream),
      },
      writable: true,
      configurable: true,
    });

    const transcribeSpy = vi.spyOn(api, "transcribeAudio").mockResolvedValueOnce({
      text: "We use horizontal pod autoscalers in Kubernetes [cough].",
      duration_seconds: 6.2,
      language: "en",
    });

    render(<InterviewChatPage />);

    expect(
      await screen.findByText(/can you describe how you scale microservices/i)
    ).toBeInTheDocument();

    const recordBtn = screen.getByRole("button", { name: /record answer/i });
    await user.click(recordBtn);

    await waitFor(() => {
      expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ audio: true });
      expect(MockMediaRecorder).toHaveBeenCalled();
      expect(recorderInstance?.start).toHaveBeenCalled();
    });

    // Click stop to trigger server transcription
    const stopBtn = screen.getByRole("button", { name: /stop voice recording/i });
    await user.click(stopBtn);

    await waitFor(() => {
      expect(transcribeSpy).toHaveBeenCalled();
    });

    // Check that textarea received cleaned server transcript
    const textarea = screen.getByLabelText(/your interview answer/i) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(textarea.value).toBe("We use horizontal pod autoscalers in Kubernetes .");
    });
  });

  it("handles microphone permission denial gracefully without blocking manual typing", async () => {
    const user = userEvent.setup();

    delete (window as { SpeechRecognition?: unknown }).SpeechRecognition;
    delete (window as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition;

    const permError = new Error("Permission denied");
    permError.name = "NotAllowedError";

    Object.defineProperty(navigator, "mediaDevices", {
      value: {
        getUserMedia: vi.fn().mockRejectedValue(permError),
      },
      writable: true,
      configurable: true,
    });

    render(<InterviewChatPage />);

    expect(
      await screen.findByText(/can you describe how you scale microservices/i)
    ).toBeInTheDocument();

    const recordBtn = screen.getByRole("button", { name: /record answer/i });
    await user.click(recordBtn);

    // Verify accessible permission warning message is displayed
    expect(
      await screen.findByRole("alert")
    ).toHaveTextContent(/microphone access was denied/i);

    // Ensure candidate can still type manually in textarea
    const textarea = screen.getByLabelText(/your interview answer/i);
    await user.type(textarea, "Typing manual answer works smoothly.");
    expect(textarea).toHaveValue("Typing manual answer works smoothly.");

    // Dismiss notice
    const dismissBtn = screen.getByRole("button", { name: /dismiss microphone notice/i });
    await user.click(dismissBtn);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("plays text-to-speech for interviewer responses and toggles auto-read", async () => {
    const user = userEvent.setup();

    render(<InterviewChatPage />);

    expect(
      await screen.findByText(/can you describe how you scale microservices/i)
    ).toBeInTheDocument();

    // Click listen button for turn 1
    const listenBtn = screen.getByRole("button", { name: /listen to turn 1/i });
    await user.click(listenBtn);

    expect(window.speechSynthesis.speak).toHaveBeenCalled();

    // Enable auto-read toggle
    const autoReadCheckbox = screen.getByLabelText(/auto-read responses/i);
    expect(autoReadCheckbox).not.toBeChecked();
    await user.click(autoReadCheckbox);
    expect(autoReadCheckbox).toBeChecked();
  });
});
