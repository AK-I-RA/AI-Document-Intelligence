from __future__ import annotations
import os
import json
import numpy as np

CACHE_SIMILARITY_THRESHOLD = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.92"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_CACHE_PREFIX = "documind:cache:"
_STATS_KEY = "documind:cache:stats"


def _get_redis():
    import redis
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


class SemanticCache:
    def __init__(self, threshold: float = CACHE_SIMILARITY_THRESHOLD):
        self.threshold = threshold
        self.r = _get_redis()

    def lookup(self, embedding: list[float]) -> dict | None:
        self.r.hincrby(_STATS_KEY, "total", 1)
        best = None
        best_score = 0.0
        for key in self.r.scan_iter(match=_CACHE_PREFIX + "entry:*"):
            raw = self.r.get(key)
            if not raw:
                continue
            entry = json.loads(raw)
            score = _cosine(embedding, entry["embedding"])
            if score > best_score:
                best_score = score
                best = entry
        if best and best_score >= self.threshold:
            self.r.hincrby(_STATS_KEY, "hits", 1)
            return {
                "answer": best["answer"],
                "question": best["question"],
                "score": round(best_score, 4),
            }
        return None

    def store(self, embedding: list[float], question: str, answer: str) -> None:
        import hashlib
        key_id = hashlib.md5(question.encode()).hexdigest()
        entry = {
            "question": question,
            "answer": answer,
            "embedding": list(embedding),
        }
        self.r.set(_CACHE_PREFIX + "entry:" + key_id, json.dumps(entry))

    def get_stats(self) -> dict:
        stats = self.r.hgetall(_STATS_KEY)
        total = int(stats.get("total", 0))
        hits = int(stats.get("hits", 0))
        hit_rate = round(hits / total * 100, 1) if total else 0.0
        return {"total": total, "hits": hits, "hit_rate": hit_rate}

    def clear(self) -> None:
        for key in self.r.scan_iter(match=_CACHE_PREFIX + "*"):
            self.r.delete(key)