from wfs_engine.analytics import (anomalies, metrics, network, sentiment)


def test_overview_matches_database(sample_case, conn):
    case_id = sample_case["id"]
    overview = metrics.overview(conn, case_id)
    total = conn.execute("SELECT COUNT(*) FROM messages WHERE case_id=?",
                         (case_id,)).fetchone()[0]
    assert overview["messages"] == total
    real = conn.execute("SELECT COUNT(*) FROM messages WHERE case_id=? AND is_system=0",
                        (case_id,)).fetchone()[0]
    assert overview["real_messages"] == real
    assert overview["incoming"] + overview["outgoing"] == real
    assert overview["first_at"] <= overview["last_at"]


def test_activity_series_and_heatmap_shape(sample_case, conn):
    case_id = sample_case["id"]
    daily = metrics.activity_series(conn, case_id, "day")
    assert daily["series"]
    assert all("bucket" in row and "count" in row for row in daily["series"])
    heat = metrics.heatmap(conn, case_id)
    assert len(heat["grid"]) == 7
    assert all(len(row) == 24 for row in heat["grid"])
    assert sum(sum(row) for row in heat["grid"]) > 0


def test_response_times_exclude_long_gaps(sample_case, conn):
    result = metrics.response_times(conn, sample_case["id"])
    assert result["samples"] > 0
    assert result["excluded_session_breaks"] > 0
    assert result["median_minutes"] is not None
    assert sum(b["count"] for b in result["histogram"]) == result["samples"]
    assert result["methodology"]["session_gap_minutes"] == 60


def test_response_times_exclude_group_chats_by_default(conn, sample_case):
    group = conn.execute(
        "SELECT id FROM conversations WHERE kind='group' LIMIT 1").fetchone()["id"]
    excluded = metrics.response_times(conn, sample_case["id"])
    included = metrics.response_times(conn, sample_case["id"],
                                      conversation_id=group, exclude_groups=False)
    assert included["methodology"]["group_chats"].startswith("included")
    assert excluded["samples"] >= included["samples"]


def test_word_and_emoji_frequency_ignore_placeholders(sample_case, conn):
    words = metrics.word_frequency(conn, sample_case["id"])
    assert words["words"]
    assert all(w["word"] != "omitted" for w in words["words"])
    emojis = metrics.emoji_frequency(conn, sample_case["id"])
    assert emojis["total"] > 0


def test_contact_profile_and_comparison(sample_case, conn):
    contacts = metrics.contacts(conn, sample_case["id"])
    assert contacts
    profile = metrics.contact_profile(conn, sample_case["id"], contacts[0]["id"])
    assert profile["messages"] > 0
    assert len(profile["hourly"]) == 24
    comparison = metrics.compare_contacts(
        conn, sample_case["id"], [c["id"] for c in contacts[:2]])
    assert len(comparison["profiles"]) == 2
    assert "not a psychological comparison" in comparison["note"]


def test_group_analysis(sample_case, conn):
    group = conn.execute(
        "SELECT id FROM conversations WHERE kind='group' LIMIT 1").fetchone()
    result = metrics.group_analysis(conn, sample_case["id"], group["id"])
    assert result["participants"]
    assert 0 <= result["participation_balance"]["gini"] <= 1
    assert result["events"]
    assert abs(sum(p["share"] for p in result["participants"]) - 100) < 0.5


def test_network_edges_distinguish_observed_and_inferred(sample_case, conn):
    graph = network.build(conn, sample_case["id"])
    assert graph["nodes"]
    assert graph["edges"]
    kinds = {e["kind"] for e in graph["edges"]}
    assert "membership" in kinds
    for edge in graph["edges"]:
        assert edge["inferred"] is (edge["kind"] == "topic")


def test_anomaly_detection_requires_baseline(sample_case, conn):
    result = anomalies.detect(conn, sample_case["id"])
    assert "method" in result
    for finding in result["findings"]:
        assert {"kind", "observed", "baseline_median", "deviation"} <= set(finding)
        assert finding["explanation"]


def test_sentiment_is_labelled_as_estimate(sample_case, conn):
    result = sentiment.analyze(conn, sample_case["id"])
    assert result["scanned_messages"] > 0
    assert "not a measurement" in result["disclaimer"]
    assert set(result["counts"]) == {"positive", "negative", "neutral"}


def test_sessions_are_bounded_by_gap(sample_case, conn):
    result = metrics.sessions(conn, sample_case["id"], gap_minutes=60)
    assert result["total_sessions"] > 0
    assert all(s["messages"] > 0 for s in result["sessions"])


def test_interpretive_analysis_can_be_disabled(conn, sample_case):
    from wfs_engine import db

    db.set_settings(conn, {"interpretive_analysis": False})
    assert db.get_settings(conn)["interpretive_analysis"] is False
