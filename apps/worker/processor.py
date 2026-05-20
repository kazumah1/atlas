import json
from bs4 import BeautifulSoup
from infra.postgres import _postgres_db, _images_db, _vector_db, test_tables, db_get_paper, drop_table, new_conn, has_embeddings, has_figures, has_keywords, has_summary
from infra.gcs import upload_figure, upload_paper
from infra.redis import cache_pdf, get_cached_pdf
from apps.llm import OpenAIClient, OllamaClient
from utils.utils import Colors
from openai import OpenAI
from PyPDF2 import PdfReader
from io import BytesIO
from pgvector.psycopg import register_vector
import numpy as np
import re
import pymupdf
import requests
import hashlib
import feedparser
import psycopg
import io
from dotenv import load_dotenv
import os

load_dotenv()

OPENAI_CLIENT = OpenAIClient()
OLLAMA_CLIENT = OllamaClient()
_embed_client = None
_local_model = None

def embed_texts(texts: list[str]) -> list[np.ndarray]:
    if os.getenv("DEVELOPMENT") == "true":
        global _local_model
        if _local_model is None:
            from sentence_transformers import SentenceTransformer
            _local_model = SentenceTransformer("nomic-ai/nomic-embed-text-v1", trust_remote_code=True)
        return [e.astype(np.float32) for e in _local_model.encode(texts)]
    else:
        global _embed_client
        if _embed_client is None:
            _embed_client = OpenAI()
        embeddings = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = _embed_client.embeddings.create(
                model="text-embedding-3-small",
                input=batch,
                dimensions=768
            )
            embeddings.extend([np.array(item.embedding, dtype=np.float32) for item in response.data])
        return embeddings

chunk_prefix_length = 17
CONTEXT_LENGTH = 2048 - chunk_prefix_length # length of 'search_document: '


URL : str = "http://export.arxiv.org/"

def _get_url(entry):
    '''returns the url of a specific entry'''
    return entry["id"]

def _get_entries(parser_output):
    '''returns the entries array from the raw feedparser output'''
    return parser_output["entries"]

def search(search_queries:list[str], max_results:int=10, page:int=0, sort:str="submittedDate", sort_order:str="descending"):
    global URL
    search_arg = "+OR+".join(search_queries)
    url = URL + f'api/query?search_query={search_arg}&start={page}&sortBy={sort}&sortOrder={sort_order}'
    if max_results:
        url += f"&max_results={max_results}"
    response = requests.get(url)
    d = feedparser.parse(response.text)
    entries = _get_entries(d)
    # for entry in entries:
    #     ingest(entry)
    return entries

def subscribe(categories:list[str]):
    """accesses an ArXiv rss feed for various categories"""
    global URL
    rss_arg = "+".join(categories)
    url = URL + f'rss/{rss_arg}'
    response = requests.get(url)
    d = feedparser.parse(response.text)
    entries = _get_entries(d)
    # for entry in entries:
    #     ingest(entry)
    return entries

