"""Turn the facts of one GitHub repository into a video script, its scenes and a LinkedIn post.

Nothing here talks to the network or to a model: the wording is assembled from the repository's
own description, README, languages and star count. make(facts) returns everything the build needs.

facts = {"full": "owner/name", "description": str, "private": bool, "stars": int or None,
         "forks": int or None, "languages": [[name, percent or None], ...], "topics": [str, ...],
         "readme": [{"tag": "p" | "li" | "h2" ..., "text": str, "sec": heading it sits under}, ...]}
"""
import html
import re
import zlib

# ---- text helpers ----------------------------------------------------------------------------
SYMBOLS = re.compile("[\U0001F000-\U0001FAFF←-⇿⌀-⏿☀-➿⬀-⯿️​-‍]")
URL = re.compile(r"https?://\S+|www\.\S+")


def tidy(text):
    """Plain one-line text: no emoji, no links, no '|' (the phrase separator of the script format)."""
    text = URL.sub("", SYMBOLS.sub("", text or "")).replace("|", ",").replace("`", "")
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"^[\s\-*•·:,.]+|[\s\-*•·:,]+$", "", text)


def shorten(text, limit, strict=False):
    """At most `limit` characters, cut at a sentence, then a clause, then a comma or a word.
    strict: never cut at a comma or a word, because half a list reads as a false claim
    ("automates Chromium" for "automates Chromium, Firefox and WebKit"); returns "" instead."""
    if len(text) <= limit:
        return text
    first = re.split(r"(?<=[.!?])\s+", text)[0]
    if len(first) <= limit:
        return first
    best = ""
    for seps in ((": ", " - ", " – ", " — ", "; ", " ("), (", ",)):
        for sep in seps:
            cut = first[:limit + 1].rfind(sep)
            if cut > len(best) and cut >= limit // 4:
                best = first[:cut]
        if best or strict:
            break
    if not best and not strict:
        best = first[:limit + 1].rsplit(" ", 1)[0]
    return best.rstrip(" ,;:-–—(")


SAY = [("C++", "C plus plus"), ("C#", "C sharp"), ("F#", "F sharp"), (".NET", "dot net"), ("Node.js", "Node J S"),
       ("Vue.js", "Vue J S"), ("Next.js", "Next J S"), (" & ", " and "), ("&", " and "), ("%", " percent"),
       (" / ", " and "), ("/", " "), ("~", "about "), ("+", " plus "), ("@", " at "), ("=", " equals ")]
WORDS = {"JSON", "REST", "CRUD", "RAM", "ROM", "GIF", "JPEG", "ASCII", "YAML", "TOML", "NASA", "SOLID", "RAG",
         "NEW", "FREE", "FAST", "NOT", "AND", "THE", "ALL", "FOR", "NOW", "ONE", "TWO", "WITH", "YOUR", "ANY"}


