"""Local edit mode: `python perseus.py edit` serves site/ on this computer only and adds the
editing tools (assets/edit.js) to each page as it is served. The built pages, and so the public
site, never contain them. Edits are rules in library/edits.tsv (see reader/edits.py); Publish
rebuilds, commits that file, pushes to GitHub and deploys to Cloudflare Pages."""
import json
import os
import subprocess
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import edits as text_edits
from . import importer
from . import sources

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
RULES = ROOT / "library" / "edits.tsv"
INBOX = ROOT / "library" / "additions"          # raw files waiting to be imported
DEST = {"private": ROOT / "library" / "private", "own": ROOT / "library" / "own"}
_catalog = None


def catalog():
    global _catalog
    if _catalog is None:
        from . import perseus
        _catalog = perseus.load_catalog()
    return _catalog


def shelf():
    d = ROOT / "library" / "perseus"
    return {p.name for p in d.iterdir()} if d.is_dir() else set()


BOOKS = (".pdf", ".epub")
ACCEPT = (".md",) + BOOKS
_pages = {}                                     # (path, mtime) -> pages of lines


def book_pages(p):
    key = (str(p), p.stat().st_mtime)
    if key not in _pages:
        _pages.clear()                          # one book at a time: they can be large
        _pages[key] = sources.read_pages(p)
    return _pages[key]


def inbox():
    """Files in library/additions waiting to be imported: raw .md (no library front matter),
    PDF and EPUB books, with guessed details."""
    out = []
    if not INBOX.is_dir():
        return out
    for p in sorted(x for x in INBOX.iterdir() if x.suffix.lower() in ACCEPT):
        if p.suffix.lower() == ".md":
            head = p.read_text(encoding="utf-8", errors="replace")[:600]
            if head.startswith("---") and "\nwork:" in head:
                continue                       # already in the library format
        g = importer.guess(p, catalog(), shelf())
        done = [k for k, d in DEST.items() if (d / f"{g['id']}.md").exists()]
        out.append({"file": p.name, **g, "imported": done,
                    "kind": "book" if p.suffix.lower() in BOOKS else "md"})
    return out


def book_parts(name):
    """The verse parts found in a book, best first, for the Import panel."""
    src = INBOX / Path(name).name
    if src.suffix.lower() not in BOOKS or not src.is_file():
        raise ValueError("not a PDF or EPUB in library/additions")
    pages = book_pages(src)
    parts = sources.parts(pages)
    for p in parts:
        p.pop("score", None)
    return {"pages": len(pages), "parts": parts}


def do_import(b, preview=False):
    src = INBOX / Path(b["file"]).name
    if not src.is_file():
        raise ValueError("file not found in library/additions")
    dest = DEST.get(b.get("dest"))
    if dest is None and not preview:
        raise ValueError("destination must be private or own")
    meta = {k: (b.get(k) or "").strip() for k in ("id", "work", "author", "title", "edition", "language")}
    meta["language"] = meta["language"] or "eng"
    meta["source"] = src.name
    if not meta["work"] or not meta["id"]:
        raise ValueError("work and id are needed")
    if src.suffix.lower() in BOOKS:
        pages = book_pages(src)
        chosen = sources.page_range(b.get("pages", ""), len(pages))
        if not chosen:
            raise ValueError("choose the pages that hold the text")
        lines = [l for n in chosen for l in pages[n - 1]]
        drop = [d.strip() for d in (b.get("drop") or "").split(",") if d.strip()]
        md, report = importer.convert_lines(lines, meta, drop)
        if meta.get("source"):
            md = md.replace(f"source: {meta['source']}", f"source: {meta['source']}, pages {b.get('pages')}", 1)
    else:
        md, report = importer.convert(src.read_text(encoding="utf-8"), meta)
    if preview:
        lines = md.split("\n")
        return {"ok": True, "preview": "\n".join(lines[:160]) + ("\n…" if len(lines) > 160 else ""),
                "tail": "\n".join(lines[-25:]), "report": report}
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{meta['id']}.md"
    out.write_text(md, encoding="utf-8")
    return {"ok": True, "path": str(out.relative_to(ROOT)).replace("\\", "/"), "report": report}


def save_upload(name, data):
    """A file chosen in the Import panel, copied into library/additions."""
    name = Path(name).name
    if Path(name).suffix.lower() not in ACCEPT or name.startswith("."):
        raise ValueError("only .md, .pdf and .epub files")
    INBOX.mkdir(parents=True, exist_ok=True)
    (INBOX / name).write_bytes(data)
    return {"ok": True, "file": name}
EDIT_JS = ROOT / "assets" / "edit.js"
INJECT = b'<script src="/__edit/edit.js"></script>\n</body>'


