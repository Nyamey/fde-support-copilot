"""Shared DuckDB connection and embedding helpers for ingest.py and retriever.py.

Deliberately reuses LiteLLM for embeddings rather than adding a dedicated
embeddings dependency (sentence-transformers, etc.) — one less thing to
install in the Docker image, and it reuses whichever API key is already
configured for the chat model.
"""

import os

import duckdb
import litellm

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "./knowledge_base/kb.duckdb")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "mistral/mistral-embed")


def get_connection(db_path: str | None = None) -> duckdb.DuckDBPyConnection:
    """Open the knowledge-base DuckDB file, creating the passages table if needed."""
    conn = duckdb.connect(db_path or DUCKDB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS passages (
            id BIGINT PRIMARY KEY,
            source VARCHAR,
            text VARCHAR,
            embedding DOUBLE[]
        )
        """
    )
    return conn


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts via LiteLLM. Raises if no embedding-capable
    provider is configured (see EMBEDDING_MODEL in .env.example).
    """
    if not texts:
        return []
    response = litellm.embedding(model=EMBEDDING_MODEL, input=texts)
    return [item["embedding"] for item in response["data"]]


def next_id(conn: duckdb.DuckDBPyConnection) -> int:
    """Next free primary key, so ingest.py and add_to_index() never collide."""
    row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM passages").fetchone()
    return row[0]
