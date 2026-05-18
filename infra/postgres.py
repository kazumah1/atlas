import json
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
import psycopg
from psycopg.rows import dict_row
import os
import numpy as np

load_dotenv()
if os.getenv("DEVELOPMENT") == "true":
    db_name = os.getenv("POSTGRES_DB_DEV")
else:
    db_name = os.getenv("POSTGRES_DB_PROD")


def new_conn():
    conn = psycopg.connect(conninfo=db_name, row_factory=dict_row)
    register_vector(conn)
    return conn


def _postgres_db():
    with new_conn() as conn:
        table_exists = conn.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'papers'
        )
        """).fetchone()
        if not table_exists:
            # might need to add gcs link to pdf and abstract
            conn.execute("""
                CREATE TABLE IF NOT EXISTS Papers (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    external_id TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    authors TEXT[] NOT NULL,
                    pdf_url TEXT NOT NULL,
                    html_url TEXT NOT NULL,
                    content_hash BYTEA NOT NULL UNIQUE,
                    abstract TEXT,
                    summary TEXT,
                    search_tsv tsvector,
                    tags TEXT[],
                    published_at TIMESTAMP NOT NULL
                )
            """)
            conn.commit()
    return True

def _images_db():
    with new_conn() as conn:
        table_exists = conn.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'images'
            )
        """).fetchone()
        if not table_exists:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS Images (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    blob_url TEXT NOT NULL,
                    paper_id UUID NOT NULL,
                    caption TEXT
                )
            """)
            conn.commit()
    return True


def _vector_db():
    with new_conn() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(conn)
        table_exists = conn.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'vectors'
            )
        """).fetchone()
        # tables = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        # if not tables:
        #     print('no tables found')
        # else:
        #     for table in tables:
        #         print(table)
        #         columns = conn.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table[0]}' AND table_schema = 'public'")
        #         for c in columns:
        #             print(c)

        if not table_exists:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vectors (
                    id BIGSERIAL PRIMARY KEY,
                    external_id TEXT NOT NULL,
                    embedding vector(768) NOT NULL
                )
            """)
            conn.execute('CREATE INDEX ON vectors USING hnsw (embedding vector_l2_ops)')
            conn.commit()
    return True


def db_get_paper(paper_id):
    records = []
    with new_conn() as conn:
        curr = conn.cursor()
        curr.execute("SELECT * FROM papers WHERE external_id = %s",
        (paper_id,))
        for record in curr:
            records.append(record)
    return records


def db_list_recent_papers(limit: int = 20) -> list:
    """Return the most recently ingested papers, newest first.

    Rows are ordered by ``published_at`` (ArXiv publication time). When a
    ``created_at`` column exists or a personalized feed is added, switch ordering there.
    """
    records = []
    with new_conn() as conn:
        curr = conn.cursor()
        curr.execute(
            """
            SELECT * FROM papers
            ORDER BY published_at DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        )
        for record in curr:
            records.append(record)
    return records


def db_get_paper_embeddings(paper_id):
    records = []
    with new_conn() as conn:
        curr = conn.cursor()
        curr.execute("SELECT * FROM vectors WHERE external_id = %s",
                    (paper_id,)
        )
        for record in curr:
            records.append(record)
    return records
                     

def db_search_by_pdf_url(pdf_url):
    records = []
    with new_conn() as conn:
        curr = conn.cursor()
        curr.execute("""
            SELECT * FROM papers WHERE pdf_url = %s
        """,
        (pdf_url,))
        for record in curr:
            records.append(record)
    return records

def db_get_entry(entry_id):
    records = []
    with new_conn() as conn:
        curr = conn.cursor()
        curr.execute("""
            SELECT * FROM papers WHERE id = %s
        """,
        (entry_id,))
        for record in curr:
            records.append(record)
    return records.pop()

def db_semantic_search(query_embeddings):
    records = []
    paper_records = []
    with new_conn() as conn:
        for e in query_embeddings:
            curr = conn.cursor()
            curr.execute("""
                SELECT * FROM vectors ORDER BY embedding <-> %s LIMIT 25;
            """,
            (np.asarray(e, dtype=np.float32),))
            for record in curr:
                records.append(record)
        for record in records:
            paper_id = record['external_id']
            paper_rs = db_get_paper(paper_id)
            for r in paper_rs:
                r['embedding'] = np.asarray(record['embedding'])
                paper_records.append(r)
    return paper_records

