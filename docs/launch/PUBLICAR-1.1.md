# Publicar Andromeda 1.1 en GitHub

Todo está preparado. Son unos 20 minutos, sin contar las capturas.

## 1. Antes de subir (10 min)

- [ ] **Prueba el paquete una vez**, en el Mac: abre la app, envía un mensaje, abre
      un archivo desde Artefactos y cambia entre 1.0 y 1.1 (claro y oscuro).
- [x] **Gráficos del README**: ya están generados en `docs/media/` (`chart-*.png`,
      versión clara y oscura). No hace falta ninguna captura. Si cambias datos,
      regenéralos con `python docs/media/generar_graficos_readme.py`.
- [ ] Comprueba que no hay nada personal en el repositorio:
      `git status` no debe mostrar `data/`, `.env`, `*.db` ni `node_modules/`
      (el `.gitignore` ya los excluye).

> El panel de Diagnóstico ya está oculto. Para usarlo tú, arranca con
> `ANDROMEDA_DIAGNOSTICS=1`.

## 2. Subir el código (5 min)

Desde la carpeta de tu repositorio local (el clon de `andromeda-lite`):

```bash
# Sustituir el contenido por la versión nueva (conserva la carpeta .git)
rsync -a --delete --exclude .git /ruta/a/andromeda-lite-github/ ./

git add -A
git status                       # revisa que no entra nada raro
git commit -m "Andromeda 1.1: diseño 1.1, memoria estilo Claude, memoria semántica y Windows"
git push origin main
```

Espera a que la **CI** salga en verde (pestaña Actions): ejecuta los tests en
Linux, macOS y Windows, el análisis del frontend y la compilación.

## 3. Publicar la release (2 min + la compilación)

```bash
git tag -a v1.1.0 -m "Andromeda Lite 1.1.0"
git push origin v1.1.0
```

La etiqueta lanza el workflow **Release**, que compila solo:

- el instalador de **Windows** (`.exe`),
- la app de **macOS** (`.zip`),

y crea la release con el texto de `docs/releases/v1.1.0.md` (instrucciones de
instalación incluidas) más la lista automática de cambios. Tarda unos 15-20 min.

Cuando termine, abre la release en GitHub y comprueba que están los dos archivos.

## 4. Para próximas versiones

1. Sube la versión en `VERSION` y ejecuta `python scripts/sync_version.py`.
2. Añade la entrada en `CHANGELOG.md`.
3. Crea `docs/releases/vX.Y.Z.md` con las notas.
4. `git tag -a vX.Y.Z` y `git push origin vX.Y.Z`.

## 5. Promoción

El post está en `docs/launch/LINKEDIN.md` (sección 1.1). Consejos:

- Publica entre martes y jueves, por la mañana.
- La primera imagen es lo que decide si alguien se para: usa
  `docs/media/chart-memory-speed-dark.png` (la mejora 8× de la memoria) o
  `chart-in-numbers-dark.png`.
- Pon el enlace al repositorio **en el primer comentario**, no en el post:
  LinkedIn reduce el alcance de los posts con enlaces externos.
- Responde a todos los comentarios la primera hora.
