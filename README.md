# atlas

Atlas is a search engine for research papers. It pulls new papers from arXiv, extracts and enriches their contents, then combines semantic search with ordinary keyword matching so useful results do not depend on an exact title or phrase.

[Source on GitHub](https://github.com/kazumah1/atlas)

## How it works

```mermaid
flowchart LR
    A[arXiv RSS] --> B[Ingestor]
    B --> C[(GCS<br/>PDF archive)]
    B --> D[(PostgreSQL<br/>metadata + text search)]
    B --> E[[Redis stream]]
    E --> F[Enrichment worker]
    F --> G[embeddings]
    F --> H[summaries]
    F --> I[figures + keywords]
    G --> J[(pgvector)]
    H --> D
    I --> D
    I --> C
    D --> K[FastAPI]
    J --> K
    K --> L[SvelteKit web app]
```

Ingestion is split from enrichment because downloading a feed and running models have very different cost and failure profiles. The ingestor records the paper first, stores the PDF under a content hash, and puts the slower work on a Redis stream. Workers then create 768-dimensional embeddings, extract searchable text and figures, and produce a summary. PDFs are cached in Redis for an hour so those stages do not repeatedly download the same file.

Search retrieves candidates from both pgvector and PostgreSQL full-text search. Results are de-duplicated and ranked with a 60/40 relevance-to-recency blend; relevance itself is 70% semantic similarity and 30% keyword matching.

## Design tradeoffs

- PostgreSQL, full-text search, and pgvector keep the serving path small and make metadata and vector results easy to join. A dedicated vector database would scale farther, but would add another system to operate.
- Content-addressed PDFs make storage idempotent and catch duplicate documents even when their URLs differ. Hashing extracted PDF text is slower than hashing raw bytes, but is less sensitive to packaging changes.
- Redis Streams are a lightweight fit for the current workload. The present single-consumer loop is simpler than consumer groups or a workflow engine, at the cost of weaker recovery and horizontal-worker coordination.
- OpenAI provides production embeddings and summaries, with local model paths available for development. That keeps local iteration possible, but local and hosted model outputs are not identical.
- The ranker is intentionally legible and tunable. It is easier to debug than a learned ranker, but its fixed weights will eventually become the quality ceiling.

## Run locally

You need Python 3.11+, [`uv`](https://docs.astral.sh/uv/), Docker, Node.js, and pnpm.

```bash
cp .env.example .env
docker compose up -d postgres redis
uv sync
uv run uvicorn apps.api.app:app --reload
```

For local development, set `DEVELOPMENT=true`, `POSTGRES_DB_DEV=postgresql://app:app_pw@localhost:5433/app_db`, and the Redis values in `.env`. Add `OPENAI_API_KEY`, `GCS_BUCKET_NAME`, and Google Cloud credentials before running ingestion.

Start the worker and ingestor in separate terminals:

```bash
uv run python -m apps.worker.jobs
uv run python -m apps.worker.cron_ingest
```

Then start the frontend:

```bash
cd apps/web
pnpm install
PUBLIC_API_URL=http://localhost:8000 pnpm dev
```

The API is available at `http://localhost:8000`, and the frontend defaults to `http://localhost:5173`.

## Stack

Python, FastAPI, PostgreSQL, pgvector, Redis, Google Cloud Storage, OpenAI/Ollama, SvelteKit, and Railway.
