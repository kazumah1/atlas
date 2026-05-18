# CLAUDE.md

> Instructions for AI agents working in this repository.

---

## Project Overview

**What this project does:**
An academic research paper discovery and search platform. It ingests papers from ArXiv RSS feeds, processes them (PDF extraction, LLM summarization, embedding generation), and exposes a REST API with hybrid semantic + keyword search and ranking.

**Current status:**
Active development

**Primary language(s) and runtime:**
Python 3.11 (pinned in `.python-version`), managed with `uv`

---

## Repo Structure

```
/apps
  /api          # FastAPI REST API (search endpoint)
  /worker       # Background job processing (ingestor, processor, job queue)
  llm.py        # LLM client abstractions (OpenAI, Ollama, HuggingFace)
/infra          # Infrastructure clients (PostgreSQL, Redis, GCS)
/utils          # Shared utilities
docker-compose.yml   # Local PostgreSQL + Redis + RedisInsight
pyproject.toml       # Project metadata and dependencies
main.py              # Placeholder entrypoint (not in use)
```

**Key files to know:**
- `apps/api/app.py` — FastAPI app; `/health` and `/search/{query}` endpoints
- `apps/api/helpers.py` — Hybrid search + ranking logic
- `apps/worker/jobs.py` — Redis Streams-based job queue; job types: embed, summarize, extract_figures, extract_keywords
- `apps/worker/ingestor.py` — ArXiv RSS feed ingestion
- `apps/worker/processor.py` — PDF download, text extraction, embedding, summarization
- `apps/worker/cron_ingest.py` — Scheduled ingestion entry point
- `apps/worker/shared.py` — Singleton `JobManager` instance
- `infra/postgres.py` — PostgreSQL + pgvector client; schema definitions (Papers, Images, Vectors tables)
- `infra/redis.py` — Redis client (PDF cache + job queue)
- `infra/gcs.py` — Google Cloud Storage client
- `apps/llm.py` — LLM client (OpenAI, Ollama, HuggingFace)

---

## Setup

```bash
# Activate the virtual environment FIRST (always do this before any uv or python command)
source .venv/bin/activate

# Install dependencies
uv sync

# Start local infrastructure (PostgreSQL on :5433, Redis on :6379, RedisInsight on :5540)
docker-compose up -d

# Set up environment variables — copy and fill in values
cp .env.example .env  # (or manually create .env — see required vars below)
```

> **CRITICAL:** Always activate the venv (`source .venv/bin/activate`) before running any Python or `uv` commands. Running without activation can cause dependency resolution failures or unintended global installs.

**Environment variables required:**

Development:
- `DEVELOPMENT=true`
- `REDIS_HOST_DEV` — Redis hostname (e.g. `localhost`)
- `REDIS_PORT` — Redis port (e.g. `6379`)
- `POSTGRES_DB_DEV` — PostgreSQL database name
- `POSTGRES_USER_DEV` — PostgreSQL user
- `POSTGRES_PASSWORD_DEV` — PostgreSQL password

Production (when `DEVELOPMENT` is unset or false):
- `REDIS_HOST_PROD` — Redis cloud hostname
- `REDIS_PASSWORD_PROD` — Redis cloud password
- `POSTGRES_DB_PROD`, `POSTGRES_USER_PROD`, `POSTGRES_PASSWORD_PROD`

General:
- `OPENAI_API_KEY` — OpenAI API key
- `GCS_BUCKET_NAME` — GCS bucket (e.g. `storage-papers`)
- `TOKENIZERS_PARALLELISM=False` — Suppress HuggingFace tokenizer warning

---

## Build, Run, and Test Commands

```bash
# Activate venv first
source .venv/bin/activate

# Run the API server
uvicorn apps.api.app:app --reload

# Run the ingestion cron (subscribes to ArXiv RSS feeds and enqueues jobs)
python apps/worker/cron_ingest.py

# Run all tests
pytest

# Run a single test file
pytest tests/path/to/test_file.py

# Lint
ruff check .

# Format
ruff format .

# Auto-fix lint issues
ruff check . --fix
```

