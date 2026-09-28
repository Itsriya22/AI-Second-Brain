"""Capture notes, web links, and local files into the raw-notes folder."""

from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
import shutil
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from pypdf.errors import PdfReadError

from config import RAW_DIR
from lib.ids import new_id
from lib.io import write_raw_note
from lib.models import RawNote

_MAX_LINK_BYTES = 2 * 1024 * 1024
_MAX_LINK_TEXT_CHARS = 12_000
_LINK_TIMEOUT_SECONDS = 10.0
_LINK_USER_AGENT = "SecondSelf/1.0 (+https://github.com/)"
_TIMEZONE = ZoneInfo("Asia/Kolkata")


class LinkFetchError(Exception):
    """Raised when a fetched page is unusable or exceeds the size limit."""


class _PageTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.description = ""
        self.text_parts: list[str] = []
        self._in_title = False
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = attributes.get("name", "").lower()
            property_name = attributes.get("property", "").lower()
            if name == "description" or property_name == "og:description":
                self.description = attributes.get("content", "").strip()
        elif tag in {"script", "style", "noscript"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag in {"script", "style", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if not self._hidden_depth:
            self.text_parts.append(data)


def _parse_page(content: str) -> tuple[str | None, str]:
    parser = _PageTextParser()
    parser.feed(content)
    title = " ".join(" ".join(parser.title_parts).split()) or None
    description = " ".join(parser.description.split())
    readable_text = " ".join(" ".join(parser.text_parts).split())
    sections = []
    if title:
        sections.append(f"Title: {title}")
    if description:
        sections.append(f"Description: {description}")
    if readable_text:
        sections.append(f"Content: {readable_text[:_MAX_LINK_TEXT_CHARS]}")
    return title, "\n\n".join(sections)


def _fetch_link(url: str) -> tuple[str | None, str]:
    with httpx.Client(
        timeout=_LINK_TIMEOUT_SECONDS,
        follow_redirects=True,
        max_redirects=5,
        headers={"User-Agent": _LINK_USER_AGENT},
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            total_bytes = 0
            for chunk in response.iter_bytes():
                total_bytes += len(chunk)
                if total_bytes > _MAX_LINK_BYTES:
                    raise LinkFetchError(f"response exceeds {_MAX_LINK_BYTES} bytes")
                chunks.append(chunk)

            content = b"".join(chunks)
            content_type = response.headers.get("content-type", "").lower()
            if "html" in content_type or not content_type:
                encoding = response.encoding or "utf-8"
                return _parse_page(content.decode(encoding, errors="replace"))
            text = content.decode(response.encoding or "utf-8", errors="replace")
            return None, f"Content: {text[:_MAX_LINK_TEXT_CHARS]}"


def ingest(kind: str, payload: str, raw_dir: Path = RAW_DIR) -> RawNote:
    """Persist one note, link, or file capture and return its metadata."""
    if kind not in {"note", "link", "file"}:
        raise ValueError("kind must be 'note', 'link', or 'file'")
    if not payload or not payload.strip():
        raise ValueError(f"{kind} payload must not be empty")

    source = Path(payload).expanduser() if kind == "file" else None
    if source is not None and not source.is_file():
        raise FileNotFoundError(f"Capture file does not exist: {source}")
    if kind == "link":
        parsed_url = urlsplit(payload)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("Link must be an absolute http:// or https:// URL")

    captured_at = datetime.now(_TIMEZONE).isoformat(timespec="seconds")
    source_type = kind
    source_ref: str | None = None
    title: str | None = None
    original_body: str | None = None

    if kind == "note":
        body = payload
    elif kind == "link":
        source_ref = payload
        try:
            title, body = _fetch_link(payload)
        except (httpx.HTTPError, LinkFetchError, UnicodeError) as exc:
            body = f"URL: {payload}\n\nLink unfetched: {exc}"
    else:
        assert source is not None
        suffix = source.suffix.lower()
        if suffix in {".txt", ".md"}:
            try:
                original_body = source.read_text(encoding="utf-8")
            except UnicodeError as exc:
                original_body = f"Original file: {source.name}\n\nText extraction failed: {exc}"
        elif suffix == ".pdf":
            from pypdf import PdfReader

            try:
                original_body = "\n\n".join(
                    page.extract_text() or "" for page in PdfReader(source).pages
                ).strip()
            except (OSError, PdfReadError, ValueError) as exc:
                original_body = f"Original file: {source.name}\n\nPDF extraction failed: {exc}"
        else:
            original_body = f"Original file: {source.name}\n\nBinary not extracted."
        body = original_body or f"Original file: {source.name}\n\nNo extractable text found."

    raw_dir.mkdir(parents=True, exist_ok=True)
    for _ in range(100):
        note_id = new_id(raw_dir)
        note = RawNote(
            id=note_id,
            captured_at=captured_at,
            source_type=source_type,
            source_ref=source_ref,
            body=body,
            processed=False,
            title=title or (source.stem if source is not None else None),
        )
        original_path: Path | None = None
        original_created = False
        try:
            if source is not None:
                originals_dir = raw_dir / "originals"
                originals_dir.mkdir(parents=True, exist_ok=True)
                original_path = originals_dir / f"{note_id}{source.suffix.lower()}"
                with source.open("rb") as original, original_path.open("xb") as copied:
                    original_created = True
                    shutil.copyfileobj(original, copied)
                note.source_ref = original_path.relative_to(raw_dir).as_posix()
            write_raw_note(note, raw_dir)
            return note
        except FileExistsError:
            if original_path is not None and original_created:
                original_path.unlink(missing_ok=True)
        except OSError:
            if original_path is not None and original_created:
                original_path.unlink(missing_ok=True)
            raise
    raise RuntimeError("Could not save capture after 100 unique-ID attempts.")
