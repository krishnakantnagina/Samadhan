"""Build the scheme RAG index: embed every row of specs/registry/schemes.csv with Gemini and save specs/registry/schemes_index.json.

Run once, and again whenever schemes.csv changes (the index stores a hash of the CSV; the backend ignores a stale index):
    uv run --env-file ../.env python scripts/build_scheme_index.py
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import schemes

BATCH = 50


def main() -> None:
    key = os.environ["GEMINI_API_KEY"].strip()
    rows = [s for s, _ in schemes._load()]
    vectors: list[list[float]] = []
    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        body = {
            "requests": [
                {
                    "model": f"models/{schemes.EMBED_MODEL}",
                    "content": {"parts": [{"text": schemes.doc_text(s)}]},
                    "taskType": "RETRIEVAL_DOCUMENT",
                    "outputDimensionality": schemes.EMBED_DIM,
                }
                for s in chunk
            ]
        }
        for attempt in range(6):
            r = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{schemes.EMBED_MODEL}:batchEmbedContents",
                headers={"x-goog-api-key": key},
                json=body,
                timeout=60,
            )
            if r.status_code == 200:
                break
            print(f"batch {i}: HTTP {r.status_code}, retry {attempt + 1}")
            time.sleep(5 * (attempt + 1))
        r.raise_for_status()
        vectors += [schemes.normalise(e["values"]) for e in r.json()["embeddings"]]
        print(f"{len(vectors)}/{len(rows)}")
    out = {
        "model": schemes.EMBED_MODEL,
        "dim": schemes.EMBED_DIM,
        "csv_sha256": schemes.csv_hash(),
        "vectors": [[round(x, 4) for x in v] for v in vectors],
    }
    schemes.INDEX_FILE.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print("wrote", schemes.INDEX_FILE, f"{schemes.INDEX_FILE.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
