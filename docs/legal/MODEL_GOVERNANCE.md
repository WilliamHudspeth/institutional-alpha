# Model Governance

**Effective Date:** 2026-07-05
**Product:** Institutional Alpha
**Scope:** ROADMAP.md Phase 1.5b, "Model Governance" and "Internal Audit Trail"

---

## 1. What Gets Logged

Every material change to a model, factor, or assumption is written to an
append-only JSON Lines audit trail — never edited or deleted in place. Two
logging layers exist, and they are complementary, not redundant:

| Layer | Module | File | Records |
|-------|--------|------|---------|
| Governance detail | `iam.governance.service.GovernanceService` | `~/.iam/governance/*.jsonl` | Full structured entries: hypothesis registry, factor audit trail, model change log, assumption overrides (see below) |
| Flat audit trail | `iam.audit.AuditLogger` | `~/.iam/audit.jsonl` | One line per event, mirrored from every governance action plus scoring/data-access events |
| Hash-chained log | `iam.compliance.audit.ImmutableAuditLog` | `audit_log.jsonl` (repo root by default) | Tamper-evident chain (each entry hashes the previous one) for `MODEL_CHANGE` / `SCORING_OPERATION` events where cryptographic tamper-evidence is required |

Use `GovernanceService` to query structured history (e.g. "show me every
weight change to the `quality` factor"); use `AuditLogger.query()` for a flat
chronological view; use `ImmutableAuditLog.verify_chain()` to prove a log
segment hasn't been altered.

### 1.1 Governance record types

`src/iam/governance/models.py` defines four record types, each with a
`rationale` field that is **required** (not optional) — no governance action
can be recorded without stating why:

1. **Hypothesis registry** (`Hypothesis`) — research theses, lifecycle
   `DRAFT → REGISTERED → ACTIVE → VALIDATED/REJECTED/RETIRED`.
2. **Factor audit trail** (`FactorAuditEntry`) — factor added/removed/
   reweighted/renamed, with old/new value, rationale, optional approver and
   ticket reference.
3. **Model change log** (`ModelChangeEntry`) — version bumps, config changes,
   deprecations, restorations, with old/new version and affected components.
4. **Assumption override tracking** (`AssumptionOverride`) — per-run or
   persistent overrides of a default assumption, with original vs. override
   value and an optional expiry.

## 2. Change Control Process

Any change to factor weights, model version, or default assumptions should be
recorded through `GovernanceService` at the point the change is made — not
reconstructed after the fact. In practice:

- **Rationale is mandatory.** Every call requires a `rationale` string.
- **Approval is optional but supported.** Pass `approved_by` and `ticket_ref`
  when a change goes through review; unattended/automated changes
  (`user="system"`) are still logged, just without an approver.
- **Validation should be referenced, not re-derived.** `ModelChangeEntry`
  carries a `backtest_run_id` field — link to the backtest that validated the
  change rather than asserting it validated without evidence.
- **Overrides expire.** `AssumptionOverride.override_type=TEMPORARY` entries
  should carry an `expires_at`; call `expire_override()` when the override
  is no longer active so `get_assumption_overrides(active_only=True)` stays
  accurate.

This mirrors ROADMAP.md's checklist ("any model update requires
documentation, testing, approval") without requiring a separate ticketing
system — the `ticket_ref` field is there if you already have one (GitHub PR,
Jira, Multica `HUD-NNN`), but recording a change with just a rationale is
sufficient for a solo/small-team operation.

## 3. Retention

None of these logs are auto-purged by the software — deletion is an
operator decision, not a background job. As a floor, match the audit-log
retention stated in [`PRIVACY_POLICY.md`](PRIVACY_POLICY.md) (2 years). There
is no upper bound: because entries are small, append-only JSONL, keeping the
full history costs little and is generally the safer default for an audit
trail.

## 4. Where This Fits

- [`PRIVACY_POLICY.md`](PRIVACY_POLICY.md) — what's collected and why.
- [`TERMS_OF_SERVICE.md`](TERMS_OF_SERVICE.md) §6 — the user-facing
  commitment that model changes are documented.
- `iam.compliance.disclaimers` — the "not investment advice" text embedded
  in every report export (`iam.reports`) and the Streamlit UI (`app.py`).
- `tests/test_governance.py` — behavioral tests for everything described
  above; run them before trusting a governance change to this doc.
