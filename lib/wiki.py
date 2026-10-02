"""Write classified notes into their PARA wiki folders."""

from datetime import datetime
from pathlib import Path
import os
import re
import tempfile

import yaml

from config import WIKI_DIR
from lib.models import Classification, RawNote, WikiNote

_CATEGORIES = {"projects", "areas", "resources", "archives"}
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
_RELATED_START = "<!-- secondself:related:start -->"
_RELATED_END = "<!-- secondself:related:end -->"


def slugify(title: str) -> str:
    """Convert a title to a filesystem-safe lowercase slug."""
    slug = _SLUG_PATTERN.sub("-", title.lower()).strip("-")
    return slug[:80].rstrip("-") or "untitled"


def _path_for_note(note: WikiNote, wiki_dir: Path) -> Path:
    if note.category not in _CATEGORIES:
        raise ValueError(f"Invalid PARA category: {note.category!r}")
    category_dir = wiki_dir / note.category
    category_dir.mkdir(parents=True, exist_ok=True)
    path = category_dir / f"{slugify(note.title)}.md"
    if path.exists():
        existing = read_wiki_note(path)
        if existing.id != note.id:
            path = category_dir / f"{slugify(note.title)}-{note.id[:4]}.md"
    if path.exists():
        existing = read_wiki_note(path)
        if existing.id != note.id:
            raise FileExistsError(f"Wiki note path collision: {path}")
    return path


def find_wiki_path(note_id: str, wiki_dir: Path = WIKI_DIR) -> Path | None:
    """Find the existing wiki file for an ID and reject duplicate IDs."""
    matches = [
        path
        for path in wiki_dir.glob("*/*.md")
        if read_wiki_note(path).id == note_id
    ]
    if len(matches) > 1:
        raise ValueError(f"Multiple wiki notes have id {note_id}: {matches}")
    return matches[0] if matches else None


def _metadata(note: WikiNote, raw_file: str, updated_at: str) -> dict[str, object]:
    return {
        "id": note.id,
        "raw_file": raw_file,
        "category": note.category,
        "tags": note.tags,
        "summary": note.summary,
        "title": note.title,
        "linked_ids": note.linked_ids,
        "updated_at": updated_at,
    }


def _write_atomic(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def write_wiki_note(
    raw_note: RawNote,
    classification: Classification,
    raw_path: Path,
    wiki_dir: Path = WIKI_DIR,
) -> WikiNote:
    """Persist classification metadata while preserving the captured body."""
    note = WikiNote(
        id=raw_note.id,
        category=classification.category,
        tags=classification.tags,
        summary=classification.summary,
        title=classification.title,
        body=raw_note.body,
        linked_ids=[],
        path=Path(),
    )
    existing_path = find_wiki_path(note.id, wiki_dir)
    if existing_path is not None and existing_path.parent.name == note.category:
        path = existing_path
    else:
        path = _path_for_note(note, wiki_dir)
    note.path = path
    updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    frontmatter = yaml.safe_dump(
        _metadata(note, raw_path.name, updated_at),
        sort_keys=False,
        allow_unicode=True,
    )
    body = f"# {note.title}\n\n{note.summary}\n\n{note.body}"
    _write_atomic(path, f"---\n{frontmatter}---\n\n{body}")
    if existing_path is not None and existing_path != path:
        existing_path.unlink()
    return note


def read_wiki_note(path: Path) -> WikiNote:
    """Read a wiki note and validate its required frontmatter."""
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError(f"Missing YAML frontmatter in {path}")
    frontmatter, separator, body = content[4:].partition("\n---\n\n")
    if not separator:
        raise ValueError(f"Unterminated YAML frontmatter in {path}")
    metadata = yaml.safe_load(frontmatter)
    if not isinstance(metadata, dict):
        raise ValueError(f"Frontmatter must be a YAML mapping in {path}")
    required = {"id", "category", "tags", "summary", "title", "linked_ids"}
    missing = required - metadata.keys()
    if missing:
        raise ValueError(f"Missing wiki frontmatter fields in {path}: {', '.join(sorted(missing))}")
    if not isinstance(metadata["id"], str) or not isinstance(metadata["category"], str):
        raise ValueError(f"Invalid id or category in {path}")
    if metadata["category"] not in _CATEGORIES:
        raise ValueError(f"Invalid PARA category in {path}: {metadata['category']!r}")
    if not isinstance(metadata["tags"], list) or not all(
        isinstance(tag, str) for tag in metadata["tags"]
    ):
        raise ValueError(f"Invalid tags in {path}")
    if not isinstance(metadata["linked_ids"], list) or not all(
        isinstance(linked_id, str) for linked_id in metadata["linked_ids"]
    ):
        raise ValueError(f"Invalid linked_ids in {path}")
    for field in ("summary", "title"):
        if not isinstance(metadata[field], str):
            raise ValueError(f"Invalid {field} in {path}")
    return WikiNote(
        id=metadata["id"],
        category=metadata["category"],
        tags=metadata["tags"],
        summary=metadata["summary"],
        title=metadata["title"],
        body=body,
        linked_ids=metadata["linked_ids"],
        path=path,
    )


def update_wiki_links(
    note: WikiNote,
    related_notes: list[WikiNote],
) -> None:
    """Persist canonical linked IDs and a matching human-readable Related section."""
    content = note.path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError(f"Missing YAML frontmatter in {note.path}")
    frontmatter, separator, body = content[4:].partition("\n---\n\n")
    if not separator:
        raise ValueError(f"Unterminated YAML frontmatter in {note.path}")
    metadata = yaml.safe_load(frontmatter)
    if not isinstance(metadata, dict) or metadata.get("id") != note.id:
        raise ValueError(f"Wiki note frontmatter does not match note {note.id}: {note.path}")

    clean_body = body
    if _RELATED_START in clean_body:
        before, _, after_start = clean_body.rpartition(_RELATED_START)
        _, end_marker, after = after_start.partition(_RELATED_END)
        if not end_marker:
            raise ValueError(f"Unterminated generated Related section in {note.path}")
        if after.strip():
            raise ValueError(f"Generated Related section is not at the end of {note.path}")
        related_heading = before.rfind("\n## Related")
        clean_body = (
            before[:related_heading].rstrip()
            if related_heading >= 0
            else before.rstrip()
        )
    else:
        related_header = "\n## Related\n"
        if related_header in clean_body:
            before, _, old_related = clean_body.rpartition(related_header)
            if all(
                not line.strip() or (line.startswith("- [[") and "]]" in line)
                for line in old_related.splitlines()
            ):
                clean_body = before.rstrip()

    unique_related: dict[str, WikiNote] = {}
    for related in related_notes:
        if related.id != note.id:
            unique_related.setdefault(related.id, related)
    note.linked_ids = list(unique_related)
    related_section = f"\n\n## Related\n\n{_RELATED_START}"
    if unique_related:
        related_section += "\n" + "\n".join(
            f"- [[{related.category}/{related.path.stem}|{related.title.replace('|', '—')}]]"
            for related in unique_related.values()
        )
    related_section += f"\n{_RELATED_END}"
    updated_body = f"{clean_body.rstrip()}{related_section}"
    if metadata.get("linked_ids") == note.linked_ids and body == updated_body:
        return

    metadata["linked_ids"] = note.linked_ids
    metadata["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    serialized_frontmatter = yaml.safe_dump(
        metadata,
        sort_keys=False,
        allow_unicode=True,
    )
    _write_atomic(
        note.path,
        f"---\n{serialized_frontmatter}---\n\n{updated_body}",
    )