def embed(serialized_job):
    '''
    generating embeddings with openai then storing embeddings + metadata in pgvector vector db
    for semantic search and later rag
    '''
    global CONTEXT_LENGTH
    job = json.loads(serialized_job)
    
    paper_id = job['id']
    if has_embeddings(paper_id):
        return
    pdf_url = job['pdf_url']
    pdf_content = get_cached_pdf(job['id'])
    if pdf_content is None:
        pdf_url = job["pdf_url"]
        response = requests.get(pdf_url)
        pdf_content = response.content
        cache_pdf(job['id'], pdf_content)
    memfile = BytesIO(pdf_content)
    reader = PdfReader(memfile)


    full_text = ""
    for p in reader.pages:
        full_text += p.extract_text()

    full_text = full_text.replace("-\n", "")
    full_text = full_text.replace("\n", " ")
    sentences = re.split(r'(?<=\.)', full_text)
    
    text_chunks = []
    line = 'search_document: '
    curr_len = len(line)

    # curr_chunk = 0
    # while curr_chunk + context_length <= len(full_text):
    #     text_chunks.append('search document: ' + full_text[curr_chunk:curr_chunk+context_length])
    #     curr_chunk += context_length - ((self.context_length + self.chunk_prefix_length) // 8)
    # if curr_chunk < len(full_text):
    #     text_chunks.append('search document: ' + full_text[curr_chunk:])
    for s in sentences:
        if curr_len + len(s) > CONTEXT_LENGTH:
            text_chunks.append(line)
            temp_s = s
            if len(temp_s) >= CONTEXT_LENGTH:
                while len(temp_s) >= CONTEXT_LENGTH:
                    line = 'search_document: '
                    line += temp_s[:CONTEXT_LENGTH]
                    text_chunks.append(line)
                    temp_s = temp_s[CONTEXT_LENGTH:]
            line = 'search_document: '
            curr_len = len(line)
            line += temp_s
            curr_len += len(temp_s)
        else:
            line += s
            curr_len += len(s)
    # Append the last partial chunk that never exceeded CONTEXT_LENGTH
    if curr_len > len('search_document: '):
        text_chunks.append(line)
    if not text_chunks:
        print(f"{Colors.YELLOW}No text extracted from PDF, skipping embed{Colors.WHITE}")
        return
    embeddings = embed_texts(text_chunks)
    # for chunk in text_chunks:
    #    print(chunk)
    #    print()
    with new_conn() as conn:
        register_vector(conn)
        for e in embeddings:
            conn.execute(
                    "INSERT INTO vectors (external_id, embedding) values (%s, %s)",
                    (job['id'], e,)
            )
        conn.commit()

    print(f"{Colors.GREEN}Successfully embedded paper content{Colors.WHITE}")

    return

def figures(serialized_job):
    job = json.loads(serialized_job)
    
    paper_id = job['id']
    if has_figures(paper_id):
        return
    pdf_url = job['pdf_url']
    pdf_content = get_cached_pdf(job['id'])
    if pdf_content is None:
        pdf_url = job["pdf_url"]
        response = requests.get(pdf_url)
        pdf_content = response.content
        cache_pdf(job['id'], pdf_content)
    filestream = BytesIO(pdf_content)
    pdf = pymupdf.open(stream=filestream)

    records = db_get_paper(paper_id)

    if not records:
        raise ValueError("No paper with given id")
    elif len(records) > 1:
        print(f"{Colors.YELLOW}More than one paper found{Colors.WHITE}")

    img_count = 0
    paper = records[0]
    if paper:
        for page in pdf:
            images = page.get_images()
            for img_idx, image in enumerate(images):
                xref = image[0]
                img = pdf.extract_image(xref)
                img_bytes = BytesIO(img['image'])
                file_destination = paper_id + '/' + str(img_count)
                upload_figure(img_bytes, file_destination) 
                
                if paper:
                    paper_table_id = paper["id"]
                    with new_conn() as conn:
                        conn.execute(
                            "INSERT INTO images (blob_url, paper_id, caption) values (%s, %s, %s)",
                            (file_destination, paper_table_id, "")
                        )
                        conn.commit()

                img_count += 1
    print(f"{Colors.GREEN}Successfully stored figures{Colors.WHITE}")

    return


def summarize(serialized_job):
    global OPENAI_CLIENT
    job = json.loads(serialized_job)
    html_url = job['html_url']
    paper_id = job['id']
    if has_summary(paper_id):
        return
    text, paper_abstract = get_text_and_abstract(html_url)

    records = db_get_paper(paper_id)
    if not records:
        raise ValueError("Error summarizing paper: No paper with given id")
        return False
    elif len(records) > 1:
        print(f"{Colors.YELLOW}More than one paper found{Colors.WHITE}")

    paper = records[0]
    if paper:
        with new_conn() as conn:
            conn.execute("""
                UPDATE papers
                SET abstract = %s
                WHERE external_id = %s;
            """,
                (paper_abstract, paper_id)
            )
            conn.commit()
            print(f"{Colors.GREEN}Successfully extracted abstract{Colors.WHITE}")
            try:
                summary_text = OPENAI_CLIENT.summarize(text)
                conn.execute("""
                    UPDATE papers
                    SET summary = %s
                    WHERE external_id = %s;
                """,
                    (summary_text, paper_id)
                )
                print(f"{Colors.GREEN}Successfully summarized paper with OpenAI{Colors.WHITE}")
                conn.commit()
            except Exception as e:
                try:
                    summary_text = OLLAMA_CLIENT.summarize(text)
                    conn.execute("""
                        UPDATE papers
                        SET summary = %s
                        WHERE external_id = %s;
                    """,
                        (summary_text, paper_id)
                    )
                    print(f"{Colors.GREEN}Successfully summarized paper with Ollama{Colors.WHITE}")
                    conn.commit()
                except Exception as e:
                    raise ValueError("Error saving summary")
    return True



