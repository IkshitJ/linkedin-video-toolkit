"""GitHub through the browser you are signed in to: is anyone signed in, which repositories do
they have, and what does one repository say about itself. No access token is created or stored.

Everything is read from the source of ordinary GitHub pages, fetched by a browser session
(toolkit.browser.Window or toolkit.safari.Safari), so it works the same in every browser.
"""
import html as entities
import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin

from . import dom

SITE = "https://github.com"
API = "https://api.github.com"


# ---- reading pages (no network here) ----------------------------------------------------------
def signed_in_user(html):
    """The user name GitHub writes into every page for a signed-in visitor, or ''."""
    m = re.search(r'<meta\s+name="user-login"\s+content="([^"]*)"', html or "")
    return m.group(1) if m else ""


def parse_repo_list(html, base=SITE):
    """-> (rows, address of the next page or ''). One row per repository on a profile's Repositories tab."""
    root = dom.parse(html)
    box = root.find(lambda n: n.get("id") == "user-repositories-list")
    rows = []
    for li in box.find_all(lambda n: n.tag == "li") if box else []:
        link = li.find(lambda n: n.tag == "a" and n.has("itemprop", "codeRepository"))
        if link is None:
            continue
        prop = lambda name: (lambda n: n.text() if n else "")(li.find(lambda n: n.get("itemprop") == name))
        when = li.find(lambda n: n.tag == "relative-time")
        rows.append({"full": link.get("href").strip("/"), "name": link.text(), "description": prop("description"),
                     "language": prop("programmingLanguage"),
                     "private": any(re.search("private|internal", n.text(), re.I) for n in li.find_all(lambda n: n.has("class", "Label"))),
                     "fork": "Forked from" in li.text(), "updated": when.get("datetime") if when else ""})
    more = root.find(lambda n: n.tag == "a" and (n.has("class", "next_page") or n.has("rel", "next")) and n.get("href"))
    return rows, urljoin(base, more.get("href")) if more else ""


def parse_repo_page(html):
    """-> {"missing", "description", "readme": [{"tag", "text", "sec"}, ...], "code": [str], "images": [{"src", "alt"}]}
    from a repository's front page. code: the README's code blocks. images: the pictures in the README."""
    title = re.search(r"<title>(.*?)</title>", html or "", re.S)
    title = entities.unescape(re.sub(r"\s+", " ", title.group(1)).strip()) if title else ""
    about = re.match(r"(?:GitHub - )?[\w.-]+/[\w.-]+: (.*?)(?: · GitHub)?$", title)
    root = dom.parse(html)
    article = root.find(lambda n: n.tag == "article" and n.has("class", "markdown-body"))
    items, heading = [], ""
    for el in article.walk() if article else []:
        if el.tag not in ("h1", "h2", "h3", "h4", "p", "li"):
            continue
        text = el.text(skip=("ul", "ol", "img", "picture", "svg", "pre"))
        if el.tag[0] == "h":
            heading = text
        if text:
            items.append({"tag": el.tag, "text": text[:400], "sec": "" if el.tag[0] == "h" else heading})
        if len(items) >= 150:
            break
    code = [c for c in (pre.text()[:700] for pre in article.find_all(lambda n: n.tag == "pre")) if c][:10] if article else []
    images = [{"src": urljoin(SITE, img.get("src") or img.get("data-canonical-src")), "alt": img.get("alt")}
              for img in (article.find_all(lambda n: n.tag == "img" and (n.get("src") or n.get("data-canonical-src"))) if article else [])]
    return {"missing": "Page not found" in title, "description": about.group(1) if about else "", "readme": items, "code": code, "images": images}


# ---- talking to GitHub ------------------------------------------------------------------------
def ensure_signed_in(session, say=print, wait=900):
    """-> the GitHub user name. Shows the sign-in page and waits if nobody is signed in."""
    user = signed_in_user(session.fetch(SITE + "/")[1])
    if user:
        say("GitHub: signed in as %s" % user)
        return user
    session.show(SITE + "/login")
    say("GitHub: not signed in. Sign in in the %s window that is open now. Waiting..." % session.label)
    end = time.time() + wait
    while time.time() < end:
        session.pause(1.5)
        url, html = session.peek()
        user = signed_in_user(html) if "github.com" in url else ""
        if user:
            say("GitHub: signed in as %s" % user)
            return user
    raise SystemExit("Gave up waiting for the GitHub sign-in. Run it again when you are ready.")


def list_repos(session, user, pages=5):
    """The user's repositories, most recently updated first (30 per page, up to `pages` pages)."""
    repos, url = [], "%s/%s?tab=repositories" % (SITE, user)
    for _ in range(pages):
        rows, url = parse_repo_list(session.fetch(url, wait_for="#user-repositories-list")[1])
        repos += rows
        if not url:
            break
    return repos


def _api(path):
    """Public GitHub API without a login: answers for public repositories only."""
    request = urllib.request.Request(API + path, headers={"Accept": "application/vnd.github+json", "User-Agent": "linkedin-video-toolkit"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        return {"_status": err.code}
    except Exception:
        return {"_status": 0}


def repo_facts(session, full, row=None):
    """Everything toolkit.story needs about one repository: see the facts layout there."""
    full = full.strip().strip("/")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", full):
        raise SystemExit("Write the repository as owner/name, for example octocat/Hello-World.")
    row = row or {}
    facts = {"full": full, "description": row.get("description", ""), "private": bool(row.get("private")), "stars": None,
             "forks": None, "languages": [[row["language"], None]] if row.get("language") else [], "topics": [], "readme": [],
             "homepage": "", "code": [], "images": []}
    seen = parse_repo_page(session.fetch("%s/%s" % (SITE, full), wait_for="article.markdown-body")[1])
    if seen["missing"]:
        raise SystemExit("There is no repository %s, or the signed-in account cannot see it." % full)
    facts.update(readme=seen["readme"], code=seen["code"], images=seen["images"])
    facts["description"] = facts["description"] or seen["description"]

    info = {} if facts["private"] else _api("/repos/" + full)   # stars, topics and the language split, for public ones
    if "full_name" in info:
        facts.update(full=info["full_name"], description=info.get("description") or facts["description"], private=bool(info.get("private")),
                     stars=info.get("stargazers_count"), forks=info.get("forks_count"), topics=info.get("topics") or [],
                     homepage=info.get("homepage") or "")
        sizes = _api("/repos/%s/languages" % full)
        total = 0 if "_status" in sizes else sum(sizes.values())
        if total:
            facts["languages"] = [[k, 100.0 * v / total] for k, v in sorted(sizes.items(), key=lambda kv: -kv[1])]
    elif info.get("_status") == 404:
        facts["private"] = True   # the page opened for you, but the public API cannot see it
    return facts
