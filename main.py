"""
Horizon Video Downloader v3 — Entry Point
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Startup sequence:
  1. Import config (triggers PATH injection for deno.exe / yt-dlp.exe)
  2. Configure structured logging
  3. Resolve an available port (80 → 8080 → 8090 → 9000 → ephemeral)
  4. Start Uvicorn in a daemon thread
  5. Wait for server readiness via /health probe
  6. Auto-open the default web browser
  7. Block the main thread (Ctrl+C to exit)

This module is the single entry point for both development
(python main.py) and the PyInstaller-frozen executable.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
import webbrowser

import urllib.request
import urllib.error

import uvicorn

# config.py is imported first — its module-level code injects the
# bundled binary directory into os.environ["PATH"] so yt-dlp can
# auto-discover deno.exe without requiring Node.js.
from config import APP_NAME, APP_VERSION, HOST, find_available_port
from server import create_app


def configure_logging() -> None:
    """Set up structured logging with clean formatting."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s │ %(name)-14s │ %(levelname)-7s │ %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # Suppress noisy uvicorn access logs (each WS frame = a log line)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # Keep uvicorn error logs visible
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)


def wait_for_server(url: str, timeout: float = 15.0, interval: float = 0.15) -> bool:
    """
    Poll the /health endpoint until the server is ready.
    Returns True if the server responded within the timeout.
    """
    health_url = f"{url}/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(interval)
    return False


def main() -> None:
    """Application entry point."""
    configure_logging()
    logger = logging.getLogger("hvd.main")

    # ── Banner ────────────────────────────────────────────────
    logger.info(f"{'═' * 52}")
    logger.info(f"  {APP_NAME} v{APP_VERSION}")
    logger.info(f"{'═' * 52}")

    # ── Resolve port ──────────────────────────────────────────
    port = find_available_port()
    url = f"http://{HOST}:{port}"
    logger.info(f"Port resolved: {port}")

    # ── Create app ────────────────────────────────────────────
    app = create_app()

    # ── Start Uvicorn in daemon thread ────────────────────────
    server_thread = threading.Thread(
        target=lambda: uvicorn.run(
            app,
            host=HOST,
            port=port,
            log_level="warning",
            # Single worker — all state is in-memory (no need for multi-worker)
            workers=1,
        ),
        name="hvd-uvicorn",
        daemon=True,
    )
    server_thread.start()
    logger.info("Uvicorn server thread started")

    # ── Wait for readiness ────────────────────────────────────
    if wait_for_server(url):
        logger.info(f"Server ready at {url}")
    else:
        logger.error(
            f"Server failed to respond within 15s at {url}. "
            "Check for port conflicts or firewall issues."
        )
        sys.exit(1)

    # ── Open browser ──────────────────────────────────────────
    logger.info(f"Opening browser → {url}")
    webbrowser.open(url)

    # ── Block main thread ─────────────────────────────────────
    # The daemon thread keeps Uvicorn running. We block here so
    # the process stays alive. Ctrl+C raises KeyboardInterrupt
    # and exits cleanly (daemon threads auto-terminate).
    logger.info("Press Ctrl+C to stop the server.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down…")


if __name__ == "__main__":
    main()
