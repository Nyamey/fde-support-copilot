"""Loads a knowledge base (docs, past resolved tickets, FAQ) into DuckDB with
embeddings, so retriever.py can run similarity search against it.

Usage:
    python knowledge_base/ingest.py --source ./docs

Reuses the same DuckDB-first approach as ai-data-agent rather than reaching
for a separate vector-database service — keeps the deployment footprint to
"one container, no extra managed service" for the free-tier cloud deploy.
"""

import argparse
from pathlib import Path

from knowledge_base import db

INDEXABLE_SUFFIXES = {".md", ".txt"}
MAX_CHUNK_CHARS = 1000


def _chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split on blank-line paragraph boundaries first (keeps a chunk's meaning
    intact), then hard-wrap any paragraph still too long for one embedding call.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
        else:
            for i in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[i : i + max_chars])
    return chunks


def ingest(source_dir: str, db_path: str) -> int:
    """Chunk every .md/.txt document under source_dir, embed each chunk, and
    upsert into the DuckDB table used by retriever.py. Returns the number of
    chunks indexed.
    """
    source_path = Path(source_dir)
    if not source_path.is_dir():
        raise FileNotFoundError(f"{source_dir} is not a directory")

    documents: list[tuple[str, str]] = []  # (source, chunk_text)
    for file_path in sorted(source_path.rglob("*")):
        if file_path.is_file() and file_path.suffix.lower() in INDEXABLE_SUFFIXES:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            relative_source = str(file_path.relative_to(source_path))
            for chunk in _chunk_text(text):
                documents.append((relative_source, chunk))

    if not documents:
        return 0

    embeddings = db.embed([chunk for _source, chunk in documents])

    conn = db.get_connection(db_path)
    try:
        start_id = db.next_id(conn)
        rows = [
            (start_id + i, source, chunk, embedding)
            for i, ((source, chunk), embedding) in enumerate(zip(documents, embeddings))
        ]
        conn.executemany(
            "INSERT INTO passages (id, source, text, embedding) VALUES (?, ?, ?, ?)",
            rows,
        )
    finally:
        conn.close()

    return len(documents)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="directory of docs to index")
    parser.add_argument("--db", default=db.DUCKDB_PATH)
    args = parser.parse_args()
    n = ingest(args.source, args.db)
    print(f"Indexed {n} chunks into {args.db}")
