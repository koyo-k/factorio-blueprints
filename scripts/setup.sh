#!/usr/bin/env bash
# One-time setup: Python deps, headless Factorio, and vanilla (base mod only) game data.
# Safe to re-run. Needs network access to factorio.com and dl.factorio.com for the download;
# without it the static tools still work using the data bundled with factorio-draftsman.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

FACTORIO_HOME="${FACTORIO_HOME:-$HOME/.cache/factorio-headless}"
FACTORIO_VERSION="${FACTORIO_VERSION:-stable}"

uv sync --quiet

if [ ! -x "$FACTORIO_HOME/factorio/bin/x64/factorio" ]; then
  mkdir -p "$FACTORIO_HOME"
  if curl -fsSL --retry 3 -o "$FACTORIO_HOME/headless.tar.xz" \
      "https://factorio.com/get-download/$FACTORIO_VERSION/headless/linux64"; then
    tar -xf "$FACTORIO_HOME/headless.tar.xz" -C "$FACTORIO_HOME"
    rm -f "$FACTORIO_HOME/headless.tar.xz"
  else
    echo "WARNING: could not download headless Factorio; 'fbp sim' will not run." >&2
  fi
fi

# Vanilla only: the DLC mods ship with both draftsman and the headless build.
DATA_ARGS=()
if [ -d "$FACTORIO_HOME/factorio/data" ]; then
  DATA_ARGS=(-p "$FACTORIO_HOME/factorio/data")   # use the real game's data so versions match
fi
.venv/bin/draftsman "${DATA_ARGS[@]}" disable space-age quality elevated-rails recycler >/dev/null
.venv/bin/draftsman "${DATA_ARGS[@]}" update >/dev/null
.venv/bin/fbp info
