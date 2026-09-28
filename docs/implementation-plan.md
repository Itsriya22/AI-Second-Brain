# SecondSelf — Phase-wise Implementation Plan

Sources: `ProblemStatement.md`, `docs/architecture.md`.

This is the execution contract. Each phase has **scope**, **files**, **tasks**, **exit criteria**, and **how to verify**. Do not start the next phase until the previous phase’s exit criteria are met.

## Phase map

| Phase | Name | Kind |
|---|---|---|
| 0 | Repository scaffold | Setup |
| 1 | Capture pipeline | Implement |
| 2 | Auto-classification (PARA) | Implement |
| 3 | Auto-linking (embeddings) | Implement |
| 4 | Graph data model | Implement |
| 5 | Streamlit graph + Ask | Implement |
| 6 | Local pipeline testing | Local testing |
| 7 | Local UI testing | Local testing |
| 8 | Deploy public URL | Deploy |
| 9 | Final testing, README, GitHub | Deploy + final testing |

```
Phase 0  scaffold
    ↓
Phase 1  capture.py  →  raw/  (10+ real items by Phase 6)
    ↓
Phase 2  classify.py →  wiki/{para}/
    ↓
Phase 3  link.py     →  linked wiki  (15+ items by Phase 6)
    ↓
Phase 4  build_graph.py → graph.json
    ↓
Phase 5  app.py + ask.py  (graph + search in one app)
    ↓
Phases 6–7  local verification
    ↓
Phases 8–9  host + README + public repo
```

**Rules carried from architecture**

- Public scripts stay at repo root: `capture.py`, `classify.py`, `link.py`, `build_graph.py`, `ask.py`, `app.py`, `graph.json`.
- Domain code has **no Streamlit imports**.
- Wiki bodies are **not** LLM-rewritten in v1.
- Public host is **read + ask only** (no open capture write API).
- Author’s **real** notes only — no lorem ipsum for acceptance.

---

## Phase 0 — Repository scaffold

**Goal:** Empty-but-runnable project shape so later phases only add behavior.

### Files to create

| Path | Purpose |
|---|---|
| `requirements.txt` | Pinned Python deps |
| `config.py` | Paths, models, thresholds |
| `.env.example` | `GROQ_API_KEY=` |
| `.gitignore` | `.env`, `.venv`, `__pycache__`, `*.pyc`, `.streamlit/secrets.toml` |
| `lib/__init__.py` | Package |
| `lib/models.py` | `RawNote`, `WikiNote`, `Graph`, `AskResult` dataclasses (stubs OK) |
| `lib/ids.py` | ID helper stub |
| `prompts/.gitkeep` | Later classify/ask templates |
| `raw/.gitkeep` | Capture landing zone |
| `raw/originals/.gitkeep` | Copied files |
| `wiki/projects/.gitkeep` | PARA |
| `wiki/areas/.gitkeep` | PARA |
| `wiki/resources/.gitkeep` | PARA |
| `wiki/archives/.gitkeep` | PARA |
| `data/.gitkeep` | Embedding cache |
| `tests/.gitkeep` | Tests |
| `README.md` | One-paragraph placeholder (full README in Phase 9) |

Placeholder root scripts (argparse `--help` only, or `NotImplementedError` with a message): `capture.py`, `classify.py`, `link.py`, `build_graph.py`, `ask.py`, `app.py`.

### `requirements.txt` (minimum)

```
python-dotenv
httpx
pypdf
pyyaml
groq
sentence-transformers
numpy
streamlit
```

Pin versions at install time (`pip freeze` after a working venv). Do not commit `.env`.

### `config.py` defaults (architecture §6.1)

- `RAW_DIR`, `WIKI_DIR`, `GRAPH_PATH` (`graph.json` at repo root)
- `GROQ_MODEL` = `llama-3.1-8b-instant` (or current Groq Llama 3 alias)
- `EMBED_MODEL` = `all-MiniLM-L6-v2`
- `SIMILARITY_THRESHOLD` = `0.55`
- `MAX_LINKS_PER_NOTE` = `8`
- `ASK_TOP_K` = `5`
- `MAX_CONTEXT_CHARS` = `12000`

### Tasks

1. Create folders and gitignores.
2. Create venv, install requirements.
3. Copy `.env.example` → `.env` and paste Groq key (local only).
4. Confirm `python -c "import config"` from repo root.

### Exit criteria

- [ ] `raw/` and `wiki/` (four PARA subfolders) exist
- [ ] `requirements.txt`, `config.py`, `.env.example`, `.gitignore` exist
- [ ] Package `lib/` importable
- [ ] No secrets in git

