"""Institutional Exports Package.

This package provides export functionality for valuation pipeline results
in institutional-grade formats:
- HTML research reports (using stdlib string.Template/f-strings)
- CSV exports (Excel-compatible, no external dependencies)
- PDF summaries (recommends fpdf2 as minimal pure-Python dependency)

All exports consume the PipelineReport dataclass from iam.pipeline.orchestrator
and expose institutional risk metrics already computed in the pipeline.
"""

from iam.reports.html import render_html_report
from iam.reports.csv import render_csv_export
from iam.reports.pdf import render_pdf_summary

__all__ = [
    "render_html_report",
    "render_csv_export",
    "render_pdf_summary",
]