import sys, os, tempfile, datetime
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import json
import streamlit as st

st.set_page_config(page_title="DocuMind", page_icon="D", layout="wide")

# env + phase detection
missing = [k for k in ["PINECONE_API_KEY"] if not os.getenv(k)]
if missing:
    st.warning(f"Missing: {', '.join(missing)} - add to .env and restart.")

from core.pipeline import async_available
ASYNC = async_available()

try:
    from core.pipeline import phase3_available
    P3 = phase3_available()
except Exception:
    P3 = False

try:
    from core.pipeline import phase4_available
    P4 = phase4_available()
except Exception:
    P4 = False

# sidebar
with st.sidebar:
    st.markdown("# DocuMind")
    st.divider()

    st.caption("CHUNKING")
    chunk_size = st.slider("Chunk size (tokens)", 100, 800, 400, 50, label_visibility="collapsed")
    st.caption(f"Size: {chunk_size} tokens")
    chunk_overlap = st.slider("Chunk overlap (tokens)", 0, 150, 50, 10, label_visibility="collapsed")
    st.caption(f"Overlap: {chunk_overlap} tokens")
    st.divider()

    st.caption("RETRIEVAL")
    top_k = st.slider("Top-k chunks", 1, 15, 5, 1, label_visibility="collapsed")
    st.caption(f"Top-k: {top_k} chunks")
    st.divider()

    st.caption("PHASES")
    for label, done in [
        ("Phase 1 · Core RAG", True),
        ("Phase 2 · Async", ASYNC),
        ("Phase 3 · Guardrails", P3),
        ("Phase 4 · Observability", P4),
    ]:
        st.markdown(f"{'✓' if done else '·'} {label}")

if "jobs" not in st.session_state:
    st.session_state.jobs = []


def ingest_uploaded_pdf(uploaded_file):
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, uploaded_file.name)
    with open(tmp_path, "wb") as tmp:
        tmp.write(uploaded_file.read())

    if ASYNC:
        from core.pipeline import submit_ingest_job
        try:
            with st.spinner("Submitting job..."):
                job_id = submit_ingest_job(tmp_path, chunk_size, chunk_overlap)
            st.success("Job submitted!")
            st.code(job_id)
            st.caption("Track progress in Job Queue tab")
            st.session_state.jobs.insert(0, {"job_id": job_id, "filename": uploaded_file.name})
        except Exception as e:
            st.error(e)
    else:
        from core.pipeline import ingest_document
        pb, cap = st.progress(0), st.empty()
        try:
            r = ingest_document(
                tmp_path, chunk_size, chunk_overlap,
                lambda step, pct=None: (
                    pb.progress(pct) if pct is not None else None,
                    cap.caption(step),
                ),
            )
            if r.status == "error":
                st.error(r.error)
            else:
                st.success(f"Ingested: {r.doc_name}")
                st.caption(f"{r.chunk_count} chunks - {r.page_count} pages - {r.total_tokens:,} tokens")
        except Exception as e:
            st.error(e)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


