# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-folder Windows build for TubeClipper."""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

EXCLUDE_QT = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtPositioning", "PySide6.QtPrintSupport",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtSerialPort", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtSvgWidgets",
    "PySide6.QtTextToSpeech", "PySide6.QtSensors", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtSpatialAudio",
    "PySide6.QtHttpServer", "PySide6.QtGraphs", "PySide6.QtLocation",
]

ffmpeg_binaries = [
    (os.path.join("ffmpeg", name), "ffmpeg")
    for name in ("ffmpeg.exe", "ffprobe.exe")
]

a = Analysis(
    ["TubeClipper.py"],
    pathex=[os.path.abspath(".")],
    binaries=ffmpeg_binaries,
    datas=[
        ("assets/TubeClipper.ico", "assets"),
        ("assets/logo.png", "assets"),
        ("assets/logo_256.png", "assets"),
        ("assets/check.png", "assets"),
    ] + collect_data_files("yt_dlp"),
    hiddenimports=collect_submodules("yt_dlp") + [
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.QtNetwork", "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDE_QT + ["tkinter", "matplotlib", "scipy", "pandas", "IPython"],
    noarchive=False,
)

# Codex's document toolchain adds Poppler's bin directory to PATH. PyInstaller
# follows DLLs it sees there and would otherwise copy Poppler's private ICU and
# OpenSSL builds beside Qt, where Windows loads the incompatible copies first.
# A normal user's shell does not have this path, but filtering it here keeps the
# build reproducible in development workspaces that do.
a.binaries = [entry for entry in a.binaries
              if ".cache\\codex-runtimes" not in entry[1].lower()]

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="TubeClipper", console=False, debug=False, strip=False, upx=False,
    icon="assets/TubeClipper.ico",
)

exe_check = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="TubeClipper-check", console=True, debug=False, strip=False, upx=False,
    icon="assets/TubeClipper.ico",
)

coll = COLLECT(
    exe, exe_check, a.binaries, a.datas,
    strip=False, upx=False, name="TubeClipper",
)
