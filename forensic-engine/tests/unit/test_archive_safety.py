import zipfile
from pathlib import Path

import pytest

from wfs_engine.parsers import archive, detect


def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def test_archive_rejects_path_traversal(tmp_path):
    target = make_zip(tmp_path / "evil.zip", {"../../escape.txt": b"x"})
    ok, problems = archive.inspect_archive(target)
    assert ok is False
    assert any("traversal" in p for p in problems)


def test_archive_rejects_absolute_paths(tmp_path):
    target = make_zip(tmp_path / "abs.zip", {"/etc/passwd": b"x"})
    ok, problems = archive.inspect_archive(target)
    assert ok is False


def test_archive_extracts_and_flattens_names(tmp_path):
    target = make_zip(tmp_path / "ok.zip", {
        "folder/WhatsApp Chat.txt": b"01/05/24, 10:00 - A: hi",
        "folder/media.png": b"\x89PNG\r\n\x1a\n",
    })
    report = archive.extract(target, tmp_path / "out")
    assert len(report.files) == 2
    names = {f.path.name for f in report.files}
    assert "WhatsApp Chat.txt" in names
    assert all(f.path.parent == (tmp_path / "out") for f in report.files)


def test_corrupt_zip_is_reported_not_raised_at_sniff(tmp_path):
    bad = tmp_path / "broken.zip"
    bad.write_bytes(b"PK\x03\x04garbage")
    result = detect.sniff(bad)
    assert result.source_type in {"unknown", "document"}


def test_sniff_detects_signatures(tmp_path):
    txt = tmp_path / "chat.txt"
    txt.write_text("01/05/24, 10:00 - A: hi")
    assert detect.sniff(txt).source_type == "whatsapp_txt"

    png = tmp_path / "a.png"
    png.write_bytes(bytes.fromhex("89504e470d0a1a0a"))
    assert detect.sniff(png).source_type == "image"

    sqlite = tmp_path / "msgstore.db"
    sqlite.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    assert detect.sniff(sqlite).source_type == "sqlite"


def test_oversized_file_is_rejected_before_copy(tmp_path, monkeypatch):
    from wfs_engine import config

    monkeypatch.setattr(config, "MAX_FILE_BYTES", 10)
    big = tmp_path / "big.txt"
    big.write_text("x" * 100)
    assert detect.sniff(big).source_type == "unknown"
