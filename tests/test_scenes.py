"""The storyboard format: what is accepted, what is refused and why, and what gets rendered."""
import copy
import json
import pathlib
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from toolkit import material, scenes, writer

P = lambda *phrases: {"say": list(phrases), "cap": list(phrases)}
EXTRA = [dict(P("One command.", "Zero clicks."), type="statement", lines=["One command.", "Zero clicks."], accent="Zero"),
         dict(P("This is what it prints."), type="console", heading="", lines=["$ weather berlin", "Berlin  12 C  light rain", "", "tomorrow  9 C"])]
BOARD = {"repo": "ada/weather-cli", "caption": "A hook.\n\nDetails.\n\nhttps://github.com/ada/weather-cli\n\n#Python #CommandLine", "scenes": [
    dict(P("Do I need a jacket?", "Ask the terminal."), type="title", kicker="A side project", title="weather-cli", subtitle="The forecast in the terminal"),
    dict(P("Here it is, running."), type="footage", src="demo.mp4", label="Running"),
    dict(P("And this is the site.", "It scrolls."), type="footage", src="site.png", label=""),
    dict(P("Three reasons.", "It caches.", "No account.", "No dependencies."), type="points", heading="Why it is fast", points=["Caches the answer", "No account", "Zero dependencies"]),
    dict(P("Two steps."), type="steps", heading="How", steps=[{"title": "Install", "text": "with pip"}, {"title": "Ask", "text": "any city"}]),
    dict(P("Install it.", "Then ask."), type="terminal", heading="", lines=["pip install weather-cli", "weather berlin --days 3"]),
    dict(P("It was slow.", "Now it is not."), type="compare", heading="", left={"title": "Before", "items": ["Open a browser", "Wait"]}, right={"title": "After", "items": ["One command"]}),
    dict(P("Mostly Python."), type="bars", heading="Built with", bars=[{"name": "Python", "value": 90}, {"name": "Shell", "value": 10}]),
    dict({"say": ["Twelve hundred stars."], "cap": ["1,200 stars."]}, type="stat", value=1200, prefix="", suffix="", label="stars on GitHub"),
    dict(P("Find it on GitHub.", "Link in the post."), type="close", heading="Find it on GitHub", title="weather-cli", link="github.com/ada/weather-cli"),
]}


def footage():
    folder = pathlib.Path(tempfile.mkdtemp())
    for name in ("demo.mp4", "site.png"):
        (folder / name).write_bytes(b"x")
    return folder


class Check(unittest.TestCase):
    def broken(self, change, expect):
        board = copy.deepcopy(BOARD)
        change(board)
        problems = scenes.check(board, footage())
        self.assertTrue(any(expect in p for p in problems), "%r not in %r" % (expect, problems))

    def test_a_complete_storyboard_has_no_problems(self):
        self.assertEqual(scenes.check(BOARD, footage()), [])

    def test_problems_are_named_so_a_writer_can_fix_them(self):
        self.broken(lambda b: b["scenes"][3]["cap"].pop(), 'scene 4 (points): "cap" must have exactly as many')
        self.broken(lambda b: b["scenes"][1].update(src="missing.png"), "there is no footage file 'missing.png'; the files are: demo.mp4, site.png")
        self.broken(lambda b: b["scenes"][1].update(src="notes.txt"), "is not an image or a video file")
        self.broken(lambda b: b["scenes"][3].update(points=["only one"]), '"points" must have 2 to 4 items, not 1')
        self.broken(lambda b: b["scenes"][7]["bars"][0].update(value=140), 'every bar needs a "name" and a "value" from 0 to 100')
        self.broken(lambda b: b["scenes"][8].update(value="many"), '"value" must be a number')
        self.broken(lambda b: b["scenes"][2].update(type="montage"), "scene 3: unknown type 'montage'")
        self.broken(lambda b: b["scenes"].reverse(), "the first scene must be a title, statement or footage scene")
        self.broken(lambda b: b["scenes"].pop(), "the last scene must be of type close")
        self.broken(lambda b: b["scenes"][0].update(say=[]), '"say" must be 1 to 5 non-empty phrases')
        self.broken(lambda b: b["scenes"][0].update(title=""), '"title" is missing')
        self.broken(lambda b: b["scenes"][4]["say"].__setitem__(0, "word " * 250), "the narration is")
        self.broken(lambda b: b.update(caption="  "), '"caption" is missing or empty')
        self.assertEqual(scenes.check("nonsense"), ["the storyboard must be a JSON object"])
        self.assertEqual(scenes.check({"caption": "x"}), ['"scenes" must be a list of 2 to 10 scenes'])

    def test_footage_is_not_looked_up_when_no_folder_is_given(self):
        self.assertEqual(scenes.check(BOARD), [])

    def test_the_schema_for_the_model_covers_the_same_scene_types_and_fields(self):
        variants = {v["properties"]["type"]["const"]: v for v in scenes.SCHEMA["properties"]["scenes"]["items"]["anyOf"]}
        self.assertEqual(set(variants), set(scenes.NEEDS))
        for kind, needed in scenes.NEEDS.items():
            self.assertTrue(set(needed) <= set(variants[kind]["required"]), kind)
            self.assertIs(variants[kind]["additionalProperties"], False)
            self.assertIn("  %-9s " % kind, scenes.FORMAT)
        for scene in BOARD["scenes"] + EXTRA:   # the examples above uses exactly the fields the schema asks for
            self.assertEqual(set(scene), set(variants[scene["type"]]["required"]), scene["type"])


