/* Propelo Autofill: the part that runs inside an application page.
   It fills empty fields from the Propelo profile it is given, attaches the resume, outlines what
   it filled, and lists what it left for you. It never presses Submit, never ticks consent boxes,
   never overwrites what is already typed, and never touches passwords, one-time codes, identity
   numbers, bank details or dates of birth. The page's own text is only matched, never followed. */
(function () {
  "use strict";
  if (window.__careerosFill) return;

  var BLOCKED = /(^|\.)(linkedin\.com|naukri\.com|indeed\.[a-z.]+|wellfound\.com|angel\.co)$/i;
  var SENSITIVE = /pass(word|code)|one[- ]?time|\botp\b|verification code|aadhaa?r|\bpan\b|pan (card|number)|permanent account|bank|ifsc|account (number|no)|routing|passport|date of birth|\bdob\b|birth ?date|\bssn\b|social security|national id|credit card|card number|\bcvv\b|security question|mother'?s maiden/i;

  // [key, label pattern]. First match wins, so specific labels come before general ones.
  var RULES = [
    ["firstName", /\b(first|given|fore) ?name\b|\bfname\b/i],
    ["lastName", /\b(last|family|sur) ?name\b|\bsurname\b|\blname\b/i],
    ["email", /e-?mail/i],
    ["phone", /phone|mobile|contact (number|no)|whats ?app/i],
    ["linkedin", /linked ?in/i],
    ["github", /git ?hub/i],
    ["portfolio", /portfolio|personal (site|website)|^website\b|\bwebsite\b|\burl\b|blog/i],
    ["currentCompany", /current (company|employer|organi[sz]ation)|present (company|employer)|^company( name)?$/i],
    ["currentTitle", /current (title|role|designation|position|job title)|^(job )?title$|designation/i],
    ["experienceYears", /(years|yrs)( of)? (total |relevant |work |professional )?experience|total experience|experience \((in )?years\)|^experience$/i],
    ["noticePeriod", /notice period|how soon can you (join|start)|earliest (start|joining)|availability to (join|start)/i],
    ["expectedCtcLpa", /expected (ctc|salary|compensation|pay)|salary expectation|desired (salary|compensation)|compensation expectation/i],
    ["currentCtcLpa", /current (ctc|salary|compensation|pay)|present (ctc|salary)/i],
    ["graduationYear", /graduation (year|date)|year of (graduation|passing)|passing year|batch/i],
    ["cgpa", /\bc?gpa\b|cgpa|^percentage$|percentage (scored|obtained)|aggregate (marks|score|percentage)|academic score|marks obtained/i],
    ["branch", /\bbranch\b|speciali[sz]ation|^major$|^stream$|^discipline$|field of study/i],
    ["backlogs", /backlogs?|arrears|\bkt\b/i],
    ["pinCode", /pin ?code|postal code|post ?code|zip ?code|\bzip\b/i],
    ["state", /^(state|province|state ?\/ ?ut|state or province|state of residence)$|\b(current|home|residential) state\b/i],
    ["degree", /degree|qualification|education level/i],
    ["college", /college|university|school|institut/i],
    ["workAuthIndia", /(authori[sz]ed|eligible|legally (allowed|permitted)).{0,40}work.{0,40}india|work (authori[sz]ation|permit).{0,30}india/i],
    ["sponsorshipAbroad", /sponsor/i],
    ["relocate", /relocat/i],
    ["city", /\bcity\b|current location|where are you (based|located)|^location\b|\blocation$|town/i],
    ["howHeard", /how did you (hear|find|learn)|where did you (hear|find)|referral source|^source$/i],
    ["fullName", /full ?name|^name\b|your name|candidate name|legal name|^name$/i]
  ];
  // Questions about someone else (a referrer, a reference, an emergency contact) are never filled with your details.
  var OTHER_PERSON = /referr(er|ed by|ing employee)|\breference\b|emergency|guardian|father|mother|spouse|parent|recruiter'?s|manager'?s|employee'?s/i;
  var CHOICE_KEYS = { workAuthIndia: 1, sponsorshipAbroad: 1, relocate: 1, noticePeriod: 1, degree: 1, backlogs: 1 };
  function words(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").split(/\s+/).filter(function (w) { return w.length > 2 && !/^(the|and|you|your|for|with|this|that|are|our|why|what|how|please|tell|describe)$/.test(w); }); }
  // A saved answer fits a question when they share most of their words, and a company-only answer
  // is used only on that company's form.
  function savedAnswer(label, answers, company) {
    var cw = words(company).concat(["here", "company", "join", "team", "organisation", "organization"]);
    var strip = function (ws) { return ws.filter(function (w) { return cw.indexOf(w) < 0; }); };
    var lw = strip(words(label)); if (lw.length < 2) return null;
    var co = String(company || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
    var best = null, bestScore = 0;
    (answers || []).forEach(function (a) {
      if (!a || !a.q || !a.a) return;
      var ac = String(a.company || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
      if (ac && (!co || (co.indexOf(ac) < 0 && ac.indexOf(co) < 0))) return;
      var qw = strip(words(a.q).filter(function (w) { return words(a.company).indexOf(w) < 0; })), inter = qw.filter(function (w) { return lw.indexOf(w) >= 0; }).length;
      var score = inter / Math.max(1, Math.min(qw.length, lw.length));
      if (score > bestScore) { best = a; bestScore = score; }
    });
    return bestScore >= 0.75 ? best : null;
  }

  function clean(s) { return String(s || "").replace(/[\s ]+/g, " ").replace(/[*:]+\s*$/, "").trim(); }
  function visible(el) {
    if (el.disabled || el.readOnly) return false;
    if (el.type === "hidden") return false;
    var r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none") return false;
    return (r.width > 0 && r.height > 0) || el.type === "file" || el.type === "radio";
  }
  function labelOf(el) {
    var parts = [];
    if (el.getAttribute("aria-labelledby")) el.getAttribute("aria-labelledby").split(/\s+/).forEach(function (id) { var n = document.getElementById(id); if (n) parts.push(n.textContent); });
    if (el.getAttribute("aria-label")) parts.push(el.getAttribute("aria-label"));
    if (el.id) { try { var l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) parts.push(l.textContent); } catch (e) { /* odd id */ } }
    var wrap = el.closest("label"); if (wrap) parts.push(wrap.textContent);
    if (!parts.length) {
      // Common form layouts: a label or legend in the same field wrapper.
      var box = el.closest(".field, .form-group, .application-question, .application-field, [class*='question'], [class*='field'], li, fieldset, div");
      for (var i = 0; box && i < 3 && !parts.length; i++, box = box.parentElement && box.parentElement.closest("div, fieldset, li")) {
        var lab = box.querySelector("label, legend, .label, [class*='label']"); if (lab && !lab.contains(el)) parts.push(lab.textContent);
      }
    }
    if (el.placeholder) parts.push(el.placeholder);
    return clean(parts.join(" ")).slice(0, 300);
  }
  function hints(el) { return [el.name, el.id, el.getAttribute("autocomplete"), el.getAttribute("data-qa"), el.getAttribute("data-automation-id")].filter(Boolean).join(" ").replace(/[_\-\[\]]+/g, " "); }
  function required(el, label) { return el.required || el.getAttribute("aria-required") === "true" || /\*\s*$|\(required\)|\brequired\b/i.test(label || ""); }

  // React, Vue and Angular track values through the prototype setter, so set it there and announce it.
  function setValue(el, v) {
    var proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    var desc = Object.getOwnPropertyDescriptor(proto, "value");
    el.focus({ preventScroll: true });
    if (desc && desc.set) desc.set.call(el, v); else el.value = v;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  }
  function norm(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9+]+/g, " ").trim(); }
  function pickOption(options, want) {
    var w = norm(want); if (!w) return null;
    var yes = /^(yes|y|true)$/.test(w), no = /^(no|n|false)$/.test(w);
    var best = null, bestScore = 0;
    options.forEach(function (o) {
      var t = norm(o.text), s = 0;
      if (!t || /^(select|choose|please select|none selected)/.test(t)) return;
      if (t === w) s = 100;
      else if (yes && /^yes\b/.test(t)) s = 90;
      else if (no && /^no\b/.test(t)) s = 90;
      else if (!yes && !no && (t.indexOf(w) === 0 || w.indexOf(t) === 0)) s = 70;
      else if (!yes && !no && t.indexOf(w) >= 0) s = 50;
      else { var n = parseFloat(w); var m = t.match(/(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)/); if (!isNaN(n) && m && n >= +m[1] && n <= +m[2]) s = 60; }
      if (s > bestScore) { best = o; bestScore = s; }
    });
    return best;
  }

  function valueFor(key, a) {
    var v = a[key];
    if (key === "firstName" && !v) v = String(a.fullName || "").split(" ")[0];
    if (key === "lastName" && !v) v = String(a.fullName || "").split(" ").slice(1).join(" ");
    if (key === "sponsorshipAbroad" && /not applicable/i.test(v || "")) v = "No";
    if ((key === "expectedCtcLpa" || key === "currentCtcLpa") && v !== undefined && v !== null && v !== "") v = String(v);
    if (key === "experienceYears" && v !== undefined && v !== null && v !== "") v = String(v);
    if (key === "graduationYear" && v) v = String(v);
    return v === undefined || v === null ? "" : String(v);
  }
  function matchKey(label, hint) {
    if (SENSITIVE.test(label) || SENSITIVE.test(hint)) return "__sensitive";
    var other = OTHER_PERSON.test(label);
    for (var i = 0; i < RULES.length; i++) if (RULES[i][1].test(label)) return other && RULES[i][0] !== "howHeard" ? "" : RULES[i][0];
    if (other) return "";
    for (var j = 0; j < RULES.length; j++) if (RULES[j][1].test(hint)) return RULES[j][0];
    if (/\bname\b/i.test(hint) && !/user ?name|company|file/i.test(hint)) return "fullName";
    return "";
  }
  function mark(el, kind) {
    el.setAttribute("data-careeros", kind);
    if (!document.getElementById("careeros-marks")) {
      var st = document.createElement("style"); st.id = "careeros-marks";
      st.textContent = "[data-careeros=filled]{outline:2px solid #F5B8DB!important;outline-offset:1px}[data-careeros=needs]{outline:2px dashed #E49A3C!important;outline-offset:1px}";
      (document.head || document.documentElement).appendChild(st);
    }
  }
  function questionOf(el, group) {
    var fs = el.closest("fieldset");
    if (fs && fs.querySelector("legend")) return clean(fs.querySelector("legend").textContent);
    var box = el.parentElement;
    for (var i = 0; box && i < 5; i++, box = box.parentElement) {
      if (!group.every(function (r) { return box.contains(r); })) continue;
      var cands = box.querySelectorAll("label, legend, p, span, div, h3, h4, [class*='label']");
      for (var j = 0; j < cands.length; j++) {
        var c = cands[j];
        if (c.querySelector("input") || group.some(function (r) { return c.contains(r) || (r.id && c.getAttribute("for") === r.id); })) continue;
        var t = clean(c.textContent); if (t.length > 3) return t.slice(0, 300);
      }
    }
    return clean(el.getAttribute("aria-label") || el.name || "");
  }
  function b64ToFile(r) {
    var bin = atob(r.b64), u = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    return new File([u], r.name || "resume.pdf", { type: r.type || "application/pdf" });
  }

  window.__careerosRead = function () {
    var h1 = document.querySelector("h1, .posting-headline h2, [data-automation-id='jobPostingHeader'], .app-title");
    var og = document.querySelector('meta[property="og:site_name"]'), ogt = document.querySelector('meta[property="og:title"]');
    var co = document.querySelector(".company-name, .main-header-logo img[alt], [class*='companyName'], [data-automation-id='company']");
    var company = co ? clean(co.getAttribute("alt") || co.textContent).replace(/^at /i, "") : og ? clean(og.content) : "";
    var title = h1 ? clean(h1.textContent) : ogt ? clean(ogt.content) : clean(document.title.split(/[|\-–]/)[0]);
    var m = location.pathname.match(/^\/([^/]+)\//);
    if (!company && /greenhouse\.io|lever\.co|ashbyhq\.com/.test(location.hostname) && m) company = m[1].replace(/[-_]+/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
    if (!company) company = location.hostname.replace(/^(www|careers|jobs|apply)\./, "").split(".")[0].replace(/\b\w/g, function (c) { return c.toUpperCase(); });
    return { url: location.href, title: title.slice(0, 160), company: company.slice(0, 120), host: location.hostname };
  };

  window.__careerosFill = function (data) {
    var out = { host: location.hostname, filled: [], needs: [], skippedSensitive: 0, resume: "", blocked: false };
    if (BLOCKED.test(location.hostname)) { out.blocked = true; return out; }
    var a = (data && data.applicant) || {};
    if (/prefer not/i.test(a.backlogs || "")) delete a.backlogs;
    out.fromAnswers = 0;
    var seenRadio = {};
    var fields = Array.prototype.slice.call(document.querySelectorAll("input, textarea, select"));
    fields.forEach(function (el) {
      var type = (el.type || "").toLowerCase();
      if (/^(submit|button|reset|image|hidden|password|checkbox|range|color|search)$/.test(type)) {
        if (type === "checkbox" && required(el, labelOf(el)) && !el.checked && visible(el)) { out.needs.push({ label: labelOf(el) || "A required checkbox", why: "Tick it yourself if it's true." }); mark(el, "needs"); }
        return;
      }
      if (!visible(el)) return;
      var label = labelOf(el), hint = hints(el), key = matchKey(label, hint);
      if (key === "__sensitive") { out.skippedSensitive++; if (required(el, label)) { out.needs.push({ label: label || "A private field", why: "Propelo never fills this. Type it yourself if you choose to share it." }); mark(el, "needs"); } return; }

      if (type === "file") {
        var isResume = /resume|\bcv\b|curriculum/i.test(label + " " + hint) && !/cover/i.test(label + " " + hint);
        if (!isResume) { if (required(el, label)) { out.needs.push({ label: label || "A file upload", why: "Attach this yourself." }); mark(el, "needs"); } return; }
        if (el.files && el.files.length) { out.resume = "already attached"; return; }
        if (!data.resume || !data.resume.b64) { out.resume = "no resume in Propelo"; out.needs.push({ label: label || "Resume", why: "Upload your resume PDF in Propelo first, or attach it here." }); mark(el, "needs"); return; }
        try { var dt = new DataTransfer(); dt.items.add(b64ToFile(data.resume)); el.files = dt.files; el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true })); out.resume = "attached"; mark(el, "filled"); out.filled.push({ label: label || "Resume", value: data.resume.name || "resume.pdf" }); }
        catch (e) { out.resume = "couldn't attach"; out.needs.push({ label: label || "Resume", why: "This page wouldn't take the file. Attach it yourself." }); mark(el, "needs"); }
        return;
      }

      if (type === "radio") {
        if (seenRadio[el.name]) return; seenRadio[el.name] = 1;
        var group = Array.prototype.slice.call(document.querySelectorAll('input[type=radio][name="' + (window.CSS ? CSS.escape(el.name) : el.name) + '"]'));
        if (group.some(function (r) { return r.checked; })) return;
        var q = questionOf(el, group);
        var gkey = matchKey(q, el.name || "");
        var want = gkey && gkey !== "__sensitive" && CHOICE_KEYS[gkey] ? valueFor(gkey, a) : gkey === "__sensitive" ? "" : "";
        var opts = group.map(function (r) { return { el: r, text: labelOf(r) || r.value }; });
        var hit = want ? pickOption(opts, want) : null;
        if (hit) { hit.el.click(); mark(hit.el, "filled"); out.filled.push({ label: q, value: hit.text }); }
        else if (required(el, q) || group.some(function (r) { return r.required; })) { out.needs.push({ label: q || "A choice", why: "Pick the answer that's true for you." }); group.forEach(function (r) { mark(r, "needs"); }); }
        return;
      }

      var current = el.tagName === "SELECT" ? (el.selectedIndex > 0 ? el.value : "") : el.value;
      if (String(current || "").trim()) return; // never overwrite what's there
      var v = key ? valueFor(key, a) : "";
      if (key === "gender" || /gender|ethnic|race|veteran|disabilit|caste|religio/i.test(label)) v = ""; // voluntary questions stay with you
      if (el.tagName === "SELECT") {
        var o = v ? pickOption(Array.prototype.slice.call(el.options).map(function (x) { return { el: x, text: x.text || x.value }; }), v) : null;
        if (o) { setValue(el, o.el.value); mark(el, "filled"); out.filled.push({ label: label, value: o.text }); return; }
      } else if (v) {
        if (type === "number" && isNaN(parseFloat(v))) v = "";
        if (type === "email" && v.indexOf("@") < 0) v = "";
        if (v) { setValue(el, v); mark(el, "filled"); out.filled.push({ label: label || key, value: v }); return; }
      }
      var saved = (el.tagName === "TEXTAREA" || type === "text" || !type) && !key ? savedAnswer(label, data.answers, data.company) : null;
      if (saved) { setValue(el, saved.a); mark(el, "filled"); out.filled.push({ label: label, value: "From your saved answers" }); out.fromAnswers++; return; }
      if (required(el, label) || el.tagName === "TEXTAREA") {
        out.needs.push({ label: label || "A question", why: el.tagName === "TEXTAREA" ? "Write this in your own words, or draft it in Propelo under Writing & interviews > Form answer." : "Propelo doesn't have this. Fill it in yourself." });
        mark(el, "needs");
      }
    });
    return out;
  };
})();
