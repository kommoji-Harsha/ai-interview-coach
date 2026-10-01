# ADR-0004: Primary LLM Provider

## Context
The system relies heavily on LLMs for generating questions, scoring answers, and providing feedback. We need to select a primary provider for development and production that balances cost, speed, and quality.

## Decision
We will use **Google Gemini (Flash-class models, e.g., gemini-2.0-flash)** as the primary provider for development and normal operations. 
- A stronger model (e.g., Gemini Pro) will be reserved for rigorous Eval runs or complex fallbacks.
- The LLM Gateway will abstract the provider, allowing seamless fallback to an **optional local OpenAI-compatible endpoint** (e.g., Ollama/vLLM) for offline dev.

## Consequences
- **Pros:** Gemini Flash provides an exceptional cost-to-quality ratio, keeping dev loops cheap and latency low. The gateway prevents vendor lock-in.
- **Cons:** Need to maintain provider abstraction layers for both the Gemini SDK and the OpenAI compatibility SDK.
