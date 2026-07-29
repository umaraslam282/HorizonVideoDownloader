# -*- mode: python ; coding: utf-8 -*-
"""
Horizon Video Downloader v3 — PyInstaller Spec
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Build command:
    pyinstaller main.spec

Produces a one-folder distribution at dist/HorizonVideoDownloader/
containing the exe plus all bundled assets.

IMPORTANT: Before building, place these files in the project root:
  - yt-dlp.exe    (from https://github.com/yt-dlp/yt-dlp/releases)
  - deno.exe      (from https://github.com/denoland/deno/releases)
"""

import os

block_cipher = None
project_root = os.path.abspath(".")

# ── Bundled binaries ──────────────────────────────────────────────
# These are placed alongside the exe so config.py can inject them
# into PATH at runtime.
bundled_binaries = []
for binary_name in ("yt-dlp.exe", "deno.exe"):
    binary_path = os.path.join(project_root, binary_name)
    if os.path.exists(binary_path):
        bundled_binaries.append((binary_path, "."))

# ── Static frontend assets ───────────────────────────────────────
# The entire static/ directory is included as data so FastAPI can
# serve it via StaticFiles.
static_dir = os.path.join(project_root, "static")
bundled_data = []
if os.path.isdir(static_dir):
    bundled_data.append((static_dir, "static"))

# ── Analysis ─────────────────────────────────────────────────────
a = Analysis(
    ["main.py"],
    pathex=[project_root],
    binaries=bundled_binaries,
    datas=bundled_data,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "xmlrpc",
        "pydoc",
        "doctest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── Build ─────────────────────────────────────────────────────────
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HorizonVideoDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window — the app runs as a GUI tray/browser app
    icon=os.path.join(project_root, "static", "assets", "icon.ico")
    if os.path.exists(os.path.join(project_root, "static", "assets", "icon.ico"))
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HorizonVideoDownloader",
)
