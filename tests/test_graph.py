"""Tests for wiki-to-graph conversion and JSON export."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from lib.graph import build_graph, export_graph
from lib.models import Classification, RawNote
from lib.wiki import read_wiki_note, write_wiki_note, update_wiki_links


class GraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.wiki_dir = self.root / "wiki"
        self.raw_dir = self.root / "raw"
        self.output_path = self.root / "graph.json"
        self.notes = {}
        for note_id, title, category in (
            ("a1b2c3d4", "Graph Node Alpha", "projects"),
            ("b1b2c3d4", "Graph Node Beta", "resources"),
            ("c1b2c3d4", "Graph Node Gamma", "areas"),
        ):
            raw_path = self.raw_dir / f"{note_id}.md"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text("source", encoding="utf-8")
            note = RawNote(
                id=note_id,
                captured_at="2026-09-30T12:00:00+05:30",
                source_type="note",
                source_ref=None,
                body=f"Unique body for {title}.\n" + ("Extra detail. " * 50),
                processed=True,
                title=title,
            )
            wiki_note = write_wiki_note(
                note,
                Classification(
                    category=category,
                    tags=["graph", "knowledge", "notes"],
                    summary=f"Summary for {title}.",
                    title=title,
                ),
                raw_path,
                self.wiki_dir,
            )
            self.notes[note_id] = wiki_note

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_graph_schema_paths_previews_and_unique_undirected_edges(self) -> None:
        update_wiki_links(self.notes["a1b2c3d4"], [self.notes["b1b2c3d4"]])
        self._set_linked_ids("b1b2c3d4", ["a1b2c3d4", "a1b2c3d4", "missing1"])
        graph = build_graph(
            self.wiki_dir,
            root_dir=self.root,
            generated_at="2026-09-30T12:00:00+05:30",
        )

        self.assertEqual(graph.generated_at, "2026-09-30T12:00:00+05:30")
        self.assertEqual(len(graph.nodes), 3)
        self.assertEqual({node["id"] for node in graph.nodes}, set(self.notes))
        self.assertEqual(
            set(graph.nodes[0]),
            {"id", "label", "category", "tags", "summary", "path", "preview"},
        )
        self.assertTrue(all(node["path"].startswith("wiki/") for node in graph.nodes))
        self.assertTrue(all(len(node["preview"]) <= 400 for node in graph.nodes))
        self.assertEqual(
            graph.edges,
            [{"from": "a1b2c3d4", "to": "b1b2c3d4", "weight": 1.0, "reason": "embedding"}],
        )

    def test_exported_json_is_pretty_and_matches_schema(self) -> None:
        graph = build_graph(self.wiki_dir, root_dir=self.root)

        result = export_graph(graph, self.output_path)
        exported = json.loads(result.read_text(encoding="utf-8"))

        self.assertEqual(set(exported), {"generated_at", "nodes", "edges"})
        self.assertEqual(exported["nodes"], graph.nodes)
        self.assertEqual(exported["edges"], graph.edges)
        self.assertIn("\n  \"nodes\": [", result.read_text(encoding="utf-8"))

    def test_dangling_and_self_links_are_dropped(self) -> None:
        self._set_linked_ids("a1b2c3d4", ["a1b2c3d4", "deadbeef"])

        graph = build_graph(self.wiki_dir, root_dir=self.root)

        self.assertEqual(graph.edges, [])

    def _set_linked_ids(self, note_id: str, linked_ids: list[str]) -> None:
        note_path = self.notes[note_id].path
        content = note_path.read_text(encoding="utf-8")
        frontmatter, separator, body = content[4:].partition("\n---\n\n")
        self.assertTrue(separator)
        metadata = yaml.safe_load(frontmatter)
        metadata["linked_ids"] = linked_ids
        note_path.write_text(
            f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\n{body}",
            encoding="utf-8",
        )

    def test_zero_node_graph_fails_export_and_cli_exits_nonzero(self) -> None:
        empty_wiki = self.root / "empty-wiki"
        empty_output = self.root / "empty-graph.json"
        graph = build_graph(empty_wiki, root_dir=self.root)
        with self.assertRaisesRegex(ValueError, "zero notes"):
            export_graph(graph, empty_output)
        self.assertFalse(empty_output.exists())

        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "build_graph.py"),
                "--wiki-dir",
                str(empty_wiki),
                "--output",
                str(empty_output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("zero notes", result.stderr)
        self.assertFalse(empty_output.exists())


if __name__ == "__main__":
    unittest.main()
