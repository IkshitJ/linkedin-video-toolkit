#!/usr/bin/env python3
"""Record a web page (http://, https:// or file://) to an H.264 MP4.

    .venv/bin/python tools/record.py <url> <out.mp4> <seconds> [--settle S] [--fps N]
                                     [--width W] [--height H] [--headed]

How it works: drives the installed Google Chrome through Playwright, takes the
page's frames from a Chrome DevTools "screencast" (JPEG frames pushed whenever
the page repaints) and feeds them at a constant frame rate into the ffmpeg
binary bundled with imageio-ffmpeg (libx264, yuv420p, +faststart). No system
ffmpeg and no Playwright-downloaded Chromium are needed.

Also importable: `Recorder` records any Playwright (async) page and can be
paused/resumed, so a script can click around and only keep the parts it wants.
"""
import argparse
import asyncio
import base64
import pathlib
import subprocess
import sys
import time

import imageio_ffmpeg
from playwright.async_api import async_playwright

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# GPU-backed WebGL in headless Chrome on macOS (maps etc.), and no throttling of
# timers/painting just because the window is not visible.
CHROME_ARGS = [
    "--use-angle=metal",
    "--enable-gpu",
    "--ignore-gpu-blocklist",
    "--enable-unsafe-swiftshader",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--autoplay-policy=no-user-gesture-required",
    "--hide-scrollbars",
]


class Recorder:
    """Screencast of one page, encoded to MP4 at a constant frame rate."""

    def __init__(self, page, out_path, fps=30, width=1280, height=720, crf=18, jpeg_quality=92):
        self.page, self.out_path, self.fps = page, str(out_path), fps
        self.width, self.height, self.crf, self.jpeg_quality = width, height, crf, jpeg_quality
        self.latest = None        # newest JPEG frame from Chrome
        self.source_frames = 0    # distinct frames Chrome delivered while recording
        self.written = 0          # frames written to the video
        self.recording = False
        self._clock = 0.0         # seconds of video recorded before the current resume()
        self._resumed_at = None
        self._task = None

    async def start(self, paused=False):
        pathlib.Path(self.out_path).parent.mkdir(parents=True, exist_ok=True)
        self.ffmpeg = subprocess.Popen(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(self.fps), "-i", "-",
             # JPEG is full-range; convert to the limited-range BT.709 yuv420p players expect.
             "-vf", f"scale={self.width}:{self.height}:flags=lanczos:in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", str(self.crf),
             "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709",
             "-color_primaries", "bt709", "-color_trc", "bt709", "-r", str(self.fps), "-movflags", "+faststart", "-an", self.out_path],
            stdin=subprocess.PIPE)
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        await self.cdp.send("Page.startScreencast", {
            "format": "jpeg", "quality": self.jpeg_quality,
            "maxWidth": self.width, "maxHeight": self.height, "everyNthFrame": 1})
        for _ in range(100):  # wait for the first frame
            if self.latest:
                break
            await asyncio.sleep(0.05)
        if not self.latest:  # a static page may not repaint: fall back to a screenshot
            self.latest = await self.page.screenshot(type="jpeg", quality=self.jpeg_quality)
        self._task = asyncio.create_task(self._pump())
        if not paused:
            self.resume()

    def _on_frame(self, params):
        self.latest = base64.b64decode(params["data"])
        if self.recording:
            self.source_frames += 1
        asyncio.ensure_future(self._ack(params["sessionId"]))

    async def _ack(self, session_id):
        try:
            await self.cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
        except Exception:
            pass  # page navigated or closed

    def resume(self):
        if not self.recording:
            self._resumed_at = time.monotonic()
            self.recording = True

    def pause(self):
        if self.recording:
            self._write_due()
            self._clock += time.monotonic() - self._resumed_at
            self.recording = False

    def _write_due(self):
        """Write as many copies of the newest frame as wall-clock time calls for."""
        due = int((self._clock + time.monotonic() - self._resumed_at) * self.fps) - self.written
        for _ in range(max(0, due)):
            self.ffmpeg.stdin.write(self.latest)
            self.written += 1

    async def _pump(self):
        while True:
            if self.recording:
                self._write_due()
            await asyncio.sleep(1 / (self.fps * 2))

    async def stop(self):
        self.pause()
        self._task.cancel()
        try:
            await self.cdp.send("Page.stopScreencast")
        except Exception:
            pass
        self.ffmpeg.stdin.close()
        if self.ffmpeg.wait() != 0:
            raise RuntimeError("ffmpeg failed")
        seconds = self.written / self.fps
        return {"seconds": seconds, "frames": self.written, "source_frames": self.source_frames,
                "source_fps": self.source_frames / seconds if seconds else 0}


async def launch(playwright, width=1280, height=720, headed=False):
    """The installed Google Chrome with one page of the given viewport size."""
    browser = await playwright.chromium.launch(channel="chrome", headless=not headed, args=CHROME_ARGS)
    context = await browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
    return browser, await context.new_page()


async def record(url, out_path, seconds, settle=1.0, fps=30, width=1280, height=720, headed=False):
    async with async_playwright() as playwright:
        browser, page = await launch(playwright, width, height, headed)
        await page.goto(url, wait_until="load")
        await page.wait_for_timeout(settle * 1000)
        recorder = Recorder(page, out_path, fps=fps, width=width, height=height)
        await recorder.start()
        await page.wait_for_timeout(seconds * 1000)
        stats = await recorder.stop()
        await browser.close()
        return stats


def main():
    parser = argparse.ArgumentParser(description="Record a URL to an H.264 MP4 (1280x720 by default).")
    parser.add_argument("url", help="http(s):// or file:// URL, or a path to a local HTML file")
    parser.add_argument("out", help="output .mp4")
    parser.add_argument("seconds", type=float, help="how long to record")
    parser.add_argument("--settle", type=float, default=1.0, help="seconds to wait after load before recording (default 1)")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--headed", action="store_true", help="show the Chrome window (default: headless)")
    args = parser.parse_args()

    url = args.url
    if "://" not in url:
        url = pathlib.Path(url).resolve().as_uri()
    stats = asyncio.run(record(url, args.out, args.seconds, args.settle, args.fps, args.width, args.height, args.headed))
    print(f"{args.out}: {stats['seconds']:.1f} s, {stats['frames']} frames at {args.fps} fps "
          f"({stats['source_fps']:.1f} distinct page frames per second)")


if __name__ == "__main__":
    sys.exit(main())
