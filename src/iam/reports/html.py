"""HTML Research Report Export.

Generates a research report from a PipelineReport using stdlib string
formatting only (no jinja2 dependency, per project's minimal-deps principle).
"""

from __future__ import annotations

import html as _html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iam.pipeline.orchestrator import PipelineReport


def _esc(value: object) -> str:
    return _html.escape("" if value is None else str(value))


def _pct(value: float | None, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%" if value is not None else "N/A"


def _num(value: float | None, digits: int = 2) -> str:
    return f"{value:.{digits}f}" if value is not None else "N/A"


def _lens_card(label: str, result) -> str:
    if result is None:
        return f'<div class="val-card"><div class="method">{_esc(label)}</div><div>N/A</div></div>'
    upside_cls = "positive" if (result.fair_value_to_price or 0) >= 0 else "negative"
    return f"""<div class="val-card">
    <div class="method">{_esc(label)}</div>
    <div class="fair-value">${_num(result.fair_value_per_share)}</div>
    <div class="upside {upside_cls}">{_pct(result.fair_value_to_price)}</div>
    <div class="confidence">Confidence: {_pct(result.confidence, 0)}</div>
</div>"""


def _law_section(law_report) -> str:
    if law_report is None or not (law_report.flags or law_report.violations):
        return ""
    violation_rows = "".join(
        f"<li>{_esc(c.law_name)}: {_esc(c.message)}</li>" for c in law_report.violations
    )
    flag_rows = "".join(f"<li>{_esc(c.law_name)}: {_esc(c.message)}</li>" for c in law_report.flags)
    out = ""
    if violation_rows:
        out += f'<div class="law-violations"><h3>Damodaran Law Violations</h3><ul>{violation_rows}</ul></div>'
    if flag_rows:
        out += f'<div class="law-flags"><h3>Damodaran Law Flags</h3><ul>{flag_rows}</ul></div>'
    return out


def _drift_section(drift_report) -> str:
    if drift_report is None or not drift_report.has_drift:
        return ""
    rows = "".join(f"<li>{_esc(b.describe())}</li>" for b in drift_report.breaches)
    return f'<div class="notes"><h3>Thesis Drift</h3><ul>{rows}</ul></div>'


def _monte_carlo_section(mc) -> str:
    if mc is None or not mc.percentiles:
        return ""
    cells = "".join(
        f'<div class="card"><div class="label">P{p}</div><div class="value">${_num(v)}</div></div>'
        for p, v in sorted(mc.percentiles.items())
    )
    return f"""<div class="section">
    <h2>Monte Carlo Fair Value Distribution</h2>
    <div class="grid">{cells}</div>
    <p>P(upside): {_pct(mc.prob_upside)} &mdash; {_esc(mc.narrative)}</p>
</div>"""


def _justified_premium_section(jp) -> str:
    if jp is None:
        return ""
    return f"""<div class="section">
    <h2>Relative Reality: Justified Premium</h2>
    <div class="grid">
        <div class="card"><div class="label">Actual Premium</div><div class="value">{_pct(jp.actual_premium)}</div></div>
        <div class="card"><div class="label">Deserved Premium</div><div class="value">{_pct(jp.deserved_premium)}</div></div>
        <div class="card"><div class="label">Premium Gap</div><div class="value">{_pct(jp.premium_gap)}</div></div>
    </div>
</div>"""


def render_html_report(report: "PipelineReport") -> str:
    """Render a self-contained HTML research report for one PipelineReport."""
    verdict = report.final_verdict
    rating = verdict.rating if verdict else "N/A"
    confidence_band = verdict.confidence_band if verdict else "N/A"
    blended_upside = verdict.blended_upside if verdict else None
    upside_cls = "positive" if (blended_upside or 0) >= 0 else "negative"

    notes_html = ""
    if verdict and verdict.notes:
        notes_html = (
            '<div class="notes"><h3>Verdict Notes</h3><ul>'
            + "".join(f"<li>{_esc(n)}</li>" for n in verdict.notes)
            + "</ul></div>"
        )

    tri = report.triangulation

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Institutional Alpha Research Report: {_esc(report.ticker)}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #1a1a2e; background: #f8f9fa; padding: 20px; }}
.container {{ max-width: 900px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }}
.header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 30px; }}
.header h1 {{ font-size: 28px; font-weight: 600; margin-bottom: 8px; }}
.header .meta {{ font-size: 14px; opacity: 0.8; }}
.content {{ padding: 30px; }}
.section {{ margin-bottom: 32px; }}
.section h2 {{ font-size: 18px; font-weight: 600; border-bottom: 2px solid #e8e8e8; padding-bottom: 8px; margin-bottom: 16px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; }}
.card {{ background: #f8f9fa; border-radius: 6px; padding: 16px; border-left: 3px solid #4a90d9; }}
.card .label {{ font-size: 12px; text-transform: uppercase; color: #666; }}
.card .value {{ font-size: 20px; font-weight: 600; }}
.card .value.positive {{ color: #2e7d32; }}
.card .value.negative {{ color: #c62828; }}
.val-card {{ background: #fafafa; border: 1px solid #e8e8e8; border-radius: 6px; padding: 20px; }}
.val-card .method {{ font-size: 11px; text-transform: uppercase; color: #666; margin-bottom: 8px; }}
.val-card .fair-value {{ font-size: 24px; font-weight: 700; }}
.val-card .upside.positive {{ color: #2e7d32; }}
.val-card .upside.negative {{ color: #c62828; }}
.val-card .confidence {{ font-size: 12px; color: #666; margin-top: 8px; }}
.notes {{ background: #fff3e0; border-left: 3px solid #ff9800; padding: 16px; border-radius: 0 6px 6px 0; margin-top: 12px; }}
.notes ul {{ list-style: none; }}
.notes li {{ padding: 4px 0; font-size: 13px; }}
.law-violations {{ background: #fff0f0; border-left: 3px solid #ef5350; padding: 16px; border-radius: 0 6px 6px 0; margin-top: 12px; }}
.law-flags {{ background: #fff8e1; border-left: 3px solid #ffa000; padding: 16px; border-radius: 0 6px 6px 0; margin-top: 12px; }}
.footer {{ background: #1a1a2e; color: #888; padding: 20px 30px; font-size: 11px; text-align: center; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>{_esc(report.ticker)}</h1>
        <div class="meta">Rating: {_esc(rating)} &middot; Confidence: {_esc(confidence_band)}</div>
    </div>
    <div class="content">
        <div class="section">
            <h2>Executive Summary</h2>
            <div class="grid">
                <div class="card"><div class="label">Blended Implied Move</div><div class="value {upside_cls}">{_pct(blended_upside)}</div></div>
                <div class="card"><div class="label">Triangulation Verdict</div><div class="value">{_esc(tri.verdict if tri else "N/A")}</div></div>
                <div class="card"><div class="label">Cluster Center</div><div class="value">{_pct(tri.cluster_center) if tri else "N/A"}</div></div>
            </div>
            {notes_html}
        </div>
        <div class="section">
            <h2>Valuation Lenses</h2>
            <div class="grid">
                {_lens_card("Intrinsic (DCF)", report.intrinsic)}
                {_lens_card("Relative", report.relative)}
                {_lens_card("Market-Implied", report.market_implied_engine)}
            </div>
        </div>
        {_monte_carlo_section(report.monte_carlo)}
        {_justified_premium_section(report.justified_premium)}
        {_drift_section(report.drift_report)}
        {_law_section(report.law_report)}
    </div>
    <div class="footer">
        Institutional Alpha &mdash; generated research report. Not investment advice.
    </div>
</div>
</body>
</html>
"""
