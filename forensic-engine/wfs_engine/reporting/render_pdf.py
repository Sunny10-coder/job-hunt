"""PDF report rendering with ReportLab.

Fonts are resolved from the operating system at runtime; when no Unicode-capable
font is found the renderer states that limitation in the document instead of
silently dropping non-Latin text.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

FONT_CANDIDATES = [
    # Windows
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    # Linux
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    # macOS
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]

BODY_FONT = "Helvetica"
BOLD_FONT = "Helvetica-Bold"
UNICODE_OK = False


def _register_fonts() -> None:
    global BODY_FONT, BOLD_FONT, UNICODE_OK
    if pdfmetrics.getRegisteredFontNames().__contains__("WFSBody"):
        BODY_FONT, BOLD_FONT, UNICODE_OK = "WFSBody", "WFSBody-Bold", True
        return
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).is_file():
            try:
                pdfmetrics.registerFont(TTFont("WFSBody", regular))
                if Path(bold).is_file():
                    pdfmetrics.registerFont(TTFont("WFSBody-Bold", bold))
                    BOLD_FONT = "WFSBody-Bold"
                else:
                    BOLD_FONT = "WFSBody"
                BODY_FONT, UNICODE_OK = "WFSBody", True
                return
            except Exception:  # noqa: BLE001
                continue
    UNICODE_OK = False


_register_fonts()

CYAN = colors.HexColor("#0e7490")
SLATE = colors.HexColor("#475569")
LINE = colors.HexColor("#d8e0ea")


def render(report: dict[str, Any], path: Path) -> Path:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName=BODY_FONT,
                          fontSize=9.2, leading=13, textColor=colors.HexColor("#111827"))
    small = ParagraphStyle("small", parent=body, fontSize=7.6, leading=10,
                           textColor=SLATE)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName=BOLD_FONT,
                        fontSize=20, textColor=colors.HexColor("#0f172a"), spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=BOLD_FONT,
                        fontSize=12.5, textColor=CYAN, spaceBefore=14, spaceAfter=6)
    kpi_style = ParagraphStyle("kpi", parent=body, fontSize=16, textColor=CYAN,
                               alignment=1, fontName=BOLD_FONT)

    story: list[Any] = []
    case = report["case"]
    story.append(Paragraph("WhatsApp Forensic Studio AI", small))
    story.append(Paragraph(escape(report["title"]), h1))
    meta_rows = [
        ["Case", case["name"]],
        ["Case number", f"CASE-{case['case_number']:04d}"],
        ["Case id", case["id"]],
        ["Generated (UTC)", report["generated_at"]],
        ["Examiner", case["examiner"] or "not recorded"],
        ["Engine", report["engine_version"]],
        ["Evidence items", str(len(report["evidence"]))],
        ["Scope", "; ".join(report["scope"]) or "whole case"],
    ]
    meta_table = Table([[Paragraph(f"<b>{escape(a)}</b>", small), Paragraph(escape(b), small)]
                        for a, b in meta_rows], colWidths=[32 * mm, 130 * mm])
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, LINE),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6))

    kpis = [b for b in report["blocks"] if b["type"] == "kpi"]
    if kpis:
        cells = [[Paragraph(str(b["value"]), kpi_style)] for b in kpis[:6]]
        labels = [[Paragraph(escape(b["label"]), small)] for b in kpis[:6]]
        grid = [cells, labels]
        attempts = min(len(kpis), 6)
        table = Table(grid, colWidths=[(162 / attempts) * mm] * attempts)
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.4, LINE),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(KeepTogether([table]))
        story.append(Spacer(1, 4))

    needs_unicode_note = False

    def safe(text: Any) -> str:
        nonlocal needs_unicode_note
        value = str(text)
        if not UNICODE_OK and any(ord(ch) > 0x2FF for ch in value):
            needs_unicode_note = True
        return escape(value)[:4000]

    for block in report["blocks"]:
        kind = block["type"]
        if kind == "kpi":
            continue
        if kind == "text":
            story.append(Paragraph(escape(block["title"]), h2))
            for line in str(block["body"]).split("\n"):
                story.append(Paragraph(safe(line) or "&nbsp;", body))
        elif kind == "table":
            story.append(Paragraph(escape(block["title"]), h2))
            header = [Paragraph(f"<b>{escape(str(c))}</b>", small) for c in block["columns"]]
            rows = [[Paragraph(safe(cell), small) for cell in row]
                    for row in block["rows"][:180]]
            data = [header] + rows if rows else [header,
                                                [Paragraph("No rows", small)]
                                                + ["" for _ in block["columns"][1:]]]
            width = 162 * mm / max(1, len(block["columns"]))
            table = Table(data, colWidths=[width] * len(block["columns"]),
                          repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(table)
            if block.get("note"):
                story.append(Paragraph(safe(block["note"]), small))
        elif kind == "chart":
            story.append(Paragraph(escape(block["title"]), h2))
            if block["chart"] == "heatmap":
                story.append(_heatmap_drawing(block["grid"]))
            else:
                values = block["series"][0]["values"][:48]
                labels = block["labels"][:48]
                story.append(_bar_drawing(labels, values))
            if block.get("note"):
                story.append(Paragraph(safe(block["note"]), small))

    story.append(Paragraph("Evidence sources and hashes", h2))
    ev_header = [Paragraph(f"<b>{escape(h)}</b>", small)
                 for h in ("File", "Type", "Bytes", "SHA-256", "Messages")]
    ev_rows = []
    for e in report["evidence"]:
        ev_rows.append([
            Paragraph(safe(e["original_name"]), small),
            Paragraph(safe(e["source_type"]), small),
            Paragraph(f"{e['size_bytes']:,}", small),
            Paragraph(f"<font size=6>{escape(e['sha256'])}</font>", small),
            Paragraph(str(e["message_count"]), small),
        ])
    ev_table = Table([ev_header] + ev_rows if ev_rows else [ev_header],
                     colWidths=[42 * mm, 26 * mm, 20 * mm, 62 * mm, 12 * mm],
                     repeatRows=1)
    ev_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(ev_table)

    story.append(Spacer(1, 10))
    disclaimer = report["disclaimer"]
    if needs_unicode_note:
        disclaimer += (" Some scripts could not be rendered with an available PDF font; "
                       "use the HTML report for full multilingual fidelity.")
    box = Table([[Paragraph(escape(disclaimer), small)]], colWidths=[162 * mm])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, CYAN),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fbfd")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(box)

    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            leftMargin=22 * mm, rightMargin=22 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=report["title"], author="WhatsApp Forensic Studio AI",
                            subject=f"Case {case['name']}")
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(BODY_FONT, 7)
    canvas.setFillColor(SLATE)
    canvas.drawString(22 * mm, 10 * mm,
                      "WhatsApp Forensic Studio AI - analytical work product, "
                      "not a forensic certification")
    canvas.drawRightString(A4[0] - 22 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _bar_drawing(labels: list[str], values: list[float],
                 width: float = 470, height: float = 120) -> Drawing:
    drawing = Drawing(width, height)
    if not values:
        drawing.add(String(10, height / 2, "No data", fontSize=8, fillColor=SLATE))
        return drawing
    maximum = max(values) or 1
    step = width / max(1, len(values))
    for idx, value in enumerate(values):
        h = (value / maximum) * (height - 20)
        drawing.add(Rect(idx * step + 1, 14, max(step - 3, 0.8), h,
                         fillColor=colors.HexColor("#22d3ee"), strokeColor=None))
    drawing.add(String(2, 2, f"{labels[0] if labels else ''} → max {maximum:g}",
                       fontSize=6, fillColor=SLATE))
    return drawing


def _heatmap_drawing(grid: list[list[int]], width: float = 470,
                     height: float = 110) -> Drawing:
    drawing = Drawing(width, height)
    if not grid:
        return drawing
    maximum = max((max(row) for row in grid), default=0) or 1
    cell_w = width / 24
    cell_h = (height - 10) / 7
    for row_idx, row in enumerate(grid):
        for hour, value in enumerate(row):
            alpha = 0.08 + 0.92 * (value / maximum)
            drawing.add(Rect(hour * cell_w, height - (row_idx + 1) * cell_h,
                             cell_w - 1, cell_h - 1,
                             fillColor=colors.Color(0.13, 0.83, 0.93, alpha=alpha),
                             strokeColor=None))
    return drawing
