# Instructions for coding agents

This file is for an AI coding agent (Claude Code, Codex, Cursor and the like) that has been asked to "run this", "run it again", "make a post" or similar in this repository. People should read [README.md](README.md) instead.

The job: make a short video about ONE of the user's GitHub repositories, with a caption, and post it to the user's LinkedIn. You write the video and the caption yourself; no API key is needed.

## Two rules that come before everything else

1. **The user chooses the repository. You never do.** Do not build, render or open any video until the user has told you, in this conversation, which repository the post is about. Not the most recent one, not one you find in `out/` or `video/build/`, not an example. If you do not know, ask and stop.
2. **The user presses Post, not you.** The tool opens LinkedIn, attaches the video, writes the caption and stops. Never pass `--press-post` unless the user asks for exactly that, and never press the Post button for them any other way.

## The procedure

### 1. List the repositories, then ask

```sh
python run.py --list
```

This checks the GitHub and LinkedIn sign-ins in the user's default browser and prints their repositories. If it says `Waiting...`, tell the user to sign in in the browser window it opened.

Show the user the list and ask which repository they want to post about. **Stop here until they answer.** If they pick a private one, tell them the post will make its name, description and README lines public, and ask them to confirm.

### 2. Collect the material

```sh
python run.py --repo OWNER/NAME --brief
```

This makes no video. It writes:

- `video/build/repo-<name>/brief.json`: the description, README text, code blocks, languages, stars, website and a list of the footage files;
- `video/build/repo-<name>/footage/`: real pictures of the product (README images, screenshots of the project's website and of the repository page).

Read the brief. **Look at every footage file** (open the images) so you know what each one really shows.

### 3. Get better footage if you can

The video is far better when it shows the product working. If the collected footage is thin, add your own files to the `footage/` folder:

- **A web app or a site:** clone the repository into `repos/` (ignored by git), start it, and record it:
  `.venv/bin/python tools/record.py http://localhost:3000 video/build/repo-<name>/footage/demo.mp4 12`
  For clicks and typing, copy `tools/demo_example.py` and script a short walkthrough.
- **A command-line tool or a library:** run it on a small real example and take a screenshot of the real output, or use a `terminal` scene with the real commands from the README.
- **Hardware, firmware, research code:** use the README's photos, diagrams and result plots.

Never fabricate footage: no mock-ups, no invented output, no screenshots of something else. If a clip is a re-enactment, the caption must say so. Do not record or show anyone's private data. `.mp4`, `.mov`, `.webm`, `.gif`, `.png`, `.jpg` and `.webp` files are accepted.

### 4. Write the storyboard

Write `video/build/repo-<name>/story.json`. The format is below. Aim for a video a stranger would watch to the end: open with the problem or the most surprising true fact, show the product early, explain how it works, give real numbers, end with where to find it. Do not walk through the README in order.

Everything you say must be true and come from the repository. No invented features, numbers, users or quotes.

### 5. Build it and hand it to the user in LinkedIn

If the command stops with "ASK THE USER how the LinkedIn post should be filled in" (exit code 4), their default browser is Safari and they have not chosen yet. Put the choice to them exactly as printed (Chrome in the background, Safari with the keyboard and mouse taken over, or another browser), wait for the answer, and run the `--post ... --post-with NAME` command it printed. Do not choose for them. Their answer is remembered.

If they chose Safari, tell them before every run that the LinkedIn step takes over the keyboard and mouse for one to three minutes, so they must not touch the computer until it says READY. If they chose Chrome or another browser, the first run shows a LinkedIn sign-in page in that browser's own window; tell them to sign in there.

```sh
python run.py --story video/build/repo-<name>/story.json
```

If it lists problems, fix the storyboard and run it again. Otherwise it builds `out/repo-<name>.mp4` and `out/repo-<name>.txt` (the caption), opens the video, then opens LinkedIn, attaches the video, writes the caption and stops with `READY`. Nothing is published: the post is waiting in the browser for the user to read, edit and press **Post**.

To check your work before LinkedIn is opened, add `--no-post`, then `cd video && ../.venv/bin/python render.py repo-<name> 3 12 25` writes still frames at those seconds into `video/build/preview/`. Look at them. Fix text that overflows, footage that shows the wrong thing, and scenes that are empty. When it is right, `python run.py --post out/repo-<name>.mp4 out/repo-<name>.txt` does the LinkedIn step on its own.

With Chrome or another browser in its own window, the command does not return after `READY`: it keeps that window open until the user has posted or closed it, for up to 30 minutes. Run it in the background and go on to step 6 as soon as it prints `READY`. With Safari it returns straight away.

### 6. Tell the user it is waiting

Say that the post is filled in and waiting in their browser, show them the caption, and tell them to press Post there, or to close the post and choose Discard. If they want changes, they should discard it first; then edit `story.json` and run step 5 again. Report the last line the command printed if it was not `READY` (the step that failed).

## The storyboard format

```
A storyboard is one JSON object:

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
```

This text is `FORMAT` in [toolkit/scenes.py](toolkit/scenes.py), which is also what checks and renders the storyboard. If the two ever differ, the code is right.

A small example:

```json
{
  "repo": "ada/weather-cli",
  "caption": "I got tired of opening a browser to see if I need a jacket.\n\nSo I wrote weather-cli: one command, and the forecast is in the terminal in under a second.\n\n- It caches the last answer, so it works on a train.\n- No account, no API key.\n- 400 lines of Python, no dependencies.\n\nhttps://github.com/ada/weather-cli\n\n#Python #CommandLine #OpenSource #DeveloperTools #Weather",
  "scenes": [
    {"type": "title", "kicker": "A side project", "title": "weather-cli", "subtitle": "The forecast, without leaving the terminal",
     "say": ["Do I need a jacket today?", "I answer that without opening a browser."],
     "cap": ["Do I need a jacket today?", "I answer that without opening a browser."]},
    {"type": "footage", "src": "demo.mp4", "label": "weather-cli, running",
     "say": ["One command, and the forecast is there in under a second."],
     "cap": ["One command, and the forecast is there in under a second."]},
    {"type": "terminal", "heading": "", "lines": ["pip install weather-cli", "weather berlin --days 3"],
     "say": ["Install it with pip.", "Then ask for any city."], "cap": ["Install it with pip.", "Then ask for any city."]},
    {"type": "points", "heading": "Why it is fast", "points": ["Caches the last answer on disk", "No account and no API key", "400 lines, zero dependencies"],
     "say": ["Three reasons it is fast.", "It caches the last answer.", "It needs no account.", "And it is four hundred lines with no dependencies."],
     "cap": ["Three reasons it is fast.", "It caches the last answer.", "It needs no account.", "And it is 400 lines with no dependencies."]},
    {"type": "close", "heading": "Find it on GitHub", "title": "weather-cli", "link": "github.com/ada/weather-cli",
     "say": ["Find it on GitHub.", "The link is in the post."], "cap": ["Find it on GitHub.", "The link is in the post."]}
  ]
}
```

## Other things worth knowing

- `python run.py --basic --repo OWNER/NAME` makes the plain template video without any writer. Use it only if the user asks for it.
- When a person runs `python run.py` in a terminal, Claude writes the storyboard through the API with the user's own key. That path is `toolkit/writer.py`; you do not need it.
- Build one video at a time. Do not commit `out/`, `video/build/`, `.browser/` or `.env`.
- Tests: `.venv/bin/python -m unittest discover tests`
