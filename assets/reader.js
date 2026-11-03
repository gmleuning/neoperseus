// Library reader page: alignment switch (keeps your place), jump to a number, edition picker,
// apparatus toggle, reading position for the index, and highlighting of search hits.
(function () {
  var body = document.body;
  var S = window.ReaderSettings;
  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

  var buttons = document.querySelectorAll(".seg button");
  var pageKey = body.getAttribute("data-page");

  function headerBottom() {
    var top = (document.querySelector(".bar") || {}).offsetHeight || 0;
    var heads = document.querySelector(".heads");
    if (heads && getComputedStyle(heads).display !== "none") top += heads.offsetHeight;
    return top;
  }

  // the first numbered line or marker visible under the sticky headers; the original column
  // is the reference unless only the translation is shown
  function anchor() {
    var top = headerBottom();
    var transOnly = document.documentElement.classList.contains("cols-trans");
    var items = document.querySelectorAll(transOnly ? ".col.e [data-k][id]" : ".col.g [data-k][id]");
    for (var i = 0; i < items.length; i++) {
      var r = items[i].getBoundingClientRect();
      if (r.height && r.top >= top - 2) return { el: items[i], y: r.top };
    }
    return null;
  }
  function keepPlace(fn) {
    var a = anchor();
    fn();
    if (a) window.scrollTo(0, window.scrollY + a.el.getBoundingClientRect().top - a.y);
  }

  function showMode(mode) {
    body.classList.toggle("tight", mode === "tight");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].setAttribute("aria-pressed", buttons[i].dataset.mode === mode ? "true" : "false");
    }
  }
  if (buttons.length) {
    showMode(S ? S.get("align") : "speech");
    for (var b = 0; b < buttons.length; b++) {
      buttons[b].addEventListener("click", function () {
        var m = this.dataset.mode;
        keepPlace(function () { showMode(m); if (S) S.set("align", m); });
      });
    }
  }
  if (S) {
    var lastCols = S.get("cols"), lastAlign = S.get("align");
    S.onChange(function (p) {
      if (p.align !== lastAlign) { lastAlign = p.align; keepPlace(function () { showMode(p.align); }); }
      if (p.cols !== lastCols) { lastCols = p.cols; }
    });
  }

  // ---- apparatus toggle -----------------------------------------------------
  var app = document.getElementById("apptog");
  function setApp(on) {
    keepPlace(function () { body.classList.toggle("app", on); });
    app.setAttribute("aria-pressed", on ? "true" : "false");
    store("app", on ? "1" : "0");
  }
  if (app) {
    body.classList.toggle("app", load("app") === "1");
    app.setAttribute("aria-pressed", load("app") === "1" ? "true" : "false");
    app.addEventListener("click", function () { setApp(!body.classList.contains("app")); });
  }

  // ---- jump: "150", "2.150", "17a" -------------------------------------------
  function lastPart(k) { var p = String(k).split("."); return p[p.length - 1]; }
  function go(q) {
    q = q.trim();
    if (!q) return;
    var el = document.getElementById("L" + q) || document.getElementById("E" + q);
    if (!el) {
      var all = document.querySelectorAll(".col.g [data-k][id]");
      var a = anchor(), sec = a ? a.el.closest("section") : null;
      var n = parseInt(q, 10), exact = null, inSec = null, loose = null;
      for (var i = 0; i < all.length; i++) {
        var lp = lastPart(all[i].dataset.k), v = parseInt(lp, 10);
        var here = sec && all[i].closest("section") === sec;
        if (lp === q) {
          if (here) { el = all[i]; break; }
          if (!exact) exact = all[i];
        } else if (!isNaN(n) && !isNaN(v) && v >= n) {
          if (here && !inSec) inSec = all[i];
          if (!loose) loose = all[i];
        }
      }
      el = el || inSec || exact || loose;
    }
    if (!el) return;
    flash(el);
  }
  function flash(el) {
    el.scrollIntoView({ block: "center" });
    el.classList.add("flash");
    setTimeout(function () { el.classList.remove("flash"); }, 1800);
  }
  var form = document.querySelector(".jump");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      go(form.querySelector("input").value);
    });
  }

  // ---- edition picker: open the other page at the same place -----------------
  var picks = document.querySelectorAll(".pick");
  for (var j = 0; j < picks.length; j++) {
    picks[j].addEventListener("change", function () {
      var a = anchor();
      location.href = this.value + (a ? "#" + a.el.id : "");
    });
  }

  // ---- remember the reading position for the index page -----------------------
  var timer = null;
  window.addEventListener("scroll", function () {
    if (!pageKey) return;
    clearTimeout(timer);
    timer = setTimeout(function () {
      var a = anchor();
      if (!a) return;
      store("pos:" + pageKey, JSON.stringify({
        id: a.el.id, key: a.el.dataset.k, t: Date.now(),
        title: body.getAttribute("data-title") || document.title,
        author: body.getAttribute("data-author") || ""
      }));
    }, 400);
  }, { passive: true });

  // ---- search hits: ?hl=word1|word2 marks them in the passage you land on ------
  function fold(s) {
    return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ς/g, "σ").toLowerCase()
      .replace(/j/g, "i").replace(/v/g, "u");
  }
  var hl = new URLSearchParams(location.search).get("hl");
  if (hl && location.hash) {
    var target = document.getElementById(location.hash.slice(1));
    var words = hl.split("|").map(fold).filter(Boolean);
    if (target && words.length) {
      var ch = target.closest(".ch") || target.parentNode;
      var scope = [ch];
      var row = ch.getAttribute("style");
      var grp = ch.closest(".grp");
      if (grp && row) {
        var twins = grp.querySelectorAll('.ch[style="' + row + '"]');
        scope = Array.prototype.slice.call(twins);
      }
      scope.forEach(function (root) { markWords(root, words); });
      setTimeout(function () { flash(target); }, 50);
    }
  }
  function markWords(root, words) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var nodes = [], n;
    while ((n = walker.nextNode())) nodes.push(n);
    nodes.forEach(function (node) {
      var text = node.nodeValue, parts = text.split(/([^\s.,;:·!?()\[\]“”‘’"']+)/), changed = false;
      var frag = document.createDocumentFragment();
      parts.forEach(function (p) {
        if (p && words.indexOf(fold(p)) >= 0) {
          var m = document.createElement("mark"); m.className = "hit"; m.textContent = p;
          frag.appendChild(m); changed = true;
        } else if (p) frag.appendChild(document.createTextNode(p));
      });
      if (changed) node.parentNode.replaceChild(frag, node);
    });
  }

  // keys: t = toggle alignment, a = apparatus, / = jump box
  document.addEventListener("keydown", function (e) {
    var tag = e.target.tagName;
    if (tag === "INPUT" || tag === "SELECT" || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "t" && buttons.length) {
      var m = body.classList.contains("tight") ? "speech" : "tight";
      keepPlace(function () { showMode(m); if (S) S.set("align", m); });
    }
    if (e.key === "a" && app) setApp(!body.classList.contains("app"));
    if (e.key === "/" && form) { e.preventDefault(); form.querySelector("input").focus(); }
  });
})();
