"""Similarity search over the DuckDB knowledge base built by ingest.py."""

import numpy as np

from agent.state import RetrievedPassage
from knowledge_base import db


def search(query: str, top_k: int = 5) -> list[RetrievedPassage]:
    """Embed the query, run a cosine-similarity search against every indexed
    passage, and return the top_k ordered by score (descending).

    Plain in-Python cosine similarity rather than DuckDB's VSS extension: the
    knowledge base a small support team builds up is realistically hundreds
    to a few thousand chunks, well within range for a full scan, and it
    avoids depending on an extension that isn't guaranteed to be available on
    every DuckDB build.
    """
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT source, text, embedding FROM passages").fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    query_embedding = np.array(db.embed([query])[0])
    query_norm = np.linalg.norm(query_embedding)
    if query_norm == 0:
        return []

    scored: list[RetrievedPassage] = []
    for source, text, embedding in rows:
        vec = np.array(embedding)
        denom = query_norm * np.linalg.norm(vec)
        score = float(np.dot(query_embedding, vec) / denom) if denom else 0.0
        scored.append(RetrievedPassage(source=source, text=text, score=score))

    scored.sort(key=lambda p: p.score, reverse=True)
    return scored[:top_k]


def add_to_index(source: str, text: str) -> None:
    """Append one new passage to the index — used by agent/nodes.py's log()
    node so an approved answer becomes retrievable for the next similar
    question, without re-running the full ingest.py pass.
    """
    conn = db.get_connection()
    try:
        embedding = db.embed([text])[0]
        new_id = db.next_id(conn)
        conn.execute(
            "INSERT INTO passages (id, source, text, embedding) VALUES (?, ?, ?, ?)",
            (new_id, source, text, embedding),
        )
    finally:
        conn.close()
