#!/bin/zsh
# usage: video/build.sh <video> [voice] [speed]      ->  out/<video>.mp4
#
# Builds one narrated video from script_data.py (the narration) and <video>.html (the scenes):
# voice -> frames -> music and effects -> final MP4. Example: video/build.sh example
# The work is done by build.py, which also runs on Windows: python video/build.py example
[ $# -ge 1 ] || { echo "usage: $0 <video> [voice] [speed]"; exit 64; }
cd "${0:A:h}"
PY=../.venv/bin/python
[ -x $PY ] || { echo "run ./setup.sh first"; exit 1; }
exec $PY build.py "$@"
