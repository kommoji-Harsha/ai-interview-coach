"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { transcribeAudio } from "./api";

// SpeechRecognition type declarations for browser environments
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      length: number;
      [index: number]: {
        transcript: string;
      };
    };
  };
}

interface SpeechRecognitionErrorEventLike {
  error: string;
  message?: string;
}

interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  }
}

export function cleanClientTranscript(text: string): string {
  if (!text) return "";
  // Remove noise brackets, e.g. [silence], [inaudible], (cough), *noise*
  const noisePattern =
    /(?:\[[^\]]*(?:inaudible|noise|silence|cough|applause|laughter|whisper|sigh|unintelligible|snort|music)[^\]]*\]|\([^\)]*(?:inaudible|noise|silence|cough|applause|laughter|whisper|sigh|unintelligible|snort|music)[^\)]*\)|\*(?:inaudible|noise|silence|cough|applause|laughter|whisper|sigh|unintelligible|snort|music)\*)/gi;
  let cleaned = text.replace(noisePattern, "");
  // Normalize whitespace
  cleaned = cleaned.replace(/\s+/g, " ").trim();
  return cleaned;
}

export interface UseVoiceOptions {
  onTranscriptChange: (text: string) => void;
  currentText: string;
}

export interface UseVoiceReturn {
  isRecording: boolean;
  isTranscribing: boolean;
  isSpeaking: boolean;
  activeSpeakingTurn: number | null;
  micError: string | null;
  voiceNotice: string | null;
  autoRead: boolean;
  isWebSpeechSupported: boolean;
  setAutoRead: (enabled: boolean) => void;
  startVoiceInput: () => Promise<void>;
  stopVoiceInput: () => void;
  clearMicError: () => void;
  speakInterviewerResponse: (text: string, turnNumber: number) => void;
  stopSpeaking: () => void;
}

