// Deterministic timeline: window.seek(t) renders the frame at t seconds. window.TL comes from <vid>_timeline.js.
(function () {
  const TL = window.TL, D = TL.duration;
  const clamp = (x) => Math.max(0, Math.min(1, x));
  const ease = (x) => 1 - Math.pow(1 - clamp(x), 3);
  const back = (x) => { x = clamp(x); const c = 1.9; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
  const scenes = TL.scenes.map((s, i) => ({ ...s, el: document.getElementById("s-" + s.id), first: i === 0, last: i === TL.scenes.length - 1 }));
  // "p2+0.3" -> absolute time of phrase 2 plus 0.3 s; "1.5" -> scene start + 1.5 s
  const when = (sc, spec) => {
    const m = /^p(\d+)([+-][\d.]+)?$/.exec(spec);
    if (m) return sc.phrases[+m[1]].t0 + (m[2] ? parseFloat(m[2]) : 0);
    return sc.t0 + parseFloat(spec);
  };
  const items = [];
  scenes.forEach((sc) => {
    if (!sc.el) throw new Error("missing scene " + sc.id);
    sc.el.querySelectorAll("[data-at]").forEach((el) => {
      const d = el.dataset;
      items.push({ el, sc, at: when(sc, d.at), out: d.out ? when(sc, d.out) : null, fx: d.fx || "up", dur: parseFloat(d.dur || "0.55"),
        count: d.count ? d.count.split(",") : null, type: d.type != null ? el.textContent : null, bar: d.bar ? parseFloat(d.bar) : null });
    });
    sc.kb = [...sc.el.querySelectorAll("[data-kb]")];
    sc.hot = [...sc.el.querySelectorAll("[data-on]")].map((el) => ({ el, on: when(sc, el.dataset.on), off: el.dataset.off ? when(sc, el.dataset.off) : sc.t1 + 1 }));
    if (window.SHORTCAPS) sc.phrases.forEach((p) => {   // short caption chunks, timed by character share
      const words = p.cap.split(" "), groups = []; let g = [];
      words.forEach((w) => { if (g.length && (g.length >= 4 || (g.join(" ") + " " + w).length > 24)) { groups.push(g.join(" ")); g = []; } g.push(w); });
      if (g.length) groups.push(g.join(" "));
      const n = groups.length;  // do not leave a single short word alone on screen
      if (n > 1 && !groups[n - 1].includes(" ") && (groups[n - 2] + " " + groups[n - 1]).length <= 30) groups.splice(n - 2, 2, groups[n - 2] + " " + groups[n - 1]);
      const total = groups.reduce((a, x) => a + x.length + 1, 0); let t = p.t0;
      p.chunks = groups.map((x) => { const d = (p.t1 - p.t0) * (x.length + 1) / total, c = { t0: t, t1: t + d, cap: x }; t += d; return c; });
    });
  });
  const cap = document.querySelector("#cap span"), prog = document.getElementById("prog"), fade = document.getElementById("fade");
  const blobs = ["b1", "b2", "b3"].map((id) => document.getElementById(id)), grid = document.getElementById("grid");

  window.seek = function (t) {
    scenes.forEach((sc) => {
      const a = sc.first ? 1 : clamp((t - (sc.t0 - 0.22)) / 0.4), b = sc.last ? 1 : 1 - clamp((t - (sc.t1 - 0.22)) / 0.4);
      const o = Math.min(a, b);
      sc.el.style.opacity = o; sc.el.style.visibility = o > 0 ? "visible" : "hidden";
      sc.el.style.transform = `scale(${1 + 0.025 * (1 - ease(a))})`;
      const k = clamp((t - sc.t0) / (sc.t1 - sc.t0));
      sc.kb.forEach((el) => { el.style.transform = `scale(${1.02 + 0.07 * k})`; });
      sc.hot.forEach((h) => h.el.classList.toggle("hot", t >= h.on && t < h.off));
    });
    items.forEach((it) => {
      const raw = (t - it.at) / it.dur, p = ease(raw);
      let o = p, tr = "";
      if (it.fx === "up") tr = `translateY(${40 * (1 - p)}px)`;
      else if (it.fx === "left") tr = `translateX(${-90 * (1 - p)}px)`;
      else if (it.fx === "right") tr = `translateX(${90 * (1 - p)}px)`;
      else if (it.fx === "pop") { tr = `scale(${0.6 + 0.4 * back(raw)})`; o = clamp(raw * 3); }
      else if (it.fx === "stamp") { tr = `scale(${1 + 1.6 * (1 - ease(raw * 1.6))})`; o = clamp(raw * 4); }
      if (it.out != null) o *= 1 - clamp((t - it.out) / 0.35);
      it.el.style.opacity = o; it.el.style.transform = tr;
      if (it.count) {
        const [from, to, pre = "", suf = ""] = it.count, v = +from + (+to - +from) * ease((t - it.at) / parseFloat(it.el.dataset.cdur || "1.2"));
        it.el.textContent = pre + Math.round(v) + suf;
      }
      if (it.type != null) {
        const n = Math.floor(clamp((t - it.at) / parseFloat(it.el.dataset.tdur || "2")) * it.type.length);
        it.el.textContent = it.type.slice(0, n) + (n < it.type.length && Math.floor(t * 4) % 2 ? "▍" : "");
        it.el.style.opacity = t >= it.at ? 1 : 0; it.el.style.transform = "";
      }
      if (it.bar != null) { it.el.style.width = it.bar * ease((t - it.at) / 1.1) + "%"; it.el.style.opacity = 1; it.el.style.transform = ""; }
    });
    // captions
    let cur = null;
    scenes.forEach((sc) => sc.phrases.forEach((p, i) => {
      const next = sc.phrases[i + 1];
      if (t >= p.t0 - 0.05 && t < (next ? next.t0 - 0.05 : p.t1 + 0.35)) cur = p;
    }));
    if (cur && cur.chunks) cur = cur.chunks.find((c, i) => t < c.t1 || i === cur.chunks.length - 1);
    if (cur) { cap.textContent = cur.cap; cap.style.opacity = Math.min(clamp((t - cur.t0 + 0.05) / 0.15), 1); cap.style.visibility = "visible"; }
    else cap.style.visibility = "hidden";
    prog.style.width = (100 * t / D) + "%";
    fade.style.opacity = Math.max(1 - clamp(t / 0.5), clamp((t - (D - 0.7)) / 0.6));
    // slow drifting background
    blobs[0].style.transform = `translate(${-250 + 160 * Math.sin(t * 0.11)}px, ${-350 + 120 * Math.cos(t * 0.09)}px)`;
    blobs[1].style.transform = `translate(${1150 + 180 * Math.cos(t * 0.08)}px, ${-420 + 140 * Math.sin(t * 0.12)}px)`;
    blobs[2].style.transform = `translate(${520 + 220 * Math.sin(t * 0.07 + 2)}px, ${520 + 100 * Math.cos(t * 0.1)}px)`;
    grid.style.transform = `translate(${(t * 6) % 80}px, ${(t * 4) % 80}px)`;
  };
  window.DURATION = D;
  const q = new URLSearchParams(location.search);
  if (q.has("t")) window.seek(parseFloat(q.get("t")));
  else if (q.has("play")) { const t0 = performance.now(); (function f() { window.seek(((performance.now() - t0) / 1000) % D); requestAnimationFrame(f); })(); }
  else window.seek(0);
  window.READY = Promise.all([...document.images].map((im) => im.decode().catch(() => 0)));
})();
