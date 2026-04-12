#!/bin/bash
set -e

INSTALL_DIR="$HOME/Development/podcast-downloader"
VENV_DIR="$INSTALL_DIR/venv"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🎧 Podcast Downloader – Installation"
echo "======================================"
echo ""

echo "📁 Erstelle Installationsverzeichnis..."
mkdir -p "$INSTALL_DIR"

echo "🐍 Erstelle Virtual Environment..."
python3 -m venv "$VENV_DIR"

echo "📦 Installiere Python-Pakete..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install requests feedparser rich -q

echo "📄 Kopiere Skripte..."
cp "$SCRIPT_DIR/main.py" "$INSTALL_DIR/"

# Wrapper-Skript
echo "🔧 Erstelle Wrapper-Skript..."
cat > "$INSTALL_DIR/run.sh" << 'EOF'
#!/bin/bash
SCRIPT_DIR="$HOME/Development/podcast-downloader"
"$SCRIPT_DIR/venv/bin/python3" "$SCRIPT_DIR/main.py" "$@"
EOF
chmod +x "$INSTALL_DIR/run.sh"

echo ""
echo "✅ Installation abgeschlossen!"
echo ""
echo "Verwendung:"
echo "  Interaktiver Modus:  $INSTALL_DIR/run.sh"
echo "  Podcast suchen:      $INSTALL_DIR/run.sh --search \"Lage der Nation\""
echo "  Feed herunterladen:  $INSTALL_DIR/run.sh --feed URL --episodes all"
echo ""
echo "Tipp: Erstelle einen Alias in deiner ~/.zshrc:"
echo "  alias podcast='$INSTALL_DIR/run.sh'"
