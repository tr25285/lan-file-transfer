# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path.cwd()
VERSION_FILE = ROOT / "version_info.txt"

a = Analysis(
    [str(ROOT / "lan_transfer" / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "lan_transfer" / "static"), "lan_transfer/static")],
    hiddenimports=["PIL._tkinter_finder"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LANFileTransfer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    version=str(VERSION_FILE),
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
