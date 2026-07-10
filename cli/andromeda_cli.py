#!/usr/bin/env python3
"""
andromeda_cli.py — CLI de Andromeda estilo Claude Code.

Uso:
  andromeda "explica este error"
  andromeda "revisa este código" --file main.py
  andromeda --shell                    # modo interactivo
  cat error.log | andromeda "¿qué significa?"
  git diff | andromeda "escribe el commit message"
  andromeda "genera tests" --file app.py --execute
  andromeda --mcp "lee el archivo README.md"

Opciones:
  --file PATH        Incluir el contenido de un archivo en el prompt
  --specialist NAME  Usar un especialista específico (default: auto)
  --strategy NAME    Estrategia de fusión (default: auto)
  --model NAME       Modelo Ollama específico
  --execute          Ejecutar el código Python generado automáticamente
  --mcp              Usar herramientas MCP si están disponibles
  --shell            Modo interactivo (REPL)
  --json             Output en JSON (para scripts)
  --no-stream        Sin streaming, esperar respuesta completa
  --url URL          URL del backend (default: http://localhost:8000)
  --version          Mostrar versión
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

VERSION     = "1.0.0"
DEFAULT_URL = "http://localhost:8000"

# ── Colores ANSI ──────────────────────────────────────────────────────────────
def _supports_color():
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty() and os.name != 'nt' or \
           os.environ.get('FORCE_COLOR') == '1'

def _c(code, text): return f"\033[{code}m{text}\033[0m" if _supports_color() else text
def cyan(t):    return _c("36",    t)
def green(t):   return _c("32",    t)
def yellow(t):  return _c("33",    t)
def red(t):     return _c("31",    t)
def dim(t):     return _c("2",     t)
def bold(t):    return _c("1",     t)
def purple(t):  return _c("35",    t)
def blue(t):    return _c("34",    t)

ANDROMEDA_LOGO = f"""
{purple('  ✦')} {bold(blue('ANDROMEDA'))} {dim(f'v{VERSION}')}
  {dim('AI Orchestration Platform')}