**Notes on testing:**
No test files exist yet. pytest is a declared dependency but tests have not been written.

---

## Planning

Before starting any task that involves more than one file or is non-trivial:
1. Write a plan to PLAN.md covering: what you are doing, what files you will touch, and any risks or open questions
2. Stop and wait for approval before proceeding
3. Update PLAN.md if the approach changes mid-task
4. Delete PLAN.md when the task is complete and committed

---

## Architecture and Patterns

**Overall architecture:**
Event-driven pipeline. ArXiv papers are ingested via RSS, queued in Redis Streams, and processed by background workers. Processed papers are stored in PostgreSQL (with pgvector embeddings). A FastAPI server provides search over the stored data.

**State management:**
- **PostgreSQL + pgvector** — paper metadata, summaries, tags, tsvector for keyword search, 768-dim HNSW embeddings in `vectors` table
- **Redis** — PDF byte cache (1-hour TTL) and job queue (Redis Streams, key: `job_queue`)
- **Google Cloud Storage** — raw PDFs (`raw/{h[:2]}/{h[2:4]}/{hash}.pdf`), extracted figures (`figures/{hash}.jpg`)

**Key patterns in use:**
- Redis Streams for async job queue; workers poll via `XREADGROUP`
- Job types dispatched by string: `embed`, `summarize`, `extract_figures`, `extract_keywords`
- Hybrid search: pgvector cosine similarity + PostgreSQL tsvector, results merged and ranked in `apps/api/helpers.py`
- Singleton infra clients (postgres, redis) initialized once in `shared.py` / module-level

**External services / integrations:**
- **ArXiv** — RSS feeds and query API for paper discovery
- **OpenAI** — Summarization (note: currently uses a non-existent API surface; see Known Issues)
- **Ollama** — Local LLM (`qwen:latest`) for summarization
- **HuggingFace** — `nomic-ai/nomic-embed-text-v1` for 768-dim embeddings; `deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B` for generation
- **Google Cloud Storage** — PDF and figure persistence

---

## Code Style and Conventions

**Formatting:**
ruff (linter + formatter)

**Naming conventions:**
`snake_case` for functions and variables, `PascalCase` for classes

**Import order:**
stdlib → third-party → local

**Things to always do:**
- Add type hints to function signatures
- Activate the venv before running any Python or `uv` commands

**Things to never do:**
- Do not run `pip install` directly — use `uv add` then `uv sync`
- Do not commit `.env` (it contains secrets)
- Do not install packages globally; always work inside the activated venv

---

## Files and Directories to Leave Alone

- `uv.lock` — generated lockfile; do not edit by hand (regenerated by `uv sync`)
- `.venv/` — virtual environment; managed by uv
- `__pycache__/` — Python bytecode cache; auto-generated

---

## Open TODOs and Known Issues

- [ ] `apps/api/helpers.py:27-28` — User profile-based ranking not implemented; ranking heuristic should be replaced with an ML model once enough papers are in the corpus
- [ ] `apps/worker/jobs.py:142` — Job payload validation should use Pydantic instead of manual dict checks
- [ ] `infra/postgres.py:233` — No validation that metadata is in the correct format before inserting
- [ ] No tests written yet despite `pytest` being a dependency
- [ ] `main.py` is a placeholder (`print("Hello from papers!")`) with no real functionality

---

## Misc Notes

- The embedding model (`nomic-ai/nomic-embed-text-v1`) requires `trust_remote_code=True` and produces 768-dim vectors; the pgvector HNSW index is built for this dimensionality — do not change embedding models without migrating the `vectors` table.
- `DEVELOPMENT=true` in `.env` switches all infra clients to local (localhost) endpoints; omitting it or setting it to false points at production credentials.
- Docker Compose maps PostgreSQL to host port **5433** (not the default 5432) to avoid conflicts.
- RQ (`rq` package) is listed as a dependency and imported in some files but is not actively used; the job queue runs on Redis Streams directly.
