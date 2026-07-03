"""Governance service layer.

Provides storage, CRUD operations, and audit integration for the four
governance capabilities:
1. Research hypothesis registry
2. Factor inclusion/exclusion audit trail
3. Model change logs
4. Assumption override tracking
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from iam.audit import AuditLog
from iam.governance.models import (
    AssumptionOverride,
    FactorAuditEntry,
    GovernanceAction,
    Hypothesis,
    ModelChangeEntry,
    ModelChangeType,
)


_GOVERNANCE_DIR = Path(os.environ.get("IAM_GOVERNANCE_DIR", "~/.iam/governance")).expanduser()
_HYPOTHESIS_FILE = _GOVERNANCE_DIR / "hypotheses.jsonl"
_FACTOR_AUDIT_FILE = _GOVERNANCE_DIR / "factor_audit.jsonl"
_MODEL_CHANGE_FILE = _GOVERNANCE_DIR / "model_changes.jsonl"
_ASSUMPTION_OVERRIDE_FILE = _GOVERNANCE_DIR / "assumption_overrides.jsonl"


def _ensure_governance_dir() -> None:
    _GOVERNANCE_DIR.mkdir(parents=True, exist_ok=True)


def _append_jsonl(file_path: Path, record: dict[str, Any]) -> None:
    _ensure_governance_dir()
    line = json.dumps(record, default=str) + "\n"
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(line)


def _read_jsonl(file_path: Path) -> list[dict[str, Any]]:
    if not file_path.exists():
        return []
    lines = file_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lines if l.strip()]


def _write_jsonl(file_path: Path, records: list[dict[str, Any]]) -> None:
    _ensure_governance_dir()
    with open(file_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, default=str) + "\n")


class GovernanceService:
    """Service layer for research governance operations."""

    # --- Hypothesis Registry ---

    def register_hypothesis(
        self,
        *,
        title: str,
        description: str,
        thesis_type: str = "BASE",
        ticker: str | None = None,
        registered_by: str = "system",
        validation_criteria: list[str] | None = None,
        rejection_criteria: list[str] | None = None,
        supporting_evidence: list[str] | None = None,
        related_tickers: list[str] | None = None,
    ) -> Hypothesis:
        """Register a new research hypothesis."""
        hypothesis = Hypothesis(
            title=title,
            description=description,
            thesis_type=thesis_type,  # type: ignore[arg-type]
            ticker=ticker,
            registered_by=registered_by,
            validation_criteria=validation_criteria or [],
            rejection_criteria=rejection_criteria or [],
            supporting_evidence=supporting_evidence or [],
            related_tickers=related_tickers or [],
        )
        self._save_hypothesis(hypothesis)
        self._audit_hypothesis(hypothesis, GovernanceAction.HYPOTHESIS_REGISTERED, registered_by)
        return hypothesis

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis | None:
        """Retrieve a hypothesis by ID."""
        for record in _read_jsonl(_HYPOTHESIS_FILE):
            if record.get("id") == hypothesis_id:
                return Hypothesis(**record)
        return None

    def list_hypotheses(
        self,
        *,
        status: str | None = None,
        ticker: str | None = None,
        thesis_type: str | None = None,
    ) -> list[Hypothesis]:
        """List hypotheses with optional filters."""
        results = []
        for record in _read_jsonl(_HYPOTHESIS_FILE):
            if status and record.get("status") != status:
                continue
            if ticker and record.get("ticker") != ticker:
                continue
            if thesis_type and record.get("thesis_type") != thesis_type:
                continue
            results.append(Hypothesis(**record))
        return results

    def update_hypothesis(
        self,
        hypothesis_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        validation_criteria: list[str] | None = None,
        rejection_criteria: list[str] | None = None,
        supporting_evidence: list[str] | None = None,
        related_tickers: list[str] | None = None,
        updated_by: str = "system",
    ) -> Hypothesis | None:
        """Update an existing hypothesis."""
        records = _read_jsonl(_HYPOTHESIS_FILE)
        for i, record in enumerate(records):
            if record.get("id") == hypothesis_id:
                old_record = record.copy()
                if title is not None:
                    record["title"] = title
                if description is not None:
                    record["description"] = description
                if status is not None:
                    record["status"] = status
                    if status == "VALIDATED":
                        record["validated_at"] = datetime.utcnow().isoformat()
                        record["validated_by"] = updated_by
                    elif status == "REJECTED":
                        record["rejected_at"] = datetime.utcnow().isoformat()
                        record["rejected_by"] = updated_by
                    elif status == "RETIRED":
                        record["retired_at"] = datetime.utcnow().isoformat()
                        record["retired_by"] = updated_by
                if validation_criteria is not None:
                    record["validation_criteria"] = validation_criteria
                if rejection_criteria is not None:
                    record["rejection_criteria"] = rejection_criteria
                if supporting_evidence is not None:
                    record["supporting_evidence"] = supporting_evidence
                if related_tickers is not None:
                    record["related_tickers"] = related_tickers
                record["updated_at"] = datetime.utcnow().isoformat()
                record["version"] = record.get("version", 1) + 1
                record["previous_version_id"] = old_record.get("id")

                _write_jsonl(_HYPOTHESIS_FILE, records)
                updated = Hypothesis(**record)
                self._audit_hypothesis(updated, GovernanceAction.HYPOTHESIS_UPDATED, updated_by)
                return updated
        return None

    def retire_hypothesis(
        self, hypothesis_id: str, reason: str, retired_by: str = "system"
    ) -> Hypothesis | None:
        """Retire a hypothesis."""
        return self.update_hypothesis(
            hypothesis_id,
            status="RETIRED",
            updated_by=retired_by,
        )

    def _save_hypothesis(self, hypothesis: Hypothesis) -> None:
        _append_jsonl(_HYPOTHESIS_FILE, hypothesis.model_dump())

    def _audit_hypothesis(
        self, hypothesis: Hypothesis, action: GovernanceAction, user: str
    ) -> None:
        AuditLog.record(
            event=action.value,
            ticker=hypothesis.ticker,
            user=user,
            hypothesis_id=hypothesis.id,
            hypothesis_title=hypothesis.title,
            hypothesis_status=hypothesis.status.value,
        )

    # --- Factor Audit Trail ---

    def record_factor_change(
        self,
        *,
        factor_name: str,
        factor_type: str = "additive",
        action: GovernanceAction,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        rationale: str,
        user: str = "system",
        approved_by: str | None = None,
        ticket_ref: str | None = None,
        impact_analysis: str | None = None,
        affected_tickers: list[str] | None = None,
        backtest_verification: str | None = None,
    ) -> FactorAuditEntry:
        """Record a factor inclusion/exclusion/weight change."""
        entry = FactorAuditEntry(
            action=action,
            user=user,
            factor_name=factor_name,
            factor_type=factor_type,  # type: ignore[arg-type]
            old_value=old_value,
            new_value=new_value,
            rationale=rationale,
            approved_by=approved_by,
            approval_timestamp=datetime.utcnow() if approved_by else None,
            ticket_ref=ticket_ref,
            impact_analysis=impact_analysis,
            affected_tickers=affected_tickers or [],
            backtest_verification=backtest_verification,
        )
        _append_jsonl(_FACTOR_AUDIT_FILE, entry.model_dump())
        AuditLog.record(
            event=action.value,
            user=user,
            factor_name=factor_name,
            factor_type=factor_type,
            old_value=old_value,
            new_value=new_value,
            rationale=rationale,
            ticket_ref=ticket_ref,
        )
        return entry

    def get_factor_audit(
        self,
        *,
        factor_name: str | None = None,
        action: GovernanceAction | None = None,
        user: str | None = None,
        limit: int = 100,
    ) -> list[FactorAuditEntry]:
        """Query factor audit trail with filters."""
        results = []
        for record in reversed(_read_jsonl(_FACTOR_AUDIT_FILE)):
            if factor_name and record.get("factor_name") != factor_name:
                continue
            if action and record.get("action") != action.value:
                continue
            if user and record.get("user") != user:
                continue
            results.append(FactorAuditEntry(**record))
            if len(results) >= limit:
                break
        return results

    # --- Model Change Log ---

    def record_model_change(
        self,
        *,
        model_name: str,
        change_type: ModelChangeType,
        rationale: str,
        user: str = "system",
        old_version: str | None = None,
        new_version: str | None = None,
        config_changes: dict[str, Any] | None = None,
        affected_components: list[str] | None = None,
        approved_by: str | None = None,
        ticket_ref: str | None = None,
        backtest_run_id: str | None = None,
        validation_notes: str | None = None,
    ) -> ModelChangeEntry:
        """Record a model configuration change."""
        action = {
            ModelChangeType.VERSION_BUMP: GovernanceAction.MODEL_VERSION_BUMPED,
            ModelChangeType.CONFIG_CHANGE: GovernanceAction.MODEL_CONFIG_CHANGED,
            ModelChangeType.DEPRECATED: GovernanceAction.MODEL_DEPRECATED,
            ModelChangeType.RESTORED: GovernanceAction.MODEL_RESTORED,
        }[change_type]
        entry = ModelChangeEntry(
            action=action,
            model_name=model_name,
            change_type=change_type,
            rationale=rationale,
            user=user,
            old_version=old_version,
            new_version=new_version,
            config_changes=config_changes or {},
            affected_components=affected_components or [],
            approved_by=approved_by,
            approval_timestamp=datetime.utcnow() if approved_by else None,
            ticket_ref=ticket_ref,
            backtest_run_id=backtest_run_id,
            validation_notes=validation_notes,
        )
        _append_jsonl(_MODEL_CHANGE_FILE, entry.model_dump())
        AuditLog.record(
            event=f"MODEL_{change_type.value}",
            user=user,
            model_name=model_name,
            change_type=change_type.value,
            old_version=old_version,
            new_version=new_version,
            config_changes=config_changes,
            rationale=rationale,
            ticket_ref=ticket_ref,
        )
        return entry

    def get_model_changes(
        self,
        *,
        model_name: str | None = None,
        change_type: str | None = None,
        user: str | None = None,
        limit: int = 100,
    ) -> list[ModelChangeEntry]:
        """Query model change log with filters."""
        results = []
        for record in reversed(_read_jsonl(_MODEL_CHANGE_FILE)):
            if model_name and record.get("model_name") != model_name:
                continue
            if change_type and record.get("change_type") != change_type:
                continue
            if user and record.get("user") != user:
                continue
            results.append(ModelChangeEntry(**record))
            if len(results) >= limit:
                break
        return results

    # --- Assumption Override Tracking ---

    def record_assumption_override(
        self,
        *,
        assumption_name: str,
        override_type: str,
        original_value: float | str | bool,
        override_value: float | str | bool,
        pipeline_name: str,
        user: str = "system",
        rationale: str | None = None,
        expires_at: datetime | None = None,
        approved_by: str | None = None,
        ticket_ref: str | None = None,
        impact_estimate: float | None = None,
    ) -> AssumptionOverride:
        """Record an assumption override."""
        override = AssumptionOverride(
            assumption_name=assumption_name,
            override_type=override_type,  # type: ignore[arg-type]
            original_value=original_value,
            override_value=override_value,
            pipeline_name=pipeline_name,
            user=user,
            rationale=rationale,
            expires_at=expires_at,
            approved_by=approved_by,
            approval_timestamp=datetime.utcnow() if approved_by else None,
            ticket_ref=ticket_ref,
            impact_estimate=impact_estimate,
        )
        _append_jsonl(_ASSUMPTION_OVERRIDE_FILE, override.model_dump())
        AuditLog.record(
            event="ASSUMPTION_OVERRIDE",
            user=user,
            assumption_name=assumption_name,
            override_type=override_type,
            original_value=original_value,
            override_value=override_value,
            pipeline_name=pipeline_name,
            rationale=rationale,
            ticket_ref=ticket_ref,
        )
        return override

    def get_assumption_overrides(
        self,
        *,
        pipeline_name: str | None = None,
        assumption_name: str | None = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[AssumptionOverride]:
        """Query assumption overrides with filters."""
        results = []
        for record in reversed(_read_jsonl(_ASSUMPTION_OVERRIDE_FILE)):
            if pipeline_name and record.get("pipeline_name") != pipeline_name:
                continue
            if assumption_name and record.get("assumption_name") != assumption_name:
                continue
            if active_only:
                expires_at = record.get("expires_at")
                if expires_at and datetime.fromisoformat(expires_at) < datetime.utcnow():
                    continue
            results.append(AssumptionOverride(**record))
            if len(results) >= limit:
                break
        return results

    def expire_override(self, override_id: str, expired_by: str = "system") -> AssumptionOverride | None:
        """Expire an active assumption override."""
        records = _read_jsonl(_ASSUMPTION_OVERRIDE_FILE)
        for record in records:
            if record.get("id") == override_id:
                record["is_active"] = False
                record["expired_at"] = datetime.utcnow().isoformat()
                record["expired_by"] = expired_by
                _write_jsonl(_ASSUMPTION_OVERRIDE_FILE, records)
                override = AssumptionOverride(**record)
                AuditLog.record(
                    event="ASSUMPTION_OVERRIDE_EXPIRED",
                    user=expired_by,
                    assumption_name=override.assumption_name,
                    pipeline_name=override.pipeline_name,
                )
                return override
        return None


# Module-level singleton instance
governance_service = GovernanceService()


__all__ = [
    "GovernanceService",
    "governance_service",
]
