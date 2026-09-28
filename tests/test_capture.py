"""Tests for raw capture persistence and metadata."""

from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from lib.ids import new_id
from lib.ingest import LinkFetchError, _fetch_link, ingest
from lib.io import read_raw_note, raw_note_path, write_raw_note
from lib.models import RawNote


class CaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.raw_dir = Path(self.temporary_directory.name) / "raw"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_note_capture_round_trips_frontmatter_and_body(self) -> None:
        note = ingest("note", "A genuine thought.\n", self.raw_dir)
        path = raw_note_path(note, self.raw_dir)
        loaded = read_raw_note(path)

        self.assertEqual(loaded, note)
        self.assertEqual(path.name, f"{datetime.fromisoformat(note.captured_at):%Y%m%dT%H%M%S}_{note.id}.md")
        self.assertFalse(loaded.processed)
        self.assertIsNotNone(datetime.fromisoformat(loaded.captured_at).tzinfo)

    def test_id_generation_skips_existing_capture_and_original(self) -> None:
        (self.raw_dir / "originals").mkdir(parents=True)
        (self.raw_dir / "20260928T141530_deadbeef.md").touch()
        (self.raw_dir / "originals" / "feedface.pdf").touch()
        with patch("lib.ids.secrets.token_hex", side_effect=["deadbeef", "feedface", "cafebabe"]):
            self.assertEqual(new_id(self.raw_dir), "cafebabe")

    def test_write_does_not_overwrite_an_existing_id(self) -> None:
        note = RawNote("deadbeef", "2026-09-28T14:15:30+05:30", "note", None, "first", False)
        path = write_raw_note(note, self.raw_dir)
        with self.assertRaises(FileExistsError):
            write_raw_note(note, self.raw_dir)
        self.assertEqual(read_raw_note(path).body, "first")

    def test_file_capture_copies_original_and_extracts_text(self) -> None:
        source = Path(self.temporary_directory.name) / "source.md"
        source.write_text("# Study\nReal course notes.\n", encoding="utf-8")

        note = ingest("file", str(source), self.raw_dir)

        self.assertEqual(note.source_ref, f"originals/{note.id}.md")
        self.assertEqual((self.raw_dir / note.source_ref).read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
        self.assertEqual(read_raw_note(raw_note_path(note, self.raw_dir)).body, "# Study\nReal course notes.\n")

    def test_binary_file_capture_keeps_original_and_explains_unextracted_body(self) -> None:
        source = Path(self.temporary_directory.name) / "source.bin"
        source.write_bytes(b"\x00\x01")

        note = ingest("file", str(source), self.raw_dir)

        self.assertEqual((self.raw_dir / note.source_ref).read_bytes(), b"\x00\x01")
        self.assertIn("Binary not extracted", note.body)

    def test_failed_link_fetch_still_persists_url(self) -> None:
        with patch("lib.ingest._fetch_link", side_effect=httpx.ConnectError("offline")):
            note = ingest("link", "https://example.com/article", self.raw_dir)

        self.assertEqual(note.source_ref, "https://example.com/article")
        self.assertIn("https://example.com/article", note.body)
        self.assertIn("Link unfetched", note.body)
        self.assertEqual(read_raw_note(raw_note_path(note, self.raw_dir)), note)

    def test_rejects_invalid_input_without_creating_a_capture(self) -> None:
        for kind, payload in (("note", " "), ("link", "file:///tmp/example"), ("file", "missing.pdf")):
            with self.subTest(kind=kind, payload=payload):
                with self.assertRaises((ValueError, FileNotFoundError)):
                    ingest(kind, payload, self.raw_dir)
        self.assertFalse(self.raw_dir.exists())

    def test_link_page_parser_extracts_title_description_and_visible_text(self) -> None:
        class FakeResponse:
            headers = {"content-type": "text/html; charset=utf-8"}
            encoding = "utf-8"

            def raise_for_status(self) -> None:
                return None

            def iter_bytes(self):
                yield b'<html><head><title>Example Site</title><meta name="description" content="A description"></head><body><p>Visible text</p><script>secret()</script></body></html>'

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        class FakeClient:
            def __init__(self, **kwargs):
                self.options = kwargs

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def stream(self, method, url):
                self.request = (method, url)
                return FakeResponse()

        with patch("lib.ingest.httpx.Client", FakeClient):
            title, body = _fetch_link("https://example.com")

        self.assertEqual(title, "Example Site")
        self.assertIn("Description: A description", body)
        self.assertIn("Visible text", body)
        self.assertNotIn("secret()", body)

    def test_link_fetch_rejects_oversized_body(self) -> None:
        class FakeResponse:
            headers = {"content-type": "text/html"}
            encoding = "utf-8"

            def raise_for_status(self) -> None:
                return None

            def iter_bytes(self):
                yield b"x" * (2 * 1024 * 1024 + 1)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def stream(self, method, url):
                return FakeResponse()

        with patch("lib.ingest.httpx.Client", FakeClient):
            with self.assertRaises(LinkFetchError):
                _fetch_link("https://example.com")


if __name__ == "__main__":
    unittest.main()
