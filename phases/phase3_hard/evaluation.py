from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np

#LOG_FILE = Path(os.getenv("EVAL_LOG_FILE", "data/logs/query_log.jsonl"))
_PROJECT_ROOT = Path(__file__).resolve().parents[2]   # phase3_hard -> phases -> RAG
LOG_FILE = Path(os.getenv("EVAL_LOG_FILE", str(_PROJECT_ROOT / "data" / "logs" / "query_log.jsonl")))
BASELINE_WINDOW = int(os.getenv("BASELINE_WINDOW", "50"))
DRIFT_THRESHOLD = float(os.getenv("DRIFT_THRESHOLD", "0.15"))


@dataclass
class QueryMetrics:
    question: str
    answer: str
    retrieved_chunks: int
    retrieval_score: float
    faithfulness: float
    latency_ms: float
    cache_hit: bool
    timestamp: float


def log_query(metrics: QueryMetrics) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(asdict(metrics)) + "\n")


def load_logs(n: int | None = None) -> list[dict]:
    if not LOG_FILE.exists():
        return []
    with open(LOG_FILE) as f:
        lines = f.readlines()
    records = [json.loads(l) for l in lines if l.strip()]
    return records[-n:] if n else records


# faithfulness
def score_faithfulness(answer: str, retrieved_chunks: list[dict]) -> float:
    if not answer or not retrieved_chunks:
        return 0.0
    chunk_words = set()
    for chunk in retrieved_chunks:
        words = chunk.get("text", "").lower().split()
        chunk_words.update(w.strip(".,;:\"'()[]") for w in words if len(w) > 4)
    sentences = [s.strip() for s in answer.split(".") if len(s.strip()) > 10]
    if not sentences:
        return 0.5
    grounded = 0
    for sent in sentences:
        sent_words = set(sent.lower().split())
        overlap = sent_words & chunk_words
        if len(overlap) >= 2:
            grounded += 1
    return round(grounded / len(sentences), 3)


def get_metrics_summary(n: int = BASELINE_WINDOW) -> dict:
    records = load_logs(n)
    if not records:
        return {
            "count": 0,
            "avg_faithfulness": 0.0,
            "avg_retrieval_score": 0.0,
            "avg_latency_ms": 0.0,
            "cache_hit_rate": 0.0,
            "p95_latency_ms": 0.0,
        }
    faithfulness = [r["faithfulness"] for r in records]
    retrieval_scores = [r["retrieval_score"] for r in records]
    latencies = [r["latency_ms"] for r in records]
    cache_hits = [r["cache_hit"] for r in records]
    return {
        "count": len(records),
        "avg_faithfulness": round(float(np.mean(faithfulness)), 3),
        "avg_retrieval_score": round(float(np.mean(retrieval_scores)), 3),
        "avg_latency_ms": round(float(np.mean(latencies)), 1),
        "p95_latency_ms": round(float(np.percentile(latencies, 95)), 1),
        "cache_hit_rate": round(sum(cache_hits) / len(cache_hits) * 100, 1),
    }


@dataclass
class DriftAlert:
    metric: str
    baseline: float
    current: float
    drop_pct: float
    severity: str


def check_drift() -> list[DriftAlert]:
    all_records = load_logs()
    if len(all_records) < BASELINE_WINDOW * 2:
        return []
    baseline_records = all_records[: -BASELINE_WINDOW]
    recent_records = all_records[-BASELINE_WINDOW:]
    alerts = []
    metrics_to_check = [
        ("faithfulness", "avg_faithfulness"),
        ("retrieval_score", "avg_retrieval_score"),
    ]

    def _avg(records, field):
        vals = [r[field] for r in records if field in r]
        return float(np.mean(vals)) if vals else 0.0

    for field, label in metrics_to_check:
        baseline_val = _avg(baseline_records, field)
        recent_val = _avg(recent_records, field)
        if baseline_val == 0:
            continue
        drop_pct = (baseline_val - recent_val) / baseline_val
        if drop_pct >= DRIFT_THRESHOLD:
            severity = "critical" if drop_pct >= DRIFT_THRESHOLD * 2 else "warning"
            alerts.append(DriftAlert(
                metric=label,
                baseline=round(baseline_val, 3),
                current=round(recent_val, 3),
                drop_pct=round(drop_pct * 100, 1),
                severity=severity,
            ))
    return alerts