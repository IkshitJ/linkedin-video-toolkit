#!/usr/bin/env python3
"""Make a short video about one of your GitHub repositories and post it to LinkedIn.

    python run.py                      the whole thing, step by step
    python run.py --browser edge       another browser than your default one: safari (macOS), chrome, edge,
                                       firefox, chromium, or the path of a browser
    python run.py --repo owner/name    skip the question about which repository
    python run.py --list               check the sign-ins, list your repositories and stop
    python run.py --no-post            make the video and the text, do not publish
    python run.py --dry-run            fill in the LinkedIn post but stop before pressing Post
    python run.py --post VIDEO TEXT    publish a video and a text file you already have
    python run.py --setup              install everything and stop

What happens: (1) the first run installs what it needs, (2) your default browser is checked for a
GitHub and a LinkedIn sign-in, and it waits while you sign in if there is none, (3) you pick
one of your repositories, (4) a narrated video and a post text are made from its description, README,
languages and stars, (5) you read the text, and it is published only when you answer yes.

Works on Windows, macOS and Linux. Needs Python 3.12 or newer, or uv (https://docs.astral.sh/uv/).
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
MODELS = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")


# ---- 1. one-time setup (plain standard library: this part runs before anything is installed) ----
def setup():
    """Python environment in .venv and the voice model in video/tts/. Skips what is already there."""
    uv = shutil.which("uv")
    if not VENV_PYTHON.exists():
        print("Setting up (one time)...", flush=True)
        if uv:
            subprocess.check_call([uv, "venv", "--python", "3.12", str(VENV)])
        elif sys.version_info >= (3, 12):
            subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
        else:
            sys.exit("Python 3.12 or newer is needed (this is %d.%d). Easiest: install uv from "
                     "https://docs.astral.sh/uv/ and run this again." % sys.version_info[:2])
    wanted = hashlib.sha256((ROOT / "requirements.txt").read_bytes()).hexdigest()
    stamp = VENV / "requirements.sha256"
    if not stamp.exists() or stamp.read_text().strip() != wanted:
        print("Installing Python packages...", flush=True)
        if uv:
            subprocess.check_call([uv, "pip", "install", "--python", str(VENV_PYTHON), "-r", str(ROOT / "requirements.txt")])
        else:
            subprocess.check_call([str(VENV_PYTHON), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])
        stamp.write_text(wanted)
    (ROOT / "out").mkdir(exist_ok=True)
    tts = ROOT / "video" / "tts"
    tts.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        target, part = tts / name, tts / (name + ".part")
        if target.exists() and target.stat().st_size:
            continue
        print("Downloading the voice model: %s" % name, flush=True)
        with urllib.request.urlopen(MODELS + name, timeout=60) as response, open(str(part), "wb") as f:
            total, done, shown = int(response.headers.get("Content-Length") or 0), 0, -1
            while True:
                block = response.read(1 << 20)
                if not block:
                    break
                f.write(block)
                done += len(block)
                tenth = done * 10 // total if total else 0
                if tenth != shown:
                    shown = tenth
                    print("  %d of %d MB" % (done >> 20, total >> 20), flush=True)
        if total and done != total:
            sys.exit("The download of %s stopped early. Run this again." % name)
        part.replace(target)


def in_venv():
    return pathlib.Path(sys.prefix).resolve() == VENV.resolve()


# ---- 2. the flow (runs inside .venv) -----------------------------------------------------------
def ask(question):
    try:
        return input(question).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit("Stopped. Nothing was published.")


def show(path):
    """Open a file with the system's default app. Never fatal."""
    try:
        if os.name == "nt":
            os.startfile(str(path))   # noqa: only exists on Windows
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def print_repos(repos, user):
    print("\nYour repositories on GitHub, most recently updated first:")
    notes = [", ".join(n for n in (r["language"], "private" if r["private"] else "", "fork" if r["fork"] else "") if n) for r in repos]
    width, wide = min(max([len(r["name"]) for r in repos] + [4]), 34), max([len(n) for n in notes] + [0])
    for i, (r, note) in enumerate(zip(repos, notes), 1):
        about = r["description"][:64] + ("..." if len(r["description"]) > 64 else "")
        print(("  %3d  %-*s  %-*s  %s" % (i, width, r["name"][:width], wide, note, about)).rstrip())
    if not repos:
        print("  (none found for %s)" % user)


def pick_repo(repos):
    """Ask which repository. -> (owner/name, its row in the list or None)."""
    if not sys.stdin.isatty():
        raise SystemExit("\nRun it again with the one you want:  python run.py --repo owner/name")
    while True:
        answer = ask("\nWhich one do you want to post about? Type its number, or owner/name: ")
        if answer.isdigit() and 1 <= int(answer) <= len(repos):
            row = repos[int(answer) - 1]
            return row["full"], row
        if "/" in answer:
            return answer, next((r for r in repos if r["full"].lower() == answer.lower()), None)
        match = [r for r in repos if r["name"].lower() == answer.lower()]
        if match:
            return match[0]["full"], match[0]
        print("That is not one of the numbers above.")


