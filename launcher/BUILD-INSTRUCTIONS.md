# Cómo compilar los ejecutables de Andromeda

## Para generar Andromeda.exe (Windows)

Necesitas una máquina Windows con Python instalado.

```powershell
# 1. Instalar PyInstaller
pip install pyinstaller

# 2. Ir a la carpeta launcher
cd "ruta\a\andromeda\launcher"

# 3. Compilar
pyinstaller --onefile --console --name Andromeda andromeda_windows.py

# 4. El .exe estará en: dist\Andromeda.exe
# Copiar dist\Andromeda.exe a la raíz del proyecto andromeda\
```

## Para generar Andromeda.app (macOS)

Necesitas una máquina macOS con Python instalado.

```bash
# 1. Instalar PyInstaller
pip3 install pyinstaller

# 2. Ir a la carpeta launcher
cd /ruta/a/andromeda/launcher

# 3. Compilar
pyinstaller --onefile --console --name Andromeda andromeda_macos.py

# 4. El binario estará en: dist/Andromeda
# Para hacer un .app de macOS:
mkdir -p "Andromeda.app/Contents/MacOS"
cp dist/Andromeda "Andromeda.app/Contents/MacOS/Andromeda"
cat > "Andromeda.app/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>Andromeda</string>
    <key>CFBundleName</key><string>Andromeda</string>
    <key>CFBundleVersion</key><string>1.0.0</string>
</dict>
</plist>
EOF
```

## Script automático (build.py)

```bash
# Windows:
python build.py windows

# macOS:
python build.py macos
```