def get_text_and_abstract(html_url: str) -> tuple[str, str]:
    print(f"{Colors.YELLOW}html_url = {html_url}{Colors.WHITE}")
    response = requests.get(html_url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Remove tables, math elements, and appendix sections
    for el in soup.find_all('table'):
        el.decompose()
    for el in soup.find_all(class_=re.compile(r'ltx_(equation|equationgroup|Math)')):
        el.decompose()
    for el in soup.find_all(class_='ltx_appendix'):
        el.decompose()

    # Extract abstract
    abstract_div = soup.find('div', class_='ltx_abstract')
    if abstract_div is None:
        return ("", "")
    abstract_text = abstract_div.get_text()[8:]  # strip leading "Abstract" heading

    # Extract conclusion section
    conclusion_text = ""
    for section in soup.find_all('section', class_='ltx_section'):
        heading = section.find(re.compile(r'h\d'))
        if heading and 'conclusion' in heading.get_text().lower():
            conclusion_text = section.get_text()
            break

    combined = abstract_text + " " + conclusion_text
    combined = re.sub(r'\([^)]*\d{4}[^)]*\)', '', combined)  # strip citation markers
    combined = " ".join(combined.split())

    return combined, abstract_text


def keywords(serialized_job):
    job = json.loads(serialized_job)
    html_url = job['html_url']
    paper_id = job['id']
    if has_keywords(paper_id):
        return
    records = db_get_paper(paper_id)
    if not records:
        raise ValueError("Error getting keywords: No paper with given id")
    elif len(records) > 1:
        print(f"{Colors.YELLOW}More than one paper returned{Colors.WHITE}")
    paper = records[0]
    if paper:
        title = paper['title']
        abstract = paper['abstract']
        if title is None:
            raise ValueError("Error getting keywords: no title")
        if abstract is None:
            text, paper_abstract = get_text_and_abstract(html_url)

            records = db_get_paper(paper_id)
            if not records:
                raise ValueError("Error getting keywords: No paper with given id")
            elif len(records) > 1:
                print(f"{Colors.YELLOW}More than one paper found{Colors.WHITE}")

            paper = records[0]
            if paper:
                with new_conn() as conn:
                    conn.execute("""
                        UPDATE papers
                        SET abstract = %s
                        WHERE external_id = %s;
                    """,
                        (paper_abstract, paper_id)
                    )
                    conn.commit()
                abstract = paper_abstract
        text = (title or "") + (abstract or "")
        with new_conn() as conn:
            conn.execute("""
                UPDATE papers
                SET search_tsv = to_tsvector('english', %s)
                WHERE external_id = %s;
            """,
                (text, paper_id)
            )
            conn.commit()
    print("Successfully stored keywords")
    return True


if __name__ == "__main__":
    drop = False
    try:
        test_tables()
    except Exception as e:
        print("Error testing tables:", e)
    if drop:
        print(drop_table("papers"))
        print(drop_table("vectors"))
        print(drop_table("images"))
        test_tables()
    # job = {
    #         "id": "arxiv.2511.11551",
    #         "pdf_url": "https://arxiv.org/pdf/2511.11551",
    #         "html_url": "https://arxiv.org/html/2511.11551",
    # }
    # print(summarize(json.dumps(job)))
    # job2 = {
    #         "id":"arxiv.2512.22121v1",
    #         "pdf_url": "https://arxiv.org/pdf/2512.22121v1",
    #         "html_url": "https://arxiv.org/html/2512.22121v1",
    # }
    # print(summarize(json.dumps(job2)))
    # print(keywords(json.dumps(job)))
    # figures(json.dumps(job))
