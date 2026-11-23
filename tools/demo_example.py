#!/usr/bin/env python3
"""Template for a scripted walkthrough of a web app, recorded to an MP4.

    .venv/bin/python tools/demo_example.py <url> [out.mp4]

As it stands it scrolls slowly from the top of the page to the bottom. Copy this file and
replace the part between the two marker comments with the clicks and typing that show your
own app. Everything on screen is the real page: the script only drives it.
"""
import asyncio
import pathlib
import sys

from playwright.async_api import async_playwright

from demo_common import OUT, scroll
from record import Recorder, launch


async def main():
    url = sys.argv[1]
    if "://" not in url:
        url = pathlib.Path(url).resolve().as_uri()
    out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else OUT / "demo.mp4"
    async with async_playwright() as pw:
        browser, page = await launch(pw)                    # 1280x720, headless Chrome
        wait = page.wait_for_timeout
        await page.goto(url, wait_until="load")
        await wait(2000)                                    # let the page settle, off camera
        rec = Recorder(page, out)
        await rec.start()

        # ---- your walkthrough starts here ------------------------------------------------
        await wait(2000)                                    # hold on the first screen
        await page.mouse.move(640, 360, steps=30)           # a visible, human-speed pointer move
        bottom = await page.evaluate("document.documentElement.scrollHeight - innerHeight")
        y = 0
        while y < bottom:                                   # one screen at a time, with a pause to read
            y = min(bottom, y + 560)
            await scroll(page, y, 1500)
            await wait(1800)
        # Other things a walkthrough usually needs:
        #   await page.click("text=Get started")              click by visible text or CSS selector
        #   await page.type("input[name=q]", "hello", delay=40)   type at a readable speed
        #   rec.pause(); await page.wait_for_selector(".result"); rec.resume()   cut a long wait
        #   await page.route("**/api/send-email/**", lambda r: r.abort())        block a side effect
        # ---- your walkthrough ends here --------------------------------------------------

        print(out, await rec.stop())
        await browser.close()


if len(sys.argv) < 2:
    sys.exit(__doc__)
asyncio.run(main())
