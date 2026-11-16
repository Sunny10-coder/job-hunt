import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """Isolated application data directory for every test."""
    target = tmp_path / "data"
    monkeypatch.setenv("WFS_DATA_DIR", str(target))
    from wfs_engine import config, db

    config.ensure_dirs()
    db.migrate()
    yield target


@pytest.fixture()
def conn(data_dir):
    from wfs_engine import db

    with db.session() as connection:
        yield connection


@pytest.fixture()
def case(conn):
    from wfs_engine import cases

    return cases.create_case(conn, "Test case", "unit test case", "tester",
                             "Authorised test evidence")


@pytest.fixture()
def sample_case(conn, case):
    """Case populated with the synthetic multilingual dataset."""
    from wfs_engine import importer, samples

    target = Path(os.environ["WFS_DATA_DIR"]) / "sample-data"
    info = samples.write_sample_files(target)
    job = importer.create_job(conn, case["id"], info["files"], importer.ImportOptions())
    importer.run_job(job["job_id"])
    return case


# --------------------------------------------------------------------------- #
# Offline OpenAI-compatible stub
#
# The AI tests never touch a network or a model. This loopback server records
# exactly what the provider layer would have sent, so tests can assert on the
# prompt as well as on the parsed answer.
# --------------------------------------------------------------------------- #
class StubAiState:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.headers: list[dict] = []
        self.lock = threading.Lock()


def _stub_handler(state: StubAiState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep pytest output clean
            pass

        def _send(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
            with state.lock:
                state.headers.append(dict(self.headers))
            if self.path.rstrip("/").endswith("/models"):
                self._send({"object": "list", "data": [{"id": "stub-model"}]})
            else:
                self._send({"error": "not found"}, 404)

        def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(raw or "{}")
            with state.lock:
                state.requests.append(payload)
                state.headers.append(dict(self.headers))

            user = next((m.get("content", "") for m in payload.get("messages", [])
                         if m.get("role") == "user"), "")
            markers = re.findall(r"^\[M(\d+)\]", user, flags=re.MULTILINE)
            cited = ["M1"]
            if markers and markers[-1] != "1":
                cited.append(f"M{markers[-1]}")

            content = " ".join(f"The excerpts confirm the plan [{m}]." for m in cited)
            first = next((line for line in user.splitlines() if line.startswith("[M1]")), "")
            # Echo the first excerpt verbatim so tests can prove script text
            # survives the round trip without reordering.
            quote = first.rsplit(" | ", 1)[-1][:120] if first else ""
            if quote:
                content += f' Quoted evidence: "{quote}".'
            content += " An unsupported claim follows [M99]."

            self._send({
                "id": "chatcmpl-stub",
                "object": "chat.completion",
                "model": payload.get("model"),
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 128, "completion_tokens": 24,
                          "total_tokens": 152},
            })

    return Handler


@pytest.fixture()
def stub_endpoint(monkeypatch):
    """Loopback OpenAI-compatible endpoint; yields (state, base_url)."""
    state = StubAiState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _stub_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Tests inject the key through the environment; production code receives it
    # from the OS credential store through the Rust shell.
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-secret")
    try:
        yield state, f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture()
def ai_stub(conn, stub_endpoint):
    """Stub endpoint plus settings that point the engine at it."""
    from wfs_engine import db as _db

    state, base_url = stub_endpoint
    _db.set_settings(conn, {
        "ai_enabled": True,
        "ai_provider": "openai-compatible",
        "ai_external_enabled": True,
        "ai_external_base_url": base_url,
        "ai_model": "stub-model",
        "ai_temperature": 0,
    })
    return state, base_url
