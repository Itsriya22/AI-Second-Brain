"""Groq-backed PARA classification and response validation."""

import json
import logging
import os
import re
from pathlib import Path

from groq import BadRequestError, Groq

from config import GROQ_MODEL, ROOT_DIR
from lib.models import Classification
from lib.runtime_config import get_runtime_setting

_CATEGORIES = {"projects", "areas", "resources", "archives"}
_FENCE_PATTERN = re.compile(r"\A\s*```(?:json)?\s*(.*?)\s*```\s*\Z", re.DOTALL | re.IGNORECASE)
_MAX_RESPONSE_ATTEMPTS = 2
_MAX_NOTE_CHARS = 24_000
_LOGGER = logging.getLogger(__name__)


class ClassificationError(RuntimeError):
    """The classification service returned an unusable result."""


def groq_client() -> Groq:
    """Create a Groq client from local environment or Streamlit secrets."""
    api_key = get_runtime_setting("GROQ_API_KEY")
    if not isinstance(api_key, str):
        raise ValueError(
            "GROQ_API_KEY is required; set it in .env, the environment, or Streamlit secrets."
        )
    return Groq(api_key=api_key)


def _parse_response(content: str) -> Classification:
    fenced = _FENCE_PATTERN.fullmatch(content)
    if fenced:
        content = fenced.group(1)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ClassificationError(f"Groq returned invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ClassificationError("Groq response must be a JSON object.")

    category = data.get("category")
    if not isinstance(category, str):
        _LOGGER.warning("Groq returned a missing or non-string category; using resources.")
        category = "resources"
    else:
        category = category.strip().lower()
        if category not in _CATEGORIES:
            _LOGGER.warning("Groq returned invalid category %r; using resources.", category)
            category = "resources"

    tags_value = data.get("tags")
    if not isinstance(tags_value, list):
        raise ClassificationError("Groq response field 'tags' must be a list.")
    tags: list[str] = []
    for tag in tags_value:
        if not isinstance(tag, str):
            continue
        normalized = re.sub(r"\s+", "-", tag.strip().replace("#", "").lower())
        if normalized and normalized not in tags:
            tags.append(normalized)
    if not 3 <= len(tags) <= 8:
        raise ClassificationError("Groq must return 3 to 8 distinct non-empty tags.")

    summary = data.get("summary")
    title = data.get("title")
    if not isinstance(summary, str) or not summary.strip():
        raise ClassificationError("Groq response field 'summary' must be a non-empty string.")
    summary = " ".join(summary.split())
    if len(summary) > 160:
        summary = summary[:157].rstrip() + "..."
    if not isinstance(title, str) or not title.strip():
        raise ClassificationError("Groq response field 'title' must be a non-empty string.")

    return Classification(
        category=category,
        tags=tags,
        summary=summary,
        title=" ".join(title.split()),
    )


def classify_content(
    body: str,
    title: str | None = None,
    *,
    client: Groq | None = None,
    prompt_path: Path = ROOT_DIR / "prompts" / "classify.txt",
) -> Classification:
    """Classify note content with Groq, retrying malformed model responses once."""
    if not body.strip():
        raise ValueError("Cannot classify an empty note.")
    if client is None:
        client = groq_client()

    system_prompt = prompt_path.read_text(encoding="utf-8")
    note_text = body[:_MAX_NOTE_CHARS]
    if len(body) > _MAX_NOTE_CHARS:
        _LOGGER.warning("Note text exceeds %s characters; classifying its beginning only.", _MAX_NOTE_CHARS)
    user_prompt = json.dumps(
        {"title": title or "Untitled", "body": note_text},
        ensure_ascii=False,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    last_error: ClassificationError | None = None

    for attempt in range(_MAX_RESPONSE_ATTEMPTS):
        try:
            response = client.chat.completions.create(
                model=os.environ.get("GROQ_MODEL", GROQ_MODEL),
                messages=messages,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
        except BadRequestError as exc:
            if "response_format" not in str(exc).lower() and "json" not in str(exc).lower():
                raise
            _LOGGER.warning("Groq JSON response mode is unavailable; retrying without it.")
            response = client.chat.completions.create(
                model=os.environ.get("GROQ_MODEL", GROQ_MODEL),
                messages=messages,
                temperature=0.2,
            )

        if not response.choices:
            last_error = ClassificationError("Groq returned no classification choices.")
            content = None
        else:
            content = response.choices[0].message.content
        if not content:
            last_error = ClassificationError("Groq returned an empty classification response.")
        else:
            try:
                return _parse_response(content)
            except ClassificationError as exc:
                last_error = exc
        if attempt + 1 < _MAX_RESPONSE_ATTEMPTS:
            _LOGGER.warning("Retrying classification after unusable response: %s", last_error)

    if last_error is None:
        raise ClassificationError("Classification did not produce a result.")
    raise last_error
