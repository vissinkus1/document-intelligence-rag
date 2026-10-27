import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import DocStatus, Document, DocumentChunk, User
from app.schemas import ChunkOut, DocumentOut
from app.services.ingestion import ingest_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=list[DocumentOut], status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin only. Validates every file first; if any is bad, nothing is saved."""
    if not files:
        raise HTTPException(400, "No files provided")
    if len(files) > settings.max_files_per_upload:
        raise HTTPException(400, f"At most {settings.max_files_per_upload} files per upload")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    validated: list[tuple[str, bytes]] = []
    for f in files:
        name = os.path.basename(f.filename or "")
        if not name.lower().endswith(".pdf"):
            raise HTTPException(400, f"'{name or 'file'}': only PDF files are supported")
        data = await f.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(413, f"'{name}' exceeds the {settings.max_upload_mb} MB limit")
        if not data.startswith(b"%PDF-"):
            raise HTTPException(400, f"'{name}' is not a valid PDF file")
        validated.append((name[:255], data))

    os.makedirs(settings.upload_dir, exist_ok=True)
    docs: list[Document] = []
    for name, data in validated:
        # Stored under a random name: no collisions, no path traversal from user input.
        path = os.path.join(settings.upload_dir, f"{uuid.uuid4().hex}.pdf")
        with open(path, "wb") as fh:
            fh.write(data)
        doc = Document(filename=name, file_path=path, size_bytes=len(data), uploaded_by=admin.id)
        db.add(doc)
        docs.append(doc)
    db.commit()

    for doc in docs:
        db.refresh(doc)
        background.add_task(ingest_document, doc.id)
    return docs


@router.get("", response_model=list[DocumentOut])
def list_documents(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Document).order_by(Document.id.desc())).all()


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.get("/{doc_id}/chunks", response_model=list[ChunkOut])
def list_chunks(
    doc_id: int,
    limit: int = 5,
    offset: int = 0,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin debugging aid: inspect how a document was chunked."""
    if not db.get(Document, doc_id):
        raise HTTPException(404, "Document not found")
    limit = max(1, min(limit, 100))
    return db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == doc_id)
        .order_by(DocumentChunk.chunk_index)
        .limit(limit)
        .offset(max(0, offset))
    ).all()


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.status == DocStatus.processing:
        raise HTTPException(409, "Document is still processing; try again in a moment")
    path = doc.file_path
    db.delete(doc)  # chunks removed by the DB (ON DELETE CASCADE)
    db.commit()
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)
