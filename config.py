"""
Horizon Video Downloader v3 — Configuration & Path Resolution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Handles PyInstaller frozen-state detection, bundled binary PATH
injection (yt-dlp + deno), port resolution, and global constants.

Imported first by main.py — the PATH mutation at module level
ensures every subprocess inherits the bundled binaries.
"""

import os
import socket
import sys
from pathlib import Path

# ── Application Metadata ──────────────────────────────────────────────
APP_NAME = "Horizon Video Downloader"
APP_VERSION = "5.0.0"
APP_ID = "hvd"

# ── Runtime Path Resolution ───────────────────────────────────────────
# PyInstaller sets sys.frozen = True and unpacks to sys._MEIPASS.
# In dev mode we resolve relative to this file's directory.
IS_FROZEN: bool = getattr(sys, "frozen", False)

BUNDLE_DIR: Path = (
    Path(sys._MEIPASS)  # type: ignore[attr-defined]
    if IS_FROZEN
    else Path(__file__).resolve().parent
)

RUNTIME_DIR: Path = (
    Path(sys.executable).resolve().parent
    if IS_FROZEN
    else Path(__file__).resolve().parent
)

# ── PATH Injection (runs on import) ──────────────────────────────────
# Prepend the bundle directory to PATH so yt-dlp can auto-discover
# deno.exe (YouTube JS interpreter) and any other bundled tools.
os.environ["PATH"] = str(BUNDLE_DIR) + os.pathsep + os.environ.get("PATH", "")

# ── Binary Paths ─────────────────────────────────────────────────────
YTDLP_PATH: str = str(BUNDLE_DIR / "yt-dlp.exe") if IS_FROZEN else "yt-dlp"
FFMPEG_PATH: str = str(BUNDLE_DIR / "ffmpeg.exe")

# ── Static Assets ────────────────────────────────────────────────────
STATIC_DIR: str = str(BUNDLE_DIR / "static")

# ── Download Defaults ────────────────────────────────────────────────
DEFAULT_DOWNLOAD_DIR: str = str(Path.home() / "Downloads")
MAX_CONCURRENT_DOWNLOADS: int = 10
OUTPUT_TEMPLATE: str = "%(title).200s.%(ext)s"

# ── Network ──────────────────────────────────────────────────────────
PREFERRED_PORTS: list[int] = [80, 8080, 8090, 9000]
HOST: str = "127.0.0.1"

# ── yt-dlp Resilience Flags ─────────────────────────────────────────
# Injected into every yt-dlp subprocess for network fault tolerance.
YTDLP_RESILIENCE_FLAGS: list[str] = [
    "--continue",
    "--retries", "infinite",
    "--fragment-retries", "infinite",
    "--retry-sleep", "2",
    "--ignore-errors",
]

# ── Windows Subprocess Flags ─────────────────────────────────────────
# Prevents console windows from flashing when spawning yt-dlp.
SUBPROCESS_FLAGS: int = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


def find_available_port() -> int:
    """
    Probe preferred ports in order and return the first available one.
    Falls back to an OS-assigned ephemeral port if none are free.
    """
    for port in PREFERRED_PORTS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((HOST, port))
                return port
        except OSError:
            continue

    # Fallback: let the OS pick an ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]
