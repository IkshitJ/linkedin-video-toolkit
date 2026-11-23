"""The basic (no AI) storyboard and its text helpers.   python -m unittest discover tests"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from toolkit import scenes, story

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


class Draft(unittest.TestCase):
    def test_every_variation_is_a_storyboard_that_can_be_built(self):
        for facts in (FACTS, dict(FACTS, private=True), dict(FACTS, languages=[["Rust", None]]), dict(FACTS, languages=[["Go", 100.0]]),
                      dict(FACTS, description="Fast <b>x</b> | simple & small"), {"full": "ada/x", "readme": []}):
            board = story.draft(facts)
            self.assertEqual(scenes.check(board), [], facts)
            self.assertEqual(board["repo"], facts["full"])

    def test_scenes_follow_what_the_repository_has(self):
        self.assertEqual([s["type"] for s in story.draft(FACTS)["scenes"]], ["title", "points", "bars", "stat", "close"])
        self.assertEqual([s["type"] for s in story.draft({"full": "ada/x", "readme": []})["scenes"]], ["title", "close"])
        self.assertEqual([b["name"] for b in story.draft(FACTS)["scenes"][2]["bars"]], ["Python", "Shell"])

    def test_private_repository_shows_no_link_and_no_stars(self):
        board = story.draft(dict(FACTS, private=True))
        self.assertNotIn("github.com", board["caption"] + str(board["scenes"]))
        self.assertNotIn("OpenSource", board["caption"])
        self.assertNotIn("stat", [s["type"] for s in board["scenes"]])

    def test_caption(self):
        caption = story.draft(FACTS)["caption"]
        self.assertTrue(caption.startswith("kokoro-onnx: TTS with kokoro and onnx runtime.\n\nWhat it does:\n- Supports multiple languages\n"))
        self.assertIn("\nBuilt with Python.\n", caption)
        self.assertTrue(caption.endswith("\nhttps://github.com/ada/kokoro-onnx\n\n#OpenSource #Python #tts #MachineLearning\n"))

    def test_build_name(self):
        self.assertEqual(story.vid_for("Ada/My.Repo_2"), "repo-my-repo-2")


class Wording(unittest.TestCase):
    def test_points_come_from_the_feature_list_not_the_setup_steps(self):
        self.assertEqual(story.highlights(FACTS), ["Supports multiple languages", "Fast performance near real-time on macOS M1", "Offer multiple voices"])

    def test_description_falls_back_to_the_readme(self):
        self.assertEqual(story.describe(dict(FACTS, description="")), "TTS with onnx runtime based on Kokoro-TTS")

    def test_small_languages_are_dropped_and_only_real_shares_are_named(self):
        self.assertEqual(story.languages(FACTS), [["Python", 91], ["Shell", 8]])
        self.assertEqual(story.named([["TypeScript", 42], ["Rust", 41], ["Python", 9], ["C++", 4]]), ["TypeScript", "Rust"])
        self.assertEqual(story.named([["Python", 92], ["HTML", 4]]), ["Python"])

    def test_points_are_never_cut_in_the_middle_of_a_list(self):
        readme = [{"tag": "p", "sec": "", "text": "Playwright is a Python library to automate Chromium, Firefox and WebKit browsers with a single API. "
                   "It delivers automation that is ever-green, capable, reliable and fast. See how Playwright is better. More comfortable elsewhere?"}]
        self.assertEqual(story.highlights({"readme": readme}), [
            "Playwright is a Python library to automate Chromium, Firefox and WebKit browsers with a single API",
            "It delivers automation that is ever-green, capable, reliable and fast"])
        self.assertEqual(story.shorten("Automates Chromium, Firefox, WebKit, Safari, Edge and every other browser you can think of today, quickly", 60, strict=True), "")

    def test_spoken_text(self):
        self.assertEqual(story.speak("A C++ API & 50% faster"), "A C plus plus A.P.I. and 50 percent faster.")
        self.assertEqual(story.speak("Lightweight: ~300MB (quantized)"), "Lightweight: about 300MB, quantized.")
        self.assertEqual(story.speak("It exports to P.D.F."), "It exports to P.D.F.")
        self.assertEqual(story.spoken_name("linkedin-video_toolkit"), "linkedin video toolkit")
        self.assertEqual(story.spoken_name("myCoolApp"), "my Cool App")

    def test_helpers(self):
        self.assertEqual(story.slug("My Repo.js"), "my-repo-js")
        self.assertEqual([story.hashtag(w) for w in ("C++", "machine-learning", "Jupyter Notebook", "123", "tts")],
                         ["#Cpp", "#MachineLearning", "#JupyterNotebook", "", "#tts"])
        self.assertEqual(story.shorten("Summarize transcripts: get quick, multilingual summaries using the API", 40), "Summarize transcripts")
        self.assertLessEqual(len(story.shorten("word " * 40, 64)), 64)


if __name__ == "__main__":
    unittest.main()
