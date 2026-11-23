"""LinkedIn through the signed-in browser: is anyone signed in, and publish ONE post (a video and
its text). post() is the Playwright way (Chrome, Edge, Firefox ...); Safari posts through
tools/post.sh. Both press the same buttons you would press: Start a post, Add media, Next, Post.
The text in the editor is compared with your text before Post is pressed, and nothing is
published if they differ.

LinkedIn must be shown in English: the buttons are found by their labels.
"""
import pathlib
import re
import time
from urllib.parse import urlparse

SITE = "https://www.linkedin.com"
SIGN_IN_PATHS = ("/login", "/uas/", "/checkpoint", "/authwall", "/signup", "/home")


class PostError(Exception):
    """A step failed. `posted` says whether Post had already been pressed."""

    def __init__(self, code, hint="", posted=False):
        super().__init__(code + (": " + hint if hint else ""))
        self.code, self.hint, self.posted = code, hint, posted


def _on_feed(url):
    u = urlparse(url)
    return (u.hostname or "").endswith("linkedin.com") and u.path.startswith("/feed")


def ensure_signed_in(session, say=print, wait=900):
    """Shows the sign-in page and waits if nobody is signed in to LinkedIn. A signed-out visit to
    the feed is sent to the sign-in page, so where the browser ends up is the answer."""
    if _on_feed(session.fetch(SITE + "/feed/", settle=1.5, source=False)[0]):
        say("LinkedIn: signed in")
        return
    session.show(SITE + "/login")
    say("LinkedIn: not signed in. Sign in in the %s window that is open now. Waiting..." % session.label)
    end, calm = time.time() + wait, 0
    while time.time() < end:
        session.pause(1.5)
        url = session.peek()[0]
        if _on_feed(url):
            say("LinkedIn: signed in")
            return
        # Signed in but landed somewhere else (a profile, a prompt): look at the feed to be sure.
        u = urlparse(url)
        away = (u.hostname or "").endswith("linkedin.com") and u.path not in ("", "/") and not u.path.startswith(SIGN_IN_PATHS)
        calm = calm + 1 if away else 0
        if calm == 4:
            if _on_feed(session.fetch(SITE + "/feed/", settle=1.5, source=False)[0]):
                say("LinkedIn: signed in")
                return
            calm = 0
    raise SystemExit("Gave up waiting for the LinkedIn sign-in. Run it again when you are ready.")


def _wait(page, locators, seconds, enabled=False):
    """The first of `locators` that is visible (and enabled, if asked), or None after `seconds`."""
    end = time.time() + seconds
    while time.time() < end:
        for locator in locators:
            try:
                first = locator.first
                if first.is_visible() and (not enabled or first.is_enabled()):
                    return first
            except Exception:
                pass
        page.wait_for_timeout(300)
    return None


def _lines(text):
    """The text as its non-empty lines, ignoring the invisible differences an editor adds."""
    text = re.sub("[​‌‍﻿]", "", text.replace(" ", " "))
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def post(page, video, text, publish=True, say=print, site=SITE):
    """Publish `video` with `text`. -> "POSTED", or "DRY RUN" when publish is False (stops before Post).
    Raises PostError; unless its .posted is True, nothing was published."""
    video = pathlib.Path(video).resolve()
    text = text.strip()
    if not video.is_file():
        raise PostError("NO VIDEO", str(video))
    if not text:
        raise PostError("NO TEXT", "the post text is empty")
    name = lambda pattern: re.compile(pattern, re.I)
    dialog = page.get_by_role("dialog")

    page.goto(site + "/feed/", wait_until="domcontentloaded")
    start = _wait(page, [page.get_by_role("button", name=name(r"^\s*start a post")), page.get_by_text(name(r"^\s*start a post\s*$"))], 40)
    if start is None:
        raise PostError("NO START BUTTON", "no 'Start a post' on the feed. Is LinkedIn signed in and shown in English?")
    start.click()

    say("  attaching the video...")
    media = _wait(page, [dialog.get_by_role("button", name=name(r"^add media")), dialog.locator('button[aria-label*="media" i]'),
                         page.get_by_role("button", name=name(r"^add media"))], 30)
    if media is None:
        raise PostError("NO MEDIA BUTTON", "the post window has no 'Add media' button")
    try:
        with page.expect_file_chooser(timeout=10000) as chooser:
            media.click()
        chooser.value.set_files(str(video))
    except Exception:
        picker = page.locator('input[type="file"]')
        if not picker.count():
            raise PostError("FILE DIALOG STUCK", "LinkedIn did not ask for a file")
        picker.first.set_input_files(str(video))

    nxt = _wait(page, [dialog.get_by_role("button", name=name(r"^next$")), page.get_by_role("button", name=name(r"^next$"))], 180, enabled=True)
    if nxt is None:
        raise PostError("VIDEO NOT ATTACHED", "the upload did not finish in three minutes")
    nxt.click()

    say("  writing the text...")
    editor = _wait(page, [dialog.get_by_role("textbox"), dialog.locator('[contenteditable="true"]'), page.locator('[contenteditable="true"]')], 40)
    if editor is None:
        raise PostError("NO EDITOR", "the post window has no text box")
    editor.click()
    page.keyboard.press("ControlOrMeta+a")
    page.keyboard.press("Delete")
    rows = text.splitlines()
    for i, row in enumerate(rows):
        if row:
            page.keyboard.insert_text(row)
        if i < len(rows) - 1:
            page.keyboard.press("Enter")
    page.keyboard.insert_text(" ")   # closes the hashtag suggestions, so nothing is picked by accident
    page.wait_for_timeout(1500)
    want, got = _lines(text), _lines(editor.inner_text())
    if want != got:
        diff = next(("line %d: wanted %r, the editor has %r" % (i + 1, w, g) for i, (w, g) in enumerate(zip(want, got)) if w != g),
                    "wanted %d lines, the editor has %d" % (len(want), len(got)))
        raise PostError("TEXT MISMATCH", diff)

    buttons = dialog.get_by_role("button", name=name(r"^post$"))
    send = _wait(page, [buttons], 120, enabled=True)
    if send is None:
        raise PostError("NO POST BUTTON", "the Post button did not become available")
    if buttons.count() != 1:
        raise PostError("NO POST BUTTON", "expected one Post button, found %d" % buttons.count())
    if not publish:
        return "DRY RUN"
    send.click()

    say("  waiting for LinkedIn to confirm...")
    end = time.time() + 180
    while time.time() < end:
        if _wait(page, [page.get_by_text(name(r"post successful"))], 2):
            return "POSTED"
        if _wait(page, [page.get_by_text(name(r"posting limit"))], 0.5):
            raise PostError("LIMIT REACHED", "LinkedIn says you have hit its posting limit. Try again tomorrow.")
    raise PostError("NO CONFIRMATION", "Post was pressed but no 'Post successful' message appeared. "
                    "Look at your profile before trying again, or you may post twice.", posted=True)
