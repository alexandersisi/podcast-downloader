#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

echo "🎧 Podcast Downloader – Installation"
echo "======================================"
echo ""

# ffmpeg für Whisper prüfen
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "⚠️  ffmpeg ist nicht installiert. Wird für Transkription benötigt."
    if command -v brew >/dev/null 2>&1; then
        read -rp "Jetzt via Homebrew installieren? [J/n] " reply
        if [[ ! "$reply" =~ ^[Nn]$ ]]; then
            brew install ffmpeg
        fi
    else
        echo "   Bitte manuell installieren: https://ffmpeg.org (macOS: 'brew install ffmpeg')"
    fi
fi

echo "🐍 Erstelle Virtual Environment..."
python3 -m venv "$VENV_DIR"

echo "📦 Installiere Python-Pakete (inkl. openai-whisper – dauert beim ersten Mal)..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# Wrapper-Skript
if [[ ! -f "$SCRIPT_DIR/run.sh" ]]; then
    echo "🔧 Erstelle Wrapper-Skript..."
    cat > "$SCRIPT_DIR/run.sh" << 'EOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/venv/bin/python3" "$SCRIPT_DIR/main.py" "$@"
EOF
    chmod +x "$SCRIPT_DIR/run.sh"
fi

echo ""
echo "✅ Installation abgeschlossen!"
echo ""
echo "Verwendung:"
echo "  Interaktiver Modus:            $SCRIPT_DIR/run.sh"
echo "  Podcast suchen:                $SCRIPT_DIR/run.sh --search \"Lage der Nation\""
echo "  Alle Episoden + Transkription: $SCRIPT_DIR/run.sh --feed URL --episodes all --transcribe"
echo ""
echo "Tipp: Alias in ~/.zshrc:"
echo "  alias podcast='$SCRIPT_DIR/run.sh'"
