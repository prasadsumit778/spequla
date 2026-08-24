"""The monthly pack as a document -- corpus/02 section 3 P0 #10, corpus/08 section 2.

P0 #10 is "Monthly pack generation ... exported as a document." Until now the
export endpoint returned the stored JSON, which is the pack's data but is not
a document anyone can hand to a board.

The format is a single self-contained HTML file. No corpus file names a
document format, so this is an engineering choice rather than a corpus rule,
and it was made on three grounds: it needs no new dependency (CLAUDE.md
section 6), a browser prints it to PDF without a server-side renderer, and it
keeps corpus/08 section 8's rule that a chart is stored and shipped as a
specification, never as a picture -- every chart here is drawn as inline SVG
from the stored spec at render time, so nothing is ever rasterised into the
artefact.

Two properties this module must not lose:

  * Deterministic. The same artefact renders byte-identical bytes every time.
    Nothing reads the clock, and nothing is recomputed from live tables --
    the input is exactly what src/reports/signoff.render_pack returns, which
    is the frozen row (corpus/08 section 9).

  * Complete. Sections are rendered structurally rather than field by field,
    so a number that exists in the artefact always reaches the page. A
    hand-written template per section would silently drop anything it forgot,
    which is the failure mode this project exists to prevent.
"""
from __future__ import annotations

from decimal import Decimal
from html import escape

SECTION_TITLES = {
    "1_cover": "Cover",
    "2_executive_summary": "Executive summary",
    "3_financial_summary": "Financial summary",
    "4_revenue_analysis": "Revenue analysis",
    "5_margin_analysis": "Margin analysis",
    "6_working_capital": "Working capital",
    "7_cash": "Cash",
    "8_statements": "Statements",
    "9_data_quality_appendix": "Data quality appendix",
}

_STYLE = """
:root { --ink:#111; --muted:#555; --rule:#d8d8d8; --neg:#b3261e; --pos:#1b5e20; }
* { box-sizing: border-box; }
body { font: 13px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       color: var(--ink); margin: 0; padding: 32px; background: #fff; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 15px; margin: 28px 0 8px; padding-bottom: 4px; border-bottom: 1px solid var(--rule); }
h3 { font-size: 13px; margin: 16px 0 6px; color: var(--muted); font-weight: 600; }
.sub { color: var(--muted); margin: 0 0 18px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; }
th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--rule); vertical-align: top; }
th { color: var(--muted); font-weight: 600; white-space: nowrap; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 2px 16px; margin: 8px 0 16px; }
dt { color: var(--muted); }
dd { margin: 0; font-variant-numeric: tabular-nums; }
.tiles { display: flex; flex-wrap: wrap; gap: 12px; margin: 8px 0 16px; }
.tile { border: 1px solid var(--rule); border-radius: 6px; padding: 10px 14px; min-width: 150px; }
.tile .label { color: var(--muted); font-size: 11px; }
.tile .value { font-size: 18px; font-variant-numeric: tabular-nums; }
.tile .delta { font-size: 11px; color: var(--muted); }
.neg { color: var(--neg); } .pos { color: var(--pos); }
figure { margin: 8px 0 16px; }
figcaption { color: var(--muted); font-size: 11px; margin-bottom: 4px; }
.note { color: var(--muted); font-style: italic; }
footer { margin-top: 32px; padding-top: 8px; border-top: 1px solid var(--rule);
         color: var(--muted); font-size: 11px; }
@media print {
  body { padding: 0; }
  h2 { break-after: avoid; }
  table, figure, .tile { break-inside: avoid; }
}
"""


# ----------------------------------------------------------------- formatting

def _fmt(value) -> str:
    """A scalar as text. Numbers keep every digit they were stored with:
    money is numeric(18,2) (CLAUDE.md section 8) and rounding it for display
    here would put a different number on the page than in the artefact."""
    if value is None:
        return "—"          # em dash: absent, not zero
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Decimal):
        return f"{value:,}"
    if isinstance(value, (int, float)):
        return f"{value:,}"
    return str(value)


def _is_num(value) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _num_class_attr(value) -> str:
    # A plain helper rather than an inline conditional string literal inside
    # an f-string's {} -- nesting the same quote character (or a backslash)
    # inside an f-string expression needs PEP 701 (Python 3.12); this stays
    # valid on any Python 3.9+ the deployment target might actually run.
    return ' class="num"' if _is_num(value) else ""


def _num_class_attr_any(column: str, items: list[dict]) -> str:
    return ' class="num"' if any(_is_num(i.get(column)) for i in items) else ""


def _label(key: str) -> str:
    return str(key).replace("_", " ").strip().capitalize()


# ------------------------------------------------------------ generic content

