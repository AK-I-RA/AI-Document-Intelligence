from __future__ import annotations
import os
import time
from dataclasses import dataclass
from pathlib import Path
from core.ingestion import ingest_pdf
from core.embeddings import embed_chunks, embed_query
from core.vector_store import upsert_chunks, query_index, delete_document, get_index_stats
from core.generation import generate_answer, LLM_MODEL, SYSTEM_PROMPT, USER_TEMPLATE, _build_context_block

OFFTOPIC_SCORE_THRESHOLD = float(os.getenv("OFFTOPIC_SCORE_THRESHOLD", "0.35"))


def async_available() -> bool:
    try:
        import redis, celery
    except ImportError:
        return False
    return bool(os.getenv("REDIS_URL") or os.getenv("CELERY_RESULT_BACKEND"))


def phase3_available() -> bool:
    try:
        from phases.phase3_hard.guardrails import check_input
        return True
    except ImportError:
        return False

def _phase4_available() -> bool:
    try:
        from phases.phase4_obs.tracker import track_llm_call
        return True
    except ImportError:
        return False


@dataclass
class IngestResult:
    doc_name: str
    chunk_count: int
    page_count: int
    total_tokens: int
    status: str = "success"
    error: str = ""


@dataclass
class QueryResults:
    answer: str
    sources: list[dict]
    query: str
    top_k: int = 5
    cache_hit: bool = False
    latency_ms: float = 0.0


def ingest_document(
    pdf_path: str | Path,
    chunk_size: int = 400,
    chunk_overlap: int = 50,
    progress_callback=None,

) -> IngestResult:
    
    pdf_path = Path(pdf_path)
    t0 = time.time()
    
    try:
        if progress_callback:
            progress_callback("Extracting and chunking", 0.10)
        chunks = ingest_pdf(pdf_path, chunk_size, chunk_overlap)
        if progress_callback:
            progress_callback("Generating embeddings", 0.40)
        embeddings = embed_chunks(chunks)
        if progress_callback:
            progress_callback("Uploading to the vector store", 0.80)
        upsert_chunks(chunks, embeddings)
        if progress_callback:
            progress_callback("Done", 1.0)

        pages = sorted(set(c.page_num for c in chunks))
        result = IngestResult(
            doc_name=pdf_path.stem,
            chunk_count=len(chunks),
            page_count=len(pages),
            total_tokens=sum(c.token_count for c in chunks),
        )
        #phase 4
        if _phase4_available():
            from phases.phase4_obs.tracker import track_ingestion
            track_ingestion(
                doc_name=result.doc_name,
                chunk_count=result.chunk_count,
                page_count=result.page_count,
                total_tokens=result.total_tokens,
                duration_ms=(time.time() - t0) * 1000,
            )
        return result

    except Exception as e:
        return IngestResult(
            doc_name=pdf_path.stem,
            chunk_count=0,
            page_count=0,
            total_tokens=0,
            status="error",
            error=str(e),
        )


# phase 2: Async
def submit_ingest_job(
    pdf_path: str | Path,
    chunk_size: int = 400,
    chunk_overlap: int = 50,
) -> str:
    if not async_available():
        raise RuntimeError("Phase 2 requires Redis. Set REDIS_URL in .env and start the celery worker.")
    from phases.phase2_async.job_status import submit_ingest_job as _submit
    return _submit(str(pdf_path), chunk_size, chunk_overlap)


def get_ingest_status(job_id: str):
    from phases.phase2_async.job_status import get_job_status
    return get_job_status(job_id)


