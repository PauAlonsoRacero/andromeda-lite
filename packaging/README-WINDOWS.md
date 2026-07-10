# Andromeda Lite — Compilar y probar en Windows 11

Guía para generar `Andromeda.exe` y, opcionalmente, un instalador `.exe`.
**Todo esto se ejecuta EN Windows** (PyInstaller genera binarios de la plataforma
en la que corre; no se puede compilar el `.exe` desde Mac/Linux).

## Requisitos previos (una sola vez)

1. **Python 3.11+** → https://www.python.org/downloads/windows/
   - Marca "Add python.exe to PATH" en el instalador.
2. **Node.js 18+** → https://nodejs.org (versión LTS).
3. **WebView2 Runtime** → ya viene en Windows 11. Si tu Windows es muy antiguo
   y la ventana sale en blanco, instálalo gratis desde Microsoft (busca
   "WebView2 Runtime").
4. *(Opcional, solo para el instalador)* **Inno Setup 6** → https://jrsoftware.org/isinfo.php

Comprueba que Python y Node responden:
```powershell
python --version
node --version
```

## Camino A — Compilar la app (lo que quieres para probar)

Desde la raíz del proyecto, en PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

El script hace todo solo: limpia cachés, compila el frontend, instala las
dependencias de Python (incluido pywebview + WebView2), y empaqueta con PyInstaller.

**Resultado:** `dist\Andromeda\Andromeda.exe` — haz doble clic y se abre la app.

> La primera vez Windows SmartScreen avisará ("aplicación no reconocida")
> porque el `.exe` no está firmado. Es normal: pulsa "Más información" →
> "Ejecutar de todas formas". (La firma de código se hará cuando haya ingresos.)

## Camino B — Crear el instalador (para distribuir)

Tras el Camino A, si tienes Inno Setup instalado:

```powershell
iscc packaging\installer.iss
```

**Resultado:** `dist\installer\Andromeda-Setup-<version>.exe` — un único instalador que:
- Instala Andromeda en `Archivos de programa`.
- Instala Ollama en silencio si no lo tienes (necesitas poner `OllamaSetup.exe`
  en `packaging\redist\` antes; descárgalo de https://ollama.com/download).
  Si no incluyes ese archivo, comenta las dos líneas de Ollama en `installer.iss`.
- Crea accesos directos y permite desinstalar limpiamente (preguntando si
  borrar también tus datos de `%APPDATA%\Andromeda`).

## Antes de usar Andromeda: ten Ollama corriendo

Andromeda es la app; **Ollama es el motor** que ejecuta los modelos.
1. Instala Ollama (https://ollama.com/download) — o deja que lo haga el instalador.
2. Descarga al menos un modelo:
   ```powershell
   ollama pull llama3.2:3b
   ```
3. Abre Andromeda. Si Ollama no está corriendo, la app te lo dirá con un aviso
   claro y un botón para descargarlo (no un error feo).

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| Ventana en blanco al abrir | Falta WebView2 Runtime | Instálalo (gratis, Microsoft) |
| "python no se reconoce" | Python no está en PATH | Reinstala marcando "Add to PATH" |
| Build falla en frontend | Node antiguo | Actualiza a Node 18+ LTS |
| SmartScreen bloquea el .exe | Sin firma de código | "Más información" → "Ejecutar igualmente" |
| El chat no responde | Ollama no está corriendo | Abre Ollama / `ollama serve` |
| "no model available" | No hay modelos | `ollama pull llama3.2:3b` |

## Notas técnicas verificadas

- **WebView2**: pywebview usa el motor EdgeChromium (WebView2) en Windows, que
  viene preinstalado en Windows 11. El spec incluye los `hiddenimports` de
  pywebview para Windows (`edgechromium`, `winforms`, `clr`) para que el motor
  se empaquete correctamente.
- **Empaquetado validado**: la estructura del bundle (spec, hiddenimports, datas)
  se ha verificado compilando con PyInstaller; el backend embebido arranca y
  responde en su puerto dentro del binario. Lo único específico de cada SO es el
  motor gráfico de la ventana (WebView2 en Windows, WKWebView en macOS), presente
  de serie en ambos sistemas actualizados.
- **Datos del usuario**: se guardan en `%APPDATA%\Andromeda` (memorias,
  conversaciones, ajustes). Sobreviven a actualizaciones; solo se borran si lo
  pides al desinstalar.

## Pendiente para "release pro"

- [ ] Firmar el `.exe` y el instalador (certificado de código)
- [ ] CI con GitHub Actions que compile en `windows-latest` y publique el Setup
- [ ] Probar en una VM Windows limpia (sin Python/Node) que el instalador funciona
