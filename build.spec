# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

block_cipher = None

ROOT_DIR = Path.cwd()
ffmpeg_path = str(ROOT_DIR / "ffmpeg.exe")
gallery_dl_path = str(ROOT_DIR / "gallery-dl.exe")
icon_path = str(ROOT_DIR / "icon.ico")  # Path to your icon file

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        (ffmpeg_path, '.'),
        (gallery_dl_path, '.')
    ],
    datas=[
        ('static', 'static'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'sqlite3'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HorizonDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_identity=None,
    icon=icon_path,  # <--- THIS INJECTS YOUR ICON INTO THE EXE
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HorizonDownloader',
)