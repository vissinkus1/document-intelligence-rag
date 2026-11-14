import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db, init_db
from app.routers import auth, chat, documents
from app.services.ingestion import recover_stuck_documents

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    recover_stuck_documents()
    yield


app = FastAPI(title="Institutional Document QA System using RAG", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        has_vector = db.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        return {"status": "ok", "database": "connected", "pgvector": bool(has_vector)}
    except Exception as exc:
        log.warning("Health check failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "database": "disconnected", "error": str(exc)},
        )
