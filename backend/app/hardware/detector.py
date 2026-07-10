"""
detector.py — Detector de hardware de Andromeda.

Detecta automáticamente el entorno de ejecución:
  - Sistema operativo
  - CPU (modelo y núcleos)
  - RAM total y disponible
  - GPU: NVIDIA (nvidia-smi), AMD (rocm-smi), Apple Silicon (system_profiler)
  - Tipo de aceleración disponible

REGLA FUNDAMENTAL: este módulo NUNCA lanza excepciones.
Si la detección falla por cualquier razón, retorna un HardwareInfo
con valores mínimos seguros (T1, CPU-only).

Uso:
    from app.hardware.detector import HardwareDetector
    detector = HardwareDetector()
    info = detector.detect()
    print(info.max_tier, info.acceleration)
"""

import json
import logging
import os
import sys
import platform
import subprocess
from app.core.silent_subprocess import silent_run

import psutil

from app.models.schemas import HardwareInfo

logger = logging.getLogger("andromeda.hardware")


def _read_cpu_model() -> str:
    """
    Lee el modelo de CPU de forma robusta según el OS.
    platform.processor() suele devolver algo inútil ('x86_64') en Linux,
    así que leemos de fuentes más fiables.
    """
    system = platform.system()
    # 1. Override explícito por variable de entorno (lo pasa el host)
    env_cpu = os.environ.get("ANDROMEDA_HOST_CPU")
    if env_cpu:
        return env_cpu
    try:
        if system == "Linux":
            # /proc/cpuinfo tiene el "model name" real
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        elif system == "Windows":
            # El registro tiene el nombre comercial real ("AMD Ryzen 9 5900X…").
            # Es más fiable que wmic (deprecado/eliminado en Windows 11 recientes,
            # lo que hacía caer al genérico "AMD64 Family 25…") y no abre ventana.
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
                name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                winreg.CloseKey(key)
                if name and name.strip():
                    return name.strip()
            except Exception:
                pass
            # Respaldo: wmic (por si el registro no estuviera disponible).
            out = silent_run(
                ["wmic", "cpu", "get", "name"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [l.strip() for l in out.stdout.splitlines() if l.strip()]
            if len(lines) >= 2:
                return lines[1]
        elif system == "Darwin":
            out = silent_run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5,
            )
            if out.stdout.strip():
                return out.stdout.strip()
    except Exception:
        pass
    # Fallback a platform
    proc = platform.processor()
    return proc if proc and proc not in ("x86_64", "") else "CPU genérica"


class HardwareDetector:
    """
    Detecta el hardware disponible y calcula el tier de ejecución.

    Soporta override por variables de entorno (útil cuando el backend
    corre en Docker y no ve el hardware real del host):
      ANDROMEDA_HOST_OS      — sistema operativo real
      ANDROMEDA_HOST_CPU     — modelo de CPU real
      ANDROMEDA_HOST_RAM_GB  — RAM total real en GB
      ANDROMEDA_HOST_VRAM_GB — VRAM real en GB
      ANDROMEDA_HOST_GPU     — nombre de la GPU real
    """

    def live_usage(self) -> dict:
        """Lee el uso ACTUAL de RAM y VRAM (en tiempo real), sin rehacer toda la
        detección. Pensado para que la UI lo sondee cada pocos segundos y muestre
        cuánta memoria libre hay ahora mismo (cambia al cargar/descargar modelos).
        """
        out: dict = {}
        # RAM en vivo (siempre disponible vía psutil).
        try:
            mem = psutil.virtual_memory()
            out["ram_total_gb"] = round(mem.total / (1024 ** 3), 1)
            out["ram_available_gb"] = round(mem.available / (1024 ** 3), 1)
            out["ram_used_pct"] = round(mem.percent, 1)
        except Exception:
            pass
        # VRAM libre en vivo (NVIDIA). Override por env si el backend va en Docker.
        env_vram = os.environ.get("ANDROMEDA_HOST_VRAM_GB")
        if env_vram and float(env_vram) > 0:
            out["vram_total_gb"] = float(env_vram)
            out["vram_free_gb"] = None   # desconocido en vivo dentro de Docker
            return out
        try:
            result = silent_run(
                ["nvidia-smi", "--query-gpu=memory.total,memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                total = free = 0.0
                for line in result.stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        total += float(parts[0]) / 1024
                        free += float(parts[1]) / 1024
                out["vram_total_gb"] = round(total, 1)
                out["vram_free_gb"] = round(free, 1)
                out["vram_used_pct"] = round((total - free) / total * 100, 1) if total else 0.0
        except Exception:
            pass
        return out

    def detect(self) -> HardwareInfo:
        """
        Detecta todo el hardware disponible.

        Proceso:
          1. OS y CPU con platform + psutil (siempre disponible)
          2. RAM con psutil (siempre disponible)
          3. GPU: intenta NVIDIA → AMD → Apple → CPU-only
          4. Calcula el tier (1–4) según VRAM disponible

        Returns:
            HardwareInfo siempre válido, incluso si todas las detecciones
            de GPU fallan (en ese caso: acceleration="cpu", tier=1)
        """
        try:
            # ── Sistema operativo (override de entorno si existe) ──────────
            os_name = os.environ.get("ANDROMEDA_HOST_OS") or platform.system()

            # ── CPU ───────────────────────────────────────────────────────
            cpu_model = _read_cpu_model()
            cpu_cores = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1

            # ── RAM (override de entorno si existe) ────────────────────────
            mem = psutil.virtual_memory()
            env_ram = os.environ.get("ANDROMEDA_HOST_RAM_GB")
            if env_ram:
                try:
                    ram_total_gb = float(env_ram)
                    ram_available_gb = ram_total_gb * (mem.available / mem.total) if mem.total else ram_total_gb * 0.7
                except ValueError:
                    ram_total_gb = mem.total / (1024 ** 3)
                    ram_available_gb = mem.available / (1024 ** 3)
            else:
                ram_total_gb = mem.total / (1024 ** 3)
                ram_available_gb = mem.available / (1024 ** 3)

            # ── GPU ───────────────────────────────────────────────────────
            # Override de entorno si el host detectó una GPU
            env_vram = os.environ.get("ANDROMEDA_HOST_VRAM_GB")
            env_gpu = os.environ.get("ANDROMEDA_HOST_GPU")
            if env_vram and float(env_vram) > 0:
                vram = float(env_vram)
                gpus = [{
                    "name": env_gpu or "GPU",
                    "vram_total_gb": vram,
                    "vram_free_gb": round(vram * 0.9, 1),
                }]
                acceleration = "cuda" if "nvidia" in (env_gpu or "").lower() or "rtx" in (env_gpu or "").lower() or "gtx" in (env_gpu or "").lower() else "gpu"
            else:
                gpus, acceleration = self._detect_gpu(os_name)

            # Suma VRAM de todas las GPUs detectadas
            total_vram_gb = sum(g.get("vram_total_gb", 0.0) for g in gpus)

            # ── Tier ──────────────────────────────────────────────────────
            max_tier = self._calculate_tier(total_vram_gb, ram_total_gb)

            hardware = HardwareInfo(
                os=os_name,
                cpu_model=cpu_model,
                cpu_cores=cpu_cores,
                ram_total_gb=round(ram_total_gb, 1),
                ram_available_gb=round(ram_available_gb, 1),
                gpus=gpus,
                total_vram_gb=round(total_vram_gb, 1),
                acceleration=acceleration,
                max_tier=max_tier,
            )

            logger.info(
                f"Hardware detectado: OS={os_name}, "
                f"GPU={'|'.join(g['name'] for g in gpus) or 'ninguna'}, "
                f"VRAM={total_vram_gb:.1f}GB, "
                f"acceleration={acceleration}, tier=T{max_tier}"
            )
            return hardware

        except Exception as exc:
            # Si algo inesperado falla, retornamos un perfil mínimo seguro
            logger.error(f"Detección de hardware fallida, usando perfil mínimo: {exc}")
            return self._fallback_hardware()

    # ── Detección de GPU ───────────────────────────────────────────────────────

    def _detect_gpu(self, os_name: str) -> tuple[list[dict], str]:
        """
        Intenta detectar GPU en orden: NVIDIA → Apple → AMD → CPU.

        Returns:
            (lista_de_gpus, tipo_aceleración)
            lista_de_gpus: cada elemento es {name, vram_total_gb, vram_free_gb}
            tipo_aceleración: "cuda" | "metal" | "rocm" | "cpu"
        """
        # NVIDIA (Windows, Linux)
        nvidia = self._detect_nvidia()
        if nvidia:
            return nvidia, "cuda"

        # Apple Silicon (macOS únicamente)
        if os_name == "Darwin":
            apple = self._detect_apple()
            if apple:
                return apple, "metal"
            # Fallback: si system_profiler falla (p.ej. dentro de un .app
            # empaquetado), pero estamos en Apple Silicon (arm64), estimamos la
            # VRAM desde la memoria unificada igualmente. Mejor esto que decir
            # "GPU no detectada" en un Mac que sí tiene GPU.
            import platform as _plat
            if _plat.machine() == "arm64":
                mem = psutil.virtual_memory()
                total_gb = mem.total / (1024 ** 3)
                if total_gb >= 32:
                    est = total_gb - 4.0
                elif total_gb >= 16:
                    est = total_gb - 5.0
                else:
                    est = total_gb * 0.65
                return [{
                    "name": "Apple Silicon GPU",
                    "vram_total_gb": round(est, 1),
                    "vram_free_gb": round(est * 0.9, 1),
                }], "metal"

        # AMD ROCm (Linux principalmente)
        amd = self._detect_amd()
        if amd:
            return amd, "rocm"

        # Sin GPU — CPU-only
        return [], "cpu"

    def _detect_nvidia(self) -> list[dict]:
        """
        Detecta GPUs NVIDIA usando nvidia-smi.

        Ejecuta: nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits
        Output ejemplo:
            NVIDIA GeForce RTX 3090, 24576, 20480

        Returns:
            Lista de GPUs con sus datos, o lista vacía si nvidia-smi no está disponible.
        """
        try:
            result = silent_run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return []

            gpus = []
            for line in result.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == 3:
                    try:
                        gpus.append({
                            "name": parts[0],
                            # nvidia-smi retorna MB → convertir a GB
                            "vram_total_gb": round(float(parts[1]) / 1024, 1),
                            "vram_free_gb": round(float(parts[2]) / 1024, 1),
                        })
                    except ValueError:
                        continue  # línea malformada, ignorar

            return gpus

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            # nvidia-smi no instalado o no disponible — completamente normal
            return []

    def _detect_apple(self) -> list[dict]:
        """
        Detecta la GPU integrada de Apple Silicon usando system_profiler.

        En Apple Silicon, la memoria de la GPU es parte de la memoria unificada,
        así que usamos psutil como estimación (no hay VRAM separada).

        Returns:
            Lista con 1 elemento si es Apple Silicon, vacía si no.
        """
        try:
            result = silent_run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return []

            data = json.loads(result.stdout)
            displays = data.get("SPDisplaysDataType", [])

            for display in displays:
                # Apple Silicon tiene "sppci_memory" con la VRAM dedicada
                # o "spdisplays_mtlgpufamilysupport" para Metal
                vram_str = display.get("sppci_memory", "")
                model_name = display.get("sppci_model", "Apple GPU")

                if "GB" in vram_str:
                    try:
                        vram_gb = float(vram_str.replace(" GB", "").strip())
                        return [{
                            "name": model_name,
                            "vram_total_gb": vram_gb,
                            # Para Apple Silicon la VRAM "libre" es estimada
                            "vram_free_gb": round(vram_gb * 0.75, 1),
                        }]
                    except ValueError:
                        pass

                # Si no encontramos VRAM explícita pero hay una GPU Apple,
                # estimar desde la RAM total (memoria unificada)
                if "Apple" in model_name or any(f"M{i}" in model_name for i in range(1, 10)):
                    mem = psutil.virtual_memory()
                    total_gb = mem.total / (1024 ** 3)
                    # Memoria unificada: casi toda la RAM es usable como VRAM.
                    # macOS reserva ~4-6GB para el sistema; en máquinas grandes
                    # (>=32GB) se puede llegar a total-4 (ej: M4 Max 48GB → ~44GB,
                    # ajustable con `sudo sysctl iogpu.wired_limit_mb=...`).
                    # Override manual: ANDROMEDA_HOST_VRAM_GB.
                    if total_gb >= 32:
                        estimated_vram = total_gb - 4.0
                    elif total_gb >= 16:
                        estimated_vram = total_gb - 5.0
                    else:
                        estimated_vram = total_gb * 0.65
                    return [{
                        "name": model_name,
                        "vram_total_gb": round(estimated_vram, 1),
                        "vram_free_gb": round(estimated_vram * 0.9, 1),
                    }]

            return []

        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _detect_amd(self) -> list[dict]:
        """
        Detecta GPUs AMD usando rocm-smi.
        Disponible en Linux con ROCm instalado.

        Returns:
            Lista de GPUs AMD o lista vacía.
        """
        try:
            result = silent_run(
                ["rocm-smi", "--showmeminfo", "vram", "--csv"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return []

            gpus = []
            lines = result.stdout.strip().split("\n")
            # Saltar la cabecera del CSV
            for line in lines[1:]:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    try:
                        # rocm-smi retorna bytes
                        total_bytes = int(parts[1])
                        gpus.append({
                            "name": f"AMD GPU {len(gpus)}",
                            "vram_total_gb": round(total_bytes / (1024 ** 3), 1),
                            "vram_free_gb": round(total_bytes / (1024 ** 3) * 0.8, 1),
                        })
                    except (ValueError, IndexError):
                        continue

            return gpus

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return []

    # ── Cálculo de tier ───────────────────────────────────────────────────────

    def _calculate_tier(self, vram_gb: float, ram_gb: float) -> int:
        """
        Calcula el tier de hardware (1–4) según la VRAM disponible.

        Si no hay GPU (vram_gb=0), usa la RAM como indicador alternativo.

        Reglas:
            GPU presente:
                T4: >= 48 GB VRAM  (workstation/server)
                T3: >= 16 GB VRAM  (alto rendimiento)
                T2: >= 8  GB VRAM  (recomendado)
                T1: >= 4  GB VRAM  (mínimo viable)
            Sin GPU (CPU-only):
                T2: >= 32 GB RAM
                T1: cualquier cantidad (mínimo)
        """
        if vram_gb >= 48:
            return 4
        elif vram_gb >= 16:
            return 3
        elif vram_gb >= 8:
            return 2
        elif vram_gb >= 4:
            return 1
        else:
            # Sin GPU o VRAM insuficiente — usar RAM como indicador
            if ram_gb >= 32:
                return 2  # Con mucha RAM se pueden usar modelos en CPU
            return 1

    def get_current_vram_free(self) -> float:
        """
        Obtiene la VRAM libre AHORA MISMO (no la detectada al arranque).

        Usada por el PolicyEngine dinámico para decidir si degradar
        antes de cada request. Llama a nvidia-smi en tiempo real.

        Returns:
            Suma de VRAM libre de todas las GPUs en GB.
            0.0 si no hay GPUs o nvidia-smi no está disponible.
        """
        # Override manual (mismo que en la detección inicial): si el usuario
        # fija ANDROMEDA_HOST_VRAM_GB, el valor "en vivo" debe respetarlo
        # (no hay nvidia-smi en Docker/Mac y devolvería 0 ignorando el override).
        env_vram = os.environ.get("ANDROMEDA_HOST_VRAM_GB")
        if env_vram:
            try:
                v = float(env_vram)
                if v > 0:
                    return round(v * 0.9, 1)
            except ValueError:
                pass
        # En Apple Silicon no existe nvidia-smi: usar la estimación de memoria
        # unificada de la detección inicial.
        if sys.platform == "darwin":
            try:
                apple = self._detect_apple()
                if apple:
                    return apple[0].get("vram_free_gb", 0.0)
            except Exception:
                pass
        try:
            result = silent_run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=3,
            )

            if result.returncode != 0:
                return 0.0

            total_free = 0.0
            for line in result.stdout.strip().split("\n"):
                try:
                    total_free += float(line.strip()) / 1024  # MB → GB
                except ValueError:
                    continue

            return round(total_free, 1)

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return 0.0

    # ── Fallback mínimo ────────────────────────────────────────────────────────

    def _fallback_hardware(self) -> HardwareInfo:
        """
        Perfil de hardware mínimo seguro.
        Se usa cuando la detección falla completamente.
        El sistema seguirá funcionando en T1 (modo conservador).
        """
        return HardwareInfo(
            os="Unknown",
            cpu_model="Unknown",
            cpu_cores=1,
            ram_total_gb=8.0,
            ram_available_gb=4.0,
            gpus=[],
            total_vram_gb=0.0,
            acceleration="cpu",
            max_tier=1,
        )

    def get_summary(self) -> dict:
        """
        Retorna un resumen legible del hardware para mostrar en logs o UI.
        Detecta el hardware en el momento de la llamada.
        """
        info = self.detect()
        return {
            "os": info.os,
            "cpu": f"{info.cpu_model} ({info.cpu_cores} cores)",
            "ram_gb": info.ram_total_gb,
            "gpus": [f"{g['name']} ({g['vram_total_gb']}GB)" for g in info.gpus],
            "acceleration": info.acceleration,
            "tier": f"T{info.max_tier}",
            "vram_total_gb": info.total_vram_gb,
        }
