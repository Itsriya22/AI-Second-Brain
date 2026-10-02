"""Tests for PARA classification and wiki persistence."""

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lib.io import read_raw_note, write_raw_note
from lib.llm import ClassificationError, _parse_response, classify_content
from lib.models import Classification, RawNote
from lib.wiki import read_wiki_note, write_wiki_note
from classify import classify_file, main


class _FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.responses.pop(0)
        return type(
            "Completion",
            (),
            {
                "choices": [
                    type("Choice", (), {"message": type("Message", (), {"content": content})()})()
                ]
            },
        )()


class _FakeGroq:
    def __init__(self, responses: list[str]) -> None:
        self.completions = _FakeCompletions(responses)
        self.chat = type("Chat", (), {"completions": self.completions})()


def _classification(
    category: str = "resources",
    title: str = "Knowledge Systems",
) -> Classification:
    return Classification(
        category=category,
        tags=["knowledge", "learning", "notes"],
        summary="A note about organizing personal knowledge.",
        title=title,
    )


def _response(category: str = "resources", title: str = "Knowledge Systems") -> str:
    return json.dumps(
        {
            "category": category,
            "tags": ["knowledge", "learning", "notes"],
            "summary": "A note about organizing personal knowledge.",
            "title": title,
        }
    )


class ClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.raw_dir = self.root / "raw"
        self.wiki_dir = self.root / "wiki"
        self.raw_note = RawNote(
            id="c0ffee12",
            captured_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            source_type="note",
            source_ref=None,
            body="An original body with exact text.\nSecond line.\n",
            processed=False,
            title="Original title",
        )
        self.raw_path = write_raw_note(self.raw_note, self.raw_dir)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_classify_content_uses_groq_json_mode_and_normalizes_values(self) -> None:
        client = _FakeGroq(
            [
                json.dumps(
                    {
                        "category": "AREAS",
                        "tags": ["#Daily Habits", " Health ", "reflection", "health"],
                        "summary": "  Maintain   a useful routine. ",
                        "title": "Daily   Routines",
                    }
                )
            ]
        )

        result = classify_content("Original note.", "My title", client=client)

        self.assertEqual(result.category, "areas")
        self.assertEqual(result.tags, ["daily-habits", "health", "reflection"])
        self.assertEqual(result.summary, "Maintain a useful routine.")
        self.assertEqual(result.title, "Daily Routines")
        call = client.chat.completions.calls[0]
        self.assertEqual(call["temperature"], 0.2)
        self.assertEqual(call["response_format"], {"type": "json_object"})
        self.assertIn("Original note.", call["messages"][1]["content"])

    def test_malformed_json_is_retried_once(self) -> None:
        client = _FakeGroq(["not json", _response()])

        result = classify_content("Original note.", client=client)

        self.assertEqual(result.category, "resources")
        self.assertEqual(len(client.chat.completions.calls), 2)

    def test_fenced_json_and_invalid_category_default_to_resources(self) -> None:
        fenced = f"```json\n{_response('not-a-para-category')}\n```"

        with self.assertLogs("lib.llm", level="WARNING") as logs:
            result = _parse_response(fenced)

        self.assertEqual(result.category, "resources")
        self.assertTrue(any("invalid category" in message for message in logs.output))

    def test_wiki_writer_preserves_original_body_and_writes_para_frontmatter(self) -> None:
        wiki_note = write_wiki_note(
            self.raw_note,
            _classification(),
            self.raw_path,
            self.wiki_dir,
        )

        saved = read_wiki_note(wiki_note.path)
        self.assertEqual(wiki_note.path.parent.name, "resources")
        self.assertEqual(saved.id, self.raw_note.id)
        self.assertEqual(saved.tags, ["knowledge", "learning", "notes"])
        self.assertEqual(saved.body, f"# {saved.title}\n\n{saved.summary}\n\n{self.raw_note.body}")
        self.assertIn("knowledge-systems.md", wiki_note.path.name)

    def test_slug_collision_uses_id_suffix_and_force_update_keeps_single_note(self) -> None:
        first = RawNote(
            id="aabbccdd",
            captured_at=self.raw_note.captured_at,
            source_type="note",
            source_ref=None,
            body="Another note.",
            processed=False,
            title=self.raw_note.title,
        )
        first_raw_path = write_raw_note(first, self.raw_dir)
        write_wiki_note(self.raw_note, _classification(), self.raw_path, self.wiki_dir)
        collided = write_wiki_note(first, _classification(), first_raw_path, self.wiki_dir)
        self.assertTrue(collided.path.stem.endswith("-aabb"))

        updated = write_wiki_note(
            first,
            _classification("areas", "Ongoing Responsibility"),
            first_raw_path,
            self.wiki_dir,
        )
        self.assertEqual(updated.path.parent.name, "areas")
        self.assertEqual(len(list(self.wiki_dir.glob("*/*.md"))), 2)
        self.assertFalse(collided.path.exists())

    def test_classify_file_writes_wiki_then_marks_raw_processed(self) -> None:
        client = _FakeGroq([_response()])

        wiki_note = classify_file(
            self.raw_path,
            client=client,
            raw_dir=self.raw_dir,
            wiki_dir=self.wiki_dir,
        )

        self.assertIsNotNone(wiki_note)
        updated_raw = read_raw_note(self.raw_path)
        self.assertTrue(updated_raw.processed)
        self.assertEqual(updated_raw.body, self.raw_note.body)
        self.assertEqual(read_wiki_note(wiki_note.path).body.split("\n\n", 2)[2], self.raw_note.body)

    def test_existing_wiki_is_skipped_and_unprocessed_raw_is_reconciled(self) -> None:
        write_wiki_note(self.raw_note, _classification(), self.raw_path, self.wiki_dir)
        client = _FakeGroq([])

        result = classify_file(
            self.raw_path,
            client=client,
            raw_dir=self.raw_dir,
            wiki_dir=self.wiki_dir,
        )

        self.assertIsNone(result)
        self.assertTrue(read_raw_note(self.raw_path).processed)
        self.assertEqual(client.chat.completions.calls, [])

    def test_force_reclassifies_existing_note(self) -> None:
        write_wiki_note(self.raw_note, _classification(), self.raw_path, self.wiki_dir)
        client = _FakeGroq([_response("projects", "New Project")])

        result = classify_file(
            self.raw_path,
            client=client,
            raw_dir=self.raw_dir,
            wiki_dir=self.wiki_dir,
            force=True,
        )

        self.assertEqual(result.category, "projects")
        self.assertEqual(len(list(self.wiki_dir.glob("*/*.md"))), 1)

    def test_missing_api_key_exits_with_status_two(self) -> None:
        with patch("classify.groq_client", side_effect=ValueError("GROQ_API_KEY is required")):
            with self.assertRaises(SystemExit) as raised:
                main(["--all"])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
