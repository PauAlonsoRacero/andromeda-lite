"""
cloud/client.py — Cliente de Andromeda Cloud dentro de la app de escritorio.

Responsabilidades:
  - Registro y login contra el servicio cloud (cualquiera que se registre en la
    app queda registrado en el cloud).
  - Guardar la sesión y la licencia firmada en local (~/.andromeda).
  - Validar la licencia OFFLINE con la clave pública incrustada, de modo que Pro
    funcione sin conexión una vez activado.
  - Degradar con elegancia: si no hay red, se usa la última licencia válida
    guardada; si no hay licencia válida, el plan es 'free'.

La URL del servicio se toma de ANDROMEDA_CLOUD_URL (por defecto el servicio
oficial). En desarrollo se apunta a http://localhost:8787.
"""
from __future__ import annotations

import os
import json
import time
from pathlib import Path

import httpx

try:
    import jwt  # PyJWT
except Exception:  # pragma: no cover
    jwt = None

CLOUD_URL = os.environ.get("ANDROMEDA_CLOUD_URL", "https://api.andromeda.app").rstrip("/")
_DATA_DIR = Path(os.environ.get("ANDROMEDA_DATA_DIR") or os.path.expanduser("~/.andromeda"))
_SESSION_FILE = _DATA_DIR / "cloud_session.json"
_LICENSE_FILE = _DATA_DIR / "cloud_license.jwt"
_PUBKEY_FILE = Path(__file__).with_name("license_public.pem")

_TIMEOUT = 12.0


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Sesión local ──────────────────────────────────────────────────────────────
def load_session() -> dict | None:
    try:
        return json.loads(_SESSION_FILE.read_text())
    except Exception:
        return None


def save_session(data: dict) -> None:
    _ensure_dir()
    _SESSION_FILE.write_text(json.dumps(data))


def clear_session() -> None:
    for f in (_SESSION_FILE, _LICENSE_FILE):
        try:
            f.unlink()
        except Exception:
            pass


# ── Validación de licencia OFFLINE ──────────────────────────────────────────
def verify_local_license() -> dict | None:
    """Valida la licencia guardada con la clave pública. Devuelve el payload
    (plan, email, exp...) si es válida y no ha caducado; si no, None."""
    if jwt is None:
        return None
    try:
        token = _LICENSE_FILE.read_text().strip()
        pub = _PUBKEY_FILE.read_text()
        payload = jwt.decode(token, pub, algorithms=["RS256"], issuer="andromeda-cloud")
        return payload
    except Exception:
        return None


def current_plan() -> str:
    """Plan efectivo según la licencia local válida. 'pro' o 'free'."""
    payload = verify_local_license()
    if payload and payload.get("plan") == "pro":
        return "pro"
    return "free"


# ── Llamadas al servicio ──────────────────────────────────────────────────────
def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register(email: str, password: str, display_name: str = "", country: str = "") -> dict:
    """Registra al usuario en el cloud y guarda la sesión. Lanza en error."""
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(f"{CLOUD_URL}/auth/register", json={
            "email": email, "password": password,
            "display_name": display_name, "country": country,
        })
    if r.status_code >= 400:
        raise CloudError(r.json().get("detail", "Error al registrar"))
    data = r.json()
    save_session({"token": data["token"], "user": data["user"], "ts": time.time()})
    sync_license(data["token"])
    return data["user"]


def login(email: str, password: str) -> dict:
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(f"{CLOUD_URL}/auth/login", json={"email": email, "password": password})
    if r.status_code >= 400:
        raise CloudError(r.json().get("detail", "Email o contraseña incorrectos"))
    data = r.json()
    save_session({"token": data["token"], "user": data["user"], "ts": time.time()})
    sync_license(data["token"])
    return data["user"]


def logout() -> None:
    sess = load_session()
    if sess:
        try:
            with httpx.Client(timeout=_TIMEOUT) as c:
                c.post(f"{CLOUD_URL}/auth/logout", headers=_auth_headers(sess["token"]))
        except Exception:
            pass
    clear_session()


def sync_license(token: str | None = None) -> str:
    """Descarga la licencia actual del cloud y la guarda. Devuelve el plan.
    Si no hay red, conserva la licencia local existente."""
    sess = load_session()
    tok = token or (sess["token"] if sess else None)
    if not tok:
        return "free"
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.get(f"{CLOUD_URL}/licenses/current", headers=_auth_headers(tok))
        if r.status_code == 200:
            data = r.json()
            if data.get("license"):
                _ensure_dir()
                _LICENSE_FILE.write_text(data["license"])
            else:
                # Sin licencia activa → borrar la local (volvió a free)
                try:
                    _LICENSE_FILE.unlink()
                except Exception:
                    pass
    except Exception:
        # Sin red: nos quedamos con la licencia local (validación offline)
        pass
    return current_plan()


def refresh_profile() -> dict | None:
    """Revalida la sesión contra el cloud y actualiza el plan. Si el token
    caducó, limpia la sesión."""
    sess = load_session()
    if not sess:
        return None
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.get(f"{CLOUD_URL}/auth/me", headers=_auth_headers(sess["token"]))
        if r.status_code == 401:
            clear_session()
            return None
        if r.status_code == 200:
            user = r.json()["user"]
            sess["user"] = user
            save_session(sess)
            sync_license(sess["token"])
            return user
    except Exception:
        # Sin red: devolvemos lo guardado
        return sess.get("user")
    return sess.get("user")


def start_checkout() -> str | None:
    """Pide al cloud una URL de pago de Stripe para suscribirse a Pro."""
    sess = load_session()
    if not sess:
        return None
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.post(f"{CLOUD_URL}/billing/checkout", headers=_auth_headers(sess["token"]))
    if r.status_code == 200:
        return r.json().get("checkout_url")
    return None


def export_data() -> dict | None:
    """Descarga todos los datos del usuario (RGPD portabilidad)."""
    sess = load_session()
    if not sess:
        return None
    with httpx.Client(timeout=_TIMEOUT) as c:
        r = c.get(f"{CLOUD_URL}/gdpr/export", headers=_auth_headers(sess["token"]))
    return r.json() if r.status_code == 200 else None


def delete_account() -> bool:
    """Borra la cuenta y todos los datos (RGPD olvido). Limpia la sesión local."""
    sess = load_session()
    if not sess:
        return False
    try:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.delete(f"{CLOUD_URL}/gdpr/account", headers=_auth_headers(sess["token"]))
        ok = r.status_code == 200
    except Exception:
        ok = False
    if ok:
        clear_session()
    return ok


class CloudError(Exception):
    pass
