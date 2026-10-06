"""Local, read-only HTTP server for the backtest results dashboard.

Serves a fixed set of routes (the page and four data endpoints) and nothing else:
any other path is a 404. It binds to loopback only. JSON is re-serialised so that
NaN / Infinity (invalid JSON) reach the browser as ``null``, never as a number.
"""

from __future__ import annotations

import http.server
import json
import logging
import math
import socket
import webbrowser
from pathlib import Path
from typing import Any

from iam.backtest.config import BacktestConfig

logger = logging.getLogger(__name__)

# Loopback only: the dashboard is a local developer tool, not a network service.
BIND_HOST = "127.0.0.1"

_HTML_PATH = Path(__file__).parent / "dashboard.html"
# Same location as iam.arbitration.reliability_loader (package-relative, not CWD-relative).
_CALIBRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "arbitration"
    / "calibrated_reliabilities_empirical.json"
)


def default_calibration_path() -> Path:
    """Package-relative path of the empirical calibration JSON."""
    return _CALIBRATION_PATH


def sanitize_json(value: Any) -> Any:
    """Recursively replace non-finite floats (NaN, +/-Infinity) with None."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_json(v) for v in value]
    return value


def make_handler(
    results_dir: Path | None = None,
    calibration_path: Path | None = None,
    html_path: Path | None = None,
) -> type[http.server.BaseHTTPRequestHandler]:
    """Build a request handler class bound to the given locations.

    ``results_dir`` defaults to the backtest config's results directory.
    """
    res_dir = Path(results_dir) if results_dir is not None else BacktestConfig().results_dir
    calib = Path(calibration_path) if calibration_path is not None else _CALIBRATION_PATH
    html = Path(html_path) if html_path is not None else _HTML_PATH

    # route -> (file, content type, is_json)
    routes: dict[str, tuple[Path, str, bool]] = {
        "/": (html, "text/html; charset=utf-8", False),
        "/index.html": (html, "text/html; charset=utf-8", False),
        "/api/manifest": (res_dir / "manifest.json", "application/json", True),
        "/api/calibration": (calib, "application/json", True),
        "/api/ic_by_horizon": (res_dir / "ic_by_horizon.csv", "text/csv; charset=utf-8", False),
        "/api/backtest_results": (
            res_dir / "backtest_results.csv",
            "text/csv; charset=utf-8",
            False,
        ),
    }

    class DashboardHandler(http.server.BaseHTTPRequestHandler):
        """Whitelist-only handler: unknown paths are 404, never a directory listing."""

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            route = self.path.split("?", 1)[0].split("#", 1)[0]
            entry = routes.get(route)
            if entry is None:
                self.send_error(404, "Not found")
                return
            path, content_type, is_json = entry
            try:
                raw = path.read_bytes()
            except OSError:
                self.send_error(404, f"{path.name} not found")
                return
            if is_json:
                try:
                    # json.loads accepts the NaN literal that json.dump writes.
                    raw = json.dumps(sanitize_json(json.loads(raw))).encode("utf-8")
                except ValueError:
                    logger.warning("Invalid JSON in %s", path)
                    self.send_error(500, f"{path.name} is not valid JSON")
                    return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            logger.debug("%s - %s", self.address_string(), format % args)

    return DashboardHandler


def find_free_port(start_port: int = 8080, max_attempts: int = 100) -> int:
    """Return the first bindable loopback TCP port at or above ``start_port``."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((BIND_HOST, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find any available TCP port after {max_attempts} attempts.")


def start_dashboard_server(
    port: int = 8080, launch_browser: bool = True, results_dir: Path | None = None
) -> None:
    """Run the dashboard until interrupted (Ctrl+C)."""
    free_port = find_free_port(port)
    handler = make_handler(results_dir=results_dir)
    with http.server.ThreadingHTTPServer((BIND_HOST, free_port), handler) as httpd:
        url = f"http://{BIND_HOST}:{free_port}"
        logger.info("Backtest dashboard running at %s (Ctrl+C to stop)", url)
        print(f"Backtest dashboard running at {url} (Ctrl+C to stop)")
        if launch_browser:
            try:
                webbrowser.open(url)
            except Exception as e:  # browser launch is best-effort
                logger.warning("Could not open browser automatically: %s", e)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Dashboard server stopped by user.")


if __name__ == "__main__":
    start_dashboard_server()
