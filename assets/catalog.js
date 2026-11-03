// Catalog page: filter every Perseus work by author or title. Accents and case are ignored
// ("λογος" finds λόγος; "cicero" finds Cicero).
(function () {
  var rows = window.CATALOG || [];
  var q = document.getElementById("q"), eng = document.getElementById("eng"),
      shelf = document.getElementById("shelf"), tbody = document.getElementById("rows"),
      count = document.getElementById("n");

  function fold(s) {
    return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ς/g, "σ")
      .replace(/j/g, "i").replace(/v/g, "u").toLowerCase();
  }
  var hay = rows.map(function (r) { return fold(r[0] + " " + r[1] + " " + r[2] + " " + r[3]); });

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function render() {
    var words = fold(q.value).split(/\s+/).filter(Boolean);
    var out = [], n = 0;
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (eng.checked && !r[5]) continue;
      if (shelf.checked && !r[6]) continue;
      var ok = true;
      for (var w = 0; w < words.length; w++) if (hay[i].indexOf(words[w]) < 0) { ok = false; break; }
      if (!ok) continue;
      n++;
      if (out.length < 300) {
        out.push("<tr><td>" + esc(r[1]) + "</td><td>" + esc(r[2]) +
          (r[3] && r[3] !== r[2] ? '<span class="orig">' + esc(r[3]) + "</span>" : "") +
          "</td><td>" + esc(r[4]) + (r[5] > 1 ? " (" + r[5] + " English)" : "") + "</td><td>" +
          (r[6] ? '<span class="on">on shelf</span>' : "<code>python perseus.py add " + esc(r[0]) + "</code>") +
          "</td></tr>");
      }
    }
    tbody.innerHTML = out.join("");
    count.textContent = n + " works" + (n > 300 ? " (showing the first 300; narrow the search)" : "");
  }
  [q, eng, shelf].forEach(function (el) { el.addEventListener("input", render); });
  render();
})();
