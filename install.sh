#!/usr/bin/env bash
# Install SynTalk into a local venv and register the desktop launcher.
# Idempotent. No sudo. Re-run after pulling changes.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID="nl.syntec.SynTalk"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

cd "$PROJECT_DIR"

command -v uv >/dev/null || { echo "install: uv is required" >&2; exit 1; }

# PyGObject comes from the system; the venv must be able to see it.
# --python 3.12 is required: an unpinned `uv venv` can resolve to a newer
# interpreter (e.g. 3.14) that has no system `gi`, silently breaking the app.
# --clear makes re-runs idempotent: `uv venv` otherwise refuses to touch an
# existing venv, and this also self-heals a stale venv on the wrong Python.
echo "==> creating venv"
uv venv --system-site-packages --python 3.12 --clear

echo "==> installing syntalk"
uv pip install -e .

BIN="$PROJECT_DIR/.venv/bin/syntalk"
[[ -x $BIN ]] || { echo "install: $BIN missing after install" >&2; exit 1; }

echo "==> verifying runtime"
"$PROJECT_DIR/.venv/bin/python" -c "
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk
from piper import PiperVoice
print('   GTK', Gtk.get_major_version(), Gtk.get_minor_version(), '+ libadwaita + piper OK')
"

for tool in ffmpeg aplay; do
  command -v "$tool" >/dev/null || echo "   warning: $tool not found; some features will fail"
done

echo "==> installing launcher"
mkdir -p "$DESKTOP_DIR" "$ICON_DIR"
sed "s|^Exec=.*|Exec=$BIN|" "data/$APP_ID.desktop" > "$DESKTOP_DIR/$APP_ID.desktop"
cp "data/icons/hicolor/scalable/apps/$APP_ID.svg" "$ICON_DIR/$APP_ID.svg"

if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$DESKTOP_DIR"
else
  echo "   note: update-desktop-database absent, skipped"
fi

if command -v gtk-update-icon-cache >/dev/null; then
  gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
else
  echo "   note: gtk-update-icon-cache absent, skipped"
fi

echo
echo "SynTalk installed. Launch it from the GNOME overview, or run:"
echo "  $BIN"
