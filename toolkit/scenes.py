"""A storyboard (plain JSON) -> the narration script and the animated scenes of one video.

The storyboard is the one format every writer produces: the AI model called by toolkit/writer.py,
a coding agent following AGENTS.md, or the no-AI fallback in toolkit/story.py. check() says what is
wrong with one, render() turns a correct one into what video/build.py needs.

FORMAT below is the description handed to whoever writes the storyboard.
"""
import html
import pathlib
import re
import zlib

from .story import speak

IMAGES = (".png", ".jpg", ".jpeg", ".webp")
CLIPS = (".mp4", ".mov", ".webm", ".gif")

FORMAT = """A storyboard is one JSON object:

{
  "repo": "owner/name",
  "caption": "the full LinkedIn post text",
  "scenes": [ {"type": "...", "say": ["..."], "cap": ["..."], ...}, ... ]
}

Every scene has:
  "say"  1 to 5 short phrases, spoken by the voice one after another. Write for the ear: short
         sentences, no symbols, no URLs, numbers the way they are said.
  "cap"  the same phrases as they should be READ on screen (same number of items as "say").
         Usually identical to "say"; differs when the spoken form is spelled out, for example
         say "three times faster", cap "3x faster".

Scene types and their extra fields ("" is allowed where a field is marked optional):

  title     "kicker" (optional, a few words above the title), "title" (up to 40 characters),
            "subtitle" (optional, one line). The name card of the project.
  footage   "src": the file name of one footage item from the brief, "label" (optional, a few
            words). Shows a real screenshot or recording of the product, filling the frame. A tall
            screenshot scrolls, a recording plays. Only use files that exist, and only describe
            what is really visible in them.
  points    "heading", "points": 2 to 4 short statements (each up to 90 characters). They appear one
            by one, in step with the phrases after the first.
  steps     "heading", "steps": 2 to 4 objects {"title", "text"} shown as numbered cards in a row:
            how it works, or how to use it.
  stat      "value": a whole number that counts up, "prefix" and "suffix" (optional, such as "$" or
            "%" or "x"), "label": what the number is. Only real numbers from the brief.
  bars      "heading", "bars": 2 to 5 objects {"name", "value"} with value 0 to 100, for example the
            language split.
  terminal  "heading" (optional), "lines": 1 to 4 real commands or code lines taken from the README,
            typed out one by one. Never invent commands or output.
  statement "lines": 1 to 3 very short lines (up to 28 characters each) shown huge, one per phrase, and
            "accent" (optional): one word or number in them to colour. For the hook, a turn in the story,
            or the one sentence people should remember.
  compare   "heading" (optional), "left" and "right": objects {"title", "items": 1 to 4 short items}.
            Left is the old or slow way, right is the new way: before and after, by hand and automated.
  console   "heading" (optional), "lines": 2 to 9 lines of real terminal output, shown appearing line by
            line in a terminal window. Copy real output; you may leave lines out, never invent them.
  close     "heading", "title", "link" (optional, such as github.com/owner/name). Always the last scene.

Rules:
  - 6 to 10 scenes, 90 to 170 spoken words in total (about 35 to 65 seconds). Short scenes: most have
    one or two phrases. A feed video that drags is skipped.
  - The first three seconds decide everything. Open with the result, a number, or a claim that sounds
    impossible, in a statement or footage scene that works with the sound off. Not with the name.
  - Show the product working (footage, console) before explaining it. Then how it works, then proof
    (numbers), then where to find it. Change the kind of scene every time: never two alike in a row.
  - If the project automates something, show the before and after (compare), and show the automation
    actually happening (footage of it running).
  - Use every good footage item at least once. Use the same file at most twice.
  - Everything must be true and come from the brief. No invented features, numbers, users or quotes.
  - No emoji and no "|" anywhere.

The caption is what people read on LinkedIn:
  - First line: a hook of at most 140 characters that makes sense on its own.
  - Then 3 to 6 short paragraphs or "- " list lines: the problem, what was built, two or three concrete
    details (how it works, numbers, design choices), and what was learned or what comes next.
  - Then the repository link on its own line (leave it out for a private repository).
  - Last line: 5 to 8 hashtags, CamelCase, specific to the project before general ones.
  - 600 to 1300 characters. Plain text: no markdown, no emoji, first person, no hype words.
"""

