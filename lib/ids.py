"""Unique identifier helpers."""

import secrets
from pathlib import Path

from config import RAW_DIR


def new_id(raw_dir: Path = RAW_DIR) -> str:
    """Return an unused, compact identifier for a raw note."""
    for _ in range(100):
        note_id = secrets.token_hex(4)
        if not any(raw_dir.glob(f"*_{note_id}.md")) and not any(
            path.stem == note_id for path in (raw_dir / "originals").glob(f"{note_id}.*")
        ):
            return note_id
    raise RuntimeError("Could not allocate a unique ID after 100 attempts.")
