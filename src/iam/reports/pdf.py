"""PDF Summary Export.

No PDF library is currently a project dependency, and this project's
architectural principle is "dependencies stay minimal." A real PDF renderer
needs a library (reportlab and weasyprint are heavy; fpdf2 is the smallest,
pure-Python option with no compiled dependencies) — that's a deliberate call
for a human to make, not something to install silently.

Until that dependency is added, this raises NotImplementedError so callers
get a clear, actionable message instead of a silent no-op or a fake PDF.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iam.pipeline.orchestrator import PipelineReport


def render_pdf_summary(report: "PipelineReport") -> bytes:
    """Render a PDF summary of one PipelineReport.

    Raises:
        NotImplementedError: always, until a PDF dependency is approved and added.
    """
    raise NotImplementedError(
        "PDF export requires a new dependency (none currently installed). "
        "Recommended: add 'fpdf2' to pyproject.toml's [project.optional-dependencies] "
        "as the smallest pure-Python option (reportlab/weasyprint are heavier and "
        "pull in more transitive dependencies). This needs an explicit decision — "
        "render_html_report() + a browser's 'print to PDF' is a zero-dependency "
        "interim path if a PDF is needed today."
    )