"""


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 10) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as exc:
        return {"error": str(exc)}


def _post(url: str, data: dict, timeout: int = 120) -> dict:
    try:
        body = json.dumps(data).encode()
        req  = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        try: return json.loads(exc.read().decode())
        except: return {"error": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"error": str(exc)}


def _stream_post(url: str, data: dict, on_token, on_complete, on_error):
    """Streaming SSE desde el backend."""
    import socket
    try:
        body   = json.dumps(data).encode()
        import http.client
        from urllib.parse import urlparse
        parsed = urlparse(url)
        conn   = http.client.HTTPConnection(parsed.netloc, timeout=130)
        conn.request("POST", parsed.path, body=body,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()

        buffer = ""
        metadata = {}
        while True:
            chunk = resp.read(512)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")
            lines = buffer.split("\n")
            buffer = lines.pop()
            for line in lines:
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    on_complete(metadata)
                    return
                try:
                    chunk_data = json.loads(data_str)
                    if chunk_data.get("is_final"):
                        metadata = chunk_data.get("metadata", {})
                    elif chunk_data.get("content"):
                        on_token(chunk_data["content"], chunk_data.get("specialist_id"))
                except json.JSONDecodeError:
                    pass

        on_complete(metadata)
    except Exception as exc:
        on_error(str(exc))


# ── Formateo de respuestas ────────────────────────────────────────────────────

def _format_markdown_for_terminal(text: str) -> str:
    """Renderizado básico de Markdown en terminal."""
    lines = []
    in_code = False
    code_lang = ""

    for line in text.split("\n"):
        if line.startswith("```"):
            if in_code:
                lines.append(dim("─" * 50))
                in_code = False
            else:
                code_lang = line[3:].strip()
                header = f" {code_lang} " if code_lang else " code "
                lines.append(dim("─" * 50) + cyan(f"[{header.strip()}]"))
                in_code = True
            continue

        if in_code:
            lines.append(yellow(line))
            continue

        # Headers
        if line.startswith("### "): line = bold(cyan(line[4:]))
        elif line.startswith("## "): line = bold(blue(line[3:]))
        elif line.startswith("# "): line = bold(purple(line[2:]))
        # Bold
        line = re.sub(r'\*\*(.+?)\*\*', lambda m: bold(m.group(1)), line)
        # Code inline
        line = re.sub(r'`([^`]+)`', lambda m: yellow(m.group(1)), line)
        # Lists
        if line.startswith("- "):
            line = f"  {dim('•')} {line[2:]}"
        elif line.startswith("  - "):
            line = f"    {dim('◦')} {line[4:]}"

        lines.append(line)

    return "\n".join(lines)


def _extract_code_blocks(text: str) -> list[dict]:
    """Extrae bloques de código de la respuesta."""
    blocks = []
    pattern = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)
    for m in pattern.finditer(text):
        blocks.append({"lang": m.group(1) or "text", "code": m.group(2).strip()})
    return blocks


# ── Comandos principales ──────────────────────────────────────────────────────

def cmd_ask(args, prompt: str, base_url: str):
    """Envía un prompt a Andromeda y muestra la respuesta."""

    # Verificar que el backend está disponible
    health = _get(f"{base_url}/api/health", timeout=5)
    if "error" in health or health.get("status") == "down":
        print(red("✗ Andromeda no está disponible."))
        print(dim(f"  Inicia Andromeda: cd <ruta> && docker-compose up -d"))
        sys.exit(1)

    # Añadir contenido de archivo si se especificó
    if args.file:
        try:
            file_content = Path(args.file).read_text(encoding="utf-8")
            file_ext     = Path(args.file).suffix.lstrip(".")
            prompt += f"\n\n```{file_ext}\n{file_content}\n```"
            if not args.json:
                print(dim(f"  📎 {args.file} ({len(file_content)} chars)"))
        except Exception as exc:
            print(red(f"✗ Error leyendo {args.file}: {exc}"))
            sys.exit(1)

    # Stdin pipe
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        if piped:
            prompt += f"\n\n```\n{piped}\n```"

    if not args.json:
        specialist_info = f" [{args.specialist}]" if args.specialist else ""
        print(dim(f"  → Andromeda{specialist_info}...\n"))

    # Modo MCP
    if args.mcp:
        result = _post(f"{base_url}/api/mcp/chat", {
            "prompt":     prompt,
            "specialist": args.specialist or "generalist",
        })
        if "error" in result:
            print(red(f"✗ {result['error']}"))
            sys.exit(1)

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            response = result.get("response", "")
            print(_format_markdown_for_terminal(response))
            if result.get("tool_calls"):
                print(dim(f"\n  🔧 Herramientas usadas: {', '.join(tc['tool'] for tc in result['tool_calls'])}"))
        return

    # Modo streaming normal
    payload = {
        "prompt":          prompt,
        "strategy":        args.strategy or "auto",
        "stream":          not args.no_stream,
        "parallel_policy": "auto",
    }
    if args.specialist:
        payload["specialists"] = [args.specialist]

    if args.no_stream or args.json:
        payload["stream"] = False
        result = _post(f"{base_url}/api/chat", payload)
        if "error" in result:
            print(red(f"✗ {result.get('message', result['error'])}"))
            sys.exit(1)
        response = result.get("response", "")
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(_format_markdown_for_terminal(response))
    else:
        # Streaming
        full_response = []
        metadata_final = {}
        done_event = threading.Event()

        def on_token(token, spec_id):
            full_response.append(token)
            sys.stdout.write(token)
            sys.stdout.flush()

        def on_complete(meta):
            metadata_final.update(meta or {})
            done_event.set()

        def on_error(err):
            print(red(f"\n✗ Error: {err}"))
            done_event.set()

        t = threading.Thread(
            target=_stream_post,
            args=(f"{base_url}/api/chat", payload, on_token, on_complete, on_error),
            daemon=True
        )
        t.start()
        done_event.wait(timeout=130)

        print()  # newline after streaming

        # Mostrar metadatos
        if metadata_final and not args.json:
            parts = []
            if metadata_final.get("latency_ms"):
                parts.append(f"{int(metadata_final['latency_ms'])}ms")
            if metadata_final.get("strategy_used"):
                parts.append(metadata_final["strategy_used"])
            if metadata_final.get("specialists_used"):
                parts.append(", ".join(metadata_final["specialists_used"]))
            if parts:
                print(dim(f"\n  ◈ {' · '.join(parts)}"))

        response = "".join(full_response)

    # Ejecutar código si se pidió
    if args.execute and response:
        code_blocks = _extract_code_blocks(response)
        python_blocks = [b for b in code_blocks if b["lang"] in ("python", "py", "")]
        if python_blocks:
            code = python_blocks[0]["code"]
            print(dim("\n  ▶ Ejecutando código generado...\n"))
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                tmp_path = f.name
            try:
                result = subprocess.run(
                    [sys.executable, tmp_path],
                    capture_output=True, text=True, timeout=30
                )
                if result.stdout:
                    print(green("stdout:"))
                    print(result.stdout)
                if result.stderr:
                    print(red("stderr:"))
                    print(result.stderr)
                if result.returncode != 0:
                    print(red(f"  Exit code: {result.returncode}"))
            except subprocess.TimeoutExpired:
                print(yellow("  ⚠ Timeout (30s)"))
            finally:
                os.unlink(tmp_path)


def cmd_shell(base_url: str):
    """Modo interactivo REPL."""
    print(ANDROMEDA_LOGO)

    # Verificar conexión
    health = _get(f"{base_url}/api/health", timeout=5)
    if "error" in health or health.get("status") == "down":
        print(red("✗ Backend no disponible. ¿Está corriendo Andromeda?"))
        print(dim("  docker-compose up -d"))
        sys.exit(1)

    active = health.get("specialists", {}).get("active", 0)
    tier   = health.get("hardware_tier", "?")
    print(green(f"  ✓ Conectado — T{tier} · {active} IAs activas"))
    print(dim("  Escribe tu pregunta. Comandos: /help /tools /status /exit\n"))

    history = []
    while True:
        try:
            user_input = input(f"{purple('andromeda')} {dim('›')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(dim("\n  ¡Hasta luego!"))
            break

        if not user_input:
            continue

        # Comandos especiales
        if user_input == "/exit" or user_input == "/quit":
            print(dim("  ¡Hasta luego!"))
            break

        elif user_input == "/help":
            print(f"""
  {bold('Comandos disponibles:')}
    /status    — Estado del sistema
    /tools     — Herramientas MCP disponibles
    /models    — Especialistas activos
    /clear     — Limpiar historial
    /export    — Exportar conversación
    /mcp <prompt> — Usar herramientas MCP
    /exit      — Salir
  
  {bold('Atajos:')}
    ↑/↓        — Historial de comandos
    Ctrl+C     — Cancelar
