# SecondSelf — Architecture

**Product:** a personal knowledge system that captures anything, classifies it, links it, visualizes it as a live graph, and answers questions from *your* notes.

**Not:** a general notes app, a chatbot, or a CMS. The brain organizes itself.

This document is the build contract for implementation. It translates `ProblemStatement.md` into components, data shapes, interfaces, and deployment constraints.

---

## 1. Goals and non-goals

### 1.1 Goals

| # | Capability | Success looks like |
|---|---|---|
| 1 | Capture | One CLI command ingests a note, URL, or file into `raw/` with timestamp + unique ID |
| 2 | Classify | LLM assigns PARA category, tags, and a one-line summary; wiki note is written |
| 3 | Auto-link | Local embeddings compare the new note to the wiki; similar notes get bidirectional markdown links |
| 4 | Graph | `build_graph.py` exports `graph.json`; Streamlit renders a force-directed, hoverable graph |
| 5 | Ask | `ask()` retrieves relevant wiki notes via embeddings and synthesizes an answer with Groq |
| 6 | Ship | One Streamlit app on a public URL; GitHub repo with README |

### 1.2 Non-goals (v1)

- Multi-user accounts, auth, or sharing other people's brains
- Real-time collaborative editing
- Fine-tuning or self-hosted LLMs
- Full-text search engines (Elasticsearch, Typesense)
- Vector databases (Pinecone, Chroma as a required service)
- Browser extensions or always-on clippers
- Automatic PDF OCR / scanned-image transcription
- Recurring background daemons (pipeline is on-demand / CLI + app-triggered)

### 1.3 Design principles

1. **Files are the source of truth.** `raw/` and `wiki/` are inspectable markdown. SQLite/JSON caches are derived, never canonical.
2. **Local embeddings, remote generation.** Embeddings run on CPU via `sentence-transformers`. Classification and Q&A use Groq (Llama 3) so the hosted app stays within a free LLM tier.
3. **Pipeline is idempotent.** Re-running classify/link/graph on the same corpus must not duplicate nodes or explode link lists.
4. **Author's real data.** Acceptance requires 10+ captures and 15+ linked wiki items from the author's life, not lorem ipsum.
5. **Deployable as a folder.** The Streamlit app reads repo files. Hugging Face Spaces / Streamlit Cloud clone the repo; heavy models must be chosen so Spaces CPU can load them or embeddings are precomputed in git.

---

## 2. System context

```
┌─────────────┐     capture.py      ┌──────────────────────────────┐
│ Author      │  note / URL / file  │  SecondSelf (this repo)      │
│ (CLI / UI)  │ ──────────────────► │  raw/  wiki/  graph.json     │
└─────────────┘                     │  Streamlit app.py            │
                                    └───────────┬──────────────────┘
          ┌─────────────────────────────────────┼──────────────────┐
          ▼                                     ▼                  ▼
   Groq API (Llama 3)              sentence-transformers      vis.js in browser
   classify + ask()                local embeddings           graph + hover
```

**Actors**

- **Author (local):** captures content, runs pipeline, iterates on real notes.
- **Visitor (public URL):** explores the published graph and asks questions. Visitors do not write captures in v1 unless the UI explicitly exposes a gated capture form (optional; default is read + ask only in production).
- **Groq:** classified labels, tags, summaries, and RAG answers.
- **Host (Streamlit Cloud / HF Spaces):** serves `app.py`, static `wiki/` + `graph.json`.

---

## 3. High-level architecture

Two runtimes share the same modules:

| Runtime | Role |
|---|---|
| **CLI pipeline** | `capture.py` → `classify.py` → `link.py` → `build_graph.py` |
| **Streamlit app** | Loads `graph.json` + wiki; hosts graph + `ask()`; optionally triggers pipeline locally |

```
Capture  →  Classify  →  Embed + Link  →  Graph export  →  Visualize / Ask
  raw/        wiki/      wiki/ + cache     graph.json       app.py
```

