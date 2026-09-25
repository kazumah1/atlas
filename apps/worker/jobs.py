import redis
from dotenv import load_dotenv
import argparse
import os
import json
import hashlib
import re
import requests
from PyPDF2 import PdfReader
import io
from infra.postgres import _postgres_db, _vector_db, _images_db, new_conn, db_search_by_pdf_url
from infra.redis import get_cached_pdf, cache_pdf
from infra.gcs import upload_paper
from apps.worker.processor import embed, figures, keywords, summarize
from utils.utils import Colors


JOB_QUEUE = "job_queue"
ARXIV_ID_PATTERN = re.compile(
    r"(?P<identifier>(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)",
    re.IGNORECASE,
)

class ArxivDataManager:
    def __init__(self):
        ...

    def get_arxiv_id(self, value):
        """Extract a modern or legacy ArXiv identifier from URLs and RSS IDs."""
        match = ARXIV_ID_PATTERN.search(value or "")
        if match is None:
            raise ValueError(f"Could not extract ArXiv id from {value!r}")
        return match.group("identifier").removesuffix(".pdf")

    def convert_url_to_html_url(self, url):
        """Convert any supported ArXiv identifier or URL to a canonical HTML URL."""
        return f"https://arxiv.org/html/{self.get_arxiv_id(url)}"
   
    def get_pdf_url(self, entry):
        links = entry["links"]
        for link in links:
            if "title" in link:
                if link["title"] == 'pdf':
                    return link["href"]
            href = link.get("href", "")
            if "/abs/" in href:
                return href.replace("/abs/", "/pdf/")
        return None

    def get_entry_id(self, entry, pdf_url):
        try:
            return self.get_arxiv_id(entry.get("id", ""))
        except ValueError:
            return self.get_arxiv_id(pdf_url)
    
    def get_authors(self, entry):
        return [a['name'] for a in entry['authors']]

    def get_tags(self, entry):
        tags = []
        primaries = set()
        for tag in entry['tags']:
            tags.append(tag['term'])
            if "." in tag['term']:
                primaries.add(tag['term'].split('.')[0])
        return tags + list(primaries)


