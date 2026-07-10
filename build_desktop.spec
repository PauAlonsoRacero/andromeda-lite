# -*- mode: python ; coding: utf-8 -*-
"""
build_desktop.spec — PyInstaller spec para Andromeda Desktop.
Funciona en Windows (.exe) y macOS (.app): PyInstaller usa la plataforma actual.
Compilar:  pyinstaller build_desktop.spec --noconfirm
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(ROOT / "config"), "config"),
    (str(ROOT / "backend" / "app" / "cloud" / "license_public.pem"), "app/cloud"),
]

binaries = []

hiddenimports = [
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    "app", "yaml",
    "jwt", "cryptography",
    "docx", "openpyxl", "reportlab", "reportlab.platypus", "reportlab.lib",
    # pywebview: el módulo base
    "webview",
]

# CRÍTICO: httpx hace imports perezosos de sus transportes y dependencias
# (httpcore, h11, anyio, sniffio, certifi). El análisis estático de PyInstaller
# los pierde y, en el .exe, TODA llamada httpx falla en silencio → "Ollama no
# detectado" y el chat tampoco responde. collect_all empaqueta el árbol completo.
for _pkg in ("httpx", "httpcore", "h11", "anyio", "sniffio", "certifi"):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        hiddenimports.append(_pkg)
hiddenimports += collect_submodules("httpx") + collect_submodules("httpcore")

# Backend de ventana específico de cada plataforma. Sin estos, PyInstaller
# puede no empaquetar el motor correcto y la ventana saldría en blanco.
if sys.platform == "win32":
    # Windows 11 usa EdgeChromium (WebView2) vía pythonnet (clr).
    hiddenimports += [
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr",
    ]
elif sys.platform == "darwin":
    hiddenimports += ["webview.platforms.cocoa"]
else:
    hiddenimports += ["webview.platforms.gtk", "webview.platforms.qt"]

a = Analysis(
    ["desktop.py"],
    pathex=[str(ROOT / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Andromeda",
    console=False,                 # SIN consola: app de escritorio pura
    icon=str(ROOT / "andromeda.ico") if sys.platform == "win32" else str(ROOT / "andromeda.icns"),
)

coll = COLLECT(exe, a.binaries, a.datas, name="Andromeda")

# macOS: envolver en .app bundle nativo
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Andromeda.app",
        icon=str(ROOT / "andromeda.icns"),
        bundle_identifier="com.pau.andromeda",
        info_plist={
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "CFBundleDisplayName": "Andromeda",
            "CFBundleName": "Andromeda",
            # WKWebView: permitir http://127.0.0.1 (backend local)
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
    )
