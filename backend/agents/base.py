"""Base agent implementation with gateway integration, Pydantic validation, and retry loop."""

import json
import re
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError

from backend.gateway.client import LLMGateway
from backend.gateway.models import Message

logger = structlog.get_logger()


class AgentValidationError(Exception):
    """Raised when an agent output fails validation after all retries."""

    def __init__(self, message: str, raw_content: str | None = None, errors: Any = None):
        super().__init__(message)
        self.raw_content = raw_content
        self.errors = errors


def extract_json_payload(content: str) -> str:
    """Extract a JSON object string from raw LLM output, handling markdown fences and extraneous text."""
    trimmed = content.strip()

    # Handle ```json ... ``` or ``` ... ```
    if "```" in trimmed:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", trimmed)
        if match:
            return match.group(1).strip()

    # Find first '{' and matching last '}'
    first_brace = trimmed.find("{")
    last_brace = trimmed.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return trimmed[first_brace : last_brace + 1]

    return trimmed


class BaseAgent[InputT: BaseModel, OutputT: BaseModel]:
    """Base class for all AI agents.

    Flow:
    1. Build prompt messages from input.
    2. Call LLM gateway.
    3. Validate output with Pydantic model.
    4. On failure, retry up to max_retries with error feedback.
    5. Fallback if configured or raise AgentValidationError.
    """

    agent_type: str = "base"
    version: str = "v1"

    def __init__(
        self,
        gateway: LLMGateway,
        response_model: type[OutputT],
        max_retries: int = 2,
        temperature: float = 0.7,
        version: str = "v1",
    ):
        self._gateway = gateway
        self.response_model = response_model
        self.max_retries = max_retries
        self.temperature = temperature
        self.version = version

    def build_prompt(self, input_data: InputT) -> list[Message]:
        """Construct the list of messages (System and User) for the LLM."""
        raise NotImplementedError("Subclasses must implement build_prompt")

    def handle_fallback(
        self, input_data: InputT, last_error: Exception, last_raw: str | None
    ) -> OutputT | None:
        """Optional hook for subclasses to return a fallback response when retries are exhausted."""
        return None

    def validate(self, raw_content: str) -> OutputT:
        """Parse and validate JSON against the Pydantic response model."""
        json_str = extract_json_payload(raw_content)
        data = json.loads(json_str)
        return self.response_model.model_validate(data)

    async def run(
        self,
        input_data: InputT,
        session_id: str | None = None,
        model: str | None = None,
    ) -> OutputT:
        """Execute the agent loop with retry-on-invalid-output."""
        messages = self.build_prompt(input_data)
        history = list(messages)
        last_raw: str | None = None
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                result = await self._gateway.complete(
                    messages=history,
                    model=model,
                    temperature=self.temperature,
                    agent_type=self.agent_type,
                    session_id=session_id,
                )
                last_raw = result.content
                parsed = self.validate(result.content)
                return parsed

            except (json.JSONDecodeError, ValidationError, ValueError) as err:
                last_error = err
                logger.warning(
                    "agent_output_validation_failed",
                    agent_type=self.agent_type,
                    attempt=attempt + 1,
                    max_attempts=self.max_retries + 1,
                    error=str(err),
                    raw_content=last_raw[:200] if last_raw else "",
                )

                if attempt < self.max_retries:
                    # Append error context to message history for next retry
                    history.append(Message(role="assistant", content=last_raw or ""))
                    error_feedback = (
                        f"Your previous response was invalid. Error details: {err}.\n"
                        f"Please correct the error and respond ONLY with a valid JSON object matching the required schema."
                    )
                    history.append(Message(role="user", content=error_feedback))

        # Check if fallback handler provides an answer
        if fallback := self.handle_fallback(input_data, last_error, last_raw):
            return fallback

        raise AgentValidationError(
            f"Agent {self.agent_type} failed validation after {self.max_retries + 1} attempts: {last_error}",
            raw_content=last_raw,
            errors=last_error,
        )