def _render_value(value, depth: int = 0) -> str:
    if isinstance(value, dict):
        return _render_mapping(value, depth)
    if isinstance(value, list):
        return _render_list(value, depth)
    cls = ' class="num"' if _is_num(value) else ""
    return f"<span{cls}>{escape(_fmt(value))}</span>"


def _render_mapping(mapping: dict, depth: int = 0) -> str:
    simple, nested = [], []
    for key, value in mapping.items():
        (nested if isinstance(value, (dict, list)) else simple).append((key, value))

    out = []
    if simple:
        rows = "".join(
            f"<dt>{escape(_label(k))}</dt>"
            f"<dd{_num_class_attr(v)}>{escape(_fmt(v))}</dd>"
            for k, v in simple
        )
        out.append(f"<dl>{rows}</dl>")
    for key, value in nested:
        heading = "h3" if depth == 0 else "h3"
        out.append(f"<{heading}>{escape(_label(key))}</{heading}>")
        out.append(_render_value(value, depth + 1))
    return "".join(out)


def _render_list(items: list, depth: int = 0) -> str:
    if not items:
        return '<p class="note">None.</p>'

    if all(isinstance(i, dict) for i in items):
        columns: list[str] = []
        for item in items:
            for key in item:
                if key not in columns:
                    columns.append(key)
        # A list of flat records is a table; anything nested falls back to
        # rendering each record on its own so no value is lost.
        if all(not isinstance(v, (dict, list)) for item in items for v in item.values()):
            head = "".join(
                f"<th{_num_class_attr_any(c, items)}>"
                f"{escape(_label(c))}</th>"
                for c in columns
            )
            body = "".join(
                "<tr>" + "".join(
                    f"<td{_num_class_attr(item.get(c))}>"
                    f"{escape(_fmt(item.get(c)))}</td>"
                    for c in columns
                ) + "</tr>"
                for item in items
            )
            return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
        return "".join(_render_mapping(i, depth + 1) for i in items)

    lis = "".join(f"<li>{escape(_fmt(i))}</li>" for i in items)
    return f"<ul>{lis}</ul>"


# ------------------------------------------------------------------- charts

def _svg_line(spec: dict) -> str:
    """corpus/08 section 8's line chart, drawn from the stored spec."""
    series = spec.get("series") or []
    points = [p for s in series for p in (s.get("points") or [])]
    values = [p.get("value") for p in points if p.get("value") is not None]
    if not values:
        return '<p class="note">No plottable points in this series.</p>'

    width, height, pad = 640, 180, 28
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    n = max(len(points) - 1, 1)

    def xy(i, v):
        x = pad + (width - 2 * pad) * (i / n)
        y = height - pad - (height - 2 * pad) * ((v - lo) / span)
        return f"{x:.1f},{y:.1f}"

    path = " ".join(xy(i, p["value"]) for i, p in enumerate(points) if p.get("value") is not None)
    first = escape(str(points[0].get("period", "")))
    last = escape(str(points[-1].get("period", "")))
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">'
        f'<polyline fill="none" stroke="#3b6fb6" stroke-width="2" points="{path}"/>'
        f'<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" stroke="#d8d8d8"/>'
        f'<text x="{pad}" y="{height - 8}" font-size="10" fill="#555">{first}</text>'
        f'<text x="{width - pad}" y="{height - 8}" font-size="10" fill="#555" '
        f'text-anchor="end">{last}</text>'
        f'<text x="{pad}" y="{pad - 10}" font-size="10" fill="#555">{escape(_fmt(hi))}</text>'
        f"</svg>"
    )


def _svg_waterfall(spec: dict) -> str:
    """corpus/08 section 8's bridge. A residual component is drawn in a
    distinct fill because CLAUDE.md invariant 15 requires a gap to be
    reported, not blended into the other bars."""
    components = spec.get("components") or []
    if not components:
        return '<p class="note">No components.</p>'

    width, height, pad = 640, 200, 28
    magnitudes = [abs(c.get("value") or 0) for c in components] or [1]
    scale = max(magnitudes) or 1
    slot = (width - 2 * pad) / len(components)
    bars = []
    for i, comp in enumerate(components):
        value = comp.get("value") or 0
        residual = bool(comp.get("is_residual"))
        h = (height - 2 * pad) * (abs(value) / scale)
        x = pad + i * slot + slot * 0.15
        w = slot * 0.7
        mid = height - pad
        y = mid - h if value >= 0 else mid
        fill = "#b0762a" if residual else ("#3b6fb6" if value >= 0 else "#b3261e")
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}"/>'
            f'<text x="{x + w / 2:.1f}" y="{height - 8}" font-size="9" fill="#555" '
            f'text-anchor="middle">{escape(str(comp.get("label", "")))[:14]}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">'
        + "".join(bars)
        + f'<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" stroke="#888"/>'
        + "</svg>"
    )