def speak(text):
    """The same sentence, spelled the way the voice should read it."""
    for a, b in SAY:
        text = text.replace(a, b)
    text = re.sub(r"[#*_<>\[\]{}\"]", " ", text).replace("(", ", ").replace(")", ", ")
    text = re.sub(r"\b[A-Z]{2,5}\b", lambda m: m[0] if m[0] in WORDS else ".".join(m[0]) + ".", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = re.sub(r"(,\s*)+([.!?])", r"\2", re.sub(r",(\s*,)+", ",", text)).strip(" ,")
    return text if text[-1:] in ".!?" else text + "."


def spoken_name(name):
    """'linkedin-video-toolkit' -> 'linkedin video toolkit', 'myCoolApp' -> 'my Cool App'."""
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return re.sub(r"\s+", " ", re.sub(r"[-_.]+", " ", name)).strip() or name


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "repo"


def sentence(text):
    return text if text[-1:] in ".!?" else text + "."


def hashtag(word):
    word = word.replace("C++", "Cpp").replace("C#", "CSharp").replace("F#", "FSharp").replace(".NET", "DotNet")
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", word) if p]
    tag = "".join(p if len(parts) == 1 else p[:1].upper() + p[1:] for p in parts)
    return "#" + tag if tag and not tag.isdigit() else ""


# ---- what to say about the repository --------------------------------------------------------
SKIP_SEC = re.compile(r"install|set ?up|getting started|quick ?start|requirement|prerequisite|usage|how to|licen[sc]e|"
                      r"contribut|contents|roadmap|todo|to-do|changelog|credit|acknowledg|support|sponsor|faq|troubleshoot|"
                      r"build|develop|test|deploy|configur|example|doc|link|community|author|contact|download|need|rules", re.I)
GOOD_SEC = re.compile(r"feature|highlight|what|why|overview|capabilit|benefit|does", re.I)
ASKS = re.compile(r"^(see|check|click|read|visit|download|install|run|please|note|for more|learn|try|star|follow|join|go to|head)\b", re.I)


def describe(facts):
    """One sentence about the project: its GitHub description, else the opening of its README."""
    text = tidy(facts.get("description"))
    if not text:
        for item in facts.get("readme") or []:
            cand = tidy(item["text"])
            if item["tag"] == "p" and len(cand) >= 20 and len(cand.split()) >= 4:
                text = cand
                break
    return shorten(text, 120).rstrip(".") if text else ""


def highlights(facts, taken=""):
    """Up to three short points: the first feature-like list of the README, else its opening sentences."""
    groups, order = {}, []
    for item in facts.get("readme") or []:
        text = tidy(item["text"])
        if item["tag"] != "li" or not 12 <= len(text) <= 220 or len(text.split()) < 2:
            continue
        sec = item.get("sec") or ""
        if sec not in groups:
            groups[sec] = []
            order.append(sec)
        groups[sec].append(text)
    picked = next((groups[s] for s in order if GOOD_SEC.search(s) and len(groups[s]) >= 2), None) \
        or next((groups[s] for s in order if not SKIP_SEC.search(s) and len(groups[s]) >= 2), None)
    if not picked:
        picked = []
        for item in facts.get("readme") or []:
            if item["tag"] == "p" and not SKIP_SEC.search(item.get("sec") or ""):
                picked += [s for s in re.split(r"(?<=[.!?])\s+", tidy(item["text"])) if 25 <= len(s) <= 100 and not s.endswith("?") and not ASKS.match(s)]
    out = []
    for text in picked:
        text = shorten(text, 100, strict=True).rstrip(".")
        if len(text) >= 12 and text.lower() != taken.lower() and text.lower() not in [o.lower() for o in out]:
            out.append(text)
        if len(out) == 3:
            break
    return out


def languages(facts):
    """Up to four [name, whole percent or None], biggest first; drops slivers under 1 %."""
    out = []
    for name, pct in facts.get("languages") or []:
        if pct is None:
            out.append([name, None])
        elif round(pct) >= 1:
            out.append([name, int(round(pct))])
    return out[:4]


def named(langs):
    """The languages worth naming in a sentence: the biggest, and any other with a tenth of the code."""
    return [l[0] for i, l in enumerate(langs) if i == 0 or l[1] is None or l[1] >= 10][:3]


def join(names):
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


# ---- the video and the post ------------------------------------------------------------------
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="video-size" content="1920x1080">
<link rel="stylesheet" href="../style.css"></head><body>
<!-- Generated by run.py from {full}. Edit freely, then: python video/build.py {vid} -->
<div id="stage">
<div class="blob" id="b1"></div><div class="blob" id="b2"></div><div class="blob" id="b3"></div><div id="grid"></div>
{scenes}
<div id="cap"><span></span></div><div id="prog"></div><div id="fade"></div>
</div>
<script src="{vid}_timeline.js"></script><script src="../engine.js"></script>
</body></html>
"""
COLORS = ("var(--fable)", "var(--local)", "var(--good)", "var(--ink)")
NUMS = ("f", "l", "m")


def fit(text, base, width=1620, ratio=0.58, floor=44):
    """Font size that keeps `text` on one line of `width` pixels."""
    return max(floor, min(base, int(width / (ratio * max(len(text), 1)))))


def make(facts):
    """-> {"vid", "segments", "cues", "music", "html", "post"} for one repository."""
    e = html.escape
    owner, name = facts["full"].split("/", 1)
    private = bool(facts.get("private"))
    desc = describe(facts)
    points = highlights(facts, desc)
    langs = languages(facts)
    stars, forks = facts.get("stars") or 0, facts.get("forks") or 0
    vid = "repo-" + slug(name)
    segments, cues, scenes = [], [], []

    # 1. hook: the name, then what it is
    say, cap = ["Meet " + speak(spoken_name(name))], ["Meet " + name + "."]
    body = '  <div class="tag" data-at="0.3" data-fx="fade">%s on GitHub</div>\n' % e(owner)
    body += '  <h1 data-at="p0" style="font-size:%dpx"><span class="f">%s</span></h1>\n' % (fit(name, 124), e(name))
    if desc:
        say.append(speak(desc)); cap.append(sentence(desc))
        body += '  <h2 data-at="p1" class="d" style="margin-top:56px;font-size:%dpx;max-width:1560px">%s</h2>\n' % (64 if len(desc) <= 60 else 52, e(desc))
    segments.append(("hook", "|".join(say), "|".join(cap), 0.5))
    cues.append(("thud", "hook", 0, 0.0, 0.6))
    scenes.append(("hook", body))

    # 2. what it does: up to three points from the README
    if points:
        say, cap = ["Here is what it does."], ["Here is what it does."]
        body = '  <h2 data-at="p0">What it does</h2>\n  <div class="col" style="margin-top:56px;gap:24px;align-items:stretch;width:1560px">\n'
        for i, point in enumerate(points):
            say.append(speak(point)); cap.append(sentence(point))
            body += ('    <div class="card" data-at="p%d" data-fx="%s" style="display:flex;gap:30px;align-items:center;text-align:left;padding:26px 38px">'
                     '<span class="num %s">%d</span><div class="big" style="font-size:%dpx;line-height:1.25">%s</div></div>\n'
                     % (i + 1, ("left", "right")[i % 2], NUMS[i], i + 1, fit(point, 46, 1320, 0.56, 36), e(point)))
            cues.append(("pop", "what", i + 1))
        segments.append(("what", "|".join(say), "|".join(cap), 0.5))
        scenes.append(("what", body + "  </div>\n"))

    # 3. what it is built with
    if langs:
        names = named(langs)
        line = ("It is written in %s." if len(names) == 1 else "It is built with %s.") % join(names)
        say, cap = [speak(line)], [line]
        body = '  <h2 data-at="p0">Built with</h2>\n'
        if langs[0][1] is None:
            body += '  <div class="row" style="margin-top:64px">%s</div>\n' % "".join(
                '<span class="pill %s" style="font-size:60px;padding:20px 52px" data-at="p0+%.1f" data-fx="pop">%s</span>' % (("f", "l", "g")[i % 3], 0.4 + 0.4 * i, e(l[0]))
                for i, l in enumerate(langs))
        else:
            body += '  <div class="col" style="margin-top:56px;gap:30px">\n'
            for i, (lang, pct) in enumerate(langs):
                at = "p0+%.1f" % (0.3 + 0.5 * i)
                body += ('    <div class="barrow" data-at="{at}" data-fx="fade"><div class="name">{name}</div><div class="track">'
                         '<div class="bar" style="background:{color}" data-at="{at}" data-bar="{pct}"></div></div>'
                         '<div class="val" data-at="{at}" data-count="0,{pct},,%" data-cdur="1.1">0%</div></div>\n'
                         ).format(at=at, name=e(lang), color=COLORS[i], pct=pct)
            body += "  </div>\n"
            if len(langs) > 1 and langs[0][1] >= 50:
                say.append(speak("%s makes up %d percent of the code." % (langs[0][0], langs[0][1])))
                cap.append("%s makes up %d%% of the code." % (langs[0][0], langs[0][1]))
        segments.append(("stack", "|".join(say), "|".join(cap), 0.5))
        cues.append(("pop", "stack", 0, 0.3))
        scenes.append(("stack", body))

    # 4. stars, when there are enough to be worth a scene
    if stars >= 10 and not private:
        big = stars >= 10000
        shown, suffix = (int(round(stars / 1000)), "k") if big else (stars, "")
        say = [("Over %d thousand stars on GitHub." % shown) if big else ("It has %d stars on GitHub." % stars)]
        cap = ["{:,} stars on GitHub.".format(stars)]
        body = ('  <div class="row" style="align-items:baseline;gap:30px" data-at="p0"><span class="huge f" data-at="p0" data-count="0,%d,,%s" data-cdur="1.2">0</span>'
                '<span class="sub" style="font-size:54px">stars on GitHub</span></div>\n' % (shown, suffix))
        if forks >= 5:
            say.append("And %d forks." % forks); cap.append("And {:,} forks.".format(forks))
            body += '  <div style="margin-top:50px"><span class="pill l" style="font-size:40px;padding:14px 36px" data-at="p1" data-fx="pop">{:,} forks</span></div>\n'.format(forks)
        segments.append(("stars", "|".join(say), "|".join(cap), 0.5))
        cues.append(("ding", "stars", 0, 0.9, 0.7))
        scenes.append(("stars", body))

    # 5. close: where to find it (a private repository has no public link to show)
    if private:
        say, cap = ["That is " + speak(spoken_name(name)), "Thanks for watching."], ["That is %s." % name, "Thanks for watching."]
        link = "by " + owner
    else:
        say = ["Find it on GitHub.", speak("%s slash %s" % (spoken_name(owner), spoken_name(name)))]
        cap = ["Find it on GitHub.", "github.com/" + facts["full"]]
        link = "github.com/" + facts["full"]
    body = '  <h2 data-at="p0" class="d">%s</h2>\n' % ("A private project" if private else "Find it on GitHub")
    body += '  <h1 data-at="p1" data-fx="pop" style="margin-top:50px;font-size:%dpx"><span class="f">%s</span></h1>\n' % (fit(name, 104), e(name))
    body += '  <div style="margin-top:56px"><span class="pill mono" style="font-size:%dpx;padding:16px 38px" data-at="p1+0.6" data-fx="pop">%s</span></div>\n' % (fit(link, 38, 1500, 0.62, 24), e(link))
    segments.append(("close", "|".join(say), "|".join(cap), 1.6))
    cues += [("ding", "close", 1, 0.0, 0.9), ("thud", "close", 1, 0.0, 0.6)]
    scenes.append(("close", body))

    page = PAGE.format(full=e(facts["full"]), vid=vid, scenes="\n".join(
        '<section class="scene" id="s-%s">\n%s</section>\n' % (sid, body) for sid, body in scenes))

    # the post text
    lines = [name + (": " + sentence(desc) if desc else "")]
    if points:
        lines += ["", "What it does:"] + ["• " + p for p in points]
    if langs:
        lines += ["", "Built with %s." % join(named(langs))]
    if not private:
        lines += ["", "https://github.com/" + facts["full"]]
    tags = []
    for word in ([] if private else ["OpenSource"]) + [l[0] for l in langs[:1]] + list(facts.get("topics") or [])[:4]:
        tag = hashtag(word)
        if tag and tag.lower() not in [t.lower() for t in tags]:
            tags.append(tag)
    if tags:
        lines += ["", " ".join(tags[:5])]
    return {"vid": vid, "segments": segments, "cues": cues, "music": zlib.crc32(name.encode()) % 4,
            "html": page, "post": "\n".join(lines) + "\n"}
