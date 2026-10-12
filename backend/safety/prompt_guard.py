"""Prompt isolation guards and XML nonce encapsulation for untrusted text."""

import re
import secrets


def generate_nonce(length: int = 16) -> str:
    """Generate a cryptographically secure random hexadecimal nonce."""
    return secrets.token_hex(length // 2)


def wrap_untrusted_text(content: str, tag: str, nonce: str | None = None) -> str:
    """Wrap untrusted candidate or job description text in an XML block with a nonce.

    Prevents prompt injection from closing the wrapper XML tags.
    """
    if nonce is None:
        nonce = generate_nonce()

    # Disarm any internal closing attempts matching </tag
    escaped = re.sub(
        rf"</\s*{re.escape(tag)}[^>]*>",
        f"&lt;/{tag}_disarmed&gt;",
        content,
        flags=re.IGNORECASE,
    )

    return f"<{tag} nonce='{nonce}'>\n{escaped}\n</{tag} nonce='{nonce}'>"
