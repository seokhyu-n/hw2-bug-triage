"""Project-wide constants and API key loading."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RUNTIME_DIR = DATA_DIR / "runtime"
PROMPTS_DIR = ROOT / "prompts"

# "headless" = Claude Code (`claude -p`) with the signed-in account, no API key (the default).
# "api" = the Anthropic API with CLAUDE_API_KEY (billed per call); only when set explicitly.
def llm_backend() -> str:
    return os.environ.get("LLM_BACKEND", "headless").strip().lower()


MODEL_DEFAULT = "claude-haiku-5-5"
MODEL_COMPARE = "claude-sonnet-5-5"

# USD per million tokens
PRICES: dict[str, dict[str, float]] = {
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_write": 0.125, "cache_read": 0.01},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.10},
}

_PLACEHOLDER = "여기에_API_키를_붙여넣기"


def get_api_key() -> str:
    """Return CLAUDE_API_KEY (environment wins over .env); raise if missing or placeholder."""
    load_dotenv(ROOT / ".env")  # does not override existing environment variables
    key = os.environ.get("CLAUDE_API_KEY", "").strip()
    if not key or key == _PLACEHOLDER:
        raise RuntimeError("CLAUDE_API_KEY가 .env에 없습니다")
    return key