class JobManager:
    def __init__(self):
        self.redis = None
        self.ingest_q = None
        self.process_q = None

        # workers
        self.worker = None

        # data managers for creating jobs
        self.arxiv = ArxivDataManager()

        # job types as of now
        self.JOBS = {
            'embed': embed, 
            'figures': figures, 
            'summarize': summarize, 
            'keywords': keywords
        }

        print("Loaded papers table:", _postgres_db())
        print("Loaded vectors table:", _vector_db())
        print("Loaded images table:", _images_db())

        self.initialize_redis()

    def store(self, job: dict):
        '''
        for storing the raw pdf of the paper to GCS
        '''
        # ingest doc to object storage
        pdf_content = get_cached_pdf(job['id'])
        if pdf_content is None:
            pdf_url = job["pdf_url"]
            response = requests.get(pdf_url)
            pdf_content = response.content
            cache_pdf(job['id'], pdf_content)
        filename = job["content_hash"] + ".pdf"

        upload_paper(filename, pdf_content)

        print(f"{Colors.GREEN}Successfully stored paper to GCS{Colors.WHITE}")

    def db_push(self, job: dict):
        with new_conn() as conn:
            conn.execute(
                """INSERT INTO Papers 
                    (external_id, source, title, authors, pdf_url, html_url, content_hash, tags, published_at)
                    VALUES 
                    (%(id)s, %(source)s, %(title)s, %(authors)s, %(pdf_url)s, %(html_url)s, %(content_hash)s, %(tags)s, %(published_at)s)
                    ON CONFLICT (external_id) DO NOTHING;
                """,
                job
            )
            conn.commit()
        print(f"{Colors.GREEN}Successfully stored initial DB entry{Colors.WHITE}")

 
    def initialize_redis(self):
        load_dotenv()
        if os.getenv("DEVELOPMENT") == 'true':
            r = redis.Redis(
                host=os.getenv("REDIS_HOST_DEV"),
                port=os.getenv("REDIS_PORT"),
                decode_responses=False,
                username="default",
                password=""
            )
        else:
            r = redis.from_url(os.getenv("REDIS_URL_PROD"), decode_responses=False)
        self.redis = r
        # self.ingest_q = Queue("ingest", connection=self.redis)
        # self.process_q = Queue("process", connection=self.redis)
        # self.worker = Worker([self.ingest_q, self.process_q], connection=self.redis)

    def hash_file(self, pdf_url, job_id):
        pdf_content = get_cached_pdf(job_id)
        max_retries = 4
        retries = 0
        completed = False
        while not completed and retries < max_retries:
            if pdf_content is None:
                response = requests.get(pdf_url)
                pdf_content = response.content
                cache_pdf(job_id, pdf_content)
            mem_object = io.BytesIO(pdf_content)
            file = PdfReader(mem_object)
            h = hashlib.sha256()
            for page in file.pages:
                text = page.extract_text()
                text_bytes = text.encode('utf-8', errors='surrogatepass').decode('utf-16', errors='ignore').encode('utf-8')
                h.update(text_bytes)
            return h.hexdigest()
    
    def add_job(self, job: dict):
        r = self.redis
        # TODO: use pydantic
        required_fields = {"id", "pdf_url", "html_url", "source", "job_type"}
        for field in required_fields:
            if field not in job.keys():
                raise ValueError("missing or incorrect field: ", field)
        serialized_job = json.dumps(job)
        return r.xadd(JOB_QUEUE, {"job": serialized_job}, maxlen=50000, approximate=False)
        

    def create_job_set(self, entry):
        '''
        for creating all subjobs once an entry is received
        types:
            - store: store raw pdf into gcs (ingestor)
            - embed: store text embeddings to vector db (pgvector) for semantic search (processor)
            - db_push: insert new postgres row (ingestor)
            - figures: extract figures from pdf/html, store in gcs, map to corresponding pdf (processor)
            - summarize: use llm to summarize paper to display on frontend (processor)
            - keywords: use tsvector to extract keywords from paper for later search and tagging (processor)
        '''
        pdf_url = self.arxiv.get_pdf_url(entry)
        if pdf_url is None:
            print(f"No PDF URL for {entry.get('title', entry.get('id', 'unknown'))}, skipping")
            return
        records = db_search_by_pdf_url(pdf_url)
        if records:
            return
        arxiv_id = self.arxiv.get_entry_id(entry, pdf_url)
        job_id = "arxiv." + arxiv_id
        content_hash = self.hash_file(pdf_url, job_id)
        authors = self.arxiv.get_authors(entry)
        html_url = self.arxiv.convert_url_to_html_url(arxiv_id)
        title = entry['title']
        publish_date = entry['published']
        tags = self.arxiv.get_tags(entry)
        job = {
            "id":job_id,
            "title":title,
            "authors":authors,
            "pdf_url":pdf_url,
            "html_url":html_url,
            "source":"arxiv",
            "content_hash":content_hash,
            "license":"",
            "published_at":publish_date,
            "tags":tags
        }
        self.store(job)
        self.db_push(job)
        for job_type in self.JOBS.keys():
            job = {
                "id":job_id,
                "title":title,
                "authors":authors,
                "pdf_url":pdf_url,
                "html_url":html_url,
                "source":"arxiv",
                "content_hash":content_hash,
                "license":"",
                "published_at":publish_date,
                "tags":tags,
                "job_type":job_type
            }
            self.add_job(job=job)


    def _normalize_job(self, job):
        if job.get("source") == "arxiv":
            job["html_url"] = self.arxiv.convert_url_to_html_url(job["pdf_url"])
        return job

    def _run_job(self, stream_id, fields, retries=3):
        serialized_job = fields.get(b"job") or fields.get("job")
        if isinstance(serialized_job, bytes):
            serialized_job = serialized_job.decode("utf-8")
        if not serialized_job:
            print(f"{Colors.RED}Job {stream_id!r} has no payload{Colors.WHITE}")
            return False

        job = self._normalize_job(json.loads(serialized_job))
        job_type = job.get("job_type")
        job_func = self.JOBS.get(job_type)
        if job_func is None:
            print(f"{Colors.RED}Unknown job type {job_type!r}{Colors.WHITE}")
            return False

        normalized_payload = json.dumps(job)
        for attempt in range(1, retries + 1):
            try:
                print(f"{Colors.BLUE}Job: {job_type} (attempt {attempt}/{retries}){Colors.WHITE}")
                job_func(normalized_payload)
                self.redis.xdel(JOB_QUEUE, stream_id)
                return True
            except Exception as exc:
                print(f"{Colors.RED}{job_type} failed: {exc}{Colors.WHITE}")
        return False

    def process_jobs(self, stop_when_empty=False, max_jobs=None, block_ms=5000):
        """Process existing backlog first, deleting only successful jobs."""
        cursor = "0-0"
        attempted = 0
        succeeded = 0

        while True:
            try:
                jobs = self.redis.xread(
                    streams={JOB_QUEUE: cursor},
                    count=100,
                    block=None if stop_when_empty else block_ms,
                )
                if not jobs:
                    if stop_when_empty:
                        return {"attempted": attempted, "succeeded": succeeded}
                    continue

                for _, entries in jobs:
                    for stream_id, fields in entries:
                        cursor = stream_id
                        attempted += 1
                        succeeded += int(self._run_job(stream_id, fields))
                        if max_jobs is not None and attempted >= max_jobs:
                            return {"attempted": attempted, "succeeded": succeeded}
            except (KeyboardInterrupt, SystemExit):
                self.jobs_info()
                raise

    def start_workers(self):
        return self.process_jobs(stop_when_empty=False)

    def drain_jobs(self, max_jobs=None):
        return self.process_jobs(stop_when_empty=True, max_jobs=max_jobs)

    def enqueue_missing_summaries(self, limit=100):
        """Queue a controlled batch of existing papers that have no summary."""
        with new_conn() as conn:
            records = conn.execute(
                """
                SELECT external_id, source, pdf_url, html_url
                FROM papers
                WHERE summary IS NULL
                ORDER BY published_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()

        queued = 0
        for record in records:
            html_url = record["html_url"]
            if record["source"] == "arxiv":
                html_url = self.arxiv.convert_url_to_html_url(record["pdf_url"])
                with new_conn() as conn:
                    conn.execute(
                        "UPDATE papers SET html_url = %s WHERE external_id = %s",
                        (html_url, record["external_id"]),
                    )
                    conn.commit()
            self.add_job(
                {
                    "id": record["external_id"],
                    "source": record["source"],
                    "pdf_url": record["pdf_url"],
                    "html_url": html_url,
                    "job_type": "summarize",
                }
            )
            queued += 1
        return queued

    def jobs_info(self): 
        print("Queue State")
        print(f"queue length: {self.redis.xlen('job_queue')}")
        # print("Ingest Workers")
        # for w in ingest_workers:
        #     print(f"Worker {w.name}:")
        #     print("Successful Jobs | Failed Jobs | Total Working Time")
        #     print(f"   {w.successful_job_count}   |   {w.failed_job_count}   |   {w.total_working_time}   ")

        # print()
        # print("Process Workers")
        # for w in process_workers:
        #     print(f"Worker {w.name}:")
        #     print("Successful Jobs | Failed Jobs | Total Working Time")
        #     print(f"   {w.successful_job_count}   |   {w.failed_job_count}   |   {w.total_working_time}   ")

    def clear_job_queue(self):
        res = self.redis.xtrim("job_queue", maxlen=0, approximate=False)
        print(res)
        self.jobs_info()

if __name__ == "__main__":
    from apps.worker.shared import job_manager

    parser = argparse.ArgumentParser(description="Process paper jobs")
    parser.add_argument("--drain", action="store_true", help="Exit when queue is empty")
    parser.add_argument("--max-jobs", type=int, default=None)
    parser.add_argument("--enqueue-missing-summaries", type=int, metavar="LIMIT")
    args = parser.parse_args()

    if args.enqueue_missing_summaries is not None:
        print(f"Queued {job_manager.enqueue_missing_summaries(args.enqueue_missing_summaries)} summaries")
    if args.drain:
        print(job_manager.drain_jobs(max_jobs=args.max_jobs))
    elif args.enqueue_missing_summaries is None:
        job_manager.start_workers()
