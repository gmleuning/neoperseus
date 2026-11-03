// Dictionary side panel. Click a Greek or Latin word: the panel lists the dictionary words it
// can come from (with the parse, for Greek), and shows the full LSJ or Lewis & Short entry.
// Data is in dict/ (built by: python perseus.py dictionaries), loaded a few letters at a time.
(function () {
  var body = document.body;
  var ROOT = body.getAttribute("data-root") || "";
  var S = window.ReaderSettings;
  var DIRS = { "lsj": "lsj", "ls": "ls", "grc-forms": "grc-forms", "grc-lemmaforms": "grc-lemmaforms", "lat-stems": "lat-stems" };
  var cache = {}, waiting = {}, failed = {};

  // ---- loading -----------------------------------------------------------------------
  window.DictLoaded = function (name, bucket, data) {
    var id = name + "/" + bucket;
    cache[id] = data;
    (waiting[id] || []).forEach(function (fn) { fn(data); });
    delete waiting[id];
  };
  function bucketOf(key) {
    var k = (key + "__").slice(0, 2), out = [];
    for (var i = 0; i < 2; i++) out.push(k.charCodeAt(i).toString(16));
    return out.join("-");
  }
  function script(src, onerror) {
    var s = document.createElement("script");
    s.src = src;
    if (onerror) s.onerror = onerror;
    document.body.appendChild(s);
  }
  function get(name, key) {
    return new Promise(function (resolve) {
      var b = bucketOf(key), id = name + "/" + b;
      if (cache[id]) return resolve(cache[id][key] || null);
      if (failed[id]) return resolve(null);
      var first = !waiting[id];
      (waiting[id] = waiting[id] || []).push(function (d) { resolve(d ? (d[key] || null) : null); });
      if (first) script(ROOT + "dict/" + DIRS[name] + "/" + b + ".js", function () {
        failed[id] = true;
        (waiting[id] || []).forEach(function (fn) { fn(null); });
        delete waiting[id];
      });
    });
  }
  function loadScript(src) {
    return new Promise(function (resolve) {
      var s = document.createElement("script");
      s.src = src;
      s.onload = function () { resolve(true); };
      s.onerror = function () { resolve(false); };
      document.body.appendChild(s);
    });
  }
  var ready = null;
  function dictReady() {        // the work-title table, and the map of works on the shelf
    if (!ready) {
      ready = Promise.all([window.DICT_WORKS ? true : loadScript(ROOT + "dict/meta.js"),
                           window.SHELF ? true : loadScript(ROOT + "shelf.js")])
        .then(function () { return !!window.DICT_WORKS; });
    }
    return ready;
  }

  // ---- folding (same rules as the Python builder) --------------------------------------
  function fold(s, latin) {
    s = s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/ς/g, "σ");
    if (latin) s = s.replace(/j/g, "i").replace(/v/g, "u");
    return s.replace(/[^\p{L}\p{N}_]/gu, "");
  }
  function exactForm(s) {     // compare with accents, but a grave counts as an acute
    return s.normalize("NFD").replace(/̀/g, "́").normalize("NFC").toLowerCase().replace(/[’'ʼ]/g, "");
  }
  function noDigits(s) { return s.replace(/\d+$/, ""); }

  // ---- Greek parse codes (Perseus tag set) ----------------------------------------------
  var POS = { n: "noun", v: "verb", t: "participle", a: "adjective", d: "adverb", l: "article", g: "particle",
    c: "conjunction", r: "preposition", p: "pronoun", m: "numeral", i: "interjection", e: "exclamation", x: "irregular" };
  var PER = { 1: "1st", 2: "2nd", 3: "3rd" }, NUM = { s: "sg", p: "pl", d: "dual" };
  var TENSE = { p: "pres", i: "imperf", r: "perf", l: "plupf", t: "fut perf", f: "fut", a: "aor" };
  var MOOD = { i: "ind", s: "subj", o: "opt", n: "inf", m: "imperat", p: "part" };
  var VOICE = { a: "act", p: "pass", m: "mid", e: "mid/pass" };
  var GEN = { m: "masc", f: "fem", n: "neut", c: "common" }, CASE = { n: "nom", g: "gen", d: "dat", a: "acc", v: "voc", l: "loc" };
  var DEG = { c: "comp", s: "superl" };
  function parseText(p) {
    if (!p) return "";
    var c = p.split(""), out = [POS[c[0]] || ""];
    [[PER, 1], [NUM, 2], [TENSE, 3], [MOOD, 4], [VOICE, 5], [GEN, 6], [CASE, 7], [DEG, 8]].forEach(function (x) {
      var v = x[0][c[x[1]]];
      if (v) out.push(v);
    });
    return out.filter(Boolean).join(" ");
  }

  // ---- Greek lookup ---------------------------------------------------------------------
  function lookupGreek(word) {
    var key = fold(word);
    return get("grc-forms", key).then(function (rows) {
      rows = rows || [];
      var exact = rows.filter(function (r) { return exactForm(r[0]) === exactForm(word); });
      var use = exact.length ? exact : rows;
      var lemmas = {}, order = [];
      use.forEach(function (r) {
        var l = r[1];
        if (!lemmas[l]) { lemmas[l] = { lemma: l, parses: [], exact: exact.length > 0 }; order.push(l); }
        if (lemmas[l].parses.indexOf(r[2]) < 0) lemmas[l].parses.push(r[2]);
      });
      if (!order.length) {                       // not an inflected form Morpheus knows: try it as a headword
        order.push(word);
        lemmas[word] = { lemma: word, parses: [], exact: false, direct: true };
      }
      return Promise.all(order.map(function (l) {
        return get("lsj", fold(noDigits(l))).then(function (entries) {
          entries = entries || [];
          var want = exactForm(noDigits(l));
          var same = entries.filter(function (e) { return exactForm(e[0]) === want; });
          lemmas[l].entries = same.length ? same : entries;
          return lemmas[l];
        });
      }));
    }).then(function (cands) {
      cands = cands.filter(function (c) { return c.entries.length || !c.direct; });
      cands.sort(function (a, b) {
        var la = a.entries.reduce(function (n, e) { return n + e[1].length; }, 0);
        var lb = b.entries.reduce(function (n, e) { return n + e[1].length; }, 0);
        return (b.entries.length > 0) - (a.entries.length > 0) || lb - la;
      });
      return { lang: "grc", source: "LSJ", cands: cands };
    });
  }

  // ---- Latin lookup (ending stripped, matched against Lewis & Short stems) ------------------
  var ENDINGS = ["issimorum", "issimarum", "issimus", "issima", "issimum", "iebamus", "iebatis", "erimus", "eritis",
    "erunt", "eramus", "eratis", "issemus", "issetis", "issent", "isset", "isses", "issem", "isse", "istis", "isti",
    "ebamus", "ebatis", "abamus", "abatis", "iebam", "iebas", "iebat", "iebant", "ebam", "ebas", "ebat", "ebant",
    "abam", "abas", "abat", "abant", "abimus", "abitis", "abunt", "ebimus", "ebitis", "ebunt", "abo", "abis", "abit",
    "ebo", "ebis", "ebit", "iemus", "ietis", "ient", "iam", "ies", "iet", "ndorum", "ndarum", "ndum", "ndus", "nda",
    "ndi", "ndo", "ndae", "ndam", "ndis", "ntium", "ntibus", "ntis", "nti", "ntem", "ntes", "ntia", "ns",
    "rentur", "remur", "remini", "rer", "reris", "retur", "ntur", "mini", "mur", "tur", "ris", "re", "ri", "rem",
    "res", "ret", "remus", "retis", "rent", "imus", "itis", "unt", "erim", "eris", "erit", "erint", "eram", "eras",
    "erat", "erant", "ero", "orum", "arum", "ibus", "ubus", "ebus", "ium", "uum", "ius", "ior", "iores", "ioris",
    "iorem", "iori", "ius", "ei", "em", "es", "is", "os", "as", "us", "um", "ae", "am", "a", "o", "e", "i", "u",
    "mus", "tis", "nt", "it", "at", "et", "ut", "t", "s", "m", "r", "ere", "are", "ire", "x", "ix", "ex"];
  ENDINGS.sort(function (a, b) { return b.length - a.length; });

  function lookupLatin(word) {
    var w = fold(word, true);
    var variants = [w];
    ["que", "ne", "ue"].forEach(function (enc) {
      if (w.length > enc.length + 2 && w.slice(-enc.length) === enc) variants.push(w.slice(0, -enc.length));
    });
    var stems = {};            // stem -> score (longer stems are more specific)
    variants.forEach(function (v) {
      stems[v] = Math.max(stems[v] || 0, 100 + v.length);
      ENDINGS.forEach(function (e) {
        if (v.length > e.length + 1 && v.slice(-e.length) === e) {
          var st = v.slice(0, -e.length);
          [st, st.replace(/[aeiu]$/, ""), st.replace(/ie$/, ""), st.replace(/i$/, "")].forEach(function (s) {
            if (s.length >= 2) stems[s] = Math.max(stems[s] || 0, s.length);
          });
        }
      });
    });
    var exactHeads = variants;
    return Promise.all(exactHeads.map(function (h) { return get("ls", h).then(function (e) { return [h, e]; }); }))
      .then(function (direct) {
        var found = {};
        direct.forEach(function (d) { if (d[1]) found[d[0]] = 1000 + d[0].length; });
        return Promise.all(Object.keys(stems).map(function (s) {
          return get("lat-stems", s).then(function (heads) {
            (heads || []).forEach(function (h) { found[h] = Math.max(found[h] || 0, stems[s]); });
          });
        })).then(function () { return found; });
      }).then(function (found) {
        var keys = Object.keys(found).sort(function (a, b) { return found[b] - found[a]; }).slice(0, 30);
        return Promise.all(keys.map(function (k) {
          return get("ls", k).then(function (entries) { return { lemma: k, parses: [], entries: entries || [], score: found[k] }; });
        }));
      }).then(function (cands) {
        cands = cands.filter(function (c) { return c.entries.length; });
        cands.sort(function (a, b) {
          var la = a.entries.reduce(function (n, e) { return n + e[1].length; }, 0);
          var lb = b.entries.reduce(function (n, e) { return n + e[1].length; }, 0);
          return (b.score >= 1000) - (a.score >= 1000) || b.score - a.score || lb - la;
        });
        return { lang: "la", source: "Lewis & Short", cands: cands.slice(0, 5) };
      });
  }

  // ---- panel ------------------------------------------------------------------------------
  var panel = null, current = null, marked = null;
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  function build() {
    panel = document.createElement("aside");
    panel.className = "drawer dict";
    panel.id = "dict";
    panel.setAttribute("aria-label", "Dictionary");
    panel.innerHTML = '<header><h2 id="dict-title">Dictionary</h2><button type="button" class="close" aria-label="Close dictionary">×</button></header>' +
      '<div class="body"><form class="look"><input type="search" aria-label="Look up a word" placeholder="Look up a Greek or Latin word"><button type="submit" class="icon-btn">Look up</button></form><div id="dict-out"></div></div>';
    document.body.appendChild(panel);
    panel.querySelector(".close").addEventListener("click", close);
    panel.querySelector("form").addEventListener("submit", function (e) {
      e.preventDefault();
      var v = panel.querySelector("input").value.trim();
      if (v) lookup(v, /[Ͱ-Ͽἀ-῿]/.test(v) ? "grc" : "la");
    });
    panel.addEventListener("click", function (e) {
      var b = e.target.closest("button.cand");
      if (b && current) { showEntry(+b.getAttribute("data-i")); }
    });
    return panel;
  }
  function open() {
    if (S && S.close) S.close();
    (panel || build()).classList.add("open");
    document.documentElement.classList.add("drawer-open");
  }
  function close() {
    if (!panel) return;
    panel.classList.remove("open");
    document.documentElement.classList.remove("drawer-open");
    unmark();
  }
  window.ReaderDict = { close: close, formsOf: formsOf, lookup: function (w, l) { lookup(w, l); } };

  function expandCitations(root) {
    var expand = !S || S.get("abbr") !== "short";
    var links = root.querySelectorAll(".cit[data-w]");
    for (var i = 0; i < links.length; i++) {
      var a = links[i], w = a.getAttribute("data-w"), r = a.getAttribute("data-r");
      var meta = window.DICT_WORKS && window.DICT_WORKS[w];
      if (meta) {
        a.title = meta[0] + ", " + meta[1] + " " + r;
        if (expand) a.textContent = meta[0] + ", " + meta[1] + " " + r;
      }
      var page = window.SHELF && window.SHELF[w];
      if (page) { a.href = ROOT + page + "#L" + r; }
      else { a.removeAttribute("href"); a.classList.remove("cit"); a.classList.add("cit", "off"); }
    }
  }
  function showEntry(i) {
    var c = current.cands[i], out = panel.querySelector("#dict-out");
    var btns = out.querySelectorAll("button.cand");
    for (var j = 0; j < btns.length; j++) btns[j].setAttribute("aria-pressed", String(j === i));
    var box = out.querySelector(".entries");
    if (!c.entries.length) {
      box.innerHTML = '<p class="note">No ' + esc(current.source) + " entry for " + esc(noDigits(c.lemma)) + ".</p>";
      return;
    }
    box.innerHTML = c.entries.map(function (e) { return '<div class="entry">' + e[1] + "</div>"; }).join("<hr>");
    expandCitations(box);
    box.scrollTop = 0;
    panel.querySelector(".body").scrollTop = 0;
  }
  function render(word, res) {
    current = res;
    var out = panel.querySelector("#dict-out"), langAttr = res.lang;
    panel.querySelector("#dict-title").innerHTML = '<span lang="' + langAttr + '">' + esc(word) + "</span>";
    if (!res.cands.length) {
      out.innerHTML = '<p class="note">' + esc(res.source) + " has nothing for <span lang=\"" + langAttr + "\">" + esc(word) +
        "</span>." + (res.lang === "la" ? " Latin forms are matched by their endings, which misses irregular forms; try the dictionary form in the box above." : " Try the dictionary form in the box above.") + "</p>";
      return;
    }
    var list = res.cands.map(function (c, i) {
      var parses = c.parses.map(parseText).filter(Boolean);
      return '<button type="button" class="cand" data-i="' + i + '" aria-pressed="false"><span class="lem" lang="' + langAttr + '">' +
        esc(noDigits(c.entries.length ? c.entries[0][0] : c.lemma)) + "</span>" +
        (parses.length ? '<span class="parse">' + esc(parses.slice(0, 4).join("; ")) + (parses.length > 4 ? "; …" : "") + "</span>" : "") +
        (c.entries.length ? "" : '<span class="gl">not in ' + esc(res.source) + "</span>") + "</button>";
    }).join("");
    out.innerHTML = '<div class="forms">' + list + '</div><p class="src">' + esc(res.source) +
      (res.cands.length > 1 ? " · other possible words above" : "") + '</p><div class="entries"></div>';
    showEntry(0);
  }
  function lookup(word, lang) {
    open();
    var out = panel.querySelector("#dict-out");
    out.innerHTML = '<p class="note">Looking up…</p>';
    dictReady().then(function (ok) {
      if (!ok) {
        out.innerHTML = '<p class="note">The dictionaries are not built yet. In the reader folder run <code>python perseus.py dictionaries</code> once (it downloads about 440 MB), then reload this page.</p>';
        return;
      }
      (lang === "grc" ? lookupGreek(word) : lookupLatin(word)).then(function (res) { render(word, res); });
    });
  }

  // all forms of a Greek word, for the search page
  function formsOf(word, cb) {
    dictReady().then(function (ok) {
      if (!ok) return cb(null, []);
      lookupGreek(word).then(function (res) {
        var lemmas = res.cands.filter(function (c) { return !c.direct; }).map(function (c) { return c.lemma; });
        if (!lemmas.length) return cb(null, []);
        Promise.all(lemmas.map(function (l) { return get("grc-lemmaforms", fold(l)); })).then(function (lists) {
          var all = {};
          lists.forEach(function (l) { (l || []).forEach(function (f) { all[f] = 1; }); });
          cb(Object.keys(all), lemmas.map(noDigits));
        });
      });
    });
  }

  // ---- clicking a word in the text -----------------------------------------------------------
  var WORDCH = /[\p{L}\p{M}’'ʼ]/u;
  function unmark() {
    if (marked && marked.parentNode) {
      var t = document.createTextNode(marked.textContent);
      marked.parentNode.replaceChild(t, marked);
      t.parentNode.normalize();
    }
    marked = null;
  }
  function caretAt(x, y) {
    if (document.caretPositionFromPoint) {
      var p = document.caretPositionFromPoint(x, y);
      return p ? { node: p.offsetNode, offset: p.offset } : null;
    }
    if (document.caretRangeFromPoint) {
      var r = document.caretRangeFromPoint(x, y);
      return r ? { node: r.startContainer, offset: r.startOffset } : null;
    }
    return null;
  }
  document.addEventListener("click", function (e) {
    if (S && S.get("dict") !== "on") return;
    var col = e.target.closest && e.target.closest(".col.g");
    if (!col) return;
    var lang = col.getAttribute("lang");
    if (lang !== "grc" && lang !== "la") return;
    if (e.target.closest("a, sup, .ln, .mk, .spk, .stage, .notes, button, summary")) return;
    var sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;           // the reader is selecting text, not looking up
    var c = caretAt(e.clientX, e.clientY);
    if (!c || c.node.nodeType !== 3) return;
    var text = c.node.nodeValue, a = c.offset, b = c.offset;
    while (a > 0 && WORDCH.test(text[a - 1])) a--;
    while (b < text.length && WORDCH.test(text[b])) b++;
    var word = text.slice(a, b).replace(/^[’'ʼ]+/, "");
    if (!word || !/\p{L}/u.test(word)) return;
    unmark();
    var range = document.createRange();
    range.setStart(c.node, a); range.setEnd(c.node, b);
    marked = document.createElement("span");
    marked.className = "dict-word";
    try { range.surroundContents(marked); } catch (err) { marked = null; }
    lookup(word.replace(/[’'ʼ]+$/, "") || word, lang);
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
})();
