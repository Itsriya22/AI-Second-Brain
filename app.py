"""SecondSelf's interactive knowledge graph and grounded Q&A app."""

import json
from pathlib import Path
import re

import streamlit as st

from ask import ask
from config import GRAPH_PATH, ROOT_DIR, WIKI_DIR
from lib.runtime_config import get_runtime_setting
from lib.wiki import read_wiki_note

_GRAPH_HEIGHT = 650
_PARA_COLORS = {
    "projects": "#f97316",
    "areas": "#14b8a6",
    "resources": "#eab308",
    "archives": "#94a3b8",
}
_NOTE_ID_PATTERN = re.compile(r"^[0-9a-f]{8}$")


def _is_read_only() -> bool:
    value = get_runtime_setting("SECONSELF_READONLY")
    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _read_graph(graph_path: Path = GRAPH_PATH) -> dict[str, object]:
    with graph_path.open(encoding="utf-8") as graph_file:
        graph = json.load(graph_file)
    if not isinstance(graph, dict):
        raise ValueError("Graph JSON must be an object.")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Graph JSON must contain node and edge lists.")
    return graph


def _safe_json(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _graph_html(graph: dict[str, object]) -> str:
    graph_json = _safe_json({"nodes": graph["nodes"], "edges": graph["edges"]})
    colors = _safe_json(_PARA_COLORS)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    html, body {{ margin: 0; background: #0e1117; color: #e5e7eb; font-family: sans-serif; }}
    #network {{ width: 100%; height: {_GRAPH_HEIGHT}px; border: 1px solid #30343b; border-radius: 12px; }}
    #empty {{ display: none; height: {_GRAPH_HEIGHT}px; align-content: center; text-align: center; color: #a1a1aa; }}
  </style>
</head>
<body>
  <div id="network"></div>
  <div id="empty">Your graph is empty. Capture and classify notes to grow your brain.</div>
  <script>
    const graph = {graph_json};
    const colors = {colors};
    const container = document.getElementById("network");
    const empty = document.getElementById("empty");
    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({{
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }}[char]));
    if (!graph.nodes.length) {{
      container.style.display = "none";
      empty.style.display = "grid";
    }} else {{
      const nodes = new vis.DataSet(graph.nodes.map((node) => ({{
        id: node.id,
        label: node.label,
        title: `<strong>${{escapeHtml(node.label)}}</strong><br>${{escapeHtml(node.summary)}}<br><br>${{escapeHtml(node.preview)}}`,
        color: {{
          background: colors[node.category] || "#64748b",
          border: "#e2e8f0",
          highlight: {{ background: colors[node.category] || "#64748b", border: "#ffffff" }}
        }},
        shape: "dot",
        size: 18,
        font: {{ color: "#f8fafc", face: "sans-serif", size: 15 }},
        borderWidth: 2,
        shadow: {{ enabled: true, color: colors[node.category] || "#64748b", size: 12, x: 0, y: 0 }}
      }})));
      const edges = new vis.DataSet(graph.edges.map((edge) => ({{
        from: edge.from,
        to: edge.to,
        value: edge.weight,
        title: escapeHtml(edge.reason || "Related note"),
        color: {{ color: "#64748b", highlight: "#cbd5e1" }},
        smooth: {{ type: "continuous" }}
      }})));
      const network = new vis.Network(container, {{ nodes, edges }}, {{
        autoResize: true,
        interaction: {{
          hover: true,
          dragNodes: true,
          dragView: true,
          zoomView: true,
          navigationButtons: true,
          keyboard: true,
          tooltipDelay: 120
        }},
        physics: {{
          enabled: true,
          solver: "barnesHut",
          barnesHut: {{ gravitationalConstant: -5500, centralGravity: 0.25, springLength: 150 }},
          stabilization: {{ iterations: 150, fit: true }}
        }},
        edges: {{ width: 1.5 }}
      }});
      network.once("stabilizationIterationsDone", () => network.fit({{ padding: 100, animation: {{ duration: 400 }} }}));
    }}
  </script>
</body>
</html>"""


def _render_graph(graph: dict[str, object]) -> None:
    nodes = graph["nodes"]
    if not nodes:
        st.info("Your graph is empty. Capture and classify notes to grow your brain.")
        return
    st.iframe(_graph_html(graph), height=_GRAPH_HEIGHT)
    legend = "　".join(
        f"{color} **{category.title()}**"
        for category, color in (
            ("projects", "🟠"),
            ("areas", "🟢"),
            ("resources", "🟡"),
            ("archives", "⚪"),
        )
    )
    st.markdown(legend)


def _render_sources(sources: list[dict[str, object]]) -> None:
    with st.expander(f"Sources ({len(sources)})"):
        for source in sources:
            note_id = source.get("id")
            title = source.get("title")
            relative_path = source.get("path")
            score = source.get("score")
            if (
                not isinstance(note_id, str)
                or not _NOTE_ID_PATTERN.fullmatch(note_id)
                or not isinstance(relative_path, str)
            ):
                st.warning("Skipped a source with invalid metadata.")
                continue
            note_path = (ROOT_DIR / relative_path).resolve()
            try:
                note_path.relative_to((ROOT_DIR / WIKI_DIR.relative_to(ROOT_DIR)).resolve())
            except ValueError:
                st.warning(f"Source {note_id} is outside the wiki folder.")
                continue
            try:
                note = read_wiki_note(note_path)
            except (OSError, ValueError) as exc:
                st.error(f"Could not load source {note_id}: {exc}")
                continue
            if note.id != note_id:
                st.warning(f"Source ID did not match its wiki file: {note_id}.")
                continue
            label = f"{title or note.title} · {score:.3f}" if isinstance(score, (int, float)) else str(title or note.title)
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.caption(f"Note ID: {note.id}")
                st.markdown(note.body)


def _render_ask() -> None:
    st.subheader("Ask your brain")
    with st.form("ask_brain"):
        question = st.text_input(
            "Ask a question about your notes",
            placeholder="What am I working on?",
            max_chars=2_000,
        )
        submitted = st.form_submit_button("Ask")
    if submitted:
        with st.spinner("Searching your notes..."):
            st.session_state["secondself_ask_result"] = ask(question)

    result = st.session_state.get("secondself_ask_result")
    if not isinstance(result, dict):
        return
    error = result.get("error")
    if error:
        st.error(str(error))
        return
    answer = result.get("answer")
    if isinstance(answer, str) and answer:
        st.markdown(answer)
    sources = result.get("sources")
    if isinstance(sources, list) and sources:
        _render_sources(sources)


def main() -> None:
    st.set_page_config(page_title="SecondSelf", page_icon="🧠", layout="wide")
    st.title("SecondSelf")
    st.caption("Your personal knowledge graph — explore connections and ask what your notes know.")
    if _is_read_only():
        st.info("Read-only mode: capturing notes is disabled in this app.")
    st.subheader("Knowledge graph")
    try:
        graph = _read_graph()
    except FileNotFoundError:
        st.info("No graph.json found yet. Run `python build_graph.py` to create it.")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        st.error(f"Could not load graph.json: {exc}")
    else:
        _render_graph(graph)
    _render_ask()


if __name__ == "__main__":
    main()