class Render(unittest.TestCase):
    def setUp(self):
        self.made = scenes.render(BOARD, "repo-weather-cli", {"demo.mp4": (75, 15)})

    def test_one_section_per_scene_in_order_with_matching_phrases(self):
        ids = re.findall(r'<section class="scene" id="s-(\w+)"', self.made["html"])
        self.assertEqual(ids, [s[0] for s in self.made["segments"]])
        self.assertEqual(len(ids), len(BOARD["scenes"]))
        for sid, say, cap, pause in self.made["segments"]:
            self.assertEqual(len(say.split("|")), len(cap.split("|")), sid)

    def test_every_animation_and_sound_points_at_a_phrase_that_exists(self):
        count = {s[0]: len(s[1].split("|")) for s in self.made["segments"]}
        for sid, body in re.findall(r'id="s-(\w+)"[^>]*>(.*?)</section>', self.made["html"], re.S):
            for n in re.findall(r'data-at="p(\d+)', body):
                self.assertLess(int(n), count[sid], sid)
        for cue in self.made["cues"]:
            self.assertLess(cue[2], count[cue[1]], cue)

    def test_footage_a_recording_plays_and_a_picture_is_shown(self):
        self.assertIn('<canvas data-seq="repo-weather-cli/footage/demo.mp4.frames,75,15"', self.made["html"])
        self.assertIn('<img src="repo-weather-cli/footage/site.png" data-pan>', self.made["html"])

    def test_spoken_text_is_made_speakable_and_captions_are_kept(self):
        say, cap = self.made["segments"][8][1], self.made["segments"][8][2]
        self.assertEqual((say, cap), ("Twelve hundred stars.", "1,200 stars."))
        self.assertIn('data-count="0,1200,,"', self.made["html"])

    def test_text_from_the_storyboard_cannot_break_the_page_or_the_script(self):
        board = copy.deepcopy(BOARD)
        board["scenes"][0].update(title="<script>alert(1)</script>", say=["a | b", "c"], cap=["a | b", "c"])
        made = scenes.render(board, "v")
        self.assertNotIn("<script>alert", made["html"])
        self.assertEqual(len(made["segments"][0][1].split("|")), 2)

    def test_statement_and_console_scenes(self):
        board = dict(BOARD, scenes=[BOARD["scenes"][0]] + EXTRA + [BOARD["scenes"][-1]])
        self.assertEqual(scenes.check(board), [])
        page = scenes.render(board, "v")["html"]
        self.assertIn('<span class="f">Zero</span> clicks.', page)
        self.assertEqual(re.findall(r'data-at="([\d.]+)" data-fx="fade" data-dur="0.25">', page), ["0.30", "0.75", "1.20", "1.65"])   # one line after another
        self.assertIn("$ weather berlin", page)
        self.assertIn("Before", scenes.render(BOARD, "v")["html"])
        broken = copy.deepcopy(board)
        broken["scenes"][1]["lines"] = ["a", "b", "c", "d"]
        self.assertTrue(any('"lines" must have 1 to 3 items' in p for p in scenes.check(broken)))
        broken = copy.deepcopy(BOARD)
        broken["scenes"][6]["right"] = {"title": "After", "items": []}
        self.assertTrue(any('"left" and "right" each need' in p for p in scenes.check(broken)))

    def test_items_appear_in_step_with_the_phrases(self):
        self.assertEqual([scenes._at(i, 3, 4) for i in range(3)], ["p1", "p2", "p3"])
        self.assertEqual([scenes._at(i, 2, 2) for i in range(2)], ["p0", "p1"])
        self.assertEqual([scenes._at(i, 3, 1) for i in range(3)], ["p0+0.3", "p0+0.9", "p0+1.5"])


