// Catalog page (local builds only): works in public domain repositories (Perseus, Wikisource).
// Filter by author, title or repository; accents and case are ignored ("λογος" finds λόγος).
// Add works with the button when the page is served by `python perseus.py edit`; otherwise the
// button is replaced by the command to run.
(function () {
  var rows = window.CATALOG || [];
  var q = document.getElementById("q"), eng = document.getElementById("eng"), src = document.getElementById("src"),
      shelf = document.getElementById("shelf"), tbody = document.getElementById("rows"),
      count = document.getElementById("n");
  var canAdd = false, busy = false;
  var REPO = { perseus: "Perseus", wikisource: "Wikisource" };
  var NAMES = { eng: "English", grc: "Greek", lat: "Latin", el: "Greek", la: "Latin", it: "Italian", fr: "French",
    de: "German", es: "Spanish", pt: "Portuguese", ru: "Russian", zh: "Chinese", ja: "Japanese" };

  function fold(s) {
    return s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ς/g, "σ")
      .replace(/j/g, "i").replace(/v/g, "u").toLowerCase();
  }
  var hay = rows.map(function (r) { return fold(r[0] + " " + r[1] + " " + r[2] + " " + r[3]); });
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  function langs(r) { return r[4].split("+").map(function (l) { return NAMES[l] || l; }).join(" + "); }

  function action(r, i) {
    if (r[6]) return '<span class="on">on your shelf</span>' + (canAdd && r[7] === "wikisource"
      ? ' <button type="button" class="linkish" data-tr="' + i + '" title="Paste the address of an English Wikisource translation">+ translation</button>' : "");
    if (canAdd) return '<button type="button" class="icon-btn" data-add="' + i + '">Add</button>' + (r[7] === "wikisource"
      ? ' <a class="linkish" target="_blank" rel="noopener" href="https://en.wikisource.org/wiki/' + encodeURIComponent(r[2].replace(/ /g, "_")) + '">translations ↗</a>' : "");
    return r[7] === "perseus" ? "<code>python perseus.py add " + esc(r[0]) + "</code>"
      : '<span class="on">add from <code>python perseus.py edit</code></span>';
  }

  function render() {
    var words = fold(q.value).split(/\s+/).filter(Boolean);
    var out = [], n = 0;
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (src.value && r[7] !== src.value) continue;
      if (eng.checked && !r[5]) continue;
      if (shelf.checked && r[6]) continue;
      var ok = true;
      for (var w = 0; w < words.length; w++) if (hay[i].indexOf(words[w]) < 0) { ok = false; break; }
      if (!ok) continue;
      n++;
      if (out.length < 300) {
        out.push("<tr><td>" + esc(r[1]) + "</td><td>" + esc(r[2]) +
          (r[3] && r[3] !== r[2] ? '<span class="orig">' + esc(r[3]) + "</span>" : "") +
          "</td><td>" + esc(langs(r)) + (r[5] > 1 ? " (" + r[5] + " English)" : "") + "</td><td>" +
          esc(REPO[r[7]] || r[7]) + '</td><td class="act">' + action(r, i) + "</td></tr>");
      }
    }
    tbody.innerHTML = out.join("");
    count.textContent = n + " works" + (n > 300 ? " (showing the first 300; narrow the search)" : "");
  }
  [q, eng, src, shelf].forEach(function (el) { el.addEventListener("input", render); });

  // ---- adding (only when served by `python perseus.py edit`) ----------------------------
  var bar = document.createElement("div");           // visible wherever the page is scrolled to
  bar.className = "cat-status"; bar.hidden = true; bar.setAttribute("role", "status");
  document.body.appendChild(bar);
  function status(msg, kind) {
    count.textContent = msg;
    bar.textContent = msg; bar.hidden = !msg;
    bar.className = "cat-status" + (kind ? " " + kind : "");
  }
  function poll(label) {
    fetch("/__edit/status", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (s) {
      var last = s.log && s.log.length ? s.log[s.log.length - 1] : "";
      if (s.state === "running") { status(label + " — " + last, "busy"); return setTimeout(function () { poll(label); }, 1500); }
      busy = false;
      var note = (s.log || []).filter(function (l) { return /^(no |the two|wrote )/.test(l); }).slice(-3).join(" · ");
      if (s.state === "done") { status(label + ": done. " + note + " Reloading…", "ok"); setTimeout(function () { location.reload(); }, note ? 4000 : 800); }
      else { status(label + " failed: " + (s.log || []).slice(-3).join(" | "), "bad"); render(); }
    }).catch(function () { busy = false; status("Lost contact with the edit server."); });
  }
  tbody.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-add], button[data-tr]");
    if (!b || busy) return;
    var tr = b.hasAttribute("data-tr");
    var r = rows[+b.getAttribute(tr ? "data-tr" : "data-add")], url = "";
    if (tr) {
      url = (prompt("Address of the English Wikisource page to pair with " + r[3] + ":", "https://en.wikisource.org/wiki/") || "").trim();
      if (!url || /\/wiki\/$/.test(url)) return;
    }
    busy = true; b.disabled = true;
    var label = (tr ? "Adding a translation of " : "Adding ") + r[2];
    b.textContent = "Adding…";
    status(label + " — starting", "busy");
    fetch("/__edit/catalog-add", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: r[0], source: r[7], translation: url }) })
      .then(function (res) { return res.json(); })
      .then(function (j) { if (j.error || !j.started) { busy = false; status(j.error || "Another job is running; try again in a minute."); render(); } else poll(label); })
      .catch(function () { busy = false; status("Could not reach the edit server."); render(); });
  });
  fetch("/__edit/status", { cache: "no-store" }).then(function (r) { canAdd = r.ok; render(); }, function () {});
  render();
})();
