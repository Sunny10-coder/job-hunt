import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from wfs_engine.api.server import EngineServer


def request(base, method, path, body=None, token=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read()
            return resp.status, (payload if raw else json.loads(payload))
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload)
        except ValueError:
            return exc.code, {"raw": payload}


@pytest.fixture()
def server(data_dir):
    srv = EngineServer("127.0.0.1", 0, token=None)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{srv.port}"
    yield base
    srv.shutdown()


@pytest.fixture()
def authed_server(data_dir):
    srv = EngineServer("127.0.0.1", 0, token="secret-token")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.port}"
    srv.shutdown()


def wait_for_job(base, job_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, job = request(base, "GET", f"/api/jobs/{job_id}")
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.2)
    raise AssertionError("import job did not finish in time")


def test_health_and_diagnostics(server):
    status, health = request(server, "GET", "/api/health")
    assert status == 200 and health["ok"] is True
    _, diag = request(server, "GET", "/api/diagnostics")
    assert diag["fts5"] is True
    assert "data_dir" in diag
    # Diagnostics must not leak message content.
    assert "messages_body" not in json.dumps(diag)


def test_case_lifecycle_over_http(server):
    status, error = request(server, "POST", "/api/cases", {"name": "No ack"})
    assert status == 400
    assert "authorisation" in error["error"]

    status, case = request(server, "POST", "/api/cases", {
        "name": "API case", "examiner": "tester",
        "authorization_acknowledged": True})
    assert status == 200
    case_id = case["id"]

    _, listed = request(server, "GET", "/api/cases")
    assert any(c["id"] == case_id for c in listed)

    status, patched = request(server, "PATCH", f"/api/cases/{case_id}",
                              {"description": "updated"})
    assert patched["description"] == "updated"

    _, archived = request(server, "POST", f"/api/cases/{case_id}/archive")
    assert archived["status"] == "archived"

    _, manifest = request(server, "GET", f"/api/cases/{case_id}/manifest")
    assert manifest["schema"] == "wfs.manifest/1"


def test_sample_import_and_dashboard(server):
    _, case = request(server, "POST", "/api/cases",
                      {"name": "Flow", "authorization_acknowledged": True})
    case_id = case["id"]
    _, started = request(server, "POST", f"/api/cases/{case_id}/import-sample", {})
    job = wait_for_job(server, started["job_id"])
    assert job["status"] == "done"
    assert job["progress"] == 1.0

    _, dashboard = request(server, "GET", f"/api/cases/{case_id}/dashboard")
    assert dashboard["overview"]["real_messages"] > 0
    assert dashboard["conversations"]
    assert dashboard["evidence"]

    _, convs = request(server, "GET", f"/api/cases/{case_id}/conversations")
    conv_id = convs[0]["id"]
    _, messages = request(
        server, "GET", f"/api/cases/{case_id}/conversations/{conv_id}/messages?limit=10")
    assert messages["messages"]
    first = messages["messages"][0]
    _, detail = request(server, "GET", f"/api/cases/{case_id}/messages/{first['id']}")
    assert detail["source_ref"]

    _, timeline = request(server, "GET", f"/api/cases/{case_id}/timeline?limit=50")
    assert timeline["events"]

    _, analytics = request(server, "GET", f"/api/cases/{case_id}/analytics")
    assert analytics["overview"]["messages"] > 0
    assert len(analytics["heatmap"]["grid"]) == 7

    _, result = request(server, "POST", f"/api/cases/{case_id}/search",
                        {"q": "hotel", "mode": "fts"})
    assert result["total"] >= 1

    _, recovery_result = request(server, "POST",
                                 f"/api/cases/{case_id}/recovery/analyze")
    assert recovery_result["findings"]

    _, report = request(server, "POST", f"/api/cases/{case_id}/reports",
                        {"type": "case", "format": "html"})
    assert report["sha256"]
    status, body = request(server, "GET", f"/api/reports/{report['id']}/download",
                           raw=True)
    assert status == 200 and b"<html" in body.lower()


def test_bookmarks_notes_and_tags(server):
    _, case = request(server, "POST", "/api/cases",
                      {"name": "Annotations", "authorization_acknowledged": True})
    case_id = case["id"]
    _, started = request(server, "POST", f"/api/cases/{case_id}/import-sample", {})
    wait_for_job(server, started["job_id"])
    _, convs = request(server, "GET", f"/api/cases/{case_id}/conversations")
    _, messages = request(
        server, "GET",
        f"/api/cases/{case_id}/conversations/{convs[0]['id']}/messages?limit=1")
    message_id = messages["messages"][0]["id"]

    status, bookmark = request(server, "POST", f"/api/cases/{case_id}/bookmarks",
                               {"message_id": message_id, "label": "important"})
    assert status == 200 and bookmark["label"] == "important"
    _, bookmarks = request(server, "GET", f"/api/cases/{case_id}/bookmarks")
    assert any(b["message_id"] == message_id for b in bookmarks)

    request(server, "POST", f"/api/cases/{case_id}/tags",
            {"message_id": message_id, "tag": "travel"})
    _, tags = request(server, "GET", f"/api/cases/{case_id}/tags")
    assert any(t["tag"] == "travel" for t in tags)

    request(server, "POST", f"/api/cases/{case_id}/notes",
            {"body": "note text", "message_id": message_id})
    _, notes = request(server, "GET", f"/api/cases/{case_id}/notes")
    assert notes[0]["body"] == "note text"


def test_token_authentication_is_enforced(authed_server):
    status, _ = request(authed_server, "GET", "/api/cases")
    assert status == 401
    status, _ = request(authed_server, "GET", "/api/cases", token="wrong")
    assert status == 401
    status, _ = request(authed_server, "GET", "/api/cases", token="secret-token")
    assert status == 200


def test_media_serving_is_confined_to_case_storage(server):
    _, case = request(server, "POST", "/api/cases",
                      {"name": "Media", "authorization_acknowledged": True})
    case_id = case["id"]
    status, _ = request(server, "GET",
                        f"/api/cases/{case_id}/media/../../../../etc/passwd/file")
    assert status in (400, 404, 500)


def test_unknown_routes_and_bad_payloads(server):
    status, payload = request(server, "GET", "/api/nope")
    assert status == 404
    status, payload = request(server, "POST", "/api/cases", {"name": ""})
    assert status == 400
    status, payload = request(server, "GET", "/api/jobs/does-not-exist")
    assert status == 404


def test_ai_status_degrades_without_a_model(server):
    status, ai = request(server, "GET", "/api/ai/status")
    assert status == 200
    assert "provider" in ai
    if not ai.get("ok"):
        assert ai.get("hint")


def test_ai_answer_without_model_still_returns_evidence(server):
    _, case = request(server, "POST", "/api/cases",
                      {"name": "AI", "authorization_acknowledged": True})
    case_id = case["id"]
    _, started = request(server, "POST", f"/api/cases/{case_id}/import-sample", {})
    wait_for_job(server, started["job_id"])
    status, answer = request(server, "POST", f"/api/cases/{case_id}/ai/ask",
                             {"question": "What did they discuss about the trip?"})
    assert status == 200
    assert answer["citations"] or answer["observed"]["retrieved"] >= 0
    assert answer["disclosure"]
