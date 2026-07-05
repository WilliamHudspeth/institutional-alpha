"""Compliance module.

Contains infrastructure for SEC/GDPR compliance:
- :mod:`iam.compliance.audit` — hash-chained immutable audit log.
- :mod:`iam.compliance.disclaimers` — canonical "not investment advice" text,
  embedded in every report export (see ``iam.reports``) and the Streamlit UI.

See :mod:`iam.audit` for the plain JSONL audit logger used by the governance
service, and :mod:`iam.governance` for model change / hypothesis / assumption
audit trails.
"""

from iam.compliance.disclaimers import (
    DISCLAIMER_LINES,
    SHORT_DISCLAIMER,
    STANDARD_DISCLAIMER,
    disclaimer_html,
)

__all__ = [
    "DISCLAIMER_LINES",
    "SHORT_DISCLAIMER",
    "STANDARD_DISCLAIMER",
    "disclaimer_html",
]
