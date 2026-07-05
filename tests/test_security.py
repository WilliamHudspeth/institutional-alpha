import pytest
from pydantic import ValidationError
from iam.validation.security import SecureRequest, sanitize_ticker, mask_pii

def test_secure_request_valid_ticker():
    req = SecureRequest(ticker="AAPL")
    assert req.ticker == "AAPL"

def test_secure_request_invalid_ticker_sql_injection():
    with pytest.raises(ValidationError):
        SecureRequest(ticker="AAPL; DROP TABLE users;")

def test_secure_request_invalid_ticker_lowercase():
    with pytest.raises(ValidationError):
        SecureRequest(ticker="aapl")

def test_secure_request_valid_ticker_with_dot():
    req = SecureRequest(ticker="BRK.B")
    assert req.ticker == "BRK.B"

def test_sanitize_ticker_fixes_whitespace():
    assert sanitize_ticker("  AAPL  ") == "AAPL"
    assert sanitize_ticker("brk.b") == "BRK.B"

def test_sanitize_ticker_rejects_unsafe():
    with pytest.raises(ValueError, match="Unsafe ticker input detected"):
        sanitize_ticker("AAPL; rm -rf /")

def test_mask_pii_masks_email():
    raw_log = "User logged in with email john.doe@example.com at 10:00"
    masked = mask_pii(raw_log)
    assert masked == "User logged in with email [REDACTED EMAIL] at 10:00"
    assert "john.doe" not in masked
