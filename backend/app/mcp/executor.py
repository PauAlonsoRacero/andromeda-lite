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

    def __init__(self, manager: MCPManager, metrics=None, tools=None):
        self.manager = manager
        self.metrics = metrics
        # Subconjunto de herramientas a ofrecer al modelo. Por defecto todas;
        # el streaming pasa solo las relevantes para el mensaje.
        self._tools = tools

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

            await self._run_tool_calls(tool_calls, messages, response_text, tool_calls_log)

        # Máximo de rondas alcanzado
        return response_text, tool_calls_log


    async def _run_tool_calls(self, tool_calls, messages, response_text, tool_calls_log):
        """Ejecuta las herramientas pedidas y añade sus resultados a la conversación."""
        # Ejecutar las herramientas solicitadas
        logger.info(f"MCP: {len(tool_calls)} herramientas a ejecutar")
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


    async def stream_with_tools(
        self, *, prompt: str, model_name: str, system_prompt: str, ollama_url: str,
        on_token, options: dict | None = None, keep_alive: str = "30m",
        max_tool_rounds: int = 3,
    ) -> tuple[str, list[dict]]:
        """Como run_with_tools, pero emitiendo el texto a medida que se genera.

        run_with_tools genera cada ronda sin streaming: con herramientas
        conectadas, el usuario esperaba en silencio toda la generación (14 s en
        un caso real) aunque el modelo no llegara a usar ninguna herramienta.

        Aquí cada ronda va en streaming. El texto se retiene solo mientras pueda
        ser una llamada a herramienta (empieza por "<tool" o "{"); en cuanto es
        claramente texto normal se emite en directo. Si a mitad de respuesta
        aparece una llamada, se deja de emitir desde ese punto.
        """
        import json as _json

        messages = [{"role": "user", "content": prompt}]
        tool_calls_log: list[dict] = []
        sistema = system_prompt + self._tools_system_injection()
        texto = ""
        for ronda in range(max_tool_rounds + 1):
            permite_herramientas = ronda < max_tool_rounds
            texto = ""          # lo generado en esta ronda (sin razonamiento)
            emitido = 0         # cuánto de `texto` ya se ha enviado
            retenido = True     # ¿esperando a saber si es una llamada?
            en_llamada = False  # ya empezó una llamada: nada más de la ronda se muestra
            en_think = False
            try:
                async with httpx.AsyncClient(trust_env=False) as client:
                    async with client.stream("POST", f"{ollama_url}/api/chat", json={
                        "model": model_name,
                        "messages": [{"role": "system", "content": sistema}, *messages],
                        "options": options or {"temperature": 0.3, "num_predict": 4096},
                        "keep_alive": keep_alive,
                        "stream": True,
                    }, timeout=180.0) as resp:
                        resp.raise_for_status()
                        async for linea in resp.aiter_lines():
                            if not linea.strip():
                                continue
                            try:
                                dato = _json.loads(linea)
                            except ValueError:
                                continue
                            token = (dato.get("message") or {}).get("content", "")
                            if not token:
                                continue
                            # El razonamiento interno (<think>) nunca se muestra.
                            if "<think>" in token:
                                en_think = True
                            if en_think:
                                if "</think>" in token:
                                    en_think = False
                                continue
                            texto += token
                            # Tras el inicio de una llamada, todo lo demás de la ronda
                            # es la propia llamada. Antes se volvía a emitir y en el
                            # chat aparecía '"fetch", "input": {…}}</t'.
                            if en_llamada:
                                continue

                            if retenido:
                                inicio = texto.lstrip()
                                parece_llamada = permite_herramientas and (
                                    inicio.startswith("<tool") or inicio.startswith("{")
                                    or "<tool_call>".startswith(inicio[:11]))
                                if parece_llamada and len(inicio) < 400:
                                    continue          # seguir esperando
                                retenido = False
                            # Si aparece una llamada a mitad de texto (en cualquiera
                            # de los dos formatos), cortar ahí. Antes solo se vigilaba
                            # <tool_call> y el formato JSON {"tool": …} se colaba en
                            # el texto visible y en el historial.
                            pendiente = texto[emitido:]
                            marcas = [pendiente.find(m) for m in ("<tool_call>", '{"tool"')
                                      if permite_herramientas and m in pendiente]
                            if marcas:
                                corte = emitido + min(marcas)
                                if corte > emitido:
                                    await on_token(texto[emitido:corte])
                                emitido = corte
                                en_llamada = True
                                continue
                            # Se reservan los últimos caracteres: una marca puede
                            # llegar partida en dos tokens ('{"to' + 'ol"').
                            seguro = len(texto) - 10
                            if seguro > emitido:
                                await on_token(texto[emitido:seguro])
                                emitido = seguro
            except Exception as exc:                      # noqa: BLE001
                logger.error(f"Error en streaming con herramientas: {exc}")
                if not texto:
                    raise

            llamadas = self._extract_tool_calls(texto) if permite_herramientas else []
            if not llamadas:
                # Lo retenido resultó no ser una llamada: se emite ahora.
                if emitido < len(texto):
                    await on_token(texto[emitido:])
                return texto, tool_calls_log
            # Hubo llamada: lo reservado al final no debe verse.

            logger.info(f"MCP ronda {ronda + 1}: {len(llamadas)} herramientas a ejecutar")
            await self._run_tool_calls(llamadas, messages, texto, tool_calls_log)
        return texto, tool_calls_log

    def _tools_system_injection(self) -> str:
        """Añade instrucciones de uso de herramientas al system prompt."""
        tools = self._tools if self._tools is not None else self.manager.tools
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
                        # Sin keep_alive, Ollama descargaba el modelo y cada
                        # respuesta con herramientas podía pagar la recarga.
                        "keep_alive": __import__("os").environ.get("ANDROMEDA_KEEP_ALIVE") or "30m",
                        "stream":  False,
                    },
                    timeout=120.0,
                )
                resp.raise_for_status()
                return resp.json().get("message", {}).get("content", "")
        except Exception as exc:
            logger.error(f"Error llamando al modelo: {exc}")
            return f"Error: {exc}"



