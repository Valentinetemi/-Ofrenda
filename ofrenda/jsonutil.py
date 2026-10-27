"""Pull a JSON object out of a model reply that may be wrapped in markdown."""

from __future__ import annotations

import json
import re


class JsonPayloadError(ValueError):
    pass


def parse_json_object(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise JsonPayloadError("no JSON object in the reply")
    blob = text[start : end + 1]
    # Gemma sometimes leaves a trailing comma before a brace.
    blob = re.sub(r",\s*([}\]])", r"\1", blob)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise JsonPayloadError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise JsonPayloadError("JSON was not an object")
    return data
