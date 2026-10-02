---
id: 5c79e7ea
raw_file: 20261001T160729_5c79e7ea.md
category: projects
tags:
- ai
- knowledge-management
- paradigm
- graph
- automation
- streamlit
summary: A system to capture, classify, link, visualize, and query personal knowledge
  using AI and a PARA-based wiki.
title: SecondSelf — Your Personal AI Second Brain
linked_ids:
- c74a3181
- 9b1ea3eb
- 613f3191
updated_at: '2026-10-01T16:14:20+05:30'
---

# SecondSelf — Your Personal AI Second Brain

A system to capture, classify, link, visualize, and query personal knowledge using AI and a PARA-based wiki.

# SecondSelf — Your Personal AI Second Brain

## Problem Statement

Every notes app fails the same way: you capture hundreds of notes, bookmarks, PDFs, and ideas, and then you never find them again. Information goes in, but nothing comes back out. Notes sit in folders nobody re-reads, bookmarks pile up unread, and knowledge doesn't compound.

Ideas, links, and notes are scattered across apps, browser tabs, and memory. Manual tagging never happens, and even a well-filed pile of notes is hard to explore or query.

## Goal

Build an end-to-end system where you can:

1. **Capture** anything (a note, a link, a file)
2. Have AI **automatically classify and file** it
3. Have AI **auto-link** it to related knowledge
4. See everything rendered as a **live, interactive graph** you can explore
5. **Ask any question in plain English** and get an answer synthesized from your own accumulated knowledge
6. Deploy it to a **public URL** anyone can open

> Not a notes app. Not a chatbot. A brain that organizes itself and answers for you.

## System Flow

```
Capture any note / link / file
        ↓
AI classifies & files it (PARA method)
        ↓
AI auto-links it to related notes (embeddings)
        ↓
Everything renders as a live, interactive, hoverable graph
        ↓
Ask it anything in plain English → answer pulled from YOUR notes
        ↓
Deployed on a public URL anyone can open
```

## Functional Requirements

### 1. Capture Pipeline

One command that captures anything into one place.

- Project structure:
  - `raw/` — every raw capture lands here
  - `wiki/` — organized, classified, linked notes
- A Python capture script (`capture.py`) that accepts a **note**, a **link**, or a **file**
- Each capture is saved to `raw/` with:
  - a timestamp
  - a unique ID
  - the raw content
- Must be tested on **10+ real pieces of the author's own information** (not test data)

### 2. Auto-Classification (The Sorting Hat)

- A function that sends any raw capture to a free LLM (Groq / Llama 3) and returns:
  - a **category** using the PARA framework (Projects, Areas, Resources, Archives)
  - **tags**
  - a **one-line summary**
- Runs across existing raw captures so they organize themselves into `wiki/`

### 3. Auto-Linking (Connect the Dots)

- Compute an embedding for each note (`sentence-transformers`, local and free)
- Compare each new capture against existing notes in `wiki/`
- When similarity exceeds a threshold, automatically insert a link between the notes
- No manual tagging: the system discovers relationships on its own
- Must run on **15+ real items**, producing an organized `wiki/` folder with linked notes

### 4. Graph Data Model

- A script (`build_graph.py`) that reads every note and its links
- Builds an in-memory nodes-and-edges representation:
  - every note → a node
  - every link/relationship → an edge
- Exports clean JSON (`graph.json`)

### 5. Interactive Graph Visualization

- Use a JS graph library (vis-network or Cytoscape.js) to render a force-directed graph:
  - notes as nodes (visually alive / pulsing)
  - links as edges
  - hover popups that reveal each note's content
  - drag-to-explore and zoom
- Built from the author's real notes, not dummy data

### 6. Ask Your Brain (Natural-Language Search)

- A single `ask()` function (`ask.py`) that combines:
  - **embeddings** to find notes relevant to a question
  - the **wiki** as the source content
  - an **LLM** to synthesize an answer from the retrieved notes
- This is retrieval-augmented Q&A over the user's own knowledge
- Tested against real questions about the author's own captured notes

### 7. UI, Deployment and Public URL

- One **Streamlit** app (`app.py`) containing:
  - the interactive brain graph
  - the ask-anything search bar
