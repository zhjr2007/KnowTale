import uuid
import re
from typing import Any

import httpx
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.services.llm import embed_text, embed_texts

_chroma_client: Any = None


def _get_chroma() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


def _collection_name(course_id: int) -> str:
    return f"course_{course_id}"


def chunk_text(text: str, max_chars: int = 800, overlap: int = 100) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) < max_chars:
            current += "\n\n" + para if current else para
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return chunks


async def index_document(course_id: int, text: str, metadata: dict | None = None) -> int:
    chunks = chunk_text(text)
    if not chunks:
        return 0

    embeddings = await embed_texts(chunks)
    client = _get_chroma()
    collection = client.get_or_create_collection(
        name=_collection_name(course_id),
        metadata={"hnsw:space": "cosine"},
    )

    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [
        {"course_id": course_id, "chunk_index": i, **(metadata or {})}
        for i in range(len(chunks))
    ]

    collection.add(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    return len(chunks)


async def retrieve(course_id: int, query: str, top_k: int = 20) -> list[dict]:
    query_embedding = await embed_text(query)
    client = _get_chroma()
    collection = client.get_or_create_collection(name=_collection_name(course_id))

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, 50),
    )

    if not results["ids"][0]:
        return []

    return [
        {
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "score": results["distances"][0][i],
            "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
        }
        for i in range(len(results["ids"][0]))
    ]


async def rerank(query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
    if not documents:
        return []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.BAILIAN_BASE_URL}/rerank",
                headers={
                    "Authorization": f"Bearer {settings.BAILIAN_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.RERANK_MODEL,
                    "query": query,
                    "documents": [d["text"] for d in documents],
                    "top_n": top_k,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            reranked = []
            for item in data.get("results", []):
                idx = item["index"]
                reranked.append({
                    **documents[idx],
                    "relevance_score": item.get("relevance_score", item.get("score", 0)),
                })
            return reranked
    except Exception:
        return documents[:top_k]


async def search(course_id: int, query: str, top_k: int = 5) -> list[dict]:
    candidates = await retrieve(course_id, query, top_k=20)
    return await rerank(query, candidates, top_k=top_k)


async def clear_course_knowledge(course_id: int):
    client = _get_chroma()
    try:
        client.delete_collection(name=_collection_name(course_id))
    except Exception:
        pass


async def get_chunk_count(course_id: int) -> int:
    client = _get_chroma()
    try:
        collection = client.get_collection(name=_collection_name(course_id))
        return collection.count()
    except Exception:
        return 0
