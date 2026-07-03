import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from iam.api import Security
from iam.backtest.runner import _score_security_worker
from iam.integration.async_bridge import ParallelWorkflow


def test_score_security_worker_exception_logging(caplog):
    # Setup test security
    sec = Security(ticker="FAIL_TICKER", sector="Tech")

    # We force build_snapshot to raise an exception to simulate failure
    with (
        patch("iam.backtest.runner.load_snapshot", return_value=None),
        patch(
            "iam.backtest.runner.build_snapshot", side_effect=ValueError("Simulated snapshot error")
        ),
    ):
        with caplog.at_level(logging.ERROR):
            ticker, score, sector, mcap = _score_security_worker(
                sec, "2026-06-16", "composite", Path(".cache/snapshots")
            )

            # Assert execution did not halt and returned nan/None
            assert ticker == "FAIL_TICKER"
            assert pytest.approx(score) is not None  # It returns NaN
            import math

            assert math.isnan(score)
            assert sector == "Tech"
            assert mcap is None

            # Verify the exception was logged with traceback info (Error level)
            assert len(caplog.records) > 0
            log_record = caplog.records[0]
            assert log_record.levelname == "ERROR"
            assert "FAIL_TICKER" in log_record.message
            assert log_record.exc_info is not None  # Stack trace was captured


def test_async_bridge_parallel_workflow_exception_logging(caplog):
    workflow = ParallelWorkflow()

    # Simulating a failing pipeline function
    def failing_pipeline(ticker):
        raise RuntimeError("Simulated pipeline crash")

    workflow.add_pipeline("FAIL_TICKER", failing_pipeline)

    with caplog.at_level(logging.ERROR):
        results = workflow.execute_and_wait(timeout=1.0)

        # Verify that the task returned None on failure
        assert results["pipeline_FAIL_TICKER"] is None

        # Verify log output contains stack trace or exception info
        assert len(caplog.records) > 0
        found_error = False
        for record in caplog.records:
            if "pipeline_FAIL_TICKER" in record.message or "FAIL_TICKER" in record.message:
                assert record.levelname == "ERROR"
                assert record.exc_info is not None
                found_error = True
                break
        assert found_error, "Log record for pipeline_FAIL_TICKER failure not found"
