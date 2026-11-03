// Library reader: alignment switch (keeps your place), jump to a number, edition picker,
// apparatus toggle, and "where you left off" on the index page.
(function () {
  var body = document.body;

  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

  // ---- index page: show where you left off in each work ------------------
  if (body.classList.contains("index")) {
    var items = document.querySelectorAll("li[data-page]");
    for (var i = 0; i < items.length; i++) {
      var page = items[i].getAttribute("data-page");
      var pos = load("pos:" + page);
      if (pos) {
        var parts = pos.split("|");
        var where = items[i].querySelector(".where");
        var a = document.createElement("a");
        a.href = page + "#" + parts[0];
        a.textContent = "continue at " + parts[1];
        where.appendChild(a);
      }
    }
    return;
  }

  var buttons = document.querySelectorAll(".seg button");
  var pageKey = body.getAttribute("data-page");

  function headerBottom() {
    var top = (document.querySelector(".bar") || {}).offsetHeight || 0;
    var heads = document.querySelector(".heads");
    if (heads && getComputedStyle(heads).display !== "none") top += heads.offsetHeight;
    return top;
  }

  // the first numbered line or marker visible under the sticky headers (left column)
  function anchor() {
    var top = headerBottom();
    var items = document.querySelectorAll(".col.g [data-k][id]");
    for (var i = 0; i < items.length; i++) {
      var r = items[i].getBoundingClientRect();
      if (r.top >= top - 2) return { el: items[i], y: r.top };
    }
    return null;
  }

  function setMode(mode, keepPlace) {
    var a = keepPlace ? anchor() : null;
    body.classList.toggle("tight", mode === "tight");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].setAttribute("aria-pressed", buttons[i].dataset.mode === mode ? "true" : "false");
    }
    if (a) window.scrollTo(0, window.scrollY + a.el.getBoundingClientRect().top - a.y);
    store("align", mode);
  }
  if (buttons.length) {
    setMode(load("align") === "tight" ? "tight" : "speech", false);
    for (var b = 0; b < buttons.length; b++) {
      buttons[b].addEventListener("click", function () { setMode(this.dataset.mode, true); });
    }
  }

  // ---- apparatus toggle -----------------------------------------------------
  var app = document.getElementById("apptog");
  function setApp(on, keepPlace) {
    var a = keepPlace ? anchor() : null;
    body.classList.toggle("app", on);
    app.setAttribute("aria-pressed", on ? "true" : "false");
    if (a) window.scrollTo(0, window.scrollY + a.el.getBoundingClientRect().top - a.y);
    store("app", on ? "1" : "0");
  }
  if (app) {
    setApp(load("app") === "1", false);
    app.addEventListener("click", function () { setApp(!body.classList.contains("app"), true); });
  }

  // ---- jump: "150", "2.150", "17a" -------------------------------------------
  function lastPart(k) { var p = String(k).split("."); return p[p.length - 1]; }
  function go(q) {
    q = q.trim();
    if (!q) return;
    var el = document.getElementById("L" + q) || document.getElementById("E" + q);
    if (!el) {
      // a bare number: prefer the section you are reading, then anywhere
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
      if (a) store("pos:" + pageKey, a.el.id + "|" + a.el.dataset.k);
    }, 400);
  }, { passive: true });

  // keys: t = toggle alignment, a = apparatus, / = jump box
  document.addEventListener("keydown", function (e) {
    var tag = e.target.tagName;
    if (tag === "INPUT" || tag === "SELECT" || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "t" && buttons.length) setMode(body.classList.contains("tight") ? "speech" : "tight", true);
    if (e.key === "a" && app) setApp(!body.classList.contains("app"), true);
    if (e.key === "/" && form) { e.preventDefault(); form.querySelector("input").focus(); }
  });
})();
