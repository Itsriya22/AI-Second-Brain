---
id: b168b7f8
raw_file: 20261001T160730_b168b7f8.md
category: projects
tags:
- implementation
- plan
- phases
- secondself
- wiki
- pipeline
summary: A detailed phase‑by‑phase implementation plan for building a SecondSelf knowledge
  management system.
title: Implementation Plan
linked_ids:
- 613f3191
- 9a8fd845
updated_at: '2026-10-01T16:14:20+05:30'
---

# Implementation Plan

A detailed phase‑by‑phase implementation plan for building a SecondSelf knowledge management system.

# SecondSelf — Implementation Plan

> Phase-wise plan derived from `ProblemStatement.md` and `architecture.md`.

## Phase Overview

| Phase | Name | Type | Outcome |
|---|---|---|---|
| 0 | Setup | Setup | Repo scaffold, environment, config, API key working |
| 1 | Capture Pipeline | Implement | `capture.py` saves notes/links/files to `raw/` |
| 2 | Auto-Classification | Implement | `classify.py` produces PARA notes in `wiki/` |
| 3 | Auto-Linking | Implement | `link.py` embeds notes and inserts related links |
| 4 | Graph Model + Visualization | Implement | `build_graph.py` → `graph.json` → interactive graph |
| 5 | Ask + Streamlit App | Implement | `ask.py` RAG and `app.py` combining graph + search |
| 6 | Local Integration Testing | Test | End-to-end flow verified on real data; thresholds tuned |
| 7 | Hardening + Docs | Test | Edge cases handled, README written, repo clean |
| 8 | Deployment | Deploy | Live public URL |
| 9 | Final Testing + Submission | Test | Deployed app verified; deliverables complete |

**Suggested order of effort:** Phases 0–2 are quick; Phases 3–5 carry the most complexity; Phases 6–9 are where quality is decided, so don't compress them.

**Data rule for every phase:** test on the author's **real** notes, links and files, not dummy data. Start collecting 20+ real items during Phase 0 so they're ready.

---

## Phase 0 — Setup

**Goal:** A clean, runnable scaffold before any feature code.

### Tasks

1. **Create the repo and folder structure**
   ```
   secondself/
   ├── raw/  (with raw/attachments/)
   ├── wiki/ (Projects/ Areas/ Resources/ Archives/)
   ├── .cache/
   ├── docs/  (ProblemStatement.md, architecture.md, implementation-plan.md, edge-case.md)
   ├── tests/
   ```
   Add `.gitkeep` files so empty folders are tracked.
2. **Create empty module files:** `capture.py`, `classify.py`, `link.py`, `build_graph.py`, `graph_view.py`, `ask.py`, `app.py`, `config.py`, `utils.py`.
3. **Python environment:** Python 3.10+, virtual environment (`python -m venv .venv`).
4. **`requirements.txt`:** `streamlit`, `groq`, `sentence-transformers`, `numpy`, `python-frontmatter`, `pyyaml`, `requests`, `trafilatura`, `beautifulsoup4`, `pypdf`, `python-dotenv`, `pytest`. Install and confirm imports work.
5. **Config:** implement `config.py` (paths, model names, thresholds, env loading) using the defaults in `architecture.md` §5.
6. **Secrets:** create a Groq account and API key; add `.env` (git-ignored) and `.env.example`.
7. **`.gitignore`:** `.env`, `.venv/`, `__pycache__/`, `.cache/` (re-enabled later for deployment, see Phase 8), OS files.
8. **Utilities:** in `utils.py`, implement ID generation (`YYYYMMDD-HHMMSS-<6hex>`), slugify, and frontmatter read/write helpers.
9. **Smoke tests:**
   - Groq: one hello-world completion succeeds.
   - Embeddings: load MiniLM, embed two sentences, print cosine similarity.
10. **Git:** initialize, first commit, push to a public GitHub repo.

### Deliverables
- Scaffolded repo pushed to GitHub
- Working environment, Groq call and embedding call both verified

