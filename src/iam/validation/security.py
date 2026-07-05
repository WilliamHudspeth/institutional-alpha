import re
from datetime import date
from typing import Annotated
from pydantic import BaseModel, Field, field_validator

# Strict Regex for Tickers: 1 to 5 uppercase letters, optionally followed by a dot and 1-2 uppercase letters (e.g. AAPL, BRK.B)
TICKER_REGEX = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")

class SecureRequest(BaseModel):
    """Base class for all incoming API requests to ensure baseline validation."""
    
    ticker: str = Field(..., description="The stock ticker symbol.")
    as_of_date: date = Field(default_factory=date.today, description="The date the request is valid for (ISO 8601).")

    @field_validator('ticker')
    def validate_ticker_format(cls, v: str) -> str:
        if not TICKER_REGEX.match(v):
            raise ValueError(f"Invalid ticker format: {v}. Must be uppercase letters only, e.g. AAPL or BRK.B")
        return v

def sanitize_ticker(ticker_input: str) -> str:
    """Helper to sanitize and upper-case raw ticker strings safely."""
    clean = str(ticker_input).strip().upper()
    if not TICKER_REGEX.match(clean):
        raise ValueError(f"Security Exception: Unsafe ticker input detected '{clean}'")
    return clean

def mask_pii(data: str) -> str:
    """Basic PII masking for logging."""
    # Mask email patterns
    email_pattern = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
    masked = email_pattern.sub("[REDACTED EMAIL]", data)
    return masked
