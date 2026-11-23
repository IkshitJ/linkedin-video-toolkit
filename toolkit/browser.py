"""Find and start a browser, on any system. Your default browser comes first.

  open_session()     the browser the flow works in.
                     Safari (macOS): the real Safari you already use, see toolkit/safari.py.
                     Anything else: a visible window of that browser with its own profile in
                     .browser/<name>/, where you sign in to GitHub and LinkedIn once. Browsers do not
                     let a program drive your everyday profile, so it has to be a separate one. This
                     code never reads passwords, cookies or tokens out of it.
  launch_renderer()  a hidden Chromium-family browser that renders video frames.

Browsers: safari (macOS only), chrome, edge, firefox, chromium, or the path of any Chromium-based
browser (Brave, Vivaldi, Opera, Arc ...). Chrome and Edge are used as installed. Firefox and Chromium
are Playwright's own builds and are downloaded the first time they are asked for.
"""
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILES = ROOT / ".browser"
KNOWN = {  # name: (Playwright engine, channel of an installed browser, label)
    "chrome": ("chromium", "chrome", "Google Chrome"),
    "edge": ("chromium", "msedge", "Microsoft Edge"),
    "firefox": ("firefox", None, "Firefox"),
    "chromium": ("chromium", None, "Chromium"),
}


def _not_installed(err):
    text = str(err)
    return "Executable doesn't exist" in text or "playwright install" in text or "is not found at" in text


def _download(engine, say):
    say("Downloading Playwright's %s (one time)..." % engine)
    subprocess.check_call([sys.executable, "-m", "playwright", "install", engine])


def name_of(text, path=""):
    """A browser's short name from whatever the system calls it ('MSEdgeHTM', 'com.google.Chrome',
    'firefox.desktop' ...), else its program path (taken to be Chromium-based), else None."""
    low = text.lower()
    for word, name in (("safari", "safari"), ("edge", "edge"), ("firefox", "firefox"), ("chromium", "chromium")):
        if word in low:
            return name
    if "chrome" in low and "google" in (low + path.lower()) or low in ("chromehtml", "google-chrome.desktop"):
        return "chrome"
    return path or None


def default_browser():
    """The system's default browser as 'safari', 'chrome', 'edge', 'firefox', 'chromium' or a program path. None if unknown."""
    try:
        if sys.platform == "darwin":
            from AppKit import NSBundle, NSWorkspace
            from Foundation import NSURL
            app = NSWorkspace.sharedWorkspace().URLForApplicationToOpenURL_(NSURL.URLWithString_("https://example.com"))
            bundle = NSBundle.bundleWithURL_(app)
            return name_of(str(bundle.bundleIdentifier() or ""), str(bundle.executablePath() or ""))
        if os.name == "nt":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice") as key:
                prog = winreg.QueryValueEx(key, "ProgId")[0]
            path = ""
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog + r"\shell\open\command") as key:
                    command = winreg.QueryValueEx(key, "")[0]
                found = re.match(r'"([^"]+)"|(\S+)', command)
                path = (found.group(1) or found.group(2)) if found else ""
            except OSError:
                pass
            return name_of(prog, path if os.path.isfile(path) else "")
        entry = subprocess.run(["xdg-settings", "get", "default-web-browser"], capture_output=True, text=True, timeout=10).stdout.strip()
        return name_of(entry) if entry else None
    except Exception:
        return None


def order(choice=None):
    """Which browsers to try. Without a choice: your default browser, one you have used here before, Chrome, Edge, Chromium."""
    if choice:
        return [choice]
    names = [default_browser()] + [n for n in KNOWN if (PROFILES / n).is_dir()] + ["chrome", "edge", "chromium"]
    return [n for i, n in enumerate(names) if n and n not in names[:i]]


