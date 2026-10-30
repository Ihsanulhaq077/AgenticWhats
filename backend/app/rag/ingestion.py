import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.entities import KnowledgeChunk, KnowledgeDocument
from app.rag.chunking import chunk_text
from app.rag.embeddings import embedding_service


def ingest_document(
    db: Session,
    business_id: int,
    title: str,
    content: str,
    source_type: str = "text",
    source_reference: str = "",
) -> KnowledgeDocument:
    """Create (or version-bump) a knowledge document and index its chunks.

    Re-ingesting a document with the same title creates a new version and
    replaces the old chunks, so retrieval never serves stale knowledge.
    """
    existing = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.business_id == business_id, KnowledgeDocument.title == title)
        .first()
    )
    if existing:
        db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == existing.id).delete()
        existing.version += 1
        existing.content = content
        existing.source_type = source_type
        existing.source_reference = source_reference
        document = existing
    else:
        document = KnowledgeDocument(
            business_id=business_id,
            title=title,
            content=content,
            source_type=source_type,
            source_reference=source_reference,
            version=1,
        )
        db.add(document)
        db.flush()

    chunks = chunk_text(content)
    if chunks:
        vectors = embedding_service.embed_texts(chunks)
        for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
            db.add(KnowledgeChunk(
                business_id=business_id,
                document_id=document.id,
                chunk_index=idx,
                content=chunk,
                embedding=json.dumps(vector),
                metadata_json=json.dumps({
                    "business_id": business_id,
                    "document_id": document.id,
                    "document_version": document.version,
                    "source": source_reference or title,
                    "category": source_type,
                    "ingested_at": datetime.utcnow().isoformat(),
                }),
            ))
    db.commit()
    return document


def delete_document(db: Session, business_id: int, document_id: int) -> bool:
    """Tenant-scoped delete: chunks cascade, other tenants are untouched."""
    doc = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.business_id == business_id, KnowledgeDocument.id == document_id)
        .first()
    )
    if doc is None:
        return False
    db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.id).delete()
    db.delete(doc)
    db.commit()
    return True


def reindex_all(db: Session, business_id: int) -> int:
    """Re-embed every document of a tenant (e.g. after changing providers)."""
    docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.business_id == business_id).all()
    count = 0
    for doc in docs:
        db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.id).delete()
        chunks = chunk_text(doc.content)
        if chunks:
            vectors = embedding_service.embed_texts(chunks)
            for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
                db.add(KnowledgeChunk(
                    business_id=business_id,
                    document_id=doc.id,
                    chunk_index=idx,
                    content=chunk,
                    embedding=json.dumps(vector),
                ))
        count += len(chunks)
    db.commit()
    return count
