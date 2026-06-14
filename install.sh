#!/usr/bin/env bash
# Installer script for Institutional Alpha (IAM)

set -e

echo "=== Institutional Alpha (IAM) Installer ==="
echo "Installing package in editable mode with [live] and [backtest] extras..."

# Make sure we are in the directory of the script
cd "$(dirname "$0")"

# 1. Install live dependencies stack (yfinance, pandas, numpy, scipy, etc.)
echo "Installing [live] stack..."
pip install -e ".[live]"

# 2. Install backtest dependencies stack (polars, diskcache, statsmodels, etc.)
echo "Installing [backtest] stack..."
pip install -e ".[backtest]"

echo "=== Installation completed successfully! ==="
