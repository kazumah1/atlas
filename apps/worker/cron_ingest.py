from apps.worker.jobs import JobManager
from apps.worker.processor import subscribe
from apps.worker.shared import job_manager
from concurrent.futures import ThreadPoolExecutor
from more_itertools import chunked

# Constants
BATCH_SIZE = 50

# A utility function to handle a batch of entries for job creation
def process_batch(entries_batch):
    for entry in entries_batch:
        print(f"Ingesting {entry['title']}")
        job_manager.create_job_set(entry)

if __name__ == "__main__":
    categories = [
        "cs", "quant-ph", "cond-mat", "gr-qc", "physics", "stat", "q-fin",
        "q-bio", "econ", "astro-ph", "hep-ex", "hep-lat", "hep-ph",
        "hep-th", "nlin", "nucl-ex", "nucl-th", "math-ph", "eess", "math"
    ]

    # Group categories into pairs
    categories = [list(p) for p in zip(categories[::2], categories[1::2])]

    # Initialize a thread pool for parallel processing
    futures = []
    with ThreadPoolExecutor() as executor:
        for c in categories:
            print(f"Category: {c}")
            entries = subscribe(categories=c)

            # Split entries into batches and process them in parallel
            for batch in chunked(entries, BATCH_SIZE):
                futures.append(executor.submit(process_batch, batch))

    for f in futures:
        f.result()
