// Library page (library.html): continue reading, one shelf per original language (chips built from the
// data), that shelf's authors on the left, the chosen author's works on the right (grouped for authors
// with many works), and a finder across every shelf. Texts kept on
// this device (local.js) join the list through LibraryPage.setLocal.
(function () {
  var base = window.LIBRARY || [], works = base;
  var $ = function (id) { return document.getElementById(id); };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function fold(s) {
    return String(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ς/g, "σ")
      .toLowerCase().replace(/j/g, "i").replace(/v/g, "u");
  }
  function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  // a work's shelf is the language it was written in, whichever language the edition here is in
  var LANG_NAMES = { grc: "Greek", lat: "Latin", eng: "English", en: "English", it: "Italian", fr: "French",
    de: "German", es: "Spanish", pt: "Portuguese", ru: "Russian", zh: "Chinese", ja: "Japanese", el: "Modern Greek" };
  function langOf(w) { return w.orig || w.lang || "eng"; }
  function langName(l) { return LANG_NAMES[l] || l; }
  function langAttr(l) { return l === "lat" ? "la" : (l === "eng" ? "en" : (l || "en")); }

  // reading positions saved by the reader pages
  function position(page) {
    var raw = load("pos:" + page);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch (e) {
      var p = raw.split("|");                       // older format: id|key
      return { id: p[0], key: p[1], t: 0 };
    }
  }

  // ---- continue reading ----------------------------------------------------------
  function renderContinue() {
    var recent = [];
    works.forEach(function (w) {
      var p = position(w.href);
      if (p && p.t) recent.push({ w: w, p: p });
    });
    recent.sort(function (a, b) { return b.p.t - a.p.t; });
    $("continue-wrap").hidden = !recent.length;
    $("continue").innerHTML = recent.slice(0, 6).map(function (r) {
      return '<a href="' + esc(r.w.href) + "#" + esc(r.p.id) + '"><span class="c-au">' + esc(r.w.author) +
        '</span><span class="c-ti">' + esc(r.w.title) + '</span><span class="c-at">continue at ' +
        esc(r.p.key) + "</span></a>";
    }).join("");
  }

  // ---- authors -------------------------------------------------------------------
  var authors = {}, order = [];
  function index() {
    authors = {}; order = [];
    works.forEach(function (w) {
      var a = authors[w.author_id];
      if (!a) {
        a = authors[w.author_id] = { id: w.author_id, name: w.author, lang: langOf(w), works: [] };
        order.push(a);
      }
      a.works.push(w);
    });
    order.sort(function (a, b) { return fold(a.name) < fold(b.name) ? -1 : 1; });
  }
  renderContinue();
  index();

  var lang = null, current = null, shelves = [];

  // shelves, largest first; each shows how many works it holds
  function renderShelves() {
    var count = {};
    works.forEach(function (w) { var l = langOf(w); count[l] = (count[l] || 0) + 1; });
    shelves = Object.keys(count).sort(function (a, b) { return count[b] - count[a] || (langName(a) < langName(b) ? -1 : 1); });
    if (shelves.indexOf(lang) < 0) lang = shelves[0] || null;
    $("langs").innerHTML = shelves.map(function (l) {
      return '<button type="button" data-l="' + esc(l) + '" aria-pressed="' + (l === lang) + '">' + esc(langName(l)) +
        ' <span class="n">' + count[l] + "</span></button>";
    }).join("");
  }
  function setShelf(l) {
    lang = l;
    store("lib-lang", l);
    var all = $("langs").querySelectorAll("button");
    for (var i = 0; i < all.length; i++) all[i].setAttribute("aria-pressed", String(all[i].getAttribute("data-l") === l));
  }

  function renderAuthors(matching) {
    var html = [];
    shelves.forEach(function (l) {
      if (!matching && lang !== l) return;
      var list = order.filter(function (a) { return a.lang === l && (!matching || matching[a.id]); });
      if (!list.length) return;
      if (matching) html.push('<div class="lang-head">' + esc(langName(l)) + "</div>");
      list.forEach(function (a) {
        var n = matching ? matching[a.id] : a.works.length;
        html.push('<button type="button" data-a="' + esc(a.id) + '"' +
          (current === a.id && !matching ? ' aria-current="true"' : "") + '><span>' + esc(a.name) +
          '</span><span class="n">' + n + "</span></button>");
      });
    });
    $("authors").innerHTML = html.join("") || '<p class="empty">No authors match.</p>';
  }

  function workItem(w, showAuthor) {
    var p = position(w.href);
    var orig = w.label && w.label !== w.title
      ? '<span class="orig" lang="' + langAttr(w.lang) + '">' + esc(w.label) + "</span>" : "";
    var who = w.translations && w.translations.length
      ? '<span class="who">' + esc(w.translations.filter(Boolean).join(", ")) + "</span>" : "";
    var where = p ? '<a class="where" href="' + esc(w.href) + "#" + esc(p.id) + '">continue at ' + esc(p.key) + "</a>" : "";
    var au = showAuthor ? '<span class="au-tag">' + esc(w.author) + "</span>" : "";
    var dev = w.local ? '<span class="dev">on this device' + (w.uploads && w.uploads.length
      ? ' <button type="button" class="linkish" data-remove="' + esc(w.uploads.join("|")) + '" title="Remove from this browser">remove</button>'
      : "") + "</span>" : "";
    return '<li><a href="' + esc(w.href) + '">' + esc(w.title) + "</a>" + orig + au + who + dev + where + "</li>";
  }

  function renderAuthor(id) {
    var a = authors[id];
    if (!a) return;
    current = id;
    if (a.lang !== lang) setShelf(a.lang);
    store("lib-author", id);
    store("lib-author:" + a.lang, id);
    if (location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
    var groups = {}, gorder = [];
    a.works.forEach(function (w) {
      var g = w.group || "";
      if (!groups[g]) { groups[g] = []; gorder.push(g); }
      groups[g].push(w);
    });
    if (gorder.length > 1) {          // named groups first, in rule order; leftovers last
      gorder.sort(function (x, y) { return (x === "") - (y === ""); });
    }
    var html = ['<h2>' + esc(a.name) + "</h2>",
      '<p class="sub">' + a.works.length + " work" + (a.works.length === 1 ? "" : "s") + "</p>"];
    gorder.forEach(function (g) {
      if (gorder.length > 1) html.push("<h3>" + esc(g || "Other works") + "</h3>");
      html.push("<ul>" + groups[g].map(function (w) { return workItem(w, false); }).join("") + "</ul>");
    });
    $("works").innerHTML = html.join("");
    renderAuthors(null);
  }

  function renderFind(q) {
    var words = fold(q).split(/\s+/).filter(Boolean);
    var hits = works.filter(function (w) {
      var hay = fold(w.author + " " + w.title + " " + (w.label || "") + " " + (w.translations || []).join(" "));
      return words.every(function (x) { return hay.indexOf(x) >= 0; });
    });
    var counts = {};
    hits.forEach(function (w) { counts[w.author_id] = (counts[w.author_id] || 0) + 1; });
    renderAuthors(counts);
    $("works").innerHTML = hits.length
      ? "<h2>" + hits.length + " match" + (hits.length === 1 ? "" : "es") + "</h2><ul>" +
        hits.slice(0, 200).map(function (w) { return workItem(w, true); }).join("") + "</ul>"
      : '<p class="empty">Nothing in the library matches.</p>';
  }

  $("authors").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-a]");
    if (!b) return;
    $("find").value = "";
    renderAuthor(b.getAttribute("data-a"));
    if (window.innerWidth < 960) $("works").scrollIntoView({ block: "start" });
  });
  $("find").addEventListener("input", function () {
    var q = this.value.trim();
    if (q) renderFind(q); else renderAuthor(current || (order[0] && order[0].id));
  });
  // the author to show on a shelf: the one last opened there, else the first
  function firstOn(l) {
    var last = authors[load("lib-author:" + l)];
    if (last && last.lang === l) return last.id;
    var a = order.filter(function (x) { return x.lang === l; })[0];
    return a && a.id;
  }
  $("langs").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-l]");
    if (!b) return;
    setShelf(b.getAttribute("data-l"));
    $("find").value = "";
    renderAuthor(firstOn(lang));
  });

  function refreshView() {
    renderShelves();
    var q = $("find").value.trim();
    if (q) return renderFind(q);
    var keep = authors[current] && authors[current].lang === lang;
    var id = keep ? current : firstOn(lang);
    if (id) renderAuthor(id);
  }
  window.LibraryPage = {
    setLocal: function (list) {
      works = base.concat(list || []);
      renderContinue();
      index();
      refreshView();
    }
  };

  if (!order.length) {
    $("works").innerHTML = '<p class="empty">The library is empty.</p>';
    return;
  }
  lang = load("lib-lang");
  renderShelves();
  var start = location.hash.slice(1);
  renderAuthor(authors[start] ? start : (authors[load("lib-author")] && authors[load("lib-author")].lang === lang
    ? load("lib-author") : firstOn(lang)));
})();