# ── Selección de herramientas relevantes ──────────────────────────────────
# Con 6 conectores, cada mensaje inyectaba 52 herramientas: miles de tokens de
# instrucciones antes de empezar, y un modelo de 8B que se confundía y llamaba
# a herramientas con argumentos inventados.

# La escritura de archivos la hace Andromeda con sus bloques ```andromeda:write```,
# que sí funcionan. Ofrecer además las de los conectores provocaba que el modelo
# usara edit_file con argumentos erróneos, fallara, y dijera que lo había hecho.
_ESCRITURA = {"write_file", "edit_file", "create_directory", "move_file", "append_file",
              "delete_file", "make_dir", "create_file"}

_VACIAS = {"the", "and", "for", "with", "that", "this", "from", "into", "your", "you",
           "que", "para", "con", "por", "los", "las", "una", "uno", "del", "est",
           "tool", "tools", "use", "using", "file", "files", "returns", "given"}


def _palabras(texto: str) -> set[str]:
    import re as _re
    texto = _re.sub(r"[_\-]", " ", (texto or "").lower())
    return {w for w in _re.findall(r"[a-záéíóúñ]{4,}", texto) if w not in _VACIAS}


def select_tools(tools, prompt: str, k: int = 6) -> list:
    """Herramientas relevantes para el mensaje (lista vacía = no usar ninguna).

    Coincidencia de palabras entre el mensaje y el nombre y la descripción de
    cada herramienta. Casos directos: una URL activa las de lectura web; pedir
    la hora activa las de tiempo.
    """
    import re as _re
    p = (prompt or "").lower()
    palabras = _palabras(p)
    tiene_url = bool(_re.search(r"https?://", p))
    pide_hora = bool(_re.search(r"\b(hora|time|zona horaria|timezone|uhr|heure)\b", p))
    puntuadas = []
    for t in tools or []:
        nombre = getattr(t, "name", "") or ""
        if nombre in _ESCRITURA:
            continue
        if getattr(t, "server_id", "") == "builtin-fs":
            continue
        texto_t = f"{nombre} {getattr(t, 'description', '') or ''}"
        puntos = len(palabras & _palabras(texto_t))
        # Abrir páginas solo con una URL en el mensaje: la búsqueda web ya la hace
        # Andromeda, y sin esta regla el modelo inventaba URLs para "fetch"
        # ("https://www.media markt.es/ps5-pro") y encadenaba fallos.
        es_web = any(x in nombre.lower() for x in ("fetch", "navigate", "scrape", "browse",
                                                   "puppeteer", "screenshot", "click"))
        if es_web and not tiene_url:
            continue
        if tiene_url and es_web:
            puntos += 3
        if pide_hora and "time" in nombre:
            puntos += 3
        if puntos >= 2 or (puntos >= 1 and len(palabras) <= 4):
            puntuadas.append((puntos, t))
    puntuadas.sort(key=lambda x: -x[0])
    return [t for _, t in puntuadas[:k]]
