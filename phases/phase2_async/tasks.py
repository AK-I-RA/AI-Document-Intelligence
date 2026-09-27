from __future__ import annotations
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
load_dotenv()

from phases.phase2_async.worker import celery_app
from core.ingestion import ingest_pdf
from core.embeddings import embed_chunks
from core.vector_store import upsert_chunks


@celery_app.task(bind=True, name="documind.ingest")
def ingest_task(
    self,
    pdf_path: str,
    chunk_size: int = 400,
    chunk_overlap: int = 50,
) -> dict:

    pdf_path = Path(pdf_path)

    def progress(step: str, pct: float):
        self.update_state(
            state="PROGRESS",
            meta={"step": step, "pct": round(pct, 2)},
        )

    # Let exceptions propagate: Celery records FAILURE itself. Setting FAILURE
    # manually with a plain dict meta crashes the worker (missing exc_type).
    if not pdf_path.exists():
        raise FileNotFoundError(f"Uploaded file no longer exists: {pdf_path}")

    try:
        progress("Extracting & chunking pdf...", 0.10)
        chunks = ingest_pdf(pdf_path, chunk_size, chunk_overlap)

        progress("Generating embeddings...", 0.40)
        embeddings = embed_chunks(chunks)

        progress("Uploading to vector store...", 0.80)
        upsert_chunks(chunks, embeddings)

        progress("Done.", 1.0)
    finally:
        try:
            pdf_path.unlink(missing_ok=True)
        except OSError:
            pass

    pages = sorted(set(c.page_num for c in chunks))
    return {
        "status": "success",
        "doc_name": pdf_path.stem,
        "chunk_count": len(chunks),
        "page_count": len(pages),
        "total_tokens": sum(c.token_count for c in chunks),
    }