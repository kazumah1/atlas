import json

from apps.worker.jobs import ArxivDataManager, JobManager


class FakeRedis:
    def __init__(self, entries):
        self.entries = entries
        self.reads = []
        self.deleted = []

    def xread(self, streams, count, block):
        self.reads.append({"streams": streams, "count": count, "block": block})
        if self.entries is None:
            return []
        entries, self.entries = self.entries, None
        return [(b"job_queue", entries)]

    def xdel(self, stream, stream_id):
        self.deleted.append((stream, stream_id))


def _manager(entries, jobs):
    manager = object.__new__(JobManager)
    manager.redis = FakeRedis(entries)
    manager.arxiv = ArxivDataManager()
    manager.JOBS = jobs
    return manager


def test_arxiv_rss_id_and_urls_are_normalized():
    arxiv = ArxivDataManager()

    identifier = arxiv.get_arxiv_id("oai:arXiv.org:2408.01400v5")

    assert identifier == "2408.01400v5"
    assert arxiv.convert_url_to_html_url(identifier) == (
        "https://arxiv.org/html/2408.01400v5"
    )
    assert arxiv.convert_url_to_html_url("https://arxiv.org/pdf/2408.01400") == (
        "https://arxiv.org/html/2408.01400"
    )


def test_worker_reads_backlog_and_deletes_only_successful_jobs():
    calls = {"success": 0, "failure": 0}

    def succeeds(_payload):
        calls["success"] += 1

    def fails(_payload):
        calls["failure"] += 1
        raise RuntimeError("temporary failure")

    success_job = json.dumps(
        {
            "id": "arxiv.good",
            "source": "arxiv",
            "pdf_url": "https://arxiv.org/pdf/2408.01400",
            "html_url": "broken",
            "job_type": "success",
        }
    ).encode()
    failed_job = json.dumps(
        {
            "id": "arxiv.failed",
            "source": "arxiv",
            "pdf_url": "https://arxiv.org/pdf/2408.01401",
            "html_url": "broken",
            "job_type": "failure",
        }
    ).encode()
    manager = _manager(
        [
            (b"1-0", {b"job": success_job}),
            (b"2-0", {b"job": failed_job}),
        ],
        {"success": succeeds, "failure": fails},
    )

    result = manager.drain_jobs()

    assert manager.redis.reads[0]["streams"] == {"job_queue": "0-0"}
    assert manager.redis.deleted == [("job_queue", b"1-0")]
    assert calls == {"success": 1, "failure": 3}
    assert result == {"attempted": 2, "succeeded": 1}


def test_worker_repairs_html_url_before_processing():
    received = {}

    def capture(payload):
        received.update(json.loads(payload))

    payload = json.dumps(
        {
            "id": "arxiv.400v5",
            "source": "arxiv",
            "pdf_url": "https://arxiv.org/pdf/2408.01400",
            "html_url": "oai:arXiv.org:240html1400v5",
            "job_type": "summarize",
        }
    ).encode()
    manager = _manager([(b"1-0", {b"job": payload})], {"summarize": capture})

    manager.drain_jobs()

    assert received["html_url"] == "https://arxiv.org/html/2408.01400"
