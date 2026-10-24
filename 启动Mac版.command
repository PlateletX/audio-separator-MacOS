#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  print -u2 "此启动器仅适用于 macOS。"
  exit 1
fi

BREW="$(command -v brew || true)"
if [[ -z "$BREW" ]]; then
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [[ -x "$candidate" ]]; then BREW="$candidate"; break; fi
  done
fi
if [[ -z "$BREW" ]]; then
  print -u2 "未找到 Homebrew。请先安装 Homebrew，再运行此启动器。"
  print -u2 "https://brew.sh/"
  exit 1
fi

PYTHON="$(command -v python3.12 || true)"
if [[ -z "$PYTHON" ]]; then
  print "正在安装 Python 3.12..."
  "$BREW" install python@3.12
  PYTHON="$("$BREW" --prefix python@3.12)/bin/python3.12"
fi

if [[ -z "$PYTHON" ]]; then
  print -u2 "未找到可用的 Python 3.12。"
  exit 1
fi

"$PYTHON" macos_setup.py --python "$PYTHON"
export QT_PLUGIN_PATH="$ROOT/.runtime/macos/lib/python3.12/site-packages/PySide6/Qt/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="$QT_PLUGIN_PATH/platforms"
exec "$ROOT/.runtime/macos/bin/python" "$ROOT/app.pyw"
