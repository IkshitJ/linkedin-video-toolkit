"""Helpers shared by the walkthrough scripts (see demo_example.py)."""
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "out"

# Eased scroll of the window (selector None) or of a scrollable element, over `ms` milliseconds.
SMOOTH_SCROLL = """([sel, to, ms]) => new Promise((done) => {
  const el = sel ? document.querySelector(sel) : document.scrollingElement;
  el.style.scrollBehavior = 'auto';
  const from = el.scrollTop, t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - t0) / ms), e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
    el.scrollTop = from + (to - from) * e;
    k < 1 ? requestAnimationFrame(step) : done();
  };
  requestAnimationFrame(step);
})"""


async def scroll(page, to, ms, sel=None):
    await page.evaluate(SMOOTH_SCROLL, [sel, to, ms])
