#!/bin/zsh
# One-time setup on macOS and Linux: Python environment in .venv and the voice model in
# video/tts/ (about 350 MB). Safe to run again; it skips what is already there.
# You do not have to run this: `python run.py` does the same setup the first time it runs,
# on Windows too. The work is done by run.py --setup.
cd "${0:A:h}"
if command -v uv >/dev/null; then exec uv run --no-project --python 3.12 run.py --setup; fi
for p in python3.13 python3.12 python3; do command -v $p >/dev/null && exec $p run.py --setup; done
echo "Python 3.12 or newer is needed. Easiest: install uv (https://docs.astral.sh/uv/), then run ./setup.sh again."
exit 1
