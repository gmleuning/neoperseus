// Text search across the shelf. Each work's text sits in search/<work>.js and is loaded only
// when a search needs it. Accents, breathings, case, final sigma, u/v and i/j are ignored.
(function () {
  var WORKS = window.WORKS || [];
  var $ = function (id) { return document.getElementById(id); };
  var loaded = {}, waiting = {};
  var PER_WORK = 40, MAX_HITS = 3000;

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  // fold one character the same way everywhere (search box, texts, highlighting)
  var foldCache = Object.create(null);
  function foldChar(c) {
    var d = foldCache[c];
    if (d !== undefined) return d;
    d = c.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    if (d === "ς") d = "σ";
    if (d === "j") d = "i";
    if (d === "v") d = "u";
    return (foldCache[c] = d);
  }
  function fold(s) { var o = ""; for (var i = 0; i < s.length; i++) o += foldChar(s[i]); return o; }
  // folded text plus, for each folded character, its index in the original
  function foldMap(s) {
    var parts = new Array(s.length), map = null, same = true;
    for (var i = 0; i < s.length; i++) {
      var f = foldChar(s[i]);
      parts[i] = f;
      if (f.length !== 1) same = false;
    }
    var text = parts.join("");
    if (!same) {                       // only when folding changed a length do we need a map
      map = [];
      for (var k = 0; k < parts.length; k++) for (var j = 0; j < parts[k].length; j++) map.push(k);
      map.push(s.length);
    }
    return { text: text, map: map };
  }
  function orig(fm, i) { return fm.map ? fm.map[i] : i; }

  window.SearchLoaded = function (data) {
    loaded[data.work] = data;
    (waiting[data.work] || []).forEach(function (fn) { fn(data); });
    delete waiting[data.work];
  };
  function loadWork(w, cb) {
    if (loaded[w.work]) return cb(loaded[w.work]);
    (waiting[w.work] = waiting[w.work] || []).push(cb);
    if (waiting[w.work].length > 1) return;
    var s = document.createElement("script");
    s.src = w.search;
    s.onerror = function () { window.SearchLoaded({ work: w.work, parts: [], failed: true }); };
    document.body.appendChild(s);
  }

  // ---- scope menu ------------------------------------------------------------------
  var scope = $("scope");
  var params = new URLSearchParams(location.search);
  (function () {
    var opts = ['<option value="*">Everything on the shelf</option>'];
    var byAuthor = {}, authors = [];
    WORKS.forEach(function (w) {
      if (!byAuthor[w.author_id]) { byAuthor[w.author_id] = []; authors.push(w.author_id); }
      byAuthor[w.author_id].push(w);
    });
    authors.sort(function (a, b) { return byAuthor[a][0].author.localeCompare(byAuthor[b][0].author); });
    authors.forEach(function (a) {
      var list = byAuthor[a];
      opts.push('<optgroup label="' + esc(list[0].author) + '">');
      if (list.length > 1) opts.push('<option value="a:' + esc(a) + '">All of ' + esc(list[0].author) + " (" + list.length + ")</option>");
      list.forEach(function (w) { opts.push('<option value="w:' + esc(w.work) + '">' + esc(w.title) + "</option>"); });
      opts.push("</optgroup>");
    });
    scope.innerHTML = opts.join("");
    if (params.get("work")) scope.value = "w:" + params.get("work");
    if (params.get("q")) $("q").value = params.get("q");
  })();

  function inScope() {
    var v = scope.value;
    if (v === "*") return WORKS.slice();
    if (v.indexOf("a:") === 0) return WORKS.filter(function (w) { return w.author_id === v.slice(2); });
    return WORKS.filter(function (w) { return w.work === v.slice(2); });
  }

  // ---- matching -------------------------------------------------------------------
  var LETTER = /[\p{L}\p{M}]/u;
  function patterns(query, whole, forms) {
    var terms = forms && forms.length ? forms.map(fold) : [fold(query.trim()).replace(/\s+/g, " ")];
    var alts = terms.map(function (t) {
      return t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/ /g, "\\s+");
    });
    var body = "(?:" + alts.join("|") + ")";
    return new RegExp(whole ? "(?<![\\p{L}\\p{M}])" + body + "(?![\\p{L}\\p{M}])" : body, "gu");
  }

  function searchWork(data, rx, side, hits) {
    data.parts.forEach(function (part) {
      if (side !== "all" && part.side !== side) return;
      part.segs.forEach(function (seg) {
        if (!seg._f) seg._f = foldMap(seg[1]);
        rx.lastIndex = 0;
        var m;
        while ((m = rx.exec(seg._f.text))) {
          var a = orig(seg._f, m.index), b = orig(seg._f, m.index + m[0].length);
          hits.push({ part: part, key: seg[0], text: seg[1], a: a, b: b, word: seg[1].slice(a, b) });
          if (m[0].length === 0) rx.lastIndex++;
        }
      });
    });
  }

  function snippet(h) {
    var s = h.text, from = Math.max(0, h.a - 90), to = Math.min(s.length, h.b + 110);
    if (from > 0) { var sp = s.indexOf(" ", from); if (sp > 0 && sp < h.a) from = sp + 1; }
    if (to < s.length) { var sp2 = s.lastIndexOf(" ", to); if (sp2 > h.b) to = sp2; }
    return (from > 0 ? "… " : "") + esc(s.slice(from, h.a)) + '<mark class="hit">' + esc(s.slice(h.a, h.b)) +
      "</mark>" + esc(s.slice(h.b, to)) + (to < s.length ? " …" : "");
  }
  var LANGS = { grc: "Greek", lat: "Latin", eng: "English" };

  function render(results, total, query) {
    var html = [];
    results.forEach(function (r) {
      if (!r.hits.length) return;
      html.push('<h3 class="res-work">' + esc(r.work.author) + ", <i>" + esc(r.work.title) + '</i><span class="n">' +
        r.hits.length + (r.hits.length === 1 ? " hit" : " hits") + "</span></h3>");
      var shown = r.hits.slice(0, PER_WORK);
      shown.forEach(function (h) {
        var id = (h.part.side === "L" ? "L" : "E") + h.key;
        var words = encodeURIComponent(fold(h.word).split(/\s+/).join("|"));
        var href = h.part.href + "?hl=" + words + (h.key ? "#" + encodeURIComponent(id) : "");
        var lang = h.part.lang === "grc" ? "grc" : (h.part.lang === "lat" ? "la" : "en");
        html.push('<div class="res"><a class="at" href="' + esc(href) + '">' + esc(h.key || "start") +
          '<span class="side"> ' + esc(LANGS[h.part.lang] || "") + '</span></a><div class="snip" lang="' + lang + '">' +
          snippet(h) + "</div></div>");
      });
      if (r.hits.length > PER_WORK) {
        html.push('<p class="search-note">' + (r.hits.length - PER_WORK) +
          ' more in this work. Narrow the search to this work to see them all.</p>');
      }
    });
    $("results").innerHTML = html.join("");
    var nworks = results.filter(function (r) { return r.hits.length; }).length;
    $("status").textContent = total ? total + (total === 1 ? " hit" : " hits") + " in " + nworks +
      (nworks === 1 ? " work" : " works") + (total >= MAX_HITS ? " (stopped at " + MAX_HITS + "; narrow the search)" : "")
      : "No hits for “" + query + "”.";
  }

  var runId = 0;
  function run(forms) {
    var query = $("q").value.trim();
    if (!query) return;
    var my = ++runId;
    var list = inScope(), side = $("side").value, whole = $("whole").checked;
    var rx = patterns(query, whole, forms);
    var results = [], total = 0, i = 0;
    var bar = $("prog"), fill = bar.querySelector("i");
    bar.hidden = list.length < 3;
    $("status").textContent = forms ? "Searching " + forms.length + " forms…" : "Searching…";
    if (perWorkMode()) PER_WORK = 100000; else PER_WORK = 40;
    function next() {
      if (my !== runId) return;
      if (i >= list.length || total >= MAX_HITS) {
        bar.hidden = true;
        render(results, total, query);
        var u = new URL(location.href);
        u.searchParams.set("q", query);
        history.replaceState(null, "", u);
        return;
      }
      var w = list[i++];
      fill.style.width = Math.round(100 * i / list.length) + "%";
      loadWork(w, function (data) {
        var hits = [];
        searchWork(data, rx, side, hits);
        total += hits.length;
        results.push({ work: w, hits: hits });
        setTimeout(next, 0);
      });
    }
    next();
  }
  function perWorkMode() { return scope.value.indexOf("w:") === 0; }

  $("sf").addEventListener("submit", function (e) {
    e.preventDefault();
    if ($("forms").checked) {
      var word = $("q").value.trim();
      if (!window.ReaderDict || !window.ReaderDict.formsOf) {
        $("status").textContent = "All-forms search needs the dictionary: run  python perseus.py dictionaries  once.";
        return;
      }
      $("status").textContent = "Looking up the forms of " + word + "…";
      window.ReaderDict.formsOf(word, function (forms, lemmas) {
        if (!forms || !forms.length) {
          $("status").textContent = "The dictionary does not know “" + word + "”. Searching for the word as typed.";
          return run(null);
        }
        run(forms);
      });
    } else run(null);
  });
  ["scope", "side", "whole"].forEach(function (id) {
    $(id).addEventListener("change", function () { if ($("q").value.trim()) $("sf").requestSubmit(); });
  });
  if ($("q").value) $("sf").requestSubmit();
})();
