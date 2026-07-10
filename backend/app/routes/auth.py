"""
auth.py — Autenticación local de Andromeda (estilo "inicia sesión para entrar").

Diseño:
  - Usuarios en SQLite (ANDROMEDA_DATA_DIR/users.db), contraseña con
    PBKDF2-HMAC-SHA256 (210k iteraciones) + salt aleatoria por usuario.
  - Sesiones con token aleatorio de 256 bits guardado HASHEADO en BD
    (robar la BD no da tokens válidos). Expiran a los 30 días. Revocables.
  - El gate se activa con ANDROMEDA_AUTH_REQUIRED=1 (el .exe/.app lo activan;
    en Docker es opcional). Sin usuarios creados, el primer registro es libre.
  - Campo `plan` (free/pro) preparado para suscripciones futuras.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

_ITER = 210_000
_SESSION_TTL = 30 * 24 * 3600


def _db_path() -> Path:
    d = Path(os.environ.get("ANDROMEDA_DATA_DIR", "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "users.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_db_path())
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            salt BLOB NOT NULL,
            pwhash BLOB NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS profiles (
            user_id INTEGER PRIMARY KEY,
            display_name TEXT DEFAULT '',
            email TEXT DEFAULT '',
            location TEXT DEFAULT '',
            organization TEXT DEFAULT '',
            updated_at REAL DEFAULT 0
        );
    """)
    return c


def _hash_pw(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def auth_required() -> bool:
    return os.environ.get("ANDROMEDA_AUTH_REQUIRED") == "1"


def current_user(request: Request) -> dict | None:
    """Devuelve {id, username, plan} si el token de la petición es válido."""
    token = request.headers.get("X-Andromeda-Token") or ""
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        return None
    with _conn() as c:
        row = c.execute(
            "SELECT u.id, u.username, u.plan, s.expires_at FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            (_hash_token(token),),
        ).fetchone()
    if not row or row["expires_at"] < time.time():
        return None
    return {"id": row["id"], "username": row["username"], "plan": row["plan"]}


@router.get("/status")
async def status(request: Request) -> JSONResponse:
    with _conn() as c:
        n_users = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    user = current_user(request)
    return JSONResponse(content={
        "auth_required": auth_required(),
        "has_users": n_users > 0,
        "logged_in": user is not None,
        "user": user,
    })


@router.post("/register")
async def register(request: Request) -> JSONResponse:
    body = await request.json()
    username = (body.get("username") or "").strip().lower()
    password = body.get("password") or ""
    if len(username) < 3 or len(username) > 32 or not username.replace("_", "").replace(".", "").isalnum():
        return JSONResponse(status_code=400, content={"error": "Usuario: 3-32 caracteres alfanuméricos."})
    if len(password) < 8:
        return JSONResponse(status_code=400, content={"error": "La contraseña debe tener al menos 8 caracteres."})

    salt = secrets.token_bytes(16)
    with _conn() as c:
        try:
            c.execute("INSERT INTO users (username, salt, pwhash, created_at) VALUES (?,?,?,?)",
                      (username, salt, _hash_pw(password, salt), time.time()))
        except sqlite3.IntegrityError:
            return JSONResponse(status_code=409, content={"error": "Ese usuario ya existe."})
        user_id = c.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()["id"]
        token = secrets.token_urlsafe(32)
        c.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?,?,?)",
                  (_hash_token(token), user_id, time.time() + _SESSION_TTL))
    return JSONResponse(content={"token": token, "username": username, "plan": "free"})


@router.post("/login")
async def login(request: Request) -> JSONResponse:
    body = await request.json()
    username = (body.get("username") or "").strip().lower()
    password = body.get("password") or ""
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row or not hmac.compare_digest(_hash_pw(password, row["salt"]), row["pwhash"]):
            time.sleep(0.4)   # frenar fuerza bruta
            return JSONResponse(status_code=401, content={"error": "Usuario o contraseña incorrectos."})
        token = secrets.token_urlsafe(32)
        c.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?,?,?)",
                  (_hash_token(token), row["id"], time.time() + _SESSION_TTL))
        # Purgar sesiones caducadas de paso
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
    return JSONResponse(content={"token": token, "username": row["username"], "plan": row["plan"]})


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    token = request.headers.get("X-Andromeda-Token") or ""
    if token:
        with _conn() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))
    return JSONResponse(content={"ok": True})


@router.get("/profile")
async def get_profile(request: Request) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "No autenticado"})
    with _conn() as c:
        row = c.execute("SELECT * FROM profiles WHERE user_id=?", (user["id"],)).fetchone()
    profile = {
        "display_name": (row["display_name"] if row else "") or user["username"],
        "email":        row["email"] if row else "",
        "location":     row["location"] if row else "",
        "organization": row["organization"] if row else "",
    }
    return JSONResponse(content={"profile": profile, "plan": user["plan"], "username": user["username"]})


@router.put("/profile")
async def update_profile(request: Request) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "No autenticado"})
    body = await request.json()
    fields = {
        "display_name": str(body.get("display_name", ""))[:120],
        "email":        str(body.get("email", ""))[:200],
        "location":     str(body.get("location", ""))[:120],
        "organization": str(body.get("organization", ""))[:120],
    }
    with _conn() as c:
        c.execute(
            "INSERT INTO profiles (user_id, display_name, email, location, organization, updated_at) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET display_name=excluded.display_name, "
            "email=excluded.email, location=excluded.location, organization=excluded.organization, "
            "updated_at=excluded.updated_at",
            (user["id"], fields["display_name"], fields["email"], fields["location"],
             fields["organization"], time.time()),
        )
    return JSONResponse(content={"success": True, "profile": fields})


@router.post("/change-password")
async def change_password(request: Request) -> JSONResponse:
    user = current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "No autenticado"})
    body = await request.json()
    current = str(body.get("current_password", ""))
    new_pw  = str(body.get("new_password", ""))
    if len(new_pw) < 8:
        return JSONResponse(status_code=400, content={"error": "La nueva contraseña debe tener al menos 8 caracteres"})
    with _conn() as c:
        row = c.execute("SELECT salt, pwhash FROM users WHERE id=?", (user["id"],)).fetchone()
        if not row or _hash_pw(current, row["salt"]) != row["pwhash"]:
            return JSONResponse(status_code=403, content={"error": "La contraseña actual no es correcta"})
        new_salt = secrets.token_bytes(16)
        c.execute("UPDATE users SET salt=?, pwhash=? WHERE id=?",
                  (new_salt, _hash_pw(new_pw, new_salt), user["id"]))
        # Cerrar otras sesiones por seguridad, salvo la actual
        token = request.headers.get("X-Andromeda-Token") or ""
        if token:
            c.execute("DELETE FROM sessions WHERE user_id=? AND token_hash != ?",
                      (user["id"], _hash_token(token)))
    return JSONResponse(content={"success": True})
