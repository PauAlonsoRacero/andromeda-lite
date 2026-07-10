# Andromeda CLI — Guía de uso

## Instalación

### Windows
```powershell
cd cli
.\install-cli.ps1
# Reinicia PowerShell
```

### macOS / Linux
```bash
cd cli
chmod +x install-cli.sh
./install-cli.sh
# Reinicia el terminal
```

## Uso básico

```bash
# Pregunta directa
andromeda "¿qué hace asyncio.gather()?"

# Con archivo
andromeda "revisa este código" --file main.py

# Con pipe
cat error.log | andromeda "¿qué significa este error?"
git diff | andromeda "escribe el commit message"
cat requirements.txt | andromeda "¿hay dependencias desactualizadas?"

# Generar y ejecutar código
andromeda "escribe un script que liste los procesos que usan más CPU" --execute

# Modo interactivo
andromeda --shell
```

## Uso avanzado

```bash
# Especialista específico
andromeda "optimiza esta query SQL" --specialist software-engineering
andromeda "documenta esta función" --specialist technical-writer

# Con herramientas MCP
andromeda --mcp "lee el archivo README.md y resúmelo"
andromeda --mcp "busca issues abiertos en mi repo"
andromeda --mcp "ejecuta los tests y dime si pasan"

# Output JSON para scripts
andromeda "analiza esto" --json | jq .response

# URL personalizada
andromeda "hola" --url http://mi-servidor:8000
```

## Integración con el flujo de trabajo

### Git hooks
```bash
# .git/hooks/prepare-commit-msg
git diff --cached | andromeda "escribe un commit message conciso" --no-stream
```

### VS Code task
```json
{
  "label": "Ask Andromeda",
  "type": "shell",
  "command": "andromeda \"${input:question}\" --file ${file}"
}
```

### PowerShell aliases útiles
```powershell
# En tu $PROFILE
function review { andromeda "revisa este código y sugiere mejoras" --file $args[0] }
function explain { andromeda "explica este código línea a línea" --file $args[0] }
function test-gen { andromeda "genera tests unitarios completos" --file $args[0] --execute }
function commit-msg { git diff --cached | andromeda "escribe el commit message" }
```

## Variables de entorno

```bash
ANDROMEDA_URL=http://localhost:8000  # URL del backend (default)
GITHUB_TOKEN=ghp_xxx                 # Para servidor MCP de GitHub
BRAVE_API_KEY=xxx                    # Para búsqueda web MCP
```
