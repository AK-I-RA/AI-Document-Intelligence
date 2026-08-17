from __future__ import annotations
import tiktoken
from phases.phase4_obs.metrics_store import log_llm_call, log_retrieval, log_ingestion

_ENCODER = tiktoken.get_encoding("cl100k_base")


def _count(text: str) -> int:
    return len(_ENCODER.encode(text))


def track_llm_call(
    messages: list[dict],
    answer: str,
    model: str,
    latency_ms: float,
    cache_hit: bool = False,
    question: str = "",
):
    try:
        input_tok = _count(" ".join(m.get("content", "") for m in messages))
        output_tok = _count(answer)
        log_llm_call(
            model=model,
            input_tokens=input_tok,
            output_tokens=output_tok,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            question=question,
        )
    except Exception:
        pass


def track_retrieval(sources: list[dict], latency_ms: float):
    try:
        scores = [s.get("score", 0.0) for s in sources]
        doc_name = sources[0].get("doc_name", "") if sources else ""
        log_retrieval(top_k=len(sources), scores=scores, latency_ms=latency_ms, doc_name=doc_name)
    except Exception:
        pass

def track_ingestion(doc_name: str, chunk_count: int, page_count: int, total_tokens: int, duration_ms: float):
    try:
        log_ingestion(doc_name, chunk_count, page_count, total_tokens, duration_ms)
    except Exception:
        pass