from __future__ import annotations
from typing import TYPE_CHECKING
from sentence_transformers import SentenceTransformer

if TYPE_CHECKING:
    from core.ingestion import Chunk

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
BATCH_SIZE = 100

_model: SentenceTransformer | None = None


def get_client() -> SentenceTransformer:
    """Load the local embedding model once and reuse it."""
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str], client: SentenceTransformer | None = None) -> list[list[float]]:
    if client is None:
        client = get_client()

    if not texts:
        return []

    embeddings = client.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return embeddings.tolist()


def embed_chunks(chunks: list["Chunk"], client: SentenceTransformer | None = None) -> list[list[float]]:
    texts = [c.text for c in chunks]
    return embed_texts(texts, client)


def embed_query(query: str, client: SentenceTransformer | None = None) -> list[float]:
    return embed_texts([query], client)[0]