"""Behavioural tests for iam.bootstrap and iam.compliance.audit (filesystem only, no network)."""

import hashlib
import json
import logging
import subprocess
import sys

import pytest

from iam import bootstrap
from iam.compliance import audit
from iam.compliance.audit import ImmutableAuditLog

GENESIS = hashlib.sha256(b"genesis").hexdigest()


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    """Point bootstrap's project-root computation at tmp_path/a/b/mod.py -> tmp_path."""
    f = tmp_path / "a" / "b" / "mod.py"
    f.parent.mkdir(parents=True)
    monkeypatch.setattr(bootstrap, "__file__", str(f))
    return tmp_path


class TestBootstrap:
    def test_python_version_ok_and_too_old(self, monkeypatch, caplog):
        assert bootstrap.check_python_version() is True
        monkeypatch.setattr(bootstrap, "REQUIRED_PYTHON_VERSION", (99, 0))
        with caplog.at_level(logging.ERROR):
            assert bootstrap.check_python_version() is False
        assert "requires Python 99.0+" in caplog.text

    def test_ensure_directories_creates_then_reuses(self, fake_root):
        bootstrap.ensure_directories()
        for d in bootstrap.REQUIRED_DIRECTORIES:
            assert (fake_root / d).is_dir()
        bootstrap.ensure_directories()  # idempotent

    def test_dependencies_present(self):
        assert bootstrap.check_dependencies() is True

    def test_dependencies_missing_install_success_and_failure(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "pydantic":
                raise ImportError(name)
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        calls = []
        monkeypatch.setattr(subprocess, "check_call", lambda cmd: calls.append(cmd))
        assert bootstrap.check_dependencies() is True
        assert calls[0][:4] == [sys.executable, "-m", "pip", "install"]

        def fail(cmd):
            raise subprocess.CalledProcessError(1, cmd)

        monkeypatch.setattr(subprocess, "check_call", fail)
        assert bootstrap.check_dependencies() is False

    def test_init_config_copies_template(self, fake_root):
        (fake_root / "config.example.yml").write_text("a: 1\n")
        bootstrap.init_config()
        assert (fake_root / "config.yml").read_text() == "a: 1\n"

    def test_init_config_does_not_overwrite_and_warns_when_missing(self, fake_root, caplog):
        (fake_root / "config.yml").write_text("mine: true\n")
        (fake_root / "config.example.yml").write_text("a: 1\n")
        bootstrap.init_config()
        assert (fake_root / "config.yml").read_text() == "mine: true\n"
        (fake_root / "config.yml").unlink()
        (fake_root / "config.example.yml").unlink()
        with caplog.at_level(logging.WARNING):
            bootstrap.init_config()
        assert "config.example.yml not found" in caplog.text
        assert not (fake_root / "config.yml").exists()

    def test_initialize_system_success_and_stops_at_failure(self, monkeypatch):
        ran = []
        monkeypatch.setattr(bootstrap, "check_python_version", lambda: ran.append(1) or True)
        monkeypatch.setattr(bootstrap, "ensure_directories", lambda: ran.append(2))
        monkeypatch.setattr(bootstrap, "check_dependencies", lambda: ran.append(3) or True)
        monkeypatch.setattr(bootstrap, "init_config", lambda: ran.append(4))
        assert bootstrap.initialize_system() is True
        assert ran == [1, 2, 3, 4]

        ran.clear()
        monkeypatch.setattr(bootstrap, "check_dependencies", lambda: ran.append(3) or False)
        assert bootstrap.initialize_system() is False
        assert ran == [1, 2, 3]  # init_config never reached


@pytest.fixture
def fresh_log(tmp_path, monkeypatch):
    """Reset the audit singleton so each test gets its own file."""
    monkeypatch.setattr(ImmutableAuditLog, "_instance", None)
    yield str(tmp_path / "audit.jsonl")
    ImmutableAuditLog._instance = None


class TestAuditLog:
    def test_chain_links_and_verifies(self, fresh_log):
        log = ImmutableAuditLog(fresh_log)
        h1 = log.log_event("A", "u", {"k": 1})
        h2 = log.log_event("B", "u", {"k": 2})
        assert h1 != h2 and log.last_hash == h2
        lines = [json.loads(x) for x in open(fresh_log)]
        assert lines[0]["payload"]["previous_hash"] == GENESIS
        assert lines[1]["payload"]["previous_hash"] == h1
        assert ImmutableAuditLog.verify_chain(fresh_log) is True

    def test_singleton(self, fresh_log):
        assert ImmutableAuditLog(fresh_log) is ImmutableAuditLog("ignored.jsonl")

    def test_resumes_chain_from_existing_file(self, fresh_log, monkeypatch):
        h = ImmutableAuditLog(fresh_log).log_event("A", "u", {})
        monkeypatch.setattr(ImmutableAuditLog, "_instance", None)
        again = ImmutableAuditLog(fresh_log)
        assert again.last_hash == h
        again.log_event("B", "u", {})
        assert ImmutableAuditLog.verify_chain(fresh_log) is True

    def test_tampering_detected(self, fresh_log):
        log = ImmutableAuditLog(fresh_log)
        log.log_event("A", "alice", {"amt": 1})
        log.log_event("B", "alice", {"amt": 2})
        text = open(fresh_log).read().replace('"alice"', '"mallory"', 1)
        open(fresh_log, "w").write(text)
        assert ImmutableAuditLog.verify_chain(fresh_log) is False

    def test_broken_link_detected(self, fresh_log):
        log = ImmutableAuditLog(fresh_log)
        log.log_event("A", "u", {})
        log.log_event("B", "u", {})
        first, second = open(fresh_log).read().splitlines()
        open(fresh_log, "w").write(second + "\n")  # drop the first entry
        assert ImmutableAuditLog.verify_chain(fresh_log) is False

    def test_verify_missing_file_and_blank_lines(self, fresh_log):
        assert ImmutableAuditLog.verify_chain(fresh_log) is True
        ImmutableAuditLog(fresh_log).log_event("A", "u", {})
        with open(fresh_log, "a") as f:
            f.write("\n   \n")
        assert ImmutableAuditLog.verify_chain(fresh_log) is True

    def test_corrupt_last_line_falls_back_to_genesis(self, fresh_log):
        with open(fresh_log, "w") as f:
            f.write("not json\n")
        assert ImmutableAuditLog(fresh_log).last_hash == GENESIS

    def test_empty_file_falls_back_to_genesis(self, fresh_log):
        open(fresh_log, "w").close()
        assert ImmutableAuditLog(fresh_log).last_hash == GENESIS

    def test_single_line_file_resumes(self, fresh_log, monkeypatch):
        # exercises the seek-before-start (OSError) branch of _get_last_hash
        entry = {"payload": {}, "hash": "abc"}
        with open(fresh_log, "w") as f:
            f.write(json.dumps(entry))
        assert ImmutableAuditLog(fresh_log).last_hash == "abc"

    def test_helpers_write_expected_actions(self, fresh_log):
        ImmutableAuditLog(fresh_log)
        audit.log_model_change("m", "1.0", "bob", {"x": 1})
        audit.log_scoring_operation("m", "AAPL", 0.7, "bob")
        audit.log_scoring_operation("m", "MSFT", 0.1, "bob", {"why": "t"})
        rows = [json.loads(x)["payload"] for x in open(fresh_log)]
        assert [r["action"] for r in rows] == [
            "MODEL_CHANGE",
            "SCORING_OPERATION",
            "SCORING_OPERATION",
        ]
        assert rows[0]["details"] == {"model_name": "m", "version": "1.0", "changes": {"x": 1}}
        assert rows[1]["details"]["metadata"] == {}
        assert rows[2]["details"]["metadata"] == {"why": "t"}
        assert ImmutableAuditLog.verify_chain(fresh_log) is True
