"""
frontend/app.py — SERA Vault OS v0.2 Streamlit frontend.

Run with: streamlit run frontend/app.py
"""

import sys
from pathlib import Path
from datetime import date

# Ensure project root is on sys.path so SERA modules are importable.
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from vault import create_client_vault, list_vaults
from engine.hypothesis import generate as generate_hypotheses
from engine.experiment import create as create_experiment
from engine.results import log_result, list_results
from engine.winner import select_winner
from reports.generator import generate as generate_report
from shared.config import PROJECT_ROOT, CONFIG
from shared.file_io import read_markdown, write_markdown, ensure_dir


# ─────────────────────────── vault helpers ──────────────────────────────────

def _clients_root() -> Path:
    return PROJECT_ROOT / CONFIG["paths"]["clients_root"]


def _reports_root() -> Path:
    return PROJECT_ROOT / CONFIG["paths"]["reports_root"]


def list_briefs(client: str) -> list:
    d = _clients_root() / client / "briefs"
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("brief-*.md"))


def list_hypotheses(client: str) -> list:
    d = _clients_root() / client / "hypotheses"
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("hyp-*.md"))


def list_experiments(client: str) -> list:
    d = _clients_root() / client / "experiments"
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("exp-*.md"))


def list_reports(client: str) -> list:
    d = _reports_root() / client
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("report-*.md"))


def next_brief_id(client: str) -> str:
    existing = list_briefs(client)
    return f"brief-{len(existing) + 1:03d}"


def create_brief(client: str, title: str, objective: str, questions: str) -> str:
    brief_id = next_brief_id(client)
    brief_path = _clients_root() / client / "briefs" / f"{brief_id}.md"
    ensure_dir(brief_path.parent)
    body = (
        f"# Research Brief: {title}\n\n"
        f"## Objective\n\n{objective}\n\n"
        f"## Research Questions\n\n{questions}\n"
    )
    write_markdown(brief_path, body, {
        "title": title,
        "client_id": client,
        "status": "active",
        "created": date.today().isoformat(),
    })
    return brief_id


def read_artifact(path: Path):
    if not path.exists():
        return {}, ""
    return read_markdown(path)


# ─────────────────────────── page config ────────────────────────────────────

st.set_page_config(
    page_title="SERA Vault OS",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────── sidebar ────────────────────────────────────────

with st.sidebar:
    st.title("🔬 SERA Vault OS")
    st.caption("v0.2 — Research Frontend")
    st.divider()

    st.subheader("Client / Topic")
    vaults = list_vaults()

    with st.expander("➕ New Client", expanded=len(vaults) == 0):
        new_client_input = st.text_input(
            "Client ID (slug)",
            placeholder="acme-corp",
            key="new_client_input",
        )
        if st.button("Create Client", key="create_client_btn"):
            slug = new_client_input.strip()
            if slug:
                try:
                    create_client_vault(slug)
                    st.success(f"Created: {slug}")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            else:
                st.warning("Enter a client ID first.")

    if vaults:
        selected_client = st.selectbox("Select Client", vaults, key="selected_client")
    else:
        st.info("No clients yet. Create one above.")
        selected_client = None

    if selected_client:
        st.divider()
        b = list_briefs(selected_client)
        h = list_hypotheses(selected_client)
        e = list_experiments(selected_client)
        st.caption(
            f"**{selected_client}**  \n"
            f"Briefs: {len(b)} · Hyps: {len(h)} · Exps: {len(e)}"
        )

# ─────────────────────────── guard ──────────────────────────────────────────

st.title("SERA Research Workflow")

if not selected_client:
    st.info("Create or select a client from the sidebar to begin.")
    st.stop()

# ─────────────────────────── tabs ───────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 Brief",
    "💡 Hypotheses",
    "🧪 Experiments",
    "📊 Results",
    "🏆 Winner",
    "📄 Report",
])

# ── TAB 1: Brief ─────────────────────────────────────────────────────────────

