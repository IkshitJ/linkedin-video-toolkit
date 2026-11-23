"""Collect what a writer needs to make a good video about one repository: the facts, the README
as text, its commands, and FOOTAGE of the product. Everything lands in video/build/<name>/:

    brief.json            what the repository says about itself, and the list of footage
    footage/              the pictures and recordings a storyboard may show

Footage comes from three places, all of them real:
  - the pictures (and GIFs) the README itself shows,
  - the project's website, if the repository names one: a screenshot and a full-page scroll,
  - the repository page on GitHub (public repositories).
An agent can add more: start the product, record it with tools/record.py, and put the MP4 in footage/.
"""
import json
import pathlib
import re
import subprocess
import urllib.request

BADGES = re.compile(r"shields\.io|badge|/workflows/|travis-ci|circleci|codecov|coveralls|badgen|sonarcloud|opencollective|contrib\.rocks", re.I)
KINDS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}


def readme_text(items, limit=14000):
    """The README as plain text with its structure kept: '# heading', '- list item', paragraphs."""
    lines = []
    for item in items:
        tag, text = item["tag"], item["text"]
        lines.append(("\n" + "#" * int(tag[1]) + " " + text) if tag[0] == "h" else ("- " + text) if tag == "li" else text)
    return "\n".join(lines).strip()[:limit]


def worth_showing(images, limit=4):
    """The README pictures that may be product shots: not badges, not vector icons, no duplicates."""
    seen, keep = set(), []
    for img in images:
        src = img.get("src") or ""
        if not src.startswith("http") or src in seen or BADGES.search(src) or BADGES.search(img.get("alt") or "") or src.split("?")[0].lower().endswith(".svg"):
            continue
        seen.add(src)
        keep.append(img)
    return keep[:limit]


def download(url, folder, stem):
    """Save one picture. -> its path, or None if it is not a real picture (too small, wrong type, unreachable)."""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "linkedin-video-toolkit"})
        with urllib.request.urlopen(request, timeout=20) as response:
            kind = KINDS.get((response.headers.get("Content-Type") or "").split(";")[0].strip().lower())
            data = response.read(12 << 20)
    except Exception:
        return None
    if not kind or not 15000 <= len(data) < (12 << 20):   # a badge or an icon is a few kilobytes
        return None
    path = pathlib.Path(folder) / (stem + kind)
    path.write_bytes(data)
    return path


def screenshots(url, folder, stem, say=print):
    """A viewport screenshot and a full-page one (for scrolling) of a public page. -> [(path, description)]"""
    from playwright.sync_api import sync_playwright
    from .browser import launch_renderer_sync
    shots = []
    try:
        with sync_playwright() as pw:
            browser = launch_renderer_sync(pw, ["--hide-scrollbars"], say)
            page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
            page.goto(url, wait_until="load", timeout=30000)
            page.wait_for_timeout(2000)
            top = pathlib.Path(folder) / (stem + ".png")
            page.screenshot(path=str(top))
            shots.append((top, "the top of " + url))
            height = min(page.evaluate("document.documentElement.scrollHeight"), 5400)
            if height > 1500:
                full = pathlib.Path(folder) / (stem + "-scroll.png")
                page.screenshot(path=str(full), clip={"x": 0, "y": 0, "width": 1600, "height": height}, full_page=True)
                shots.append((full, "a scroll down " + url))
            browser.close()
    except Exception as err:
        say("  could not capture %s (%s)" % (url, str(err).strip().splitlines()[0][:90]))
    return shots


def cut_frames(clip, fps=15, seconds=14):
    """Cut a recording (mp4, mov, webm, gif) into JPEG frames next to it. -> (number of frames, fps)"""
    import imageio_ffmpeg
    frames = pathlib.Path(str(clip) + ".frames")
    frames.mkdir(exist_ok=True)
    for old in frames.glob("*.jpg"):
        old.unlink()
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-t", str(seconds), "-i", str(clip),
                    "-vf", "fps=%d,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black" % fps,
                    "-q:v", "4", str(frames / "%04d.jpg")], check=True)
    return len(list(frames.glob("*.jpg"))), fps


def clips_in(story, footage):
    """Cut every recording the storyboard shows into frames. -> {file name: (frames, fps)} for scenes.render()."""
    from .scenes import CLIPS
    clips = {}
    for scene in story["scenes"]:
        name = pathlib.PurePath(str(scene.get("src") or "")).name
        if scene.get("type") == "footage" and name.lower().endswith(CLIPS) and name not in clips:
            count, fps = cut_frames(pathlib.Path(footage) / name)
            if count:
                clips[name] = (count, fps)
    return clips


def gather(facts, folder, say=print):
    """Collect the footage and write brief.json into `folder`. -> the brief (a dict)."""
    folder = pathlib.Path(folder)
    footage = folder / "footage"
    footage.mkdir(parents=True, exist_ok=True)
    found = []
    for i, img in enumerate(worth_showing(facts.get("images") or []), 1):
        path = download(img["src"], footage, "readme-%d" % i)
        if path:
            found.append({"file": path.name, "what": "a picture from the README" + (": " + img["alt"] if img.get("alt") else "")
                          + (" (animated)" if path.suffix == ".gif" else "")})
    home = facts.get("homepage") or ""
    if home.startswith("http") and "github.com" not in home:
        say("  capturing the project's website...")
        found += [{"file": p.name, "what": "the project's website, " + what} for p, what in screenshots(home, footage, "website", say)]
    if not facts.get("private"):
        say("  capturing the repository page...")
        found += [{"file": p.name, "what": "the repository on GitHub, " + what} for p, what in screenshots("https://github.com/" + facts["full"], footage, "github", say)]
    listed = {f["file"] for f in found}   # footage someone put there by hand (a recording of the product) counts too
    found += [{"file": p.name, "what": "added by hand"} for p in sorted(footage.iterdir())
              if p.is_file() and p.name not in listed and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm")]
    brief = {"repo": facts["full"], "private": bool(facts.get("private")), "description": facts.get("description") or "",
             "stars": facts.get("stars"), "forks": facts.get("forks"), "topics": facts.get("topics") or [], "website": home,
             "languages": [[name, round(pct, 1) if pct is not None else None] for name, pct in facts.get("languages") or []],
             "link": "" if facts.get("private") else "https://github.com/" + facts["full"],
             "readme": readme_text(facts.get("readme") or []), "code_blocks": facts.get("code") or [], "footage": found}
    (folder / "brief.json").write_text(json.dumps(brief, indent=1, ensure_ascii=False), encoding="utf-8")
    return brief
