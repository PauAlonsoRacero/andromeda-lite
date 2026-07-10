# Andromeda — Instalador Profesional

## Cómo usar

1. Clic derecho en `Andromeda-Setup.ps1`
2. Selecciona **"Ejecutar como Administrador"**
3. Sigue las instrucciones en pantalla

El instalador te preguntará qué módulos instalar y lo hace todo automáticamente.

## Qué instala

| Módulo | Obligatorio | Qué hace |
|--------|-------------|----------|
| **Core** | ✅ Sí | Docker Engine, Ollama, Andromeda completo, acceso directo en Escritorio, autostart con Windows |
| **Métricas** | Opcional | Dashboard MLOps, traces, rendimiento |
| **Modelos** | Opcional | Descarga ~6GB de modelos de IA y los configura automáticamente |

## Dónde se instala

- Programa: `C:\Program Files\Andromeda\`
- Datos: `C:\Users\TuUsuario\AppData\Roaming\Andromeda\`
- Acceso directo: Escritorio

## Después de instalar

Doble clic en el icono **Andromeda** del Escritorio. Se abre el navegador en `http://localhost`.

## Desinstalar

```powershell
cd "C:\Program Files\Andromeda"
docker-compose down
docker rmi andromeda-backend andromeda-frontend
Unregister-ScheduledTask -TaskName "Andromeda AI Autostart" -Confirm:$false
Remove-Item "C:\Program Files\Andromeda" -Recurse -Force
Remove-Item "$env:DESKTOP\Andromeda.lnk"
```
