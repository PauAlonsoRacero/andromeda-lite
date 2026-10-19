"""Windows: el .exe nuevo cargaba la interfaz de una versión antigua (v2.12.0-beta).

Tres vías, las tres corregidas:
  1. Otra Andromeda en el puerto: cualquier respuesta HTTP (incluso 404) se daba
     por "backend listo" y la ventana cargaba la interfaz de la otra.
  2. setdefault de ANDROMEDA_FRONTEND_DIST: una variable antigua del sistema ganaba.
  3. index.html sin cabeceras anti-caché: WebView2 podía reutilizar uno antiguo.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_SCRIPT = r'''
import sys, json, threading, http.server
sys.path.insert(0, ROOT)
import desktop as d
res = {}
def servir(codigo, cuerpo):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(codigo); self.end_headers()
            if cuerpo is not None: self.wfile.write(json.dumps(cuerpo).encode())
        def log_message(self, *a): pass
    s = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, s.server_address[1]
for nombre, codigo, cuerpo in (("vieja", 404, None), ("otra", 200, {"instance": "x"}),
                               ("nuestra", 200, "PROPIA")):
    if cuerpo == "PROPIA": cuerpo = {"instance": d.INSTANCE_ID}
    s, p = servir(codigo, cuerpo)
    d.PORT = p; d._backend_error.clear()
    res[nombre] = [d.wait_for_backend(timeout=5), d._port_is_free(p)]
    s.shutdown()
res["dist_forzado"] = __import__("os").environ["ANDROMEDA_FRONTEND_DIST"] == str(d.DIST)
open(OUT, "w").write(json.dumps(res))
'''


def test_desktop_rejects_another_andromeda_on_the_port(tmp_path):
    out = tmp_path / "r.json"
    codigo = f"ROOT = {str(ROOT)!r}\nOUT = {str(out)!r}\n" + _SCRIPT
    env = {**os.environ, "HOME": str(tmp_path), "APPDATA": str(tmp_path), "XDG_DATA_HOME": str(tmp_path),
           "ANDROMEDA_FRONTEND_DIST": "/ruta/de/una/version/antigua"}
    subprocess.run([sys.executable, "-c", codigo], env=env, capture_output=True, timeout=90, cwd=str(tmp_path))
    r = json.loads(out.read_text())
    assert r["vieja"] == [False, False], "cargaría la interfaz de la versión antigua"
    assert r["otra"] == [False, False]
    assert r["nuestra"][0] is True
    assert r["dist_forzado"] is True, "una variable del sistema no puede cambiar la interfaz"


def test_instance_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANDROMEDA_INSTANCE_ID", "abc123")
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        d = c.get("/api/health/instance").json()
        assert d["instance"] == "abc123" and d["version"]


def test_index_html_is_never_cached_and_no_path_traversal(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>nueva</html>", encoding="utf-8")
    (tmp_path / "secreto.txt").write_text("no", encoding="utf-8")
    monkeypatch.setenv("ANDROMEDA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ANDROMEDA_FRONTEND_DIST", str(dist))
    from fastapi.testclient import TestClient
    from app import create_app
    with TestClient(create_app()) as c:
        r = c.get("/")
        assert "no-store" in r.headers.get("cache-control", "")
        r = c.get("/cualquier/ruta")
        assert "nueva" in r.text and "no-store" in r.headers.get("cache-control", "")
        assert "no" != c.get("/..%2Fsecreto.txt").text


def test_webview_loads_a_unique_url_per_launch():
    src = (ROOT / "desktop.py").read_text(encoding="utf-8")
    assert 'window.load_url(f"http://127.0.0.1:{PORT}/?v={INSTANCE_ID}")' in src
    assert 'os.environ["ANDROMEDA_FRONTEND_DIST"] = str(DIST)' in src


_SCRIPT_CACHE = r'''
import sys, os, json
sys.path.insert(0, ROOT)
import desktop as d
p = os.path.join(ST, "EBWebView", "Default")
for x in ("Cache", "Code Cache", "Service Worker", "GPUCache", "Local Storage", "IndexedDB"):
    os.makedirs(os.path.join(p, x), exist_ok=True)
r = {"primera": d.limpiar_cache_webview(ST), "quedan": sorted(os.listdir(p)),
     "segunda": d.limpiar_cache_webview(ST), "js": d.script_comprobar_interfaz()}
open(OUT, "w").write(json.dumps(r))
'''


def test_webview_caches_are_cleared_for_a_new_build_keeping_local_storage(tmp_path):
    """El perfil del webview es el mismo para todas las versiones: sus cachés
    (y Service Workers) servían la interfaz de junio con el servidor nuevo."""
    out, st = tmp_path / "r.json", tmp_path / "webview"
    codigo = f"ROOT = {str(ROOT)!r}\nOUT = {str(out)!r}\nST = {str(st)!r}\n" + _SCRIPT_CACHE
    env = {**os.environ, "HOME": str(tmp_path), "APPDATA": str(tmp_path), "XDG_DATA_HOME": str(tmp_path)}
    subprocess.run([sys.executable, "-c", codigo], env=env, capture_output=True, timeout=90, cwd=str(tmp_path))
    r = json.loads(out.read_text())
    assert r["primera"] == 4 and r["quedan"] == ["IndexedDB", "Local Storage"]
    assert r["segunda"] == 0, "no debe borrar en cada arranque, solo al cambiar la interfaz"
    if (ROOT / "frontend" / "dist" / "index.html").exists():
        assert "serviceWorker" in r["js"] and "location.replace" in r["js"]


def test_frontend_unregisters_service_workers():
    src = (ROOT / "frontend" / "src" / "index.jsx").read_text(encoding="utf-8")
    assert "getRegistrations" in src and "unregister" in src
