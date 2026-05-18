### api server helper functions
from typing import Optional, List
from sentence_transformers import SentenceTransformer
from infra.postgres import new_conn, db_semantic_search, db_keyword_search, db_get_entry
from pgvector.psycopg import register_vector
from datetime import datetime
import numpy as np
import numpy.linalg as LA
import json
import re

RECENCY_WEIGHT = .4
RELEVANCE_WEIGHT = .6
QUALITY_WEIGHT = 0.0
SCORE_THRESHOLD = 0.0

MODEL = None

def get_model():
    global MODEL
    if MODEL is None:
        MODEL = SentenceTransformer("nomic-ai/nomic-embed-text-v1", trust_remote_code=True)
    return MODEL

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

    text_chunks = []
    text_chunks.append("search_query: " + query)
    # get top k candidates
    query_embedding = get_model().encode(text_chunks)
    semantic_records = db_semantic_search(query_embedding)

    keywords = re.sub(r'[^\w\s]', "", query).split(" ")
    keyword_records = db_keyword_search(keywords)

    records = semantic_records + keyword_records
    for record in records:
        if record['id'] in seen:
            continue

        seen.add(record['id'])

        recency = calculate_recency(record)
        relevance = calculate_relevance(query_embedding, keywords, record, tags)
        quality = calculate_quality(query_embedding, record)

        overall = RECENCY_WEIGHT * recency + RELEVANCE_WEIGHT * relevance + QUALITY_WEIGHT * quality
        scored.append((overall, record["id"]))

    scored.sort(key=lambda t: t[0], reverse=True)
    sorted_results = [cand_id for score, cand_id in scored if score >= SCORE_THRESHOLD]

    return sorted_results[page * limit : (page + 1) * limit]

def calculate_relevance(query_embedding, keywords, entry, user=None, semantic_weight=0.7, keyword_weight=0.3, tags=None):
    semantic_weight = semantic_weight / (semantic_weight + keyword_weight)
    keyword_weight = 1 - semantic_weight

    # calculating semantic similarity through cosine similarity
    entry_embedding = entry['embedding']
    query_embedding = query_embedding[0]
    semantic_sim = query_embedding.dot(entry_embedding) / (LA.norm(query_embedding) * LA.norm(entry_embedding))
    if user is not None:
        user_embedding = np.array([])
        user_sim = user_embedding.dot(entry_embedding) / (LA.norm(user_embedding) * LA.norm(entry_embedding))
        semantic_sim = max(semantic_sim, user_sim)
    
    # calculating keyword similarity through keyword hits
    keyword_sim = 0
    tag_sim = 0
    for kw in keywords:
        if entry['abstract'] and kw.lower() in entry['abstract'].lower():
            keyword_sim += 1
        elif entry['summary'] and kw.lower() in entry['summary'].lower():
            keyword_sim += 1

        if tags:
            for tag in tags:
                if tag.lower() in [t.lower() for t in entry['tags']]:
                    tag_sim += 1
                    break

    keyword_sim /= len(keywords)
    if tag_sim > 0:
        keyword_sim += tag_sim / len(tags)
    return semantic_weight*semantic_sim + keyword_weight*keyword_sim
    

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
