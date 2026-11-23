"""The basic storyboard: no AI, no network. draft(facts) assembles a short video and a post from the
repository's own description, README, languages and star count. It is what you get with --basic,
or when no AI writer is available. The format it returns is described in toolkit/scenes.py.

facts = {"full": "owner/name", "description": str, "private": bool, "stars": int or None,
         "forks": int or None, "languages": [[name, percent or None], ...], "topics": [str, ...],
         "readme": [{"tag": "p" | "li" | "h2" ..., "text": str, "sec": heading it sits under}, ...]}
"""
import re

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


# ---- the storyboard ---------------------------------------------------------------------------
def vid_for(full):
    """The build name of a repository's video: 'owner/My.Repo' -> 'repo-my-repo'."""
    return "repo-" + slug(full.split("/", 1)[-1])


def draft(facts):
    """-> a storyboard (see toolkit/scenes.py) for one repository, written without AI."""
    owner, name = facts["full"].split("/", 1)
    private = bool(facts.get("private"))
    desc = describe(facts)
    points = highlights(facts, desc)
    langs = languages(facts)
    stars, forks = facts.get("stars") or 0, facts.get("forks") or 0
    scenes = [{"type": "title", "kicker": owner + " on GitHub", "title": name, "subtitle": desc,
               "say": ["Meet " + spoken_name(name) + "."] + ([desc] if desc else []),
               "cap": ["Meet " + name + "."] + ([sentence(desc)] if desc else [])}]
    if points:
        scenes.append({"type": "points", "heading": "What it does", "points": points,
                       "say": ["Here is what it does."] + points, "cap": ["Here is what it does."] + [sentence(p) for p in points]})
    if langs and langs[0][1] is not None and len(langs) > 1:
        line = "It is built with %s." % join(named(langs))
        say, cap = [line], [line]
        if langs[0][1] >= 50:
            say.append("%s makes up %d percent of the code." % (langs[0][0], langs[0][1]))
            cap.append("%s makes up %d%% of the code." % (langs[0][0], langs[0][1]))
        scenes.append({"type": "bars", "heading": "Built with", "bars": [{"name": l[0], "value": l[1]} for l in langs], "say": say, "cap": cap})
    elif langs:
        line = "It is written in %s." % join(named(langs))
        scenes.append({"type": "title", "kicker": "Built with", "title": join(named(langs)), "subtitle": "", "say": [line], "cap": [line]})
    if stars >= 10 and not private:
        big = stars >= 10000
        say = ["Over %d thousand stars on GitHub." % round(stars / 1000) if big else "It has %d stars on GitHub." % stars]
        cap = ["{:,} stars on GitHub.".format(stars)]
        if forks >= 5:
            say.append("And %d forks." % forks); cap.append("And {:,} forks.".format(forks))
        scenes.append({"type": "stat", "value": int(round(stars / 1000)) if big else stars, "prefix": "", "suffix": "k" if big else "",
                       "label": "stars on GitHub", "say": say, "cap": cap})
    if private:
        scenes.append({"type": "close", "heading": "A private project", "title": name, "link": "by " + owner,
                       "say": ["That is " + spoken_name(name) + ".", "Thanks for watching."], "cap": ["That is %s." % name, "Thanks for watching."]})
    else:
        scenes.append({"type": "close", "heading": "Find it on GitHub", "title": name, "link": "github.com/" + facts["full"],
                       "say": ["Find it on GitHub.", "%s slash %s." % (spoken_name(owner), spoken_name(name))],
                       "cap": ["Find it on GitHub.", "github.com/" + facts["full"]]})

    lines = [name + (": " + sentence(desc) if desc else "")]
    if points:
        lines += ["", "What it does:"] + ["- " + p for p in points]
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
    return {"repo": facts["full"], "caption": "\n".join(lines) + "\n", "scenes": scenes}
