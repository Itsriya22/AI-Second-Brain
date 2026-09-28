"""Capture a note, web link, or file into the raw-notes folder."""

import argparse

from config import RAW_DIR
from lib.ingest import ingest
from lib.io import raw_note_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="kind", required=True)
    for kind, help_text in (
        ("note", "Capture a text note"),
        ("link", "Capture a web page"),
        ("file", "Capture a local file"),
    ):
        subparser = subparsers.add_parser(kind, help=help_text)
        subparser.add_argument("payload", help="Text, URL, or file path")

    args = parser.parse_args(argv)
    try:
        note = ingest(args.kind, args.payload)
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    output_path = raw_note_path(note, RAW_DIR)
    output_path = output_path.relative_to(RAW_DIR.parent)
    print(f"Captured {args.kind}: {output_path} (id: {note.id})")


if __name__ == "__main__":
    main()
