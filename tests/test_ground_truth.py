"""Tests for the GroundTruth calibration engine."""

import os
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from iam.validation.ground_truth import GroundTruth, run_calibration

def test_ground_truth_init():
    gt = GroundTruth("dummy.csv")
    assert str(gt.results_path) == "dummy.csv"

def test_ground_truth_calibrate_missing_file(caplog):
    gt = GroundTruth("non_existent.csv")
    results = gt.calibrate()
    assert results == {}
    assert "Backtest results not found" in caplog.text

@patch("pandas.read_csv")
@patch("iam.validation.ground_truth.summarize_backtest")
@patch("iam.validation.ground_truth.write_calibration")
def test_ground_truth_calibrate_success(mock_write, mock_summarize, mock_read, tmp_path):
    # Create a dummy CSV
    csv_file = tmp_path / "test_results.csv"
    csv_file.write_text("dummy,content")
    
    mock_read.return_value = pd.DataFrame({"ic": [0.05, 0.06]})
    mock_summarize.return_value = {"ic_mean": 0.05}
    
    gt = GroundTruth(str(csv_file))
    results = gt.calibrate()
    
    assert len(results) > 0
    assert "reverse_dcf" in results
    assert results["reverse_dcf"] > 0.5
    mock_write.assert_called_once()

def test_run_calibration_cli(capsys):
    with patch("iam.validation.ground_truth.GroundTruth.calibrate") as mock_cal:
        mock_cal.return_value = {"lens1": 0.8}
        run_calibration()
        captured = capsys.readouterr()
        assert "GroundTruth Calibration Results" in captured.out
        assert "lens1" in captured.out
        assert "0.80 reliability" in captured.out