- Deploy to a free platform (Streamlit Cloud or Hugging Face Spaces)
- Obtain a public URL anyone can open
- The full pipeline must work end to end in the deployed app

## Suggested Tech Stack

| Layer | Choice |
|---|---|
| Language | Python |
| LLM | Groq (Llama 3), free tier |
| Embeddings | `sentence-transformers` (local) |
| Graph rendering | vis-network or Cytoscape.js |
| UI | Streamlit |
| Hosting | Streamlit Cloud / Hugging Face Spaces |

## Suggested Repo Structure

```
secondself/
├── raw/             # raw captures (timestamp + unique ID)
├── wiki/            # classified + auto-linked notes
├── capture.py       # one-command capture
├── classify.py      # PARA classification via LLM
├── link.py          # embeddings + auto-linking
├── build_graph.py   # nodes/edges → graph.json
├── graph.json       # exported graph data
├── ask.py           # retrieval + LLM answer
├── app.py           # Streamlit UI (graph + search)
├── requirements.txt
└── README.md
```

## Acceptance Criteria

**Capture**
- [ ] `raw/` and `wiki/` folder structure exists
- [ ] One command captures a note, a link, AND a file
- [ ] Every capture has a timestamp + unique ID
- [ ] 10+ real items captured

**Organize**
- [ ] Any raw capture → category + tags + summary automatically
- [ ] PARA categorization working
- [ ] Embeddings computed per note
- [ ] Related notes auto-linked (no manual tagging)
- [ ] Runs on 15+ real items → organized `wiki/`

**Visualize**
- [ ] Script builds nodes + edges from notes and exports clean JSON
- [ ] Interactive force-directed graph renders from that JSON
- [ ] Hover reveals note content
- [ ] Drag + zoom work
- [ ] Built from real notes, not dummy data

**Ask and Ship**
- [ ] `ask()` returns answers synthesized from your own notes (retrieval + LLM)
- [ ] One Streamlit app contains both the graph and the search bar
- [ ] Deployed live with a public URL
- [ ] Full pipeline works end to end in the deployed app

## Final Deliverables

- [ ] Public GitHub repo with a clean README and setup instructions
- [ ] Live deployed URL with the interactive graph and ask-your-brain search both working
- [ ] End-to-end flow verified: capture → classify → link → graph → ask

## Suggested Build Order

1. Scaffold repo structure + `requirements.txt`
2. `capture.py`: test on real items
3. `classify.py`: PARA categories, tags, summary
4. `link.py`: embeddings + similarity auto-linking
5. `build_graph.py`: JSON nodes/edges
6. Graph rendering with vis-network / Cytoscape
7. `ask.py`: retrieval-augmented Q&A
8. `app.py`: Streamlit app combining graph + search
9. Deploy to Streamlit Cloud / HF Spaces → public URL
10. Write README, push to GitHub

## Working Method (AI-Assisted Development)

**Tools:** Cursor, Antigravity, Qoder, Devin, or VS Code + Claude.

**Context documents to maintain:**

| File | Purpose |
|---|---|
| `PROBLEM_STATEMENT.md` | The problem being solved |
| `architecture.md` | How the project will be built |
| `implementation-plan.md` | Phase-wise plan (Phase 0: setup; Phases 1–5: implement; Phases 6–7: local testing; Phases 8–9: deploy and final testing) |
| `edge-case.md` | Corner scenarios and edge cases |

**Prompt sequence:**
1. Generate a detailed architecture from `@PROBLEM_STATEMENT.md`
2. Save it to `architecture.md`
3. Generate a phase-wise `implementation-plan.md` from `@architecture.md` and `@PROBLEM_STATEMENT.md`
4. Generate `edge-case.md` from `@docs/architecture.md` and `@docs/implementation-plan.md`
5. Implement Phase 0 per `@docs/implementation-plan.md`

## Related

<!-- secondself:related:start -->
- [[projects/secondself-project-plan|SecondSelf Project Plan]]
- [[projects/command-to-capture-all-notes-in-one-place|Command to Capture All Notes in One Place]]
- [[projects/secondself-architecture-overview|SecondSelf Architecture Overview]]
<!-- secondself:related:end -->