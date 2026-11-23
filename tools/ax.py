"""Small accessibility helper for Safari. Usage:
  ax.py find <substring> [role]     list matching elements in the front Safari window
  ax.py press <substring> [role] [index]   AXPress the nth match
  ax.py dump [maxdepth]             dump web-area tree (role, desc, title, value)
"""
import sys, time
from ApplicationServices import *
from AppKit import NSWorkspace

def attr(e, a):
    err, v = AXUIElementCopyAttributeValue(e, a, None)
    return v if err == 0 else None

def safari():
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if app.bundleIdentifier() == "com.apple.Safari":
            ax = AXUIElementCreateApplication(app.processIdentifier())
            AXUIElementSetMessagingTimeout(ax, 3.0)
            return ax
    sys.exit("Safari not running")

def label(e):
    parts = []
    for a in ("AXDescription", "AXTitle", "AXValue", "AXHelp", "AXPlaceholderValue"):
        v = attr(e, a)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return " | ".join(parts)

def walk(e, depth=0, maxdepth=60, budget=[40000]):
    if budget[0] <= 0 or depth > maxdepth:
        return
    budget[0] -= 1
    yield e, depth
    kids = attr(e, "AXChildren") or []
    for k in kids:
        yield from walk(k, depth + 1, maxdepth, budget)

def root():
    app = safari()
    w = attr(app, "AXFocusedWindow") or (attr(app, "AXWindows") or [None])[0]
    if w is None:
        sys.exit("no Safari window")
    return w

def find(sub, role=None):
    sub = sub.lower()
    out = []
    for e, d in walk(root()):
        r = attr(e, "AXRole") or ""
        if role and r != role:
            continue
        l = label(e)
        if sub in l.lower():
            out.append((e, r, l))
    return out

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "find":
        for i, (e, r, l) in enumerate(find(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)):
            print(i, r, attr(e, "AXSubrole") or "", "::", l[:160].replace("\n", " "))
    elif cmd == "press":
        m = find(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else None)
        i = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        if not m:
            sys.exit("no match")
        e, r, l = m[i]
        print("pressing", r, "::", l[:120], "->", AXUIElementPerformAction(e, "AXPress"))
    elif cmd == "dump":
        md = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        for e, d in walk(root(), maxdepth=md):
            r = attr(e, "AXRole") or ""
            l = label(e)
            if l or r in ("AXButton", "AXTextArea", "AXTextField"):
                print("  " * min(d, 20) + r, "::", l[:120].replace("\n", " "))