SAY = {"type": "array", "items": {"type": "string"}}
TEXT = {"type": "string"}


def _scene(kind, **fields):
    props = dict({"type": {"const": kind}, "say": SAY, "cap": SAY}, **fields)
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _items(**fields):
    return {"type": "array", "items": {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}}


SIDE = {"type": "object", "properties": {"title": TEXT, "items": SAY}, "required": ["title", "items"], "additionalProperties": False}
SCHEMA = {  # the same format as a JSON schema, for a model's structured output
    "type": "object", "additionalProperties": False, "required": ["repo", "caption", "scenes"],
    "properties": {"repo": TEXT, "caption": TEXT, "scenes": {"type": "array", "items": {"anyOf": [
        _scene("title", kicker=TEXT, title=TEXT, subtitle=TEXT),
        _scene("footage", src=TEXT, label=TEXT),
        _scene("points", heading=TEXT, points=SAY),
        _scene("steps", heading=TEXT, steps=_items(title=TEXT, text=TEXT)),
        _scene("stat", value={"type": "integer"}, prefix=TEXT, suffix=TEXT, label=TEXT),
        _scene("bars", heading=TEXT, bars=_items(name=TEXT, value={"type": "integer"})),
        _scene("terminal", heading=TEXT, lines=SAY),
        _scene("statement", lines=SAY, accent=TEXT),
        _scene("compare", heading=TEXT, left=SIDE, right=SIDE),
        _scene("console", heading=TEXT, lines=SAY),
        _scene("close", heading=TEXT, title=TEXT, link=TEXT),
    ]}}},
}
NEEDS = {"title": ("title",), "footage": ("src",), "points": ("heading", "points"), "steps": ("heading", "steps"),
         "stat": ("value", "label"), "bars": ("heading", "bars"), "terminal": ("lines",), "close": ("heading", "title"),
         "statement": ("lines",), "compare": ("left", "right"), "console": ("lines",)}
LISTS = {"points": ("points", 2, 4), "steps": ("steps", 2, 4), "bars": ("bars", 2, 5), "terminal": ("lines", 1, 4),
         "statement": ("lines", 1, 3), "console": ("lines", 2, 9)}


