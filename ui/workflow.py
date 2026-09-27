"""Ingest and job-status helpers shared by the landing workspace and the dashboard."""
import os
import tempfile

import streamlit as st

WORKER_CMD = "celery -A phases.phase2_async.worker worker --loglevel=info --pool=solo"


def worker_available() -> bool:
    # A --pool=solo worker can't answer pings while busy, so a job in
    # progress also counts as proof that a worker is running.
    from core.pipeline import workers_online, get_ingest_status
    if workers_online():
        return True
    for job in st.session_state.get("jobs", []):
        try:
            if get_ingest_status(job["job_id"]).state in ("STARTED", "PROGRESS"):
                return True
        except Exception:
            pass
    return False


def ingest(uploaded_file, chunk_size: int, chunk_overlap: int, on_progress=None) -> dict:
    """Index an uploaded PDF, in the background when a Celery worker is running, otherwise inline.

    Returns a doc record: {"name", "status": "ready" | "indexing" | "failed", "job_id", "detail", "pct"}.
    """
    from core.pipeline import async_available

    doc = {"name": uploaded_file.name, "status": "failed", "job_id": None, "detail": "", "pct": 0.0}
    tmp_path = os.path.join(tempfile.mkdtemp(), uploaded_file.name)
    with open(tmp_path, "wb") as tmp:
        tmp.write(uploaded_file.getvalue())

    if async_available() and worker_available():
        from core.pipeline import submit_ingest_job
        try:
            # the worker deletes the temp file when it's done
            doc["job_id"] = submit_ingest_job(tmp_path, chunk_size, chunk_overlap)
            doc.update(status="indexing", detail="Queued")
            st.session_state.setdefault("jobs", []).insert(0, {"job_id": doc["job_id"], "filename": doc["name"]})
        except Exception as e:
            doc["detail"] = str(e)
        return doc

    from core.pipeline import ingest_document
    try:
        r = ingest_document(tmp_path, chunk_size, chunk_overlap, on_progress)
        if r.status == "error":
            doc["detail"] = r.error
        else:
            doc.update(status="ready", pct=1.0,
                       detail=f"{r.chunk_count:,} chunks · {r.page_count} pages")
    except Exception as e:
        doc["detail"] = str(e)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return doc


def refresh(doc: dict) -> bool:
    """Update a background-indexing doc from its Celery job. Returns True if its status changed."""
    if doc["status"] != "indexing" or not doc.get("job_id"):
        return False
    from core.pipeline import get_ingest_status
    try:
        s = get_ingest_status(doc["job_id"])
    except Exception:
        return False
    if s.state == "SUCCESS" and s.result:
        doc.update(status="ready", pct=1.0,
                   detail=f"{s.result.get('chunk_count', 0):,} chunks · {s.result.get('page_count', 0)} pages")
        return True
    if s.state == "FAILURE":
        doc.update(status="failed", detail=s.error or "Indexing failed")
        return True
    doc.update(pct=s.pct or 0.0, detail=s.step or "Queued")
    return False


def summary(doc: dict) -> str:
    """One chat line describing a doc record."""
    name = f"**{doc['name']}**"
    if doc["status"] == "ready":
        return f"Indexed {name}: {doc['detail']}. Ask me anything about it."
    if doc["status"] == "indexing":
        return f"Indexing {name} in the background. I'll answer questions about it once it's ready."
    return f"Couldn't index {name}: {doc['detail']}"
