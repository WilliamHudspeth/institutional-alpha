"""Canonical disclaimer text for Institutional Alpha (ROADMAP Phase 1.5b).

Single source of truth for the disclaimer language required on every score,
report, and export. Import these constants rather than restating the text —
that way "what does the disclaimer say" only has one answer, and updating it
(e.g. after counsel review) only requires editing this file.
"""

from __future__ import annotations

#: One-line disclaimer for tight spaces (report footers, CLI prompts).
SHORT_DISCLAIMER = (
    "Institutional Alpha is a research tool, not investment advice. "
    "Model outputs are subject to error; past performance does not guarantee future results."
)

#: The five standard disclosure lines from ROADMAP.md Phase 1.5b, in order.
DISCLAIMER_LINES: tuple[str, ...] = (
    "This is not investment advice.",
    "Past performance does not guarantee future results.",
    "Model outputs are subject to model error and data limitations.",
    "Consult a licensed financial advisor before making investment decisions.",
    "No warranty of accuracy, completeness, or timeliness is made or implied.",
)

#: Multi-line plain-text disclaimer for reports, CLI output, and docs.
STANDARD_DISCLAIMER = "\n".join(DISCLAIMER_LINES)


def disclaimer_html() -> str:
    """Render the standard disclaimer as an HTML fragment for report footers."""
    items = "".join(f"<li>{line}</li>" for line in DISCLAIMER_LINES)
    return f'<ul class="disclaimer">{items}</ul>'


__all__ = [
    "SHORT_DISCLAIMER",
    "DISCLAIMER_LINES",
    "STANDARD_DISCLAIMER",
    "disclaimer_html",
]