def check(story, footage_dir=None):
    """-> a list of problems, in words the writer can act on. Empty when the storyboard can be built."""
    if not isinstance(story, dict):
        return ["the storyboard must be a JSON object"]
    problems = []
    caption, scenes = story.get("caption"), story.get("scenes")
    if not isinstance(caption, str) or not caption.strip():
        problems.append('"caption" is missing or empty')
    elif len(caption) > 3000:
        problems.append("the caption is %d characters; LinkedIn allows 3000" % len(caption))
    if not isinstance(scenes, list) or not 2 <= len(scenes) <= 10:
        return problems + ['"scenes" must be a list of 2 to 10 scenes']
    words = 0
    for i, s in enumerate(scenes, 1):
        kind = s.get("type") if isinstance(s, dict) else None
        where = "scene %d (%s)" % (i, kind)
        if kind not in NEEDS:
            problems.append("scene %d: unknown type %r; use one of %s" % (i, kind, ", ".join(NEEDS)))
            continue
        say, cap = s.get("say"), s.get("cap") or s.get("say")
        if not isinstance(say, list) or not 1 <= len(say) <= 5 or not all(isinstance(p, str) and p.strip() for p in say):
            problems.append('%s: "say" must be 1 to 5 non-empty phrases' % where)
            continue
        if not isinstance(cap, list) or len(cap) != len(say) or not all(isinstance(p, str) and p.strip() for p in cap):
            problems.append('%s: "cap" must have exactly as many non-empty phrases as "say" (%d)' % (where, len(say)))
        problems += ["%s: phrase %d is %d characters; keep phrases under 170" % (where, j, len(p)) for j, p in enumerate(say, 1) if len(p) > 170]
        words += sum(len(p.split()) for p in say)
        problems += ['%s: "%s" is missing' % (where, f) for f in NEEDS[kind] if s.get(f) in (None, "", [])]
        if kind in LISTS:
            field, low, high = LISTS[kind]
            if isinstance(s.get(field), list) and not low <= len(s[field]) <= high:
                problems.append('%s: "%s" must have %d to %d items, not %d' % (where, field, low, high, len(s[field])))
        if kind == "stat" and not isinstance(s.get("value"), (int, float)):
            problems.append('%s: "value" must be a number' % where)
        if kind == "bars" and not all(isinstance(b, dict) and isinstance(b.get("value"), (int, float)) and 0 <= b["value"] <= 100 and b.get("name")
                                      for b in s.get("bars") or []):
            problems.append('%s: every bar needs a "name" and a "value" from 0 to 100' % where)
        if kind == "steps" and not all(isinstance(b, dict) and b.get("title") for b in s.get("steps") or []):
            problems.append('%s: every step needs a "title"' % where)
        if kind == "compare" and not all(isinstance(s.get(side), dict) and s[side].get("title") and isinstance(s[side].get("items"), list)
                                         and 1 <= len(s[side]["items"]) <= 4 for side in ("left", "right")):
            problems.append('%s: "left" and "right" each need a "title" and 1 to 4 "items"' % where)
        if kind == "footage" and s.get("src"):
            name = pathlib.PurePath(str(s["src"])).name
            if not name.lower().endswith(IMAGES + CLIPS):
                problems.append("%s: %r is not an image or a video file" % (where, s["src"]))
            elif footage_dir is not None and not (pathlib.Path(footage_dir) / name).is_file():
                have = sorted(p.name for p in pathlib.Path(footage_dir).glob("*") if p.is_file()) if pathlib.Path(footage_dir).is_dir() else []
                problems.append("%s: there is no footage file %r; the files are: %s" % (where, name, ", ".join(have) or "(none)"))
    if scenes and isinstance(scenes[0], dict) and scenes[0].get("type") not in ("title", "statement", "footage"):
        problems.append("the first scene must be a title, statement or footage scene")
    if scenes and isinstance(scenes[-1], dict) and scenes[-1].get("type") != "close":
        problems.append("the last scene must be of type close")
    if words > 240:
        problems.append("the narration is %d words; keep it under 200 (about 80 seconds)" % words)
    return problems


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="video-size" content="1920x1080">
<link rel="stylesheet" href="../style.css"></head><body>
<!-- Generated by run.py for {repo}. To change the video, edit {vid}/story.json and run: python run.py --story video/build/{vid}/story.json -->
<div id="stage">
<div class="blob" id="b1"></div><div class="blob" id="b2"></div><div class="blob" id="b3"></div><div id="grid"></div>
{scenes}
<div id="cap"><span></span></div><div id="prog"></div><div id="fade"></div>
</div>
<script src="{vid}_timeline.js"></script><script src="../engine.js"></script>
</body></html>
"""
COLORS = ("var(--fable)", "var(--local)", "var(--good)", "var(--ink)", "var(--dim)")
NUMS = ("f", "l", "m", "")


def fit(text, base, width=1620, ratio=0.58, floor=44):
    """Font size that keeps `text` on one line of `width` pixels."""
    return max(floor, min(base, int(width / (ratio * max(len(text), 1)))))


def _at(i, items, phrases):
    """When item i of a list appears: one per phrase after the intro when there are enough phrases,
    one per phrase when they match, otherwise one after another during the last phrase."""
    if phrases > items:
        return "p%d" % (i + 1)
    if phrases == items:
        return "p%d" % i
    return "p%d+%.1f" % (phrases - 1, 0.3 + 0.6 * i)


def render(story, vid, clips=None):
    """-> {"segments", "cues", "music", "html"}. clips: {file name: (number of frames, frames per second)} for recordings
    already cut into frames in <vid>/footage/<name>.frames/ (see toolkit/material.py)."""
    e, clips = html.escape, clips or {}
    segments, cues, sections = [], [], []
    for n, s in enumerate(story["scenes"], 1):
        sid, kind = "s%d" % n, s["type"]
        say = [speak(p.replace("|", ", ")) for p in s["say"]]
        cap = [re.sub(r"\s+", " ", p.replace("|", ", ")).strip() for p in (s.get("cap") or s["say"])]
        k = len(say)
        pad = ""
        if kind == "title":
            body = ('  <div class="tag" data-at="0.3" data-fx="fade">%s</div>\n' % e(s["kicker"]) if s.get("kicker") else "")
            body += '  <h1 data-at="p0" style="font-size:%dpx"><span class="f">%s</span></h1>\n' % (fit(s["title"], 124), e(s["title"]))
            if s.get("subtitle"):
                body += '  <h2 data-at="p%d" class="d" style="margin-top:56px;font-size:%dpx;max-width:1560px">%s</h2>\n' % (
                    min(1, k - 1), 64 if len(s["subtitle"]) <= 60 else 52, e(s["subtitle"]))
            cues.append(("thud", sid, 0, 0.0, 0.6))
        elif kind == "footage":
            name = pathlib.PurePath(str(s["src"])).name
            pad = ' style="padding:40px 120px 250px"'
            if name in clips:
                media = '<canvas data-seq="%s/footage/%s.frames,%d,%d" width="1280" height="720" style="display:block;width:100%%;height:100%%"></canvas>' % (
                    e(vid), e(name), clips[name][0], clips[name][1])
            else:
                media = '<img src="%s/footage/%s" data-pan>' % (e(vid), e(name))
            label = '<div class="lab"><span class="num f" style="font-size:30px">▸</span>%s</div>' % e(s["label"]) if s.get("label") else ""
            body = '  <div class="shot" data-at="0.05" data-fx="fade" style="width:1400px;height:750px">%s%s</div>\n' % (media, label)
        elif kind == "points":
            body = '  <h2 data-at="p0">%s</h2>\n  <div class="col" style="margin-top:52px;gap:24px;align-items:stretch;width:1560px">\n' % e(s["heading"])
            for i, point in enumerate(s["points"]):
                body += ('    <div class="card" data-at="%s" data-fx="%s" style="display:flex;gap:30px;align-items:center;text-align:left;padding:26px 38px">'
                         '<span class="num %s">%d</span><div class="big" style="font-size:%dpx;line-height:1.25">%s</div></div>\n'
                         % (_at(i, len(s["points"]), k), ("left", "right")[i % 2], NUMS[i % 4], i + 1, fit(point, 46, 1320, 0.56, 36), e(point)))
            body += "  </div>\n"
            cues += [("pop", sid, min(i + 1, k - 1)) for i in range(min(len(s["points"]), k))]
        elif kind == "steps":
            cards = []
            for i, step in enumerate(s["steps"]):
                cards.append('<div class="card col node" data-at="%s" data-fx="pop" style="min-width:0;flex:1;gap:14px"><span class="num %s">%d</span>'
                             '<h3 style="font-size:%dpx">%s</h3><div class="sub" style="font-size:30px">%s</div></div>'
                             % (_at(i, len(s["steps"]), k), NUMS[i % 4], i + 1, fit(step["title"], 44, 330, 0.6, 28), e(step["title"]), e(step.get("text") or "")))
            arrow = '<div class="arrow" data-at="p0+0.4" data-fx="fade">→</div>'
            body = '  <h2 data-at="p0">%s</h2>\n  <div class="row" style="margin-top:60px;align-items:stretch;gap:26px;width:1640px">%s</div>\n' % (e(s["heading"]), arrow.join(cards))
            cues += [("pop", sid, min(i + 1, k - 1)) for i in range(min(len(s["steps"]), k))]
        elif kind == "stat":
            value = int(round(s["value"]))
            body = ('  <div class="row" style="align-items:baseline;gap:30px" data-at="p0"><span class="huge f" style="font-size:%dpx" data-at="p0" data-count="0,%d,%s,%s" data-cdur="1.2">0</span></div>\n'
                    % (fit(str(value) + (s.get("prefix") or "") + (s.get("suffix") or ""), 250, 1500, 0.62, 120), value,
                       e((s.get("prefix") or "").replace(",", "")), e((s.get("suffix") or "").replace(",", ""))))
            body += '  <div class="sub" style="font-size:54px;margin-top:26px;max-width:1500px" data-at="p0+0.5">%s</div>\n' % e(s["label"])
            cues.append(("ding", sid, 0, 0.9, 0.7))
        elif kind == "bars":
            body = '  <h2 data-at="p0">%s</h2>\n  <div class="col" style="margin-top:56px;gap:30px">\n' % e(s["heading"])
            for i, bar in enumerate(s["bars"]):
                at, value = "p0+%.1f" % (0.3 + 0.5 * i), int(round(bar["value"]))
                body += ('    <div class="barrow" data-at="{at}" data-fx="fade"><div class="name" style="font-size:{size}px">{name}</div><div class="track">'
                         '<div class="bar" style="background:{color}" data-at="{at}" data-bar="{value}"></div></div>'
                         '<div class="val" data-at="{at}" data-count="0,{value},,%" data-cdur="1.1">0%</div></div>\n'
                         ).format(at=at, name=e(bar["name"]), size=fit(bar["name"], 36, 400, 0.6, 22), color=COLORS[i % 5], value=value)
            body += "  </div>\n"
            cues.append(("pop", sid, 0, 0.3))
        elif kind == "terminal":
            body = ('  <h2 data-at="p0" style="margin-bottom:50px">%s</h2>\n' % e(s["heading"]) if s.get("heading") else "")
            body += '  <div class="card" data-at="0.1" data-fx="fade" style="width:1560px;text-align:left;padding:40px 48px;background:rgba(4,7,16,.78)">\n'
            for i, line in enumerate(s["lines"]):
                body += '    <div class="prompt" style="min-width:0;min-height:0;font-size:%dpx;line-height:1.7" data-at="%s" data-type data-tdur="%.1f">%s</div>\n' % (
                    fit(line, 40, 1400, 0.62, 22), "p%d+0.2" % i if k >= len(s["lines"]) else "p0+%.1f" % (0.2 + 1.3 * i), min(1.6, 0.4 + len(line) * 0.03), e(line))
            body += "  </div>\n"
        elif kind == "statement":
            body = ""
            for i, line in enumerate(s["lines"]):
                shown = e(line)
                if s.get("accent") and e(s["accent"]) in shown:
                    shown = shown.replace(e(s["accent"]), '<span class="f">%s</span>' % e(s["accent"]), 1)
                body += '  <h1 data-at="%s" data-fx="%s" style="font-size:%dpx;line-height:1.12;margin:10px 0">%s</h1>\n' % (
                    "p%d" % i if k >= len(s["lines"]) else "p0+%.1f" % (0.5 * i), ("stamp", "pop", "up")[i % 3], fit(line, 170, 1640, 0.56, 80), shown)
            cues += [("thud", sid, min(i, k - 1), 0.0 if k >= len(s["lines"]) else 0.5 * i, 0.5) for i in range(len(s["lines"]))]
        elif kind == "compare":
            body = ('  <h2 data-at="p0" style="margin-bottom:50px">%s</h2>\n' % e(s["heading"]) if s.get("heading") else "")
            cols = []
            for side, tone, at, fx in (("left", "b", "p0", "left"), ("right", "g", "p%d" % min(1, k - 1), "right")):
                rows = "".join('<div class="sub" style="font-size:%dpx;color:var(--ink);padding:10px 0;border-top:1px solid var(--line)">%s</div>'
                               % (fit(item, 38, 620, 0.56, 26), e(item)) for item in s[side]["items"])
                cols.append('<div class="card" data-at="%s%s" data-fx="%s" style="flex:1;text-align:left;padding:34px 42px"><div class="pill %s" style="font-size:30px;margin-bottom:22px">%s</div>%s</div>'
                            % (at, "+0.2" if k == 1 and side == "right" else "", fx, tone, e(s[side]["title"]), rows))
            body += '  <div class="row" style="width:1600px;gap:40px;align-items:stretch">%s</div>\n' % '<div class="arrow" data-at="p0+0.5" data-fx="fade">→</div>'.join(cols)
            cues.append(("ding", sid, min(1, k - 1), 0.2, 0.6))
        elif kind == "console":
            body = ('  <h2 data-at="p0" style="margin-bottom:40px;font-size:60px">%s</h2>\n' % e(s["heading"]) if s.get("heading") else "")
            size = fit(max(s["lines"], key=len), 34, 1440, 0.61, 20)
            body += ('  <div class="card" data-at="0.1" data-fx="fade" style="width:1600px;text-align:left;padding:0;background:rgba(4,7,16,.86);overflow:hidden">'
                     '<div style="padding:16px 24px;border-bottom:1px solid var(--line);display:flex;gap:10px">'
                     '<span style="width:16px;height:16px;border-radius:50%;background:#ff5f57"></span><span style="width:16px;height:16px;border-radius:50%;background:#febc2e"></span>'
                     '<span style="width:16px;height:16px;border-radius:50%;background:#28c840"></span></div><div style="padding:28px 40px 34px">\n')
            for i, line in enumerate(s["lines"]):
                body += '    <div class="mono" style="font-size:%dpx;line-height:1.55;white-space:pre;color:%s" data-at="%.2f" data-fx="fade" data-dur="0.25">%s</div>\n' % (
                    size, "var(--local)" if line.lstrip().startswith(("$", ">")) else "var(--ink)", 0.3 + i * 0.45, e(line) or "&nbsp;")
            body += "  </div></div>\n"
        else:  # close
            body = '  <h2 data-at="p0" class="d">%s</h2>\n' % e(s["heading"])
            body += '  <h1 data-at="p%d" data-fx="pop" style="margin-top:50px;font-size:%dpx"><span class="f">%s</span></h1>\n' % (min(1, k - 1), fit(s["title"], 104), e(s["title"]))
            if s.get("link"):
                body += '  <div style="margin-top:56px"><span class="pill mono" style="font-size:%dpx;padding:16px 38px" data-at="p%d+0.6" data-fx="pop">%s</span></div>\n' % (
                    fit(s["link"], 38, 1500, 0.62, 24), min(1, k - 1), e(s["link"]))
            cues += [("ding", sid, min(1, k - 1), 0.0, 0.9), ("thud", sid, min(1, k - 1), 0.0, 0.6)]
        segments.append((sid, "|".join(say), "|".join(cap), 1.6 if n == len(story["scenes"]) else 0.5))
        sections.append('<section class="scene" id="s-%s"%s>\n%s</section>\n' % (sid, pad, body))
    return {"segments": segments, "cues": cues, "music": zlib.crc32(str(story.get("repo") or vid).encode()) % 4,
            "html": PAGE.format(repo=e(str(story.get("repo") or "")), vid=vid, scenes="\n".join(sections))}
