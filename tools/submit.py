import sys, time
from ax import *
m = [e for e, r, l in find("post", "AXButton") if l.strip() == "Post"]
if len(m) != 1: sys.exit("expected one Post button, found %d" % len(m))
print("enabled:", attr(m[0], "AXEnabled"))
print("press:", AXUIElementPerformAction(m[0], "AXPress"))
