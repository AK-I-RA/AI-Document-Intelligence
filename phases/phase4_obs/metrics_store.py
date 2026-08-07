from __future__ import annotations
import os, sqlite3, time
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(os.getenv("METRICS_DB", "data/metrics/documind.db"))

COSTS = {
    "gpt-4o-mini":           {"input": 0.5,  "output": .60},
    "gpt-4o":                {"input": 5.00, "output": 15.00},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}

@contextmanager
def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with _db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS llm_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, model TEXT, input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0, total_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0, latency_ms REAL DEFAULT 0,
                cache_hit INTEGER DEFAULT 0, question TEXT
            );
            CREATE TABLE IF NOT EXISTS retrievals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, top_k INTEGER, avg_score REAL DEFAULT 0,
                latency_ms REAL DEFAULT 0, doc_name TEXT
            );
            CREATE TABLE IF NOT EXISTS ingestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, doc_name TEXT, chunk_count INTEGER DEFAULT 0,
                page_count INTEGER DEFAULT 0, total_tokens INTEGER DEFAULT 0,
                duration_ms REAL DEFAULT 0, embedding_cost_usd REAL DEFAULT 0
            );
            """
        )

init_db()


def _cost(model, inp, out):
    r = COSTS.get(model, {"input": 0.0, "output": 0.0})
    return (inp * r["input"] + out * r["output"]) / 1_000_000


def log_llm_call(model, input_tokens, output_tokens, latency_ms, cache_hit=False, question=""):
    with _db() as c:
        c.execute(
            "INSERT INTO llm_calls (ts,model,input_tokens,output_tokens,total_tokens,cost_usd,latency_ms,cache_hit,question) VALUES (?,?,?,?,?,?,?,?,?)",
            (time.time(), model, input_tokens, output_tokens, input_tokens+output_tokens,
             _cost(model, input_tokens, output_tokens), latency_ms, int(cache_hit), question[:200])
        )


def log_retrieval(top_k, scores, latency_ms, doc_name=""):
    avg = sum(scores)/len(scores) if scores else 0.0
    with _db() as c:
        c.execute(
            "INSERT INTO retrievals (ts,top_k,avg_score,latency_ms,doc_name) VALUES (?,?,?,?,?)",
            (time.time(), top_k, avg, latency_ms, doc_name)
        )

def log_ingestion(doc_name, chunk_count, page_count, total_tokens, duration_ms):
    with _db() as c:
        c.execute(
            "INSERT INTO ingestions (ts,doc_name,chunk_count,page_count,total_tokens,duration_ms,embedding_cost_usd) VALUES (?,?,?,?,?,?,?)",
            (time.time(), doc_name, chunk_count, page_count, total_tokens, duration_ms,
             _cost("text-embedding-3-small", total_tokens, 0))
        )


def get_summary(days=7):
    since = time.time() - days * 86400
    with _db() as c:
        llm = c.execute(
            "SELECT COUNT(*) calls, COALESCE(SUM(total_tokens),0) tokens, "
            "COALESCE(SUM(cost_usd),0) cost, COALESCE(AVG(latency_ms),0) avg_lat, "
            "COALESCE(SUM(cache_hit),0) cache_hits FROM llm_calls WHERE ts >= ?",
            (since,),
        ).fetchone()
        ing = c.execute("SELECT COUNT(*) count, COALESCE(SUM(embedding_cost_usd),0) cost FROM ingestions WHERE ts >= ?", (since,)).fetchone()
    calls = llm["calls"] or 0
    return {
            "llm_calls":      calls,
            "total_tokens":   llm["tokens"] or 0,
            "total_cost_usd": round((llm["cost"] or 0) + (ing["cost"] or 0), 6),
            "avg_latency_ms": round(llm["avg_lat"] or 0, 1),
            "cache_hit_rate": round((llm["cache_hits"] or 0) / calls * 100, 1) if calls else 0.0,
            "docs_ingested":  ing["count"] or 0,
        }


def get_daily_costs(days=14):
    since = time.time() - days * 86400
    with _db() as c:
        rows = c.execute("SELECT DATE(ts,'unixepoch','localtime') day, SUM(cost_usd) cost, COUNT(*) calls FROM llm_calls WHERE ts >= ? GROUP BY day ORDER BY day", (since,)).fetchall()
    return [{"day": r["day"], "cost": round(r["cost"], 6), "calls": r["calls"]} for r in rows]


def get_latency_series(days=7):
    since = time.time() - days * 86400
    with _db() as c:
        rows = c.execute("SELECT DATE(ts,'unixepoch','localtime') day, AVG(latency_ms) avg_ms, MAX(latency_ms) p95_ms FROM llm_calls WHERE ts >= ? GROUP BY day ORDER BY day", (since,)).fetchall()
    return [{"day": r["day"], "avg_ms": round(r["avg_ms"], 1), "p95_ms": round(r["p95_ms"], 1)} for r in rows]


def get_recent_calls(limit=20):
    with _db() as c:
        rows = c.execute("SELECT ts,model,input_tokens,output_tokens,total_tokens,cost_usd,latency_ms,cache_hit,question FROM llm_calls ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]