"""Tests for cached note embeddings and deterministic auto-linking."""

from pathlib import Path
import tempfile
import unittest

import numpy as np

from lib.embed import embed_notes, embedding_text
from lib.models import Classification, RawNote
from lib.wiki import read_wiki_note, write_wiki_note
from link import relink_corpus


class FakeEncoder:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[list[str]] = []

    def encode(self, sentences: list[str], **kwargs: object) -> np.ndarray:
        self.calls.append(sentences)
        return np.asarray(
            [
                self.vectors[next(key for key in self.vectors if text == key or text.startswith(f"{key}\n"))]
                for text in sentences
            ],
            dtype=np.float32,
        )


class LinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.wiki_dir = self.root / "wiki"
        self.cache_path = self.root / "data" / "embeddings.npz"
        self.metadata_path = self.root / "data" / "embedding_meta.json"
        self.texts = {
            "a1b2c3d4": [1.0, 0.0],
            "b1b2c3d4": [0.8, 0.6],
            "c1b2c3d4": [0.0, 1.0],
        }
        titles = ("Note Alpha", "Note Beta", "Note Gamma")
        for note_id, title in zip(self.texts, titles, strict=True):
            raw_note = RawNote(
                id=note_id,
                captured_at="2026-09-30T12:00:00+05:30",
                source_type="note",
                source_ref=None,
                body=f"Original body for {title}.",
                processed=True,
                title=title,
            )
            write_wiki_note(
                raw_note,
                Classification(
                    category="resources",
                    tags=["notes", "links", "knowledge"],
                    summary=f"Summary for {title}.",
                    title=title,
                ),
                self.root / "raw.md",
                self.wiki_dir,
            )
        self.encoder = FakeEncoder(dict(zip(titles, self.texts.values(), strict=True)))

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_similarity_threshold_creates_expected_symmetric_edge(self) -> None:
        count = relink_corpus(
            self.wiki_dir,
            model=self.encoder,
            cache_path=self.cache_path,
            metadata_path=self.metadata_path,
            threshold=0.75,
        )

        self.assertEqual(count, 1)
        notes = [read_wiki_note(path) for path in sorted(self.wiki_dir.glob("*/*.md"))]
        links = {note.id: note.linked_ids for note in notes}
        self.assertEqual(links["a1b2c3d4"], ["b1b2c3d4"])
        self.assertEqual(links["b1b2c3d4"], ["a1b2c3d4"])
        self.assertEqual(links["c1b2c3d4"], [])
        alpha = next(note for note in notes if note.id == "a1b2c3d4")
        alpha_text = alpha.path.read_text(encoding="utf-8")
        self.assertIn("## Related", alpha_text)
        beta = next(note for note in notes if note.id == "b1b2c3d4")
        obsidian_target = f"[[{beta.category}/{beta.path.stem}|{beta.title}]]"
        self.assertIn(f"- {obsidian_target}", alpha_text)
        self.assertTrue((self.wiki_dir / f"{beta.category}" / f"{beta.path.stem}.md").is_file())
        self.assertEqual(
            read_wiki_note(self.wiki_dir / beta.category / f"{beta.path.stem}.md").id,
            beta.id,
        )

    def test_rerun_is_idempotent_without_duplicating_related_ids(self) -> None:
        options = {
            "model": self.encoder,
            "cache_path": self.cache_path,
            "metadata_path": self.metadata_path,
            "threshold": 0.5,
        }
        first_count = relink_corpus(self.wiki_dir, **options)
        first_contents = {path: path.read_text(encoding="utf-8") for path in self.wiki_dir.glob("*/*.md")}
        second_count = relink_corpus(self.wiki_dir, **options)
        second_contents = {path: path.read_text(encoding="utf-8") for path in self.wiki_dir.glob("*/*.md")}

        self.assertEqual(first_count, second_count)
        self.assertEqual(first_contents, second_contents)
        for path in self.wiki_dir.glob("*/*.md"):
            note = read_wiki_note(path)
            self.assertEqual(len(note.linked_ids), len(set(note.linked_ids)))
            self.assertEqual(path.read_text(encoding="utf-8").count("## Related"), 1)

    def test_global_link_cap_remains_symmetric(self) -> None:
        self.encoder = FakeEncoder({title: [1.0, 0.0] for title in ("Note Alpha", "Note Beta", "Note Gamma")})

        count = relink_corpus(
            self.wiki_dir,
            model=self.encoder,
            cache_path=self.cache_path,
            metadata_path=self.metadata_path,
            threshold=0.5,
            max_links_per_note=1,
        )

        self.assertEqual(count, 1)
        notes = [read_wiki_note(path) for path in self.wiki_dir.glob("*/*.md")]
        links = {note.id: note.linked_ids for note in notes}
        self.assertEqual(links["a1b2c3d4"], ["b1b2c3d4"])
        self.assertEqual(links["b1b2c3d4"], ["a1b2c3d4"])
        self.assertEqual(links["c1b2c3d4"], [])
        self.assertTrue(all(len(linked_ids) <= 1 for linked_ids in links.values()))

    def test_cache_reuses_matching_vectors_and_reembeds_changed_content(self) -> None:
        cache_encoder = FakeEncoder({"one": [1.0, 0.0], "two": [0.0, 1.0]})
        first = embed_notes(
            {"note": "one", "other": "two"},
            model=cache_encoder,
            cache_path=self.cache_path,
            metadata_path=self.metadata_path,
        )
        self.assertEqual(len(cache_encoder.calls), 1)
        self.assertTrue(self.cache_path.is_file())
        self.assertTrue(self.metadata_path.is_file())
        self.assertAlmostEqual(float(np.linalg.norm(first["note"])), 1.0)

        second_encoder = FakeEncoder({"updated": [1.0, 1.0]})
        second = embed_notes(
            {"note": "one", "other": "updated"},
            model=second_encoder,
            cache_path=self.cache_path,
            metadata_path=self.metadata_path,
        )

        self.assertEqual(second_encoder.calls, [["updated"]])
        np.testing.assert_allclose(second["note"], first["note"])
        self.assertAlmostEqual(float(np.linalg.norm(second["other"])), 1.0, places=6)

    def test_no_wiki_notes_produces_empty_cache(self) -> None:
        empty_wiki = self.root / "empty-wiki"

        count = relink_corpus(
            empty_wiki,
            model=self.encoder,
            cache_path=self.cache_path,
            metadata_path=self.metadata_path,
        )

        self.assertEqual(count, 0)
        self.assertTrue(self.cache_path.is_file())
        self.assertTrue(self.metadata_path.is_file())
        self.assertEqual(self.encoder.calls, [])

    def test_generated_related_section_does_not_change_embedding_content(self) -> None:
        before = embedding_text("Title", "Summary", "Body text.\n")
        after = embedding_text(
            "Title",
            "Summary",
            "Body text.\n\n## Related\n\n"
            "<!-- secondself:related:start -->\n"
            "- [[b1b2c3d4]] Related note\n"
            "<!-- secondself:related:end -->",
        )

        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
