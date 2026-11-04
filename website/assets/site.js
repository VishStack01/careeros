/* CareerOS website motion: reveals, word-by-word headlines, counters, parallax, terminal typing, tilt, docs helpers.
   Everything is decoration: the page reads fully without it, and it all switches off with prefers-reduced-motion. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // Old job-board links (?q=... or #/job/...) moved to jobs.html.
  if (document.body.dataset.page === "home" && (location.search || /^#\//.test(location.hash))) {
    location.replace("jobs.html" + location.search + location.hash);
    return;
  }

  // Stagger: children of [data-stagger] get increasing delays.
  $$("[data-stagger]").forEach(function (g) {
    var step = parseFloat(g.dataset.stagger) || 0.08;
    $$(":scope > .reveal", g).forEach(function (el, i) { el.style.setProperty("--d", (i * step).toFixed(2) + "s"); });
  });

  // Headline words.
  $$(".split-words").forEach(function (el) {
    var i = 0;
    var walk = function (node) {
      Array.prototype.slice.call(node.childNodes).forEach(function (n) {
        if (n.nodeType === 3) {
          var frag = document.createDocumentFragment();
          n.textContent.split(/(\s+)/).forEach(function (part) {
            if (!part) return;
            if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(part)); return; }
            var s = document.createElement("span");
            s.className = "w"; s.textContent = part;
            s.style.transitionDelay = (0.15 + i++ * 0.035).toFixed(3) + "s";
            frag.appendChild(s);
          });
          n.parentNode.replaceChild(frag, n);
        } else if (n.nodeType === 1) { walk(n); }
      });
    };
    walk(el);
  });

  function countUp(el) {
    var end = parseFloat(el.dataset.count), dur = 1400, t0 = null;
    var fmt = function (v) { return Math.round(v).toLocaleString("en-US"); };
    if (reduce) { el.textContent = fmt(end); return; }
    var tick = function (t) {
      if (!t0) t0 = t;
      var p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 4);
      el.textContent = fmt(end * e);
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  function typeTerm(term) {
    var lines = $$(".ln", term), i = 0;
    var caret = term.querySelector(".caret");
    var next = function () {
      if (i >= lines.length) { if (caret) lines[lines.length - 1].appendChild(caret); return; }
      lines[i].classList.add("on");
      if (caret) lines[i].appendChild(caret);
      i++;
      setTimeout(next, reduce ? 0 : 260);
    };
    next();
  }

  function show(el) {
    el.classList.add("in");
    if (el.classList.contains("split-words")) el.classList.add("words-in");
    $$("[data-count]", el).concat(el.dataset.count ? [el] : []).forEach(function (c) { if (!c._done) { c._done = 1; countUp(c); } });
    if (el.classList.contains("term")) typeTerm(el);
  }

  var targets = $$(".reveal, .split-words, .pr, .term, .tick, [data-count]");
  if (reduce || !("IntersectionObserver" in window)) {
    targets.forEach(show);
  } else {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { show(e.target); io.unobserve(e.target); } });
    }, { threshold: 0.15, rootMargin: "0px 0px -6% 0px" });
    targets.forEach(function (t) { io.observe(t); });
  }

  // Principles pop in one after another.
  $$(".pr").forEach(function (p, i) {
    var d = (i * 0.12).toFixed(2) + "s";
    var bg = p.querySelector(".bg"), tx = p.querySelector(".tx");
    if (bg) bg.style.transitionDelay = d;
    if (tx) tx.style.transitionDelay = (i * 0.12 + 0.35).toFixed(2) + "s";
  });

  // Nav shadow, parallax.
  var nav = document.querySelector("nav.top");
  var par = reduce ? [] : $$("[data-speed]");
  var ticking = false;
  function onScroll() {
    if (nav) nav.classList.toggle("scrolled", window.scrollY > 8);
    par.forEach(function (el) {
      var r = el.parentElement.getBoundingClientRect();
      var off = (r.top + r.height / 2 - innerHeight / 2) * parseFloat(el.dataset.speed);
      el.style.translate = "0 " + off.toFixed(1) + "px";
    });
    ticking = false;
  }
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });
  onScroll();

  // Tilt.
  if (!reduce) $$("[data-tilt]").forEach(function (box) {
    var card = box.querySelector(".mock") || box;
    box.addEventListener("pointermove", function (e) {
      var r = box.getBoundingClientRect();
      var x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      card.style.transform = "rotateY(" + (x * 10).toFixed(2) + "deg) rotateX(" + (-y * 10).toFixed(2) + "deg) translateZ(0)";
    });
    box.addEventListener("pointerleave", function () { card.style.transform = ""; });
  });

  // Docs: copy buttons and the active section in the table of contents.
  $$(".code").forEach(function (block) {
    var b = document.createElement("button");
    b.className = "copy"; b.type = "button"; b.textContent = "Copy";
    b.addEventListener("click", function () {
      var text = block.innerText.replace(/^Copy\n?/, "").split("\n").filter(function (l) { return !/^\s*#/.test(l); }).join("\n").trim();
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
