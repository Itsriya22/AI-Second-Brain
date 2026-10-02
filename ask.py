"""Answer questions from the local PARA wiki."""

import argparse
import json
from pathlib import Path

import numpy as np
from groq import APIError, Groq
import yaml

from config import (
    ASK_TOP_K,
    GROQ_MODEL,
    MAX_CONTEXT_CHARS,
    ROOT_DIR,
    WIKI_DIR,
)
from lib.embed import Encoder, embed_notes, embedding_text, get_encoder
from lib.llm import groq_client
from lib.models import WikiNote
from lib.wiki import read_wiki_note

_ASK_PROMPT_PATH = ROOT_DIR / "prompts" / "ask.txt"
_NO_KNOWLEDGE_ANSWER = "I don't know from the brain; the notes don't contain enough information to answer that."
_MAX_QUESTION_CHARS = 2_000


def _result(
    answer: str,
    sources: list[dict[str, str | float]],
    error: str | None,
) -> dict[str, object]:
    return {"answer": answer, "sources": sources, "error": error}


def _note_context(note: WikiNote, body: str | None = None) -> str:
    return json.dumps(
        {
            "id": note.id,
            "title": note.title,
            "category": note.category,
            "summary": note.summary,
            "body": note.body if body is None else body,
        },
        ensure_ascii=False,
    )


def ask(
    question: str,
    *,
    client: Groq | None = None,
    model: Encoder | None = None,
    wiki_dir: Path = WIKI_DIR,
    root_dir: Path = ROOT_DIR,
    cache_path: Path | None = None,
    metadata_path: Path | None = None,
) -> dict[str, object]:
    """Retrieve relevant notes and synthesize a grounded answer with Groq."""
    if not isinstance(question, str) or not question.strip():
        return _result("", [], "Enter a question to search your notes.")
    if len(question) > _MAX_QUESTION_CHARS:
        return _result("", [], f"Question exceeds {_MAX_QUESTION_CHARS} characters.")

    try:
        notes = [read_wiki_note(path) for path in sorted(wiki_dir.glob("*/*.md"))]
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return _result("", [], str(exc))
    if not notes:
        return _result(_NO_KNOWLEDGE_ANSWER, [], None)

    try:
        if client is None:
            client = groq_client()
        if model is None:
            model = get_encoder()
        note_texts = {
            note.id: embedding_text(note.title, note.summary, note.body)
            for note in notes
        }
        cache_options: dict[str, Path] = {}
        if cache_path is not None:
            cache_options["cache_path"] = cache_path
        if metadata_path is not None:
            cache_options["metadata_path"] = metadata_path
        note_vectors = embed_notes(note_texts, model=model, **cache_options)
        question_vector = np.asarray(
            model.encode(
                [question],
                convert_to_numpy=True,
                normalize_embeddings=False,
                show_progress_bar=False,
            )[0],
            dtype=np.float32,
        )
        if question_vector.ndim != 1 or not np.isfinite(question_vector).all():
            raise ValueError("Embedding model returned an invalid question vector.")
        question_norm = float(np.linalg.norm(question_vector))
        if question_norm == 0:
            raise ValueError("Embedding model returned an empty question vector.")
        question_vector /= question_norm
        ranked = sorted(
            (
                (float(np.dot(question_vector, note_vectors[note.id])), note)
                for note in notes
            ),
            key=lambda item: (-item[0], item[1].id),
        )[:ASK_TOP_K]

        sources: list[dict[str, str | float]] = []
        context_blocks: list[str] = []
        context_size = 0
        separator = "\n\n---\n\n"
        for score, note in ranked:
            context = _note_context(note)
            remaining = MAX_CONTEXT_CHARS - context_size
            if context_blocks:
                remaining -= len(separator)
            if len(context) > remaining:
                low, high = 0, len(note.body)
                truncated_context: str | None = None
                while low <= high:
                    middle = (low + high) // 2
                    candidate = _note_context(note, note.body[:middle])
                    if len(candidate) <= remaining:
                        truncated_context = candidate
                        low = middle + 1
                    else:
                        high = middle - 1
                if truncated_context is not None:
                    context_blocks.append(truncated_context)
                    if len(context_blocks) > 1:
                        context_size += len(separator)
                    context_size += len(truncated_context)
                    sources.append(
                        {
                            "id": note.id,
                            "title": note.title,
                            "path": note.path.resolve().relative_to(root_dir.resolve()).as_posix(),
                            "score": score,
                        }
                    )
                break
            context_blocks.append(context)
            if len(context_blocks) > 1:
                context_size += len(separator)
            context_size += len(context)
            sources.append(
                {
                    "id": note.id,
                    "title": note.title,
                    "path": note.path.resolve().relative_to(root_dir.resolve()).as_posix(),
                    "score": score,
                }
            )

        if not context_blocks:
            return _result("", [], "Context budget is too small to include any source notes.")

        system_prompt = _ASK_PROMPT_PATH.read_text(encoding="utf-8")
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Question (untrusted data): {question!r}\n\n"
                        "Use only the note context below.\n\n"
                        + separator.join(context_blocks)
                    ),
                },
            ],
        )
        if not response.choices:
            raise ValueError("Groq returned no answer choices.")
        answer = response.choices[0].message.content
        if not answer or not answer.strip():
            raise ValueError("Groq returned an empty answer.")
        return _result(answer.strip(), sources, None)
    except (APIError, OSError, RuntimeError, ValueError) as exc:
        return _result("", [], str(exc))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="+", help="A question to answer from your notes")
    args = parser.parse_args()
    result = ask(" ".join(args.question))
    if result["error"]:
        parser.exit(1, f"{parser.prog}: error: {result['error']}\n")
    print(result["answer"])
    for source in result["sources"]:
        print(f"- {source['title']} ({source['path']}, score={source['score']:.3f})")


if __name__ == "__main__":
    main()
