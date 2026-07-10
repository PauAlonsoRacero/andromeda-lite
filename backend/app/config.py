"""
config.py — Configuración central de Andromeda.

Pydantic Settings carga automáticamente desde:
  1. Variables de entorno del sistema
  2. Archivo .env en la raíz del backend

Uso en cualquier módulo:
    from app.config import settings
    print(settings.ollama_base_url)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """
    Todas las variables de configuración del sistema.
    Cada campo puede sobreescribirse con una variable de entorno
    del mismo nombre en mayúsculas (ej: ANDROMEDA_PORT=9000).
    """

    model_config = SettingsConfigDict(
        env_file=".env",           # busca .env en el directorio de trabajo
        env_prefix="ANDROMEDA_",   # prefijo opcional — ANDROMEDA_PORT=8000
        case_sensitive=False,      # acepta tanto PORT como port en el .env
        extra="ignore",            # ignora variables de entorno desconocidas
    )

    # ── Identidad ─────────────────────────────────────────────────────────────
    app_name: str = Field(default="Andromeda", description="Nombre del sistema")
    app_version: str = Field(default="1.0.0", description="Versión actual")
    environment: str = Field(
        default="development",
        description="Entorno de ejecución: development | production",
    )

    # ── Servidor ──────────────────────────────────────────────────────────────
    port: int = Field(default=8000, description="Puerto donde escucha FastAPI")
    frontend_url: str = Field(
        default="http://localhost:5173",
        description="URL del frontend SolidJS — usada para configurar CORS",
    )

    # ── Ollama ────────────────────────────────────────────────────────────────
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description=(
            "URL base del servidor Ollama. "
            "En Docker usa el nombre del servicio 'ollama' (sobreescribe con env). "
            "En app de escritorio (Windows/Mac): http://localhost:11434 o 127.0.0.1"
        ),
    )
    ollama_timeout_seconds: int = Field(
        default=120,
        description="Timeout en segundos para cada llamada a un modelo. "
                    "Modelos lentos en T1 pueden tardar hasta 60-90s.",
    )

    # ── Inferencia ────────────────────────────────────────────────────────────
    default_temperature: float = Field(
        default=0.7,
        description="Temperatura de generación de texto (0=determinista, 1=creativo)",
    )
    default_max_tokens: int = Field(
        default=2048,
        description="Número máximo de tokens a generar por respuesta",
    )
    max_parallel_specialists: int = Field(
        default=3,
        description="Techo absoluto de especialistas en paralelo. "
                    "El Policy Engine puede reducir este número según la VRAM disponible.",
    )

    # ── Observabilidad ────────────────────────────────────────────────────────
    telemetry_enabled: bool = Field(
        default=True,
        description="Activar o desactivar el sistema de traces OpenTelemetry",
    )
    telemetry_db_path: str = Field(
        default="data/traces.db",
        description="Ruta al archivo SQLite donde se guardan los traces",
    )
    trace_history_limit: int = Field(
        default=200,
        description="Número máximo de traces a conservar en SQLite",
    )

    # ── MLOps ─────────────────────────────────────────────────────────────────
    mlops_enabled: bool = Field(
        default=True,
        description="Activar tracking de experimentos MLOps (SQLite local)",
    )
    mlops_db_path: str = Field(
        default="data/mlops_runs.db",
        description="Ruta al SQLite de runs MLOps",
    )
    memory_db_path: str = Field(
        default="data/memory.db",
        description="Ruta al SQLite de memoria semántica",
    )
    specialists_writable_path: str = Field(
        default="",
        description="Ruta ESCRIBIBLE del specialists.yaml (carpeta de datos del usuario en el binario). Si está vacío, se usa specialists_config_path.",
    )
    mlflow_enabled: bool = Field(
        default=False,
        description="Activar MLflow como backend (requiere servidor MLflow corriendo)",
    )
    mlflow_tracking_uri: str = Field(
        default="http://localhost:5001",
        description="URI del servidor MLflow. Solo se usa si mlflow_enabled=true.",
    )

    # ── Rutas de configuración ────────────────────────────────────────────────
    specialists_config_path: str = Field(
        default="../config/specialists.yaml",
        description="Ruta al YAML con la configuración de modelos de los especialistas",
    )
    hardware_policies_path: str = Field(
        default="../config/hardware_policies.yaml",
        description="Ruta al YAML con las políticas de comportamiento por tier de hardware",
    )
    mcp_servers_path: str = Field(
        default="../config/mcp_servers.yaml",
        description="Ruta al YAML con la configuración de servidores MCP",
    )


# ── Instancia global ──────────────────────────────────────────────────────────
# Se importa directamente en cualquier módulo:
#   from app.config import settings


def _resolve_config_paths(s: "Settings") -> None:
    """Hace que las rutas de los YAML de config funcionen en los tres escenarios:

    1. Desarrollo desde backend/  → '../config/x.yaml' (relativa, como siempre).
    2. Binario PyInstaller (.app/.exe) → los datos viven en sys._MEIPASS/config.
    3. Docker → /config (montado), respetado vía variable de entorno absoluta.

    Solo reescribe una ruta si la actual NO existe pero sí la encontramos en
    otra ubicación conocida. Nunca pisa una ruta absoluta que el usuario/entorno
    haya fijado explícitamente y que exista.
    """
    import sys
    from pathlib import Path

    # Bases candidatas donde buscar la carpeta config, en orden de prioridad.
    candidates: list[Path] = []
    # PyInstaller: datos extraídos en _MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "config")
    # Junto al ejecutable (build COLLECT) o junto al paquete
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "config")
    # Raíz del repo (dos niveles por encima de este archivo: app/ → backend/ → raíz)
    here = Path(__file__).resolve()
    candidates.append(here.parents[2] / "config")   # <repo>/config
    candidates.append(here.parents[1] / "config")   # backend/config (fallback)
    # Docker
    candidates.append(Path("/config"))

    for attr, filename in (
        ("specialists_config_path", "specialists.yaml"),
        ("hardware_policies_path", "hardware_policies.yaml"),
        ("mcp_servers_path", "mcp_servers.yaml"),
    ):
        current = Path(getattr(s, attr))
        if current.exists():
            continue  # la ruta configurada ya funciona, no tocar
        for base in candidates:
            candidate = base / filename
            if candidate.exists():
                setattr(s, attr, str(candidate))
                break


settings = Settings()
_resolve_config_paths(settings)
