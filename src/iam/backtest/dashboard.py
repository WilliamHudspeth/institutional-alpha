"""Lightweight zero-dependency HTTP server to run the Backtest Dashboard.

Serves backtest results from local cache/directories directly to the browser
without triggering CORS restrictions.
"""

import http.server
import logging
import socket
import socketserver
import webbrowser
from pathlib import Path

logger = logging.getLogger("DashboardServer")
logging.basicConfig(level=logging.INFO)


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """Custom request handler that serves APIs for backtest files alongside index.html."""

    def do_GET(self):
        # Resolve target paths
        results_dir = Path("data/results")
        calibration_path = Path("src/iam/arbitration/calibrated_reliabilities_empirical.json")

        # Routing
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()

            # Read dashboard HTML
            html_path = Path(__file__).parent / "dashboard.html"
            if html_path.exists():
                with open(html_path, encoding="utf-8") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            else:
                self.wfile.write(
                    b"<h1>Dashboard Asset (dashboard.html) Missing in src/iam/backtest/</h1>"
                )

        elif self.path == "/api/manifest":
            self._serve_file(results_dir / "manifest.json", "application/json")

        elif self.path == "/api/calibration":
            self._serve_file(calibration_path, "application/json")

        elif self.path == "/api/ic_by_horizon":
            self._serve_file(results_dir / "ic_by_horizon.csv", "text/csv")

        elif self.path == "/api/backtest_results":
            # Check CSV fallback first
            csv_path = results_dir / "backtest_results.csv"
            if csv_path.exists():
                self._serve_file(csv_path, "text/csv")
            else:
                self.send_error(404, "backtest_results.csv not found")
        else:
            # Fallback to default SimpleHTTPRequestHandler for static assets
            super().do_GET()

    def _serve_file(self, path: Path, content_type: str):
        if path.exists():
            self.send_response(200)
            self.send_header("Content-type", content_type)
            # Enable CORS for local testing stability
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with open(path, encoding="utf-8") as f:
                self.wfile.write(f.read().encode("utf-8"))
        else:
            self.send_error(404, f"File {path.name} not found locally.")


def find_free_port(start_port: int = 8080, max_attempts: int = 100) -> int:
    """Finds an available TCP port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find any available TCP port after {max_attempts} attempts.")


def start_dashboard_server(port: int = 8080, launch_browser: bool = True):
    """Starts the HTTP server and optionally launches the default browser."""
    # Ensure correct port is free
    free_port = find_free_port(port)

    # Configure socket server
    # Set allow_reuse_address to True to prevent 'Address already in use' errors
    socketserver.TCPServer.allow_reuse_address = True

    with socketserver.TCPServer(("127.0.0.1", free_port), DashboardHandler) as httpd:
        url = f"http://127.0.0.1:{free_port}"
        logger.info(f"🎯 Backtest Dashboard Server is running at: {url}")
        logger.info("📁 Serving historical observations and Bayesian calibrations dynamically.")
        logger.info("🛑 Press CTRL+C to terminate the dashboard server.")

        if launch_browser:
            # Open browser asynchronously
            try:
                webbrowser.open(url)
            except Exception as e:
                logger.warning(f"Could not open browser automatically: {e}")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("\n🛑 Server terminated by user. Exiting dashboard server.")
            httpd.server_close()


if __name__ == "__main__":
    start_dashboard_server()