def query_document(
    question: str,
    top_k: int = 5,
    stream: bool = True,
    filter_doc: str | None = None,
):
    question = question.strip()
    t0 = time.time()
    if not question:
        raise ValueError("Question cannot be empty.")
    cache_hit = False

    # Phase 3: input guardrails
    if phase3_available():
        from phases.phase3_hard.guardrails import check_input, GuardrailError
        try:
            question = check_input(question)
        except GuardrailError as e:
            reason = e.reason
            latency_ms = (time.time() - t0) * 1000
            _log_metrics(question, f"Blocked: {reason}", [], latency_ms, cache_hit=False)
            if stream:
                def _blocked():
                    yield f"Blocked: {reason}"
                return _blocked(), []
            else:
                return QueryResults(
                    answer=f"Blocked: {reason}",
                    sources=[],
                    query=question,
                    top_k=top_k,
                    latency_ms=latency_ms,
                )

    q_embedding = embed_query(question)

    # Phase 3: semantic cache
    if phase3_available() and async_available():
        try:
            from phases.phase3_hard.cache import SemanticCache
            cache = SemanticCache()
            cached = cache.lookup(q_embedding)
            if cached:
                cache_hit = True
                latency_ms = (time.time() - t0) * 1000
                _log_metrics(question, cached["answer"], [], latency_ms, cache_hit=True)
                if stream:
                    def _cached_gen():
                        yield cached["answer"]
                        yield f"\n\nCache hit (similarity: {cached['score']})"
                    return _cached_gen(), []
                else:
                    return QueryResults(
                        answer=cached["answer"],
                        sources=[],
                        query=question,
                        top_k=top_k,
                        cache_hit=True,
                        latency_ms=latency_ms,
                    )
        except Exception:
            pass

    sources = query_index(q_embedding, top_k=top_k, filter_doc=filter_doc)

    best_score = max((s.get("score", 0.0) for s in sources), default=0.0)
    if best_score < OFFTOPIC_SCORE_THRESHOLD:
        reason = ("This question doesn't appear to relate to your uploaded "
                  "documents. DocuMind only answers questions about them.")
        latency_ms = (time.time() - t0) * 1000
        _log_metrics(question, reason, [], latency_ms, cache_hit=False)
        if stream:
            def _offtopic():
                yield f"🚫 **Off-topic:** {reason}"
            return _offtopic(), []
        else:
            return QueryResults(
                answer=f"🚫 Off-topic: {reason}",
                sources=[],
                query=question,
                top_k=top_k,
                latency_ms=latency_ms,
            )
    # phase 4
    ret_ms = (time.time() - t0) * 1000

    if _phase4_available():
        from phases.phase4_obs.tracker import track_retrieval
        track_retrieval(sources, ret_ms)

    context_block = _build_context_block(sources)
    user_message = USER_TEMPLATE.format(context_block=context_block, question=question)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    if stream:
        t_gen = time.time()

        def _stream_with_hooks():
            full_answer = ""
            for delta in generate_answer(question, sources, stream=True):
                full_answer += delta
                yield delta
            gen_ms = (time.time() - t_gen) * 1000

            if phase3_available():
                try:
                    from phases.phase3_hard.guardrails import check_output
                    checked = check_output(full_answer, sources)
                    warning = checked[len(full_answer):]
                    if warning:
                        yield warning
                except Exception:
                    pass
                try:
                    if async_available():
                        from phases.phase3_hard.cache import SemanticCache
                        SemanticCache().store(q_embedding, question, full_answer)
                except Exception:
                    pass

            _log_metrics(question, full_answer, sources,
                         (time.time() - t0) * 1000, cache_hit=False)

            # Phase 4: log LLM call
            if _phase4_available():
                from phases.phase4_obs.tracker import track_llm_call
                track_llm_call(messages=messages, answer=full_answer, model=LLM_MODEL,
                               latency_ms=gen_ms, cache_hit=False, question=question)

        return _stream_with_hooks(), sources

    else:
        t_gen = time.time()
        answer = generate_answer(question, sources, stream=False)
        gen_ms = (time.time() - t_gen) * 1000

        if phase3_available():
            try:
                from phases.phase3_hard.guardrails import check_output
                answer = check_output(answer, sources)
            except Exception:
                pass

            try:
                if async_available():
                    from phases.phase3_hard.cache import SemanticCache
                    SemanticCache().store(q_embedding, question, answer)
            except Exception:
                pass

        _log_metrics(question, answer, sources,
                     (time.time() - t0) * 1000, cache_hit=False)

        if _phase4_available():
            from phases.phase4_obs.tracker import track_llm_call
            track_llm_call(messages=messages, answer=answer, model=LLM_MODEL,
                           latency_ms=gen_ms, cache_hit=False, question=question)

        return QueryResults(answer=answer, sources=sources, query=question, top_k=top_k,
                           cache_hit=False, latency_ms=(time.time() - t0) * 1000)



def _log_metrics(question, answer, sources, latency_ms, cache_hit):
    try:
        from phases.phase3_hard.evaluation import (
            log_query, score_faithfulness, QueryMetrics
        )
        avg_score = (sum(s.get("score", 0) for s in sources) / len(sources)) if sources else 0.0
        metrics = QueryMetrics(
            question=question,
            answer=answer[:500],
            retrieved_chunks=len(sources),
            retrieval_score=round(avg_score, 4),
            faithfulness=score_faithfulness(answer, sources),
            latency_ms=round(latency_ms, 1),
            cache_hit=cache_hit,
            timestamp=time.time(),
        )
        log_query(metrics)
    except Exception:
        pass


def remove_document(doc_name: str) -> None:
    delete_document(doc_name)


def index_stats() -> dict:
    return get_index_stats()


def phase4_available() -> bool:
    return _phase4_available()