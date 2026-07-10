"""
executor.py — Ejecutor de herramientas MCP integrado con el orquestador.

Cuando un especialista genera una respuesta que contiene llamadas a herramientas
(tool_use blocks), este módulo las ejecuta y retorna los resultados al modelo
para que genere la respuesta final con contexto real.

Flujo:
  1. Especialista recibe prompt + tools disponibles
  2. Especialista genera tool_use: {"name":"read_file","input":{"path":"/x"}}
  3. MCPExecutor ejecuta la herramienta en el servidor MCP
  4. Resultado se inyecta de vuelta al modelo como tool_result
  5. Modelo genera respuesta final con los datos reales
"""

import json
import logging
import re
import time

import httpx

from app.mcp.manager import MCPManager

logger = logging.getLogger("andromeda.mcp.executor")

# Regex para detectar llamadas a herramientas en formato JSON
TOOL_CALL_RE = re.compile(
    r'<tool_call>\s*(\{.*?\})\s*</tool_call>',
    re.DOTALL | re.IGNORECASE
)
# JSON directo con "tool"/"input" en cualquier parte (input puede ser multilínea)
JSON_TOOL_RE = re.compile(
    r'\{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"input"\s*:\s*(\{.*?\})\s*\}',
    re.DOTALL
)


class MCPExecutor:
    """
    Ejecuta las herramientas MCP que los modelos solicitan.
    Se integra en el pipeline del orquestador.
    """

    def __init__(self, manager: MCPManager, metrics=None):
        self.manager = manager
        self.metrics = metrics

    async def run_with_tools(
        self,
        prompt: str,
        model_name: str,
        system_prompt: str,
        ollama_url: str,
        max_tool_rounds: int = 5,
    ) -> tuple[str, list[dict]]:
        """
        Ejecuta un ciclo completo de prompt → tool calls → resultado final.

        Args:
            prompt:          Prompt del usuario
            model_name:      Modelo Ollama a usar
            system_prompt:   System prompt del especialista
            ollama_url:      URL de Ollama
            max_tool_rounds: Máximo de rondas de herramientas (evita loops)

        Returns:
            (respuesta_final, lista_de_tool_calls_ejecutados)
        """
        messages = [{"role": "user", "content": prompt}]
        tool_calls_log = []

        for round_n in range(max_tool_rounds):
            # Llamar al modelo con las herramientas disponibles
            response_text = await self._call_model(
                model_name=model_name,
                system_prompt=system_prompt + self._tools_system_injection(),
                messages=messages,
                ollama_url=ollama_url,
            )

            # Detectar si el modelo quiere usar herramientas
            tool_calls = self._extract_tool_calls(response_text)

            if not tool_calls:
                # No hay más herramientas — respuesta final
                return response_text, tool_calls_log

            # Ejecutar las herramientas solicitadas
            logger.info(f"MCP ronda {round_n+1}: {len(tool_calls)} herramientas a ejecutar")
            tool_results = []
            for tc in tool_calls:
                t_start = time.perf_counter()
                result = await self.manager.call_tool(tc["name"], tc["input"])
                elapsed = (time.perf_counter() - t_start) * 1000

                tool_calls_log.append({
                    "tool":       tc["name"],
                    "input":      tc["input"],
                    "result":     result.text[:500],
                    "is_error":   result.is_error,
                    "latency_ms": round(elapsed, 1),
                })

                logger.info(f"  [{tc['name']}] {'ERROR' if result.is_error else 'OK'} ({elapsed:.0f}ms)")
                # Analytics: registrar la ejecución (params sanitizados dentro)
                if self.metrics is not None:
                    try:
                        self.metrics.record_tool_call(
                            name=tc["name"],
                            latency_ms=elapsed,
                            success=not result.is_error,
                            params=tc.get("input"),
                            error=result.error_msg if result.is_error else None,
                        )
                    except Exception:
                        pass  # analytics nunca debe romper la ejecución
                tool_results.append({
                    "tool":   tc["name"],
                    "result": result.text if not result.is_error else f"ERROR: {result.error_msg}",
                })

            # Añadir el resultado al historial de mensajes
            messages.append({"role": "assistant", "content": response_text})
            results_text = "\n".join(
                f"[{r['tool']}]: {r['result']}" for r in tool_results
            )
            messages.append({
                "role":    "user",
                "content": f"Resultados de las herramientas:\n{results_text}\n\nContinúa con la respuesta.",
            })

        # Máximo de rondas alcanzado
        return response_text, tool_calls_log

    def _tools_system_injection(self) -> str:
        """Añade instrucciones de uso de herramientas al system prompt."""
        tools = self.manager.tools
        if not tools:
            return ""
        # Describir cada herramienta CON sus parámetros, para que el modelo sepa
        # exactamente cómo llamarla (sin esto inventa formatos como ':write').
        lines = []
        for t in tools:
            params = []
            schema = getattr(t, "input_schema", None) or {}
            props = schema.get("properties", {}) if isinstance(schema, dict) else {}
            for pname, pinfo in props.items():
                ptype = pinfo.get("type", "string") if isinstance(pinfo, dict) else "string"
                params.append(f"{pname} ({ptype})")
            param_str = ", ".join(params) if params else "sin parámetros"
            desc = getattr(t, "description", "") or ""
            lines.append(f'- "{t.name}": {desc} | parámetros: {param_str}')
        tools_desc = "\n".join(lines)

        # Buscar una herramienta de escritura de archivos para el ejemplo.
        write_tool = next(
            (t.name for t in tools if "write" in t.name.lower() or "create" in t.name.lower()),
            tools[0].name,
        )
        return f"""

TIENES ACCESO A ESTAS HERRAMIENTAS (úsalas para acciones reales, no expliques cómo hacerlo a mano):
{tools_desc}

CÓMO USARLAS — formato OBLIGATORIO y EXACTO (JSON dentro de las etiquetas):
<tool_call>{{"tool": "nombre_exacto", "input": {{"parametro": "valor"}}}}</tool_call>

REGLAS:
- Si el usuario pide crear/escribir/guardar un archivo, leer archivos, buscar en la web, etc., DEBES emitir un <tool_call>. NUNCA describas los pasos manuales.
- Usa EXACTAMENTE el nombre de herramienta y los parámetros listados arriba. No inventes formatos como ":write".
- Tras la etiqueta no escribas nada más; espera el resultado.

EJEMPLO (crear un archivo de texto):
<tool_call>{{"tool": "{write_tool}", "input": {{"path": "index.html", "content": "<h1>Hola</h1>"}}}}</tool_call>
Usa rutas simples (solo el nombre, p. ej. "index.html" o "notas/todo.txt"). Andromeda lo guarda en tu carpeta de trabajo automáticamente — no escribas rutas absolutas como C:\\... ni /home/...
"""

    def _extract_tool_calls(self, text: str) -> list[dict]:
        """Extrae las llamadas a herramientas del texto del modelo."""
        calls = []

        # Formato <tool_call>{...}</tool_call>
        for match in TOOL_CALL_RE.finditer(text):
            try:
                data = json.loads(match.group(1))
                if "tool" in data and "input" in data:
                    calls.append({"name": data["tool"], "input": data["input"]})
            except json.JSONDecodeError:
                pass

        # Formato {"tool":"name","input":{...}}
        if not calls:
            for match in JSON_TOOL_RE.finditer(text):
                try:
                    name  = match.group(1)
                    input_data = json.loads(match.group(2))
                    calls.append({"name": name, "input": input_data})
                except json.JSONDecodeError:
                    pass

        return calls

    async def _call_model(
        self,
        model_name: str,
        system_prompt: str,
        messages: list[dict],
        ollama_url: str,
    ) -> str:
        """Llamada al modelo Ollama."""
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                resp = await client.post(
                    f"{ollama_url}/api/chat",
                    json={
                        "model":   model_name,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            *messages,
                        ],
                        "options": {"temperature": 0.3, "num_predict": 4096},
                        "stream":  False,
                    },
                    timeout=120.0,
                )
                resp.raise_for_status()
                return resp.json().get("message", {}).get("content", "")
        except Exception as exc:
            logger.error(f"Error llamando al modelo: {exc}")
            return f"Error: {exc}"
