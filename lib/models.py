"""Domain data structures shared by the pipeline."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RawNote:
    id: str
    captured_at: str
    source_type: str
    source_ref: str | None
    body: str
    processed: bool
    title: str | None = None


@dataclass
class Classification:
    category: str
    tags: list[str]
    summary: str
    title: str


@dataclass
class WikiNote:
    id: str
    category: str
    tags: list[str]
    summary: str
    title: str
    body: str
    linked_ids: list[str]
    path: Path


@dataclass
class Graph:
    nodes: list[dict[str, str | list[str]]]
    edges: list[dict[str, str | float]]
    generated_at: str


@dataclass
class AskResult:
    answer: str
    sources: list[dict[str, object]]
    error: str | None