def stat_cards(items):
    cols = st.columns(len(items))
    for col, (value, label) in zip(cols, items):
        col.markdown(
            f"<div style='text-align:center'>"
            f"<div style='font-size:1.75rem;font-weight:700'>{value}</div>"
            f"<div style='font-size:0.7rem;color:#888;letter-spacing:.05em'>{label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


tab_main, tab_jobs, tab_eval, tab_dash, tab_docs = st.tabs(
    ["Ask", "Job Queue", "Eval", "Dashboard", "Documents"]
)

# ASK
with tab_main:
    left, right = st.columns(2, gap="large")

    with left:
        st.markdown("**Upload**")
        uploaded = st.file_uploader("Upload PDF", type=["pdf"], label_visibility="collapsed")

        if uploaded and st.button("Ingest document", use_container_width=True):
            ingest_uploaded_pdf(uploaded)
        elif not uploaded:
            stat_cards([
                (chunk_size, "CHUNK SIZE"),
                (chunk_overlap, "OVERLAP"),
                (top_k, "TOP-K"),
            ])

    with right:
        st.markdown("**Question**")
        question = st.text_area("Question", placeholder="What is the refund policy?",
                                height=120, label_visibility="collapsed")
        col1, col2 = st.columns([2, 1])
        show_chunks = col2.toggle("Sources", value=True)
        ask         = col1.button("Ask", use_container_width=True)

        def render_sources(sources):
            if show_chunks and sources:
                st.divider()
                st.caption(f"SOURCES - {len(sources)} chunks")
                for i, c in enumerate(sources, 1):
                    pct = int(c["score"] * 100)
                    st.caption(f"#{i} - {c['doc_name']} - p.{c['page_num']} - {pct}% match")
                    st.markdown(c["text"][:400] + ("..." if len(c["text"]) > 400 else ""))
                    st.divider()
            elif not sources:
                st.caption("No chunks found - ingest a document first.")

        if ask:
            if not question.strip():
                st.warning("Enter a question.")
            else:
                try:
                    from core.pipeline import query_document
                    with st.spinner("Searching..."):
                        gen, sources = query_document(question=question, top_k=top_k, stream=True)
                    st.markdown("**Answer**")
                    answer = st.write_stream(gen)
                    st.session_state.last_answer = answer
                    st.session_state.last_sources = sources

                    if P3:
                        try:
                            from phases.phase3_hard.cache import SemanticCache
                            cs = SemanticCache().get_stats()
                            if cs["total"] > 0:
                                st.caption(f"Cache: {cs['hits']} hits / {cs['total']} - {cs['hit_rate']}% hit rate")
                        except Exception:
                            pass

                    render_sources(sources)
                except Exception as e:
                    st.session_state.pop("last_answer", None)
                    st.error(e)
        elif st.session_state.get("last_answer") is not None:
            # Re-render the previous answer so it survives reruns triggered
            # by other tabs' Refresh buttons (st.rerun() re-executes this whole script).
            st.markdown("**Answer**")
            st.write(st.session_state.last_answer)
            render_sources(st.session_state.get("last_sources"))

# JOB QUEUE
with tab_jobs:
    st.markdown("**Ingestion jobs**")
    if not ASYNC:
        st.info("Phase 2 feature - start Redis + Celery to enable.")
        st.code("celery -A phases.phase2_async.worker worker --loglevel=info --pool=solo")
    else:
        if st.button("Refresh", key="refresh_jobs"):
            st.rerun()
        jobs = st.session_state.jobs
        if not jobs:
            st.caption("No jobs yet.")
        else:
            from core.pipeline import get_ingest_status
            for job in jobs:
                s = get_ingest_status(job["job_id"])
                color = {"SUCCESS": "green", "FAILURE": "red",
                         "PROGRESS": "orange", "STARTED": "orange"}.get(s.state, "gray")
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**{job.get('filename','-')}**")
                    c2.markdown(f":{color}[{s.state}]")
                    st.caption(job["job_id"])
                    st.caption(s.step)
                    if s.state == "PROGRESS":
                        st.progress(s.pct)
                    elif s.state == "SUCCESS" and s.result:
                        r = s.result
                        stat_cards([
                            (r.get("chunk_count", "-"), "CHUNKS"),
                            (r.get("page_count", "-"), "PAGES"),
                            (f"{r.get('total_tokens', 0):,}", "TOKENS"),
                        ])
                    elif s.state == "FAILURE":
                        st.error(s.error)


# EVAL & METRICS
with tab_eval:
    st.markdown("**Evaluation metrics**")
    if not P3:
        st.info("Phase 3 feature - becomes active once Phase 3 modules are running.")
    else:
        if st.button("Refresh", key="refresh_eval"):
            st.rerun()
        try:
            from phases.phase3_hard.evaluation import get_metrics_summary, check_drift
            s = get_metrics_summary()
            if s["count"] == 0:
                st.caption("No queries logged yet - ask a question first.")
            else:
                stat_cards([
                    (s["count"], "QUERIES"),
                    (s["avg_faithfulness"], "FAITHFULNESS"),
                    (s["avg_retrieval_score"], "RETRIEVAL"),
                    (f"{s['avg_latency_ms']}ms", "AVG LAT"),
                    (f"{s['p95_latency_ms']}ms", "P95"),
                    (f"{s['cache_hit_rate']}%", "CACHE"),
                ])
                alerts = check_drift()
                for a in alerts:
                    icon = "🔴" if a.severity == "critical" else "🟡"
                    st.warning(f"{icon} {a.metric} dropped {a.drop_pct}% - was {a.baseline}, now {a.current}")
                if not alerts:
                    st.success("No drift detected.")
        except Exception as e:
            st.error(e)

        st.divider()
        st.caption("RAGAS EVALUATION")
        st.markdown("**Upload test set (.json) or a PDF to ingest**")
        eval_upload = st.file_uploader(
            "Upload test set (.json) or a PDF to ingest", type=["json", "pdf"],
            label_visibility="collapsed", key="ragas_upload",
        )

        if eval_upload is not None:
            try:
                if eval_upload.file_id != st.session_state.get("ragas_file_id"):
                    st.session_state.ragas_file_id = eval_upload.file_id
                    st.session_state.pop("ragas_result", None)
                    st.session_state.pop("ragas_pairs", None)

                    if eval_upload.name.lower().endswith(".pdf"):
                        from phases.phase3_hard.ragas_eval import generate_test_set_from_pdf
                        tmp_dir = tempfile.mkdtemp()
                        tmp_path = os.path.join(tmp_dir, eval_upload.name)
                        with open(tmp_path, "wb") as tmp:
                            tmp.write(eval_upload.read())
                        try:
                            from core.pipeline import ingest_document
                            with st.spinner("Ingesting PDF..."):
                                r = ingest_document(tmp_path, chunk_size, chunk_overlap)
                            if r.status == "error":
                                st.error(r.error)
                            else:
                                with st.spinner("Generating test questions from the PDF..."):
                                    st.session_state.ragas_pairs = generate_test_set_from_pdf(tmp_path)
                        finally:
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)
                    else:
                        st.session_state.ragas_pairs = json.load(eval_upload)

                questions_and_truths = st.session_state.get("ragas_pairs")
                if questions_and_truths:
                    st.caption(f"{len(questions_and_truths)} pairs loaded")

                    if st.button("Run RAGAS", key="run_ragas"):
                        from phases.phase3_hard.ragas_eval import (
                            build_test_set_from_pipeline, run_ragas_evaluation,
                        )
                        with st.spinner(f"Running {len(questions_and_truths)} questions through the pipeline..."):
                            test_set = build_test_set_from_pipeline(questions_and_truths, top_k=top_k)
                        with st.spinner("Scoring with RAGAS..."):
                            st.session_state.ragas_result = run_ragas_evaluation(test_set)

                    result = st.session_state.get("ragas_result")
                    if result is not None:
                        if result.get("error"):
                            st.error(result["error"])
                        else:
                            scores = result["scores"]
                            st.caption(
                                f"Faithfulness: {scores['faithfulness']} · "
                                f"Relevancy: {scores['answer_relevancy']} · "
                                f"Precision: {scores['context_precision']} · "
                                f"Recall: {scores['context_recall']}"
                            )
                            st.markdown(f"Report: `{scores['report_path']}`")
            except Exception as e:
                st.error(e)

        st.caption('Format: [{"question":"...","ground_truth":"..."}]')

