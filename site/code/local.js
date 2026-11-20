// Texts on this device: Markdown files (library format) kept in this browser only. Two sources:
// a linked folder (Chrome and Edge: the browser remembers it and re-reads it on each visit) and
// files added by hand or dropped on the library page (every browser). Nothing is uploaded.
// On library.html this adds the "On this device" bar and lists the texts under their authors;
// on local.html it parses and renders one text, the same way reader/build.py does for the site.
(function () {
  "use strict";

  // ---- storage (IndexedDB): files {path, source, name, text, mtime}; kv {folder handle} ------
  var DB_NAME = "mandate-local";
  var dbp = null;
  function db() {
    if (dbp) return dbp;
    dbp = new Promise(function (res, rej) {
      if (!window.indexedDB) return rej(new Error("no IndexedDB"));
      var r = indexedDB.open(DB_NAME, 1);
      r.onupgradeneeded = function () {
        r.result.createObjectStore("files", { keyPath: "path" });
        r.result.createObjectStore("kv");
      };
      r.onsuccess = function () { res(r.result); };
      r.onerror = function () { rej(r.error); };
    });
    return dbp;
  }
  function req(store, mode, fn) {
    return db().then(function (d) {
      return new Promise(function (res, rej) {
        var t = d.transaction(store, mode), s = t.objectStore(store), out = fn(s);
        t.oncomplete = function () { res(out && "result" in out ? out.result : undefined); };
        t.onerror = function () { rej(t.error); };
        t.onabort = function () { rej(t.error); };
      });
    });
  }
  var store = {
    all: function () { return req("files", "readonly", function (s) { return s.getAll(); }); },
    put: function (f) { return req("files", "readwrite", function (s) { s.put(f); }); },
    del: function (path) { return req("files", "readwrite", function (s) { s.delete(path); }); },
    clear: function (source) {
      return store.all().then(function (all) {
        return req("files", "readwrite", function (s) {
          all.forEach(function (f) { if (f.source === source) s.delete(f.path); });
        });
      });
    },
    get: function (k) { return req("kv", "readonly", function (s) { return s.get(k); }); },
    set: function (k, v) { return req("kv", "readwrite", function (s) { s.put(v, k); }); },
    unset: function (k) { return req("kv", "readwrite", function (s) { s.delete(k); }); }
  };

  // ---- parsing (port of reader/library.py) -----------------------------------------------
  function escText(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function esc(s) { return escText(s == null ? "" : s).replace(/"/g, "&quot;").replace(/'/g, "&#x27;"); }
  function inline(t) {
    t = escText(t);
    t = t.replace(/\*([^*\n]+)\*/g, "<i>$1</i>");
    t = t.replace(/\[\^([^\]]+)\]/g, '<sup class="fn" data-note="$1"></sup>');
    return t;
  }
  function unescapeStart(line) { return line.charAt(0) === "\\" ? line.slice(1) : line; }
  function splitLines(s) {          // like Python's splitlines: no empty item after a final newline
    var a = s.split(/\r\n|\r|\n/);
    if (a.length && a[a.length - 1] === "") a.pop();
    return a;
  }

  function frontMatter(raw) {
    var meta = {}, body = raw;
    if (raw.slice(0, 3) === "---") {
      var end = raw.indexOf("\n---", 3);
      if (end > 0) {
        splitLines(raw.slice(3, end).trim()).forEach(function (line) {
          var i = line.indexOf(":");
          if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim();
        });
        body = raw.slice(end + 4);
      }
    }
    return { meta: meta, body: body };
  }

  // a file without front matter still opens: its name becomes the work and the title
  function withDefaults(meta, name) {
    var stem = String(name || "text").replace(/^.*[\\/]/, "").replace(/\.(md|markdown|txt)$/i, "");
    meta.id = meta.id || stem;
    meta.work = meta.work || stem;
    meta.title = meta.title || stem.replace(/[._-]+/g, " ");
    meta.author = meta.author || "Unknown author";
    meta.language = meta.language || "eng";
    return meta;
  }

  function parse(raw, name) {
    raw = raw.normalize("NFC").replace(/^﻿/, "");
    var fm = frontMatter(raw), meta = withDefaults(fm.meta, name);
    var layout = meta.layout || "prose", numbering = meta.numbering || "explicit";
    var notes = {}, lines = [], front = [], fblock = null;
    splitLines(fm.body).forEach(function (line) {
      var m = /^\[\^([^\]]+)\]:\s*(.*)$/.exec(line), st = line.trim();
      if (st.slice(0, 3) === ":::") {         // ::: Title ... ::: front matter (see reader/library.py)
        if (!fblock) { fblock = [st.slice(3).trim() || "Introduction", []]; front.push(fblock); }
        else fblock = null;
        return;
      }
      if (fblock && !m) { fblock[1].push(line); return; }
      if (m) notes[m[1]] = inline(m[2]);
      else lines.push(line.replace(/\s+$/, ""));
    });
    var events = [], para = [], sectionNo = 0, lineNo = 0;
    function last() { return events[events.length - 1]; }
    function flush() {
      if (!para.length) return;
      var text = para.map(function (p) { return p.trim(); }).join(" ");
      para = [];
      if (events.length && ["pb", "h2", "h3", "spk", "stage"].indexOf(last()[0]) < 0) events.push(["pb"]);
      var re = /\{\{([^}]+)\}\}/g, pos = 0, m;
      while ((m = re.exec(text))) {
        var chunk = text.slice(pos, m.index);
        if (chunk.trim()) events.push(["text", inline(chunk)]);
        events.push(["key", m[1].trim()]);
        pos = m.index + m[0].length;
      }
      if (text.slice(pos).trim()) events.push(["text", inline(text.slice(pos))]);
    }
    lines.forEach(function (line) {
      var s = line.trim();
      if (!s) {
        flush();
        if (layout === "verse" && events.length && last()[0] === "line") events.push(["pb"]);
        return;
      }
      if (s.slice(0, 3) === "## ") { flush(); sectionNo++; lineNo = 0; events.push(["h2", inline(s.slice(3).trim())]); }
      else if (s.slice(0, 4) === "### ") { flush(); events.push(["h3", inline(s.slice(4).trim())]); }
      else if (/^\*\*[^*]+\*\*$/.test(s)) { flush(); events.push(["spk", inline(s.slice(2, -2))]); }
      else if (/^\*\(.*\)\*$/.test(s)) { flush(); events.push(["stage", inline(s.slice(2, -2))]); }
      else if (s === "{{gap}}") { flush(); events.push(["gap"]); }
      else if (s.slice(0, 2) === "> ") {
        if (layout === "prose") { flush(); events.push(["bq", inline(s.slice(2))]); }
        else events.push(["line", null, inline(s.slice(2))]);
      } else if (layout === "verse" && s.slice(0, 2) === "¶ ") {
        flush(); events.push(["pb"]); events.push(["text", inline(s.slice(2).trim())]); events.push(["pb"]);
      } else if (layout === "verse") {
        s = unescapeStart(s);
        var m = /^\{\{([^}]+)\}\}\s*/.exec(s), key = null;
        if (m) {
          key = m[1].trim();
          s = s.slice(m[0].length);
          if (key === "+") key = null;
          else if (/^\d+$/.test(key)) lineNo = parseInt(key, 10);
        } else if (numbering.slice(0, 4) === "auto") {
          lineNo++; key = String(lineNo);
        }
        if (key && numbering === "auto-by-section" && key.indexOf(".") < 0) key = sectionNo + "." + key;
        events.push(["line", key, inline(s)]);
      } else para.push(unescapeStart(s));
    });
    flush();
    meta._front = front.map(function (b) { return [inline(b[0]), frontParagraphs(b[1])]; });
    return { meta: meta, events: events, notes: notes };
  }
  function frontParagraphs(lines) {
    var out = [], cur = [];
    lines.concat([""]).forEach(function (line) {
      var s = line.trim();
      if (s.slice(0, 2) === "¶ ") {
        if (cur.length) { out.push(cur.join(" ")); cur = []; }
        out.push(unescapeStart(s.slice(2).trim()));
      } else if (s) cur.push(unescapeStart(s));
      else if (cur.length) { out.push(cur.join(" ")); cur = []; }
    });
    return out.map(inline);
  }

  // ---- alignment and rendering (port of reader/build.py) ---------------------------------
  var STRUCT = { h2: 1, h3: 1, spk: 1, stage: 1, pb: 1 };
  var GROUP_MIN = 250, GROUP_MAX = 1600;
  var ORIGINAL = { grc: 1, lat: 1 };
  var LANG_NAMES = { grc: "Greek", lat: "Latin", eng: "English" };
  var HTML_LANG = { grc: "grc", lat: "la", eng: "en" };

  function lastPart(k) { var i = k.lastIndexOf("."); return i < 0 ? k : k.slice(i + 1); }
  function textLen(evs) {
    var n = 0;
    evs.forEach(function (e) {
      if (e[0] === "text" || e[0] === "bq") n += e[1].length;
      else if (e[0] === "line") n += e[2].length;
    });
    return n;
  }
  function keyOf(e) { return (e[0] === "key" || e[0] === "line") ? e[1] : null; }
  function bisectLeft(a, x) { var lo = 0, hi = a.length; while (lo < hi) { var m = (lo + hi) >> 1; if (a[m] < x) lo = m + 1; else hi = m; } return lo; }
  function bisectRight(a, x) { var lo = 0, hi = a.length; while (lo < hi) { var m = (lo + hi) >> 1; if (x < a[m]) hi = m; else lo = m + 1; } return lo; }

  function sharedKeys(left, right) {
    var rfirst = {}, pairs = [], seen = {};
    right.forEach(function (e, i) { var k = keyOf(e); if (k && !(k in rfirst)) rfirst[k] = i; });
    left.forEach(function (e, i) {
      var k = keyOf(e);
      if (k && (k in rfirst) && !seen[k]) { seen[k] = 1; pairs.push([i, rfirst[k], k]); }
    });
    var tails = [], tailsIdx = [], prev = [];
    pairs.forEach(function (p, j) {
      var q = bisectLeft(tails, p[1]);
      if (q === tails.length) { tails.push(p[1]); tailsIdx.push(j); } else { tails[q] = p[1]; tailsIdx[q] = j; }
      prev[j] = q ? tailsIdx[q - 1] : null;
    });
    var out = [], j = tailsIdx.length ? tailsIdx[tailsIdx.length - 1] : null;
    while (j !== null && j !== undefined) { out.push(pairs[j]); j = prev[j]; }
    return out.reverse();
  }
  function backOverStruct(evs, pos, floor) {
    while (pos > floor && STRUCT[evs[pos - 1][0]]) pos--;
    return pos;
  }
  function splitSingle(evs) {
    var out = [], cur = [];
    evs.forEach(function (e) {
      if ((e[0] === "h2" || e[0] === "h3" || e[0] === "spk") && cur.length &&
          cur.some(function (x) { return !STRUCT[x[0]]; })) { out.push(cur); cur = []; }
      if (e[0] === "pb" && textLen(cur) > GROUP_MAX) { out.push(cur); cur = []; }
      cur.push(e);
    });
    if (cur.length) out.push(cur);
    return out;
  }
  function chunk(left, right) {
    if (!right) return { chunks: splitSingle(left).map(function (c) { return [c, []]; }), shared: 0 };
    var pairs = sharedKeys(left, right), bounds = [[0, 0]];
    pairs.forEach(function (p) {
      var b = bounds[bounds.length - 1];
      var lp = backOverStruct(left, p[0], b[0]), rp = backOverStruct(right, p[1], b[1]);
      if (lp <= b[0]) lp = p[0];
      if (rp <= b[1]) rp = p[1];
      if (lp > b[0] && rp > b[1]) bounds.push([lp, rp]);
    });
    bounds.push([left.length, right.length]);
    var chunks = [];
    for (var i = 0; i + 1 < bounds.length; i++) {
      chunks.push([left.slice(bounds[i][0], bounds[i + 1][0]), right.slice(bounds[i][1], bounds[i + 1][1])]);
    }
    return { chunks: chunks, shared: pairs.length };
  }
  function sectionsAndGroups(chunks) {
    var sections = [], cur = { title: null, groups: [] }, group = [], glen = 0;
    chunks.forEach(function (ch) {
      var l = ch[0].slice(), r = ch[1].slice();
      var lead = l.slice(0, 4).filter(function (e) { return e[0] === "h2"; });
      if (lead.length) {
        if (group.length) cur.groups.push(group);
        if (cur.groups.length || cur.title) sections.push(cur);
        l.splice(l.indexOf(lead[0]), 1);
        r = r.filter(function (e, i) { return !(e[0] === "h2" && i < 4); });
        cur = { title: lead[0][1], groups: [] };
        group = []; glen = 0;
      }
      var startsBlock = l.length && ["h3", "spk", "stage", "pb"].indexOf(l[0][0]) >= 0;
      if (group.length && ((startsBlock && glen >= GROUP_MIN) || glen >= GROUP_MAX)) {
        cur.groups.push(group); group = []; glen = 0;
      }
      group.push([l, r]);
      glen += textLen(l);
    });
    if (group.length) cur.groups.push(group);
    if (cur.groups.length || cur.title) sections.push(cur);
    return sections;
  }

  // verse translations that number their own lines
  function splitKey(k) { var i = k.lastIndexOf("."); return i < 0 ? ["", k] : [k.slice(0, i), k.slice(i + 1)]; }
  function verseLines(evs) {
    var nums = {}, turns = {}, afterSpk = false;
    evs.forEach(function (e) {
      if (e[0] === "spk") afterSpk = true;
      else if (e[0] === "line" && e[1]) {
        var pn = splitKey(e[1]);
        if (/^\d+$/.test(pn[1])) {
          (nums[pn[0]] = nums[pn[0]] || []).push(+pn[1]);
          if (afterSpk) (turns[pn[0]] = turns[pn[0]] || []).push(+pn[1]);
        }
        afterSpk = false;
      }
    });
    for (var p in nums) {
      nums[p] = nums[p].filter(function (v, i, a) { return a.indexOf(v) === i; }).sort(function (a, b) { return a - b; });
    }
    return [nums, turns];
  }
  function ownLineation(left, right, lmeta, rmeta) {
    if (lmeta.layout !== "verse" || rmeta.layout !== "verse") return false;
    var ln = verseLines(left)[0], rn = verseLines(right)[0];
    var common = Object.keys(ln).filter(function (p) { return rn[p] && ln[p].length && rn[p].length; });
    if (!common.length) return false;
    var off = common.filter(function (p) {
      var a = ln[p][ln[p].length - 1], b = rn[p][rn[p].length - 1];
      return Math.abs(b - a) > Math.max(3, 0.03 * a);
    }).length;
    return off > common.length / 3;
  }
  function pyRound(x) {             // Python's round(): halves go to the even neighbour
    var f = Math.floor(x), d = x - f;
    return d > 0.5 ? f + 1 : d < 0.5 ? f : (f % 2 === 0 ? f : f + 1);
  }
  function remapTranslation(left, right) {
    var L = verseLines(left), R = verseLines(right), maps = {};
    Object.keys(R[0]).forEach(function (p) {
      var rn = R[0][p], ln = L[0][p];
      if (!ln) return;
      var anchors = [[rn[0], ln[0]]];
      var lt = L[1][p] || [], rt = R[1][p] || [];
      if (lt.length === rt.length) rt.forEach(function (x, i) { anchors.push([x, lt[i]]); });
      anchors.push([rn[rn.length - 1], ln[ln.length - 1]]);
      anchors.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
      var clean = [anchors[0]];
      anchors.slice(1).forEach(function (a) {
        var c = clean[clean.length - 1];
        if (a[0] > c[0] && a[1] >= c[1]) clean.push(a);
      });
      maps[p] = [clean, ln];
    });
    function mapped(p, n) {
      var anchors = maps[p][0], ln = maps[p][1], target;
      if (anchors.length === 1) target = anchors[0][1];
      else {
        var xs = anchors.map(function (a) { return a[0]; });
        var i = Math.max(0, Math.min(bisectRight(xs, n) - 1, anchors.length - 2));
        var x0 = anchors[i][0], y0 = anchors[i][1], x1 = anchors[i + 1][0], y1 = anchors[i + 1][1];
        target = x1 !== x0 ? y0 + (n - x0) * (y1 - y0) / (x1 - x0) : y0;
      }
      return ln[Math.min(bisectLeft(ln, pyRound(target)), ln.length - 1)];
    }
    return right.map(function (e) {
      if (e[0] === "line" && e[1]) {
        var pn = splitKey(e[1]);
        if (maps[pn[0]] && /^\d+$/.test(pn[1])) {
          var m = mapped(pn[0], +pn[1]);
          return ["line", pn[0] ? pn[0] + "." + m : String(m), e[2], e[1]];
        }
      }
      return e;
    });
  }

  function Side(prefix, layout, notes) {
    this.prefix = prefix; this.layout = layout; this.notes = notes;
    this.ids = {}; this.pending = []; this.n = 0; this.fn = 0;
  }
  Side.prototype.anchor = function (key) {
    var i = this.prefix + key;
    if (this.ids[i]) return "";
    this.ids[i] = 1;
    return ' id="' + esc(i) + '"';
  };
  Side.prototype.fillNotes = function (s) {
    var self = this;
    return s.replace(/<sup class="fn" data-note="([^"]+)"><\/sup>/g, function (_, nid) {
      if (!(nid in self.notes)) return "";
      self.n++;
      var app = nid.charAt(0) === "a", ref = self.prefix + "n" + self.n;
      if (!app) self.fn++;
      var mark = app ? "°" : String(self.fn);
      self.pending.push([ref, nid, app, mark]);
      return '<sup class="' + (app ? "fn app" : "fn") + '"><a href="#' + ref + '" id="r' + ref + '">' + mark + "</a></sup>";
    });
  };
  Side.prototype.render = function (evs) {
    var self = this, out = [];
    evs.forEach(function (e) {
      var t = e[0];
      if (t === "line") {
        if (e[1]) {
          var lp = lastPart(e.length > 3 ? e[3] : e[1]);
          var cls = /^\d+$/.test(lp) && +lp % 5 === 0 ? "ln n5" : "ln";
          out.push('<span class="v" data-k="' + esc(e[1]) + '"' + self.anchor(e[1]) + '><span class="' + cls + '">' +
            esc(lp) + "</span>" + self.fillNotes(e[2]) + "</span>");
        } else out.push('<span class="v">' + self.fillNotes(e[2]) + "</span>");
      } else if (t === "key") {
        out.push('<span class="mk" data-k="' + esc(e[1]) + '"' + self.anchor(e[1]) + ">" + esc(lastPart(e[1])) + "</span>");
      } else if (t === "text") out.push(self.fillNotes(e[1]));
      else if (t === "pb") out.push('<span class="pb"></span>');
      else if (t === "spk") out.push('<span class="spk">' + e[1] + "</span>");
      else if (t === "stage") out.push('<span class="stage">' + e[1] + "</span>");
      else if (t === "h2" || t === "h3") out.push('<span class="sub">' + e[1] + "</span>");
      else if (t === "bq") out.push('<span class="bq">' + self.fillNotes(e[1]) + "</span>");
      else if (t === "gap") out.push('<span class="gap">…</span>');
    });
    return out.join("");
  };
  Side.prototype.notesHtml = function (row) {
    if (!this.pending.length) return "";
    var self = this;
    var items = this.pending.map(function (p) {
      return "<li" + (p[2] ? ' class="app"' : "") + ' id="' + p[0] + '"><a class="back" href="#r' + p[0] +
        '" title="back to the text">' + p[3] + "</a>" + self.notes[p[1]] + "</li>";
    });
    this.pending = [];
    return '<ol class="notes" style="--r:' + row + '">' + items.join("") + "</ol>";
  };
  function firstKey(evs) { for (var i = 0; i < evs.length; i++) { var k = keyOf(evs[i]); if (k) return k; } return null; }
  function lastKey(evs) { for (var i = evs.length - 1; i >= 0; i--) { var k = keyOf(evs[i]); if (k) return k; } return null; }

  var CAST_TITLES = ["characters", "cast", "dramatis personae", "persons of the drama", "persons of the play"];
  function frontHtml(side, meta, cls, lang) {
    return '<div class="col ' + cls + '" lang="' + lang + '">' + (meta._front || []).map(function (f, i) {
      var cast = CAST_TITLES.indexOf(f[0].replace(/<[^>]+>/g, "").trim().toLowerCase()) >= 0;
      var body = f[1].map(function (p) { return "<p>" + side.fillNotes(p) + "</p>"; }).join("");
      return '<details class="fm' + (cast ? " cast" : "") + '" id="' + side.prefix + "fm" + (i + 1) + '"' + (cast ? " open" : "") +
        "><summary>" + f[0] + "</summary>" + body + side.notesHtml(1) + "</details>";
    }).join("") + "</div>";
  }
  function frontSection(cols, toc) {
    if (!cols.some(function (c) { return (c[1]._front || []).length; })) return "";
    cols.forEach(function (c) {
      var who = (c[1].edition || "").split(/\s+/).filter(Boolean);
      (c[1]._front || []).forEach(function (f, i) {
        toc.push('<li class="fm"><a href="#' + c[0].prefix + "fm" + (i + 1) + '"><span class="t">' + f[0] +
          '</span><span class="r">' + esc(who.length ? who[who.length - 1] : "") + "</span></a></li>");
      });
    });
    return '<section class="front"><div class="grp' + (cols.length === 1 ? " single" : "") + '">' +
      cols.map(function (c) { return frontHtml(c[0], c[1], c[2], c[3]); }).join("") + "</div></section>";
  }

  function renderPage(orig, trans) {
    var two = !!trans, levents = orig.events, revents = two ? trans.events : null;
    if (two && ownLineation(levents, revents, orig.meta, trans.meta)) revents = remapTranslation(levents, revents);
    var sections = sectionsAndGroups(chunk(levents, revents).chunks);
    var L = new Side("L", orig.meta.layout || "prose", orig.notes);
    var R = two ? new Side("E", trans.meta.layout || "prose", trans.notes) : null;
    var llang = HTML_LANG[orig.meta.language] || orig.meta.language || "en", rlang = two ? (HTML_LANG[trans.meta.language] || trans.meta.language || "en") : "en";
    var body = [], toc = [];
    var fcols = [[L, orig.meta, "g " + L.layout, llang]];
    if (two) fcols.push([R, trans.meta, "e " + R.layout, rlang]);
    body.push(frontSection(fcols, toc));
    sections.forEach(function (sec, si) {
      var all = [];
      sec.groups.forEach(function (g) { g.forEach(function (c) { all = all.concat(c[0]); }); });
      var k0 = firstKey(all), k1 = lastKey(all);
      var rng = k0 && k1 && k0 !== k1 ? lastPart(k0) + "–" + lastPart(k1) : (k0 ? lastPart(k0) : "");
      var sid = "s" + (si + 1);
      if (sec.title) toc.push('<li><a href="#' + sid + '"><span class="t">' + sec.title + '</span><span class="r">' + esc(rng) + "</span></a></li>");
      var head = sec.title ? '<h2><span class="t">' + sec.title + '</span><span class="r">' + esc(rng) + "</span></h2>" : "";
      var groups = sec.groups.map(function (g) {
        var lh = [], rh = [];
        g.forEach(function (c, i) {
          var r = i + 1;
          lh.push('<div class="ch" style="--r:' + r + '">' + L.render(c[0]) + "</div>");
          if (two) {
            var inner = R.render(c[1]);
            if (textLen(c[0]) === 0 && textLen(c[1]) > 600) {
              var ft = c[1].findIndex(function (e) { return e[0] === "text"; });
              var heads = c[1].slice(0, ft < 0 ? c[1].length : ft).filter(function (e) { return e[0] === "h3"; });
              var label = heads.length ? heads[heads.length - 1][1].replace(/\.+$/, "") : "Translator’s introduction";
              inner = '<details class="aside"><summary>' + label + "</summary>" + inner + "</details>";
            }
            rh.push('<div class="ch" style="--r:' + r + '">' + inner + "</div>");
          }
        });
        var lastRow = g.length + 1;
        var lcls = 'col g ' + L.layout + '" lang="' + llang;
        var lnote = L.notesHtml(lastRow).replace('class="notes"', 'class="notes left"');
        if (two) {
          return '<div class="grp"><div class="' + lcls + '">' + lh.join("") + lnote + '</div><div class="col e ' +
            R.layout + '" lang="' + rlang + '">' + rh.join("") + R.notesHtml(lastRow) + "</div></div>";
        }
        return '<div class="grp single"><div class="' + lcls + '">' + lh.join("") + lnote + "</div></div>";
      });
      body.push('<section class="sec" id="' + sid + '">' + head + groups.join("") + "</section>");
    });
    var hasApp = Object.keys(orig.notes).some(function (k) { return k.charAt(0) === "a"; });
    return { html: body.join(""), toc: toc, hasApp: hasApp, two: two };
  }

  // ---- works on this device ---------------------------------------------------------------
  function slug(s) {
    return String(s).normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase()
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "x";
  }
  function metaOf(f) { return withDefaults(frontMatter(f.text.normalize("NFC")).meta, f.name); }
  function byWork(files) {
    var works = {}, order = [];
    files.forEach(function (f) {
      var m = metaOf(f);
      if (!works[m.work]) { works[m.work] = []; order.push(m.work); }
      works[m.work].push({ file: f, meta: m });
    });
    return order.map(function (w) {
      var docs = works[w];
      var sortId = function (a, b) { return a.meta.id < b.meta.id ? -1 : 1; };
      var originals = docs.filter(function (d) { return ORIGINAL[d.meta.language]; }).sort(sortId);
      var translations = docs.filter(function (d) { return !ORIGINAL[d.meta.language]; }).sort(sortId);
      if (!originals.length) { originals = translations.slice(0, 1); translations = translations.slice(1); }
      return { work: w, originals: originals, translations: translations };
    });
  }
  function href(work, o, t) {
    return "local.html?w=" + encodeURIComponent(work) + (o || t ? "&o=" + (o || 0) + "&t=" + (t || 0) : "");
  }
  // entries in the shape library.js uses for the library list
  function entries(files, library) {
    var ids = {};
    (library || []).forEach(function (e) { if (!e.local) ids[e.author] = e.author_id; });
    return byWork(files).map(function (w) {
      var m = w.originals[0].meta;
      return {
        work: w.work, author: m.author, author_id: ids[m.author] || "local-" + slug(m.author),
        title: m.title, label: m.label || "", href: href(w.work),
        translations: w.translations.map(function (d) { return d.meta.edition || d.meta.label || ""; }),
        lang: m.language, orig: m.original || m.language, local: true,
        uploads: w.originals.concat(w.translations).filter(function (d) { return d.file.source === "upload"; })
          .map(function (d) { return d.file.path; })
      };
    });
  }

  // ---- linked folder (File System Access API) ------------------------------------------------
  var canLink = typeof window.showDirectoryPicker === "function";
  function isText(name) {
    return /\.(md|markdown)$/i.test(name) && !/^[_.]/.test(name) && name.toUpperCase() !== "README.MD";
  }
  async function readFolder(dir) {
    var found = [];
    async function walk(h, prefix) {
      for await (var entry of h.values()) {
        if (entry.kind === "directory") { if (!/^[_.]/.test(entry.name)) await walk(entry, prefix + entry.name + "/"); }
        else if (isText(entry.name)) {
          var file = await entry.getFile();
          found.push({ path: "folder:" + prefix + entry.name, source: "folder", name: entry.name,
            text: await file.text(), mtime: file.lastModified });
        }
      }
    }
    await walk(dir, "");
    await store.clear("folder");
    for (var i = 0; i < found.length; i++) await store.put(found[i]);
    return found.length;
  }
  async function folderState() {
    var h = await store.get("folder").catch(function () { return null; });
    if (!h) return { handle: null, state: "none" };
    var state = h.queryPermission ? await h.queryPermission({ mode: "read" }) : "granted";
    return { handle: h, state: state };
  }
  async function linkFolder() {
    var h = await window.showDirectoryPicker({ id: "mandate-texts", mode: "read" });
    await store.set("folder", h);
    return readFolder(h);
  }
  async function reconnect(h) {
    var s = await h.requestPermission({ mode: "read" });
    if (s !== "granted") throw new Error("Permission was not given.");
    return readFolder(h);
  }
  async function unlink() { await store.unset("folder"); await store.clear("folder"); }
  async function addFiles(list) {
    var n = 0;
    for (var i = 0; i < list.length; i++) {
      var f = list[i];
      if (!/\.(md|markdown|txt)$/i.test(f.name)) continue;
      await store.put({ path: "upload:" + f.name, source: "upload", name: f.name, text: await f.text(), mtime: f.lastModified });
      n++;
    }
    return n;
  }

  window.LocalTexts = { parse: parse, renderPage: renderPage, entries: entries, all: store.all };

  // ---- library page: the "On this device" bar --------------------------------------------------
  function libraryPage() {
    var bar = document.getElementById("local");
    if (!window.indexedDB) return;
    if (!bar) {          // the library page: texts kept on this device simply join the list
      if (window.LibraryPage) store.all().then(function (files) {
        window.LibraryPage.setLocal(entries(files, window.LIBRARY));
      }).catch(function () {});
      return;
    }
    var status = document.getElementById("local-status");
    var linkBtn = document.getElementById("local-link");
    var input = document.getElementById("local-files");
    bar.hidden = false;
    if (!canLink) linkBtn.hidden = true;

    async function refresh(note) {
      var files = await store.all().catch(function () { return []; });
      var fs = await folderState();
      var nFolder = files.filter(function (f) { return f.source === "folder"; }).length;
      var nUp = files.length - nFolder;
      var parts = [];
      if (fs.handle) {
        parts.push("Folder <b>" + esc(fs.handle.name) + "</b>: " + nFolder + " file" + (nFolder === 1 ? "" : "s"));
        if (fs.state === "granted") parts.push('<button type="button" class="linkish" data-act="reread">Re-read</button>');
        else parts.push('<button type="button" class="linkish" data-act="reconnect">Reconnect to see changes</button>');
        parts.push('<button type="button" class="linkish" data-act="unlink">Unlink</button>');
        linkBtn.textContent = "Link a different folder";
      } else linkBtn.textContent = "Link a folder";
      if (nUp) parts.push(nUp + " added file" + (nUp === 1 ? "" : "s"));
      if (!fs.handle && !nUp) parts.push("Nothing yet.");
      if (note) parts.push('<span class="note">' + esc(note) + "</span>");
      status.innerHTML = parts.join(" · ");
      if (window.LibraryPage) window.LibraryPage.setLocal(entries(files, window.LIBRARY));
    }
    async function act(fn, done) {
      try { await fn(); await refresh(done || ""); }
      catch (e) { if (e && e.name !== "AbortError") await refresh(e.message || String(e)); }
    }
    linkBtn.addEventListener("click", function () {
      act(async function () { var n = await linkFolder(); return n; }, "Folder linked.");
    });
    input.addEventListener("change", function () {
      var files = Array.prototype.slice.call(input.files);
      act(function () { return addFiles(files); }, "Added.");
      input.value = "";
    });
    status.addEventListener("click", async function (e) {
      var b = e.target.closest("[data-act]");
      if (!b) return;
      var a = b.getAttribute("data-act"), fs = await folderState();
      if (a === "reread" && fs.handle) act(function () { return readFolder(fs.handle); }, "Re-read.");
      if (a === "reconnect" && fs.handle) act(function () { return reconnect(fs.handle); }, "Reconnected.");
      if (a === "unlink") act(unlink, "Folder unlinked; its files are untouched.");
    });
    document.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-remove]");
      if (!b) return;
      var paths = b.getAttribute("data-remove").split("|");
      act(async function () { for (var i = 0; i < paths.length; i++) await store.del(paths[i]); }, "Removed.");
    });
    // drop .md files anywhere on the page
    document.addEventListener("dragover", function (e) {
      if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, "Files") >= 0) {
        e.preventDefault(); document.body.classList.add("dropping");
      }
    });
    document.addEventListener("dragleave", function (e) {
      if (!e.relatedTarget) document.body.classList.remove("dropping");
    });
    document.addEventListener("drop", function (e) {
      document.body.classList.remove("dropping");
      if (!e.dataTransfer || !e.dataTransfer.files.length) return;
      e.preventDefault();
      var files = Array.prototype.slice.call(e.dataTransfer.files);
      act(function () { return addFiles(files); }, "Added.");
    });
    // the folder is re-read on each visit when the browser still allows it without asking
    folderState().then(function (fs) {
      if (fs.handle && fs.state === "granted") act(function () { return readFolder(fs.handle); });
      else refresh();
    });
  }

  // ---- local.html: render one text -------------------------------------------------------------
  function editionHead(meta, others, current, kind) {
    var lang = LANG_NAMES[meta.language] || meta.language || "";
    if (others.length > 1) {
      return "<div><b>" + esc(lang) + '</b> <select class="pick" aria-label="' + kind + '">' + others.map(function (o) {
        return '<option value="' + esc(o[1]) + '"' + (o[1] === current ? " selected" : "") + ">" +
          esc(o[0].edition || o[0].label || o[0].id) + "</option>";
      }).join("") + "</select></div>";
    }
    return "<div><b>" + esc(lang) + "</b> " + esc(meta.edition || meta.label || "") + "</div>";
  }
  function loadScripts(list) {
    list.forEach(function (src) {
      var s = document.createElement("script");
      s.src = src; s.async = false;
      document.body.appendChild(s);
    });
  }
  async function localPage() {
    var main = document.querySelector("main");
    function fail(msg) {
      main.innerHTML = '<p class="empty">' + msg + ' <a href="library.html">Back to the library</a>.</p>';
    }
    var q = new URLSearchParams(location.search), wid = q.get("w");
    var oi = parseInt(q.get("o") || "0", 10) || 0, ti = parseInt(q.get("t") || "0", 10) || 0;
    var files;
    try { files = await store.all(); } catch (e) { return fail("This browser keeps no texts on this device."); }
    var w = byWork(files).filter(function (x) { return x.work === wid; })[0];
    if (!w) return fail("That text is not on this device (it may have been removed, or added in another browser).");
    var o = w.originals[oi] || w.originals[0], t = w.translations.length ? (w.translations[ti] || w.translations[0]) : null;
    var orig = parse(o.file.text, o.file.name), trans = t ? parse(t.file.text, t.file.name) : null;
    var page = renderPage(orig, trans), here = href(wid, oi, ti);
    var m = orig.meta;
    document.title = m.title + " — " + m.author;
    var body = document.body;
    body.setAttribute("data-page", href(wid));
    body.setAttribute("data-title", m.title);
    body.setAttribute("data-author", m.author);
    body.setAttribute("data-lang", m.language);
    document.querySelector(".bar .au").textContent = m.author;
    document.querySelector(".bar .wk").textContent = m.title;
    var tools = [];
    if (page.two) tools.push('<div class="seg" role="group" aria-label="Alignment"><button type="button" data-mode="speech">Blocks</button><button type="button" data-mode="tight">Lines</button></div>');
    if (page.hasApp) tools.push('<button type="button" class="tog" id="apptog" aria-pressed="false">Apparatus</button>');
    tools.push('<form class="jump"><label for="jump">Go to</label><input id="jump" autocomplete="off" placeholder="1.150"></form>');
    tools.push('<button type="button" class="icon-btn" data-settings aria-expanded="false" aria-controls="settings" title="Settings (,)">Settings</button>');
    document.querySelector(".bar .tools").innerHTML = tools.join("");
    var lhead = editionHead(orig.meta, w.originals.map(function (d, i) { return [d.meta, href(wid, i, ti)]; }), here, "Original edition");
    var rhead = trans ? editionHead(trans.meta, w.translations.map(function (d, i) { return [d.meta, href(wid, oi, i)]; }), here, "Translation") : "";
    var layout = document.querySelector(".layout");
    layout.className = page.toc.length ? "layout" : "layout notoc";
    layout.innerHTML = (page.toc.length ? '<nav class="toc"><details open><summary>Contents</summary><ol>' + page.toc.join("") + "</ol></details></nav>" : "") +
      '<main><div class="' + (page.two ? "heads" : "heads one") + '">' + lhead + rhead + "</div>" + page.html + "</main>";
    // settings.js wired its buttons on DOMContentLoaded, before this one existed
    var sb = document.querySelector(".bar [data-settings]");
    if (sb && window.ReaderSettings) sb.addEventListener("click", function () { window.ReaderSettings.open(); });
    if (location.hash) {
      var target = document.getElementById(location.hash.slice(1));
      if (target) target.scrollIntoView();
    }
    loadScripts(["reader.js", "work_pages.js", "dict.js"]);
  }

  if (document.body.classList.contains("local-page")) localPage();
  else libraryPage();
})();
