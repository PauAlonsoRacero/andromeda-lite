"""
registry.py — Registro de especialistas con sistema de niveles.

Gestiona el catálogo con:
  1. 4 niveles de potencia por especialista (low/mid/high/ultra)
  2. Selección automática del mejor nivel según hardware
  3. Soporte de forced_level para override manual
  4. Sistema de precarga (keep_warm) para latencia cero

Prioridad de configuración:
  profiles.py (defaults) → specialists.yaml (usuario) → runtime API
"""

import logging
from pathlib import Path

import yaml

from app.models.schemas import SpecialistProfile, ModelLevel, ModelTiers
from app.specialists.profiles import SPECIALIST_PROFILES

logger = logging.getLogger("andromeda.registry")

_PENDIENTE = "PENDIENTE_CONFIGURAR"


def _model_size_b(model_name: str) -> float:
    """
    Estima el tamaño en miles de millones de parámetros a partir del tag de
    Ollama (p. ej. 'qwen3:32b' → 32, 'gemma3:4b' → 4, 'mistral:7b' → 7).
    Si no se puede inferir, devuelve 0 (se considera el más pequeño).
    """
    import re as _re
    tag = model_name.split(":", 1)[1] if ":" in model_name else model_name
    m = _re.search(r"(\d+(?:\.\d+)?)\s*b", tag.lower())
    if m:
        return float(m.group(1))
    return 0.0


def _largest_model(models: list[str]) -> str:
    """Devuelve el modelo más grande de la lista (por tamaño inferido del tag)."""
    if not models:
        return ""
    return max(models, key=lambda m: (_model_size_b(m), m))

# Mapeo de nivel → rango de VRAM recomendado
LEVEL_VRAM_THRESHOLDS = {
    "ultra": 48.0,
    "high":  20.0,
    "mid":   8.0,
    "low":   0.0,
}


