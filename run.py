#!/usr/bin/env python3
"""Make a short video about one of your GitHub repositories and post it to LinkedIn.

    python run.py                      the whole thing, step by step
    python run.py --browser edge       another browser than your default one: safari (macOS), chrome, edge,
                                       firefox, chromium, or the path of a browser
    python run.py --list               check the sign-ins, list your repositories and stop
    python run.py --repo owner/name    skip the question about which repository
    python run.py --basic              the simple template video, without AI
    python run.py --no-post            make the video and the text, do not open LinkedIn
    python run.py --post VIDEO TEXT    put a video and a text file you already have into a LinkedIn post
    python run.py --post-with chrome   the browser that fills in the LinkedIn post (asked once if your default is Safari)
    python run.py --press-post         also press Post, instead of leaving that to you
    python run.py --setup              install everything and stop

What happens: (1) the first run installs what it needs, (2) your default browser is checked for a
GitHub and a LinkedIn sign-in, and it waits while you sign in if there is none, (3) you pick one of
your repositories; nothing is made before that, (4) footage of the product is collected and an AI
writes the video and the post around it, (5) LinkedIn is opened, the video is attached and the caption
is written, and it stops there: you look it over and press Post yourself.

Who writes the video: in a terminal, Claude through the API, with your own API key (asked for once;
ANTHROPIC_API_KEY or .env also work). When a coding agent runs this, the agent writes it:
`--repo X --brief` collects the material and `--story FILE` builds the agent's storyboard. See AGENTS.md.

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


def publish(session, video, text_file, press):
    """Open LinkedIn, attach the video and write the caption. Unless `press` (--press-post), stop there:
    the person presses Post themselves. -> exit code: 0 ready or posted, 1 a step failed, 2 limit, 3 unconfirmed."""
    from toolkit import linkedin
    print("\nOpening LinkedIn in %s and filling in the post (one to three minutes)..." % session.label, flush=True)
    try:
        result = session.post(video, text_file, publish=press)
    except linkedin.PostError as err:
        print("\n%s%s" % (err.code, ": " + err.hint if err.hint else ""))
        if not err.posted:
            print("Nothing was published. If a half-finished post is open in %s, close it before trying again." % session.label)
        return 3 if err.posted else 2 if err.code == "LIMIT REACHED" else 1
    if result == "DRY RUN":
        print("\nREADY: the video and the caption are in a LinkedIn post in %s. Nothing is published yet.\n"
              "Look it over there, change the text if you like, and press Post yourself. To drop it, close the post and choose Discard." % session.label)
        return session.wait_for_post()
    print("\nPOSTED: your post is live on LinkedIn.")
    return 0


def poster_session(args, reader=None):
    """The browser that fills in the LinkedIn post: `reader` itself when it is the same browser, a new session
    otherwise, or None when the user has to be asked first and nobody is at the terminal."""
    from toolkit import browser
    choice = browser.poster_choice(args.post_with, args.browser, ask if sys.stdin.isatty() else None)
    if choice is None:
        return None
    if reader is not None and ((choice.lower() == "safari" and not reader.own_profile) or
                               (choice.lower() != "safari" and reader.own_profile and not args.post_with)):
        return reader   # the browser that is already open
    poster = browser.open_session(choice)
    if poster.own_profile:
        print("LinkedIn post in: %s, in its own window (you can keep working)" % poster.label, flush=True)
    return poster


def hand_over(args, video, text_file):
    """Open LinkedIn in the chosen browser and fill in the post. -> exit code"""
    from toolkit import browser, linkedin
    poster = poster_session(args)
    if poster is None:
        print("\nLinkedIn was not opened yet. " + browser.POSTER_HELP + "\n  python run.py --post %s %s --post-with NAME"
              % (os.path.relpath(str(video)), os.path.relpath(str(text_file))))
        return 4
    try:
        linkedin.ensure_signed_in(poster)
        return publish(poster, video, text_file, args.press_post)
    finally:
        poster.close()


def api_key():
    """An Anthropic API key from the environment or .env, else asked for in a terminal. '' means: no AI."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ANTHROPIC_API_KEY":
                key = value.strip().strip("\"'")
    if key or not sys.stdin.isatty():
        return key
    import getpass
    print("\nClaude can write the video and the post from the repository and its footage. That needs an Anthropic API key\n"
          "(create one at https://console.anthropic.com/settings/keys). It is sent only to Anthropic's API.")
    try:
        key = getpass.getpass("Paste the key (it is not shown), or press Enter for the basic video without AI: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit("Stopped. Nothing was made or published.")
    if key and ask("Save it in .env in this folder for next time? The file is ignored by git. [y/N] ").lower() in ("y", "yes"):
        with open(str(env), "a", encoding="utf-8") as f:
            f.write("ANTHROPIC_API_KEY=%s\n" % key)
    return key


def produce(storyboard, vid, voice):
    """Storyboard -> out/<vid>.mp4 and out/<vid>.txt. -> (video, text file)"""
    from toolkit import material, scenes
    sys.path.insert(0, str(ROOT / "video"))
    import build as video_build
    build_dir = ROOT / "video" / "build"
    clips = material.clips_in(storyboard, build_dir / vid / "footage")
    made = scenes.render(storyboard, vid, clips)
    (build_dir / (vid + "_script.json")).write_text(
        json.dumps({"segments": made["segments"], "cues": made["cues"], "music": made["music"]}, indent=1), encoding="utf-8")
    (build_dir / (vid + ".html")).write_text(made["html"], encoding="utf-8")
    text_file = ROOT / "out" / (vid + ".txt")
    text_file.parent.mkdir(exist_ok=True)
    text_file.write_text(storyboard["caption"].strip() + "\n", encoding="utf-8")
    print("\nMaking the video (a minute or two)...", flush=True)
    try:
        video = video_build.build(vid, voice)
    except subprocess.CalledProcessError:
        raise SystemExit("The video could not be built. The messages above say which step failed.")
    print("\n" + "=" * 72 + "\n" + storyboard["caption"].strip() + "\n" + "=" * 72)
    print("Video: %s\nText:  %s" % (video, text_file))
    show(video)
    return video, text_file


def from_story(args):
    """--story FILE: build the video from a storyboard somebody wrote (an agent, or you). Opens no browser."""
    from toolkit import scenes, story
    path = pathlib.Path(args.story).expanduser().resolve()
    try:
        storyboard = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise SystemExit("Could not read the storyboard %s: %s" % (path, err))
    if not isinstance(storyboard, dict) or "/" not in str(storyboard.get("repo") or ""):
        raise SystemExit('The storyboard needs "repo": "owner/name", as in the brief.')
    vid = story.vid_for(storyboard["repo"])
    problems = scenes.check(storyboard, ROOT / "video" / "build" / vid / "footage")
    if problems:
        raise SystemExit("The storyboard cannot be built yet:\n  - " + "\n  - ".join(problems))
    video, text_file = produce(storyboard, vid, args.voice)
    if args.no_post:
        print("\nLinkedIn was not opened (--no-post). To put these two files into a LinkedIn post:\n"
              "  python run.py --post %s %s" % (os.path.relpath(str(video)), os.path.relpath(str(text_file))))
        return 0
    return hand_over(args, video, text_file)


def flow(args):
    from toolkit import browser, github, linkedin, material, scenes, story, writer

    if args.story:
        return from_story(args)
    person = sys.stdin.isatty()   # False when an agent or a script runs this: then nothing is decided for the user
    if args.post:                                       # put files you already have into a LinkedIn post
        return hand_over(args, *(pathlib.Path(p).expanduser().resolve() for p in args.post))
    session = browser.open_session(args.browser)
    try:
        print("Browser: %s (%s)" % (session.label, "its own profile, kept in .browser/" if session.own_profile
                                     else "the one you already use"), flush=True)
        print("\nChecking your sign-ins...", flush=True)
        user = github.ensure_signed_in(session)
        if not (args.no_post or args.brief or args.list):   # LinkedIn is checked in the browser that will fill in the post
            poster = poster_session(args, session)
            if poster is None:
                print("LinkedIn: will be checked in the browser you choose for the post")
            else:
                try:
                    linkedin.ensure_signed_in(poster)
                finally:
                    if poster is not session:
                        poster.close()

        full, row = args.repo, None
        if args.list or not full:
            repos = github.list_repos(session, user)
            print_repos(repos, user)
            if args.list or not person:
                if not person:
                    print("\nNEXT STEP, IF YOU ARE AN AGENT: ask the user which of these repositories the post is about, and wait for\n"
                          "their answer. Do not choose one for them, and do not make a video before they have chosen. Then:\n"
                          "  python run.py --repo OWNER/NAME --brief        (the whole procedure is in AGENTS.md)")
                return 0
            full, row = pick_repo(repos)

        # Nothing below this line happens before a repository has been chosen.
        print("\nReading %s..." % full, flush=True)
        facts = github.repo_facts(session, full, row)
        if facts["private"]:
            print("\n%s is a PRIVATE repository. The video and the post will show its name, its description and lines\n"
                  "from its README to everyone who sees the post. With an API key, its README text and pictures are also sent to\n"
                  "Anthropic's API to write the script (use --basic to avoid that)." % facts["full"])
            if person and ask("Go on? Type yes to continue: ").lower() not in ("y", "yes"):
                raise SystemExit("Stopped. Nothing was made or published.")
        vid = story.vid_for(facts["full"])
        folder = ROOT / "video" / "build" / vid
        print("Collecting footage of the product...", flush=True)
        brief = material.gather(facts, folder)
        print("  %d footage file(s) in %s" % (len(brief["footage"]), os.path.relpath(str(folder / "footage"))))

        if args.basic:
            storyboard = story.draft(facts)
        else:
            key = "" if args.brief else api_key()
            if not key and (args.brief or not person):   # an agent writes the storyboard itself
                print("\nBrief:   %s\nFootage: %s" % (os.path.relpath(str(folder / "brief.json")), os.path.relpath(str(folder / "footage"))))
                print("\nNo video was made. NEXT STEP, IF YOU ARE AN AGENT: read the brief, look at the footage, write the storyboard to\n"
                      "  %s\nas described in AGENTS.md, then run:\n  python run.py --story %s"
                      % (os.path.relpath(str(folder / "story.json")), os.path.relpath(str(folder / "story.json"))))
                return 0
            storyboard = None
            if key:
                print("Writing the video and the post with Claude (%s)..." % writer.MODEL, flush=True)
                try:
                    storyboard = writer.write(brief, folder / "footage", api_key=key)
                except writer.WriterError as err:
                    print("  The AI writer did not work: %s.\n  Making the basic version instead." % err)
            storyboard = storyboard or story.draft(facts)
        (folder / "story.json").write_text(json.dumps(storyboard, indent=1, ensure_ascii=False), encoding="utf-8")
        problems = scenes.check(storyboard, folder / "footage")
        if problems:
            raise SystemExit("The storyboard cannot be built:\n  - " + "\n  - ".join(problems))

        video, text_file = produce(storyboard, vid, args.voice)
        if args.no_post:
            print("\nLinkedIn was not opened (--no-post). To put these two files into a LinkedIn post later:\n"
                  "  python run.py --post %s %s" % (os.path.relpath(str(video)), os.path.relpath(str(text_file))))
            return 0
    finally:
        session.close()
    return hand_over(args, video, text_file)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, usage="python run.py [options]")
    parser.add_argument("--browser", help="safari (macOS), chrome, edge, firefox, chromium, or the full path of a Chromium-based browser; "
                                          "your default browser if left out")
    parser.add_argument("--repo", metavar="OWNER/NAME", help="the repository to post about")
    parser.add_argument("--list", action="store_true", help="check the sign-ins, list your repositories and stop")
    parser.add_argument("--no-post", action="store_true", help="make the video and the text, do not open LinkedIn")
    parser.add_argument("--post-with", metavar="BROWSER", help="the browser that fills in the LinkedIn post: chrome, safari, edge, firefox or a path "
                                                                 "(asked once when your default browser is Safari)")
    parser.add_argument("--press-post", action="store_true", help="also press Post, instead of leaving that to you")
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)   # the old name of what is now the normal behaviour
    parser.add_argument("--post", nargs=2, metavar=("VIDEO", "TEXT"), help="put a video and a text file you already have into a LinkedIn post")
    parser.add_argument("--basic", action="store_true", help="make the simple video from a fixed template, without AI")
    parser.add_argument("--brief", action="store_true", help="with --repo: collect the facts and the footage for a writer and stop (for agents)")
    parser.add_argument("--story", metavar="FILE", help="build the video from a storyboard file (for agents; see AGENTS.md)")
    parser.add_argument("--voice", default="am_michael", help="Kokoro voice, for example am_michael, af_heart, bf_emma")
    parser.add_argument("--setup", action="store_true", help="install everything and stop")
    args = parser.parse_args()

    for f in (args.post or []) + ([args.story] if args.story else []):
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
