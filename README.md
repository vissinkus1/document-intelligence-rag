# Document Intelligence RAG Platform

A full-stack Retrieval-Augmented Generation (RAG) platform designed for institutional documents, policy briefs, handbooks, and regulatory manuals. Grounded answers, vector semantic search with pgvector, citation tracking, and role-based access control.

---

## Features

- **Document Ingestion & Chunking**: PDF parsing with `pypdf`, recursive text chunking with overlap via LangChain text splitters, and embedding generation via Google GenAI (`gemini-embedding-001`).
- **Vector Search with pgvector**: Semantic similarity retrieval powered by PostgreSQL 16 and the `pgvector` extension (cosine similarity, 768 dimensions).
- **Context-Aware Conversational AI**: Grounded responses powered by Google Gemini (`gemini-3.5-flash-lite` with automatic fallback cascade) with exact source citations (document name, page, and snippet) and conversational greeting filtering.
- **Role-Based Access Control (RBAC)**: JWT authentication separating Administrator actions (document upload and deletion) from Member queries.
- **Clean React Interface**: Intuitive SPA built with React 19 and Vite, featuring chat session management, citation inspection, document status monitoring, and PDF uploads.
- **Fully Containerized**: Multi-container orchestration with Docker Compose (PostgreSQL/pgvector, FastAPI backend, and Nginx reverse proxy serving React).

---

## Architecture & Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 19, Vite, React Router 7, Nginx |
| **Backend** | FastAPI, Python 3.12, Uvicorn, SQLAlchemy, Pydantic v2 |
| **RAG & LLM** | Google GenAI SDK (`gemini-3.5-flash-lite`, fallback cascade), `gemini-embedding-001` (768-dim) |
| **Database** | PostgreSQL 16 with `pgvector` |
| **Reverse Proxy** | Nginx (proxies `/api/` to backend, serves SPA with HTML5 fallback) |
| **Orchestration** | Docker & Docker Compose |

---

## Quick Start (Docker Compose)

### 1. Clone the repository & Enter directory
```bash
git clone https://github.com/vissinkus1/document-intelligence-rag.git
cd document-intelligence-rag/rag-platform
```

### 2. Configure Environment Variables
Copy the template and provide your Google Gemini API key:
```bash
cp .env.example .env
```
Ensure `.env` contains:
```env
POSTGRES_USER=raguser
POSTGRES_PASSWORD=ragpass
POSTGRES_DB=ragdb
GEMINI_API_KEY=your-gemini-api-key-here
JWT_SECRET=your-random-32-byte-hex-secret
```

### 3. Launch Services
```bash
docker compose up -d --build
```

Verify service status:
```bash
docker compose ps
```

### 4. Access the Applications
- **Web UI**: [http://localhost:3000](http://localhost:3000)
- **Backend API (via Nginx reverse proxy)**: [http://localhost:3000/api](http://localhost:3000/api)
- **FastAPI Interactive API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **PostgreSQL / pgvector**: `localhost:5432`

---

## Authentication & Roles

- The **first account registered** is automatically granted the `admin` role to bootstrap the system.
- Subsequent accounts are assigned the `member` role.
- Only users with the `admin` role can upload (`POST /api/documents`) or delete documents (`DELETE /api/documents/{id}`).
- Members can create chat sessions and ask questions grounded in the indexed documents.

---

## Running Tests

To run the full backend test suite inside the Docker container:
```bash
docker compose exec backend pytest -v
```

To run frontend lint and production build:
```bash
cd frontend
npm run lint
npm run build
```

---

## Known Limitations

- **Scanned PDFs unsupported (no OCR)**: The ingestion pipeline extracts digital text using `pypdf`; scanned images without embedded text layers cannot be indexed.
- **Tables handled poorly**: Standard text chunking treats tables as raw whitespace/newline-separated strings without cell boundary semantics.
- **Single document collection**: All uploaded documents share a single vector space; there is currently no multi-tenant or per-team document partitioning.
- **Open sign-up**: Any user with network access to the application can register an account.
- **No refresh token**: Access tokens expire after a configured duration (default: 60 minutes) requiring re-authentication.
- **Follow-up questions retrieval**: Conversational context is maintained in the LLM prompt, but vector retrieval queries use only the latest user message text without conversational query reformulation.
- **Similarity threshold**: The retrieval similarity score cutoff (`RETRIEVAL_SCORE_THRESHOLD = 0.25`) is heuristic and has not been formally calibrated across diverse document benchmarks.

---

## License
This project is licensed under the MIT License.
