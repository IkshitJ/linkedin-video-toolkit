"""Reading GitHub pages and waiting for sign-ins, without a browser or the network."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from toolkit import browser, github, linkedin

HEAD = '<html><head><meta name="user-login" content="%s"><title>%s</title></head><body>'
LIST = HEAD % ("ada", "ada (Ada) / Repositories") + """
<div id="user-repositories-list"><ul>
 <li><h3><a href="/ada/weather-cli" itemprop="name codeRepository">
        weather-cli</a> <span class="Label Label--secondary">Public</span></h3>
     <p itemprop="description">
        A tiny weather report &amp; forecast   </p>
     <span itemprop="programmingLanguage">Python</span> <relative-time datetime="2026-11-20T10:00:00Z">Nov 20</relative-time></li>
 <li><h3><a href="/ada/notes" itemprop="name codeRepository">notes</a> <span class="Label">Private</span></h3>
     <span>Forked from grace/notes</span></li>
</ul><a class="next_page" rel="next" href="/ada?page=2&amp;tab=repositories">Next</a></div></body></html>"""
REPO = HEAD % ("ada", "GitHub - ada/weather-cli: A tiny weather report · GitHub") + """
<article class="markdown-body entry-content"><h1>weather-cli</h1>
<p><img src="badge.svg" alt="build passing"> <img src="https://x.test/shot.png" alt="The app"> </p>
<p>Weather for your terminal, <code>fast</code>.</p>
<h2>Features</h2>
<ul><li>Shows today and tomorrow<ul><li>nested detail</li></ul></li><li>Works offline <svg><title>icon</title></svg></li></ul>
<h2>Install</h2><pre>pip install weather-cli</pre><script>alert(1)</script>
</article></body></html>"""


class Session:
    """Stands in for a browser: serves `pages` by address, and becomes signed in after `after` peeks."""
    label = "Test browser"

    def __init__(self, pages=None, after=0, signed_in=("https://github.com/", HEAD % ("ada", "GitHub"))):
        self.pages, self.after, self.signed_in, self.shown, self.fetched = pages or {}, after, signed_in, [], []

    def fetch(self, url, wait_for=None, settle=0, source=True):
        self.fetched.append(url)
        return self.pages.get(url, (url, ""))

    def show(self, url):
        self.shown.append(url)

    def peek(self):
        self.after -= 1
        return self.signed_in if self.after <= 0 else (self.shown[-1], HEAD % ("", "Sign in"))

    def pause(self, seconds):
        pass


class Pages(unittest.TestCase):
    def test_repository_list(self):
        rows, more = github.parse_repo_list(LIST)
        self.assertEqual(rows[0], {"full": "ada/weather-cli", "name": "weather-cli", "description": "A tiny weather report & forecast",
                                   "language": "Python", "private": False, "fork": False, "updated": "2026-11-20T10:00:00Z"})
        self.assertEqual((rows[1]["full"], rows[1]["private"], rows[1]["fork"], rows[1]["language"]), ("ada/notes", True, True, ""))
        self.assertEqual(more, "https://github.com/ada?page=2&tab=repositories")
        self.assertEqual(github.parse_repo_list("<html></html>"), ([], ""))

    def test_repository_page(self):
        page = github.parse_repo_page(REPO)
        self.assertEqual(page["description"], "A tiny weather report")
        self.assertFalse(page["missing"])
        self.assertEqual(page["readme"], [
            {"tag": "h1", "text": "weather-cli", "sec": ""},
            {"tag": "p", "text": "Weather for your terminal, fast.", "sec": "weather-cli"},
            {"tag": "h2", "text": "Features", "sec": ""},
            {"tag": "li", "text": "Shows today and tomorrow", "sec": "Features"},
            {"tag": "li", "text": "nested detail", "sec": "Features"},
            {"tag": "li", "text": "Works offline", "sec": "Features"},
            {"tag": "h2", "text": "Install", "sec": ""}])
        self.assertEqual(page["code"], ["pip install weather-cli"])
        self.assertEqual(page["images"], [{"src": "https://github.com/badge.svg", "alt": "build passing"}, {"src": "https://x.test/shot.png", "alt": "The app"}])

    def test_titles_with_and_without_a_description_or_a_sign_in(self):
        for title, want in (("ada/weather-cli: Fast: and small", "Fast: and small"), ("GitHub - ada/weather-cli · GitHub", ""), ("ada/weather-cli", "")):
            self.assertEqual(github.parse_repo_page(HEAD % ("ada", title))["description"], want, title)
        self.assertTrue(github.parse_repo_page(HEAD % ("", "Page not found · GitHub"))["missing"])

    def test_who_is_signed_in(self):
        self.assertEqual(github.signed_in_user(LIST), "ada")
        self.assertEqual(github.signed_in_user(HEAD % ("", "GitHub")), "")


class SignIns(unittest.TestCase):
    def setUp(self):
        self.said = []

    def test_github_already_signed_in_opens_nothing(self):
        s = Session({"https://github.com/": ("https://github.com/", HEAD % ("ada", "GitHub"))})
        self.assertEqual(github.ensure_signed_in(s, self.said.append), "ada")
        self.assertEqual(s.shown, [])

    def test_github_signed_out_shows_the_sign_in_page_and_waits(self):
        s = Session(after=3)
        self.assertEqual(github.ensure_signed_in(s, self.said.append), "ada")
        self.assertEqual(s.shown, ["https://github.com/login"])
        self.assertIn("not signed in", self.said[0])
        self.assertIn("Test browser", self.said[0])

    def test_linkedin_signed_in_and_signed_out(self):
        s = Session({"https://www.linkedin.com/feed/": ("https://www.linkedin.com/feed/foryou/", "")})
        linkedin.ensure_signed_in(s, self.said.append)
        self.assertEqual((s.shown, self.said), ([], ["LinkedIn: signed in"]))
        s = Session({"https://www.linkedin.com/feed/": ("https://www.linkedin.com/uas/login?session_redirect=feed", "")},
                    after=2, signed_in=("https://www.linkedin.com/feed/", ""))
        linkedin.ensure_signed_in(s, self.said.append)
        self.assertEqual(s.shown, ["https://www.linkedin.com/login"])

    def test_gives_up_instead_of_waiting_for_ever(self):
        with self.assertRaises(SystemExit):
            github.ensure_signed_in(Session(after=10 ** 9), self.said.append, wait=0)


class Facts(unittest.TestCase):
    def setUp(self):
        self.api = github._api
        self.addCleanup(lambda: setattr(github, "_api", self.api))

    def test_public_repository(self):
        github._api = lambda path: {"Python": 900, "Shell": 100} if path.endswith("/languages") else {
            "full_name": "ada/weather-cli", "description": "A tiny weather report", "private": False, "stargazers_count": 42, "forks_count": 3, "topics": ["cli"], "homepage": "https://weather.test"}
        facts = github.repo_facts(Session({"https://github.com/ada/weather-cli": ("x", REPO)}), "ada/weather-cli")
        self.assertEqual((facts["stars"], facts["forks"], facts["topics"], facts["private"]), (42, 3, ["cli"], False))
        self.assertEqual((facts["homepage"], facts["code"], len(facts["images"])), ("https://weather.test", ["pip install weather-cli"], 2))
        self.assertEqual(facts["languages"], [["Python", 90.0], ["Shell", 10.0]])
        self.assertEqual(len(facts["readme"]), 7)

    def test_private_repository_never_asks_the_public_api(self):
        github._api = lambda path: self.fail("asked the public API about a private repository")
        row = {"description": "Secret notes", "private": True, "language": "Go"}
        facts = github.repo_facts(Session({"https://github.com/ada/notes": ("x", REPO)}), "ada/notes", row)
        self.assertEqual((facts["private"], facts["description"], facts["languages"], facts["stars"]), (True, "Secret notes", [["Go", None]], None))

    def test_a_repository_the_public_api_cannot_see_is_treated_as_private(self):
        github._api = lambda path: {"_status": 404}
        self.assertTrue(github.repo_facts(Session({"https://github.com/ada/x": ("x", REPO)}), "ada/x")["private"])

    def test_missing_repository_and_bad_names(self):
        github._api = lambda path: {"_status": 404}
        for name, page in (("ada/gone", HEAD % ("ada", "Page not found · GitHub")), ("not a repo", "")):
            with self.assertRaises(SystemExit):
                github.repo_facts(Session({"https://github.com/ada/gone": ("x", page)}), name)


class Browsers(unittest.TestCase):
    def test_names_the_systems_use_for_browsers(self):
        for text, path, want in (("MSEdgeHTM", "", "edge"), ("ChromeHTML", "", "chrome"), ("FirefoxURL-308046B0AF4A39CB", "", "firefox"),
                                 ("com.apple.Safari", "/x/Safari", "safari"), ("com.google.Chrome", "/x/Google Chrome", "chrome"),
                                 ("BraveHTML", "C:/brave.exe", "C:/brave.exe"), ("firefox.desktop", "", "firefox"), ("unknown.desktop", "", None)):
            self.assertEqual(browser.name_of(text, path), want, text)

    def test_the_browser_for_the_linkedin_post_is_asked_once_when_the_default_is_safari(self):
        import tempfile
        real = browser.default_browser, browser.CHOICE, browser.PROFILES
        self.addCleanup(lambda: (setattr(browser, "default_browser", real[0]), setattr(browser, "CHOICE", real[1]), setattr(browser, "PROFILES", real[2])))
        browser.PROFILES = pathlib.Path(tempfile.mkdtemp())
        browser.CHOICE = browser.PROFILES / "post-with.txt"
        quiet = lambda *a: None
        browser.default_browser = lambda: "edge"
        self.assertEqual(browser.poster_choice(say=quiet), "edge")                       # not Safari: no question
        browser.default_browser = lambda: "safari"
        self.assertIsNone(browser.poster_choice(say=quiet))                              # nobody to ask
        self.assertEqual(browser.poster_choice(browser="firefox", say=quiet), "firefox")  # --browser decides everything
        answers = iter(["x", "3", "edge"])
        self.assertEqual(browser.poster_choice(ask=lambda q: next(answers), say=quiet), "edge")
        self.assertEqual(browser.poster_choice(say=quiet), "edge")                       # remembered, not asked again
        self.assertEqual(browser.poster_choice(post_with="safari", say=quiet), "safari")
        self.assertEqual(browser.poster_choice(say=quiet), "safari")                     # --post-with is remembered too
        browser.CHOICE.unlink()
        self.assertEqual(browser.poster_choice(ask=lambda q: "1", say=quiet), "chrome")

    def test_an_explicit_choice_wins_and_the_default_browser_comes_first(self):
        self.assertEqual(browser.order("edge"), ["edge"])
        real = browser.default_browser
        self.addCleanup(lambda: setattr(browser, "default_browser", real))
        browser.default_browser = lambda: "firefox"
        self.assertEqual(browser.order()[0], "firefox")
        self.assertEqual(len(browser.order()), len(set(browser.order())))
        browser.default_browser = lambda: None
        self.assertIn("chrome", browser.order())


if __name__ == "__main__":
    unittest.main()