def db_keyword_search(keywords: list):
    records = []
    paper_records = []
    with new_conn() as conn:
        curr = conn.cursor()
        curr.execute("""
            SELECT DISTINCT ON (external_id) * FROM papers WHERE search_tsv @@ to_tsquery(%s) ORDER BY external_id, published_at DESC LIMIT 25;
        """,
        (" | ".join(keywords),))
        for record in curr:
            records.append(record)

        for record in records:
            paper_id = record['external_id']
            paper_rs = db_get_paper_embeddings(paper_id)
            for r in paper_rs:
                record['embedding'] = np.asarray(r['embedding'])
                paper_records.append(record)
    return paper_records

def db_add(metadata):
    # TODO: verify metadata is in right format
    with new_conn() as conn:
        conn.execute(
            """INSERT INTO Papers
                (id, external_id, title, authors, pdf_url, html_url, content_hash, published_at)
                VALUES
                (%(id)s, %(external_id)s, %(title)s, %(authors)s, %(pdf_url)s, %(html_url)s, %(content_hash)s, %(published_at)s)
            """,
            metadata
        )
    return True

def test_tables():
    with new_conn() as conn:
        curr = conn.cursor()
        print("papers table")
        curr.execute("""
            SELECT COUNT (id) FROM papers
        """)
        print("length:")
        for record in curr:
            print(record)

        curr.execute("""
            SELECT * FROM papers
        """)

        for record in curr:
            print(record)
        
        curr_images = conn.cursor()
        print("images table")
        curr.execute("""
            SELECT COUNT (DISTINCT id) FROM images
        """)
        print("length:")
        for record in curr:
            print(record)

        curr_images.execute("""
            SELECT * FROM images
        """)
        
        # for record in curr_images:
        #     print(record)

        curr_vectors = conn.cursor()
        print("vectors table")
        curr.execute("""
            SELECT COUNT (DISTINCT id) FROM vectors
        """)
        print("length:")
        for record in curr:
            print(record)

        curr_vectors.execute("""
            SELECT * FROM vectors
        """)
        for record in curr_vectors:
            print(record['external_id'])
    return True

def drop_table(table_name):
    if table_name not in {"papers", "vectors", "images"}:
        return False
    try:
        with new_conn() as conn:
            conn.execute("SET lock_timeout = '5s'")
            conn.execute(
                psycopg.sql.SQL("DROP TABLE IF EXISTS {}").format(
                    psycopg.sql.Identifier(table_name)
                )
            )
            conn.commit()
    except Exception as e:
        print("Error dropping table:", e)
        return False
    return True


def has_embeddings(paper_id):
    with new_conn() as conn:
        curr = conn.cursor()
        curr.execute(
            "SELECT 1 FROM vectors WHERE external_id = %s LIMIT 1",
            (paper_id,)
        )
        return curr.fetchone() is not None

def has_figures(paper_id):
    records = db_get_paper(paper_id)
    if not records:
        return False
    paper_uuid = records[0]["id"]
    with new_conn() as conn:
        curr = conn.cursor()
        curr.execute(
            "SELECT 1 FROM images WHERE paper_id = %s LIMIT 1",
            (paper_uuid,)
        )
        return curr.fetchone() is not None

def has_summary(paper_id):
    with new_conn() as conn:
        curr = conn.cursor()
        curr.execute(
            "SELECT 1 FROM papers WHERE external_id = %s AND summary IS NOT NULL LIMIT 1",
            (paper_id,)
        )
        return curr.fetchone() is not None

def has_keywords(paper_id):
    with new_conn() as conn:
        curr = conn.cursor()
        curr.execute(
            "SELECT 1 FROM papers WHERE external_id = %s AND search_tsv IS NOT NULL LIMIT 1",
            (paper_id,)
        )
        return curr.fetchone() is not None
