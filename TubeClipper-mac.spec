# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller macOS app bundle for TubeClipper."""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

a = Analysis(
    ["TubeClipper.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=[
        ("assets/TubeClipper.icns", "assets"),
        ("assets/logo.png", "assets"),
        ("assets/logo_256.png", "assets"),
        ("assets/check.png", "assets"),
    ] + collect_data_files("yt_dlp"),
    hiddenimports=collect_submodules("yt_dlp") + [
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.QtNetwork", "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="TubeClipper", console=False, debug=False, strip=False, upx=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
               name="TubeClipper")
app = BUNDLE(
    coll,
    name="TubeClipper.app",
    icon="assets/TubeClipper.icns",
    bundle_identifier="com.pierrekostantine.tubeclipper",
    version=os.environ.get("TUBECLIPPER_VERSION", "0.0.0"),
    info_plist={
        "CFBundleName": "TubeClipper",
        "CFBundleDisplayName": "TubeClipper",
        "CFBundleShortVersionString": os.environ.get("TUBECLIPPER_VERSION", "0.0.0"),
        "CFBundleVersion": os.environ.get("TUBECLIPPER_VERSION", "0.0.0"),
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "LSMinimumSystemVersion": "11.0",
        "LSApplicationCategoryType": "public.app-category.video",
    },
)