class Window:
    """A Playwright browser window with its own profile. toolkit.safari.Safari offers the same methods."""
    own_profile = True

    def __init__(self, playwright, context, label):
        self.playwright, self.context, self.label = playwright, context, label
        self.page = context.pages[0] if context.pages else context.new_page()

    def fetch(self, url, wait_for=None, settle=0, source=True):
        """Load `url`, -> (final address, page source). wait_for: a CSS selector to give a few seconds to appear."""
        self.page.goto(url, wait_until="domcontentloaded")
        if wait_for:
            try:
                self.page.wait_for_selector(wait_for, timeout=8000)
            except Exception:
                pass
        if settle:
            self.page.wait_for_timeout(settle * 1000)
        return self.page.url, self.page.content() if source else ""

    def show(self, url):
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.bring_to_front()

    def peek(self):
        try:
            return self.page.url, self.page.content()
        except Exception as err:   # in the middle of a navigation
            if type(err).__name__ == "TargetClosedError":
                raise
            return self.page.url, ""

    def pause(self, seconds):
        self.page.wait_for_timeout(seconds * 1000)

    def post(self, video, text_file, publish=True, say=print):
        from . import linkedin
        say("  Do not use the browser window until this finishes.")
        return linkedin.post(self.page, video, pathlib.Path(text_file).read_text(encoding="utf-8"), publish=publish, say=say)

    def close(self):
        for stop in (self.context.close, self.playwright.stop):
            try:
                stop()
            except Exception:
                pass


def open_session(choice=None, say=print):
    """-> the browser to work in: Safari itself, or a Window of another browser. Your default browser first."""
    names = order(choice)
    if names[0].lower() == "safari":
        if sys.platform != "darwin":
            raise SystemExit("Safari only exists on macOS. Use --browser chrome, edge or firefox.")
        from .safari import Safari
        return Safari()
    from playwright.sync_api import sync_playwright
    playwright = sync_playwright().start()
    try:
        context, label = open_profile(playwright, [n for n in names if n.lower() != "safari"], say)
    except BaseException:
        playwright.stop()
        raise
    return Window(playwright, context, label)


def open_profile(pw, names, say=print):
    """-> (context, label). A visible browser window that remembers its sign-ins between runs."""
    errors = []
    for name in names:
        if name.lower() in KNOWN:
            key = name.lower()
            engine, channel, label = KNOWN[key]
            exe = None
        else:
            exe = pathlib.Path(name).expanduser()
            if not exe.exists():
                raise SystemExit("Unknown browser %r. Use chrome, edge, firefox, chromium or the full path of a Chromium-based browser." % name)
            engine, channel, label = "chromium", None, exe.stem
            key = "custom-" + (re.sub(r"[^a-z0-9]+", "-", exe.stem.lower()).strip("-") or "browser")
        options = {"user_data_dir": str(PROFILES / key), "headless": False, "no_viewport": True}
        if channel:
            options["channel"] = channel
        if exe:
            options["executable_path"] = str(exe)
        for attempt in (1, 2):
            try:
                return getattr(pw, engine).launch_persistent_context(**options), label
            except Exception as err:  # not installed, or its profile is open in another window
                if attempt == 1 and not channel and not exe and _not_installed(err):
                    _download(engine, say)
                    continue
                errors.append("%s: %s" % (label, str(err).strip().splitlines()[0]))
                profile = PROFILES / key
                if profile.is_dir() and not any(profile.iterdir()):
                    profile.rmdir()   # a browser that never started must not look like one you have used
                break
    raise SystemExit("Could not start a browser.\n  " + "\n  ".join(errors) +
                     "\nIf a window from an earlier run is still open, close it. Otherwise install Chrome or Edge, or pass --browser.")


async def launch_renderer(pw, args=(), say=print):
    """Hidden Chromium-family browser for rendering: Chrome, else Edge, else Playwright's Chromium."""
    last = None
    for channel in ("chrome", "msedge", None):
        try:
            return await pw.chromium.launch(headless=True, args=list(args), **({"channel": channel} if channel else {}))
        except Exception as err:
            last = err
    if _not_installed(last):
        _download("chromium", say)
        return await pw.chromium.launch(headless=True, args=list(args))
    raise last
