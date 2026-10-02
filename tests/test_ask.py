"""Tests for grounded retrieval-augmented Q&A."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from ask import ask
from lib.models import Classification, RawNote
from lib.wiki import write_wiki_note


class FakeEncoder:
    def encode(self, sentences: list[str], **kwargs: object) -> np.ndarray:
        vectors = []
        for sentence in sentences:
            if sentence == "What project am I working on?":
                vectors.append([1.0, 0.0])
            elif sentence.startswith("Career Planning"):
                vectors.append([0.98, 0.2])
            elif sentence.startswith("Cooking Reference"):
                vectors.append([0.0, 1.0])
            else:
                vectors.append([1.0, 0.0])
        return np.asarray(vectors, dtype=np.float32)


class FakeCompletions:
    def __init__(self, answer: str = "Your notes say you are planning your career.") -> None:
        self.answer = answer
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object):
        self.calls.append(kwargs)
        message = type("Message", (), {"content": self.answer})()
        choice = type("Choice", (), {"message": message})()
        return type("Completion", (), {"choices": [choice]})()


class FakeGroq:
    def __init__(self, answer: str = "Your notes say you are planning your career.") -> None:
        self.completions = FakeCompletions(answer)
        self.chat = type("Chat", (), {"completions": self.completions})()


class AskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.wiki_dir = self.root / "wiki"
        for note_id, title, category, body in (
            (
                "a1b2c3d4",
                "Career Planning",
                "projects",
                "I am planning the next step in my career.",
            ),
            (
                "b1b2c3d4",
                "Cooking Reference",
                "resources",
                "A recipe collection for weekend meals.",
            ),
        ):
            raw_path = self.root / "raw" / f"{note_id}.md"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text("source", encoding="utf-8")
            write_wiki_note(
                RawNote(
                    id=note_id,
                    captured_at="2026-09-30T12:00:00+05:30",
                    source_type="note",
                    source_ref=None,
                    body=body,
                    processed=True,
                ),
                Classification(
                    category=category,
                    tags=["planning", "personal", "notes"],
                    summary=f"Summary of {title}.",
                    title=title,
                ),
                raw_path,
                self.wiki_dir,
            )
        self.cache_path = self.root / "data" / "embeddings.npz"
        self.metadata_path = self.root / "data" / "embedding_meta.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _ask(self, question: str = "What project am I working on?", *, answer: str | None = None):
        return ask(
            question,
            client=FakeGroq(answer or "Your notes say you are planning your career."),
            model=FakeEncoder(),
            wiki_dir=self.wiki_dir,
            root_dir=self.root,
            cache_path=self.cache_path,
            metadata_path=self.metadata_path,
        )

    def test_retrieves_and_returns_sources_with_grounded_answer(self) -> None:
        client = FakeGroq()
        result = ask(
            "What project am I working on?",
            client=client,
            model=FakeEncoder(),
            wiki_dir=self.wiki_dir,
            root_dir=self.root,
            cache_path=self.cache_path,
            metadata_path=self.metadata_path,
        )

        self.assertEqual(result["answer"], "Your notes say you are planning your career.")
        self.assertIsNone(result["error"])
        self.assertEqual(result["sources"][0]["id"], "a1b2c3d4")
        self.assertEqual(result["sources"][0]["path"], "wiki/projects/career-planning.md")
        self.assertEqual(set(result["sources"][0]), {"id", "title", "path", "score"})
        request = client.chat.completions.calls[0]
        self.assertEqual(request["temperature"], 0.2)
        context = request["messages"][1]["content"].partition(
            "Use only the note context below.\n\n"
        )[2]
        payload = [json.loads(block) for block in context.split("\n\n---\n\n")]
        self.assertEqual(payload[0]["id"], "a1b2c3d4")
        self.assertIn("I am planning the next step", payload[0]["body"])

    def test_missing_api_key_returns_error_without_loading_model(self) -> None:
        with patch("ask.groq_client", side_effect=ValueError("GROQ_API_KEY is required")):
            result = ask(
                "Any question?",
                client=None,
                model=None,
                wiki_dir=self.wiki_dir,
                root_dir=self.root,
                cache_path=self.cache_path,
                metadata_path=self.metadata_path,
            )

        self.assertIsInstance(result["error"], str)
        self.assertIn("GROQ_API_KEY", result["error"])
        self.assertEqual(result["sources"], [])

    def test_empty_wiki_returns_explicit_no_knowledge_answer(self) -> None:
        result = ask(
            "What do I know?",
            wiki_dir=self.root / "empty",
            root_dir=self.root,
        )

        self.assertIn("don't know from the brain", result["answer"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["sources"], [])

    def test_invalid_question_is_reported_without_calling_groq(self) -> None:
        for question in (" ", "q" * 2_001):
            with self.subTest(question_length=len(question)):
                result = self._ask(question)
                self.assertEqual(result["sources"], [])
                self.assertIsInstance(result["error"], str)

    def test_groq_answer_error_is_returned_for_ui(self) -> None:
        class FailedGroq:
            class Completions:
                def create(self, **kwargs: object):
                    raise OSError("network unavailable")

            chat = type("Chat", (), {"completions": Completions()})()

        result = ask(
            "What project am I working on?",
            client=FailedGroq(),
            model=FakeEncoder(),
            wiki_dir=self.wiki_dir,
            root_dir=self.root,
            cache_path=self.cache_path,
            metadata_path=self.metadata_path,
        )

        self.assertEqual(result["answer"], "")
        self.assertIn("network unavailable", result["error"])

    def test_context_budget_truncates_note_body_without_breaking_json(self) -> None:
        career_path = self.wiki_dir / "projects" / "career-planning.md"
        career_path.write_text(
            career_path.read_text(encoding="utf-8") + ("Long note body. " * 500),
            encoding="utf-8",
        )
        client = FakeGroq()

        with patch("ask.MAX_CONTEXT_CHARS", 600):
            result = ask(
                "What project am I working on?",
                client=client,
                model=FakeEncoder(),
                wiki_dir=self.wiki_dir,
                root_dir=self.root,
                cache_path=self.cache_path,
                metadata_path=self.metadata_path,
            )

        context = client.chat.completions.calls[0]["messages"][1]["content"].partition(
            "Use only the note context below.\n\n"
        )[2]
        blocks = context.split("\n\n---\n\n")
        parsed_blocks = [json.loads(block) for block in blocks]
        self.assertLessEqual(len(context), 600)
        self.assertEqual(len(parsed_blocks), 1)
        self.assertLess(len(parsed_blocks[0]["body"]), 8_000)
        self.assertEqual(len(result["sources"]), 1)


if __name__ == "__main__":
    unittest.main()
