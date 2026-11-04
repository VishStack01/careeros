/* CareerOS website behaviour.
   Motion follows one rule set: an element enters once, the first time it scrolls into view,
   in 280 ms with a strong ease-out (opacity + a short rise; never from scale 0, never blurred).
   Nothing loops, nothing moves while you read it, and Reduce Motion turns entrances into fades. */
(function () {
  "use strict";
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // Old job-board links (?q=... or #/job/...) moved to jobs.html.
  if (document.body.dataset.page === "home" && (location.search || /^#\//.test(location.hash))) {
    location.replace("jobs.html" + location.search + location.hash);
    return;
  }

  // Links into the hosted app follow <meta name="careeros-app">, so the address lives in one place.
  var appMeta = document.querySelector('meta[name="careeros-app"]');
  var appUrl = appMeta && /^https:\/\//.test(appMeta.content) ? appMeta.content.replace(/\/+$/, "") : "";
  if (appUrl) $$("[data-app]").forEach(function (a) { a.href = appUrl + a.getAttribute("data-app"); });

  // Siblings in a group enter 40 ms apart, capped at eight steps; beyond that they enter as a block.
  $$("[data-stagger]").forEach(function (g) {
    $$(":scope > .reveal", g).forEach(function (el, i) { el.style.setProperty("--d", (Math.min(i, 8) * 0.04).toFixed(2) + "s"); });
  });
  $$(".principles .pr").forEach(function (p, i) {
    var d = Math.min(i, 8) * 40;
    var bg = p.querySelector(".bg"), tx = p.querySelector(".tx");
    if (bg) bg.style.transitionDelay = d + "ms";
    if (tx) tx.style.transitionDelay = (d + 60) + "ms";
  });

  // Enter once, on first view.
  var targets = $$(".reveal, .split-words, .pr, .tick, .phone");
  if (!("IntersectionObserver" in window)) {
    targets.forEach(function (t) { t.classList.add("in"); });
  } else {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
    targets.forEach(function (t) { io.observe(t); });
  }

  // The nav gets its hairline once the page has scrolled.
  var nav = document.querySelector("nav.top");
  var ticking = false;
  function onScroll() { if (nav) nav.classList.toggle("scrolled", window.scrollY > 8); ticking = false; }
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });
  onScroll();

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