# ============================
# DASHBOARD (Phase 4)
# ============================

with tab_dash:
    st.markdown("**Cost · latency · usage**")
    if not P4:
        st.info("Phase 4 feature — ask a question to start logging observability data.")
    else:
        try:
            from phases.phase4_obs.metrics_store import get_summary, get_daily_costs, get_latency_series, get_recent_calls
            import pandas as pd

            c1, c2 = st.columns([5, 1])
            with c2:
                days = st.selectbox("Window", [1, 7, 14, 30], index=1,
                                    format_func=lambda x: f"{x}d", label_visibility="collapsed")
                if st.button("Refresh", key="rd"): st.rerun()

            s = get_summary(days=days)
            stat_cards([
                (s["llm_calls"], "CALLS"),
                (f"{s['total_tokens']:,}", "TOKENS"),
                (f"${s['total_cost_usd']:.4f}", "COST"),
                (f"{s['avg_latency_ms']:.0f}ms", "AVG LAT"),
                (f"{s['cache_hit_rate']}%", "CACHE"),
            ])

            daily = get_daily_costs(days=days)
            if daily:
                df = pd.DataFrame(daily).set_index("day")
                st.caption("COST PER DAY ($)")
                st.bar_chart(df[["cost"]], height=160)
                st.caption("QUERIES PER DAY")
                st.bar_chart(df[["calls"]], height=160)

            latency = get_latency_series(days=days)
            if latency:
                st.caption("LATENCY (ms)")
                st.bar_chart(pd.DataFrame(latency).set_index("day")[["avg_ms", "p95_ms"]], height=160, stack=False)

            recent = get_recent_calls(10)
            if recent:
                st.divider()
                st.caption("RECENT CALLS")
                for call in recent:
                    ts = datetime.datetime.fromtimestamp(call["ts"]).strftime("%H:%M:%S")
                    hit = "⚡" if call["cache_hit"] else "→"
                    st.caption(f"{ts} {hit} {call['model']} · {call['total_tokens']} tok · ${call['cost_usd']:.5f}")
                    st.markdown((call.get("question") or "")[:80])
                    st.divider()

        except Exception as e:
            st.error(e)

# DOCUMENTS
with tab_docs:
    st.markdown("**Indexed documents**")
    if st.button("Refresh", key="refresh_docs"):
        st.rerun()
    try:
        from core.vector_store import list_indexed_documents, get_index_stats
        stats = get_index_stats()
        st.caption(f"{stats['total_vectors']:,} vectors - {stats['dimension']} dims - cosine")
        for doc in list_indexed_documents():
            c1, c2 = st.columns([6, 1])
            c1.markdown(f"`{doc}`")
            if c2.button("Remove", key=f"d_{doc}"):
                from core.pipeline import remove_document
                remove_document(doc)
                st.rerun()
    except Exception as e:
        st.error(e)