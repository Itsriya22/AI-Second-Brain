# SecondSelf

SecondSelf is a personal knowledge system that captures notes, classifies them with PARA, links related ideas, visualizes the knowledge graph, and answers questions from your own notes.

## Run locally

Create `.env` in the project root with `GROQ_API_KEY=your-key`, then run:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

For local use, install the pinned packages from `requirements.txt` into a Python virtual environment first.

## Deploy on Streamlit Community Cloud

Select this GitHub repository, the `main` branch, and `app.py` as the entry point. Add `GROQ_API_KEY` in the app's Streamlit secrets settings and set `SECONSELF_READONLY=1` there as well. Streamlit Cloud secrets are read through `st.secrets`; local `.env` and environment variables continue to work. The app has no capture form, and read-only mode is identified in the UI.

The app uses `all-MiniLM-L6-v2` for query embeddings. The first question on a new Cloud instance may download model weights from Hugging Face and use additional startup time and memory. `data/embeddings.npz` caches corpus vectors but does not include those model weights.

See [the deployment plan](./docs/deployment-plan.md) for privacy review, setup, and live verification steps.

Live app: [SecondSelf on Streamlit Community Cloud](https://ai-second-brain-nfkx63fnajjgmeypjesgq8.streamlit.app/)

**Privacy warning:** A public GitHub repository and public Streamlit app make committed wiki Markdown, graph data, and embeddings publicly accessible. Review every note before publishing; never commit `.env`, API keys, raw captures, or original files.