def publish(session, video, text_file, dry_run):
    """Post and report. -> exit code: 0 posted (or dry run), 1 nothing posted, 2 limit, 3 unconfirmed."""
    from toolkit import linkedin
    print("\nPosting to LinkedIn through %s (one to three minutes)..." % session.label, flush=True)
    try:
        result = session.post(video, text_file, publish=not dry_run)
    except linkedin.PostError as err:
        print("\n%s%s" % (err.code, ": " + err.hint if err.hint else ""))
        if not err.posted:
            print("Nothing was published. If a half-finished post is open in %s, close it before trying again." % session.label)
        return 3 if err.posted else 2 if err.code == "LIMIT REACHED" else 1
    if result == "DRY RUN":
        print("\nDRY RUN: the post is filled in and ready in %s. Post was NOT pressed." % session.label)
        if sys.stdin.isatty() and session.own_profile:
            ask("Look at it, then press Enter here to close the browser (the draft is discarded). ")
        elif not session.own_profile:
            print("Look at it in %s, then close the post there (Discard)." % session.label)
        return 0
    print("\nPOSTED: your post is live on LinkedIn.")
    return 0


def flow(args):
    from toolkit import browser, github, linkedin, story
    sys.path.insert(0, str(ROOT / "video"))
    import build as video_build

    session = browser.open_session(args.browser)
    try:
        print("Browser: %s (%s)" % (session.label, "its own profile, kept in .browser/" if session.own_profile
                                     else "the one you already use"), flush=True)

        if args.post:                                   # publish files you already have
            video, text_file = (pathlib.Path(p).expanduser().resolve() for p in args.post)
            linkedin.ensure_signed_in(session)
            return publish(session, video, text_file, args.dry_run)

        print("\nChecking your sign-ins...", flush=True)
        user = github.ensure_signed_in(session)
        if not args.no_post:
            linkedin.ensure_signed_in(session)

        full, row = args.repo, None
        if args.list or not full:
            repos = github.list_repos(session, user)
            print_repos(repos, user)
            if args.list:
                return 0
            full, row = pick_repo(repos)

        print("\nReading %s..." % full, flush=True)
        facts = github.repo_facts(session, full, row)
        if facts["private"]:
            print("\n%s is a PRIVATE repository. The video and the post will show its name, its description and lines\n"
                  "from its README to everyone who sees the post." % facts["full"])
            if not sys.stdin.isatty() or ask("Go on? Type yes to continue: ").lower() not in ("y", "yes"):
                raise SystemExit("Stopped. Nothing was made or published.")

        made = story.make(facts)
        vid = made["vid"]
        build_dir = ROOT / "video" / "build"
        build_dir.mkdir(exist_ok=True)
        (build_dir / (vid + "_script.json")).write_text(
            json.dumps({"segments": made["segments"], "cues": made["cues"], "music": made["music"]}, indent=1), encoding="utf-8")
        (build_dir / (vid + ".html")).write_text(made["html"], encoding="utf-8")
        text_file = ROOT / "out" / (vid + ".txt")
        text_file.parent.mkdir(exist_ok=True)
        text_file.write_text(made["post"], encoding="utf-8")

        print("\nMaking the video (about a minute)...", flush=True)
        try:
            video = video_build.build(vid, args.voice)
        except subprocess.CalledProcessError:
            raise SystemExit("The video could not be built. The messages above say which step failed.")

        print("\n" + "=" * 72 + "\n" + made["post"] + "=" * 72)
        print("Video: %s\nText:  %s" % (video, text_file))
        show(video)
        again = "python run.py --post %s %s" % (os.path.relpath(str(video)), os.path.relpath(str(text_file)))
        if args.no_post:
            print("\nNot published (--no-post). To publish these two files later:\n  " + again)
            return 0
        if not args.dry_run:
            if not sys.stdin.isatty():
                print("\nNot published: there is nobody to ask. To publish these two files:\n  " + again)
                return 0
            print("\nThis is exactly what will be posted to your LinkedIn profile. Watch the video and read the text.\n"
                  "To change the wording, edit the text file and save it before you answer.")
            if ask("Publish it now? Type yes to publish, anything else to stop: ").lower() not in ("y", "yes"):
                print("Not published. To publish these two files later:\n  " + again)
                return 0
        return publish(session, video, text_file, args.dry_run)
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, usage="python run.py [options]")
    parser.add_argument("--browser", help="safari (macOS), chrome, edge, firefox, chromium, or the full path of a Chromium-based browser; "
                                          "your default browser if left out")
    parser.add_argument("--repo", metavar="OWNER/NAME", help="the repository to post about")
    parser.add_argument("--list", action="store_true", help="check the sign-ins, list your repositories and stop")
    parser.add_argument("--no-post", action="store_true", help="make the video and the text, do not publish")
    parser.add_argument("--dry-run", action="store_true", help="fill in the LinkedIn post but do not press Post")
    parser.add_argument("--post", nargs=2, metavar=("VIDEO", "TEXT"), help="publish a video and a text file you already have")
    parser.add_argument("--voice", default="am_michael", help="Kokoro voice, for example am_michael, af_heart, bf_emma")
    parser.add_argument("--setup", action="store_true", help="install everything and stop")
    args = parser.parse_args()

    for f in args.post or []:
        if not pathlib.Path(f).expanduser().is_file():
            sys.exit("No such file: %s" % f)
    setup()
    if args.setup:
        print("\nSetup finished. Start with:  python run.py")
        return 0
    if not in_venv():   # hand over to the Python that has the packages
        return subprocess.call([str(VENV_PYTHON), str(ROOT / "run.py")] + sys.argv[1:])
    for stream in (sys.stdout, sys.stderr):   # a Windows console may not be able to print every character
        try:
            stream.reconfigure(errors="replace", line_buffering=True)   # and show each line at once, even through a pipe
        except Exception:
            pass
    try:
        return flow(args)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except Exception as err:
        if type(err).__name__ == "TargetClosedError":
            print("\nThe browser window was closed. Nothing more was done.")
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