### Exit criteria
- [ ] `raw/` and `wiki/` structure exists
- [ ] `pip install -r requirements.txt` succeeds on a fresh venv
- [ ] Groq and sentence-transformers smoke tests pass
- [ ] No secrets in git history

---

## Phase 1 — Capture Pipeline

**Goal:** One command captures a note, a link, or a file into `raw/` with timestamp + unique ID.

### Tasks

1. **CLI** with `argparse`: `capture.py [note|link|file] <value>`, plus auto-detection when the type is omitted (URL → link, existing path → file, else note).
2. **Note handler:** save the text as-is.
3. **Link handler:** fetch with timeout and a user-agent, extract title and main text (`trafilatura`, fall back to `beautifulsoup4`); on failure store the URL with a `fetch_failed: true` flag rather than dropping the capture.
4. **File handler:** support `.txt`, `.md`, `.pdf` (via `pypdf`); copy the original to `raw/attachments/`; extract text into the raw file. Reject or clearly warn on unsupported types.
5. **Raw file writer:** write `raw/<id>.md` with frontmatter (`id`, `captured_at`, `type`, `source`, `title`, `status: pending`) plus the content body.
6. **Reusable function:** expose `capture(input, type=None) -> id` so the Streamlit app can call it later.
7. **Console output:** print the ID and path of what was saved.
8. **Real data capture:** capture **10+ real items** (mix of notes, links and files): e.g., saved articles, project ideas, meeting notes, study material, PDFs.

### Deliverables
- Working `capture.py`
- `raw/` populated with 10+ real items

### Exit criteria
- [ ] One command captures a note, a link, AND a file
- [ ] Every capture has a timestamp and unique ID
- [ ] Two captures in the same second don't collide
- [ ] 10+ real items in `raw/`
- [ ] 🏅 The Archivist

---

## Phase 2 — Auto-Classification (The Sorting Hat)

**Goal:** Any raw capture becomes a wiki note with a PARA category, tags and a one-line summary.

### Tasks

1. **Groq client wrapper** in `classify.py` (or `utils.py`): retries with exponential backoff on 429/5xx, request timeout, throttling between calls.
2. **Prompt:** implement the JSON-only PARA prompt from `architecture.md` §3.2; truncate input to `MAX_CONTENT_CHARS`.
3. **Response validation:**
   - parse JSON (strip stray code fences)
   - enforce `category ∈ {Projects, Areas, Resources, Archives}` (fallback `Resources`)
   - normalize tags (lowercase, dedupe, max 6)
   - trim the summary to one sentence
4. **Wiki note writer:** write `wiki/<Category>/<id>-<slug>.md` with the frontmatter from `architecture.md` §3.2, copying the body from the raw file.
5. **State handling:** mark the raw file `status: classified` (or `failed` with a reason). Skip files already classified so re-runs are idempotent.
6. **CLI:** `classify.py` (process all pending), `classify.py <id>` (single), `--force` (re-classify).
7. **Run on all real captures** and review: is the categorization sensible? Adjust the prompt wording if categories look wrong (e.g., everything landing in Resources).

### Deliverables
- Working `classify.py`
- All Phase 1 captures classified into `wiki/`

### Exit criteria
- [ ] Any raw capture → category + tags + summary automatically
- [ ] PARA categorization working, and outputs spot-checked by hand
- [ ] Failed items don't stop the batch
- [ ] Re-running doesn't duplicate notes

---

## Phase 3 — Auto-Linking (Connect the Dots)

**Goal:** Related notes are linked automatically via embeddings, with no manual tagging.

### Tasks

