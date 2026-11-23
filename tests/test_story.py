"""python -m unittest discover tests     (run with the .venv Python)"""
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from toolkit import story

FACTS = {
    "full": "ada/kokoro-onnx", "description": "TTS with kokoro and onnx runtime", "private": False,
    "stars": 2923, "forks": 329, "languages": [["Python", 91.4], ["Shell", 8.2], ["Makefile", 0.4]],
    "topics": ["tts", "machine-learning", "python"],
    "readme": [
        {"tag": "h1", "text": "kokoro-onnx", "sec": ""},
        {"tag": "p", "text": "TTS with onnx runtime based on Kokoro-TTS", "sec": "kokoro-onnx"},
        {"tag": "li", "text": "Install uv from the website first", "sec": "Setup"},
        {"tag": "li", "text": "Then run the installer script", "sec": "Setup"},
        {"tag": "li", "text": "\U0001F30D Supports multiple languages", "sec": "Features \U0001F31F"},
        {"tag": "li", "text": "Fast performance near real-time on macOS M1", "sec": "Features \U0001F31F"},
        {"tag": "li", "text": "Offer multiple voices", "sec": "Features \U0001F31F"},
        {"tag": "li", "text": "Lightweight: ~300MB (quantized: ~80MB)", "sec": "Features \U0001F31F"},
    ],
}


class Story(unittest.TestCase):
    def test_every_scene_has_as_many_spoken_as_caption_phrases(self):
        for sid, say, cap, pause in story.make(FACTS)["segments"]:
            self.assertEqual(len(say.split("|")), len(cap.split("|")), sid)
            self.assertTrue(all(p.strip() for p in say.split("|") + cap.split("|")), sid)

    def test_scenes_in_the_page_match_the_script(self):
        made = story.make(FACTS)
        self.assertEqual(re.findall(r'<section class="scene" id="s-(\w+)"', made["html"]), [s[0] for s in made["segments"]])
        self.assertEqual([s[0] for s in made["segments"]], ["hook", "what", "stack", "stars", "close"])
        self.assertIn('src="repo-kokoro-onnx_timeline.js"', made["html"])

    def test_every_animation_points_at_a_phrase_that_exists(self):
        made = story.make(FACTS)
        count = {s[0]: len(s[1].split("|")) for s in made["segments"]}
        for sid, body in re.findall(r'id="s-(\w+)">(.*?)</section>', made["html"], re.S):
            for n in re.findall(r'data-at="p(\d+)', body):
                self.assertLess(int(n), count[sid], sid)
        for cue in made["cues"]:
            self.assertLess(cue[2], count[cue[1]], cue)

    def test_points_come_from_the_feature_list_not_the_setup_steps(self):
        self.assertEqual(story.highlights(FACTS), ["Supports multiple languages", "Fast performance near real-time on macOS M1", "Offer multiple voices"])

    def test_description_falls_back_to_the_readme(self):
        self.assertEqual(story.describe(dict(FACTS, description="")), "TTS with onnx runtime based on Kokoro-TTS")

    def test_a_bare_repository_still_makes_a_video(self):
        made = story.make({"full": "ada/x", "description": "", "readme": [], "languages": [], "topics": []})
        self.assertEqual([s[0] for s in made["segments"]], ["hook", "close"])
        self.assertIn("https://github.com/ada/x", made["post"])

    def test_private_repository_shows_no_link(self):
        made = story.make(dict(FACTS, private=True))
        self.assertNotIn("github.com", made["post"])
        self.assertNotIn("OpenSource", made["post"])
        self.assertNotIn("github.com", made["html"].split("<div id=\"stage\">")[1])
        self.assertNotIn("stars", [s[0] for s in made["segments"]])

    def test_post_text(self):
        post = story.make(FACTS)["post"]
        self.assertTrue(post.startswith("kokoro-onnx: TTS with kokoro and onnx runtime.\n\nWhat it does:\n• Supports multiple languages\n"))
        self.assertIn("\nBuilt with Python.\n", post)
        self.assertTrue(post.endswith("\nhttps://github.com/ada/kokoro-onnx\n\n#OpenSource #Python #tts #MachineLearning\n"))

    def test_text_from_the_repository_cannot_break_the_page_or_the_script(self):
        made = story.make(dict(FACTS, description="Fast <script>alert(1)</script> | simple & small"))
        self.assertNotIn("<script>alert", made["html"])
        self.assertEqual(len(made["segments"][0][1].split("|")), 2)

    def test_small_languages_are_dropped_and_unknown_shares_become_pills(self):
        self.assertEqual(story.languages(FACTS), [["Python", 91], ["Shell", 8]])
        made = story.make(dict(FACTS, languages=[["Rust", None]]))
        self.assertIn(">Rust</span>", made["html"])
        self.assertNotIn("data-bar", made["html"])

    def test_spoken_text(self):
        self.assertEqual(story.speak("A C++ API & 50% faster"), "A C plus plus A.P.I. and 50 percent faster.")
        self.assertEqual(story.speak("Lightweight: ~300MB (quantized)"), "Lightweight: about 300MB, quantized.")
        self.assertEqual(story.spoken_name("linkedin-video_toolkit"), "linkedin video toolkit")
        self.assertEqual(story.spoken_name("myCoolApp"), "my Cool App")

    def test_only_languages_with_a_real_share_are_named(self):
        self.assertEqual(story.named([["TypeScript", 42], ["Rust", 41], ["Python", 9], ["C++", 4]]), ["TypeScript", "Rust"])
        self.assertEqual(story.named([["Python", 92], ["HTML", 4]]), ["Python"])

    def test_points_are_never_cut_in_the_middle_of_a_list(self):
        readme = [{"tag": "p", "sec": "", "text": "Playwright is a Python library to automate Chromium, Firefox and WebKit browsers with a single API. "
                   "It delivers automation that is ever-green, capable, reliable and fast. See how Playwright is better."}]
        self.assertEqual(story.highlights({"readme": readme}), [
            "Playwright is a Python library to automate Chromium, Firefox and WebKit browsers with a single API",
            "It delivers automation that is ever-green, capable, reliable and fast"])
        self.assertEqual(story.shorten("Automates Chromium, Firefox, WebKit, Safari, Edge and every other browser you can think of today, quickly", 60, strict=True), "")

    def test_helpers(self):
        self.assertEqual(story.slug("My Repo.js"), "my-repo-js")
        self.assertEqual([story.hashtag(w) for w in ("C++", "machine-learning", "Jupyter Notebook", "123", "tts")],
                         ["#Cpp", "#MachineLearning", "#JupyterNotebook", "", "#tts"])
        self.assertEqual(story.shorten("Summarize transcripts: get quick, multilingual summaries using the API", 40), "Summarize transcripts")
        self.assertLessEqual(len(story.shorten("word " * 40, 64)), 64)


if __name__ == "__main__":
    unittest.main()
