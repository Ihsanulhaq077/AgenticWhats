from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.api.deps import get_current_business
from app.db.session import get_db
from app.models.entities import Business, KnowledgeChunk, KnowledgeDocument
from app.rag.ingestion import delete_document, ingest_document, reindex_all
from app.services.notification_service import write_audit

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_ALLOWED_UPLOAD_TYPES = {"text/plain", "text/markdown", "text/csv", "application/json"}
_ALLOWED_UPLOAD_SUFFIXES = {".txt", ".md", ".csv", ".json"}
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def _doc_out(db: Session, doc: KnowledgeDocument) -> dict:
    chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.id).count()
    return {"id": doc.id, "title": doc.title, "source_type": doc.source_type,
            "version": doc.version, "chunk_count": chunks, "created_at": doc.created_at}


@router.get("")
def list_documents(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    docs = (
        db.query(KnowledgeDocument).filter(KnowledgeDocument.business_id == business.id)
        .order_by(KnowledgeDocument.id.desc()).all()
    )
    return [_doc_out(db, d) for d in docs]


@router.post("/documents", status_code=201)
def add_document(
    title: str = Form(...),
    content: str = Form(...),
    source_type: str = Form("text"),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    doc = ingest_document(db, business.id, title, content, source_type)
    write_audit(db, business_id=business.id, actor_id=None, action="knowledge.add",
                entity_type="knowledge_document", entity_id=doc.id)
    return _doc_out(db, doc)


@router.post("/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """File upload with strict validation (type, suffix, size)."""
    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if file.content_type not in _ALLOWED_UPLOAD_TYPES or suffix not in _ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(400, f"Only {sorted(_ALLOWED_UPLOAD_SUFFIXES)} files are supported")
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large (max 2MB)")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be UTF-8 text")
    doc = ingest_document(db, business.id, title or (file.filename or "upload"), content,
                          source_type="file", source_reference=file.filename or "")
    write_audit(db, business_id=business.id, actor_id=None, action="knowledge.upload",
                entity_type="knowledge_document", entity_id=doc.id)
    return _doc_out(db, doc)


@router.delete("/{document_id}", status_code=204)
def remove_document(
    document_id: int,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    if not delete_document(db, business.id, document_id):
        raise HTTPException(404, "Document not found")


@router.post("/reindex")
def reindex(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    count = reindex_all(db, business.id)
    write_audit(db, business_id=business.id, actor_id=None, action="knowledge.reindex",
                entity_type="business", entity_id=business.id)
    return {"status": "reindexed", "chunks": count}


@router.post("/search")
def search(
    query: str = Form(...),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    from app.rag.retrieval import search_knowledge
    return search_knowledge(db, business.id, query, k=5)
