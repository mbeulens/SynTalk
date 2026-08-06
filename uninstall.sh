#!/usr/bin/env bash
# Remove the SynTalk launcher and icon. Leaves the project and venv alone.
set -euo pipefail

APP_ID="nl.syntec.SynTalk"
DESKTOP_FILE="$HOME/.local/share/applications/$APP_ID.desktop"
ICON_FILE="$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg"

rm -fv "$DESKTOP_FILE" "$ICON_FILE"

if command -v update-desktop-database >/dev/null; then
  # A malformed *other* .desktop file in this directory can make this exit
  # non-zero even though ours is already gone; never let that abort the
  # uninstall after rm has already succeeded.
  update-desktop-database "$HOME/.local/share/applications" || true
else
  echo "   note: update-desktop-database absent, skipped"
fi

if command -v gtk-update-icon-cache >/dev/null; then
  gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
else
  echo "   note: gtk-update-icon-cache absent, skipped"
fi

echo "SynTalk launcher removed."
