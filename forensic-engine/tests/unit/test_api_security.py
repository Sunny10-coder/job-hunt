"""Origin validation and authenticated health probe.

The Rust shell health-checks `/api/health` with the session bearer token, so the
engine must both (a) require that token on every route and (b) never reflect an
attacker-controlled Origin back in CORS headers.
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

from wfs_engine.api.server import EngineServer, Handler


@pytest.mark.parametrize("origin", [
    "http://localhost:1420",
    "http://localhost:3000",
    "http://127.0.0.1:8765",
    "https://localhost",
    "tauri://localhost",
    "https://tauri.localhost",
])
def test_desktop_and_loopback_origins_are_allowed(origin):
    assert Handler._origin_allowed(origin)


@pytest.mark.parametrize("origin", [
    "http://localhost.evil.com",
    "http://127.0.0.1.attacker.net",
    "http://localhost@evil.com",
    "https://evil.com",
    "http://localhost:3000.evil.com",
    "null",
    "",
])
def test_spoofed_origins_are_rejected(origin):
    assert not Handler._origin_allowed(origin)


@pytest.fixture()
def authed_server(data_dir):
    srv = EngineServer("127.0.0.1", 0, token="session-token")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.port}"
    srv.shutdown()


def _get(url, headers=None):
    request = urllib.request.Request(url)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), json.loads(exc.read() or b"{}")


def test_health_requires_the_session_token(authed_server):
    status, _, _ = _get(f"{authed_server}/api/health")
    assert status == 401
    status, _, payload = _get(f"{authed_server}/api/health",
                              {"Authorization": "Bearer session-token"})
    assert status == 200 and payload["ok"] is True


def test_wrong_token_is_rejected(authed_server):
    status, _, _ = _get(f"{authed_server}/api/health",
                        {"Authorization": "Bearer not-the-token"})
    assert status == 401


def test_spoofed_origin_is_not_echoed_in_cors_headers(authed_server):
    _, headers, _ = _get(f"{authed_server}/api/health",
                         {"Authorization": "Bearer session-token",
                          "Origin": "http://localhost.evil.com"})
    assert "Access-Control-Allow-Origin" not in headers


def test_loopback_origin_is_echoed(authed_server):
    _, headers, _ = _get(f"{authed_server}/api/health",
                         {"Authorization": "Bearer session-token",
                          "Origin": "http://localhost:1420"})
    assert headers.get("Access-Control-Allow-Origin") == "http://localhost:1420"
