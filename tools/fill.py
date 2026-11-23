import sys, time, subprocess
from ax import *
text = open(sys.argv[1]).read().strip()
def editor():
    for e, d in walk(root(), budget=[40000]):
        if attr(e, "AXRole") == "AXTextArea":
            return e
ed = editor()
if ed is None: sys.exit("no editor")
subprocess.run(["osascript", "-e", 'tell application "Safari" to activate'])
time.sleep(0.5)
print("focus", AXUIElementSetAttributeValue(ed, "AXFocused", True))
time.sleep(0.5)
# Accessibility focus alone does not always put the cursor in LinkedIn's editor, and then the paste
# goes nowhere. A real click inside the box does.
import Quartz
ok1, pos = AXValueGetValue(attr(ed, "AXPosition"), kAXValueCGPointType, None)
ok2, size = AXValueGetValue(attr(ed, "AXSize"), kAXValueCGSizeType, None)
if ok1 and ok2:
    for kind in (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, Quartz.CGEventCreateMouseEvent(None, kind, (pos.x + 60, pos.y + size.height / 2), Quartz.kCGMouseButtonLeft))
        time.sleep(0.15)
    time.sleep(0.5)
subprocess.run(["pbcopy"], input=text.encode())
subprocess.run(["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'])
time.sleep(3)
ed = editor()
v = attr(ed, "AXValue") or ""
print("editor chars:", len(v), "expected:", len(text))
print(v[:200]); print("..."); print(v[-200:])
