"""Build and export a graph from PARA wiki notes."""

from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile

from config import ROOT_DIR, WIKI_DIR
from lib.models import Graph
from lib.wiki import read_wiki_note

_RELATED_SECTION = re.compile(
    r"\n## Related\n\n<!-- secondself:related:start -->.*?<!-- secondself:related:end -->\s*\Z",
    re.DOTALL,
)
_PREVIEW_LIMIT = 400


def _preview(body: str, title: str, summary: str) -> str:
    body = _RELATED_SECTION.sub("", body).strip()
    if body.startswith(f"# {title}"):
        body = body[len(title) + 2 :].lstrip()
    if body.startswith(summary):
        body = body[len(summary) :].lstrip()
    preview = " ".join(body.split())
    if len(preview) > _PREVIEW_LIMIT:
        preview = preview[: _PREVIEW_LIMIT - 3].rstrip() + "..."
    return preview


def build_graph(
    wiki_dir: Path = WIKI_DIR,
    *,
    root_dir: Path = ROOT_DIR,
    generated_at: str | None = None,
) -> Graph:
    """Read wiki notes into unique nodes and undirected, non-dangling edges."""
    notes = [
        read_wiki_note(path)
        for path in sorted(wiki_dir.glob("*/*.md"))
    ]
    note_by_id = {note.id: note for note in notes}
    if len(note_by_id) != len(notes):
        raise ValueError("Wiki corpus contains duplicate note IDs.")

    nodes: list[dict[str, str | list[str]]] = []
    for note in notes:
        try:
            relative_path = note.path.resolve().relative_to(root_dir.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError(f"Wiki note is outside the project root: {note.path}") from exc
        nodes.append(
            {
                "id": note.id,
                "label": note.title,
                "category": note.category,
                "tags": note.tags,
                "summary": note.summary,
                "path": relative_path,
                "preview": _preview(note.body, note.title, note.summary),
            }
        )

    edge_pairs: set[tuple[str, str]] = set()
    for note in notes:
        for linked_id in note.linked_ids:
            if linked_id == note.id or linked_id not in note_by_id:
                continue
            edge_pairs.add(tuple(sorted((note.id, linked_id))))
    edges: list[dict[str, str | float]] = [
        {"from": source, "to": target, "weight": 1.0, "reason": "embedding"}
        for source, target in sorted(edge_pairs)
    ]
    return Graph(
        nodes=nodes,
        edges=edges,
        generated_at=generated_at or datetime.now().astimezone().isoformat(timespec="seconds"),
    )


def export_graph(
    graph: Graph,
    path: Path,
) -> Path:
    """Write a non-empty graph as formatted JSON using an atomic replacement."""
    if not graph.nodes:
        raise ValueError("Cannot export graph: wiki contains zero notes.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(
                {
                    "generated_at": graph.generated_at,
                    "nodes": graph.nodes,
                    "edges": graph.edges,
                },
                temporary_file,
                ensure_ascii=False,
                indent=2,
            )
            temporary_file.write("\n")
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return path


def export(
    path: Path,
    wiki_dir: Path = WIKI_DIR,
    *,
    root_dir: Path = ROOT_DIR,
) -> Graph:
    """Build and export a graph, returning the in-memory representation."""
    graph = build_graph(wiki_dir, root_dir=root_dir)
    export_graph(graph, path)
    return graph