with tab1:
    st.header("Research Brief")
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Create New Brief")
        brief_title = st.text_input(
            "Title",
            placeholder="Onboarding Conversion Study",
            key="brief_title",
        )
        brief_obj = st.text_area(
            "Objective",
            placeholder="Increase trial-to-paid conversion from 8% to 15% within 60 days.",
            height=100,
            key="brief_objective",
        )
        brief_qs = st.text_area(
            "Research Questions (one per line)",
            placeholder="1. What are the top friction points?\n2. Which steps correlate with conversion?",
            height=120,
            key="brief_questions",
        )
        if st.button("Create Brief", type="primary", key="create_brief_btn"):
            if brief_title.strip() and brief_obj.strip():
                try:
                    bid = create_brief(
                        selected_client,
                        brief_title.strip(),
                        brief_obj.strip(),
                        brief_qs.strip(),
                    )
                    st.success(f"Created: `{bid}`")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error: {exc}")
            else:
                st.warning("Title and Objective are required.")

    with col_right:
        st.subheader("Existing Briefs")
        briefs = list_briefs(selected_client)
        if not briefs:
            st.info("No briefs yet. Create one on the left.")
        else:
            chosen = st.selectbox("View", briefs, key="brief_view_select")
            fm, body = read_artifact(
                _clients_root() / selected_client / "briefs" / f"{chosen}.md"
            )
            if fm:
                st.caption(
                    f"Status: `{fm.get('status', '—')}` · Created: {fm.get('created', '—')}"
                )
            st.markdown(body)

# ── TAB 2: Hypotheses ────────────────────────────────────────────────────────

with tab2:
    st.header("Hypotheses")
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Generate Hypotheses")
        briefs = list_briefs(selected_client)
        if not briefs:
            st.warning("Create a research brief first (Brief tab).")
        else:
            hyp_brief = st.selectbox("Brief to use", briefs, key="hyp_brief_select")
            if st.button("Generate 3 Hypotheses", type="primary", key="gen_hyp_btn"):
                with st.spinner("Generating…"):
                    try:
                        ids = generate_hypotheses(selected_client, hyp_brief)
                        st.success(f"Created: {', '.join(ids)}")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Error: {exc}")

    with col_right:
        st.subheader("Existing Hypotheses")
        hyps = list_hypotheses(selected_client)
        if not hyps:
            st.info("No hypotheses yet.")
        else:
            chosen = st.selectbox("View", hyps, key="hyp_view_select")
            fm, body = read_artifact(
                _clients_root() / selected_client / "hypotheses" / f"{chosen}.md"
            )
            if fm:
                st.caption(
                    f"Status: `{fm.get('status', '—')}` · Brief: `{fm.get('brief_id', '—')}`"
                )
            st.markdown(body)

# ── TAB 3: Experiments ───────────────────────────────────────────────────────

with tab3:
    st.header("Experiments")
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Create Experiment")
        hyps = list_hypotheses(selected_client)
        if not hyps:
            st.warning("Generate hypotheses first (Hypotheses tab).")
        else:
            exp_hyp = st.selectbox("Hypothesis to test", hyps, key="exp_hyp_select")
            if st.button("Create Experiment", type="primary", key="create_exp_btn"):
                with st.spinner("Creating…"):
                    try:
                        eid = create_experiment(selected_client, exp_hyp)
                        st.success(f"Created: `{eid}`")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Error: {exc}")

    with col_right:
        st.subheader("Existing Experiments")
        exps = list_experiments(selected_client)
        if not exps:
            st.info("No experiments yet.")
        else:
            chosen = st.selectbox("View", exps, key="exp_view_select")
            fm, body = read_artifact(
                _clients_root() / selected_client / "experiments" / f"{chosen}.md"
            )
            if fm:
                st.caption(
                    f"Status: `{fm.get('status', '—')}` · Hypothesis: `{fm.get('hypothesis_id', '—')}`"
                )
            st.markdown(body)

# ── TAB 4: Results ───────────────────────────────────────────────────────────

