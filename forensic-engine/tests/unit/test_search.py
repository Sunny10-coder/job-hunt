import pytest

from wfs_engine import search
from wfs_engine.search import SearchQuery, build_fts_expression


def run(conn, case_id, **kwargs):
    return search.search(conn, case_id, SearchQuery(**kwargs))


def test_full_text_search_finds_message(sample_case, conn):
    result = run(conn, sample_case["id"], q="hotel")
    assert result["total"] >= 1
    assert any("hotel" in r["body"].lower() for r in result["results"])


def test_search_is_scoped_to_the_case(sample_case, conn):
    from wfs_engine import cases

    other = cases.create_case(conn, "Empty case")
    result = run(conn, other["id"], q="hotel")
    assert result["total"] == 0


def test_phrase_and_boolean_queries(sample_case, conn):
    assert run(conn, sample_case["id"], q='"boat tour"')["total"] >= 1
    assert run(conn, sample_case["id"], q="boat AND tour")["total"] >= 1
    assert run(conn, sample_case["id"], q="hotel OR station")["total"] >= 1


def test_prefix_query(sample_case, conn):
    assert run(conn, sample_case["id"], q="tick*")["total"] >= 1


def test_hostile_query_syntax_is_neutralised(sample_case, conn):
    for hostile in ['"unclosed', "AND", "OR OR", "NEAR(", "body:", "*", "'"]:
        result = run(conn, sample_case["id"], q=hostile)
        assert isinstance(result["total"], int)


def test_filters_by_sender_and_date(sample_case, conn):
    contacts = {r["display_name"]: r["id"] for r in conn.execute(
        "SELECT id, display_name FROM contacts")}
    result = run(conn, sample_case["id"], q="", sender_ids=[contacts["Priya"]])
    assert result["total"] > 0
    assert all(r["sender_raw"] == "Priya" for r in result["results"])

    dated = run(conn, sample_case["id"], q="", date_from="2024-02-01")
    assert all(r["sent_at_utc"] >= "2024-02-01" for r in dated["results"])


def test_delete_and_media_filters(sample_case, conn):
    deleted = run(conn, sample_case["id"], q="", is_deleted=True)
    assert deleted["total"] >= 1
    media = run(conn, sample_case["id"], q="", media_type="any")
    assert media["total"] >= 1


def test_exact_mode_treats_percent_literally(sample_case, conn):
    result = run(conn, sample_case["id"], q="100%", mode="exact")
    assert result["total"] == 0


def test_regex_mode_is_bounded(sample_case, conn):
    result = run(conn, sample_case["id"], q=r"hotel\s+near", mode="regex")
    assert result["total"] >= 1
    with pytest.raises(ValueError):
        run(conn, sample_case["id"], q="([unclosed", mode="regex")
    with pytest.raises(ValueError):
        run(conn, sample_case["id"], q="a" * 400, mode="regex")


def test_snippet_markers_are_present(sample_case, conn):
    result = run(conn, sample_case["id"], q="hotel")
    assert any("\u0002" in r["snippet"] for r in result["results"])


def test_saved_searches_roundtrip(sample_case, conn):
    saved = search.save_search(conn, sample_case["id"], "hotel search",
                               {"q": "hotel", "mode": "fts"})
    listed = search.list_saved(conn, sample_case["id"])
    assert any(s["name"] == "hotel search" for s in listed)
    search.delete_saved(conn, sample_case["id"], saved["id"])
    assert not search.list_saved(conn, sample_case["id"])


def test_fts_expression_quoting():
    expression = build_fts_expression('hotel "boat tour" AND station*')
    assert '"hotel"' in expression
    assert '"boat tour"' in expression
    assert "AND" in expression
    assert '"station"*' in expression
