import sys, time
from ax import *
import Quartz
sub, role = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None)
idx = int(sys.argv[3]) if len(sys.argv) > 3 else 0
m = find(sub, role)
if not m: sys.exit("no match")
e = m[idx][0]
ok1, p = AXValueGetValue(attr(e, "AXPosition"), kAXValueCGPointType, None)
ok2, s = AXValueGetValue(attr(e, "AXSize"), kAXValueCGSizeType, None)
x, y = p.x + s.width / 2, p.y + s.height / 2
print("element", m[idx][2][:60], "at", round(x), round(y), "size", round(s.width), round(s.height))
if "--dry" in sys.argv: sys.exit()
for t in (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
    ev = Quartz.CGEventCreateMouseEvent(None, t, (x, y), Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
    time.sleep(0.15)