with tab4:
    st.header("Log Results")
    exps = list_experiments(selected_client)
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Log a Result")
        if not exps:
            st.warning("Create an experiment first (Experiments tab).")
        else:
            res_exp = st.selectbox("Experiment", exps, key="result_exp_select")
            res_condition = st.text_input(
                "Condition (e.g. A, B, control)",
                placeholder="A",
                key="result_condition",
            )
            res_metric = st.text_input(
                "Metric",
                placeholder="conversion_rate",
                key="result_metric",
            )
            res_value = st.number_input(
                "Value",
                value=0.0,
                step=0.01,
                format="%.4f",
                key="result_value",
            )
            res_notes = st.text_area("Notes (optional)", height=80, key="result_notes")

            if st.button("Log Result", type="primary", key="log_result_btn"):
                if res_condition.strip() and res_metric.strip():
                    try:
                        rid = log_result(
                            selected_client,
                            res_exp,
                            res_condition.strip(),
                            res_metric.strip(),
                            float(res_value),
                            res_notes.strip(),
                        )
                        st.success(f"Logged: `{rid}`")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Error: {exc}")
                else:
                    st.warning("Condition and Metric are required.")

    with col_right:
        st.subheader("Logged Results")
        if not exps:
            st.info("No experiments yet.")
        else:
            view_exp = st.selectbox(
                "View results for", exps, key="result_view_select"
            )
            results = list_results(selected_client, view_exp)
            if not results:
                st.info("No results logged for this experiment yet.")
            else:
                rows = [
                    {
                        "ID": r.get("id", ""),
                        "Condition": r.get("condition", ""),
                        "Metric": r.get("metric", ""),
                        "Value": r.get("value", ""),
                        "Winner": r.get("winner", ""),
                        "Status": r.get("status", ""),
                    }
                    for r in results
                ]
                st.dataframe(rows, use_container_width=True)

# ── TAB 5: Winner ────────────────────────────────────────────────────────────

with tab5:
    st.header("Select Winner")
    exps = list_experiments(selected_client)

    if not exps:
        st.warning("Create experiments and log results first.")
    else:
        winner_exp = st.selectbox("Experiment", exps, key="winner_exp_select")
        results = list_results(selected_client, winner_exp)

        if results:
            st.subheader("Current Results")
            rows = [
                {
                    "ID": r.get("id", ""),
                    "Condition": r.get("condition", ""),
                    "Metric": r.get("metric", ""),
                    "Value": r.get("value", ""),
                    "Winner": r.get("winner", ""),
                }
                for r in results
            ]
            st.dataframe(rows, use_container_width=True)
        else:
            st.info("No results logged yet. Log results in the Results tab first.")

        if st.button("Select Winner", type="primary", key="select_winner_btn"):
            if not results:
                st.warning("Log results for this experiment first.")
            else:
                try:
                    summary = select_winner(selected_client, winner_exp)
                    st.success("Winner selected!")
                    st.balloons()
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Winner ID", summary["winner_id"])
                    c2.metric("Condition", summary["winner_condition"])
                    c3.metric("Value", f"{float(summary['winner_value']):.4f}")
                    st.info(
                        f"**{summary['winner_condition']}** wins on "
                        f"**{summary['winner_metric']}** = {summary['winner_value']} "
                        f"({summary['total_results']} results compared)"
                    )
                except ValueError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Error: {exc}")

# ── TAB 6: Report ────────────────────────────────────────────────────────────

with tab6:
    st.header("Generate Report")
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("Generate")
        briefs = list_briefs(selected_client)
        if not briefs:
            st.warning("Create a research brief first (Brief tab).")
        else:
            report_brief = st.selectbox(
                "Brief", briefs, key="report_brief_select"
            )
            if st.button("Generate Report", type="primary", key="gen_report_btn"):
                with st.spinner("Compiling report…"):
                    try:
                        rpath = generate_report(selected_client, report_brief)
                        st.success(f"Saved: `{rpath.name}`")
                        st.session_state["preview_report"] = str(rpath)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Error: {exc}")

        existing_reports = list_reports(selected_client)
        if existing_reports:
            st.divider()
            st.subheader("Existing Reports")
            chosen_rep = st.selectbox(
                "Select to preview", existing_reports, key="report_view_select"
            )
            if st.button("Preview", key="preview_report_btn"):
                rp = _reports_root() / selected_client / f"{chosen_rep}.md"
                st.session_state["preview_report"] = str(rp)
                st.rerun()

    with col_right:
        st.subheader("Preview")
        preview_path = st.session_state.get("preview_report")
        if preview_path:
            rp = Path(preview_path)
            if rp.exists():
                _, body = read_artifact(rp)
                st.markdown(body)
            else:
                st.info("Report file not found. Generate it first.")
        else:
            st.info(
                "Generate a report or select an existing one on the left to preview here."
            )