1. **Embedding text builder:** `title + summary + tags + first ~1,000 chars of body`.
2. **Embedding store:** load MiniLM once; keep vectors in `.cache/embeddings.npz` with `index.json` (id → row, content hash). Only embed new or changed notes.
3. **Similarity search:** normalized vectors, dot product against all other notes; exclude the note itself.
4. **Link selection:** keep matches with `score ≥ LINK_THRESHOLD`, capped at `LINK_TOP_K`.
5. **Link writing:**
   - write bidirectionally into both notes' frontmatter (`links: [{id, score}]`)
   - regenerate the managed `## Related` section with `[[<id>-<slug>]]` links (replace, never append)
6. **CLI:** `link.py` (all notes), `link.py --threshold 0.5`, `link.py --rebuild` (clear cache and recompute).
7. **Diagnostics:** print the score distribution (min / median / max, count above threshold) and the top pairs, to tune the threshold.
8. **Grow the dataset:** capture more real items until there are **15+**, then run the full raw → classify → link pipeline.

### Deliverables
- Working `link.py`
- 15+ real notes, classified and auto-linked in `wiki/`

### Exit criteria
- [ ] Embeddings computed per note and cached
- [ ] Related notes auto-linked, and links checked by hand for relevance
- [ ] Links are symmetric and re-running doesn't duplicate them
- [ ] Threshold chosen from real score data, not guessed
- [ ] 🏅 The Librarian

---

## Phase 4 — Graph Data Model + Visualization

**Goal:** Turn the wiki into an interactive, explorable graph.

### 4A — `build_graph.py`

1. Read every wiki note (frontmatter + body).
2. Create one node per note: `id`, `label` (title), `category`, `tags`, `summary`, `content` excerpt (~600 chars), `source`, `degree`.
3. Create one edge per unordered pair from the `links` field, with `weight` = similarity; dedupe A→B / B→A; drop dangling edges.
4. Write `graph.json` with a `meta` block (generation time, node and edge counts), with sorted, deterministic output.
5. Expose `build_graph() -> dict` for reuse by the app.

### 4B — `graph_view.py`

1. Generate a self-contained HTML string with **vis-network** (CDN) from `graph.json`.
2. Physics: force-directed layout (`forceAtlas2Based` or `barnesHut`) tuned so the graph settles quickly.
3. Visuals: color by PARA category, node size by `degree`, edge width by `weight`, and a "pulse" animation so nodes look alive.
4. Interaction: hover popup (title, category, tags, summary, content excerpt), drag, zoom, and a category legend.
5. **Escape all note text** before it goes into the HTML.
6. Standalone test: write `graph.html` and open it in a browser before integrating into Streamlit.

### Deliverables
- `build_graph.py`, `graph.json`, `graph_view.py`
- Interactive graph built from real notes

### Exit criteria
- [ ] Script builds nodes + edges and exports clean JSON
- [ ] Force-directed graph renders from that JSON
- [ ] Hover reveals note content
- [ ] Drag and zoom work
- [ ] Built from real notes, not dummy data
- [ ] 🏅 The Cartographer

---

## Phase 5 — Ask + Streamlit App

**Goal:** Natural-language Q&A over the wiki, and one app that combines everything.

### 5A — `ask.py`

1. **Retrieval:** embed the question with the same model, cosine search over cached vectors, take `ASK_TOP_K` above `ASK_MIN_SCORE`.
2. **Optional expansion:** add 1-hop linked neighbors of the top hit.
3. **Context builder:** `[id | title] summary + body`, limited to a token/character budget.
4. **Grounded prompt:** "answer only from the notes, cite by id, say so if the answer isn't there."
5. **Guardrail:** if nothing passes the relevance floor, return a "nothing relevant found" answer without calling the LLM.
6. **Return:** `{"answer", "sources": [{id, title, score}]}`.
7. **Test on 10 real questions** about your own notes (include some that *should* fail to find an answer).

### 5B — `app.py`

