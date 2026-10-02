"""Create embedding-based links between related PARA wiki notes."""

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np

from config import MAX_LINKS_PER_NOTE, SIMILARITY_THRESHOLD, WIKI_DIR
from lib.embed import Encoder, embed_notes, embedding_text
from lib.wiki import read_wiki_note, update_wiki_links


def relink_corpus(
    wiki_dir: Path = WIKI_DIR,
    *,
    model: Encoder | None = None,
    cache_path: Path | None = None,
    metadata_path: Path | None = None,
    threshold: float = SIMILARITY_THRESHOLD,
    max_links_per_note: int = MAX_LINKS_PER_NOTE,
) -> int:
    """Recompute corpus relationships and return the number of undirected links."""
    if not 0 <= threshold <= 1:
        raise ValueError("similarity threshold must be between 0 and 1")
    if max_links_per_note < 0:
        raise ValueError("max_links_per_note must not be negative")

    paths = sorted(wiki_dir.glob("*/*.md"))
    notes = [read_wiki_note(path) for path in paths]
    ids = [note.id for note in notes]
    if len(ids) != len(set(ids)):
        raise ValueError("Wiki corpus contains duplicate note IDs.")

    texts = {
        note.id: embedding_text(note.title, note.summary, note.body)
        for note in notes
    }
    embedding_options: dict[str, object] = {}
    if cache_path is not None:
        embedding_options["cache_path"] = cache_path
    if metadata_path is not None:
        embedding_options["metadata_path"] = metadata_path
    vectors = embed_notes(texts, model=model, **embedding_options)

    similarities: list[tuple[float, str, str]] = []
    for left, right in combinations(notes, 2):
        score = float(np.dot(vectors[left.id], vectors[right.id]))
        if score >= threshold:
            similarities.append((score, left.id, right.id))
    similarities.sort(key=lambda candidate: (-candidate[0], candidate[1], candidate[2]))

    note_by_id = {note.id: note for note in notes}
    related_by_id: dict[str, list[tuple[float, str]]] = {note.id: [] for note in notes}
    for score, left_id, right_id in similarities:
        if (
            len(related_by_id[left_id]) < max_links_per_note
            and len(related_by_id[right_id]) < max_links_per_note
        ):
            related_by_id[left_id].append((score, right_id))
            related_by_id[right_id].append((score, left_id))

    for note in notes:
        related = [
            note_by_id[related_id]
            for _, related_id in sorted(
                related_by_id[note.id],
                key=lambda candidate: (-candidate[0], candidate[1]),
            )
        ]
        update_wiki_links(note, related)
    return sum(len(related) for related in related_by_id.values()) // 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=SIMILARITY_THRESHOLD)
    parser.add_argument("--max-links", type=int, default=MAX_LINKS_PER_NOTE)
    args = parser.parse_args()
    try:
        count = relink_corpus(threshold=args.threshold, max_links_per_note=args.max_links)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"{parser.prog}: error: {exc}\n")
    print(f"Created {count} related-note link(s).")


if __name__ == "__main__":
    main()
