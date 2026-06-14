# PowerShell Installer script for Institutional Alpha (IAM)
Write-Host "=== Institutional Alpha (IAM) PowerShell Installer ===" -ForegroundColor Cyan
Write-Host "Installing package in editable mode with [live] and [backtest] extras..."

# Make sure we are in the directory of the script
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($ScriptDir) { cd $ScriptDir }

# 1. Install live dependencies stack
Write-Host "Installing [live] stack..." -ForegroundColor Yellow
pip install -e ".[live]"

# 2. Install backtest dependencies stack
Write-Host "Installing [backtest] stack..." -ForegroundColor Yellow
pip install -e ".[backtest]"

Write-Host "=== Installation completed successfully! ===" -ForegroundColor Green
