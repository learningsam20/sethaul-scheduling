from __future__ import annotations

import os
from typing import Any

from app.config import get_settings


def tracing_enabled() -> bool:
    settings = get_settings()
    return bool(settings.langchain_tracing_v2 and settings.langsmith_api_key)


def configure_langsmith() -> dict[str, Any]:
    """Push LangSmith env vars so LangChain auto-traces LLM calls."""
    settings = get_settings()
    enabled = tracing_enabled()
    if enabled:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        # Prefer cloud endpoint unless overridden
        os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
        os.environ.setdefault("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
        # Fail fast if LangSmith is unreachable so agent turns do not hang on ingest retries
        os.environ.setdefault("LANGSMITH_TIMEOUT", "8")
        os.environ.setdefault("LANGCHAIN_CALLBACKS_BACKGROUND", "true")
    else:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["LANGSMITH_TRACING"] = "false"
    return {
        "enabled": enabled,
        "project": settings.langsmith_project if enabled else None,
        "has_api_key": bool(settings.langsmith_api_key),
    }
