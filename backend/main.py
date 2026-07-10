"""
main.py — Punto de entrada de Andromeda.

Arranca el servidor Uvicorn con la app creada por create_app().

Uso:
    # Desarrollo (con hot-reload):
    python main.py

    # Producción (en Docker):
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
"""

import os
import sys

# Añadir el directorio backend al path para imports absolutos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

from app import create_app
from app.config import settings

# Instancia global de la app — Uvicorn la importa como "main:app"
app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        # hot-reload solo en development
        reload=settings.environment == "development",
        # 1 worker: asyncio maneja la concurrencia,
        # múltiples workers causarían estado duplicado en app.state
        workers=1,
        log_level="debug" if settings.environment == "development" else "info",
    )
