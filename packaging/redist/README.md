# redist/ — Binarios de terceros para el instalador

Coloca aquí **OllamaSetup.exe** si quieres que el instalador de Andromeda
instale Ollama automáticamente cuando el usuario no lo tenga.

Descárgalo de: https://ollama.com/download/OllamaSetup.exe

Este archivo NO se sube al repositorio (ver .gitignore) porque pesa mucho y
tiene su propia licencia. El instalador (`installer.iss`) lo busca aquí.

Si NO lo incluyes, comenta en `packaging/installer.iss`:
- La línea `Source: "redist\OllamaSetup.exe"...` en la sección [Files]
- La línea de Ollama en la sección [Run]
...y el instalador simplemente no instalará Ollama (el usuario lo hará a mano).
