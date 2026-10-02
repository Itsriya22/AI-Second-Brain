"""Local sentence-transformer embeddings with a content-addressed disk cache."""

from hashlib import sha256
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from config import DATA_DIR, EMBED_MODEL

_CACHE_PATH = DATA_DIR / "embeddings.npz"
_METADATA_PATH = DATA_DIR / "embedding_meta.json"
_EMBED_TEXT_LIMIT = 2_000
_GENERATED_RELATED_SECTION = re.compile(
    r"\n## Related\n\n<!-- secondself:related:start -->.*?<!-- secondself:related:end -->\s*\Z",
    re.DOTALL,
)


class Encoder(Protocol):
    def encode(self, sentences: list[str], **kwargs: object) -> NDArray[np.float32]: ...


@lru_cache(maxsize=1)
def get_encoder() -> Encoder:
    """Load and reuse one CPU sentence-transformer model per process."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBED_MODEL, device="cpu")


def embedding_text(title: str, summary: str, body: str) -> str:
    """Compose the searchable text and keep it within the model's input budget."""
    body = _GENERATED_RELATED_SECTION.sub("", body)
    return f"{title}\n{summary}\n{body.rstrip()}"[:_EMBED_TEXT_LIMIT]


def _atomic_json(path: Path, data: dict[str, object]) -> None:
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
            json.dump(data, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _write_cache(
    cache_path: Path,
    metadata_path: Path,
    note_ids: list[str],
    hashes: dict[str, str],
    vectors: NDArray[np.float32],
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=cache_path.parent,
            prefix=f".{cache_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            np.savez_compressed(
                temporary_file,
                ids=np.asarray(note_ids, dtype=np.str_),
                embeddings=vectors.astype(np.float32, copy=False),
            )
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, cache_path)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    _atomic_json(
        metadata_path,
        {"model": EMBED_MODEL, "hashes": hashes},
    )


def _load_cache(
    cache_path: Path,
    metadata_path: Path,
) -> tuple[dict[str, NDArray[np.float32]], dict[str, str]]:
    if not cache_path.exists() and not metadata_path.exists():
        return {}, {}
    if not cache_path.is_file() or not metadata_path.is_file():
        raise ValueError("Embedding cache is incomplete; remove both cache files and retry.")

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        with np.load(cache_path, allow_pickle=False) as cached:
            ids = cached["ids"].tolist()
            vectors = cached["embeddings"]
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read embedding cache: {exc}") from exc

    if metadata.get("model") != EMBED_MODEL:
        return {}, {}
    hashes = metadata.get("hashes")
    if not isinstance(hashes, dict):
        raise ValueError("Embedding cache metadata is missing its hashes mapping.")
    if vectors.ndim != 2 or vectors.shape[0] != len(ids):
        raise ValueError("Embedding cache has an invalid vector shape.")
    if not np.isfinite(vectors).all():
        raise ValueError("Embedding cache contains non-finite vectors.")
    return (
        {note_id: vectors[index].astype(np.float32, copy=False) for index, note_id in enumerate(ids)},
        {str(note_id): str(text_hash) for note_id, text_hash in hashes.items()},
    )


def embed_notes(
    note_texts: dict[str, str],
    *,
    model: Encoder | None = None,
    cache_path: Path = _CACHE_PATH,
    metadata_path: Path = _METADATA_PATH,
) -> dict[str, NDArray[np.float32]]:
    """Return normalized embeddings, reusing vectors whose content hashes match."""
    hashes = {
        note_id: sha256(text.encode("utf-8")).hexdigest()
        for note_id, text in note_texts.items()
    }
    cached_vectors, cached_hashes = _load_cache(cache_path, metadata_path)
    vectors = {
        note_id: cached_vectors[note_id]
        for note_id in note_texts
        if note_id in cached_vectors and cached_hashes.get(note_id) == hashes[note_id]
    }
    missing_ids = [note_id for note_id in note_texts if note_id not in vectors]

    if missing_ids:
        if model is None:
            model = get_encoder()
        encoded = np.asarray(
            model.encode(
                [note_texts[note_id] for note_id in missing_ids],
                convert_to_numpy=True,
                normalize_embeddings=False,
                show_progress_bar=False,
            ),
            dtype=np.float32,
        )
        if encoded.ndim != 2 or encoded.shape[0] != len(missing_ids):
            raise ValueError("Embedding model returned an invalid vector matrix.")
        if not np.isfinite(encoded).all():
            raise ValueError("Embedding model returned non-finite values.")
        for note_id, vector in zip(missing_ids, encoded, strict=True):
            vectors[note_id] = vector

    dimensions = {vector.shape[0] for vector in vectors.values()}
    if len(dimensions) > 1:
        raise ValueError("Embedding cache contains vectors with inconsistent dimensions.")
    normalized: dict[str, NDArray[np.float32]] = {}
    for note_id, vector in vectors.items():
        norm = float(np.linalg.norm(vector))
        normalized[note_id] = vector / norm if norm > 0 else vector

    if note_texts:
        ordered_ids = list(note_texts)
        matrix = np.stack([normalized[note_id] for note_id in ordered_ids])
        _write_cache(cache_path, metadata_path, ordered_ids, hashes, matrix)
    else:
        _write_cache(
            cache_path,
            metadata_path,
            [],
            {},
            np.empty((0, 0), dtype=np.float32),
        )
    return normalized