""")
            continue

        elif user_input == "/status":
            h = _get(f"{base_url}/api/health")
            print(f"  Status: {green(h.get('status','?'))}")
            print(f"  Tier:   T{h.get('hardware_tier','?')}")
            print(f"  IAs:    {h.get('specialists',{}).get('active','?')} activas")
            print(f"  Ollama: {'✓' if h.get('ollama',{}).get('reachable') else '✗'}")
            continue

        elif user_input == "/tools":
            tools = _get(f"{base_url}/api/mcp/tools")
            if not tools.get("tools"):
                print(dim("  Sin herramientas MCP disponibles."))
                print(dim("  Configura servidores en config/mcp_servers.yaml"))
            else:
                for t in tools["tools"]:
                    print(f"  {green(t['name'])} {dim('['+ t['server_id'] +']')} — {t['description']}")
            continue

        elif user_input == "/models":
            models = _get(f"{base_url}/api/models/active")
            for s in models.get("specialists", []):
                print(f"  {green('●')} {s['name']} — {dim(s['model_name'])}")
            continue

        elif user_input == "/clear":
            history.clear()
            print(dim("  Historial limpiado."))
            continue

        elif user_input.startswith("/mcp "):
            mcp_prompt = user_input[5:]
            result = _post(f"{base_url}/api/mcp/chat", {"prompt": mcp_prompt})
            if "error" in result:
                print(red(f"  ✗ {result['error']}"))
            else:
                print(_format_markdown_for_terminal(result.get("response", "")))
                if result.get("tool_calls"):
                    for tc in result["tool_calls"]:
                        print(dim(f"  🔧 {tc['tool']}: {tc.get('result','')[:80]}"))
            continue

        # Pregunta normal
        history.append(user_input)
        print()

        done_event = threading.Event()
        def on_token(token, _): sys.stdout.write(token); sys.stdout.flush()
        def on_complete(meta):
            done_event.set()
            if meta:
                parts = []
                if meta.get("latency_ms"): parts.append(f"{int(meta['latency_ms'])}ms")
                if meta.get("strategy_used"): parts.append(meta["strategy_used"])
                if parts: print(dim(f"\n  ◈ {' · '.join(parts)}"))
        def on_error(err): print(red(f"\n✗ {err}")); done_event.set()

        t = threading.Thread(
            target=_stream_post,
            args=(f"{base_url}/api/chat", {"prompt": user_input, "stream": True}, on_token, on_complete, on_error),
            daemon=True
        )
        t.start()
        done_event.wait(timeout=130)
        print("\n")


def cmd_status(base_url: str, json_output: bool):
    """Muestra el estado del sistema."""
    h = _get(f"{base_url}/api/health")
    m = _get(f"{base_url}/api/mlops/summary")

    if json_output:
        print(json.dumps({"health": h, "mlops": m}, ensure_ascii=False, indent=2))
        return

    print(ANDROMEDA_LOGO)
    status_color = green if h.get("status") == "ok" else yellow if h.get("status") == "degraded" else red
    print(f"  Sistema:  {status_color(h.get('status', 'desconocido'))}")
    print(f"  Tier:     T{h.get('hardware_tier', '?')}")
    specs = h.get("specialists", {})
    print(f"  IAs:      {specs.get('active', 0)}/{specs.get('total', 0)} activas")
    ollama_ok = h.get("ollama", {}).get("reachable", False)
    print(f"  Ollama:   {'✓ conectado' if ollama_ok else red('✗ offline')}")

    if m.get("total_runs"):
        print(f"\n  Requests: {m['total_runs']} total · {m.get('success_rate_pct', 0):.1f}% éxito")
        print(f"  Latencia: {m.get('avg_latency_ms', 0):.0f}ms promedio")

    mcp = _get(f"{base_url}/api/mcp/status")
    if mcp.get("total_tools", 0) > 0:
        print(f"\n  MCP:      {mcp['total_tools']} herramientas · {mcp['total_servers']} servidores")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="andromeda",
        description="Andromeda CLI — AI Orchestration Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  andromeda "¿qué hace este error?"
  andromeda "revisa este código" --file main.py
  andromeda "genera tests unitarios" --file app.py --execute
  git diff | andromeda "escribe el commit message"
  cat logs.txt | andromeda "resume los errores más importantes"
  andromeda --shell
  andromeda --mcp "lista los archivos en el escritorio"
  andromeda status
        """
    )

    parser.add_argument("prompt",          nargs="?",      help="Prompt a enviar")
    parser.add_argument("--file",    "-f", metavar="PATH", help="Incluir archivo en el contexto")
    parser.add_argument("--specialist","-s",metavar="ID",  help="Especialista (generalist, software-engineering...)")
    parser.add_argument("--strategy",      metavar="NAME", help="Estrategia (auto, single, iterative_refine...)")
    parser.add_argument("--model",   "-m", metavar="NAME", help="Modelo Ollama específico")
    parser.add_argument("--execute", "-e", action="store_true", help="Ejecutar código Python generado")
    parser.add_argument("--mcp",           action="store_true", help="Usar herramientas MCP")
    parser.add_argument("--shell",         action="store_true", help="Modo interactivo REPL")
    parser.add_argument("--json",    "-j", action="store_true", help="Output en JSON")
    parser.add_argument("--no-stream",     action="store_true", help="Sin streaming")
    parser.add_argument("--url",           default=os.environ.get("ANDROMEDA_URL", DEFAULT_URL), help="URL del backend")
    parser.add_argument("--version", "-v", action="version", version=f"andromeda {VERSION}")

    # Subcomando 'status'
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        args = parser.parse_args(["--json" if "--json" in sys.argv else "status"])
        cmd_status(DEFAULT_URL, "--json" in sys.argv)
        return

    args = parser.parse_args()

    if args.shell:
        cmd_shell(args.url)
        return

    if not args.prompt:
        # Sin argumentos — intentar leer stdin
        if not sys.stdin.isatty():
            args.prompt = "(ver contenido adjunto)"
        else:
            parser.print_help()
            sys.exit(0)

    cmd_ask(args, args.prompt, args.url)


if __name__ == "__main__":
    main()