**Layering**

1. **Storage layer** — markdown files + optional `data/embeddings.npz` cache
2. **Domain layer** — capture, classify, link, graph, ask (pure Python, no Streamlit imports)
3. **Presentation layer** — Streamlit + vis-network HTML component
4. **External I/O** — Groq HTTP, optional URL fetch for links, local filesystem for files

Domain modules must remain importable without Streamlit so CLI and tests stay fast.

---

## 4. Repository layout

```
secondself/                          # repo root (this folder)
├── ProblemStatement.md
├── architecture.md                  # this file
├── docs/
│   ├── architecture.md              # same spec for @docs/architecture.md prompts
│   ├── implementation-plan.md       # next artifact
│   └── edge-case.md
├── raw/                             # immutable-ish captures
│   └── YYYYMMDDTHHMMSS_<id>.md
├── wiki/
│   ├── projects/
│   ├── areas/
│   ├── resources/
│   └── archives/
├── data/                            # derived, git-friendly
│   ├── embeddings.npz               # optional cache keyed by note id
│   └── graph.json                   # or repo-root graph.json per brief
├── src/                             # optional package; v1 may keep scripts at root
│   └── secondself/
├── capture.py
├── classify.py
├── link.py
├── build_graph.py
├── ask.py
├── app.py
├── config.py                        # paths, thresholds, model names
├── prompts/                         # LLM prompt templates
│   ├── classify.txt
│   └── ask.txt
├── tests/
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

**Brief alignment:** the problem statement lists scripts at repo root and `graph.json` at root. Implementation **keeps those public paths** (`capture.py`, `graph.json`, etc.) so graders find them. Internal helpers may live in `lib/` or `src/secondself/` without breaking the contract.

**Recommended split (implementation):**

| Public script | Imports from |
|---|---|
| `capture.py` | `lib/ids.py`, `lib/io.py`, `lib/ingest.py` |
| `classify.py` | `lib/llm.py`, `lib/wiki.py`, `prompts/` |
| `link.py` | `lib/embed.py`, `lib/wiki.py` |
| `build_graph.py` | `lib/wiki.py`, `lib/graph.py` |
| `ask.py` | `lib/embed.py`, `lib/llm.py`, `lib/wiki.py` |
| `app.py` | `ask.py`, `graph.json`, Streamlit components |

---

## 5. Data architecture

### 5.1 Identity

- **Capture ID:** 8-character lowercase hex (`secrets.token_hex(4)`), unique in `raw/`.
- **Stable filename:** `{iso_compact}_{id}.md` e.g. `20260928T141530_a3f91c2b.md`.
- **Wiki slug:** derived from summary or title: kebab-case, max 60 chars, collision suffix `-{id[:4]}`.
- **Graph node id:** the capture ID (never the slug), so moves across PARA folders do not break edges.

### 5.2 Raw capture (`raw/*.md`)

YAML frontmatter + body. Body is the captured text (or extracted text). Binary originals for files are copied beside the note.

```markdown
---
id: a3f91c2b
captured_at: 2026-09-28T14:15:30+05:30
source_type: note | link | file
source_ref: "" | "https://..." | "originals/a3f91c2b.pdf"
title: optional human title
processed: false
---

<raw text or extracted content>
```

**File originals:** `raw/originals/{id}{ext}` — PDF, TXT, MD, DOCX (optional v1: PDF + TXT + MD + images as path-only with filename in body).

**Link captures:** fetch HTML when possible; store URL in `source_ref`; body = title + meta description + first N characters of readable text. If fetch fails, body = URL + “unfetched” note; classify still runs on the URL string.

### 5.3 Wiki note (`wiki/{para}/{slug}.md`)

```markdown
---
id: a3f91c2b
raw_file: 20260928T141530_a3f91c2b.md
category: projects | areas | resources | archives
tags: [career, masai, ai]
summary: One-line LLM summary.
title: Display title
linked_ids: [b1c2d3e4, f0e1d2c3]
embedding_model: all-MiniLM-L6-v2
updated_at: 2026-09-28T14:20:00+05:30
---

# {title}

{summary}

{body — cleaned / lightly structured from raw}

## Related

- [[b1c2d3e4]] Title of related note
```

**PARA folders** map 1:1 to `category`. Moving a note = rewrite path; `id` unchanged.

**Links:** store as `linked_ids` in frontmatter (canonical) **and** a `## Related` markdown section (human + graph parser fallback). Wiki-style `[[id]]` tokens are the graph edge source.

### 5.4 Graph JSON (`graph.json`)

Exported, derived artifact. Schema:

```json
{
  "generated_at": "ISO-8601",
  "nodes": [
    {
      "id": "a3f91c2b",
      "label": "Short title",
      "category": "resources",
      "tags": ["ai"],
      "summary": "…",
      "path": "wiki/resources/some-slug.md",
      "preview": "first ~400 chars of body"
    }
  ],
  "edges": [
    {
      "from": "a3f91c2b",
      "to": "b1c2d3e4",
      "weight": 0.82,
      "reason": "embedding"
    }
  ]
}
```

- Undirected relationship → **one** edge with `from < to` lexicographically to avoid duplicates, **or** two directed edges if vis-network needs direction; prefer **undirected unique pairs** plus `weight`.
- `weight` is cosine similarity at link time (optional; default 1.0 if unknown).

### 5.5 Embedding cache

- File: `data/embeddings.npz` or `data/embeddings.json` (npz preferred).
- Keys: note `id` → float32 vector.
- Invalidate when body hash changes (`sha256` of markdown body stored in a sidecar `data/embedding_meta.json`).
- On HF Spaces, **commit precomputed embeddings** so visitors do not download the transformer model on first ask (see §11).

---

## 6. Component design

### 6.1 `config.py`

Central constants:

| Key | Default | Notes |
|---|---|---|
| `RAW_DIR` / `WIKI_DIR` | `raw/`, `wiki/` | Pathlib |
| `GRAPH_PATH` | `graph.json` | Repo root |
| `GROQ_MODEL` | `llama-3.1-8b-instant` (or current Groq Llama 3 alias) | Overridable |
| `EMBED_MODEL` | `all-MiniLM-L6-v2` | 384-dim, CPU-friendly |
| `SIMILARITY_THRESHOLD` | `0.55` | Tune on 15+ real notes |
| `MAX_LINKS_PER_NOTE` | `8` | Cap noisy graphs |
| `ASK_TOP_K` | `5` | RAG context notes |
| `MAX_CONTEXT_CHARS` | `12000` | Truncate for Groq |

Env: `GROQ_API_KEY` from `.env` (python-dotenv) locally; Streamlit secrets / HF secret in prod.

### 6.2 Capture (`capture.py`)

**CLI**

```text
python capture.py note "text..."
python capture.py link https://example.com
python capture.py file path/to/doc.pdf
python capture.py --help
```

**Flow**

1. Parse subcommand (`note` | `link` | `file`).
2. Generate `id` + `captured_at`.
3. Resolve content:
   - **note:** UTF-8 string as body.
   - **link:** HTTP GET (timeout 10s, user-agent set); extract title + text; on failure store URL only.
   - **file:** copy to `raw/originals/`; extract text (`.txt`/`.md` as-is; `.pdf` via `pypdf`; otherwise store filename + “binary not extracted”).
4. Write `raw/{stamp}_{id}.md` with `processed: false`.
5. Print path + id.

**Invariants:** never overwrite an existing id; never write into `wiki/` from capture.

### 6.3 Classification (`classify.py`)

**Input:** one raw file or `--all` unprocessed raw files.

**LLM contract (JSON only)**

```json
{
  "category": "projects|areas|resources|archives",
  "tags": ["kebab-or-words", "..."],
  "summary": "one sentence, max 160 chars",
  "title": "short title"
}
```

**Prompt rules (in `prompts/classify.txt`)**

- PARA definitions embedded in the system prompt (Tiago Forte):
  - **Projects:** outcomes with an end date
  - **Areas:** ongoing standards of responsibility
  - **Resources:** topics of ongoing interest
  - **Archives:** inactive items from the other three
- Tags: 3–8, lowercase, no `#`.
- If the model returns invalid category, default `resources` and log a warning.
- Temperature ~0.2; `response_format` JSON if Groq supports it, else parse fenced JSON with a regex fallback.

**Output:** write wiki markdown; set raw `processed: true`. Do not compute links here.

**Batch:** process all `processed: false` files; skip already-wiki'd ids unless `--force`.

### 6.4 Auto-linking (`link.py`)

**Algorithm**

1. Load all wiki notes (id, body+summary+title for embedding text).
2. Embed each note (use cache if hash matches).
3. For each note *i*, cosine similarity vs all *j ≠ i*.
4. Candidates with `sim >= SIMILARITY_THRESHOLD`, sort desc, take `MAX_LINKS_PER_NOTE`.
5. Symmetric update: if A links to B, B's `linked_ids` includes A (unless over cap; then keep highest weights).
6. Rewrite `linked_ids` and `## Related` section **without** duplicating existing ids.
7. Persist embedding cache.

**Embedding text:** `title + "\n" + summary + "\n" + body` truncated to 512 tokens-ish (model max sequence). Strip YAML.

**No LLM in this step** — embeddings only, as specified.

### 6.5 Graph builder (`build_graph.py`)

1. Parse every `wiki/**/*.md`.
2. Node per note; edge per unique `linked_ids` pair that exists as a node (drop dangling ids).
3. Write pretty-printed `graph.json`.
4. Exit non-zero if zero nodes (fail loud in CI).

### 6.6 Ask (`ask.py`)

**Signature**

```python
def ask(question: str) -> dict:
    return {"answer": str, "sources": [{"id", "title", "path", "score"}], "error": None}