export function useVoice({
  onTranscriptChange,
  currentText,
}: UseVoiceOptions): UseVoiceReturn {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [activeSpeakingTurn, setActiveSpeakingTurn] = useState<number | null>(
    null
  );
  const [micError, setMicError] = useState<string | null>(null);
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const [autoRead, setAutoRead] = useState(false);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const initialTextRef = useRef<string>("");

  const isWebSpeechSupported =
    typeof window !== "undefined" &&
    !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  const clearMicError = useCallback(() => {
    setMicError(null);
  }, []);

  // Stop recording / speech recognition
  const stopVoiceInput = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // Ignore if already stopped
      }
      recognitionRef.current = null;
    }

    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state !== "inactive"
    ) {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // Ignore
      }
    }

    setIsRecording(false);
  }, []);

  // Server-side fallback using MediaRecorder + POST /voice/transcribe
  const startMediaRecorderFallback = useCallback(async () => {
    try {
      if (!navigator?.mediaDevices?.getUserMedia) {
        setMicError(
          "Audio recording is not supported in this browser. Please type your response."
        );
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      audioChunksRef.current = [];

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        // Stop stream tracks
        stream.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
        mediaRecorderRef.current = null;

        const chunks = audioChunksRef.current;
        if (chunks.length === 0) {
          setVoiceNotice("No audio was recorded. Please try again.");
          return;
        }

        const audioBlob = new Blob(chunks, {
          type: recorder.mimeType || "audio/webm",
        });

        setIsTranscribing(true);
        setVoiceNotice("Transcribing audio via server...");
        try {
          const res = await transcribeAudio(audioBlob);
          const cleaned = cleanClientTranscript(res.text);
          if (!cleaned) {
            setVoiceNotice(
              "No clear speech detected. Please review or try speaking again."
            );
          } else {
            const prefix = initialTextRef.current
              ? initialTextRef.current + " "
              : "";
            onTranscriptChange(prefix + cleaned);
            setVoiceNotice(
              "Transcript ready. You can review and edit before sending."
            );
          }
        } catch (err) {
          setMicError(
            err instanceof Error
              ? err.message
              : "Server-side transcription failed. You can continue typing manually."
          );
        } finally {
          setIsTranscribing(false);
        }
      };

      recorder.start(250);
      setIsRecording(true);
      setVoiceNotice("Recording audio (fallback mode)... Click Stop to transcribe.");
    } catch (err: unknown) {
      setIsRecording(false);
      const errorName = (err as { name?: string })?.name;
      if (
        errorName === "NotAllowedError" ||
        errorName === "PermissionDeniedError"
      ) {
        setMicError(
          "Microphone access was denied. You can still type your answer below or allow microphone access in your browser."
        );
      } else {
        setMicError(
          "Could not access microphone. Please ensure a microphone is connected or type your response."
        );
      }
    }
  }, [onTranscriptChange]);

  // Primary Web Speech API flow
  const startVoiceInput = useCallback(async () => {
    setMicError(null);
    setVoiceNotice(null);
    initialTextRef.current = currentText.trim();

    const SpeechRecognitionClass =
      typeof window !== "undefined"
        ? window.SpeechRecognition || window.webkitSpeechRecognition
        : undefined;

    if (!SpeechRecognitionClass) {
      // Fallback to server-side transcription
      await startMediaRecorderFallback();
      return;
    }

    try {
      const recognition = new SpeechRecognitionClass();
      recognitionRef.current = recognition;
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      let finalAccumulated = "";

      recognition.onresult = (event: SpeechRecognitionEventLike) => {
        let interimText = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const transcriptChunk = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalAccumulated += " " + transcriptChunk;
          } else {
            interimText += transcriptChunk;
          }
        }

        const rawCombined = (finalAccumulated + " " + interimText).trim();
        const cleaned = cleanClientTranscript(rawCombined);

        const prefix = initialTextRef.current
          ? initialTextRef.current + " "
          : "";
        onTranscriptChange(prefix + cleaned);
      };

      recognition.onerror = async (event: SpeechRecognitionErrorEventLike) => {
        const err = event.error;
        if (err === "not-allowed" || err === "permission-denied") {
          setMicError(
            "Microphone access was denied. You can still type your answer below or allow microphone access in your browser."
          );
          setIsRecording(false);
        } else if (err === "no-speech") {
          setVoiceNotice("No speech detected. Please speak into your microphone.");
        } else if (
          err === "network" ||
          err === "service-not-allowed" ||
          err === "aborted"
        ) {
          // If browser Web Speech fails on network or service, attempt MediaRecorder fallback
          recognition.abort();
          recognitionRef.current = null;
          await startMediaRecorderFallback();
        } else {
          setMicError(`Voice recognition error: ${err}`);
          setIsRecording(false);
        }
      };

      recognition.onend = () => {
        setIsRecording(false);
        setVoiceNotice(
          "Voice input stopped. Review and edit your transcript before submitting."
        );
      };

      recognition.start();
      setIsRecording(true);
      setVoiceNotice("Listening... Speak your answer clearly.");
    } catch {
      // Fallback if recognition instantiation or start fails
      await startMediaRecorderFallback();
    }
  }, [currentText, onTranscriptChange, startMediaRecorderFallback]);

  // Text-to-Speech (TTS) for interviewer answers
  const stopSpeaking = useCallback(() => {
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
    setActiveSpeakingTurn(null);
  }, []);

  const speakInterviewerResponse = useCallback(
    (text: string, turnNumber: number) => {
      if (typeof window === "undefined" || !window.speechSynthesis) return;

      // If already speaking this turn, toggle stop
      if (isSpeaking && activeSpeakingTurn === turnNumber) {
        stopSpeaking();
        return;
      }

      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "en-US";
      utterance.rate = 1.0;
      utterance.pitch = 1.0;

      utterance.onstart = () => {
        setIsSpeaking(true);
        setActiveSpeakingTurn(turnNumber);
      };

      utterance.onend = () => {
        setIsSpeaking(false);
        setActiveSpeakingTurn(null);
      };

      utterance.onerror = () => {
        setIsSpeaking(false);
        setActiveSpeakingTurn(null);
      };

      window.speechSynthesis.speak(utterance);
    },
    [activeSpeakingTurn, isSpeaking, stopSpeaking]
  );

  // Clean up media streams and speech synthesis on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // Ignore
        }
      }
      if (
        mediaRecorderRef.current &&
        mediaRecorderRef.current.state !== "inactive"
      ) {
        try {
          mediaRecorderRef.current.stop();
        } catch {
          // Ignore
        }
      }
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  return {
    isRecording,
    isTranscribing,
    isSpeaking,
    activeSpeakingTurn,
    micError,
    voiceNotice,
    autoRead,
    isWebSpeechSupported,
    setAutoRead,
    startVoiceInput,
    stopVoiceInput,
    clearMicError,
    speakInterviewerResponse,
    stopSpeaking,
  };
}
