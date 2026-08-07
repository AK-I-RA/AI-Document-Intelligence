from __future__ import annotations
import os
import uuid
from typing import TYPE_CHECKING
from pinecone import Pinecone, ServerlessSpec

if TYPE_CHECKING:
    from core.ingestion import Chunk

INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "documind")
CLOUD      = os.getenv("PINECONE_CLOUD", "aws")
REGION     = os.getenv("PINECONE_REGION", "us-east-1")
DIMENSION  = 384
METRIC     = "cosine"
UPSERT_BATCH = 100


def get_index():
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise EnvironmentError("Pinecone api_key not set")

    pc = Pinecone(api_key=api_key)

    existing = [idx.name for idx in pc.list_indexes()]
    if INDEX_NAME not in existing:
        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSION,
            metric=METRIC,
            spec=ServerlessSpec(cloud=CLOUD, region=REGION),
        )
    return pc.Index(INDEX_NAME)


def upsert_chunks(
    chunks: list["Chunk"],
    embeddings: list[list[float]],
) -> int:
    index = get_index()

    vectors = []
    for chunk, embedding in zip(chunks, embeddings):
        vec_id = f"{chunk.doc_name}_{chunk.chunk_index}"
        vectors.append({
            "id": vec_id,
            "values": embedding,
            "metadata": chunk.to_pinecone_metadata(),
        })

    for i in range(0, len(vectors), UPSERT_BATCH):
        batch = vectors[i : i + UPSERT_BATCH]
        index.upsert(vectors=batch)

    return len(vectors)


def query_index(
    query_embeddings: list[float],
    top_k=5,
    filter_doc: str | None = None,
) -> list[dict]:

    index = get_index()
    query_kwargs: dict = {
        "vector": query_embeddings,
        "top_k": top_k,
        "include_metadata": True,
    }

    if filter_doc:
        query_kwargs["filter"] = {"doc_name": {"$eq": filter_doc}}

    response = index.query(**query_kwargs)

    results = []
    for match in response.matches:
        results.append({
            "id": match.id,
            "score": round(match.score, 4),
            "text": match.metadata.get("text", ""),
            "doc_name": match.metadata.get("doc_name", ""),
            "page_num": match.metadata.get("page_num", 0),
            "chunk_index": match.metadata.get("chunk_index", 0),
        })
    return results


def delete_document(doc_name: str) -> None:
    index = get_index()
    index.delete(filter={"doc_name": {"$eq": doc_name}})


def get_index_stats() -> dict:
    index = get_index()
    stats = index.describe_index_stats()
    return {
        "total_vectors": stats.total_vector_count,
        "dimension": stats.dimension,
        "index_name": INDEX_NAME,
    }


def list_indexed_documents(index=None) -> list[str]:
    if index is None:
        index = get_index()

    zero_vec = [0.0] * DIMENSION
    response = index.query(vector=zero_vec, top_k=100, include_metadata=True)
    docs = list({m.metadata.get("doc_name", "") for m in response.matches if m.metadata})
    return sorted(d for d in docs if d)