```

**RAG pipeline**

1. Embed the question with the **same** model as notes.
2. Rank wiki notes by cosine similarity; take `ASK_TOP_K`.
3. Build context blocks: title, category, summary, body excerpt.
4. Call Groq with `prompts/ask.txt`: answer **only** from context; if insufficient, say so explicitly (no invented biography).
5. Return answer + source list for UI citations.

**Grounding rule:** the model must not use world knowledge that contradicts or is absent from notes. Prompt: “If the notes do not contain the answer, say you don't know from the brain.”

### 6.7 Streamlit UI (`app.py`)

**Layout (single page)**

| Region | Content |
|---|---|
| Header | Product name, short subtitle |
| Graph | `components.html` / `st.components.v1.html` with vis-network, data from `graph.json` |
| Sidebar or below | Legend: PARA colors |
| Ask | `st.chat_input` or text + button; markdown answer; expander with source notes |

**Graph UX (acceptance)**

- Force-directed physics (vis-network `barnesHut` or similar)
- Node color by PARA
- Subtle pulse: vis `scaling` / `shadow` or CSS animation on canvas (keep light)
- Hover tooltip: title + summary + preview
- Drag nodes, zoom/scroll, fit on load
- Click optional: `st.session_state` selected node → show full wiki body in a panel

**Capture in UI:** optional local-only form. Production default: **Ask + Graph** so the public URL cannot be used as an open write API. Document that captures are CLI (author machine) then git push / rebuild.

**Pipeline button (local):** `st.button("Rebuild graph")` calling classify/link/build — disabled or hidden when `os.getenv("SECONSELF_READONLY")` is set on the host.

---

## 7. Interactive graph (frontend)

**Library:** vis-network (smaller lift with Streamlit HTML). Cytoscape.js is the fallback if vis hover/physics feel insufficient.

**Injection:** Python reads `graph.json`, serializes to JS:

```javascript
const nodes = new vis.DataSet([...]);
const edges = new vis.DataSet([...]);
const network = new vis.Network(container, { nodes, edges }, options);
network.on("hoverNode", ...);
```

**Node visual mapping**

| PARA | Color role |
|---|---|
| projects | accent / high energy |
| areas | stable / green-blue |
| resources | neutral / gold |
| archives | muted gray |

**Performance:** 15–200 nodes is in scope. No clustering required for acceptance. If N > 300, disable physics after stabilization.

---

## 8. External services and models

### 8.1 Groq

- **Auth:** `GROQ_API_KEY`
- **Client:** official `groq` Python SDK
- **Calls:** classify (short JSON), ask (longer completion)
- **Rate limits:** batch classify with small sleep; surface Streamlit error on 429
- **No secrets in git**

### 8.2 sentence-transformers

- Model: `sentence-transformers/all-MiniLM-L6-v2`
- Device: CPU
- **Deploy constraint:** HF Spaces free CPU may time out on first download. Mitigation: (a) precompute `data/embeddings.npz` and skip loading the model for **graph-only** views; (b) for **ask**, either include the model in a cached HF layer or use Groq embeddings if ever available — v1 sticks to local model **locally**, and on Spaces prefers **precomputed note vectors + load model once** with `ST_CACHE` env. If Spaces cannot load transformers, **document** a two-tier deploy: Streamlit Cloud with enough RAM, or ship a **Groq-only keyword fallback** (not preferred). Primary path: HF Space with `requirements.txt` pinning `sentence-transformers` and a persistent cache directory.

### 8.3 HTTP fetch (links)

- `httpx` with timeout, follow redirects (max 5), size cap (e.g. 2 MB).
- No JS rendering.

---

## 9. End-to-end sequences

### 9.1 New capture (author)

```
User CLI → capture.py writes raw/*.md
        → classify.py → Groq JSON → wiki/{para}/*.md
        → link.py → update linked_ids on N notes
        → build_graph.py → graph.json
        → (optional) git commit / push → host rebuilds
        → app.py serves new graph
```

### 9.2 Ask (visitor)

```
User question → app.py → ask()
  → embed question
  → top-k wiki notes
  → Groq synthesis
  → answer + sources in UI
```

Graph render does **not** call Groq.

---

## 10. Error handling and observability

| Failure | Behavior |
|---|---|
| Missing `GROQ_API_KEY` | CLI exits 2 with message; app shows config error, graph still loads |
| Groq timeout / 5xx | Retry once; then keep raw unprocessed; ask returns error string |
| Invalid LLM JSON | Repair parse; else default category `resources` |
| File extract fail | Capture still stored; body explains failure |
| Empty wiki | Graph empty state in UI; ask explains no knowledge yet |
| Corrupt frontmatter | Skip file, print warning, continue batch |
| Dangling links | Drop in `build_graph.py`; do not crash |

Logging: `print` + optional `logging` to stderr. No PII shipping.

---

## 11. Deployment architecture

### 11.1 Target

Primary: **Hugging Face Spaces (Streamlit SDK)** or **Streamlit Community Cloud**. Both: public URL, `app.py` as entry.

### 11.2 What is deployed

- Source + `wiki/` + `graph.json` + embedding cache
- Secrets: `GROQ_API_KEY`
- `requirements.txt` pinned

### 11.3 What is not deployed as a writable brain

Public visitors should not append to `raw/` on the host filesystem (ephemeral and unsafe). Capture remains an **author-side** workflow unless a future auth layer exists.

### 11.4 Build on host

```text
install deps → start streamlit app.py → read graph.json from repo
```

No separate backend process.

### 11.5 GitHub

- Public repo, MIT or personal license
- README: setup, `.env`, capture examples, PARA, deploy badge/URL
- `.gitignore`: `.env`, `__pycache__`, `.venv`, large originals if needed

---

## 12. Security and privacy

- Notes may be personal. Public deploy **is** a public brain — README must warn the author not to capture secrets, medical data, or credentials.
- Strip `GROQ_API_KEY` from logs.
- HTML from URL fetch: store **text**, not raw HTML execution; Streamlit markdown must not render untrusted HTML (`unsafe_allow_html` only for the vis-network shell, not note bodies).
- File upload path traversal: resolve `Path(file).resolve()` stays under allowed dirs.

---

## 13. Testing strategy

Aligned with acceptance criteria; author's real corpus is the primary test.

| Layer | Tests |
|---|---|
| Unit | ID uniqueness, frontmatter round-trip, JSON graph schema, cosine + threshold linking on fixtures |
| Integration | classify mocked Groq → wiki file; ask mocked LLM + real embeddings on fixture wiki |
| Manual acceptance | 10+ real captures; 15+ wiki notes; hover/drag/zoom; 3+ real questions |
| Deploy smoke | Public URL loads; graph visible; one ask round-trip |

Fixtures live in `tests/fixtures/` (anonymized). Real notes stay in `raw/` / `wiki/` in the author's repo.

---

## 14. Technology choices (locked for v1)

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Matches brief |
| LLM | Groq Llama 3.x | Free tier, JSON-capable |
| Embeddings | `all-MiniLM-L6-v2` | Local, free, small |
| Graph UI | vis-network | Force layout, hover, Streamlit HTML |
| App | Streamlit | Specified |
| HTTP | httpx | Timeouts |
| PDF | pypdf | Lightweight |
| Config | python-dotenv + env | Keys |
| Host | HF Spaces or Streamlit Cloud | Public URL, free |

---

## 15. Module interface summary

```text
capture.ingest(kind, payload) -> RawNote
classify.classify_raw(raw_path) -> WikiNote
link.relink_corpus() -> None
build_graph.export(path) -> Graph
ask.ask(question) -> AskResult
```

All types are dataclasses in `lib/models.py`:

- `RawNote(id, captured_at, source_type, source_ref, body, processed)`
- `WikiNote(id, category, tags, summary, title, body, linked_ids, path)`
- `Graph(nodes, edges, generated_at)`
- `AskResult(answer, sources, error)`

---

## 16. Implementation order (architecture view)

Matches the problem statement, with one extra hardening step:

0. Scaffold dirs, `requirements.txt`, `config.py`, `.env.example`
1. Capture + 10 real items
2. Classify + PARA wiki
3. Embeddings + auto-link on 15+ items
4. `graph.json`
5. vis-network in Streamlit (graph only)
6. `ask()`
7. Combine UI
8. Deploy + secrets
9. README + GitHub

Detailed phases belong in `docs/implementation-plan.md` (next document).

---

## 17. Open decisions (defaults applied)

| Topic | Default |
|---|---|
| Graph file location | Repo-root `graph.json` (brief) |
| Symmetric links | Yes |
| Public capture form | Off |
| Embedding on Spaces | Precompute + load MiniLM; document RAM |
| Wiki body rewriting | Keep raw body; prepend title/summary; do not let LLM rewrite the whole note in v1 (avoids hallucination of the source) |

---

## 18. Traceability to acceptance criteria

| Criterion | Architecture element |
|---|---|
| `raw/` + `wiki/` exist | §4, §5 |
| One command for note, link, file | §6.2 |
| Timestamp + unique ID | §5.1–5.2 |
| 10+ real items | §1.3, §13 |
| Auto category, tags, summary | §6.3 |
| PARA | §6.3, wiki folders |
| Embeddings per note | §6.4, §5.5 |
| Auto-link, no manual tags | §6.4 |
| 15+ organized wiki | §13 |
| Nodes/edges JSON | §5.4, §6.5 |
| Interactive graph, hover, drag, zoom | §6.7, §7 |
| Real notes in graph | §1.3 |
| `ask()` RAG | §6.6 |
| One Streamlit app | §6.7 |
| Public URL, E2E | §11 |