### Verify

```text
python -c "import config; from pathlib import Path; assert Path('raw').is_dir() and Path('wiki/projects').is_dir()"
```

---

## Phase 1 — Capture pipeline

**Goal:** One command captures a **note**, a **link**, or a **file** into `raw/` with timestamp + unique ID. (`ProblemStatement` Capture; architecture §6.2)

### Files

- `lib/ids.py` — `secrets.token_hex(4)`, uniqueness check against `raw/`
- `lib/io.py` — frontmatter read/write (PyYAML)
- `lib/ingest.py` — note / link / file content resolution
- `capture.py` — CLI
- `tests/test_capture.py` — filename, id, source_type (no Groq)

### CLI contract

```text
python capture.py note "text..."
python capture.py link https://example.com
python capture.py file path/to/doc.pdf
```

### Behavior

1. Generate `id` + `captured_at` (timezone-aware ISO).
2. Filename: `{YYYYMMDDTHHMMSS}_{id}.md`.
3. Frontmatter per architecture §5.2 (`processed: false`).
4. **note:** body = argument text.
5. **link:** `httpx` GET, 10s timeout, 2 MB cap, max 5 redirects; body = title + meta + readable text; on failure still write URL + “unfetched”.
6. **file:** copy to `raw/originals/{id}{ext}`; extract `.txt`/`.md` as-is, `.pdf` via `pypdf`; else body explains binary not extracted.
7. Print path + id. Never write `wiki/`. Never overwrite an existing id.

### Tasks

1. Implement models + IO round-trip.
2. Implement ingest + CLI.
3. Capture **at least 3** real items in this phase (one of each kind) so the path is proven; remaining count is completed by Phase 6 (**10+** total).

### Exit criteria

- [ ] Note, link, and file each produce a `raw/` markdown file
- [ ] Every file has timestamp + unique `id`
- [ ] Originals land under `raw/originals/` for file captures
- [ ] Unit tests for id uniqueness and frontmatter

### Verify

```text
python capture.py note "A real thought from today"
python capture.py link https://<real-url-you-use>
python capture.py file <real-file>
dir raw
```

---

## Phase 2 — Auto-classification (Sorting Hat)

**Goal:** Raw capture → PARA category + tags + one-line summary + title; wiki note written; raw marked processed. (`ProblemStatement` §2; architecture §6.3)

### Files

- `prompts/classify.txt`
- `lib/llm.py` — Groq client, JSON parse + retry, invalid category → `resources`
- `lib/wiki.py` — slug, PARA path, write wiki markdown (raw body preserved)
- `classify.py` — one file or `--all` / `--force`
- `tests/test_classify.py` — mocked Groq JSON → wiki file

### LLM JSON contract

```json
{
  "category": "projects|areas|resources|archives",
  "tags": ["..."],
  "summary": "one sentence, max 160 chars",
  "title": "short title"
}
```

Prompt includes PARA definitions (Projects / Areas / Resources / Archives). Temperature ~0.2. Tags: 3–8, lowercase, no `#`.

### Behavior

- Wiki path: `wiki/{category}/{slug}.md` with `id` in frontmatter.
- Body = original capture text (plus title heading + summary). **No full-note rewrite.**
- Set raw `processed: true`.
- `--all` skips processed unless `--force`.
- Missing `GROQ_API_KEY` → exit code 2.

### Tasks

1. Prompts + Groq wrapper.
2. Wiki writer + slug collision suffix `-{id[:4]}`.
3. Run classify on existing raw captures.

### Exit criteria

- [ ] Any raw capture produces category + tags + summary automatically
- [ ] PARA folders receive notes
- [ ] Raw `processed` flips to true
- [ ] Mocked unit/integration test without live Groq

### Verify

```text
python classify.py --all
# Inspect wiki/**/*.md frontmatter
```

---

## Phase 3 — Auto-linking

**Goal:** Local embeddings; similarity above threshold inserts links; no manual tagging. (`ProblemStatement` §3; architecture §6.4)

### Files

- `lib/embed.py` — MiniLM, cosine, cache `data/embeddings.npz` + `data/embedding_meta.json` (body hash)
- `link.py` — `relink_corpus()`
- `tests/test_link.py` — fixture notes, threshold, no duplicate ids, symmetry

### Algorithm

1. Load all wiki notes; embed `title + summary + body` (YAML stripped, truncated).
2. Pairwise cosine; `sim >= 0.55`; top `MAX_LINKS_PER_NOTE` (8).
3. Symmetric `linked_ids`; if over cap, keep highest weights.
4. Rewrite frontmatter + `## Related` with `[[id]]` labels.
5. Idempotent: re-run does not duplicate links.
6. **No LLM** in this step.

