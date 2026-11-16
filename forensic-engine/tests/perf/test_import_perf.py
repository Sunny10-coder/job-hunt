import os
import time
from pathlib import Path

import pytest

from wfs_engine import importer, samples


def _run_import(conn, case, messages: int, tmp_path: Path) -> float:
    source = tmp_path / f"big-{messages}.txt"
    source.write_text(samples.big_dataset(messages), encoding="utf-8")
    started = time.perf_counter()
    importer.import_single_file(conn, case["id"], source,
                               {"source_timezone": "UTC", "date_order": "mdy"})
    return time.perf_counter() - started


def test_import_20k_messages_is_fast(conn, case, tmp_path):
    elapsed = _run_import(conn, case, 20_000, tmp_path)
    count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert count == 20_000
    # Generous bound for shared CI hardware; the 100k target is measured separately.
    assert elapsed < 90, f"20k import took {elapsed:.1f}s"
    print(f"\n20k messages imported in {elapsed:.2f}s")


@pytest.mark.skipif(os.environ.get("WFS_PERF") != "1",
                    reason="set WFS_PERF=1 to run the 100k benchmark")
def test_import_100k_messages_under_60_seconds(conn, case, tmp_path):
    elapsed = _run_import(conn, case, 100_000, tmp_path)
    count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert count == 100_000
    print(f"\n100k messages imported in {elapsed:.2f}s")
    assert elapsed < 60, f"100k import took {elapsed:.1f}s"


def test_conversation_browsing_is_paginated(conn, case, tmp_path):
    _run_import(conn, case, 5_000, tmp_path)
    conv = conn.execute("SELECT id FROM conversations LIMIT 1").fetchone()["id"]
    started = time.perf_counter()
    rows = conn.execute(
        "SELECT id FROM messages WHERE conversation_id=? ORDER BY sent_at_utc LIMIT 200",
        (conv,)).fetchall()
    assert len(rows) == 200
    assert (time.perf_counter() - started) < 1.0


def test_indexed_search_is_fast_at_scale(conn, case, tmp_path):
    from wfs_engine.search import SearchQuery, search

    _run_import(conn, case, 20_000, tmp_path)
    started = time.perf_counter()
    result = search(conn, case["id"], SearchQuery(q="budget", mode="fts", limit=50))
    elapsed = time.perf_counter() - started
    assert result["total"] > 0
    assert elapsed < 2.0, f"search took {elapsed:.2f}s"
