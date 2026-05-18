from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Union, Optional, List
from datetime import datetime
from apps.api.helpers import get_sorted_results, fetch_papers_from_ids
from infra.postgres import db_get_paper, db_list_recent_papers
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(title="papers api server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGIN"), "http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status" : "OK"}


@app.get("/search/{search_query}")
def search(search_query: str, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None, tags: Optional[List[str]] = None, page: int = 0, limit: int = 20):
    result_ids = get_sorted_results(query=search_query, date_from=date_from, date_to=date_to, tags=tags, page=page, limit=limit)

    results = fetch_papers_from_ids(result_ids)

    return {
            "results":results
    }


@app.get("/papers/recent")
def list_recent_papers(limit: int = 20):
    """Default home-feed list; replace with personalized ranking later."""
    limit = min(max(limit, 1), 50)
    return {"results": db_list_recent_papers(limit)}


@app.get("/papers/{paper_id}")
def get_paper(paper_id: str):
    paper_records = db_get_paper(paper_id)
    if not paper_records:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper_records[0]