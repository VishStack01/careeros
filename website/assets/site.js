/* Propelo website behaviour.
   Motion: things enter once, the first time they scroll into view, with one easing curve.
   The intro plays once per visit. Headlines arrive letter by letter, cards open from the bottom
   with a curved edge, bars fill and the step line follows the scroll. Nothing loops, and
   Reduce Motion shows every page at rest. */
(function () {
  "use strict";
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var root = document.documentElement;
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Old job-board links (?q=... or #/job/...) moved to jobs.html.
  if (document.body.dataset.page === "home" && (location.search || /^#\//.test(location.hash))) {
    location.replace("jobs.html" + location.search + location.hash);
    return;
  }

  // Links into the hosted app follow <meta name="careeros-app">, so the address lives in one place.
  var appMeta = document.querySelector('meta[name="careeros-app"]');
  var appUrl = appMeta && /^https:\/\//.test(appMeta.content) ? appMeta.content.replace(/\/+$/, "") : "";
  if (appUrl) $$("[data-app]").forEach(function (a) { a.href = appUrl + a.getAttribute("data-app"); });

  // Small screens: the links fold into one menu button.
  var menu = document.querySelector(".menu"), links = document.getElementById("links");
  if (menu && links) {
    menu.addEventListener("click", function () {
      var open = links.classList.toggle("open");
      menu.setAttribute("aria-expanded", open ? "true" : "false");
    });
    $$("a", links).forEach(function (a) { a.addEventListener("click", function () { links.classList.remove("open"); menu.setAttribute("aria-expanded", "false"); }); });
  }

  // Live numbers from the latest scan (data/stats.json, written by `careeros site`).
  var fmt = function (n) { return Number(n).toLocaleString("en-IN"); };
  fetch("data/stats.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (s) {
    if (!s || !s.openings) return;
    var date = s.feedAt ? new Date(s.feedAt).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" }) : "";
    var vals = { openings: fmt(s.openings), companies: fmt(s.companies), boards: fmt(s.boards), relisted: fmt(s.relisted), date: date };
    $$("[data-stat]").forEach(function (el) { var v = vals[el.getAttribute("data-stat")]; if (v) el.textContent = v; });
    (s.byAts || []).slice(0, 5).forEach(function (a, i) {
      var p = document.querySelector('[data-ats="' + i + '"]'), b = document.querySelector('[data-pct="' + i + '"]');
      var fl = document.querySelectorAll("#bars .fl")[i];
      if (p) p.textContent = a.label; if (b) b.textContent = Math.round(a.share * 100) + "%";
      if (fl) fl.style.setProperty("--v", a.share.toFixed(3));
    });
  }).catch(function () {});

  // Headlines: split into words and letters (screen readers get the plain sentence).
  $$(".split").forEach(function (el) {
    var k = 0, wave = el.hasAttribute("data-wave");
    el.setAttribute("aria-label", el.textContent.replace(/\s+/g, " ").trim());
    // Keep punctuation that follows a highlighted phrase on the same line as it.
    $$("mark", el).forEach(function (m) {
      var nx = m.nextSibling, lead = nx && nx.nodeType === 3 && nx.textContent.match(/^[^\s]+/);
      if (!lead) return;
      var nb = document.createElement("span"); nb.className = "nb";
      m.parentNode.insertBefore(nb, m); nb.appendChild(m); nb.appendChild(document.createTextNode(lead[0]));
      nx.textContent = nx.textContent.slice(lead[0].length);
    });
    (function walk(node) {
      Array.prototype.slice.call(node.childNodes).forEach(function (n) {
        if (n.nodeType === 3) {
          var frag = document.createDocumentFragment();
          n.textContent.split(/(\s+)/).forEach(function (part) {
            if (!part) return;
            if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(" ")); return; }
            var w = document.createElement("span"); w.className = "w"; w.setAttribute("aria-hidden", "true");
            part.split("").forEach(function (ch) {
              var c = document.createElement("span"); c.className = "c"; c.textContent = ch; c.style.setProperty("--k", k++);
              if (wave) c.style.setProperty("--r", (Math.random() * 10 - 5).toFixed(1) + "deg");
              w.appendChild(c);
            });
            frag.appendChild(w);
          });
          n.parentNode.replaceChild(frag, n);
        } else if (n.nodeType === 1) walk(n);
      });
    })(el);
    el.style.setProperty("--ks", Math.max(4, Math.min(12, Math.round(900 / Math.max(k, 1)))) + "ms");
  });

  // Siblings enter 70 ms apart, capped at six steps.
  var groups = new Map();
  $$(".reveal, .curv").forEach(function (el) {
    var p = el.parentElement, n = groups.get(p) || 0;
    if (!el.style.getPropertyValue("--d")) el.style.setProperty("--d", (Math.min(n, 6) * 0.07).toFixed(2) + "s");
    groups.set(p, n + 1);
  });
  $$(".principles .pr").forEach(function (p, i) { p.style.setProperty("--n", i); });

  // Enter once, on first view. Clipped cards are watched through their parent (a fully clipped
  // element has no visible area to intersect).
  var hero = document.querySelector(".hero h1.split");
  var watched = $$(".reveal, .split, .bars, .principles").filter(function (el) { return el !== hero; });
  var curvs = $$(".curv");
  function show(el) { el.classList.add("in"); }
  if (!("IntersectionObserver" in window)) {
    watched.concat(curvs).forEach(show);
  } else {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        if (e.target.__curv) e.target.__curv.forEach(show); else show(e.target);
      });
    }, { threshold: 0.1, rootMargin: "0px 0px -8% 0px" });
    watched.forEach(function (el) { io.observe(el); });
    curvs.forEach(function (el) {
      var p = el.parentElement; (p.__curv = p.__curv || []).push(el);
      if (p.__curv.length === 1) io.observe(p);
    });
  }

  // Intro: once per visit; the hero headline starts as the panel lifts.
  var intro = document.getElementById("intro"), seen = false;
  try { seen = sessionStorage.getItem("propelo-intro") === "1"; sessionStorage.setItem("propelo-intro", "1"); } catch (e) {}
  function startHero() { if (hero) show(hero); }
  if (!intro || reduce || seen) { root.classList.add("no-intro"); startHero(); }
  else {
    var b = intro.querySelector("b");
    b.innerHTML = b.textContent.split("").map(function (c, i) { return '<span style="transition-delay:' + (i * 45) + 'ms">' + c + "</span>"; }).join("");
    requestAnimationFrame(function () { requestAnimationFrame(function () { intro.classList.add("show"); }); });
    var finished = false;
    var done = function () {
      if (finished) return; finished = true;
      intro.classList.add("leave");
      setTimeout(startHero, 300);
      setTimeout(function () { root.classList.add("no-intro"); }, 950);
    };
    var t = setTimeout(done, 1000);
    intro.addEventListener("click", function () { clearTimeout(t); done(); });
  }

  // The nav gets its hairline once the page has scrolled; the step line follows the scroll.
  var nav = document.querySelector("nav.top"), steps = document.getElementById("steps"), ticking = false;
  if (steps) { var pr = document.createElement("span"); pr.className = "prog"; pr.setAttribute("aria-hidden", "true"); steps.appendChild(pr); }
  function clamp(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }
  function onScroll() {
    ticking = false;
    if (nav) nav.classList.toggle("scrolled", window.scrollY > 8);
    if (steps) {
      var vh = window.innerHeight, r = steps.getBoundingClientRect();
      steps.style.setProperty("--s", reduce ? 1 : clamp((vh * 0.8 - r.top) / (r.height + vh * 0.2)).toFixed(3));
    }
  }
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });
  onScroll();

  // Hero panel: a quiet dot grid that swells and takes colour near the cursor. It only draws
  // while the cursor moves over it, so nothing runs while you read.
  var cv = document.getElementById("dots");
  if (cv && cv.getContext && !reduce) {
    var ctx = cv.getContext("2d"), W = 0, H = 0, pts = [], mx = -999, my = -999, sx = -999, sy = -999, raf = 0;
    var cols = ["#FF85BA", "#FF7034", "#FCC63E"];
    var size = function () {
      var r = cv.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2); W = r.width; H = r.height;
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      pts = []; for (var y = 12; y < H; y += 24) for (var x = 12; x < W; x += 24) pts.push([x, y, (x * 7 + y * 3) % 3]);
    };
    var draw = function () {
      ctx.clearRect(0, 0, W, H);
      sx += (mx - sx) * 0.18; sy += (my - sy) * 0.18;
      var moving = Math.abs(mx - sx) + Math.abs(my - sy) > 0.5;
      for (var i = 0; i < pts.length; i++) {
        var p = pts[i], dx = p[0] - sx, dy = p[1] - sy, d = Math.sqrt(dx * dx + dy * dy), near = d < 140 ? Math.pow(1 - d / 140, 2) : 0;
        ctx.globalAlpha = 0.32 + near * 0.68;
        ctx.fillStyle = near > 0.05 ? cols[p[2]] : "#8E85E8";
        ctx.beginPath(); ctx.arc(p[0], p[1], 1.4 + near * 3.6, 0, 6.2832); ctx.fill();
      }
      ctx.globalAlpha = 1;
      raf = moving ? requestAnimationFrame(draw) : 0;
    };
    size(); draw();
    window.addEventListener("resize", function () { size(); draw(); });
    cv.parentElement.addEventListener("pointermove", function (e) {
      var r = cv.getBoundingClientRect(); mx = e.clientX - r.left; my = e.clientY - r.top;
      if (sx < -900) { sx = mx; sy = my; }
      if (!raf) raf = requestAnimationFrame(draw);
    });
    cv.parentElement.addEventListener("pointerleave", function () { mx = -999; my = -999; if (!raf) raf = requestAnimationFrame(draw); });
  }

  // Docs: copy buttons and the active section in the table of contents.
  $$(".code").forEach(function (block) {
    var b = document.createElement("button");
    b.className = "copy"; b.type = "button"; b.textContent = "Copy";
    b.addEventListener("click", function () {
      var text = block.innerText.replace(/Copy$/, "").split("\n").filter(function (l) { return !/^\s*#/.test(l); }).join("\n").trim();
      (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () {
        b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1500);
      }, function () { b.textContent = "Select and copy"; });
    });
    block.appendChild(b);
  });
  var toc = $$(".toc a");
  if (toc.length && "IntersectionObserver" in window) {
    var map = {};
    toc.forEach(function (a) { map[a.getAttribute("href").slice(1)] = a; });
    var tio = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting && map[e.target.id]) { toc.forEach(function (a) { a.classList.remove("on"); }); map[e.target.id].classList.add("on"); }
      });
    }, { rootMargin: "-20% 0px -70% 0px" });
    $$(".doc h2[id]").forEach(function (h) { tio.observe(h); });
  }
})();