class Material(unittest.TestCase):
    def test_readme_pictures_worth_showing(self):
        images = [{"src": "https://img.shields.io/badge/build-passing.svg", "alt": "build"}, {"src": "https://x.test/logo.svg", "alt": ""},
                  {"src": "https://camo.githubusercontent.com/abc", "alt": "CI badge"}, {"src": "https://x.test/shot.png", "alt": "The dashboard"},
                  {"src": "https://x.test/shot.png", "alt": "again"}, {"src": "/relative.png", "alt": ""}, {"src": "https://x.test/demo.gif?raw=1", "alt": ""}]
        self.assertEqual([i["src"] for i in material.worth_showing(images)], ["https://x.test/shot.png", "https://x.test/demo.gif?raw=1"])

    def test_readme_as_text_keeps_its_structure(self):
        items = [{"tag": "h1", "text": "App", "sec": ""}, {"tag": "p", "text": "Does things.", "sec": "App"},
                 {"tag": "h2", "text": "Features", "sec": ""}, {"tag": "li", "text": "Fast", "sec": "Features"}]
        self.assertEqual(material.readme_text(items), "# App\nDoes things.\n\n## Features\n- Fast")

    def test_the_brief_lists_collected_and_hand_added_footage(self):
        real = material.download, material.screenshots
        self.addCleanup(lambda: (setattr(material, "download", real[0]), setattr(material, "screenshots", real[1])))
        folder = pathlib.Path(tempfile.mkdtemp())
        (folder / "footage").mkdir()
        (folder / "footage" / "my-recording.mp4").write_bytes(b"x")

        def download(url, where, stem):
            path = pathlib.Path(where) / (stem + ".png"); path.write_bytes(b"x"); return path

        def screenshots(url, where, stem, say):
            path = pathlib.Path(where) / (stem + ".png"); path.write_bytes(b"x"); return [(path, "the top of " + url)]
        material.download, material.screenshots = download, screenshots
        facts = {"full": "ada/app", "description": "An app", "private": False, "stars": 5, "forks": 0, "topics": [], "homepage": "https://app.test",
                 "languages": [["Go", 99.96]], "readme": [], "code": ["go run ."], "images": [{"src": "https://x.test/shot.png", "alt": "Dashboard"}]}
        brief = material.gather(facts, folder, say=lambda *a: None)
        self.assertEqual([f["file"] for f in brief["footage"]], ["readme-1.png", "website.png", "github.png", "my-recording.mp4"])
        self.assertEqual(brief["footage"][0]["what"], "a picture from the README: Dashboard")
        self.assertEqual(json.loads((folder / "brief.json").read_text(encoding="utf-8")), brief)
        self.assertEqual((brief["link"], brief["languages"], brief["code_blocks"]), ("https://github.com/ada/app", [["Go", 100.0]], ["go run ."]))
        private = material.gather(dict(facts, private=True, homepage=""), pathlib.Path(tempfile.mkdtemp()), say=lambda *a: None)
        self.assertEqual(([f["file"] for f in private["footage"]], private["link"]), (["readme-1.png"], ""))


class FakeClient:
    """Stands in for anthropic.Anthropic: records each request and answers with the next canned text."""

    def __init__(self, *answers, stop="end_turn"):
        self.answers, self.requests, self.stop = list(answers), [], stop
        self.beta = self.messages = self

    def stream(self, **request):
        self.requests.append(request)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        text = self.answers.pop(0)
        block = type("Block", (), {"type": "text", "text": text})()
        return type("Message", (), {"stop_reason": self.stop, "content": [block]})()


class Writer(unittest.TestCase):
    def setUp(self):
        self.footage = footage()
        (self.footage / "site.png").write_bytes(b"\x89PNG fake")
        self.brief = {"repo": "ada/weather-cli", "description": "Weather", "footage": [
            {"file": "site.png", "what": "the website"}, {"file": "demo.mp4", "what": "added by hand"}, {"file": "site-scroll.png", "what": "scroll"}]}

    def test_the_request_carries_the_brief_the_pictures_and_the_format(self):
        client = FakeClient(json.dumps(BOARD))
        board = writer.write(self.brief, self.footage, client=client, say=lambda *a: None)
        self.assertEqual(board["scenes"], BOARD["scenes"])
        request = client.requests[0]
        self.assertEqual(request["model"], "claude-opus-5-5")
        self.assertEqual(request["output_config"]["format"], {"type": "json_schema", "schema": scenes.SCHEMA})
        self.assertIn(scenes.FORMAT, request["system"])
        self.assertNotIn("thinking", request)
        content = request["messages"][0]["content"]
        self.assertIn('"repo": "ada/weather-cli"', content[0]["text"])
        self.assertEqual([c["source"]["media_type"] for c in content if c["type"] == "image"], ["image/png"])   # stills only, once
        self.assertIn("Footage file site.png (the website):", [c.get("text") for c in content])

    def test_a_storyboard_with_problems_is_sent_back_once_with_the_problems(self):
        bad = copy.deepcopy(BOARD)
        bad["scenes"][1]["src"] = "invented.png"
        client = FakeClient(json.dumps(bad), json.dumps(BOARD))
        board = writer.write(self.brief, self.footage, client=client, say=lambda *a: None)
        self.assertEqual(board["scenes"][1]["src"], "demo.mp4")
        self.assertEqual([m["role"] for m in client.requests[1]["messages"]], ["user", "assistant", "user"])
        self.assertIn("there is no footage file 'invented.png'", client.requests[1]["messages"][2]["content"])

    def test_failures_are_reported_in_plain_words(self):
        bad = copy.deepcopy(BOARD)
        bad["scenes"][1]["src"] = "invented.png"
        for client, expect in ((FakeClient(json.dumps(bad), json.dumps(bad)), "still had problems"), (FakeClient("not json"), "did not answer with a storyboard"),
                               (FakeClient("{}", stop="refusal"), "declined"), (FakeClient("{}", stop="max_tokens"), "cut off")):
            with self.assertRaises(writer.WriterError) as caught:
                writer.write(self.brief, self.footage, client=client, say=lambda *a: None)
            self.assertIn(expect, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
