# outline

# what it is

a system that continuously ingests papers from sources (arXiv, OpenReview, Crossref/DOI, project blogs), normalizes + stores PDFs/metadata, runs embeddings/summaries, and serves fast personalized search/alerts via a clean UI.

# services (clear ownership + boundaries)

1. **ingestor** (workers)
    - pulls RSS/APIs/webhooks, backfills, dedupes (content hash), retries, rate-limits.
    - writes raw docs to object storage; metadata to Postgres.
    - emits jobs to a queue for downstream processing.
2. **processor** (GPU/CPU workers)
    - PDF text/figure extraction, reference graph.
    - embeddings (title/abstract/sections), keyphrase tagging, topic model.
    - summary + TL;DR + highlights; safety redaction.
    - stores vectors (Qdrant/pgvector) + processed text (object storage).
3. **ranker/rec engine**
    - learning-to-rank or heuristic (recency × citations × novelty).
    - user profiles (topics, authors, venues) → personalized feed.
4. **api-gateway** (FastAPI/Go)
    - REST/GraphQL: search, filter, facets, recs, alerts, webhooks.
    - auth (OAuth + API keys), rate limiting, audit.
5. **frontend** (SvelteKit SSR)
    - instant search (typeahead), reader view (sections/figures), compare papers, “diff since last visit,” saved queries.
    - streaming summaries & citations panel.
6. **scheduler/orchestrator**
    - Temporal/Airflow/Celery Beat or Cloud Scheduler → kicks crawls, re-embeds, sitemaps, index maintenance.
7. **ops plane**
    - metrics (Prometheus/OpenTelemetry), logs (Loki/Cloud Logging), alerts (PagerDuty/Slack).
    - admin console for stuck jobs, backfills, secret rotation.

# data plane & storage

- **object storage**: PDFs, extracted JSON (GCS/S3) with lifecycle (e.g., coldline after 90d).
- **postgres**: canonical metadata (papers, authors, sources), user prefs, jobs.
- **vector DB**: Qdrant/Weaviate/pgvector for semantic search.
- **redis**: queues (RQ/Celery) + hot caches (search facets, trending).

# infra choices (copy the “self-managed website” vibe)

- **containers everywhere**: each service has a `Dockerfile`; local parity via `docker-compose`.
- **cloud runtime**: Cloud Run (or ECS/Fargate); processor can run on GPU nodes if needed (GKE or Lambda GPU/Fly GPU).
- **networking**: Cloudflare (DNS/TLS/WAF) → API/FE; private VPC connector to Postgres/Redis/Vector DB if self-hosted.
- **secrets**: GitHub OIDC → cloud IAM; pull secrets at deploy/runtime from Secret Manager (never bake into images).
- **IaC**: Terraform/Pulumi for Cloud Run, registries, VPC, DBs, buckets, queues, roles.
- **CI/CD**: GitHub Actions
    - on PR: build, unit tests, typecheck, integration tests (docker-compose), ephemeral preview (tagged images + temporary env)
    - on main: build multi-arch images → Artifact Registry, run DB migrations, progressive deploy (10%/50%/100%), smoke tests, auto-rollback
- **observability**: trace ingestion→search end-to-end; SLOs (p95 search <300 ms, ingestion lag <10 min), error budgets

# request/ingest→search flow

1. **poll** arXiv/OpenReview feeds → new item → **job** on queue.
2. **ingestor** downloads PDF → stores to bucket → writes row to Postgres.
3. **processor** extracts text/figures → splits by section → embeddings + TL;DR → write vectors + artifacts.
4. **ranker** updates indices, trending, topic maps.
5. **api** exposes: `/search?q=...&topics=...`, `/feed/me`, `/alerts`, `/paper/{id}`.
6. **frontend** renders SSR results; client hydrates, supports offline read mode.

# “infra-y” features that make it stand out

- **incremental backfills** with checkpoints; **idempotent** pipelines using content hashes & versioned artifacts.
- **schema versioning** for embeddings (v1→v2) with rolling re-embed jobs.
- **blue/green** deploys of the vector index (A/B shards) with shadow traffic.
- **rate-limit governance** per source; respectful crawl policies.
- **document lineage**: every summary/embedding references the artifact digest for reproducibility.
- **privacy & compliance**: robots.txt adherence, opt-out list, license tags.
- **plugin/connectors**: add new sources by dropping a small “connector” module (clean interface).

# concrete stack (opinionated, fast to build)

- **FE**: SvelteKit (Node adapter), Tailwind; SSR on Cloud Run.
- **API**: FastAPI + uvicorn; Pydantic models; OpenAPI docs.
- **workers**: Celery + Redis (or Temporal if you want durable workflows).
- **queue**: Redis Streams (simple) → upgrade to Pub/Sub/Kafka later.
- **DB**: Postgres + pgvector (keeps vectors & metadata together) or Postgres + Qdrant.
- **PDF**: PyMuPDF + GROBID (optional) for citations; science-parse alternative.
- **embeddings**: local (nomic-embed, bge-small) or external (OpenAI/Groq) behind a provider interface.
- **summaries**: batch with a small LLM; cache in object storage.
- **monitoring**: OpenTelemetry → Grafana Cloud or GCP Monitoring; Loki for logs.

# minimal repo layout

```
/apps
  /frontend     # sveltekit
  /api          # fastapi
  /worker       # processor/ingestor
  /ranker       # optional service
/infrastructure
  /terraform    # cloud run, buckets, secrets, vpc, db
/.github/workflows
  build.yml     # build/test
  deploy.yml    # oidc->gcp, push images, migrate, deploy, rollout

```

# key APIs (so it’s product-useful)

- `GET /search?q=&topics=&author=&venue=&year=` → results + facets
- `POST /alerts` (saved query → email/webhook on new matches)
- `GET /paper/{id}` → metadata, sections, figures, references, similar
- `GET /feed` → personalized ranking
- `POST /ingest/webhook` → accept external feeds/blog posts

# mvp → plus-ups

**MVP (1–2 weeks):**

- arXiv + OpenReview connectors, PDF → text, embeddings, searchable UI.
- CI/CD + secrets + Cloud Run + Postgres/pgvector + Cloudflare.
- basic alerts + saved searches.

**Stretch:**

- author disambiguation, citation graph, topic discovery (HDBSCAN/LDA).
- figure extraction + caption summaries.
- “compare papers” (semantic diff by sections).
- browser extension: highlight text → find similar sections across papers.

---

if you want, I can sketch the exact GitHub Actions (OIDC → GCP), Terraform skeleton, and the docker-compose you’ll use for local parity—so you can scaffold this tonight and have the full infra path (dev → CI → prod) working before you add fancy ranking.