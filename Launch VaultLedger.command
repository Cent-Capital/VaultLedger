#!/bin/zsh

# Finder opens .command files in Terminal. Keep every first-run action visible.
set -u

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

PYTHON_BIN=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>/dev/null; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "VaultLedger needs Python 3.11 or newer."
  echo "Opening the official Python download page now."
  /usr/bin/open "https://www.python.org/downloads/macos/"
  echo "Install Python, then double-click Launch VaultLedger again."
  read "?Press Return to close this window…"
  exit 1
fi

"$PYTHON_BIN" "$SCRIPT_DIR/scripts/launch_vaultledger.py"
