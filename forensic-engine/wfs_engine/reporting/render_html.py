"""HTML report renderer (self-contained, print friendly)."""
from __future__ import annotations

from html import escape
from typing import Any

from . import charts

THEMES = {
    "graphite": {
        "bg": "#0b0f14", "panel": "#111823", "border": "#1f2a37", "text": "#e6edf5",
        "muted": "#7c8ba1", "accent": "#22d3ee",
    },
    "light": {
        "bg": "#f8fafc", "panel": "#ffffff", "border": "#d8e0ea", "text": "#111827",
        "muted": "#5b6b7f", "accent": "#0e7490",
    },
}


def render(report: dict[str, Any], theme: str = "graphite") -> str:
    palette = THEMES.get(theme, THEMES["graphite"])
    case = report["case"]
    body: list[str] = []
    kpis: list[str] = []
    for block in report["blocks"]:
        kind = block["type"]
        if kind == "kpi":
            kpis.append(
                f'<div class="kpi"><div class="kpi-value">{escape(str(block["value"]))}</div>'
                f'<div class="kpi-label">{escape(block["label"])}</div>'
                + (f'<div class="kpi-hint">{escape(block["hint"])}</div>'
                   if block.get("hint") else "")
                + "</div>")
        elif kind == "text":
            body.append(f'<section><h2>{escape(block["title"])}</h2>'
                        f'<p class="prose">{_paragraphs(block["body"])}</p></section>')
        elif kind == "table":
            head = "".join(f"<th>{escape(str(c))}</th>" for c in block["columns"])
            rows = "".join(
                "<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>"
                for row in block["rows"][:400])
            note = (f'<p class="note">{escape(block["note"])}</p>'
                    if block.get("note") else "")
            body.append(f'<section><h2>{escape(block["title"])}</h2>'
                        f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
                        f'<tbody>{rows or "<tr><td>No rows</td></tr>"}</tbody></table></div>'
                        f'{note}</section>')
        elif kind == "chart":
            if block["chart"] == "heatmap":
                svg = charts.heatmap_chart(block["grid"], block["labels"])
            elif block["chart"] == "line":
                svg = charts.line_chart(block["labels"], block["series"][0]["values"],
                                       color=palette["accent"])
            else:
                svg = charts.bar_chart(block["labels"], block["series"][0]["values"])
            note = (f'<p class="note">{escape(block["note"])}</p>'
                    if block.get("note") else "")
            body.append(f'<section><h2>{escape(block["title"])}</h2>'
                        f'<div class="chart-wrap">{svg}</div>{note}</section>')

    evidence_rows = "".join(
        f"<tr><td>{escape(e['original_name'])}</td><td>{escape(e['source_type'])}</td>"
        f"<td>{e['size_bytes']:,}</td><td class='mono'>{escape(e['sha256'])}</td>"
        f"<td>{escape(e['imported_at'])}</td><td>{e['message_count']}</td></tr>"
        for e in report["evidence"])

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(report['title'])} — {escape(case['name'])}</title>
<style>
  :root {{ color-scheme: {"dark" if theme != "light" else "light"}; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: {palette['bg']}; color: {palette['text']};
    font-family: "Segoe UI", Inter, system-ui, -apple-system, sans-serif;
    font-size: 14px; line-height: 1.55; }}
  .page {{ max-width: 1040px; margin: 0 auto; padding: 40px 32px 80px; }}
  header.cover {{ border: 1px solid {palette['border']}; border-radius: 16px;
    padding: 28px 32px; background: linear-gradient(160deg, {palette['panel']},
    rgba(34,211,238,0.06)); }}
  .eyebrow {{ letter-spacing: .16em; text-transform: uppercase; font-size: 11px;
    color: {palette['accent']}; margin-bottom: 8px; }}
  h1 {{ font-size: 30px; margin: 0 0 8px; }}
  h2 {{ font-size: 17px; margin: 34px 0 12px; padding-bottom: 6px;
    border-bottom: 1px solid {palette['border']}; }}
  .meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 10px 24px; margin-top: 18px; font-size: 13px; }}
  .meta div span {{ color: {palette['muted']}; display: block; font-size: 11px;
    text-transform: uppercase; letter-spacing: .06em; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px; margin: 20px 0 4px; }}
  .kpi {{ background: {palette['panel']}; border: 1px solid {palette['border']};
    border-radius: 12px; padding: 14px 16px; }}
  .kpi-value {{ font-size: 22px; font-weight: 650; color: {palette['accent']}; }}
  .kpi-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: .07em;
    color: {palette['muted']}; }}
  .kpi-hint {{ font-size: 11px; color: {palette['muted']}; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  .table-wrap {{ overflow-x: auto; border: 1px solid {palette['border']};
    border-radius: 12px; }}
  th, td {{ text-align: start; unicode-bidi: plaintext; padding: 8px 10px;
    border-bottom: 1px solid {palette['border']}; vertical-align: top; }}
  /* Imported evidence decides its own direction: Arabic/Hebrew cells and
     paragraphs read right-to-left instead of being forced LTR. */
  .prose, .note {{ unicode-bidi: plaintext; text-align: start; }}
  th {{ background: rgba(255,255,255,0.03); font-size: 11px; text-transform: uppercase;
    letter-spacing: .06em; color: {palette['muted']}; }}
  tr:last-child td {{ border-bottom: none; }}
  .mono {{ font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; font-size: 11px;
    word-break: break-all; }}
  .chart-wrap {{ background: {palette['panel']}; border: 1px solid {palette['border']};
    border-radius: 12px; padding: 12px; }}
  .chart {{ width: 100%; height: auto; display: block; }}
  .prose {{ white-space: pre-wrap; color: {palette['text']}; opacity: .92; }}
  .note {{ font-size: 11.5px; color: {palette['muted']}; margin-top: 8px; }}
  .disclaimer {{ margin-top: 40px; border-left: 3px solid {palette['accent']};
    background: {palette['panel']}; padding: 14px 18px; border-radius: 8px; font-size: 12.5px;
    color: {palette['muted']}; }}
  footer {{ margin-top: 28px; font-size: 11px; color: {palette['muted']}; }}
  @media print {{ body {{ background: #fff; color: #111; }}
    .kpi, .chart-wrap, .table-wrap, header.cover {{ break-inside: avoid; }} }}
</style></head>
<body><div class="page">
<header class="cover">
  <div class="eyebrow">WhatsApp Forensic Studio AI · Analytical Report</div>
  <h1>{escape(report['title'])}</h1>
  <div class="meta">
    <div><span>Case</span>{escape(case['name'])}</div>
    <div><span>Case ID</span>{escape(str(case['case_number']))} · {escape(case['id'][:12])}</div>
    <div><span>Generated (UTC)</span>{escape(report['generated_at'])}</div>
    <div><span>Examiner</span>{escape(case['examiner'] or 'not recorded')}</div>
    <div><span>Engine</span>{escape(report['engine_version'])}</div>
    <div><span>Evidence items</span>{len(report['evidence'])}</div>
  </div>
  <div class="kpis">{''.join(kpis)}</div>
</header>
{''.join(body)}
<section><h2>Evidence sources and hashes</h2>
<div class="table-wrap"><table><thead><tr><th>File</th><th>Type</th><th>Bytes</th>
<th>SHA-256</th><th>Imported (UTC)</th><th>Messages</th></tr></thead>
<tbody>{evidence_rows or '<tr><td>No evidence</td></tr>'}</tbody></table></div></section>
<div class="disclaimer">{escape(report['disclaimer'])}</div>
<footer>Generated by WhatsApp Forensic Studio AI v{escape(report['engine_version'])} ·
Local processing only · Evidence hashes are recorded at ingestion.</footer>
</div></body></html>"""


def _paragraphs(text: str) -> str:
    return "<br>".join(escape(line) for line in str(text).split("\n"))
