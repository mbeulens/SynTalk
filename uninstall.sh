#!/usr/bin/env bash
# Remove the SynTalk launcher and icon. Leaves the project and venv alone.
set -euo pipefail

APP_ID="nl.syntec.SynTalk"
DESKTOP_FILE="$HOME/.local/share/applications/$APP_ID.desktop"
ICON_FILE="$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg"

rm -fv "$DESKTOP_FILE" "$ICON_FILE"

command -v update-desktop-database >/dev/null \
  && update-desktop-database "$HOME/.local/share/applications"
command -v gtk-update-icon-cache >/dev/null \
  && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "SynTalk launcher removed."
