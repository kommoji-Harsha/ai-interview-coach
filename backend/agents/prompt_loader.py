"""Prompt loader and template rendering for AI Interview Coach agents."""

from pathlib import Path
from typing import Any


def get_repo_root() -> Path:
    """Find the repository root directory."""
    # Current file is in backend/agents/
    return Path(__file__).resolve().parent.parent.parent


def load_prompt_file(agent_name: str, version: str = "v1") -> str:
    """Load the raw markdown prompt template for a specific agent and version."""
    repo_root = get_repo_root()
    prompt_path = repo_root / "prompts" / agent_name / f"{version}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found at {prompt_path} (agent={agent_name}, version={version})"
        )
    return prompt_path.read_text(encoding="utf-8")


def parse_prompt_sections(raw_content: str) -> tuple[str, str]:
    """Split prompt content into SYSTEM and USER sections.

    Expected format:
    ## SYSTEM
    <system text>
    ## USER
    <user text>
    """
    system_text = ""
    user_text = ""

    if "## SYSTEM" in raw_content and "## USER" in raw_content:
        system_part = raw_content.split("## SYSTEM", 1)[1]
        system_text, user_part = system_part.split("## USER", 1)
        user_text = user_part.strip()
        system_text = system_text.strip()
    elif "## SYSTEM" in raw_content:
        system_text = raw_content.split("## SYSTEM", 1)[1].strip()
    else:
        system_text = raw_content.strip()

    return system_text, user_text


def render_template(template: str, variables: dict[str, Any]) -> str:
    """Render double-curly-brace placeholders (e.g. {{variable}}) with provided values."""
    rendered = template
    for key, value in variables.items():
        placeholder = f"{{{{{key}}}}}"
        str_val = str(value) if value is not None else ""
        rendered = rendered.replace(placeholder, str_val)
    return rendered
