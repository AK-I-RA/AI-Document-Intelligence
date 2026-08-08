from __future__ import annotations
from dataclasses import dataclass
from celery.result import AsyncResult


@dataclass
class JobStatus:
    job_id: str
    state: str
    step: str = ""
    pct: float = 0.0
    result: dict | None = None
    error: str = ""

def submit_ingest_job(
    pdf_path: str,
    chunk_size: int = 400,
    chunk_overlap: int = 50,
) -> str:
    from phases.phase2_async.tasks import ingest_task
    result = ingest_task.delay(pdf_path, chunk_size, chunk_overlap)
    return result.id


def get_job_status(job_id: str) -> JobStatus:
    ar = AsyncResult(job_id)
    state = ar.state

    if state == "PROGRESS":
        meta = ar.info or {}
        return JobStatus(
            job_id=job_id,
            state=state,
            step=meta.get("step", ""),
            pct=meta.get("pct", 0.0),
        )
    elif state == "SUCCESS":
        meta = ar.info or {}
        return JobStatus(
            job_id=job_id,
            state=state,
            step="Done.",
            pct=1.0,
            result=ar.result,
        )

    elif state == "FAILURE":
        meta = ar.info or {}
        return JobStatus(
            job_id=job_id,
            state=state,
            step="error",
            pct=0.0,
            error=str(ar.result),
        )

    else:
        return JobStatus(job_id=job_id, state=state, step="Queued..", pct=0.0)