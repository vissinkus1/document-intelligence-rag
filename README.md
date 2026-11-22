# Institutional Document Intelligence RAG Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.162.0-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19.0-61DAFB.svg?style=flat&logo=React&logoColor=black)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1.svg?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-0.5.1-336791.svg?style=flat)](https://github.com/pgvector/pgvector)
[![Google Gemini](https://img.shields.io/badge/Google%20GenAI-Gemini%203.5-4285F4.svg?style=flat&logo=google&logoColor=white)](https://ai.google.dev/)
[![Render](https://img.shields.io/badge/Render-Deployed-46E3B7.svg?style=flat&logo=render&logoColor=white)](https://render.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An enterprise-grade, full-stack **Retrieval-Augmented Generation (RAG)** platform engineered for high-precision question answering on institutional PDFs, academic guidelines, policy manuals, and compliance documentation. Features grounded LLM generation, vector similarity search with `pgvector`, multi-bracket citation tracking, and strict Role-Based Access Control (RBAC).

---

## 🚀 Live Deployments & Demo Access

The platform is deployed live on **Render Cloud Infrastructure**:

| Service | Endpoint | Description |
|---|---|---|
| 🌐 **Web Application (SPA)** | [https://docqa-frontend-0jr6.onrender.com](https://docqa-frontend-0jr6.onrender.com) | React 19 Single Page App hosted on global CDN (0s cold start) |
| ⚡ **Backend API** | [https://docqa-backend-sc5f.onrender.com](https://docqa-backend-sc5f.onrender.com) | FastAPI REST service running in Docker container |
| 📖 **Interactive API Docs** | [https://docqa-backend-sc5f.onrender.com/docs](https://docqa-backend-sc5f.onrender.com/docs) | Swagger UI for exploring and testing endpoints |
| 🩺 **Health Check** | [https://docqa-backend-sc5f.onrender.com/health](https://docqa-backend-sc5f.onrender.com/health) | Live PostgreSQL & `pgvector` connectivity status |

### Demo Credentials

- **Admin Account**:
  - **Email**: `admin@demo.com`
  - **Password**: `password123`
  - *Privileges*: Upload PDF documents, trigger chunking/indexing, inspect vector chunks, delete documents.
- **Student / Member Account**:
  - Click **Register** on the website to create any personal test account (e.g. `student@demo.com`).
  - *Privileges*: Query the knowledge base, inspect source citations, manage personal chat sessions. Document uploads and deletions are protected and restricted to Admins.

---

## 🏗️ System Architecture & Workflow

```
                        +---------------------------+
                        |   React 19 SPA (Vite)     |
                        | (Document & Chat UI)      |
                        +-------------+-------------+
                                      |
                     REST API / JWT   |  HTTPS
                                      v
                        +-------------+-------------+
                        |      FastAPI Backend      |
                        | (Auth, RBAC, RAG Pipeline)|
                        +------+-------------+------+
                               |             |
           Document Ingestion  |             | Vector Search & Retrieval
                               v             v
+--------------------------------+         +--------------------------------+
|       Ingestion Pipeline       |         |       RAG Query Pipeline       |
| 1. PDF Parsing (pypdf)         |         | 1. Query Embedding (768-dim)   |
| 2. Recursive Split (1000/200)  |         | 2. Cosine Similarity Search    |
| 3. Gemini Embedding Gen        |         | 3. Context Ranking & Threshold |
+---------------+----------------+         +---------------+----------------+
                |                                          |
                +-------------------+  +-------------------+
                                    |  |
                                    v  v
                    +---------------+---------------+
                    |  PostgreSQL 16 + pgvector     |
                    | (Vectors, Users, Docs, Chats) |
                    +---------------+---------------+
                                    |
                            Grounded Context
                                    v
                    +---------------+---------------+
                    |       Google Gemini LLM       |
                    | (gemini-3.5-flash-lite /      |
                    |  fallback cascade + citations)|
                    +-------------------------------+
```

---

## ✨ Key Features & Engineering Highlights

### 1. Document Ingestion & Vector Indexing
- **PDF Extraction**: Digital PDF extraction via `pypdf` with strict byte validation (`%PDF-` magic byte check) and size guards (default: 20 MB).
- **Semantic Text Splitting**: Recursive character splitting with `chunk_size = 1000` characters and `chunk_overlap = 200` characters to preserve semantic continuity across section boundaries.
- **High-Dimensional Embeddings**: 768-dimensional dense vector embeddings generated using Google GenAI `gemini-embedding-001`.
- **Vector Search Engine**: Stored in PostgreSQL 16 using `pgvector` with cosine distance operator (`<=>`) and indexed similarity retrieval.

### 2. Context-Aware Grounded RAG with Exact Citations
- **Strict Grounding**: System prompt strictly constrains responses to retrieved document context, preventing model hallucinations.
- **Multi-Citation Parser**: Supports complex bracketed citation forms (e.g., `[1]`, `[2]`, `[1, 2]`) and formats verifiable references with document title, page number, and original chunk snippet.
- **Conversational Intent Filter**: Natural greetings (e.g., *"Hello"*, *"Good morning"*) bypass vector retrieval to deliver fast greeting responses without triggering unnecessary database lookups, while compound queries (e.g., *"Hi, what is the leave policy?"*) route directly into semantic retrieval.
- **History Sanitization**: Prior conversational citations (`[1]`, `[2]`) are stripped before appending to LLM memory to prevent prompt leakage and index drift.

### 3. Production LLM Resilience & Fallback Cascade
- **Automatic Fallback Cascade**: High-availability inference architecture targeting `gemini-3.5-flash-lite` as the primary engine, automatically cascading to `gemini-3.5-flash` or `gemini-3.8-flash` if rate limits or transient errors occur.
- **Exponential Backoff**: Jittered exponential retries handle transient 429/503 responses gracefully.

### 4. Role-Based Access Control (RBAC)
- **Granular Permissions**:
  - `admin`: Upload documents, trigger background indexing, inspect raw chunk embeddings, delete documents, promote users.
  - `member`: Search knowledge base, engage in cited conversational Q&A, manage personal session history.
- **Bootstrap Architecture**: The very first user to register in the database automatically receives `Role.admin`. Subsequent registrations default to `Role.member`.

### 5. Multi-Dialect Database Compatibility
- Built-in dialect normalizer automatically translates legacy `postgres://` or `postgresql://` connection strings (commonly provided by cloud platforms like Render or Supabase) into `postgresql+psycopg://` for modern Python 3 / psycopg3 drivers.

---

## 🛠️ Tech Stack

| Category | Technology | Purpose |
|---|---|---|
| **Frontend** | React 19, Vite, React Router 7 | Responsive, high-performance user interface |
| **Styling** | Modern CSS Variables & Responsive Layouts | Clean institutional look and feel with dark/light harmony |
| **Backend** | FastAPI, Python 3.12, Uvicorn | Asynchronous RESTful API backend |
| **Database** | PostgreSQL 16 + `pgvector` 0.5.1 | Relational persistence & vector similarity search |
| **ORM & Migrations** | SQLAlchemy 2.0, Psycopg 3 | High-performance async/sync database transactions |
| **AI / Embeddings** | Google GenAI SDK (`google-genai`) | `gemini-3.5-flash-lite`, `gemini-embedding-001` |
| **Document Processing** | `pypdf`, LangChain Text Splitters | PDF parsing, chunking, and metadata tagging |
| **Security** | PyJWT, Passlib, Bcrypt | Token-based stateless authentication and password hashing |
| **Deployment** | Docker, Render Blueprint (`render.yaml`) | Containerized backend, managed Postgres, static CDN |

---

## 📋 Role-Based Access Control (RBAC) Matrix

| Endpoint | Method | Admin | Member | Description |
|---|---|:---:|:---:|---|
| `/auth/register` | `POST` |  |  | Self-service registration (1st user = Admin) |
| `/auth/login` | `POST` |  |  | OAuth2 password grant login returning JWT |
| `/auth/users` | `GET` |  | ❌ | View all registered platform users |
| `/auth/users/{id}/role` | `PATCH` |  | ❌ | Promote or modify user role |
| `/documents` | `POST` |  | ❌ | Upload institutional PDF documents |
| `/documents` | `GET` |  |  | List all uploaded documents & indexing status |
| `/documents/{id}` | `DELETE` |  | ❌ | Delete document and cascade delete vector embeddings |
| `/documents/{id}/chunks` | `GET` |  | ❌ | Inspect chunks, embeddings, and token metrics |
| `/chat/ask` | `POST` |  |  | Ask a question; returns answer with source citations |
| `/chat/sessions` | `GET` |  |  | List personal chat session history |
| `/chat/sessions/{id}` | `DELETE` |  |  | Delete a specific chat session |

---

## 💻 Local Development Setup

### Prerequisites
- [Docker](https://www.docker.com/) & Docker Compose installed.
- A free [Google Gemini API Key](https://aistudio.google.com/).

### 1. Clone Repository & Enter Directory
```bash
git clone https://github.com/vissinkus1/document-intelligence-rag.git
cd document-intelligence-rag/rag-platform
```

### 2. Configure Environment Variables
Create your local environment file:
```bash
cp .env.example .env
```

Ensure your `.env` contains:
```env
# Database Settings
POSTGRES_USER=raguser
POSTGRES_PASSWORD=ragpass
POSTGRES_DB=ragdb
DATABASE_URL=postgresql+psycopg://raguser:ragpass@db:5432/ragdb

# Security & Secrets
JWT_SECRET=super-secret-hex-key-minimum-32-characters-long
ENVIRONMENT=development

# Google Gemini API Key
GEMINI_API_KEY=your-gemini-api-key-here
```

### 3. Launch Services with Docker Compose
```bash
docker compose up -d --build
```

Verify all three containers are healthy:
```bash
docker compose ps
```

### 4. Access Local Services
- **Web Interface**: [http://localhost:3000](http://localhost:3000)
- **API (Reverse Proxy)**: [http://localhost:3000/api](http://localhost:3000/api)
- **Direct FastAPI Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **PostgreSQL Database**: `localhost:5432`

---

## 🧪 Running Tests

The test suite validates database models, authentication, document validation, chunking, and end-to-end RAG pipeline logic:

```bash
# Run pytest inside the backend container
docker compose exec backend pytest -v
```

All 11 test suites run with isolated in-memory/throwaway databases to ensure 100% deterministic results.

---

## ☁️ Deployment on Render (100% Free Blueprint)

This project includes a production-ready `render.yaml` Blueprint file that deploys all 3 required services:

1. **PostgreSQL Database with pgvector** (Managed Render PostgreSQL Free Tier).
2. **FastAPI Web Service** (Docker runtime, auto-configured with health check).
3. **React 19 Static Site** (Render Static Site CDN with 0-second cold starts).

### One-Click Deploy:
1. Fork or push this repository to your GitHub account.
2. In the [Render Dashboard](https://dashboard.render.com), click **New +** &rarr; **Blueprint**.
3. Select this repository and branch `main`.
4. Enter your `GEMINI_API_KEY` when prompted.
5. Click **Apply** &mdash; Render will provision the database, build the Docker container, compile the React SPA, and wire the environment variables automatically.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
