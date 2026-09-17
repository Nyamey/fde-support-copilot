"""Tests for ingest.py chunking and retriever.py similarity search.

Uses a real (temp-file) DuckDB connection — fast and avoids mocking DuckDB's
SQL layer — but mocks knowledge_base.db.embed so no real LLM call happens.
"""

import math

import pytest

from knowledge_base import db, ingest, retriever


@pytest.fixture
def kb_path(tmp_path):
    return str(tmp_path / "test_kb.duckdb")


def test_chunk_text_splits_on_paragraph_boundaries():
    text = "First paragraph.\n\nSecond paragraph."
    assert ingest._chunk_text(text) == ["First paragraph.", "Second paragraph."]


def test_chunk_text_hard_wraps_an_overlong_paragraph():
    long_paragraph = "x" * 2500
    chunks = ingest._chunk_text(long_paragraph, max_chars=1000)
    assert len(chunks) == 3
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(chunks) == long_paragraph


def test_ingest_indexes_markdown_and_text_files_only(tmp_path, kb_path, mocker):
    (tmp_path / "notes.md").write_text("A useful FAQ answer.", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("Another useful note.", encoding="utf-8")
    (tmp_path / "ignored.pdf").write_bytes(b"%PDF-not-real")

    mocker.patch.object(db, "embed", side_effect=lambda texts: [[1.0, 0.0] for _ in texts])

    n = ingest.ingest(str(tmp_path), kb_path)

    assert n == 2
    conn = db.get_connection(kb_path)
    try:
        rows = conn.execute("SELECT source, text FROM passages ORDER BY source").fetchall()
    finally:
        conn.close()
    assert [r[1] for r in rows] == ["A useful FAQ answer.", "Another useful note."]


def test_ingest_on_empty_directory_indexes_nothing(tmp_path, kb_path, mocker):
    embed = mocker.patch.object(db, "embed")

    n = ingest.ingest(str(tmp_path), kb_path)

    assert n == 0
    embed.assert_not_called()


def test_search_ranks_by_cosine_similarity(kb_path, mocker):
    mocker.patch.object(db, "DUCKDB_PATH", kb_path)

    conn = db.get_connection(kb_path)
    try:
        conn.execute(
            "INSERT INTO passages VALUES (1, 'a.md', 'closely related passage', ?)", [[1.0, 0.0, 0.0]]
        )
        conn.execute(
            "INSERT INTO passages VALUES (2, 'b.md', 'unrelated passage', ?)", [[0.0, 1.0, 0.0]]
        )
    finally:
        conn.close()

    mocker.patch.object(db, "embed", return_value=[[1.0, 0.0, 0.0]])

    results = retriever.search("some query", top_k=5)

    assert [r.source for r in results] == ["a.md", "b.md"]
    assert math.isclose(results[0].score, 1.0, abs_tol=1e-6)
    assert math.isclose(results[1].score, 0.0, abs_tol=1e-6)


def test_search_on_empty_index_returns_nothing(kb_path, mocker):
    mocker.patch.object(db, "DUCKDB_PATH", kb_path)
    db.get_connection(kb_path).close()  # create the empty table
    embed = mocker.patch.object(db, "embed")

    results = retriever.search("anything", top_k=5)

    assert results == []
    embed.assert_not_called()


def test_search_with_a_zero_vector_query_embedding_returns_nothing(kb_path, mocker):
    """A malformed/zero embedding would divide by zero in the cosine-similarity
    calculation — guarded against explicitly rather than left to crash.
    """
    mocker.patch.object(db, "DUCKDB_PATH", kb_path)
    conn = db.get_connection(kb_path)
    try:
        conn.execute("INSERT INTO passages VALUES (1, 'a.md', 'some passage', ?)", [[1.0, 0.0]])
    finally:
        conn.close()
    mocker.patch.object(db, "embed", return_value=[[0.0, 0.0]])

    assert retriever.search("anything", top_k=5) == []


def test_add_to_index_makes_a_passage_searchable(kb_path, mocker):
    mocker.patch.object(db, "DUCKDB_PATH", kb_path)
    mocker.patch.object(db, "embed", return_value=[[1.0, 0.0]])

    retriever.add_to_index(source="slack-thread:C1:1.1", text="Q: reset password? A: click forgot password")

    conn = db.get_connection(kb_path)
    try:
        row = conn.execute("SELECT source, text FROM passages").fetchone()
    finally:
        conn.close()
    assert row[0] == "slack-thread:C1:1.1"
    assert "reset password" in row[1]
