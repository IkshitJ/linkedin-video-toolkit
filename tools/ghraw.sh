#!/bin/zsh
# usage: tools/ghraw.sh <owner/repo> <path-in-repo> <dest-file> [branch]
#
# Saves one file of a GitHub repository, read through the Safari window you are signed in
# to. Meant for PRIVATE repositories you have access to: no token is created or stored.
# For public repositories you do not need this; use git clone.
[ $# -ge 3 ] || { echo "usage: $0 <owner/repo> <path-in-repo> <dest-file> [branch]"; exit 64; }
osascript - "$1" "$2" "${4:-main}" <<'A' > "$3"
on run argv
tell application "Safari"
tell window 1
set t to make new tab with properties {URL:"https://github.com/" & (item 1 of argv) & "/raw/" & (item 3 of argv) & "/" & (item 2 of argv)}
set n to 0
repeat while n < 40
delay 0.5
set n to n + 1
try
if (URL of t) starts with "https://raw.githubusercontent.com" and (do shell script "true") is "" then exit repeat
end try
end repeat
delay 1.2
set s to text of t
close t
end tell
end tell
return s
end run
A