def _render_tile(spec: dict) -> str:
    def delta(label, value):
        if value is None:
            return ""
        cls = "pos" if _is_num(value) and value >= 0 else "neg"
        return f'<div class="delta {cls}">{escape(label)} {escape(_fmt(value))}</div>'

    return (
        '<div class="tile">'
        f'<div class="label">{escape(str(spec.get("title", "")))}'
        f'{" (" + escape(str(spec["unit"])) + ")" if spec.get("unit") else ""}</div>'
        f'<div class="value">{escape(_fmt(spec.get("value")))}</div>'
        + delta("MoM", spec.get("delta_vs_prior_month"))
        + delta("YoY", spec.get("delta_vs_prior_year"))
        + "</div>"
    )


def _render_chart(spec: dict) -> str:
    kind = spec.get("chart_type")
    title = escape(str(spec.get("title", "")))
    if kind == "line":
        body = _svg_line(spec)
    elif kind == "waterfall":
        body = _svg_waterfall(spec)
    elif kind == "table":
        columns = spec.get("columns") or []
        rows = spec.get("rows") or []
        head = "".join(f"<th>{escape(_label(c))}</th>" for c in columns)
        body_rows = "".join(
            "<tr>" + "".join(
                f"<td{_num_class_attr(cell)}>{escape(_fmt(cell))}</td>"
                for cell in row
            ) + "</tr>"
            for row in rows
        )
        body = f"<table><thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table>"
    else:
        # corpus/08 section 8: "Anything the rules cannot handle falls back to
        # a table, which is always a correct answer."
        body = _render_value(spec)
    return f"<figure><figcaption>{title}</figcaption>{body}</figure>"


def _render_charts(specs: list) -> str:
    if not specs:
        return ""
    tiles = [s for s in specs if s.get("chart_type") == "kpi_tile"]
    others = [s for s in specs if s.get("chart_type") != "kpi_tile"]
    out = []
    if tiles:
        out.append('<div class="tiles">' + "".join(_render_tile(t) for t in tiles) + "</div>")
    out.extend(_render_chart(s) for s in others)
    return "".join(out)


# --------------------------------------------------------------------- entry

def render_html(rendered: dict) -> str:
    """The pack as one self-contained HTML document.

    `rendered` is exactly what src/reports/signoff.render_pack returns.
    """
    sections = rendered.get("sections") or {}
    period = escape(str(rendered.get("period_key", "")))
    profile = escape(str(rendered.get("profile", "")))
    status = escape(str(rendered.get("status", "")))

    body = [
        f"<h1>Monthly management pack &mdash; {period}</h1>",
        f'<p class="sub">{profile} &middot; status {status} &middot; '
        f'artefact {escape(str(rendered.get("report_artefact_id", "")))}</p>',
    ]

    if status != "signed":
        # corpus/08 section 10 gates signing; a draft leaving the building
        # unlabelled is how an unreviewed number reaches a board.
        body.append('<p class="note neg">DRAFT &mdash; this pack has not been signed off.</p>')

    for key in sorted(sections):
        title = SECTION_TITLES.get(key, _label(key))
        body.append(f"<h2>{escape(title)}</h2>")
        content = sections[key]
        if key == "2_executive_summary" and isinstance(content, dict):
            text = content.get("bullets_markdown")
            if text:
                items = "".join(
                    f"<li>{escape(line.lstrip('- ').strip())}</li>"
                    for line in str(text).splitlines() if line.strip()
                )
                body.append(f"<ul>{items}</ul>")
                body.append(f'<p class="note">Written by '
                               f'{escape(str(content.get("written_by", "human")))}.</p>')
            else:
                body.append('<p class="note">No commentary written.</p>')
            continue
        body.append(_render_value(content))

    charts = _render_charts(rendered.get("chart_specs") or [])
    if charts:
        body.append("<h2>Charts</h2>")
        body.append(charts)

    # corpus/08 section 9: provenance travels with the document.
    provenance = {
        "report_artefact_id": rendered.get("report_artefact_id"),
        "generated_at": rendered.get("generated_at"),
        "generated_by": rendered.get("generated_by"),
        "mapping_version_id": rendered.get("mapping_version_id"),
        "content_hash": rendered.get("content_hash"),
        "status": rendered.get("status"),
        "reviewer": rendered.get("reviewer"),
        "signed_at": rendered.get("signed_at"),
        "unmapped_value_inr": rendered.get("unmapped_value_inr"),
        "blocking_exception_override_reason": rendered.get("blocking_exception_override_reason"),
    }
    body.append("<footer>" + " &middot; ".join(
        f"{escape(_label(k))}: {escape(_fmt(v))}" for k, v in provenance.items() if v is not None
    ) + "</footer>")

    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>Monthly pack {period}</title>"
        f"<style>{_STYLE}</style></head><body>"
        + "".join(body)
        + "</body></html>\n"
    )
