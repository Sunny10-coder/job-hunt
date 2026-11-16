import json
from pathlib import Path

import pytest

from wfs_engine import reporting


@pytest.mark.parametrize("fmt", ["html", "pdf", "xlsx", "json", "csv"])
def test_every_format_generates_a_real_file(conn, sample_case, fmt):
    result = reporting.generate(conn, sample_case["id"], "case", fmt)
    path = Path(result["path"])
    assert path.is_file()
    assert path.stat().st_size > 0
    assert result["sha256"]
    assert len(result["sha256"]) == 64
    assert path.suffix == f".{fmt}"


def test_pdf_has_pdf_signature(conn, sample_case):
    result = reporting.generate(conn, sample_case["id"], "case", "pdf")
    head = Path(result["path"]).read_bytes()[:5]
    assert head == b"%PDF-"


def test_html_contains_case_metadata_and_disclaimer(conn, sample_case):
    result = reporting.generate(conn, sample_case["id"], "case", "html")
    html = Path(result["path"]).read_text(encoding="utf-8")
    assert sample_case["name"] in html
    assert "not an independent forensic certification" in html
    assert "<svg" in html  # charts are embedded


def test_xlsx_has_expected_sheets(conn, sample_case):
    from openpyxl import load_workbook

    result = reporting.generate(conn, sample_case["id"], "case", "xlsx")
    workbook = load_workbook(result["path"])
    names = set(workbook.sheetnames)
    assert "Summary" in names
    assert "Evidence" in names
    assert len(names) > 2


def test_json_report_matches_database_counts(conn, sample_case):
    result = reporting.generate(conn, sample_case["id"], "case", "json")
    payload = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    kpis = {b["label"]: b["value"] for b in payload["blocks"] if b["type"] == "kpi"}
    db_messages = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE case_id=? AND is_system=0",
        (sample_case["id"],)).fetchone()[0]
    assert kpis["Messages"] == db_messages
    assert payload["evidence"][0]["sha256"]


def test_report_records_are_listed(conn, sample_case):
    reporting.generate(conn, sample_case["id"], "conversation", "pdf",
                       {"include_messages": False})
    listed = reporting.list_reports(conn, sample_case["id"])
    assert listed
    assert listed[0]["format"] == "pdf"


def test_message_export_csv_and_json(conn, sample_case):
    from wfs_engine.reporting import export_messages

    csv_result = export_messages(conn, sample_case["id"], fmt="csv")
    assert Path(csv_result["path"]).read_text(encoding="utf-8-sig").splitlines()[:1]
    json_result = export_messages(conn, sample_case["id"], fmt="json")
    rows = json.loads(Path(json_result["path"]).read_text(encoding="utf-8"))
    assert rows and "sent_at_utc" in rows[0]


def test_report_rejects_unknown_format(conn, sample_case):
    with pytest.raises(ValueError):
        reporting.generate(conn, sample_case["id"], "case", "docx")
