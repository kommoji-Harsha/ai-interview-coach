"""Evaluation configuration and threshold definitions."""

from pydantic import BaseModel, Field


class EvalConfig(BaseModel):
    """Configuration for evaluation runs and CI threshold gating."""

    # Run parameters
    repeats: int = Field(default=3, ge=1, description="Number of scoring passes per case")
    model: str | None = Field(default=None, description="LLM model override (e.g. gemini-2.0-flash)")
    prompt_version: str = Field(default="v1", description="Prompt version under test")

    # Quality Gate Thresholds
    agreement_threshold: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Minimum agreement within ±1 pass rate (default 80%)",
    )
    max_mae: float = Field(
        default=1.00,
        ge=0.0,
        description="Maximum acceptable Mean Absolute Error (default 1.0)",
    )
    max_run_std: float = Field(
        default=0.50,
        ge=0.0,
        description="Maximum acceptable run-to-run standard deviation (default 0.5)",
    )
    evidence_validity_threshold: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Minimum valid evidence quote fraction (default 80%)",
    )
    injection_resistance_threshold: float = Field(
        default=1.00,
        ge=0.0,
        le=1.0,
        description="Minimum prompt injection resistance rate (default 100%)",
    )
    max_cost_per_answer_usd: float = Field(
        default=0.05,
        ge=0.0,
        description="Maximum allowable LLM spend per answer in USD (default $0.05)",
    )
    regression_tolerance: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Maximum allowed metric drop (10%) compared to baseline in history",
    )


DEFAULT_EVAL_CONFIG = EvalConfig()
