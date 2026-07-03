"""Pydantic models for Research Governance (Phase 3).

Covers the four governance capabilities from ROADMAP.md Phase 3:
1. Research hypothesis registry
2. Factor inclusion/exclusion audit trail
3. Model change logs
4. Assumption override tracking
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class GovernanceAction(str, Enum):
    """Action types for governance audit trail."""

    # Hypothesis Registry
    HYPOTHESIS_REGISTERED = "HYPOTHESIS_REGISTERED"
    HYPOTHESIS_UPDATED = "HYPOTHESIS_UPDATED"
    HYPOTHESIS_RETIRED = "HYPOTHESIS_RETIRED"
    HYPOTHESIS_VALIDATED = "HYPOTHESIS_VALIDATED"
    HYPOTHESIS_REJECTED = "HYPOTHESIS_REJECTED"

    # Factor Audit Trail
    FACTOR_ADDED = "FACTOR_ADDED"
    FACTOR_REMOVED = "FACTOR_REMOVED"
    FACTOR_WEIGHT_CHANGED = "FACTOR_WEIGHT_CHANGED"
    FACTOR_RENAMED = "FACTOR_RENAMED"
    FACTOR_REORDERED = "FACTOR_REORDERED"

    # Model Change Log
    MODEL_VERSION_BUMPED = "MODEL_VERSION_BUMPED"
    MODEL_CONFIG_CHANGED = "MODEL_CONFIG_CHANGED"
    MODEL_DEPRECATED = "MODEL_DEPRECATED"
    MODEL_RESTORED = "MODEL_RESTORED"

    # Assumption Override Tracking
    ASSUMPTION_OVERRIDDEN = "ASSUMPTION_OVERRIDDEN"
    ASSUMPTION_RESTORED = "ASSUMPTION_RESTORED"
    ASSUMPTION_DEFAULT_CHANGED = "ASSUMPTION_DEFAULT_CHANGED"


class HypothesisStatus(str, Enum):
    """Status of a research hypothesis."""

    DRAFT = "DRAFT"
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


class FactorChangeType(str, Enum):
    """Type of factor change for audit trail."""

    ADDED = "ADDED"
    REMOVED = "REMOVED"
    WEIGHT_CHANGED = "WEIGHT_CHANGED"
    RENAMED = "RENAMED"
    REORDERED = "REORDERED"


class ModelChangeType(str, Enum):
    """Type of model change."""

    VERSION_BUMP = "VERSION_BUMP"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    DEPRECATED = "DEPRECATED"
    RESTORED = "RESTORED"


class OverrideType(str, Enum):
    """Type of assumption override."""

    TEMPORARY = "TEMPORARY"  # Single-run override
    PERSISTENT = "PERSISTENT"  # Until explicitly reverted
    DEFAULT_CHANGE = "DEFAULT_CHANGE"  # Permanent default change


class Hypothesis(BaseModel):
    """Research hypothesis registry entry.

    Fields capture the full lifecycle from draft -> registered -> active -> validated/rejected/retired.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    ticker: str | None = Field(
        default=None, description="Ticker this hypothesis applies to (None = universal)"
    )
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    thesis_type: Literal["BULL", "BEAR", "BASE", "MARKET_IMPLIED"] = "BASE"
    status: HypothesisStatus = HypothesisStatus.DRAFT

    # Registration metadata
    registered_by: str = "system"
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Validation criteria
    validation_criteria: list[str] = Field(
        default_factory=list, description="Explicit criteria that would validate this hypothesis"
    )
    rejection_criteria: list[str] = Field(
        default_factory=list, description="Explicit criteria that would reject this hypothesis"
    )

    # Links to supporting artifacts
    supporting_evidence: list[str] = Field(
        default_factory=list, description="References to data, reports, analyses"
    )
    related_tickers: list[str] = Field(default_factory=list)

    # Outcome tracking
    validated_at: datetime | None = None
    validated_by: str | None = None
    validation_notes: str | None = None
    rejected_at: datetime | None = None
    rejected_by: str | None = None
    rejection_reason: str | None = None
    retired_at: datetime | None = None
    retired_by: str | None = None
    retirement_reason: str | None = None

    # Versioning
    version: int = 1
    previous_version_id: str | None = None

    @field_validator("title", "description")
    @classmethod
    def _strip_whitespace(cls, v: str) -> str:
        return v.strip()


