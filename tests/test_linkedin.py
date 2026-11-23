"""The posting steps, against a local stand-in page (tests/fake_linkedin.html). This checks that the
driver presses the right things in the right order and refuses to post changed text. It cannot check
that linkedin.com still has those buttons: only a real dry run can (python run.py --dry-run)."""
import functools
import http.server
import pathlib
import sys
import tempfile
import threading
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from playwright.sync_api import sync_playwright
from toolkit import linkedin

TEXT = "kokoro-onnx: TTS with kokoro.\n\nWhat it does:\n• Supports multiple languages\n• Offer multiple voices\n\nBuilt with Python.\n\nhttps://github.com/ada/kokoro-onnx\n\n#OpenSource #Python\n"


class Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = (HERE / "fake_linkedin.html").read_bytes()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


class Posting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.site = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(channel="chrome", headless=True)
        cls.video = pathlib.Path(tempfile.mkdtemp()) / "clip.mp4"
        cls.video.write_bytes(b"not really a video")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close(); cls.pw.stop(); cls.server.shutdown(); cls.server.server_close()

    def run_post(self, mode="", **kw):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        quiet = lambda *a: None
        try:
            return linkedin.post(page, self.video, TEXT, say=quiet, site=self.site + mode, **kw), page
        except linkedin.PostError as err:
            return err, page

    def test_posts_the_video_with_exactly_the_text(self):
        result, page = self.run_post()
        self.assertEqual(result, "POSTED")
        fake = page.evaluate("fake")
        self.assertEqual(fake["file"], "clip.mp4")
        self.assertEqual(linkedin._lines(fake["posted"]), linkedin._lines(TEXT))
        self.assertNotIn("old draft", fake["posted"])

    def test_dry_run_fills_everything_in_and_does_not_post(self):
        result, page = self.run_post(publish=False)
        self.assertEqual(result, "DRY RUN")
        self.assertIsNone(page.evaluate("fake.posted"))
        self.assertEqual(linkedin._lines(page.inner_text("#editor")), linkedin._lines(TEXT))

    def test_changed_text_is_not_posted(self):
        result, page = self.run_post("/mangle")
        self.assertIsInstance(result, linkedin.PostError)
        self.assertEqual(result.code, "TEXT MISMATCH")
        self.assertFalse(result.posted)
        self.assertIsNone(page.evaluate("fake.posted"))

    def test_posting_limit_is_reported(self):
        result, page = self.run_post("/limit")
        self.assertEqual(getattr(result, "code", result), "LIMIT REACHED")

    def test_signed_out_urls_are_not_the_feed(self):
        self.assertTrue(linkedin._on_feed("https://www.linkedin.com/feed/"))
        self.assertFalse(linkedin._on_feed("https://www.linkedin.com/uas/login?session_redirect=https%3A%2F%2Fwww.linkedin.com%2Ffeed%2F"))
        self.assertFalse(linkedin._on_feed("https://example.com/feed/"))


if __name__ == "__main__":
    unittest.main()
