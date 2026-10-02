"""Classify raw captures into PARA-organized wiki notes."""

import argparse
from dataclasses import replace
import logging
from pathlib import Path

from groq import APIError

from config import RAW_DIR, WIKI_DIR
from lib.io import read_raw_note, update_raw_note
from lib.llm import ClassificationError, classify_content, groq_client
from lib.models import WikiNote
from lib.wiki import find_wiki_path, write_wiki_note

_LOGGER = logging.getLogger("secondself.classify")


def _resolve_raw_path(value: str, raw_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
        if not path.exists():
            path = raw_dir / value
    path = path.resolve()
    try:
        path.relative_to(raw_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"Raw note must be inside {raw_dir}: {path}") from exc
    if path.suffix.lower() != ".md" or not path.is_file():
        raise FileNotFoundError(f"Raw Markdown note does not exist: {path}")
    return path


def classify_file(
    raw_path: Path,
    *,
    client,
    raw_dir: Path = RAW_DIR,
    wiki_dir: Path = WIKI_DIR,
    force: bool = False,
) -> WikiNote | None:
    """Classify one raw note, returning None when an existing result is skipped."""
    raw_path = raw_path.resolve()
    raw_path.relative_to(raw_dir.resolve())
    raw_note = read_raw_note(raw_path)
    existing_path = find_wiki_path(raw_note.id, wiki_dir)
    if raw_note.processed and not force:
        _LOGGER.info("Skipping already-processed capture %s", raw_note.id)
        return None
    if existing_path is not None and not force:
        if not raw_note.processed:
            update_raw_note(raw_path, replace(raw_note, processed=True))
        _LOGGER.info("Skipping capture %s; wiki note already exists at %s", raw_note.id, existing_path)
        return None

    classification = classify_content(raw_note.body, raw_note.title, client=client)
    wiki_note = write_wiki_note(raw_note, classification, raw_path, wiki_dir)
    if not raw_note.processed:
        update_raw_note(raw_path, replace(raw_note, processed=True))
    _LOGGER.info("Classified %s -> %s", raw_note.id, wiki_note.path)
    return wiki_note


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_file", nargs="?", help="One raw Markdown capture to classify")
    parser.add_argument("--all", action="store_true", help="Classify every eligible raw capture")
    parser.add_argument("--force", action="store_true", help="Reclassify even processed or existing notes")
    args = parser.parse_args(argv)
    if args.all == (args.raw_file is not None):
        parser.error("provide one raw_file or use --all")
    if args.force and not (args.all or args.raw_file):
        parser.error("--force requires a raw_file or --all")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.all:
        raw_paths = sorted(RAW_DIR.glob("*.md"))
    else:
        try:
            raw_paths = [_resolve_raw_path(args.raw_file, RAW_DIR)]
        except (FileNotFoundError, ValueError) as exc:
            parser.error(str(exc))

    try:
        client = groq_client()
    except ValueError as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")

    classified = 0
    for raw_path in raw_paths:
        try:
            if classify_file(raw_path, client=client, force=args.force):
                classified += 1
        except (OSError, ValueError, ClassificationError, APIError) as exc:
            parser.exit(1, f"{parser.prog}: error processing {raw_path}: {exc}\n")
    print(f"Classified {classified} capture(s).")


if __name__ == "__main__":
    main()
