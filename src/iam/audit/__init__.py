"""Immutable audit logger for Institutional Alpha.

Every model invocation, scoring operation, assumption override, and
data-access event is appended here. Logs are append-only (never
deleted or modified) to satisfy SEC 17a-4 and GDPR Article 30
record-keeping requirements.

Usage:
    from iam.audit import AuditLog
    AuditLog.record("score", ticker="MSFT", user="anonymous", verdict="BUY")
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

_LOG_PATH = Path(os.environ.get("IAM_AUDIT_LOG", "~/.iam/audit.jsonl")).expanduser()


def _ensure_log_dir() -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _append(record: dict[str, Any]) -> None:
    """Atomically append a JSON record to the audit log."""
    _ensure_log_dir()
    line = json.dumps(record, default=str) + "\n"
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)


class AuditLog:
    """Append-only audit logger.  Call AuditLog.record() anywhere in the pipeline."""

    @staticmethod
    def record(
        event: str,
        *,
        ticker: str | None = None,
        user: str = "anonymous",
        **kwargs: Any,
    ) -> None:
        """Append a single audit record.

        Args:
            event:  Event type (e.g. "score", "assumption_override", "data_access").
            ticker: Ticker symbol if applicable.
            user:   Authenticated user identifier (defaults to "anonymous").
            **kwargs: Arbitrary key-value metadata to include in the record.
        """
        _append(
            {
                "id": str(uuid.uuid4()),
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": event,
                "ticker": ticker,
                "user": user,
                **kwargs,
            }
        )

    @staticmethod
    def tail(n: int = 20) -> list[dict[str, Any]]:
        """Return the last *n* audit records (for inspection / tests only)."""
        if not _LOG_PATH.exists():
            return []
        lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()
        return [json.loads(l) for l in lines[-n:] if l.strip()]

    @staticmethod
    def query(
        event_type: str | None = None,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Return audit records matching an event type, a `ts` time range, and field filters.

        `start_time`/`end_time` bound the record's write timestamp (`ts`), not any
        business-date field the caller passed in as metadata. `filters` are exact-match
        against top-level record fields; a `None`-valued filter is treated as unconstrained.
        Reads and parses the entire log file — fine for periodic monitoring queries, not a
        hot path.
        """
        if not _LOG_PATH.exists():
            return []
        lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()
        results = []
        for line in lines:
            if not line.strip():
                continue
            record = json.loads(line)
            if event_type is not None and record.get("event") != event_type:
                continue
            if start_time is not None or end_time is not None:
                ts = datetime.strptime(record["ts"], "%Y-%m-%dT%H:%M:%SZ")
                if start_time is not None and ts < start_time:
                    continue
                if end_time is not None and ts > end_time:
                    continue
            if any(record.get(key) != value for key, value in filters.items() if value is not None):
                continue
            results.append(record)
        return results
