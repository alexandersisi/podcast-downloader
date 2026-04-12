#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/venv/bin/python3" "$SCRIPT_DIR/main.py" "$@"
