/* Propelo Autofill popup: connect once with your server address and a computer key, then
   "Fill this form" on any application page. Filling runs only when you press the button, only
   in the tab you're looking at, and never submits. The key stays in this browser's extension storage. */
(function () {
  "use strict";
  var BLOCKED = /(^|\.)(linkedin\.com|naukri\.com|indeed\.[a-z.]+|wellfound\.com|angel\.co)$/i;
  var app = document.getElementById("app");
  var S = { server: "", key: "", tab: null, page: null, report: null, busy: "", msg: "", err: false, tracked: null };

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function originOf(u) { try { var x = new URL(u); return x.protocol + "//" + x.host; } catch (e) { return ""; } }
  function okServer(u) { return /^https:\/\/[^/]+/i.test(u) || /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?/i.test(u); }
  function hostOf(u) { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (e) { return ""; } }

  function api(path, opts) {
    opts = opts || {};
    var h = { "Authorization": "Bearer " + S.key };
    if (opts.body) h["Content-Type"] = "application/json";
    return fetch(S.server + path, { method: opts.method || "GET", headers: h, body: opts.body ? JSON.stringify(opts.body) : undefined, credentials: "omit", cache: "no-store" })
      .then(function (r) {
        if (opts.raw && r.ok) return r;
        return r.json().catch(function () { return {}; }).then(function (d) {
          if (!r.ok) { var e = new Error(d.error || ("The server answered " + r.status + ".")); e.status = r.status; throw e; }
          return d;
        });
      }, function () { throw new Error("Couldn't reach " + hostOf(S.server) + ". Check the address and your connection."); });
  }
  function bufToB64(buf) {
    var bytes = new Uint8Array(buf), out = "", step = 0x8000;
    for (var i = 0; i < bytes.length; i += step) out += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
    return btoa(out);
  }

  function render() {
    if (!S.server || !S.key) return renderConnect();
    var t = S.tab, url = t && t.url || "", host = hostOf(url);
    var parts = [];
    if (!/^https?:/.test(url)) {
      parts.push('<h1>Open an application form</h1><p class="muted">Go to a job\'s application page, then click Propelo and press Fill this form.</p>');
    } else if (BLOCKED.test(host)) {
      parts.push('<h1>Apply here yourself</h1><div class="note">Propelo never fills forms on LinkedIn, Naukri, Indeed or Wellfound. Those sites don\'t allow it, and it can get your account restricted. Your answers are ready in Propelo to copy.</div>');
      parts.push(trackCard());
    } else {
      parts.push('<h1>' + esc(S.page && S.page.title || host) + '</h1><p class="muted">' + esc(S.page && S.page.company ? S.page.company + " · " + host : host) + '</p>');
      parts.push('<button class="btn solid block" data-act="fill"' + (S.busy ? " disabled" : "") + '>' + (S.busy === "fill" ? '<span class="spin" aria-hidden="true"></span>Filling…' : S.report ? "Fill again" : "Fill this form") + '</button>');
      if (S.report) parts.push(reportView(S.report));
      if (S.page && S.page.frames && S.page.frames.length && !S.framesOk) parts.push('<div class="note">This form sits inside a frame from <b>' + esc(S.page.frames.map(hostOf).join(", ")) + '</b>. <button class="btn ghost" data-act="frames">Allow Propelo there</button></div>');
      parts.push(trackCard());
    }
    if (S.msg) parts.push('<p class="' + (S.err ? "note" : "good") + '" role="status">' + esc(S.msg) + '</p>');
    parts.push('<div class="foot"><a href="' + esc(S.server) + '/app" target="_blank" rel="noopener">Open Propelo</a><button class="btn ghost" data-act="disconnect">Disconnect</button></div>');
    app.innerHTML = parts.join("");
  }
  function trackCard() {
    if (S.tracked) return '<div class="good">Tracked in Propelo as <b>' + esc(S.tracked.stage === "applied" ? "Applied" : "Saved") + '</b>.</div>';
    var p = S.page || {};
    return '<details class="card"' + (S.report ? " open" : "") + '><summary>Track this application</summary>' +
      '<label>Role<input type="text" id="tr-title" value="' + esc(p.title || "") + '" maxlength="160"></label>' +
      '<label>Company<input type="text" id="tr-company" value="' + esc(p.company || "") + '" maxlength="120"></label>' +
      '<div class="row"><button class="btn solid" data-act="track" data-applied="1"' + (S.busy ? " disabled" : "") + '>I submitted it</button><button class="btn" data-act="track" data-applied="0"' + (S.busy ? " disabled" : "") + '>Save for later</button></div></details>';
  }
  function reportView(r) {
    var out = [];
    out.push('<div class="good"><b>Filled ' + r.filled.length + (r.filled.length === 1 ? " field" : " fields") + '.</b> Check each answer on the page (outlined in pink), then press Submit yourself.</div>');
    if (r.fromAnswers) out.push('<div class="note"><b>' + r.fromAnswers + ' from your saved answers.</b> Read each one: it should still be true for this role.</div>');
    if (r.needs.length) out.push('<div class="card"><div class="row end"><b>Needs you</b><span class="count">' + r.needs.length + '</span></div><ul>' +
      r.needs.slice(0, 12).map(function (n) { return '<li><b>' + esc(n.label.slice(0, 120)) + '</b><span>' + esc(n.why) + '</span></li>'; }).join("") + '</ul>' +
      (r.needs.length > 12 ? '<p class="muted">And ' + (r.needs.length - 12) + ' more, outlined in orange on the page.</p>' : "") + '</div>');
    if (r.filled.length) out.push('<details class="card"><summary>What was filled</summary><ul>' + r.filled.slice(0, 30).map(function (f) { return '<li><b>' + esc(f.label.slice(0, 90)) + '</b><span>' + esc(String(f.value).slice(0, 90)) + '</span></li>'; }).join("") + '</ul></details>');
    if (r.skippedSensitive) out.push('<p class="muted">Left ' + r.skippedSensitive + ' private ' + (r.skippedSensitive === 1 ? "field" : "fields") + ' alone. Propelo never fills passwords, codes, ID numbers, bank details or dates of birth.</p>');
    return out.join("");
  }
  function renderConnect() {
    app.innerHTML = '<h1>Connect to Propelo</h1><p class="muted">Fills application forms from your Propelo profile. You review every answer and press Submit yourself.</p>' +
      '<form id="connect" class="card" novalidate><label>Your Propelo address<input type="url" id="server" placeholder="https://your-careeros-server" value="' + esc(S.server || "") + '" required></label>' +
      '<label>Computer key<input type="password" id="key" placeholder="cos_k_…" autocomplete="off" required></label>' +
      '<p class="muted">Make one in Propelo: Settings, Your computer, Create computer key. The key stays in this browser.</p>' +
      '<button class="btn solid block" type="submit"' + (S.busy ? " disabled" : "") + '>' + (S.busy === "connect" ? '<span class="spin" aria-hidden="true"></span>Checking…' : "Connect") + '</button></form>' +
      (S.msg ? '<p class="' + (S.err ? "note" : "good") + '" role="status">' + esc(S.msg) + '</p>' : "");
  }
  function say(m, err) { S.msg = m; S.err = !!err; render(); }

  function connect(e) {
    e.preventDefault();
    var server = document.getElementById("server").value.trim().replace(/\/+$/, "").replace(/\/app$/, "");
    var key = document.getElementById("key").value.trim();
    if (!okServer(server)) return say("Use your Propelo address starting with https://", true);
    if (!/^cos_k_[A-Za-z0-9_-]{10,}$/.test(key)) return say("That doesn't look like a computer key. It starts with cos_k_.", true);
    // Permission must be asked inside the click, before anything async.
    chrome.permissions.request({ origins: [originOf(server) + "/*"] }, function (granted) {
      if (!granted) return say("Propelo needs permission to talk to " + hostOf(server) + ".", true);
      S.server = server; S.key = key; S.busy = "connect"; S.msg = ""; renderConnect();
      api("/api/agent/applicant").then(function (d) {
        S.busy = "";
        chrome.storage.local.set({ server: server, key: key });
        say(d.applicant ? "Connected. Your application details are ready." : "Connected. Add your application details in Propelo (Profile) so there's something to fill.", !d.applicant);
        loadPage();
      }, function (err) {
        S.busy = ""; S.key = "";
        say(err.status === 401 || err.status === 403 ? "That key didn't work. Make a new one in Propelo and paste it here." : err.message, true);
      });
    });
  }

  function exec(tabId, allFrames, fn, args) {
    return chrome.scripting.executeScript({ target: { tabId: tabId, allFrames: allFrames }, files: ["fill.js"] })
      .then(function () { return chrome.scripting.executeScript({ target: { tabId: tabId, allFrames: allFrames }, func: fn, args: args || [] }); });
  }
  function loadPage() {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      S.tab = tabs && tabs[0]; S.page = null;
      if (!S.tab || !/^https?:/.test(S.tab.url || "")) return render();
      exec(S.tab.id, false, function () {
        var r = window.__careerosRead();
        r.frames = Array.prototype.slice.call(document.querySelectorAll("iframe[src]")).map(function (f) { return f.src; })
          .filter(function (s) { return /greenhouse\.io|lever\.co|ashbyhq\.com|myworkdayjobs\.com|smartrecruiters\.com|workable\.com|recruitee\.com|teamtailor\.com|icims\.com|jobvite\.com|breezy\.hr|zohorecruit/i.test(s); });
        return r;
      }).then(function (res) {
        S.page = res && res[0] && res[0].result;
        var origins = (S.page && S.page.frames || []).map(function (f) { return originOf(f) + "/*"; });
        if (!origins.length) { S.framesOk = true; return render(); }
        chrome.permissions.contains({ origins: origins }, function (ok) { S.framesOk = ok; render(); });
      }, function () { render(); });
    });
  }
  function fill() {
    if (!S.tab) return;
    S.busy = "fill"; S.msg = ""; render();
    api("/api/agent/applicant").then(function (d) {
      var a = d.applicant || {};
      if (!d.applicant) throw new Error("Add your application details in Propelo first (Profile, Application details).");
      var res = a.resume || {};
      var getResume = res.id ? api("/_blob/" + encodeURIComponent(res.id), { raw: true }).then(function (r) { return r.arrayBuffer(); })
        .then(function (b) { return b.byteLength > 8 * 1024 * 1024 ? null : { b64: bufToB64(b), name: res.name || "resume.pdf", type: "application/pdf" }; }, function () { return null; }) : Promise.resolve(null);
      return getResume.then(function (resume) {
        var applicant = {};
        ["fullName", "email", "phone", "city", "linkedin", "github", "portfolio", "currentTitle", "currentCompany", "experienceYears", "noticePeriod",
          "currentCtcLpa", "expectedCtcLpa", "degree", "college", "graduationYear", "cgpa", "branch", "backlogs", "state", "pinCode",
          "workAuthIndia", "sponsorshipAbroad", "relocate", "howHeard"].forEach(function (k) { if (a[k] !== undefined && a[k] !== null && a[k] !== "") applicant[k] = a[k]; });
        var answers = (a.answers || []).filter(function (x) { return x && x.q && x.a; }).map(function (x) { return { q: x.q, a: x.a, company: x.company || "" }; });
        return exec(S.tab.id, true, function (data) { return window.__careerosFill(data); }, [{ applicant: applicant, resume: resume, answers: answers, company: (S.page && S.page.company) || "" }]);
      });
    }).then(function (results) {
      var merged = { filled: [], needs: [], skippedSensitive: 0, resume: "", blocked: false };
      (results || []).forEach(function (r) {
        var x = r && r.result; if (!x) return;
        merged.filled = merged.filled.concat(x.filled); merged.needs = merged.needs.concat(x.needs);
        merged.skippedSensitive += x.skippedSensitive; merged.blocked = merged.blocked || x.blocked; if (x.resume) merged.resume = x.resume;
        merged.fromAnswers = (merged.fromAnswers || 0) + (x.fromAnswers || 0);
      });
      S.busy = ""; S.report = merged;
      if (merged.blocked) return say("Propelo doesn't fill forms on this site.", true);
      if (!merged.filled.length && !merged.needs.length) return say("No form fields found on this page. Open the application form itself (often behind an Apply button).", true);
      S.msg = ""; render();
    }).catch(function (err) { S.busy = ""; say(err.message || "Something went wrong.", true); });
  }
  function track(applied) {
    var title = (document.getElementById("tr-title") || {}).value || "", company = (document.getElementById("tr-company") || {}).value || "";
    if (!title.trim() || !company.trim()) return say("Add the role and the company first.", true);
    S.busy = "track"; render();
    api("/api/agent/track", { method: "POST", body: { url: S.tab.url, title: title.trim(), company: company.trim(), applied: applied } })
      .then(function (d) { S.busy = ""; S.tracked = d; say(d.created ? "Added to your applications." : "Updated the role you already had."); },
            function (err) { S.busy = ""; say(err.message, true); });
  }

  app.addEventListener("submit", function (e) { if (e.target.id === "connect") connect(e); });
  app.addEventListener("click", function (e) {
    var b = e.target.closest("[data-act]"); if (!b) return;
    var act = b.dataset.act;
    if (act === "fill") fill();
    else if (act === "track") track(b.dataset.applied === "1");
    else if (act === "frames") {
      var origins = S.page.frames.map(function (f) { return originOf(f) + "/*"; });
      chrome.permissions.request({ origins: origins }, function (ok) { S.framesOk = ok; if (ok) fill(); else say("Without that, Propelo can't reach the form inside the frame.", true); });
    }
    else if (act === "disconnect") { chrome.storage.local.remove(["server", "key"]); S.key = ""; S.report = null; S.msg = ""; render(); }
  });

  chrome.storage.local.get(["server", "key"], function (v) {
    S.server = v.server || ""; S.key = v.key || "";
    if (S.server && S.key) loadPage(); else render();
  });
})();
