"""Read and write raw-note Markdown files with YAML frontmatter."""

import re
from datetime import datetime
from pathlib import Path

import yaml

from config import RAW_DIR
from lib.models import RawNote

_ID_PATTERN = re.compile(r"^[0-9a-f]{8}$")


def raw_note_path(note: RawNote, raw_dir: Path = RAW_DIR) -> Path:
    """Return the canonical filename for a raw note."""
    if not _ID_PATTERN.fullmatch(note.id):
        raise ValueError(f"Invalid note ID: {note.id!r}")
    captured_at = datetime.fromisoformat(note.captured_at)
    stamp = captured_at.strftime("%Y%m%dT%H%M%S")
    return raw_dir / f"{stamp}_{note.id}.md"


def write_raw_note(note: RawNote, raw_dir: Path = RAW_DIR) -> Path:
    """Create a raw note without replacing an existing file."""
    path = raw_note_path(note, raw_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "id": note.id,
        "captured_at": note.captured_at,
        "source_type": note.source_type,
        "source_ref": note.source_ref or "",
        "title": note.title or "",
        "processed": note.processed,
    }
    serialized = f"---\n{yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)}---\n\n{note.body}"

    try:
        with path.open("x", encoding="utf-8", newline="\n") as capture_file:
            capture_file.write(serialized)
    except FileExistsError:
        raise FileExistsError(f"Raw note already exists: {path}") from None
    except OSError:
        path.unlink(missing_ok=True)
        raise
    return path


def read_raw_note(path: Path) -> RawNote:
    """Load and validate a raw-note Markdown file."""
    with path.open(encoding="utf-8") as capture_file:
        content = capture_file.read()

    if not content.startswith("---\n"):
        raise ValueError(f"Missing YAML frontmatter in {path}")
    frontmatter, separator, body = content[4:].partition("\n---\n\n")
    if not separator:
        raise ValueError(f"Unterminated YAML frontmatter in {path}")

    metadata = yaml.safe_load(frontmatter)
    if not isinstance(metadata, dict):
        raise ValueError(f"Frontmatter must be a YAML mapping in {path}")
    required = {"id", "captured_at", "source_type", "source_ref", "processed"}
    missing = required - metadata.keys()
    if missing:
        raise ValueError(f"Missing frontmatter fields in {path}: {', '.join(sorted(missing))}")
    for field in ("id", "captured_at", "source_type", "source_ref"):
        if not isinstance(metadata[field], str):
            raise ValueError(f"{field} must be a string in {path}")
    if not _ID_PATTERN.fullmatch(metadata["id"]):
        raise ValueError(f"Invalid note ID in {path}: {metadata['id']!r}")
    if metadata["source_type"] not in {"note", "link", "file"}:
        raise ValueError(f"Invalid source_type in {path}: {metadata['source_type']!r}")
    if not isinstance(metadata["processed"], bool):
        raise ValueError(f"processed must be a boolean in {path}")
    try:
        captured_at = datetime.fromisoformat(metadata["captured_at"])
    except ValueError as exc:
        raise ValueError(f"Invalid captured_at timestamp in {path}") from exc
    if captured_at.utcoffset() is None:
        raise ValueError(f"captured_at must include a timezone in {path}")
    title = metadata.get("title") or None
    if title is not None and not isinstance(title, str):
        raise ValueError(f"title must be a string in {path}")

    return RawNote(
        id=str(metadata["id"]),
        captured_at=str(metadata["captured_at"]),
        source_type=metadata["source_type"],
        source_ref=metadata["source_ref"] or None,
        body=body,
        processed=metadata["processed"],
        title=title,
    )