class SpecialistRegistry:
    """
    Catálogo de especialistas con sistema de 4 niveles de potencia.
    """

    def __init__(self, config_path: str) -> None:
        self._profiles: dict[str, SpecialistProfile] = {
            k: v.model_copy(deep=True)
            for k, v in SPECIALIST_PROFILES.items()
        }
        self._tiers: dict[str, ModelTiers]   = {}
        self._warm:  dict[str, bool]         = {}
        self._forced_level: dict[str, str | None] = {}
        self._orchestrator_model = _PENDIENTE
        self._orchestrator_active = False
        self._orchestrator_warm = False
        self._available_models: set[str] = set()
        self._auto_activated_once = False    # auto-activación masiva: solo 1 vez
        self._user_toggled: set[str] = set() # especialistas que el usuario tocó a mano

        self._load_yaml(config_path)

        active = len(self.get_active())
        total  = len(self._profiles)
        logger.info(
            f"Registry cargado: {active}/{total} activos. "
            f"Warm: {[k for k,v in self._warm.items() if v]}. "
            f"Orquestador: {'activo' if self._orchestrator_active else 'inactivo'}"
        )

    # ── Carga de YAML ─────────────────────────────────────────────────────────

    def _load_yaml(self, config_path: str) -> None:
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"specialists.yaml no encontrado en '{config_path}'")
            return

        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            for entry in data.get("specialists", []):
                spec_id = entry.get("id")
                if not spec_id:
                    continue

                # Añadir al perfil si no existe (permite especialistas personalizados)
                if spec_id not in self._profiles:
                    logger.info(f"Especialista personalizado detectado: {spec_id}")
                    # Crear perfil mínimo
                    self._profiles[spec_id] = SpecialistProfile(
                        id=spec_id,
                        name=entry.get("name", spec_id.replace("-", " ").title()),
                        model_name=_PENDIENTE,
                        domain=entry.get("domain", "Custom"),
                        description=entry.get("description", ""),
                    )

                profile = self._profiles[spec_id]

                # Estado básico
                if "active" in entry:
                    profile.active = bool(entry["active"])

                self._warm[spec_id]         = bool(entry.get("keep_warm", False))
                self._forced_level[spec_id] = entry.get("forced_level")

                # Cargar niveles de potencia
                levels_data = entry.get("levels", {})
                if levels_data:
                    tiers = self._parse_levels(levels_data)
                    self._tiers[spec_id] = tiers
                    # El model_name activo se determina en resolve_model_for_tier()
                    # pero ponemos el mid como default visual
                    if tiers.mid:
                        profile.model_name = tiers.mid.model_name
                elif "model_name" in entry:
                    # Compatibilidad con formato antiguo (sin niveles)
                    profile.model_name = entry["model_name"]

            # Orquestador
            orch = data.get("orchestrator", {})
            if orch:
                self._orchestrator_model  = orch.get("model_name", _PENDIENTE)
                self._orchestrator_active = bool(orch.get("active", False))
                self._orchestrator_warm   = bool(orch.get("keep_warm", False))

        except yaml.YAMLError as exc:
            logger.error(f"Error parseando specialists.yaml: {exc}")

    def _parse_levels(self, levels_data: dict) -> ModelTiers:
        """Convierte el dict del YAML en un objeto ModelTiers."""
        parsed = {}
        for level_name in ["low", "mid", "high", "ultra"]:
            ld = levels_data.get(level_name)
            if ld and ld.get("model_name"):
                parsed[level_name] = ModelLevel(
                    name=level_name,
                    model_name=ld["model_name"],
                    params_b=float(ld.get("params_b", 7)),
                    vram_required_gb=float(ld.get("vram_required_gb", 5)),
                    min_tier=int(ld.get("min_tier", 1)),
                    description=ld.get("description", ""),
                )
        return ModelTiers(**parsed)

    # ── Resolución de modelo según hardware ──────────────────────────────────

    def set_available_models(self, models: list[str]) -> None:
        """Guarda la lista de modelos realmente descargados en Ollama.

        Idempotente: si la lista no cambió respecto a la última vez, no hace
        nada (ni log ni reproceso). Esto evita el spam de logs y trabajo
        redundante cuando se llama en cada request de chat.
        """
        nuevos = set(models or [])
        if nuevos == self._available_models and self._available_models:
            return  # sin cambios → no-op (evita polling/log infinito)
        cambio_real = nuevos != self._available_models
        self._available_models = nuevos
        if models and cambio_real:
            logger.info(f"Modelos disponibles en Ollama: {len(models)}")
            self._auto_activate_from_available()
            # Zero-config: mapear automáticamente los modelos instalados a los
            # niveles de potencia (low/mid/high/ultra) que no tenga fijados el
            # usuario. Sin esto, en una instalación limpia specialists.yaml trae
            # los niveles vacíos y la potencia no cambiaba nunca de modelo.
            try:
                self._auto_assign_tiers()
            except Exception as exc:
                logger.warning(f"Auto-asignación de niveles falló: {exc}")

    def should_refresh_tags(self, min_interval_s: float = 30.0) -> bool:
        """Indica si conviene volver a consultar /api/tags de Ollama.

        Debounce: devuelve True como mucho una vez cada `min_interval_s`. Así el
        chat no machaca a Ollama con /api/tags en cada mensaje.
        """
        import time as _t
        now = _t.monotonic()
        last = getattr(self, "_last_tags_refresh", 0.0)
        if now - last >= min_interval_s:
            self._last_tags_refresh = now
            return True
        return False


    # ── Auto-asignación de niveles de potencia (zero-config) ─────────────────

    _AUTO_DESC = "asignado automáticamente"
    _NON_CHAT_HINTS = ("embed", "embedding", "bge", "nomic", "minilm", "e5-",
                       "reranker", "llava", "bakllava", "moondream")
    _LEVEL_TARGETS = {"low": 3.0, "mid": 7.0, "high": 22.0, "ultra": 70.0}
    # Las asignaciones con esta descripción se recalculan cuando cambian los
    # modelos instalados o el modelo activado; las manuales se respetan siempre.


    def _estimate_params_b(self, model_name: str) -> float:
        """Estima los parámetros (en B) de un modelo instalado.

        1) ':7b' / '14b' explícito en el nombre; 2) el catálogo; 3) heurística
        por familia. Si todo falla, asume 7B (tamaño más común).
        """
        import re as _re
        n = (model_name or "").lower()
        m = _re.search(r"(\d+(?:\.\d+)?)\s*b\b", n)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        try:
            from app.core.model_catalog import CATALOG
            base = n.split(":")[0]
            for entry in CATALOG:
                en = str(entry.get("name", "")).lower()
                if en.split(":")[0] == base:
                    return float(entry.get("params_b", 7.0))
        except Exception:
            pass
        _FAMILY = {"llama2": 7.0, "llama3": 8.0, "mistral": 7.0, "gemma": 7.0,
                   "gemma2": 9.0, "gemma3": 4.0, "phi3": 3.8, "phi4": 14.0,
                   "qwen": 7.0, "codellama": 7.0, "deepseek": 7.0, "tinyllama": 1.1}
        for fam, p in _FAMILY.items():
            if fam in n:
                return p
        return 7.0

    def _auto_assign_tiers(self) -> None:
        """Mapea los modelos instalados a low/mid/high/ultra automáticamente.

        - Respeta cualquier nivel que el usuario ya tenga asignado a un modelo
          que siga instalado (su elección manda).
        - Rellena los niveles vacíos (o cuyo modelo ya no existe) con el modelo
          instalado más cercano al tamaño objetivo del nivel (3/7/22/70 B).
        - Desempate: prefiere modelos capaces de usar herramientas, luego orden
          alfabético (determinista).
        - Excluye embeddings y modelos de visión pura.
        """
        chat_models = [m for m in sorted(self._available_models)
                       if not any(h in m.lower() for h in self._NON_CHAT_HINTS)]
        if not chat_models:
            return

        try:
            from app.core.model_catalog import supports_tools, estimate_vram, classify_tier
        except Exception:
            supports_tools = lambda _m: True          # noqa: E731
            estimate_vram = lambda p, q="Q4": p * 0.7  # noqa: E731
            classify_tier = lambda p, v=0: 1           # noqa: E731

        est = {m: self._estimate_params_b(m) for m in chat_models}
        from app.models.schemas import ModelTiers, ModelLevel

        for spec_id in list(self._profiles.keys()):
            try:
                _anchor = self.get_model_override(spec_id)
            except Exception:
                _anchor = None
            tiers = self._tiers.get(spec_id) or ModelTiers()
            changed = []
            for level, target in self._LEVEL_TARGETS.items():
                existing = getattr(tiers, level, None)
                if existing and existing.model_name and \
                        existing.model_name in self._available_models and \
                        existing.description != self._AUTO_DESC:
                    continue  # asignación manual del usuario válida → se respeta
                best = min(chat_models,
                           key=lambda m: (abs(est[m] - target),
                                          0 if m == _anchor else 1,
                                          0 if supports_tools(m) else 1, m))
                params = est[best]
                setattr(tiers, level, ModelLevel(
                    name=level, model_name=best, params_b=params,
                    vram_required_gb=round(estimate_vram(params), 1),
                    min_tier=int(classify_tier(params)),
                    description=self._AUTO_DESC,
                ))
                changed.append(f"{level}→{best}")
            if changed:
                self._tiers[spec_id] = tiers
                logger.info(f"Niveles auto-asignados para '{spec_id}': "
                            + ", ".join(changed))

    def _auto_activate_from_available(self) -> None:
        """
        Andromeda NO activa ninguna IA automáticamente. La primera vez que se
        abre no hay ningún modelo activo ni precargado: el usuario instala el
        modelo que quiera y lo activa él mismo desde "Modelos de IA". Su elección
        se persiste para las siguientes aperturas.

        (Antes se auto-activaban especialistas al detectar modelos descargados,
        pero Pau quiere arranque limpio y control total del usuario.)
        """
        # Marcamos que ya pasó la "primera detección" para no reactivar nada nunca.
        self._auto_activated_once = True
        return

    # ── Overrides de modelo (variantes del Lab) ──────────────────────────────
    def _overrides_path(self):
        import os
        from pathlib import Path
        d = Path(os.environ.get("ANDROMEDA_DATA_DIR", "data"))
        d.mkdir(parents=True, exist_ok=True)
        return d / "model_overrides.json"

    def get_model_override(self, specialist_id: str) -> str | None:
        return self._load_overrides().get(specialist_id)

    def get_all_overrides(self) -> dict:
        return self._load_overrides()

    def set_model_override(self, specialist_id: str, model_name: str | None) -> None:
        """Asigna (o quita con None) un modelo concreto a un especialista.
        Persiste en JSON (escritura atómica + lock) para sobrevivir reinicios y
        evitar corrupción si llegan dos asignaciones a la vez."""
        import json, os, threading
        if not hasattr(self, "_overrides_lock"):
            self._overrides_lock = threading.Lock()
        with self._overrides_lock:
            ov = dict(self._load_overrides())  # copia para no mutar la caché compartida
            if model_name:
                ov[specialist_id] = model_name
                logger.info(f"Override: {specialist_id} → {model_name}")
            else:
                ov.pop(specialist_id, None)
                logger.info(f"Override eliminado para {specialist_id}")
            try:
                path = self._overrides_path()
                tmp = path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(ov, indent=2))
                os.replace(tmp, path)  # rename atómico: nunca deja el archivo a medias
            except OSError as exc:
                logger.warning(f"No se pudo persistir overrides: {exc}")
            self._overrides_cache = ov
        # El modelo activado ancla la auto-asignación de niveles → recomputar.
        try:
            self._auto_assign_tiers()
        except Exception as exc:
            logger.warning(f"Re-asignación de niveles tras override falló: {exc}")

    def _load_overrides(self) -> dict:
        import json
        if getattr(self, "_overrides_cache", None) is not None:
            return self._overrides_cache
        try:
            self._overrides_cache = json.loads(self._overrides_path().read_text())
        except (OSError, json.JSONDecodeError):
            self._overrides_cache = {}
        return self._overrides_cache

    def _pick_available(self, preferred: str, exclude: set[str] | None = None) -> str:
        """
        Si el modelo preferido está descargado, lo usa.
        Si no, busca un fallback entre los modelos disponibles.
        `exclude`: modelos ya asignados a otros especialistas en esta misma
        petición, para repartir modelos distintos y que la fusión aporte
        diversidad real (si quedan opciones; si no, se permite repetir).
        """
        available = getattr(self, "_available_models", set())
        if not available:
            return preferred  # No sabemos qué hay — usar el preferido
        exclude = exclude or set()
        if preferred in available:
            return preferred
        # Coincidencia por familia (ej: 'qwen2.5-coder:14b' → 'qwen2.5-coder:7b')
        base = preferred.split(":")[0]
        family = [m for m in available if m.split(":")[0] == base]
        if family:
            chosen = _largest_model(family)
            logger.info(f"Fallback familia: '{preferred}' no descargado, usando '{chosen}'")
            return chosen
        # Preferir un modelo aún no asignado a otro especialista (diversidad).
        # Entre los candidatos, elegimos el MÁS GRANDE disponible (no el primero
        # alfabético, que solía dar codellama por la 'c').
        unused = sorted(available - exclude)
        if unused:
            chosen = _largest_model(unused)
            logger.info(f"Fallback: '{preferred}' no descargado, usando '{chosen}' (sin repetir)")
            return chosen
        # Si todos están en uso, permitir repetir (el más grande)
        chosen = _largest_model(sorted(available))
        logger.info(f"Fallback: '{preferred}' no descargado, usando '{chosen}'")
        return chosen

    def resolve_model_for_tier(
        self,
        specialist_id: str,
        hardware_tier: int,
        vram_free_gb: float = 999.0,
        exclude_models: set[str] | None = None,
        power_tier: int | None = None,
    ) -> tuple[str, str]:
        """
        Retorna (model_name, level_name) para el especialista.

        Si `power_tier` (1-4) se indica, elige el modelo del tamaño que el prompt
        necesita (escalado de potencia de Andromeda Orquesta), no el máximo del
        hardware. Si no, comportamiento clásico: el mejor que cabe.
        """
        forced = self._forced_level.get(specialist_id)
        tiers  = self._tiers.get(specialist_id)

        override = self.get_model_override(specialist_id)
        if override:
            return (override, "lab")

        if not tiers:
            base = self._profiles[specialist_id].model_name
            return (self._pick_available(base, exclude_models), "custom")

        if forced:
            level = tiers.level_for_name(forced)
            if level:
                return (self._pick_available(level.model_name, exclude_models), forced)

        # Escalado por potencia (Andromeda Orquesta): el más pequeño que basta.
        if power_tier is not None:
            level = tiers.best_for_power(power_tier, hardware_tier, vram_free_gb)
            if level:
                return (self._pick_available(level.model_name, exclude_models), level.name)

        # Selección automática clásica — mejor nivel que cabe
        level = tiers.best_for_tier(hardware_tier, vram_free_gb)
        if level:
            return (self._pick_available(level.model_name, exclude_models), level.name)

        if tiers.low:
            return (self._pick_available(tiers.low.model_name, exclude_models), "low")

        base = self._profiles[specialist_id].model_name
        return (self._pick_available(base, exclude_models), "unknown")

    def get_tiers(self, specialist_id: str) -> ModelTiers | None:
        """Retorna los niveles de potencia de un especialista."""
        return self._tiers.get(specialist_id)

    def get_forced_level(self, specialist_id: str) -> str | None:
        return self._forced_level.get(specialist_id)

    def set_forced_level(self, specialist_id: str, level: str | None) -> None:
        """Override manual del nivel. None = automático."""
        self._forced_level[specialist_id] = level
        logger.info(f"Nivel forzado para '{specialist_id}': {level or 'automático'}")

    def get_warm_specialists(self) -> list[str]:
        """Retorna IDs de especialistas marcados como keep_warm."""
        warm = [sid for sid, w in self._warm.items() if w]
        if self._orchestrator_warm and self._orchestrator_active:
            warm.append("orchestrator")
        return warm

    def is_warm(self, specialist_id: str) -> bool:
        return self._warm.get(specialist_id, False)

    def set_warm(self, specialist_id: str, warm: bool) -> None:
        self._warm[specialist_id] = warm

    # ── Consultas estándar ────────────────────────────────────────────────────

    def get_all(self) -> list[SpecialistProfile]:
        return list(self._profiles.values())

    def get_active(self) -> list[SpecialistProfile]:
        return [p for p in self._profiles.values() if p.active]

    def get_eligible_for_tier(self, tier: int) -> list[SpecialistProfile]:
        return [p for p in self.get_active() if p.min_tier <= tier]

    def get_by_id(self, specialist_id: str) -> SpecialistProfile:
        if specialist_id not in self._profiles:
            raise ValueError(f"Especialista '{specialist_id}' no existe.")
        return self._profiles[specialist_id]

    def is_configured(self, specialist_id: str) -> bool:
        try:
            p = self.get_by_id(specialist_id)
            return p.active and (
                p.model_name != _PENDIENTE
                or specialist_id in self._tiers
            )
        except ValueError:
            return False

    def get_status_summary(self) -> dict:
        all_p    = self.get_all()
        active   = self.get_active()
        pending  = [p for p in all_p if p.model_name == _PENDIENTE and not self._tiers.get(p.id)]
        return {
            "total":               len(all_p),
            "active":              len(active),
            "pending":             len(pending),
            "pending_ids":         [p.id for p in pending],
            "active_ids":          [p.id for p in active],
            "warm_ids":            self.get_warm_specialists(),
            "orchestrator_active": self._orchestrator_active,
            "orchestrator_model":  self._orchestrator_model,
            "orchestrator_warm":   self._orchestrator_warm,
        }

    # ── Modificación en runtime ───────────────────────────────────────────────

    def update_model(self, specialist_id: str, model_name: str, active: bool = True) -> SpecialistProfile:
        profile = self.get_by_id(specialist_id)
        if model_name:
            profile.model_name = model_name
        profile.active = active
        # Recordar que el usuario tocó este especialista a mano: la
        # auto-activación no debe volver a pisarlo.
        if not hasattr(self, "_user_toggled"):
            self._user_toggled = set()
        self._user_toggled.add(specialist_id)
        logger.info(f"Runtime update: '{specialist_id}' → {model_name or '(sin cambio)'} (active={active})")
        return profile

    def update_orchestrator(self, model_name: str, active: bool = True) -> None:
        self._orchestrator_model  = model_name
        self._orchestrator_active = active

    @property
    def orchestrator_model(self) -> str:
        return self._orchestrator_model

    @property
    def orchestrator_active(self) -> bool:
        return self._orchestrator_active and self._orchestrator_model != _PENDIENTE

    @property
    def orchestrator_warm(self) -> bool:
        return self._orchestrator_warm
