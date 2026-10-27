"""Gemma through Ollama, or the local stand-in when the mock flag is on."""

from __future__ import annotations

import logging

import httpx

from ofrenda.config import Settings
from ofrenda.mock_llm import mock_complete

logger = logging.getLogger("ofrenda.llm")


class StorytellerError(RuntimeError):
    """Ollama is down, or the configured Gemma model is not pulled."""


def ollama_complete(prompt: str, settings: Settings) -> str:
    url = f"{settings.ollama_host}/api/chat"
    body = {
        "model": settings.ollama_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 900},
    }
    try:
        with httpx.Client(timeout=settings.llm_timeout) as client:
            response = client.post(url, json=body)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300]
        raise StorytellerError(
            f"Ollama refused the request ({exc.response.status_code}). {detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise StorytellerError(
            "Ollama isn't running. Start it, then `ollama pull "
            f"{settings.ollama_model}`, or set OFRENDA_MOCK_LLM=1."
        ) from exc
    try:
        return payload["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise StorytellerError("Ollama replied without a message.") from exc


def completer_for(settings: Settings):
    if settings.mock_llm:
        return mock_complete
    return lambda prompt: ollama_complete(prompt, settings)


def ollama_status(settings: Settings) -> dict:
    """A short look at the local daemon. Never raises."""
    if settings.mock_llm:
        return {
            "llm": "mock",
            "model": settings.ollama_model,
            "ollama_reachable": False,
            "model_ready": False,
        }
    try:
        with httpx.Client(timeout=0.6) as client:
            response = client.get(f"{settings.ollama_host}/api/tags")
            response.raise_for_status()
            names = [item.get("name", "") for item in response.json().get("models", [])]
    except Exception as exc:
        logger.info("Ollama not reachable: %s", exc)
        return {
            "llm": "ollama",
            "model": settings.ollama_model,
            "ollama_reachable": False,
            "model_ready": False,
        }
    wanted = settings.ollama_model
    ready = wanted in names or any(name == wanted or name.startswith(wanted + "-") for name in names)
    # `gemma2` should also match `gemma2:latest` when the user omitted the tag.
    if not ready and ":" not in wanted:
        ready = any(name.split(":", 1)[0] == wanted for name in names)
    return {
        "llm": "ollama",
        "model": settings.ollama_model,
        "ollama_reachable": True,
        "model_ready": ready,
    }