1. **Layout:** sidebar (capture form, "Process new captures" button, stats) plus tabs (Brain graph, Ask, optional Notes browser).
2. **Capture form:** note / link / file upload calling `capture()`.
3. **Process button:** runs classify → link → build_graph with a progress indicator, then refreshes the graph.
4. **Brain tab:** embed the graph with `components.v1.html`.
5. **Ask tab:** input box, answer, expandable cited source notes; highlight cited nodes in the graph if feasible.
6. **Performance:** `@st.cache_resource` for the embedding model, `@st.cache_data` for `graph.json` keyed on file mtime.
7. **Secrets handling:** read `GROQ_API_KEY` from `st.secrets` or `.env`.

### Deliverables
- `ask.py` returning cited, grounded answers
- `app.py` with graph and search in one Streamlit app, running locally

### Exit criteria
- [ ] `ask()` returns answers synthesized from your own notes
- [ ] Unanswerable questions get an honest "not in your notes" response
- [ ] One Streamlit app contains both graph and search bar
- [ ] Capture → process → graph refresh works from the UI
- [ ] 🏅 The Oracle (once deployed)

---

## Phase 6 — Local Integration Testing

**Goal:** Prove the full pipeline works end to end locally and tune quality.

### Tasks

1. **Clean-slate run:** delete `wiki/`, `.cache/` and `graph.json`; re-run everything from `raw/` and confirm the outputs regenerate identically (or near-identically).
2. **End-to-end via the UI:** capture a brand-new note, a link and a PDF through the app, process them, and confirm each appears in the graph, is classified, and is linked sensibly.
3. **Quality review of real data:**
   - Classification: are PARA categories defensible? Fix the prompt if not.
   - Links: any false positives (too low a threshold) or obvious missed relations (too high)? Re-tune `LINK_THRESHOLD`.
   - Ask: run 15+ questions; check every answer against source notes for hallucination and correct citations.
4. **Automated tests** (`tests/`, with the LLM mocked):
   - ID uniqueness and format; type detection
   - frontmatter round-trip
   - LLM JSON validation (good, malformed, wrong-category responses)
   - link selection (threshold, top-K, symmetry, idempotency)
   - graph dedupe and dangling-edge removal
5. **Log defects** and fix them before moving on.

### Exit criteria
- [ ] Clean-slate rebuild works
- [ ] UI capture → graph → ask flow verified
- [ ] Unit tests pass
- [ ] Thresholds and prompts tuned on real data

---

## Phase 7 — Hardening, Edge Cases and Documentation

**Goal:** Handle the corner cases, then make the repo presentable.

### Tasks

1. **Work through `edge-case.md`.** Priority items:
   - empty or whitespace-only note; very long note; non-UTF-8 text; emoji/Unicode
   - link: 404, timeout, paywall, redirect loop, non-HTML content, private/internal IPs (block)
   - file: unsupported type, empty PDF, scanned (image-only) PDF, huge file, duplicate upload
   - Groq: rate limit, invalid key, malformed JSON, network drop mid-batch
   - linking: single note in wiki, all notes near-identical, no note above threshold, hub nodes
   - graph: zero nodes, zero edges, isolated nodes, very long titles
   - ask: empty question, question with no relevant notes, prompt-injection text inside a captured note
2. **Security pass:** HTML-escape everything shown in graph popups and Streamlit; sanitize filenames; file size and type limits; SSRF protection on link fetching.
3. **UX polish:** clear error and empty-state messages in the app (e.g., "No notes yet: capture something first"), spinner and progress states, and a per-session request cap on `ask()` to protect the Groq quota once public.
4. **Cleanup:** remove dead code, add docstrings, consistent logging.
5. **README.md:** what it is, the pipeline diagram, setup (venv, `pip install`, `.env`), usage (CLI commands and the app), project structure, configuration table, and screenshots or a GIF of the graph.
6. **Content review:** decide what real notes go into the **public** repo. Remove anything private or sensitive from `raw/`, `wiki/` and the caches before publishing.

### Exit criteria
- [ ] Every item in `edge-case.md` is handled or explicitly documented as out of scope
- [ ] No secrets or private notes in the repo
- [ ] README lets a stranger set up and run the project

---

