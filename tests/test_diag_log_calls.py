"""Toda llamada a diag.log(...) debe usar solo los argumentos que la función acepta.

Bug real (1.1): streaming.py llamaba diag.log(..., modelo=..., nivel=...) y
``log`` no acepta esos nombres → TypeError en CADA mensaje con un modelo de
razonamiento. Ningún test lo cazaba porque la rama solo se ejecuta con modelos
reales. Este test revisa el código fuente, sin necesitar Ollama.
"""
import ast
import inspect
from pathlib import Path

from app.observability import diagnostics

BACKEND = Path(__file__).resolve().parent.parent / "backend"


def _allowed():
    sig = inspect.signature(diagnostics.log)
    return {n for n, p in sig.parameters.items()
            if p.kind is inspect.Parameter.KEYWORD_ONLY}


def _llamadas_diag_log():
    for py in BACKEND.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "log"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "diag"):
                yield py, node


def test_hay_llamadas_que_revisar():
    # Si esto da 0, el test de abajo no estaría comprobando nada.
    assert sum(1 for _ in _llamadas_diag_log()) >= 5


def test_diag_log_solo_usa_argumentos_validos():
    permitidos = _allowed()
    assert {"detail", "data", "level", "duration_ms"} <= permitidos
    malos = []
    for py, call in _llamadas_diag_log():
        for kw in call.keywords:
            if kw.arg is not None and kw.arg not in permitidos:
                malos.append(f"{py.name}:{call.lineno} → {kw.arg}=")
    assert not malos, "diag.log con argumentos inexistentes: " + ", ".join(malos)


def test_diag_log_lleva_categoria_y_evento_posicionales():
    for py, call in _llamadas_diag_log():
        assert len(call.args) >= 2, f"{py.name}:{call.lineno} sin category/event"
