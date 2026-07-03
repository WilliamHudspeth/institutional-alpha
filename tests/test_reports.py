import pytest

from iam.data.security import Security
from iam.pipeline.orchestrator import ValuationPipeline
from iam.reports import render_csv_export, render_html_report, render_pdf_summary


def _sample_report():
    sec = Security(ticker="AAPL")
    sec.name = "Apple Inc."
    sec.sector = "Technology"
    sec.market.price = 150.0
    sec.fundamentals.fcf_ttm = 100000.0
    sec.fundamentals.shares_outstanding = 15000.0
    sec.fundamentals.total_debt = 50000.0
    sec.fundamentals.cash_and_equivalents = 0.0
    sec.fundamentals.revenue_history = [1000, 900, 800, 700]
    sec.fundamentals.operating_margin_history = [0.25, 0.24, 0.23, 0.22]
    sec.market.pe_history = [25.0] * 24
    sec.market.ev_ebitda = 14.5
    sec.market.sector_ev_ebitda_median = 12.0

    pipeline = ValuationPipeline()
    return pipeline.run(sec)


def test_render_html_report_contains_ticker_and_verdict():
    report = _sample_report()
    html = render_html_report(report)
    assert report.ticker in html
    assert report.final_verdict.rating in html
    assert "<html" in html and "</html>" in html


def test_render_html_report_handles_missing_optional_sections():
    report = _sample_report()
    report.monte_carlo = None
    report.justified_premium = None
    report.drift_report = None
    report.law_report = None
    html = render_html_report(report)
    assert report.ticker in html


def test_render_csv_export_has_header_and_ticker_row():
    report = _sample_report()
    csv_text = render_csv_export(report)
    assert "ticker" in csv_text
    assert report.ticker in csv_text
    assert "fair_value_per_share" in csv_text


def test_render_pdf_summary_raises_until_dependency_added():
    report = _sample_report()
    with pytest.raises(NotImplementedError, match="fpdf2"):
        render_pdf_summary(report)
