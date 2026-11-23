"""Safari on macOS, the real one: the window you already use and are already signed in to.

Pages are opened through AppleScript and their source is read back. Posting presses LinkedIn's
buttons through macOS Accessibility (tools/post.sh). Nothing is injected into pages, and no
password, cookie or token is read.

macOS asks once whether your terminal app may control Safari (Automation). Posting also needs
that app switched on under System Settings > Privacy & Security > Accessibility.
"""
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent

FETCH = """on run argv
  set wantSource to (item 2 of argv) is "1"
  tell application "Safari"
    if (count of windows) = 0 then make new document
    tell window 1
      set t to make new tab with properties {URL:(item 1 of argv)}
      set n to 0
      set seen to -1
      set s to ""
      repeat while n < 90
        delay 0.5
        set n to n + 1
        try
          set s to source of t
          if (length of s) > 0 and (length of s) = seen and (URL of t) starts with "http" then exit repeat
          set seen to length of s
        end try
      end repeat
      set u to URL of t
      close t
    end tell
  end tell
  if wantSource then return u & linefeed & s
  return u & linefeed
end run"""
SHOW = """on run argv
  tell application "Safari"
    activate
    if (count of windows) = 0 then make new document
    tell window 1 to set current tab to (make new tab with properties {URL:(item 1 of argv)})
  end tell
end run"""
PEEK = """tell application "Safari"
  if (count of windows) = 0 then return linefeed
  set t to current tab of window 1
  set u to URL of t
  if u is missing value then return linefeed
  return u & linefeed & (source of t)
end tell"""
LINKEDIN_TAB = """tell application "Safari"
  activate
  if (count of windows) = 0 then make new document
  tell window 1
    if not (exists (first tab whose URL contains "linkedin.com")) then
      make new tab with properties {URL:"https://www.linkedin.com/feed/"}
      delay 4
    end if
  end tell
end tell"""


def _script(source, *args):
    done = subprocess.run(["osascript", "-", *args], input=source, capture_output=True, text=True, encoding="utf-8")
    if done.returncode:
        problem = done.stderr.strip()
        if "-1743" in problem or "Not authorized" in problem or "not allowed" in problem.lower():
            raise SystemExit("macOS did not let this app control Safari.\nOpen System Settings > Privacy & Security > Automation, "
                             "switch on Safari for the app you run this from (Terminal, iTerm, VS Code ...), then run it again.")
        raise SystemExit("Safari did not answer: " + problem)
    return done.stdout


def can_press_buttons():
    """True if this app may use macOS Accessibility, which posting through Safari needs."""
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


class Safari:
    """The same four things toolkit.browser.Window offers, done in the real Safari."""
    label = "Safari"
    own_profile = False

    def fetch(self, url, wait_for=None, settle=0, source=True):
        """Load `url` in a background tab, close the tab, -> (final address, page source)."""
        final, _, html = _script(FETCH, url, "1" if source else "0").partition("\n")
        return final.strip(), html

    def show(self, url):
        _script(SHOW, url)

    def peek(self):
        """(address, source) of the tab you are looking at."""
        url, _, html = _script(PEEK).partition("\n")
        return url.strip(), html

    def pause(self, seconds):
        time.sleep(seconds)

    def post(self, video, text_file, publish=True, say=print):
        from .linkedin import PostError
        if not can_press_buttons():
            subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])
            raise PostError("NO ACCESSIBILITY", "posting through Safari presses its buttons through macOS Accessibility. In the settings window "
                            "that just opened, switch on the app you run this from (Terminal, iTerm, VS Code ...), then run it again")
        say("  Do not touch the keyboard or the mouse until this finishes: it types into the front window.")
        _script(LINKEDIN_TAB)
        env = dict(os.environ, DRY_RUN="" if publish else "1")
        run = subprocess.Popen([str(ROOT / "tools" / "post.sh"), str(video), str(text_file)], env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        last = ""
        for line in run.stdout:
            if line.strip():
                last = line.strip()
                sys.stdout.write("  " + line)
                sys.stdout.flush()
        code = run.wait()
        if code == 0:
            return "POSTED" if publish else "DRY RUN"
        if code == 2:
            raise PostError("LIMIT REACHED", "LinkedIn says you have hit its posting limit. Try again tomorrow")
        if code == 3:
            raise PostError("NO CONFIRMATION", "Post was pressed but no 'Post successful' message appeared. "
                            "Look at your profile before trying again, or you may post twice", posted=True)
        raise PostError(last.upper() if last and len(last) < 40 else "A STEP FAILED",
                        "the Safari window must be on screen with LinkedIn in English, and macOS in English")

    def wait_for_post(self):
        return 0   # Safari is your own window: it stays open with the post in it

    def close(self):
        pass
