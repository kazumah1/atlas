### api server helper functions
from typing import Optional, List
from openai import OpenAI
from infra.postgres import db_semantic_search, db_keyword_search, db_get_entry
from datetime import datetime
import logging
import numpy as np
import numpy.linalg as LA
import re
import os

RECENCY_WEIGHT = .4
RELEVANCE_WEIGHT = .6
QUALITY_WEIGHT = 0.0
SCORE_THRESHOLD = 0.0

_openai_client = None
_local_model = None
logger = logging.getLogger(__name__)

def embed_query(text: str) -> np.ndarray:
    if os.getenv("DEVELOPMENT") == "true":
        global _local_model
        if _local_model is None:
            from sentence_transformers import SentenceTransformer
            _local_model = SentenceTransformer("nomic-ai/nomic-embed-text-v1", trust_remote_code=True)
        return _local_model.encode([text])[0].astype(np.float32)
    else:
        global _openai_client
        if _openai_client is None:
            _openai_client = OpenAI()
        response = _openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            dimensions=768
        )
        return np.array(response.data[0].embedding, dtype=np.float32)

def get_sorted_results(query: str, date_from: Optional[datetime], date_to: Optional[datetime], tags: Optional[List[str]], page: int = 0, limit: int = 20):
    """the ranking heuristic is a weighted product of 3 components:
        recency : exponential decay, prioritizing more recent papers
        relevance : a weighted sum of semantic (user profile) and keyword matching (search query)
        quality : a rough estimation of paper quality based on abstract length and keywords. ideally train a small model for this later
    """
    # TODO: DONT HAVE USER PROFILE RN
    # TODO: get rid of heuristic in place of model once enough papers in corpus and once working version is done

    seen = set()
    scored: list[tuple[float, object]] = []

    # Text search is the reliable baseline. It searches titles directly and does
    # not require precomputed vectors or an external embedding service.
    candidate_limit = max(100, (page + 1) * limit * 5)
    keyword_records = db_keyword_search(
        query,
        date_from=date_from,
        date_to=date_to,
        tags=tags,
        limit=candidate_limit,
    )

    # Semantic search enriches the baseline when embeddings are available. A
    # missing/expired API key must not take down ordinary title search.
    query_embedding = None
    semantic_records = []
    if os.getenv("OPENAI_API_KEY") or os.getenv("DEVELOPMENT") == "true":
        try:
            query_embedding = embed_query("search_query: " + query)
            semantic_records = db_semantic_search([query_embedding])
        except Exception as exc:
            logger.warning("Semantic search unavailable; using text search: %s", exc)

    keywords = [kw for kw in re.sub(r'[^\w\s]', "", query).lower().split() if kw]

    records = semantic_records + keyword_records
    for record in records:
        if record['id'] in seen:
            continue

        seen.add(record['id'])

        recency = calculate_recency(record)
        relevance = calculate_relevance(query_embedding, keywords, record, query=query, tags=tags)
        quality = calculate_quality(query_embedding, record)

        overall = RECENCY_WEIGHT * recency + RELEVANCE_WEIGHT * relevance + QUALITY_WEIGHT * quality
        scored.append((overall, record["id"]))

    scored.sort(key=lambda t: t[0], reverse=True)
    sorted_results = [cand_id for score, cand_id in scored if score >= SCORE_THRESHOLD]

    return sorted_results[page * limit : (page + 1) * limit]

def calculate_relevance(query_embedding, keywords, entry, query="", tags=None):
    title = (entry.get('title') or '').lower()
    abstract = (entry.get('abstract') or '').lower()
    summary = (entry.get('summary') or '').lower()
    normalized_query = " ".join(query.lower().split())

    title_hits = sum(kw in title for kw in keywords)
    body_hits = sum(kw in abstract or kw in summary for kw in keywords)
    keyword_count = max(len(keywords), 1)

    text_score = 0.7 * (title_hits / keyword_count)
    text_score += 0.3 * (body_hits / keyword_count)
    if normalized_query and normalized_query == " ".join(title.split()):
        text_score += 1.0
    elif normalized_query and normalized_query in title:
        text_score += 0.5

    if tags:
        paper_tags = {tag.lower() for tag in (entry.get('tags') or [])}
        text_score += 0.2 * sum(tag.lower() in paper_tags for tag in tags) / len(tags)

    entry_embedding = entry.get('embedding')
    if query_embedding is None or entry_embedding is None:
        return text_score

    denominator = LA.norm(query_embedding) * LA.norm(entry_embedding)
    if denominator == 0:
        return text_score
    semantic_sim = float(query_embedding.dot(entry_embedding) / denominator)
    semantic_score = (semantic_sim + 1) / 2
    return 0.6 * semantic_score + 0.4 * text_score
    

def calculate_recency(entry):
    today = datetime.today()
    published_date = entry['published_at']
    
    difference = today - published_date
    decay_rate = 0.01
    return np.exp(-decay_rate * difference.days)

def calculate_quality(query, entry):
    return 1

def fetch_papers_from_ids(entry_ids: list) -> list:
    if not entry_ids:
        return []

    papers = []
    for entry_id in entry_ids:
        record = db_get_entry(entry_id)
        papers.append(record)
    return papers

if __name__ == "__main__":
    _ids = get_sorted_results("quantum mechanics", None, None, None)
