#!/usr/bin/env python3
"""Web UI ringan untuk menjalankan Kalodata email finder."""

import html
import json
import os
import csv
import io
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from kalodata_email_finder import clean_username, run_batch_scrape

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8010"))
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "chocodata_settings.json")
LAST_EXPORT = b""
JOBS = {}
JOBS_LOCK = threading.Lock()


def load_api_key() -> str:
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return str(json.load(f).get("api_key", "")).strip()
    except (OSError, ValueError, TypeError):
        return ""


def save_api_key(api_key: str) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"api_key": api_key}, f)


def page(body: str, error: str = "") -> bytes:
    message = f'<div class="error">{html.escape(error)}</div>' if error else ""
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KOL Email Finder</title><style>
body{{font:15px system-ui;margin:0;background:#f5f7fb;color:#172033}}main{{max-width:760px;margin:40px auto;padding:24px;background:white;border-radius:14px;box-shadow:0 8px 30px #17203312}}h1{{margin-top:0}}label{{display:block;font-weight:600;margin:18px 0 7px}}input,textarea{{box-sizing:border-box;width:100%;padding:12px;border:1px solid #ccd3df;border-radius:8px;font:inherit}}textarea{{min-height:180px;resize:vertical}}button{{margin-top:20px;background:#1769e0;color:white;border:0;border-radius:8px;padding:12px 18px;font-weight:700;cursor:pointer}}.hint{{color:#637087;font-size:13px}}.error{{padding:12px;background:#fee2e2;color:#991b1b;border-radius:8px}}table{{width:100%;border-collapse:collapse;margin-top:20px}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #e5e7eb;font-size:13px}}
</style></head><body><main><h1>KOL Email Finder</h1><p class="hint">Chocodata • TikTok • country: US</p>{message}{body}</main></body></html>""".encode()


FORM = """<form id="finder-form" method="post" action="/start">
<label>Chocodata API key <span class="hint">(kosongkan jika tetap memakai key tersimpan)</span></label><input name="api_key" type="password" autocomplete="off" placeholder="cd_live_...">
<label>Mode email</label><label><input name="barter" value="1" type="radio" checked style="width:auto"> Personal / Barter</label>
<label><input name="barter" value="agency" type="radio" style="width:auto"> Agency</label>
<label><input name="barter" value="0" type="radio" style="width:auto"> All (Personal + Agency)</label>
<label>Username TikTok</label><textarea name="usernames" required placeholder="username1
username2
atau paste satu kolom dari Excel"></textarea>
<p class="hint">Key tersimpan lokal di komputer ini. Masukkan key baru kapan saja untuk menggantinya. Country: US.</p>
<button type="submit">Mulai cari</button></form>
<section id="progress" hidden><h2>Progress</h2><p id="progress-text">Menyiapkan...</p><p id="current-text" class="hint"></p><progress id="progress-bar" value="0" max="100" style="width:100%"></progress><div id="result"></div></section>
<script>
const form=document.getElementById('finder-form'); const progress=document.getElementById('progress');
form.addEventListener('submit', async (e)=>{e.preventDefault(); form.hidden=true; progress.hidden=false;
 const r=await fetch('/start',{method:'POST',body:new URLSearchParams(new FormData(form))}); const j=await r.json();
 if(!r.ok){document.getElementById('progress-text').textContent=j.error||'Gagal';return;} poll(j.job_id);});
async function poll(id){const r=await fetch('/status?id='+encodeURIComponent(id)); const j=await r.json();
 document.getElementById('progress-text').textContent=`${j.done}/${j.total} selesai (${j.percent}%)`;
 document.getElementById('current-text').textContent=j.active.length ? 'Sedang dicari: '+j.active.join(', ') : '';
 document.getElementById('progress-bar').value=j.percent;
 if(j.status==='done'){document.getElementById('result').innerHTML='<p>Selesai. <button type="button" id="copy-button">Copy hasil</button> <a href="/download">⬇ Export Excel</a></p><pre>'+j.summary+'</pre><a href="/">← Cari lagi</a>'; document.getElementById('copy-button').onclick=async()=>{await navigator.clipboard.writeText(j.copy_text); document.getElementById('copy-button').textContent='Copied ✓';};} else if(j.status==='error'){document.getElementById('result').textContent=j.error;} else setTimeout(()=>poll(id),500);}
</script>"""


class Handler(BaseHTTPRequestHandler):
    def send_page(self, content: bytes, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.path.startswith("/status"):
            job_id = self.path.split("id=", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(job_id, {"status": "error", "error": "Job tidak ditemukan."}).copy()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(job).encode())
            return
        if self.path == "/download":
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="hasil_kol_email.csv"')
            self.end_headers()
            self.wfile.write(LAST_EXPORT or b"TikTok Username,Email Address,Inbox Type,Source,Status\n")
            return
        self.send_page(page(FORM))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode("utf-8", "ignore"))
        api_key = form.get("api_key", [""])[0].strip() or load_api_key()
        raw = form.get("usernames", [""])[0]
        mode = form.get("barter", ["1"])[0]
        targets = []
        for line in raw.replace("\t", "\n").replace(",", "\n").splitlines():
            username = clean_username(line)
            if username and username not in targets:
                targets.append(username)
        if not api_key or not targets:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "API key dan username wajib diisi."}).encode())
            return
        save_api_key(api_key)
        job_id = uuid.uuid4().hex
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "running", "done": 0, "total": len(targets), "percent": 0, "active": []}

        def worker():
            def update(event, username, done, total, _result):
                with JOBS_LOCK:
                    active = JOBS[job_id].setdefault("active", [])
                    if event == "start" and username not in active:
                        active.append(username)
                    elif event == "done" and username in active:
                        active.remove(username)
                    JOBS[job_id].update(done=done, total=total, percent=round(done / total * 100), active=active)
            try:
                results = run_batch_scrape(targets, workers=5, barter_only=(mode == "1"), api_key=api_key, progress_callback=update)
                if mode == "agency":
                    results = [r for r in results if r.get("email") and not r.get("is_barter")]
                global LAST_EXPORT
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(["Username TikTok", "Email", "Inbox Type", "Source", "Status"])
                for result in results:
                    writer.writerow([result["username"], result.get("email") or "", result.get("inbox_type") or "", result.get("source") or "", result.get("status") or ""])
                LAST_EXPORT = ("sep=,\n" + output.getvalue()).encode("utf-8-sig")
                summary = "\n".join(f'{r["username"]} | {r.get("email") or "Not Found"}' for r in results)
                copy_text = "Username TikTok\tEmail\n" + "\n".join(f'{r["username"]}\t{r.get("email") or ""}' for r in results)
                with JOBS_LOCK:
                    JOBS[job_id].update(status="done", done=len(targets), percent=100, active=[], summary=summary, copy_text=copy_text)
            except Exception as exc:
                with JOBS_LOCK:
                    JOBS[job_id].update(status="error", error=str(exc))
        threading.Thread(target=worker, daemon=True).start()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"job_id": job_id}).encode())


if __name__ == "__main__":
    print(f"Buka http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
