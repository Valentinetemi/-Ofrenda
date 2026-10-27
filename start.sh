#!/usr/bin/env bash
# One command to run Ofrenda on this computer.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required." >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --disable-pip-version-check -r requirements.txt

if ! python -c "import mediapipe" >/dev/null 2>&1; then
  echo "MediaPipe did not import. Ghost cutouts will use the colour-key fallback."
  echo "On Ubuntu or Debian: sudo apt install libgl1 libegl1 libglib2.0-0"
fi

exec python -m ofrenda
