# SecondSelf Deployment Plan — Streamlit Community Cloud

This plan deploys the SecondSelf Streamlit app from GitHub to Streamlit Community
Cloud. It covers preparation and verification; it does not authorize publishing
the personal wiki or pushing commits.

## Deployment summary

| Setting | Value |
|---|---|
| Host | [Streamlit Community Cloud](https://share.streamlit.io/) |
| Repository | `Itsriya22/AI-Second-Brain` |
| Branch | `main` |
| App entry point | `app.py` |
| Dependencies | `requirements.txt` |
| Required secret | `GROQ_API_KEY` |
| Required variable | `SECONSELF_READONLY=1` |
| Public app data | Reviewed `wiki/`, `graph.json`, and embedding cache files |

The deployed app reads the checked-in wiki and graph and has no capture form.
Do not include `raw/` or original files unless there is a separate, explicit
need to publish them.

## 1. Review privacy and deployment scope

Treat the deployment as public. Anyone who can open the app can read its wiki
notes, graph labels, summaries, previews, and content shown in source panels.
Anyone with access to the GitHub repository can also read the committed files
directly.

Before proceeding:

- [ ] Review every note in `wiki/`, including imported course and project
  documents, for personal, confidential, licensed, or otherwise unsuitable
  material.
- [ ] Review `graph.json`, which contains note titles, tags, summaries,
  previews, and repository-relative paths.
- [ ] Confirm that each wiki note is intended for public access. Remove or
  redact sensitive notes at the source and regenerate the graph before
  publishing.
- [ ] Keep `.env`, `.streamlit/secrets.toml`, `raw/`, `raw/originals/`, PDFs,
  and `files.zip` out of Git. Never put the Groq key in source, Markdown,
  README text, a command committed to the repository, or a public issue.
- [ ] Only Markdown files are eligible from `wiki/`. The Git ignore rules
  exclude `wiki/.obsidian/` and every non-`.md` file under `wiki/`; Markdown
  notes still require an individual privacy review before staging.
- [ ] Do not use `git add -A` blindly in this workspace. It may include the
  local `Second Self/` vault or `wiki/.obsidian/`. Stage only reviewed project
  files and the specifically approved public wiki/graph assets.

**Stop condition:** Do not push or deploy until the owner has reviewed and
approved the exact public corpus and files to publish.

## 2. Streamlit Cloud secrets compatibility

The app's runtime configuration helper checks the process environment first,
then reads Streamlit Cloud values from `st.secrets`. This preserves local
`.env`/environment workflows while supporting Cloud's secret store.
`GROQ_API_KEY` must be a string; missing credentials return a clear error, and
secret values are never printed. `SECONSELF_READONLY` accepts the environment
or a Streamlit secret and recognizes `1`, `true`, or `yes` (case-insensitive);
TOML boolean `true` is also supported.

Focused tests cover environment precedence, blank-environment fallback,
Streamlit-secret fallback, missing credentials, invalid setting types, and
read-only mode. If changing this behavior, preserve those contracts.

## 3. Prepare and validate the deployment commit

The deployment must contain the app and the exact corpus it serves:

- Application modules: `app.py`, `ask.py`, `build_graph.py`, `classify.py`,
  `config.py`, `link.py`, `capture.py`, and required `lib/` modules.
- Prompts: `prompts/ask.txt` and `prompts/classify.txt`.
- Runtime manifest: pinned `requirements.txt`.
- Reviewed public data: `wiki/`, `graph.json`, `data/embeddings.npz`, and
  `data/embedding_meta.json` if using the precomputed embedding cache. From
  `wiki/`, include reviewed Markdown notes only; `.obsidian/`, attachments,
  and other non-Markdown files are excluded.

`raw/` is not needed by the read-only app. Keep it local and untracked. Confirm
the ignore rules still exclude `.env`, `.streamlit/secrets.toml`, raw captures,
and originals.

From the repository root, run the local checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m streamlit run app.py
.\.venv\Scripts\python.exe build_graph.py
git diff --check
```

Before staging, inspect both the staged file list and staged diff. Check for
secret strings and unintended files, and verify graph node count equals the
number of reviewed Markdown files in `wiki/`. Do not commit or push until the
owner approves the reviewed staging set.

### Python and model footprint

The app uses `all-MiniLM-L6-v2` to embed questions. The checked-in
`data/embeddings.npz` caches corpus vectors; it does **not** include the model
weights. The first question on a fresh Cloud instance may download the model
from Hugging Face and use additional startup time and memory. Test that
first-run path in the deployed app. Keep the embedding cache and model files
free of secrets.

`requirements.txt` is pinned. If Cloud dependency installation fails or exceeds
available resources, use the build logs to identify the specific dependency
problem and make a tested, minimal manifest change; do not broadly unpin
packages as a first response.

## 4. Create the Community Cloud app

After the approved deployment commit is available on GitHub:

1. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with the
   GitHub account that can access the repository.
2. Choose **Create app**.
3. Select repository `Itsriya22/AI-Second-Brain`, branch `main`, and file path
   `app.py`.
4. Open **Advanced settings** before deploying and enter the secrets using
   TOML syntax:

   ```toml
   GROQ_API_KEY = "your-key"
   SECONSELF_READONLY = "1"
   ```

   Replace the placeholder in the Cloud settings UI only. Do not put a real key
   in this document, Git, or a committed local file.
5. Choose public app visibility only after the corpus review in section 1.
6. Deploy and retain the URL shown by Community Cloud.

Streamlit Cloud settings can be edited after creation. If the secret is rotated,
update the Cloud secret there; do not rotate it by committing a replacement.

## 5. Verify the live app

Test the deployed URL in a private/incognito browser window while signed out,
where supported:

- [ ] The URL loads without requiring a GitHub or Streamlit login.
- [ ] The page title is SecondSelf and the graph renders from the committed
  `graph.json`; its node count matches the published wiki note count.
- [ ] Hovering a graph node shows its note content or preview.
- [ ] Nodes can be dragged; the graph can be panned and zoomed.
- [ ] The read-only notice is visible and no capture form is present.
- [ ] Submit a question answerable from an approved public note.
- [ ] The answer is grounded in that note and the source expander displays the
  matching note ID and body.
- [ ] The app still shows the graph if Groq is unavailable, and reports a
  visible Ask error rather than crashing the page.
- [ ] Cloud logs contain no API key or note content accidentally written by
  diagnostics.

If deployment fails, inspect Community Cloud build/runtime logs. Check the app
entry point, selected branch, Python package installation, secret names, and
model download before changing code or dependencies.

## 6. Ongoing updates and rollback

To update the live app, make and test a change locally, regenerate `graph.json`
when wiki content or links change, review the exact files to publish, and push
only after corpus approval. Community Cloud rebuilds from its configured
repository and branch.

If private material is published accidentally:

1. Remove or redact it from the repository and wiki, then regenerate the graph
   and embedding cache.
2. Push the correction so the app rebuilds.
3. Review Git history and repository visibility: deleting a file in a later
   commit does not remove it from earlier commits. Rotate any exposed
   credential immediately.
4. Contact the hosting provider if cached copies need attention.

## Phase 8 completion checklist

- [ ] Public corpus reviewed and approved.
- [ ] Cloud secrets work without exposing the Groq key.
- [ ] `SECONSELF_READONLY=1` is honored in the deployed app.
- [ ] Required application files, wiki, graph, and cache are in the approved
  deployment commit.
- [ ] Dependencies install and the first model-backed Ask succeeds.
- [ ] Public URL opens without login.
- [ ] Graph and Ask pass the live checks above.
- [ ] URL and setup instructions are added to `README.md` after deployment.

## References

- [Deploy an app — Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app)
- [Secrets management — Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [Manage your app — Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)
