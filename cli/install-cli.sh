#!/usr/bin/env bash
# ============================================================
#  ANDROMEDA CLI — Instalador para macOS / Linux
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.andromeda/bin"
CLI_SRC="$SCRIPT_DIR/andromeda_cli.py"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo ""
echo -e "${CYAN}  ✦ Instalando Andromeda CLI...${NC}"
echo ""

# Verificar Python 3
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}  [ERROR] Python 3 no encontrado.${NC}"
    echo "  Instala con: brew install python3  (macOS)"
    echo "               sudo apt install python3  (Ubuntu)"
    exit 1
fi
echo -e "${GREEN}  [OK] $(python3 --version)${NC}"

# Crear directorio
mkdir -p "$BIN_DIR"

# Copiar CLI
cp "$CLI_SRC" "$BIN_DIR/andromeda_cli.py"

# Crear wrapper ejecutable
cat > "$BIN_DIR/andromeda" << 'WRAPPER'
#!/usr/bin/env bash
python3 "$HOME/.andromeda/bin/andromeda_cli.py" "$@"
WRAPPER
chmod +x "$BIN_DIR/andromeda"

# Añadir al PATH en .bashrc y .zshrc
for RCFILE in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.bash_profile"; do
    if [ -f "$RCFILE" ] && ! grep -q "andromeda/bin" "$RCFILE" 2>/dev/null; then
        echo '' >> "$RCFILE"
        echo '# Andromeda CLI' >> "$RCFILE"
        echo "export PATH=\"\$HOME/.andromeda/bin:\$PATH\"" >> "$RCFILE"
        echo -e "${GREEN}  [OK] PATH añadido a $RCFILE${NC}"
    fi
done

# Symlink en /usr/local/bin si hay permisos
if [ -w "/usr/local/bin" ]; then
    ln -sf "$BIN_DIR/andromeda" /usr/local/bin/andromeda
    echo -e "${GREEN}  [OK] Symlink creado en /usr/local/bin/andromeda${NC}"
fi

echo ""
echo -e "${GREEN}  ╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}  ║   ✦  Andromeda CLI instalado               ║${NC}"
echo -e "${GREEN}  ║                                              ║${NC}"
echo -e "${GREEN}  ║   Uso:                                      ║${NC}"
echo -e "${GREEN}  ║     andromeda \"explica este error\"          ║${NC}"
echo -e "${GREEN}  ║     andromeda --shell                       ║${NC}"
echo -e "${GREEN}  ║     andromeda --help                        ║${NC}"
echo -e "${GREEN}  ╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}  Reinicia tu terminal para usar 'andromeda'${NC}"
echo ""

# Activar en la sesión actual
export PATH="$BIN_DIR:$PATH"
echo -e "${GREEN}  PATH activado para esta sesión${NC}"

# Probar
if python3 "$BIN_DIR/andromeda_cli.py" status --json &>/dev/null; then
    echo -e "${GREEN}  [OK] CLI funciona correctamente${NC}"
else
    echo -e "${YELLOW}  [!] CLI instalado pero Andromeda puede no estar corriendo${NC}"
fi
echo ""
