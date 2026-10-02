"""Tests for safe graph rendering and app graph loading."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from app import _graph_html, _is_read_only, _read_graph


class AppGraphTests(unittest.TestCase):
    def test_app_is_read_only_and_displays_graph_and_ask(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict(os.environ, {"SECONSELF_READONLY": "1"}):
            app = AppTest.from_file(str(app_path)).run()

        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "SecondSelf")
        self.assertIn("Knowledge graph", [item.value for item in app.subheader])
        self.assertIn("Ask your brain", [item.value for item in app.subheader])
        self.assertTrue(any("Read-only mode" in item.value for item in app.info))
        self.assertFalse(any("capture" in item.label.lower() for item in app.text_input))

    def test_ask_error_does_not_hide_the_graph(self) -> None:
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_path)).run()
        app.session_state["secondself_ask_result"] = {
            "answer": "",
            "sources": [],
            "error": "Test API error.",
        }
        app.run()

        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "SecondSelf")
        self.assertTrue(any("Test API error." in item.value for item in app.error))

    def test_read_only_mode_accepts_common_true_values(self) -> None:
        for value in ("1", "true", "yes", " TRUE "):
            with self.subTest(value=value), patch.dict(os.environ, {"SECONSELF_READONLY": value}):
                self.assertTrue(_is_read_only())

        with patch.dict(os.environ, {"SECONSELF_READONLY": "0"}):
            self.assertFalse(_is_read_only())

    def test_read_graph_loads_phase_four_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "graph.json"
            graph = {"generated_at": "2026-09-30T12:00:00+05:30", "nodes": [], "edges": []}
            path.write_text(json.dumps(graph), encoding="utf-8")

            self.assertEqual(_read_graph(path), graph)

    def test_graph_html_escapes_note_content_before_javascript_injection(self) -> None:
        graph = {
            "nodes": [
                {
                    "id": "a1b2c3d4",
                    "label": "</script><script>alert(1)</script>",
                    "category": "projects",
                    "summary": "<img src=x onerror=alert(1)>",
                    "preview": "Knowledge",
                }
            ],
            "edges": [],
        }

        rendered = _graph_html(graph)

        self.assertNotIn("</script><script>alert(1)</script>", rendered)
        self.assertNotIn("<img src=x onerror=alert(1)>", rendered)
        self.assertIn("\\u003c/script\\u003e", rendered)
        self.assertIn("barnesHut", rendered)
        self.assertIn("dragNodes: true", rendered)
        self.assertIn("dragView: true", rendered)
        self.assertIn("zoomView: true", rendered)
        self.assertIn("stabilizationIterationsDone", rendered)
        self.assertIn("escapeHtml(node.preview)", rendered)

    def test_empty_graph_has_interactive_empty_state(self) -> None:
        rendered = _graph_html({"nodes": [], "edges": []})

        self.assertIn("Your graph is empty.", rendered)
        self.assertIn("if (!graph.nodes.length)", rendered)


if __name__ == "__main__":
    unittest.main()