## Phase 8 — Deployment

**Goal:** A public URL running the complete app.

### Tasks

1. **Decide persistence** (open decision in `architecture.md` §11). Recommended baseline: the deployed app reads the committed wiki, graph and embedding cache; in-app captures are session-level.
2. **Prepare the repo for deploy:**
   - commit `wiki/`, `graph.json` and the embedding cache (remove `.cache/` from `.gitignore` or copy it to a committed path)
   - pin dependency versions in `requirements.txt`; use CPU-only `torch` if the build is too heavy
   - set `app.py` as the entry point; confirm it runs from a fresh clone
3. **Deploy to Streamlit Community Cloud** (or HF Spaces as a fallback): connect the GitHub repo, set the main file to `app.py`, choose the Python version.
4. **Add secrets:** `GROQ_API_KEY` in the platform's Secrets manager, never in the repo.
5. **First-boot check:** confirm the embedding model downloads and caches, and the app starts within the platform's time limits.
6. **Record the public URL** and add it to the README.

### Exit criteria
- [ ] App is live at a public URL
- [ ] Build succeeded from a clean checkout
- [ ] Secrets configured on the platform, not in git

---

## Phase 9 — Final Testing and Submission

**Goal:** Verify the deployed product and complete the deliverables.

### Tasks

1. **Incognito/other-device test:** open the URL logged out, on desktop and mobile if possible.
2. **Functional checklist on the live app:**
   - graph loads from real notes
   - hover shows note content; drag and zoom work
   - ask returns synthesized, cited answers (test 10+ questions)
   - capture → process → graph refresh works in the deployed environment
3. **Failure-mode checks on live:** empty question, unanswerable question, oversized upload, Groq error (temporarily use a bad key in a staging copy or simulate) all fail gracefully.
4. **Performance:** cold-start time acceptable; graph responsive at the actual node count.
5. **Final repo pass:** README has the live URL, setup steps and screenshots; the repo is public; commit history is clean.
6. **Verify all acceptance criteria** from `ProblemStatement.md`, and tick each one.
7. **Submit:** GitHub link + live URL.

### Final deliverables checklist
- [ ] Public GitHub repo with a clean README and setup instructions
- [ ] Live deployed URL with the interactive graph and ask-your-brain search both working
- [ ] End-to-end flow verified: capture → classify → link → graph → ask
- [ ] Capture pipeline, self-organizing wiki, living brain and SecondSelf deployment all complete
- [ ] 🏅 The Archivist · The Librarian · The Cartographer · The Oracle

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Groq free-tier rate limits | Batch classification stalls | Throttle, backoff, resumable `status` field |
| Poor PARA classification | Wiki looks random | Iterate on the prompt using real notes; consider the 70B model |
| Bad link threshold | Hairball or empty graph | Tune from real score distribution; top-K cap |
| Streamlit Cloud filesystem resets | Deployed captures vanish | Commit the knowledge base; document the limitation or add persistence |
| Heavy dependencies on the free tier | Build fails or is slow | Pin versions, CPU-only torch, cache the model |
| Public URL burns the Groq quota | App stops answering | Per-session rate limit; secret only in platform settings |
| Private notes leak via public repo | Privacy breach | Phase 7 content review before publishing |
| Graph slows with many nodes | Poor UX | Fine for hundreds of nodes; cluster or filter beyond that |

## Suggested Cursor Prompts (per phase)

Following the workflow in `ProblemStatement.md`, give Cursor one phase at a time:

```
Implement Phase 0 as per @docs/implementation-plan.md
Implement Phase 1 as per @docs/implementation-plan.md using @docs/architecture.md
...
```

Commit after each phase, and don't start the next one until the current phase's exit criteria are ticked.

## Related

<!-- secondself:related:start -->
- [[projects/secondself-architecture-overview|SecondSelf Architecture Overview]]
- [[projects/edge-cases-reference|Edge Cases Reference]]
<!-- secondself:related:end -->