Need **15+ wiki notes** before Phase 6 exit (capture more + classify in this phase if short).

### Exit criteria

- [ ] Embeddings computed per note (cache present after run)
- [ ] Related notes auto-linked
- [ ] Re-run does not duplicate `linked_ids`
- [ ] Threshold test on fixtures

### Verify

```text
python link.py
# Open two related wiki files; confirm linked_ids and ## Related
```

---

## Phase 4 — Graph data model

**Goal:** Notes + links → in-memory graph → clean `graph.json`. (`ProblemStatement` §4; architecture §5.4, §6.5)

### Files

- `lib/graph.py` — parse wiki, unique undirected edges (`from < to`), drop dangling ids
- `build_graph.py` — write pretty `graph.json`; exit non-zero if zero nodes
- `tests/test_graph.py` — schema keys, no dangling edges, no duplicate pairs

### `graph.json` schema

- `generated_at`
- `nodes[]`: `id`, `label`, `category`, `tags`, `summary`, `path`, `preview` (~400 chars)
- `edges[]`: `from`, `to`, `weight`, `reason` (`embedding`)

Node **id** = capture id, not slug.

### Exit criteria

- [ ] Script builds nodes + edges from real wiki notes
- [ ] `graph.json` is valid JSON matching the schema
- [ ] Zero-node run fails loudly

### Verify

```text
python build_graph.py
python -c "import json; g=json.load(open('graph.json')); print(len(g['nodes']), len(g['edges']))"
```

---

## Phase 5 — Interactive graph + Ask + Streamlit app

**Goal:** One Streamlit app with force-directed graph **and** plain-English ask, both on real notes. (`ProblemStatement` §5–7; architecture §6.6–6.7, §7)

Implement in this order inside the phase: (A) `ask.py`, (B) graph HTML, (C) combine in `app.py`.

### 5A — `ask.py`

- `ask(question) -> dict` with `answer`, `sources[{id,title,path,score}]`, `error`
- Same embedding model; top `ASK_TOP_K` (5); Groq + `prompts/ask.txt`
- Grounding: only from notes; otherwise “don’t know from the brain”
- Missing key: return `error`, do not crash import

### 5B — Graph in Streamlit

- vis-network via `st.components.v1.html`
- Physics (barnesHut); PARA colors; hover = title + summary + preview
- Drag + zoom; fit on load
- Optional click → session state + full note panel
- Empty wiki: empty-state copy, not a JS crash

### 5C — `app.py`

| Region | Content |
|---|---|
| Header | SecondSelf + one-line subtitle |
| Graph | vis-network from `graph.json` |
| Legend | PARA colors |
| Ask | Input + markdown answer + sources expander |

- Production: graph + ask only. Hide rebuild/capture when `SECONSELF_READONLY` is set (default on host in Phase 8).
- Note bodies rendered as markdown, **not** untrusted HTML.
- `unsafe_allow_html` only for the vis-network shell.

### Exit criteria

- [ ] `ask()` synthesizes from retrieved wiki notes
- [ ] Interactive graph from real `graph.json` (hover, drag, zoom)
- [ ] One `app.py` contains graph **and** search
- [ ] `streamlit run app.py` works locally

### Verify

```text
python -c "from ask import ask; print(ask('What am I working on?')['answer'][:200])"
streamlit run app.py
```

Exercise hover, drag, zoom, and one real question in the UI.

---

## Phase 6 — Local pipeline testing

**Goal:** Corpus and CLI meet Capture / Organize / graph-export bars **without** relying on the hosted URL.

### Corpus bars (`ProblemStatement` acceptance)

- [ ] **10+** real raw captures (mix of note, link, file)
- [ ] **15+** classified, linked wiki notes
- [ ] PARA looks sane on a manual skim (misfiles noted, `--force` reclassify if needed)
- [ ] `graph.json` node count matches wiki notes
- [ ] Three CLI asks about **your** notes return grounded answers + sources

### Automated

- [ ] `tests/test_capture.py`
- [ ] `tests/test_classify.py` (mocked LLM)
- [ ] `tests/test_link.py` (fixtures)
- [ ] `tests/test_graph.py`

```text
python -m pytest tests -q
python classify.py --all
python link.py
python build_graph.py
```

### Threshold tuning

If the graph is empty or a hairball: adjust `SIMILARITY_THRESHOLD` in `config.py` on **this** corpus; document the final value in README (Phase 9).

### Exit criteria

