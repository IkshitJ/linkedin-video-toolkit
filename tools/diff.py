import sys, difflib
from ax import *
text = open(sys.argv[1]).read().strip()
ed = [e for e, d in walk(root()) if attr(e, "AXRole") == "AXTextArea"][0]
v = attr(ed, "AXValue")
for op in difflib.SequenceMatcher(None, text, v).get_opcodes():
    if op[0] != "equal": print(op[0], repr(text[op[1]:op[2]]), "->", repr(v[op[3]:op[4]]), "ctx:", repr(text[max(0,op[1]-30):op[2]+10]))
