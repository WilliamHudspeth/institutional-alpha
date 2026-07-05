"""CSV Export (Excel-compatible).

A plain CSV satisfies ROADMAP.md's "Excel-compatible outputs" bullet without
adding a pandas/openpyxl dependency — Excel opens CSV natively.
"""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

from iam.compliance.disclaimers import DISCLAIMER_LINES

if TYPE_CHECKING:
    from iam.pipeline.orchestrator import PipelineReport


def render_csv_export(report: "PipelineReport") -> str:
    """Render a single-row-per-lens CSV summary of one PipelineReport."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    verdict = report.final_verdict
    writer.writerow(["ticker", report.ticker])
    writer.writerow(["rating", verdict.rating if verdict else ""])
    writer.writerow(["confidence_band", verdict.confidence_band if verdict else ""])
    writer.writerow(["blended_upside", verdict.blended_upside if verdict else ""])
    writer.writerow([])

    writer.writerow(["lens", "fair_value_per_share", "fair_value_to_price", "confidence"])
    for label, result in (
        ("intrinsic", report.intrinsic),
        ("relative", report.relative),
        ("market_implied", report.market_implied_engine),
    ):
        if result is None:
            writer.writerow([label, "", "", ""])
        else:
            writer.writerow(
                [
                    label,
                    result.fair_value_per_share,
                    result.fair_value_to_price,
                    result.confidence,
                ]
            )

    tri = report.triangulation
    if tri is not None:
        writer.writerow([])
        writer.writerow(["triangulation_verdict", tri.verdict])
        writer.writerow(["cluster_center", tri.cluster_center])
        writer.writerow(["spread", tri.spread])
        writer.writerow(["triangulation_confidence", tri.confidence])

    writer.writerow([])
    writer.writerow(["disclaimer"])
    for line in DISCLAIMER_LINES:
        writer.writerow([line])

    return buf.getvalue()
