# ADR-0005: Voice Input Strategy

## Context
The platform needs to support voice inputs for realistic mock interviews. We need a reliable way to transcribe browser-recorded audio into text for the LLM agents to process.

## Decision
We will use the **OpenAI Whisper API** for transcription.
- The browser will record audio using `MediaRecorder` (WebM/WAV).
- Audio is posted to the backend, which proxies it to the Whisper API.

## Consequences
- **Pros:** Exceptionally high accuracy, handles multiple accents well, and avoids complex infrastructure overhead of running Whisper locally in production.
- **Cons:** Incurs per-minute transcription costs.
- **Future:** Can evaluate client-side WASM Whisper to eliminate server costs if accuracy is sufficient.
