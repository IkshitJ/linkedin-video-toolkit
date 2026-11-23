#!/bin/zsh
# usage: tools/post.sh <video.mp4> <text.txt>
#
# Publishes ONE LinkedIn post (a video plus its text) through the Safari window you are
# already signed in to. It presses the same buttons you would press, using macOS
# Accessibility. It never sees your password and stores nothing.
#
# Exit codes: 0 posted | 1 a step failed, nothing was posted | 2 LinkedIn posting limit
#             3 "Post" was pressed but no confirmation appeared (check your profile before retrying)
[ $# -eq 2 ] || { echo "usage: $0 <video.mp4> <text.txt>"; exit 64; }
VIDEO=${1:A}; TEXT=${2:A}          # absolute paths: the file dialog needs one
[ -f "$VIDEO" ] || { echo "no such video: $VIDEO"; exit 64; }
[ -s "$TEXT" ] || { echo "no such text file, or it is empty: $TEXT"; exit 64; }
[[ "$VIDEO" == *[\"\\]* ]] && { echo "the video path must not contain quotes or backslashes"; exit 64; }
cd "${0:A:h}/.."
PY=.venv/bin/python
[ -x $PY ] || { echo "run ./setup.sh first"; exit 1; }

front() { osascript -e 'tell application "Safari" to activate' -e 'delay 0.7' -e 'tell application "System Events" to tell process "Safari" to set frontmost to true' -e 'delay 0.4'; }
osascript -e 'tell application "Safari"
activate
set w to window 1
set current tab of w to (first tab of w whose URL contains "linkedin.com")
set URL of current tab of w to "https://www.linkedin.com/feed/"
end tell' || { echo "NO LINKEDIN TAB: open linkedin.com in the front Safari window and sign in first"; exit 1; }
# Press a button as soon as the page shows it, for up to about a minute (a feed can take a while to load).
press() { for i in $(seq 1 20); do $PY tools/ax.py press "$@" 2>/dev/null && return 0; sleep 3; done; echo "no match: $1"; return 1; }
sleep 4
press "Start a post" AXButton 0 || exit 1
sleep 3
press "Media" AXPopUpButton 0 || exit 1
sleep 3
ok=0
for try in 1 2 3; do
  front
  osascript -e "tell application \"System Events\"
keystroke \"g\" using {command down, shift down}
delay 2
keystroke \"$VIDEO\"
delay 2
key code 36
delay 2.5
key code 36
end tell"
  sleep 5
  $PY tools/ax.py find "Recents" | grep -q Recents || { ok=1; break; }
done
[ $ok = 1 ] || { echo "FILE DIALOG STUCK"; exit 1; }
att=0
for i in $(seq 1 20); do $PY tools/ax.py find "video 0" AXButton | grep -q "video 0" && { att=1; break; }; sleep 6; done
[ $att = 1 ] || { echo "VIDEO NOT ATTACHED"; exit 1; }
press "Next" AXButton 0 || exit 1
sleep 4
$PY tools/fill.py "$TEXT" | head -2
# The text in the editor must match the file exactly before anything is published.
$PY tools/diff.py "$TEXT" | grep -v -E "^insert '' -> '\\\\n'" | grep . && { echo "TEXT MISMATCH"; exit 1; }
[ -n "$DRY_RUN" ] && { echo "DRY RUN: everything is filled in, Post was not pressed"; exit 0; }   # set by run.py --dry-run
$PY tools/submit.py || exit 1
for i in $(seq 1 15); do
  $PY tools/ax.py find "Post successful" | grep -q successful && { echo "POSTED: $TEXT"; exit 0; }
  $PY tools/ax.py find "posting limit" | grep -q limit && { echo "LIMIT REACHED"; exit 2; }
  sleep 8
done
echo "NO CONFIRMATION"; exit 3
