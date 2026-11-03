// Reader settings: applied before the page draws (this file loads in <head>), stored in this
// browser only, and editable from the Settings panel (gear button or the "," key).
(function () {
  var KEY = "reader-settings";
  var DEFAULTS = {
    theme: "auto", grc: "Gentium Book Plus", lat: "Gentium Book Plus", eng: "Spectral",
    size: 17, oscale: 110, lh: 1.6, width: "medium",
    cols: "both", align: "speech", ln: "5", mk: "on", fn: "on", toc: "on", justify: "off",
    dict: "on", abbr: "expand"
  };
  var FONTS = {
    grc: ["Gentium Book Plus", "EB Garamond", "Cardo", "GFS Didot", "GFS Neohellenic", "Palatino Linotype", "Times New Roman"],
    lat: ["Gentium Book Plus", "Spectral", "EB Garamond", "Cardo", "Georgia", "Palatino Linotype"],
    eng: ["Spectral", "EB Garamond", "Cardo", "Gentium Book Plus", "Georgia", "Palatino Linotype", "system-ui"]
  };
  var WIDTHS = { narrow: "64rem", medium: "84rem", wide: "110rem", full: "none" };

  function load() {
    var p = {};
    try { p = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { p = {}; }
    var out = {};
    for (var k in DEFAULTS) out[k] = (k in p) ? p[k] : DEFAULTS[k];
    return out;
  }
  function save(p) { try { localStorage.setItem(KEY, JSON.stringify(p)); } catch (e) {} }
  function fam(name) { return name === "system-ui" ? "system-ui, sans-serif" : '"' + name + '"'; }

  var prefs = load();
  var listeners = [];

  function apply() {
    var r = document.documentElement, s = r.style, p = prefs;
    if (p.theme === "auto") r.removeAttribute("data-theme"); else r.setAttribute("data-theme", p.theme);
    s.setProperty("--font-grc", fam(p.grc));
    s.setProperty("--font-lat", fam(p.lat));
    s.setProperty("--font-eng", fam(p.eng));
    s.setProperty("--fs", p.size + "px");
    s.setProperty("--oscale", String(p.oscale / 100));
    s.setProperty("--lh", String(p.lh));
    s.setProperty("--page-max", WIDTHS[p.width] || WIDTHS.medium);
    var cls = r.className.replace(/\b(cols-\w+|ln-\w+|no-mk|no-fn|no-toc|justify|dict-on)\b/g, "").trim();
    var add = [];
    if (p.cols !== "both") add.push("cols-" + p.cols);
    if (p.ln === "all") add.push("ln-all");
    if (p.ln === "off") add.push("ln-off");
    if (p.mk === "off") add.push("no-mk");
    if (p.fn === "off") add.push("no-fn");
    if (p.toc === "off") add.push("no-toc");
    if (p.justify === "on") add.push("justify");
    if (p.dict === "on") add.push("dict-on");
    r.className = (cls + " " + add.join(" ")).trim();
    for (var i = 0; i < listeners.length; i++) listeners[i](p);
  }
  apply();

  window.ReaderSettings = {
    get: function (k) { return prefs[k]; },
    set: function (k, v) { prefs[k] = v; save(prefs); apply(); },
    onChange: function (fn) { listeners.push(fn); }
  };

  // ---- the panel ----------------------------------------------------------------
  function el(tag, attrs, html) {
    var e = document.createElement(tag);
    for (var a in attrs || {}) e.setAttribute(a, attrs[a]);
    if (html != null) e.innerHTML = html;
    return e;
  }
  function chips(key, options) {
    var wrap = el("div", { "class": "chips", role: "group" });
    options.forEach(function (o) {
      var b = el("button", { type: "button", "data-v": o[0] }, o[1]);
      b.setAttribute("aria-pressed", String(prefs[key] === o[0]));
      b.addEventListener("click", function () {
        window.ReaderSettings.set(key, o[0]);
        var all = wrap.querySelectorAll("button");
        for (var i = 0; i < all.length; i++) all[i].setAttribute("aria-pressed", String(all[i] === b));
      });
      wrap.appendChild(b);
    });
    return wrap;
  }
  function select(key, options) {
    var s = el("select", { id: "set-" + key });
    options.forEach(function (o) {
      var opt = el("option", { value: o }, o === "system-ui" ? "System sans-serif" : o);
      opt.style.fontFamily = fam(o);
      if (prefs[key] === o) opt.selected = true;
      s.appendChild(opt);
    });
    s.addEventListener("change", function () { window.ReaderSettings.set(key, s.value); });
    return s;
  }
  function range(key, min, max, step, fmt) {
    var wrap = el("div");
    var r = el("input", { type: "range", min: min, max: max, step: step, id: "set-" + key, value: prefs[key] });
    var v = el("div", { "class": "val" }, fmt(prefs[key]));
    r.addEventListener("input", function () {
      var n = parseFloat(r.value);
      v.textContent = fmt(n);
      window.ReaderSettings.set(key, n);
    });
    wrap.appendChild(r); wrap.appendChild(v);
    return wrap;
  }
  function row(label, control, forId) {
    var r = el("div", { "class": "set-row" });
    r.appendChild(el("label", forId ? { "for": forId } : {}, label));
    r.appendChild(control);
    return r;
  }
  function group(title, rows) {
    var f = el("fieldset", { "class": "set-group" });
    f.appendChild(el("legend", {}, title));
    rows.forEach(function (r) { f.appendChild(r); });
    return f;
  }
  var SW = function (c) { return '<span class="swatch" style="background:' + c + '"></span>'; };

  function build() {
    var d = el("aside", { "class": "drawer", id: "settings", "aria-label": "Settings", "aria-hidden": "true" });
    var head = el("header");
    head.appendChild(el("h2", {}, "Settings"));
    var close = el("button", { type: "button", "class": "close", "aria-label": "Close settings" }, "×");
    head.appendChild(close);
    var body = el("div", { "class": "body" });
    body.appendChild(group("Appearance", [
      row("Colour scheme", chips("theme", [["auto", "Auto"], ["light", SW("#f4f5f2") + "Light"],
        ["sepia", SW("#f3ead8") + "Sepia"], ["dark", SW("#15171b") + "Dark"], ["black", SW("#000") + "Black"]])),
      row("Page width", chips("width", [["narrow", "Narrow"], ["medium", "Medium"], ["wide", "Wide"], ["full", "Full"]]))
    ]));
    var preview = el("div", { "class": "preview" },
      '<span class="pg" lang="grc">μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος</span>' +
      '<span class="pl" lang="la">Arma virumque cano, Troiae qui primus ab oris</span>' +
      '<span class="pe">Sing, goddess, the wrath of Achilles, son of Peleus</span>');
    body.appendChild(group("Type", [
      row("Greek font", select("grc", FONTS.grc), "set-grc"),
      row("Latin font", select("lat", FONTS.lat), "set-lat"),
      row("English font", select("eng", FONTS.eng), "set-eng"),
      preview,
      row("Text size", range("size", 14, 24, 1, function (n) { return n + " px"; }), "set-size"),
      row("Greek & Latin size", range("oscale", 90, 140, 5, function (n) { return n + "% of the English"; }), "set-oscale"),
      row("Line spacing", range("lh", 1.3, 2.1, 0.05, function (n) { return n.toFixed(2); }), "set-lh"),
      row("Justify prose", chips("justify", [["off", "Off"], ["on", "On"]]))
    ]));
    body.appendChild(group("Layout", [
      row("Columns", chips("cols", [["both", "Side by side"], ["stack", "Stacked"], ["orig", "Original only"], ["trans", "Translation only"]])),
      row("Alignment", chips("align", [["speech", "Blocks"], ["tight", "Lines"]])),
      row("Line numbers", chips("ln", [["5", "Every 5"], ["all", "Every line"], ["off", "Off"]])),
      row("Section numbers", chips("mk", [["on", "Show"], ["off", "Hide"]])),
      row("Footnotes", chips("fn", [["on", "Show"], ["off", "Hide"]])),
      row("Contents sidebar", chips("toc", [["on", "Show"], ["off", "Hide"]]))
    ]));
    body.appendChild(group("Dictionary", [
      row("Click a word", chips("dict", [["on", "Look it up"], ["off", "Do nothing"]])),
      row("Citations", chips("abbr", [["expand", "Author and title"], ["short", "LSJ abbreviations"]]))
    ]));
    var reset = el("button", { type: "button", "class": "icon-btn reset" }, "Reset all settings");
    reset.addEventListener("click", function () {
      prefs = JSON.parse(JSON.stringify(DEFAULTS)); save(prefs); apply();
      d.remove(); panel = null; open();
    });
    body.appendChild(reset);
    d.appendChild(head); d.appendChild(body);
    close.addEventListener("click", shut);
    document.body.appendChild(d);
    return d;
  }

  var panel = null;
  function open() {
    if (window.ReaderDict) window.ReaderDict.close();
    panel = panel || build();
    panel.classList.add("open");
    panel.setAttribute("aria-hidden", "false");
    var b = document.querySelector("[data-settings]");
    if (b) b.setAttribute("aria-expanded", "true");
    var first = panel.querySelector("button, select, input");
    if (first) first.focus();
  }
  function shut() {
    if (!panel) return;
    panel.classList.remove("open");
    panel.setAttribute("aria-hidden", "true");
    var b = document.querySelector("[data-settings]");
    if (b) { b.setAttribute("aria-expanded", "false"); b.focus(); }
  }
  window.ReaderSettings.open = open;
  window.ReaderSettings.close = shut;

  document.addEventListener("DOMContentLoaded", function () {
    var btns = document.querySelectorAll("[data-settings]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener("click", function () {
        if (panel && panel.classList.contains("open")) shut(); else open();
      });
    }
    document.addEventListener("keydown", function (e) {
      var tag = e.target.tagName;
      if (e.key === "Escape") shut();
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === ",") { e.preventDefault(); if (panel && panel.classList.contains("open")) shut(); else open(); }
    });
  });
})();
