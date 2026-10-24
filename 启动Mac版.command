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
  print "正在安装 Python 3.12 与 Tk 支持（Homebrew）..."
  "$BREW" install python@3.12 python-tk@3.12
  PYTHON="$("$BREW" --prefix python@3.12)/bin/python3.12"
fi

if ! "$PYTHON" -c 'import tkinter' >/dev/null 2>&1; then
  print "正在安装 Python 3.12 的 Tk 支持..."
  "$BREW" install python@3.12 python-tk@3.12
  PYTHON="$("$BREW" --prefix python@3.12)/bin/python3.12"
fi

if ! "$PYTHON" -c 'import tkinter' >/dev/null 2>&1; then
  print -u2 "Python 3.12 的 tkinter 不可用。请运行：brew reinstall python@3.12 python-tk@3.12"
  exit 1
fi

"$PYTHON" macos_setup.py --python "$PYTHON"
exec "$ROOT/.runtime/macos/bin/python" "$ROOT/app.pyw"
