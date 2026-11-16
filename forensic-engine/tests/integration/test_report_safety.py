"""Report and export products must not collide or carry live formulas."""

from pathlib import Path

from openpyxl import load_workbook

from wfs_engine import importer, reporting

PAYLOAD = "12/10/2024, 10:05 - Mallory: =SUM(1+1)"


def _import_payload(conn, case_id, tmp_path):
    source = tmp_path / "chat-with-mallory.txt"
    source.write_text(PAYLOAD + "\n", encoding="utf-8")
    job = importer.create_job(conn, case_id, [str(source)], importer.ImportOptions())
    importer.run_job(job["job_id"])


def test_two_reports_in_the_same_second_both_survive(conn, sample_case):
    first = reporting.generate(conn, sample_case["id"], "case", "json")
    second = reporting.generate(conn, sample_case["id"], "case", "json")
    assert first["path"] != second["path"]
    assert Path(first["path"]).is_file()
    assert Path(second["path"]).is_file()
    assert Path(first["path"]).read_text(encoding="utf-8")


def test_two_message_exports_do_not_overwrite(conn, sample_case):
    first = reporting.export_messages(conn, sample_case["id"], fmt="csv")
    second = reporting.export_messages(conn, sample_case["id"], fmt="csv")
    assert first["path"] != second["path"]
    assert Path(first["path"]).is_file() and Path(second["path"]).is_file()


def test_xlsx_cells_never_start_a_formula(conn, sample_case):
    from wfs_engine.reporting.render_xlsx import _clean

    assert _clean("=SUM(1+1)") == "'=SUM(1+1)"
    assert _clean("+1") == "'+1"
    assert _clean("plain text") == "plain text"

    result = reporting.generate(conn, sample_case["id"], "case", "xlsx")
    workbook = load_workbook(result["path"])
    values = [cell.value for sheet in workbook.worksheets
              for row in sheet.iter_rows() for cell in row if cell.value]
    assert not any(isinstance(value, str) and value.startswith(("=", "+", "@"))
                   for value in values)


def test_csv_export_neutralises_formulas(conn, case, tmp_path):
    _import_payload(conn, case["id"], tmp_path)
    result = reporting.export_messages(conn, case["id"], fmt="csv")
    text = Path(result["path"]).read_text(encoding="utf-8-sig")
    assert "'=SUM(1+1)" in text
    assert "\n=SUM(1+1)" not in text
