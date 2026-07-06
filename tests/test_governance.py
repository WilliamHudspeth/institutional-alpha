import pytest

from iam import audit as audit_module
from iam.governance import service as governance_service_module
from iam.governance.models import GovernanceAction, ModelChangeType, OverrideType
from iam.governance.service import GovernanceService


@pytest.fixture(autouse=True)
def isolated_governance_storage(tmp_path, monkeypatch):
    """Redirect governance + audit JSONL storage to a tmp dir so tests never
    touch the real ~/.iam/ directory."""
    monkeypatch.setattr(governance_service_module, "_GOVERNANCE_DIR", tmp_path)
    monkeypatch.setattr(governance_service_module, "_HYPOTHESIS_FILE", tmp_path / "hypotheses.jsonl")
    monkeypatch.setattr(governance_service_module, "_FACTOR_AUDIT_FILE", tmp_path / "factor_audit.jsonl")
    monkeypatch.setattr(governance_service_module, "_MODEL_CHANGE_FILE", tmp_path / "model_changes.jsonl")
    monkeypatch.setattr(
        governance_service_module, "_ASSUMPTION_OVERRIDE_FILE", tmp_path / "assumption_overrides.jsonl"
    )
    original_init = audit_module.AuditLogger.__init__
    def new_init(self, log_path="audit_log.jsonl"):
        original_init(self, str(tmp_path / "audit_log.jsonl"))
    monkeypatch.setattr(audit_module.AuditLogger, "__init__", new_init)
    yield


@pytest.fixture
def svc():
    return GovernanceService()


def test_hypothesis_register_and_get_roundtrip(svc):
    h = svc.register_hypothesis(
        title="AAPL margin expansion thesis",
        description="Services mix shift drives gross margin above 46% by FY26",
        thesis_type="BULL",
        ticker="AAPL",
        registered_by="analyst_1",
    )
    fetched = svc.get_hypothesis(h.id)
    assert fetched is not None
    assert fetched.title == h.title
    assert fetched.status.value == "DRAFT"


def test_hypothesis_update_status_and_versioning(svc):
    h = svc.register_hypothesis(title="Thesis A", description="Description A")
    updated = svc.update_hypothesis(h.id, status="VALIDATED", updated_by="analyst_2")
    assert updated is not None
    assert updated.status.value == "VALIDATED"
    assert updated.validated_by == "analyst_2"
    assert updated.version == 2


def test_hypothesis_retire(svc):
    h = svc.register_hypothesis(title="Thesis B", description="Description B")
    retired = svc.retire_hypothesis(h.id, reason="No longer relevant")
    assert retired is not None
    assert retired.status.value == "RETIRED"


def test_hypothesis_list_filters_by_ticker(svc):
    svc.register_hypothesis(title="T1", description="D1", ticker="AAPL")
    svc.register_hypothesis(title="T2", description="D2", ticker="MSFT")
    results = svc.list_hypotheses(ticker="AAPL")
    assert len(results) == 1
    assert results[0].ticker == "AAPL"


def test_get_hypothesis_missing_returns_none(svc):
    assert svc.get_hypothesis("does-not-exist") is None


def test_factor_audit_record_and_query(svc):
    entry = svc.record_factor_change(
        factor_name="quality_score",
        action=GovernanceAction.FACTOR_WEIGHT_CHANGED,
        old_value={"weight": 0.2},
        new_value={"weight": 0.3},
        rationale="Backtest showed improved IC after reweighting",
    )
    results = svc.get_factor_audit(factor_name="quality_score")
    assert len(results) == 1
    assert results[0].id == entry.id
    assert results[0].new_value == {"weight": 0.3}


def test_factor_audit_requires_rationale(svc):
    with pytest.raises(Exception):
        svc.record_factor_change(
            factor_name="momentum",
            action=GovernanceAction.FACTOR_ADDED,
            rationale="",
        )


def test_model_change_log_record_and_query(svc):
    svc.record_model_change(
        model_name="DamodaranLawRegistry",
        change_type=ModelChangeType.CONFIG_CHANGE,
        rationale="Tightened Law 3 ceiling band from 0.5% to 0.25%",
        old_version="1.2.0",
        new_version="1.3.0",
    )
    results = svc.get_model_changes(model_name="DamodaranLawRegistry")
    assert len(results) == 1
    assert results[0].new_version == "1.3.0"


def test_assumption_override_record_and_query(svc):
    svc.record_assumption_override(
        assumption_name="terminal_growth",
        override_type=OverrideType.TEMPORARY,
        original_value=0.025,
        override_value=0.035,
        pipeline_name="AAPL_run_2026Q3",
        rationale="Analyst override for one-off re-rating scenario",
    )
    results = svc.get_assumption_overrides(pipeline_name="AAPL_run_2026Q3")
    assert len(results) == 1
    assert results[0].override_value == 0.035
    assert results[0].is_active is True


def test_assumption_override_expire(svc):
    override = svc.record_assumption_override(
        assumption_name="wacc",
        override_type=OverrideType.PERSISTENT,
        original_value=0.09,
        override_value=0.11,
        pipeline_name="run_1",
    )
    expired = svc.expire_override(override.id, expired_by="analyst_3")
    assert expired is not None
    assert expired.is_active is False
    assert expired.expired_by == "analyst_3"


def test_governance_actions_are_audited(svc, monkeypatch):
    """Every governance write should also emit an entry to the shared AuditLogger."""
    recorded_events = []
    original_log_change = audit_module.AuditLogger.log_change

    def spy_log_change(self, model_id, change_type, details):
        recorded_events.append(change_type)
        return original_log_change(self, model_id, change_type, details)

    monkeypatch.setattr(audit_module.AuditLogger, "log_change", spy_log_change)

    svc.register_hypothesis(title="Audited thesis", description="Should emit an audit event")
    assert GovernanceAction.HYPOTHESIS_REGISTERED.value in recorded_events
