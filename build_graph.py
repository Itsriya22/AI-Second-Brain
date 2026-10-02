"""Export PARA wiki notes and their links as graph.json."""

import argparse
from pathlib import Path

from config import GRAPH_PATH, ROOT_DIR, WIKI_DIR
from lib.graph import export


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wiki-dir", type=Path, default=WIKI_DIR)
    parser.add_argument("--output", type=Path, default=GRAPH_PATH)
    args = parser.parse_args(argv)
    try:
        graph = export(args.output, args.wiki_dir, root_dir=ROOT_DIR)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{parser.prog}: error: {exc}\n")
    print(f"Exported {len(graph.nodes)} node(s) and {len(graph.edges)} edge(s) to {args.output}.")


if __name__ == "__main__":
    main()
