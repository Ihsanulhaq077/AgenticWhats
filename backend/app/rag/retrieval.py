import json

import numpy as np
from sqlalchemy.orm import Session

from app.models.entities import KnowledgeChunk


def _cosine_matrix(query_vec: list[float], matrix: np.ndarray) -> np.ndarray:
    q = np.asarray(query_vec, dtype=np.float32)
    q_norm = np.linalg.norm(q) or 1.0
    m_norm = np.linalg.norm(matrix, axis=1)
    m_norm[m_norm == 0] = 1.0
    return (matrix @ q) / (m_norm * q_norm)


def search_knowledge(
    db: Session,
    business_id: int,
    query: str,
    k: int = 4,
    min_score: float = 0.05,
) -> list[dict]:
    """Tenant-filtered vector search over the knowledge base.

    The tenant filter is applied in the SQL WHERE clause — never only in the
    prompt — so one business can never retrieve another business's chunks.
    """
    from app.rag.embeddings import embedding_service

    rows = (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.business_id == business_id)
        .all()
    )
    if not rows:
        return []

    matrix = np.array([row.embedding_list() for row in rows], dtype=np.float32)
    if matrix.size == 0:
        return []
    query_vec = embedding_service.embed_query(query)
    scores = _cosine_matrix(query_vec, matrix)

    results = []
    for idx in np.argsort(scores)[::-1][:k]:
        score = float(scores[idx])
        if score < min_score:
            break
        row = rows[int(idx)]
        try:
            meta = json.loads(row.metadata_json or "{}")
        except (ValueError, TypeError):
            meta = {}
        results.append({
            "chunk_id": row.id,
            "document_id": row.document_id,
            "content": row.content,
            "score": round(score, 4),
            "metadata": meta,
        })
    return results