# ---- jobs: rebuild / publish, one at a time, with a log the page can poll ----------------
class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.state, self.name, self.log = "idle", "", []

    def start(self, name, steps):
        with self.lock:
            if self.state == "running":
                return False
            self.state, self.name, self.log = "running", name, []
        threading.Thread(target=self._run, args=(steps,), daemon=True).start()
        return True

    def _run(self, steps):
        ok = True
        for label, cmd, optional in steps:
            if callable(cmd):
                try:
                    msg = cmd()
                    if msg:
                        self.log.append(msg)
                    if msg == "skip-rest":
                        break
                    continue
                except Exception as e:     # noqa: BLE001 — report anything to the page
                    self.log.append(f"{label} failed: {e}")
                    ok = False
                    break
            self.log.append(f"$ {label}")
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            out = (p.stdout + p.stderr).strip().splitlines()
            self.log.extend(l for l in out[-12:] if "check sync" not in l)
            if p.returncode != 0 and not optional:
                self.log.append(f"{label} failed (exit {p.returncode})")
                ok = False
                break
        self.state = "done" if ok else "failed"

    def status(self):
        return {"state": self.state, "name": self.name, "log": self.log[-40:]}


JOB = Job()
PY = os.environ.get("PYTHON", "python")


def build_steps(private=True):
    """Here the site is built with library/private; Publish builds without it."""
    return [("build", [PY, "perseus.py", "build"] + (["--private"] if private else []), False)]


def publish_steps():
    def commit():
        subprocess.run(["git", "add", str(RULES.relative_to(ROOT))], cwd=ROOT, check=True)
        if DEST["own"].is_dir():           # texts imported into the public library
            subprocess.run(["git", "add", "library/own"], cwd=ROOT, check=True)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
            return "no new edits to commit"
        n = len(text_edits.Rules(RULES).rules)
        subprocess.run(["git", "commit", "-m", f"Text edits ({n} rule{'s' if n != 1 else ''} in library/edits.tsv)"],
                       cwd=ROOT, check=True, capture_output=True)
        return "committed library/edits.tsv"
    shell = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "deploy.ps1"] \
        if os.name == "nt" else ["pwsh", "-File", "deploy.ps1"]
    return build_steps(private=False) + [("commit", commit, False),
                                         ("git push", ["git", "push"], False),
                                         ("deploy to Cloudflare Pages", shell, False)] + \
        [("rebuild with private texts for this computer", s[1], True) for s in build_steps()]


def publish_cli():
    """python perseus.py publish: the same steps, in the terminal."""
    JOB._run(publish_steps())
    print("\n".join(JOB.log))
    return JOB.state == "done"


# ---- HTTP ---------------------------------------------------------------------------------
class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/__edit/edit.js":
            data = EDIT_JS.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/__edit/rules":
            ids = [x for x in (self.path.split("ids=", 1)[1:] or [""])[0].split(",") if x]
            from urllib.parse import unquote
            ids = [unquote(x) for x in ids]
            rules = text_edits.Rules(RULES)
            self.send_json([{"id": t, "action": a, "anchor": x} for t, a, x in rules.rules if t in ids])
            return
        if path == "/__edit/status":
            return self.send_json(JOB.status())
        if path == "/__edit/inbox":
            return self.send_json(inbox())
        if path == "/__edit/parts":
            from urllib.parse import parse_qs, urlsplit
            q = parse_qs(urlsplit(self.path).query)
            try:
                return self.send_json(book_parts(q.get("file", [""])[0]))
            except (ValueError, RuntimeError, OSError) as e:
                return self.send_json({"error": str(e)}, 400)
        # pages: add the edit tools on the way out
        local = Path(self.translate_path(path))
        if local.is_dir():
            local = local / "index.html"
        if local.suffix == ".html" and local.is_file():
            data = local.read_bytes()
            data = data.replace(b"</body>", INJECT, 1) if b"</body>" in data else data + INJECT
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/__edit/upload":
            from urllib.parse import parse_qs, unquote, urlsplit
            name = unquote(parse_qs(urlsplit(self.path).query).get("name", [""])[0])
            n = int(self.headers.get("Content-Length") or 0)
            if n > 300 * 1024 * 1024:
                return self.send_json({"error": "file too large"}, 400)
            try:
                return self.send_json(save_upload(name, self.rfile.read(n)))
            except (ValueError, OSError) as e:
                return self.send_json({"error": str(e)}, 400)
        try:
            b = self.body()
        except ValueError:
            return self.send_json({"error": "bad request"}, 400)
        rules = text_edits.Rules(RULES)
        if path == "/__edit/delete":
            if not b.get("id") or not b.get("text"):
                return self.send_json({"error": "missing id or text"}, 400)
            r = rules.add(b["id"], "delete", b["text"])
            return self.send_json({"ok": True, "anchor": r[2]})
        if path == "/__edit/undo":
            rules.remove(b.get("id", ""), b.get("action", "delete"), b.get("anchor", ""))
            return self.send_json({"ok": True})
        if path in ("/__edit/import", "/__edit/preview"):
            try:
                return self.send_json(do_import(b, preview=path.endswith("preview")))
            except (ValueError, KeyError, RuntimeError, OSError) as e:
                return self.send_json({"error": str(e)}, 400)
        if path == "/__edit/build":
            return self.send_json({"started": JOB.start("Rebuild", build_steps())})
        if path == "/__edit/publish":
            return self.send_json({"started": JOB.start("Publish", publish_steps())})
        self.send_json({"error": "unknown"}, 404)


def serve(port=8790, open_browser=True):
    handler = partial(Handler, directory=str(SITE))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)      # this computer only
    url = f"http://127.0.0.1:{port}/library.html"
    print(f"edit mode: {url}  (Alt-click a paragraph to delete it; Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
