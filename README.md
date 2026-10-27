# Document Intelligence RAG Platform

A full-stack, enterprise-ready Retrieval-Augmented Generation (RAG) platform designed for institutional documents, policy briefs, handbooks, and regulatory manuals. Grounded answers, vector semantic search with pgvector, real-time citation tracking, and role-based access control.

---

## 🌟 Features

- **Document Ingestion & Chunking**: Automatic PDF parsing, character/token-aware text chunking with overlap, and embedding generation via Google GenAI.
- **Vector Search with pgvector**: High-performance semantic similarity retrieval powered by PostgreSQL and the `pgvector` extension.
- **Context-Aware Conversational AI**: Grounded responses powered by Google Gemini (e.g. `gemini-2.0-flash`) with conversation memory and exact source citations (document name, page, and snippet).
- **Role-Based Access Control (RBAC)**: Secure JWT authentication separating Administrator actions (document upload, chunk inspection, user management) from Member queries.
- **Modern React Interface**: Clean, responsive UI with chat session management, drag-and-drop file uploader, and markdown rendering.
- **Fully Containerized**: Turnkey multi-container orchestration with Docker Compose (Postgres/pgvector, FastAPI backend, and Nginx/React frontend).

---

## 🛠️ Architecture & Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 19, Vite, React Router, CSS3, Nginx |
| **Backend** | FastAPI, Python 3.12, Uvicorn, SQLAlchemy, Pydantic v2 |
| **RAG & LLM** | Google GenAI SDK (`gemini-2.0-flash`), LangChain, text-embedding-004 |
| **Database** | PostgreSQL 16 with `pgvector` |
| **Orchestration** | Docker & Docker Compose |

---

## 🚀 Quick Start (Docker Compose)

### 1. Clone the repository
```bash
git clone https://github.com/vissinkus1/document-intelligence-rag.git
cd document-intelligence-rag
```

### 2. Configure Environment Variables
Copy the template and provide your Google Gemini API key:
```bash
cp .env.example .env
```
Edit `.env`:
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

### 4. Access the Applications
- **Web UI**: [http://localhost:3000](http://localhost:3000)
- **FastAPI Interactive API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **PostgreSQL / pgvector**: `localhost:5432`

---

## 🔐 Authentication & Roles

- The **first account registered** is automatically granted the `admin` role to bootstrap the system.
- Subsequent accounts are assigned the `member` role.
- Admins can manage documents, upload institutional PDFs, and promote members via `/auth/users/{user_id}/role`.

---

## 📂 Project Structure

```text
├── backend/
│   ├── app/
│   │   ├── routers/       # Auth, Documents, and Chat endpoints
│   │   ├── services/      # Ingestion, Embeddings, Retrieval, and RAG logic
│   │   ├── models.py      # SQLAlchemy models (User, Document, Chunk, Session)
│   │   ├── schemas.py     # Pydantic request/response schemas
│   │   ├── deps.py        # Dependency injection & RBAC guards
│   │   └── config.py      # App configuration via pydantic-settings
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/         # ChatPage, DocumentsPage, LoginPage
│   │   ├── components/    # Navbar, ChatInterface, etc.
│   │   └── api.js         # Axios / Fetch client
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🧪 Running Tests

To run the backend test suite:
```bash
cd backend
pytest
```

---

## 📄 License
This project is licensed under the MIT License.
