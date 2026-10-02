"""Project paths and model defaults."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
RAW_DIR = ROOT_DIR / "raw"
WIKI_DIR = ROOT_DIR / "wiki"
DATA_DIR = ROOT_DIR / "data"
GRAPH_PATH = ROOT_DIR / "graph.json"

GROQ_MODEL = "openai/gpt-oss-20b"
EMBED_MODEL = "all-MiniLM-L6-v2"
SIMILARITY_THRESHOLD = 0.5
MAX_LINKS_PER_NOTE = 8
ASK_TOP_K = 5
MAX_CONTEXT_CHARS = 12_000
