"""The AI writer: one request to the Claude API turns a brief (toolkit/material.py) into a
storyboard (toolkit/scenes.py). Used when run.py is started from a terminal with an API key.
A coding agent does the same job itself, without this file: see AGENTS.md.

The request carries the brief and the footage stills, so the model can see what each picture
really shows. The answer is constrained to the storyboard's JSON schema, then checked; if the
check finds problems the model gets one chance to fix them.
"""
import base64
import json
import pathlib

from . import scenes

MODEL = "claude-opus-5-5"
MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
SYSTEM = """You write short product videos and LinkedIn posts for software developers who want to show their own project.

You are given a brief about one GitHub repository: what it says about itself, its README, its numbers, and footage \
(screenshots, README pictures, recordings) of the product. The owner will post the result on their own LinkedIn \
profile, under their own name, so it has to be accurate, specific and worth a stranger's 60 seconds. Their readers \
are other engineers and hiring managers scrolling a feed: they stop for a concrete problem, a real result, or \
something they can see working, and they scroll past adjectives.

Find what is actually interesting about this project, such as the problem it removes, the unusual way it works, \
or a number that surprises, and build the video around that instead of walking through the README in order. Show the \
product itself as much as the footage allows. Say plainly what it does. If the brief is thin, make a shorter video \
rather than padding it.

Write a storyboard in this format:

""" + scenes.FORMAT


class WriterError(Exception):
    """The AI writer could not produce a usable storyboard. The message says why, in plain words."""


def _content(brief, footage):
    """The user turn: the brief as JSON, then each footage still with its file name."""
    content = [{"type": "text", "text": "The brief:\n\n" + json.dumps(brief, indent=1, ensure_ascii=False)}]
    shown = 0
    for item in brief.get("footage") or []:
        path = pathlib.Path(footage) / item["file"]
        kind = MEDIA.get(path.suffix.lower())
        if not kind or "-scroll" in path.stem or not path.is_file() or path.stat().st_size > 4_500_000 or shown == 6:
            continue
        shown += 1
        content.append({"type": "text", "text": "Footage file %s (%s):" % (item["file"], item["what"])})
        content.append({"type": "image", "source": {"type": "base64", "media_type": kind, "data": base64.standard_b64encode(path.read_bytes()).decode("ascii")}})
    content.append({"type": "text", "text": "Write the storyboard for this repository."})
    return content


def _ask(client, messages):
    with client.beta.messages.stream(
        model=MODEL, max_tokens=16000, system=SYSTEM, messages=messages,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",   # if a safety filter declines, another model answers
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": scenes.SCHEMA}},
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "refusal":
        raise WriterError("the model declined to write about this repository")
    if message.stop_reason == "max_tokens":
        raise WriterError("the model's answer was cut off")
    text = next((block.text for block in message.content if block.type == "text"), "")
    try:
        return json.loads(text), text
    except ValueError:
        raise WriterError("the model did not answer with a storyboard")


def write(brief, footage, api_key=None, client=None, say=print):
    """-> a checked storyboard for the brief. Raises WriterError with a reason a person can act on."""
    import anthropic
    client = client or anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": _content(brief, footage)}]
    try:
        story, text = _ask(client, messages)
        problems = scenes.check(story, footage)
        if problems:
            say("  the first draft had %d problem(s); asking for a corrected one..." % len(problems))
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": "That storyboard cannot be built yet. Fix these problems and send the whole storyboard again:\n- " + "\n- ".join(problems)}]
            story, text = _ask(client, messages)
            problems = scenes.check(story, footage)
    except anthropic.AuthenticationError:
        raise WriterError("the API key was not accepted. Check it at https://console.anthropic.com/settings/keys")
    except anthropic.PermissionDeniedError:
        raise WriterError("this API key is not allowed to use %s" % MODEL)
    except anthropic.RateLimitError:
        raise WriterError("the API key has hit its rate limit or has no credit left. Try again in a minute")
    except anthropic.APIStatusError as err:
        raise WriterError("the Claude API answered with an error (%s): %s" % (err.status_code, err.message))
    except anthropic.APIConnectionError:
        raise WriterError("could not reach the Claude API. Check the internet connection")
    if problems:
        raise WriterError("the storyboard still had problems: " + "; ".join(problems[:3]))
    story["repo"] = brief["repo"]
    return story
