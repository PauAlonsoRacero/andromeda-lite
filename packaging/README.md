# Empaquetado de Andromeda

Scripts para construir Andromeda en cada plataforma. **Cada binario se construye
en su propio sistema operativo** (no se puede compilar un .app de macOS en
Windows, ni viceversa).

Antes de cualquier script: ten Python 3.11+ y Node 18+ instalados.

## macOS → `Andromeda.app`
```bash
bash packaging/build_macos.sh
```
Resultado en `dist/Andromeda.app`. Para distribuirla fuera de tu Mac hay que
firmarla y notarizarla con un Apple Developer ID (instrucciones al final del script).

## Windows 11 → instalador `.exe`
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```
Esto genera `dist\Andromeda\` (la app empaquetada). Para el **instalador único que
también instala Ollama**:

1. Instala [Inno Setup](https://jrsoftware.org/isinfo.php).
2. Descarga `OllamaSetup.exe` desde https://ollama.com/download/windows y ponlo
   en `packaging\redist\OllamaSetup.exe`.
3. Compila el instalador:
   ```powershell
   iscc packaging\installer.iss
   ```
   Resultado: `packaging\Output\Andromeda-Setup.exe` — un único ejecutable que
   instala Andromeda y Ollama (si falta) desde cero.

> Node y `uv` (para herramientas MCP) son opcionales y solo se necesitan si el
> usuario activa MCPs. El instalador no los incluye por defecto para no inflarlo;
> Andromeda avisa dentro de la app si faltan.

## Linux → `Andromeda.AppImage`
```bash
# Dependencias del sistema (Debian/Ubuntu):
sudo apt install python3-gi gir1.2-webkit2-4.1 libgirepository1.0-dev
bash packaging/build_linux.sh
```
Genera `dist/Andromeda/`. Para un AppImage portable, usa
[appimagetool](https://github.com/AppImage/AppImageKit) sobre esa carpeta.

## Nota sobre dependencias

Andromeda necesita **Ollama** para la inferencia local. En Windows el instalador
puede incluirlo; en macOS/Linux pídele al usuario instalarlo desde
https://ollama.com (es un paso de un clic) o añádelo al script de build.