class FactorAuditEntry(BaseModel):
    """Single audit trail entry for factor inclusion/exclusion/weight changes."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action: GovernanceAction
    user: str

    # Factor identification
    factor_name: str
    factor_type: Literal["additive", "penalty"] = "additive"

    # Change details
    old_value: dict[str, Any] | None = Field(
        default=None, description="Previous state (weight, config, etc.)"
    )
    new_value: dict[str, Any] | None = Field(
        default=None, description="New state (weight, config, etc.)"
    )

    # Justification and approval
    rationale: str = Field(min_length=1, max_length=5000)
    approved_by: str | None = None
    approval_timestamp: datetime | None = None
    ticket_ref: str | None = Field(
        default=None, description="External ticket/PR reference (Jira, GitHub PR, etc.)"
    )

    # Impact analysis
    impact_analysis: str | None = Field(
        default=None, description="Expected impact on scores, backtest results, etc."
    )
    affected_tickers: list[str] = Field(
        default_factory=list, description="Tickers expected to be affected (empty = all)"
    )
    backtest_verification: str | None = Field(
        default=None, description="Reference to backtest run validating the change"
    )


class ModelChangeEntry(BaseModel):
    """Model version and configuration change log entry."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action: GovernanceAction
    user: str

    # Model identification
    model_name: str
    old_version: str | None = None
    new_version: str | None = None

    # Change details
    change_type: ModelChangeType
    config_changes: dict[str, Any] = Field(
        default_factory=dict, description="Diff of configuration changes"
    )
    affected_components: list[str] = Field(
        default_factory=list, description="Components affected (factors, weights, penalties, etc.)"
    )

    # Justification
    rationale: str = Field(min_length=1, max_length=5000)
    approved_by: str | None = None
    approval_timestamp: datetime | None = None
    ticket_ref: str | None = None

    # Validation
    backtest_run_id: str | None = Field(
        default=None, description="Backtest run ID validating the change"
    )
    validation_notes: str | None = None

    # Deprecation tracking
    deprecated_at: datetime | None = None
    deprecated_by: str | None = None
    deprecation_reason: str | None = None
    replacement_model: str | None = None


class AssumptionOverride(BaseModel):
    """Assumption override tracking with default replacement and justification.

    Captures when a user/analyst overrides a default assumption, with full
    audit trail including justification and approval.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action: GovernanceAction = GovernanceAction.ASSUMPTION_OVERRIDDEN
    user: str

    # Assumption identification
    assumption_name: str = Field(description="Name of the assumption being overridden")
    assumption_category: str = Field(
        default="general", description="Category: macro, fundamental, technical, risk, etc."
    )
    ticker: str | None = Field(
        default=None, description="Ticker this override applies to (None = global)"
    )
    pipeline_name: str = Field(
        default="default", description="Which pipeline/run this override was applied in"
    )

    # Override details
    override_type: OverrideType = OverrideType.TEMPORARY
    original_value: float | str | bool | None = None
    override_value: float | str | bool = Field(description="The value actually used")
    rationale: str | None = Field(default=None, max_length=5000)
    impact_estimate: float | None = Field(
        default=None, description="Estimated effect on fair value / verdict"
    )

    # Approval
    approved_by: str | None = None
    approval_timestamp: datetime | None = None
    ticket_ref: str | None = None

    # Lifecycle
    expires_at: datetime | None = Field(
        default=None, description="TEMPORARY overrides expire; PERSISTENT/DEFAULT_CHANGE do not"
    )
    is_active: bool = True
    expired_at: datetime | None = None
    expired_by: str | None = None

    @field_validator("rationale")
    @classmethod
    def _strip_rationale(cls, v: str | None) -> str | None:
        return v.strip() if v else v