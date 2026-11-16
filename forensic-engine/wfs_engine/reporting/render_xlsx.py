"""XLSX report rendering with openpyxl."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ..safety import spreadsheet_safe

HEADER_FILL = PatternFill("solid", fgColor="0F172A")
HEADER_FONT = Font(color="E6EDF5", bold=True, size=10)
BODY_FONT = Font(size=10)


def render(report: dict[str, Any], path: Path) -> Path:
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    rows: list[tuple[str, Any]] = [
        ("Report", report["title"]),
        ("Case", report["case"]["name"]),
        ("Case number", f"CASE-{report['case']['case_number']:04d}"),
        ("Case id", report["case"]["id"]),
        ("Generated (UTC)", report["generated_at"]),
        ("Examiner", report["case"]["examiner"]),
        ("Engine", report["engine_version"]),
        ("Scope", "; ".join(report["scope"]) or "whole case"),
        ("Disclaimer", report["disclaimer"]),
    ]
    for block in report["blocks"]:
        if block["type"] == "kpi":
            rows.append((block["label"], block["value"]))
    _write_rows(summary, ["Field", "Value"], rows, widths=[28, 100])

    for block in report["blocks"]:
        if block["type"] != "table":
            continue
        sheet = wb.create_sheet(_sheet_name(block["title"]))
        _write_rows(sheet, block["columns"], block["rows"], widths=None)
        if block.get("note"):
            sheet.cell(row=sheet.max_row + 2, column=1, value=block["note"]).font = Font(
                italic=True, size=9, color="5B6B7F")

    evidence = wb.create_sheet("Evidence")
    _write_rows(evidence, ["File", "Type", "Bytes", "SHA-256", "Imported", "Messages"],
                [[e["original_name"], e["source_type"], e["size_bytes"], e["sha256"],
                  e["imported_at"], e["message_count"]] for e in report["evidence"]],
                widths=[40, 18, 12, 70, 22, 12])
    wb.save(path)
    return path


def _sheet_name(title: str) -> str:
    cleaned = "".join(ch for ch in title if ch not in "[]:*?/\\")[:28]
    return cleaned or "Sheet"


def _write_rows(sheet, columns: list[str], rows: list[list[Any]],
                widths: list[int] | None) -> None:
    sheet.append(list(columns))
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    for row in rows:
        sheet.append([_clean(cell) for cell in row])
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.font = BODY_FONT
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    if widths:
        for idx, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(idx)].width = width
    else:
        for idx in range(1, len(columns) + 1):
            longest = max([len(str(columns[idx - 1]))]
                          + [len(str(r[idx - 1])) for r in rows[:200] if idx - 1 < len(r)]
                          or [10])
            sheet.column_dimensions[get_column_letter(idx)].width = min(60, longest + 2)
    sheet.freeze_panes = "A2"


def _clean(value: Any) -> Any:
    if isinstance(value, (int, float)) or value is None:
        return value
    # Imported chat text must never be evaluated as a spreadsheet formula.
    return spreadsheet_safe(value) if isinstance(value, str) else str(value)