- [ ] All Capture + Organize checkboxes in the problem statement that do not require a browser
- [ ] Pytest green
- [ ] Real corpus committed (no secrets in notes)

---

## Phase 7 — Local UI testing

**Goal:** Visualize + Ask bars on a local Streamlit session.

### Checklist

- [ ] Graph uses **real** notes, not dummy JSON
- [ ] Hover reveals note content
- [ ] Drag + zoom work
- [ ] Ask bar answers from the same wiki
- [ ] Sources list opens the right note ids
- [ ] Empty/error: stop Groq (invalid key) → graph still loads; ask shows error
- [ ] No capture form on the default app path (or clearly local-only)

### Verify

`streamlit run app.py` — walk the acceptance **Visualize** and **Ask** items that are local.

### Exit criteria

- [ ] Visualize acceptance criteria satisfied locally
- [ ] Ask + combined-app criteria satisfied locally

---

## Phase 8 — Deploy public URL

**Goal:** Free public host with graph + ask working. (`ProblemStatement` UI/Deploy; architecture §11)

### Tasks

1. Choose **Hugging Face Spaces (Streamlit)** or **Streamlit Community Cloud**.
2. Set secret `GROQ_API_KEY`.
3. Set `SECONSELF_READONLY=1` (or equivalent) so visitors cannot write `raw/`.
4. Commit `wiki/`, `graph.json`, and `data/embeddings.npz` if used.
5. Pin `requirements.txt`; confirm MiniLM can load or document cache/RAM.
6. Deploy; copy public URL.

### Exit criteria

- [ ] Public URL opens without login
- [ ] Graph visible from committed `graph.json`
- [ ] One ask round-trip on the live app
- [ ] Key not in the repo

### Verify

Incognito browser: load URL, hover a node, ask one real question.

---

## Phase 9 — Final testing, README, GitHub

**Goal:** Deliverables complete: public repo, live URL, E2E story.

### README must include

- What SecondSelf is (not a notes app / not a chatbot)
- Setup: Python version, venv, `.env`, Groq key
- Capture / classify / link / build_graph commands
- `streamlit run app.py`
- PARA + privacy warning (public brain; no secrets)
- Live URL
- Tech stack table from the problem statement

### GitHub

- Public repo, clean history, no `.env`
- Push `architecture.md` / `docs/*` as needed

### Final E2E (problem statement)

```text
capture → classify → link → graph → ask
```

Run once more locally on a **new** real capture, then push and confirm the host rebuild (or rebuild graph before push).

### Exit criteria (deliverables)

- [ ] Public GitHub repo + setup README
- [ ] Live URL: graph **and** ask both working
- [ ] E2E verified on real author data
- [ ] Problem statement acceptance checkboxes all ticked

---

## Suggested calendar (single developer)

| Phase | Effort (indicative) |
|---|---|
| 0 | 0.5 day |
| 1 | 1 day |
| 2 | 1 day |
| 3 | 1–1.5 days (model download + tuning) |
| 4 | 0.5 day |
| 5 | 1.5–2 days |
| 6 | 0.5–1 day |
| 7 | 0.5 day |
| 8 | 0.5–1 day (host quirks) |
| 9 | 0.5 day |

---

## Dependency and risk log

| Risk | Phase | Mitigation |
|---|---|---|
| Groq rate limits on `--all` | 2 | Sleep between calls; retry once |
| MiniLM slow/first download | 3, 8 | Cache locally; commit embeddings for host |
| Spaces RAM | 8 | Precomputed vectors; Streamlit Cloud fallback |
| Similarity 0.55 wrong for corpus | 3, 6 | Tune; cap 8 links |
| Personal data on public URL | 8–9 | README warning; scrub notes |

---

## Traceability

| Problem statement bar | Phase that closes it |
|---|---|
| `raw/` + `wiki/` structure | 0 |
| Capture note + link + file | 1 |
| Timestamp + unique ID | 1 |
| 10+ real items | 1–6 |
| Auto category, tags, summary, PARA | 2 |
| Embeddings + auto-link | 3 |
| 15+ organized wiki | 3–6 |
| `graph.json` nodes/edges | 4 |
| Interactive graph, hover, drag, zoom, real data | 5, 7 |
| `ask()` RAG | 5, 6 |
| One Streamlit app | 5 |
| Public URL, full pipeline on host | 8–9 |
| GitHub + README | 9 |

---

## Next action

Implement **Phase 0** in this repo per this file (`docs/implementation-plan.md`). Then generate `docs/edge-case.md` from architecture + this plan, or proceed Phase 0 first if implementation should start immediately.
