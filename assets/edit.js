// Local edit mode. Served only by `python perseus.py edit` (reader/editserver.py), which adds
// this script to pages as it serves them; it is never copied into site/. Alt-click a paragraph
// to delete it: the rule goes to library/edits.tsv and takes effect on Rebuild or Publish.
(function () {
  "use strict";
  var body = document.body;
  var SRC = { g: body.getAttribute("data-src-g"), e: body.getAttribute("data-src-e"), f: body.getAttribute("data-src-f") };
  var ids = [SRC.g, SRC.e, SRC.f].filter(Boolean);

  // ---- styles ----
  var css = document.createElement("style");
  css.textContent =
    ".ed-bar{position:fixed;right:14px;bottom:14px;z-index:60;max-width:26rem;background:var(--panel);color:var(--ink);" +
    "border:1px solid var(--accent);border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.18);font:13px/1.45 system-ui,sans-serif;padding:.6rem .8rem}" +
    ".ed-bar b{color:var(--accent)} .ed-bar button{font:inherit;border:1px solid var(--faint);background:var(--paper);color:var(--ink);border-radius:999px;padding:.1rem .7rem;cursor:pointer;margin:.3rem .3rem 0 0}" +
    ".ed-bar button.go{background:var(--accent);color:var(--paper);border-color:var(--accent)} .ed-bar button:disabled{opacity:.5;cursor:default}" +
    ".ed-bar ul{list-style:none;margin:.4rem 0 0;padding:0;max-height:9rem;overflow:auto} .ed-bar li{display:flex;gap:.5rem;align-items:baseline;border-top:1px solid var(--faint);padding:.2rem 0}" +
    ".ed-bar li span{flex:1;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap} .ed-bar li button{margin:0;padding:0 .5rem}" +
    ".ed-bar pre{max-height:10rem;overflow:auto;background:var(--paper);border:1px solid var(--faint);border-radius:6px;padding:.4rem;margin:.4rem 0 0;font-size:11px;white-space:pre-wrap}" +
    ".ed-bar .min{float:right;border:0;background:none;margin:0;padding:0 .2rem;color:var(--muted)}" +
    ".ed-pop{position:absolute;z-index:61;background:var(--panel);border:1px solid var(--accent);border-radius:8px;padding:.5rem .7rem;font:13px/1.4 system-ui,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.2);max-width:24rem}" +
    ".ed-pop p{margin:0 0 .4rem;color:var(--muted)} .ed-pop button{font:inherit;border:1px solid var(--faint);background:var(--paper);color:var(--ink);border-radius:999px;padding:.1rem .7rem;cursor:pointer;margin-right:.3rem}" +
    ".ed-pop button.go{background:var(--accent);color:var(--paper);border-color:var(--accent)}" +
    ".ed-gone{text-decoration:line-through;opacity:.35} ::highlight(ed-para){background:var(--hl)}";
  document.head.appendChild(css);

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function post(url, data) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data || {}) })
      .then(function (r) { return r.json(); });
  }

  // ---- paragraphs as the build sees them (reader/edits.py: segments) ----------------------
  var BOUNDARY = ".pb, .spk, .sub, .stage, .gap";
  var SKIP = ".mk, .ln, sup.fn, .notes, summary";
  // one side of the page (original, translation, second translation) runs through many
  // blocks, each its own column element; a paragraph can continue from one to the next
  function sideOf(col) { return col.classList.contains("g") ? "g" : (col.classList.contains("f") ? "f" : "e"); }
  function columns(side) {
    var sel = side === "g" ? ".col.g" : (side === "f" ? ".col.f" : ".col.e:not(.f)");
    return document.querySelectorAll(sel);
  }
  function tokens(cols) {
    var out = [];
    for (var c = 0; c < cols.length; c++) walkCol(cols[c], out);
    return out;
  }
  function walkCol(col, out) {
    (function walk(el) {
      for (var n = el.firstChild; n; n = n.nextSibling) {
        if (n.nodeType === 3) { out.push({ t: n }); continue; }
        if (n.nodeType !== 1) continue;
        if (n.matches(SKIP)) continue;
        if (n.matches(BOUNDARY)) { out.push({ b: true }); continue; }
        if (n.matches(".bq")) { out.push({ b: true }); walk(n); out.push({ b: true }); continue; }
        if (n.matches(".v")) out.push({ v: true });
        walk(n);
      }
    })(col);
  }
  function paragraphAt(node) {
    var col = node.parentElement && node.parentElement.closest(".col");
    if (!col) return null;
    var side = sideOf(col), toks = tokens(columns(side)), i = -1;
    for (var k = 0; k < toks.length; k++) if (toks[k].t === node) { i = k; break; }
    if (i < 0) return null;
    var a = i, b = i;
    while (a > 0 && !toks[a - 1].b) a--;
    while (b < toks.length - 1 && !toks[b + 1].b) b++;
    var text = "", nodes = [];
    for (k = a; k <= b; k++) {
      if (toks[k].v) text += " ";
      else if (toks[k].t) { text += toks[k].t.nodeValue; nodes.push(toks[k].t); }
    }
    text = text.normalize("NFC").replace(/\s+/g, " ").trim();
    return text && nodes.length ? { id: SRC[side], text: text, nodes: nodes } : null;
  }

  // ---- the bar ------------------------------------------------------------------------------
  var bar = document.createElement("div");
  bar.className = "ed-bar";
  document.body.appendChild(bar);
  var rules = [], job = null, collapsed = false;
  try { collapsed = sessionStorage.getItem("ed-min") === "1"; } catch (e) {}

  function render() {
    if (collapsed) {
      bar.innerHTML = '<button class="min" data-a="max" title="Show">▴</button><b>Edit mode</b> · ' + rules.length + " edit" + (rules.length === 1 ? "" : "s") + " here";
      return;
    }
    var running = job && job.state === "running";
    var h = '<button class="min" data-a="min" title="Hide">▾</button><b>Edit mode</b> (this computer only)<br>';
    h += ids.length ? "Alt-click a paragraph to delete it." : "Open a text to edit it.";
    if (rules.length) {
      h += "<ul>" + rules.map(function (r, i) {
        return '<li><span title="' + esc(r.anchor) + '">' + esc(r.id.replace(/^.*?\./, "")) + ": " + esc(r.anchor) +
          '</span><button data-a="undo" data-i="' + i + '">undo</button></li>';
      }).join("") + "</ul>";
    }
    h += '<div><button data-a="build"' + (running ? " disabled" : "") + ' title="Rebuild the site here to see the edits">Rebuild</button>' +
      '<button class="go" data-a="publish"' + (running ? " disabled" : "") + ' title="Rebuild, commit library/edits.tsv, push to GitHub, deploy to Cloudflare">Publish</button></div>';
    if (job && job.state !== "idle") {
      h += '<div style="margin-top:.4rem">' + esc(job.name) + ": <b>" + esc(job.state) + "</b>" +
        (job.state === "done" && job.name === "Rebuild" ? ' <button data-a="reload">Reload page</button>' : "") + "</div>" +
        "<pre>" + esc(job.log.join("\n")) + "</pre>";
    }
    bar.innerHTML = h;
  }
  function loadRules() {
    if (!ids.length) { render(); return Promise.resolve(); }
    return fetch("/__edit/rules?ids=" + ids.map(encodeURIComponent).join(","))
      .then(function (r) { return r.json(); }).then(function (r) { rules = r; render(); });
  }
  function poll() {
    fetch("/__edit/status").then(function (r) { return r.json(); }).then(function (s) {
      job = s; render();
      if (s.state === "running") setTimeout(poll, 1500);
    });
  }
  bar.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-a]");
    if (!b) return;
    var a = b.getAttribute("data-a");
    if (a === "min" || a === "max") {
      collapsed = a === "min";
      try { sessionStorage.setItem("ed-min", collapsed ? "1" : "0"); } catch (err) {}
      render();
    } else if (a === "undo") {
      var r = rules[+b.getAttribute("data-i")];
      post("/__edit/undo", r).then(loadRules);
    } else if (a === "build" || a === "publish") {
      if (a === "publish" && !confirm("Publish: rebuild the site, commit library/edits.tsv, push to GitHub and deploy to Cloudflare Pages?")) return;
      post("/__edit/" + a).then(function () { poll(); });
    } else if (a === "reload") location.reload();
  });

  // ---- Alt-click: choose a paragraph -----------------------------------------------------------
  var pop = null;
  function closePop() {
    if (pop) { pop.remove(); pop = null; }
    if (window.CSS && CSS.highlights) CSS.highlights.delete("ed-para");
  }
  document.addEventListener("click", function (e) {
    if (pop && !pop.contains(e.target)) closePop();
    if (!e.altKey || !ids.length) return;
    var pos = document.caretPositionFromPoint ? document.caretPositionFromPoint(e.clientX, e.clientY) : null;
    var node = pos ? pos.offsetNode : (document.caretRangeFromPoint ? document.caretRangeFromPoint(e.clientX, e.clientY).startContainer : null);
    if (!node || node.nodeType !== 3) return;
    var para = paragraphAt(node);
    if (!para || !para.id) return;
    e.preventDefault(); e.stopPropagation();
    closePop();
    if (window.CSS && CSS.highlights && window.Highlight) {
      var range = document.createRange();
      range.setStart(para.nodes[0], 0);
      var last = para.nodes[para.nodes.length - 1];
      range.setEnd(last, last.nodeValue.length);
      CSS.highlights.set("ed-para", new Highlight(range));
    }
    pop = document.createElement("div");
    pop.className = "ed-pop";
    pop.innerHTML = "<p>" + esc(para.text.slice(0, 140)) + (para.text.length > 140 ? "…" : "") + "</p>" +
      '<button class="go" data-a="del">Delete paragraph</button><button data-a="cancel">Cancel</button>';
    pop.style.left = Math.min(e.pageX, window.scrollX + window.innerWidth - 400) + "px";
    pop.style.top = (e.pageY + 12) + "px";
    document.body.appendChild(pop);
    pop.addEventListener("click", function (ev) {
      ev.stopPropagation();
      var b = ev.target.closest("button");
      if (!b) return;
      if (b.getAttribute("data-a") === "del") {
        post("/__edit/delete", { id: para.id, text: para.text }).then(function (res) {
          if (res.ok) {
            para.nodes.forEach(function (t) {
              var s = document.createElement("span"); s.className = "ed-gone";
              t.parentNode.replaceChild(s, t); s.appendChild(t);
            });
            loadRules();
          }
          closePop();
        });
      } else closePop();
    });
  }, true);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closePop(); });

  loadRules();
  poll();
})();
