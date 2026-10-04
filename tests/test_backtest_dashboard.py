"""Backtest dashboard server: route whitelist, honest JSON, static-page guards."""

from __future__ import annotations

import http.client
import json
import re
import socket
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from typer.testing import CliRunner

from iam.backtest import dashboard
from iam.backtest.cli import app

HTML_PATH = Path(dashboard.__file__).parent / "dashboard.html"


@pytest.fixture
def served(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    (results / "manifest.json").write_text('{"git_sha": "abc1234"}', encoding="utf-8")
    (results / "ic_by_horizon.csv").write_text("date,ic\n2020-01-31,0.05\n", encoding="utf-8")
    (results / "backtest_results.csv").write_text("date,ic\n2020-01-31,0.05\n", encoding="utf-8")
    calib = tmp_path / "calib.json"
    calib.write_text(
        '{"empirical_ic": {"mean": NaN, "n_obs": 59}, "bayesian_calibration": '
        '{"posterior_ic": NaN, "reliability": 0.95}}',
        encoding="utf-8",
    )
    # A secret file next to the results that must never be reachable.
    (tmp_path / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
    handler = dashboard.make_handler(results_dir=results, calibration_path=calib)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1], results
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.getheader("Content-Type"), resp.read(), resp
    finally:
        conn.close()


@pytest.mark.parametrize(
    "route,ctype,expected",
    [
        ("/api/manifest", "application/json", b'{"git_sha": "abc1234"}'),
        ("/api/ic_by_horizon", "text/csv", b"date,ic\n2020-01-31,0.05\n"),
        ("/api/backtest_results", "text/csv", b"date,ic\n2020-01-31,0.05\n"),
    ],
)
def test_api_routes_return_file_content(served, route, ctype, expected):
    port, _ = served
    status, content_type, body, _ = _get(port, route)
    assert status == 200
    assert content_type.startswith(ctype)
    assert body.replace(b"\r\n", b"\n") == expected


@pytest.mark.parametrize("route", ["/", "/index.html"])
def test_index_serves_dashboard_html(served, route):
    port, _ = served
    status, content_type, body, _ = _get(port, route)
    assert status == 200
    assert content_type.startswith("text/html")
    assert body == HTML_PATH.read_bytes()


@pytest.mark.parametrize("route", ["/api/manifest", "/api/ic_by_horizon", "/api/backtest_results"])
def test_missing_file_is_404(served, route):
    port, results = served
    for f in results.iterdir():
        f.unlink()
    status, _, _, _ = _get(port, route)
    assert status == 404


@pytest.mark.parametrize(
    "path",
    [
        "/pyproject.toml",
        "/../README.md",
        "/secret.txt",
        "/%2e%2e/secret.txt",
        "/api/manifest/extra",
        "/api/",
        "/index.html/",
        "/static/anything",
    ],
)
def test_unknown_path_is_404(served, path):
    port, _ = served
    status, _, body, _ = _get(port, path)
    assert status == 404
    assert b"TOP SECRET" not in body


def test_query_string_does_not_change_routing(served):
    port, _ = served
    assert _get(port, "/api/manifest?x=1")[0] == 200
    assert _get(port, "/secret.txt?/api/manifest")[0] == 404


def test_calibration_nan_becomes_null_and_is_valid_json(served):
    port, _ = served
    status, content_type, body, _ = _get(port, "/api/calibration")
    assert status == 200
    assert content_type.startswith("application/json")
    data = json.loads(body)  # would raise on a literal NaN
    assert data["empirical_ic"]["mean"] is None
    assert data["empirical_ic"]["n_obs"] == 59
    assert data["bayesian_calibration"]["posterior_ic"] is None
    assert data["bayesian_calibration"]["reliability"] == 0.95
    assert b"NaN" not in body


def test_invalid_json_file_is_not_served_as_valid(served, tmp_path):
    port, results = served
    (results / "manifest.json").write_text("{not json", encoding="utf-8")
    status, _, _, _ = _get(port, "/api/manifest")
    assert status == 500


def test_no_cors_header(served):
    port, _ = served
    _, _, _, resp = _get(port, "/api/manifest")
    assert resp.getheader("Access-Control-Allow-Origin") is None


def test_sanitize_converts_non_finite_recursively():
    out = dashboard.sanitize_json(
        {"a": float("nan"), "b": [float("inf"), -float("inf"), 1.5], "c": {"d": "x"}}
    )
    assert out == {"a": None, "b": [None, None, 1.5], "c": {"d": "x"}}


def test_default_calibration_path_is_package_relative():
    path = dashboard.default_calibration_path()
    assert path.is_absolute()
    assert path.name == "calibrated_reliabilities_empirical.json"
    assert path.parent.name == "arbitration"
    assert path.parent.parent.name == "iam"


def test_find_free_port_returns_bindable_port():
    port = dashboard.find_free_port(18080)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_find_free_port_skips_busy_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        busy = s.getsockname()[1]
        s.listen(1)
        assert dashboard.find_free_port(busy) != busy


def test_server_binds_loopback_only():
    assert dashboard.BIND_HOST == "127.0.0.1"


def test_import_does_not_configure_root_logging():
    src = Path(dashboard.__file__).read_text(encoding="utf-8")
    assert "basicConfig" not in src


def test_html_has_no_zero_fallbacks_on_data_fields():
    html = HTML_PATH.read_text(encoding="utf-8")
    assert not re.search(r"\|\|\s*0\b", html), "`|| 0` fabricates a zero for missing data"
    assert not re.search(r"\?\s*[^:\n]+:\s*0\s*\)", html), "ternary default of 0"


def test_html_declares_honest_missing_states():
    html = HTML_PATH.read_text(encoding="utf-8")
    assert "n/a" in html
    assert "Insufficient data" in html
    assert "no measured IC (n_obs = " in html
    assert "not supported by data" in html


def test_html_pins_chartjs_version():
    html = HTML_PATH.read_text(encoding="utf-8")
    assert re.search(r"cdn\.jsdelivr\.net/npm/chart\.js@\d+\.\d+\.\d+", html)


def test_cli_dashboard_command_exists():
    result = CliRunner().invoke(app, ["dashboard", "--help"])
    assert result.exit_code == 0
    assert "--port" in result.output
    assert "--no-browser" in result.output
