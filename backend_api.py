"""ArenHost API for the GitHub Pages frontend."""

import json
import os
import threading
import uuid
from http import HTTPStatus

from flask import Flask, jsonify, request

from kalodata_email_finder import run_batch_scrape

app = Flask(__name__)
JOBS = {}
JOBS_LOCK = threading.Lock()
ALLOWED_ORIGIN = os.environ.get(
    "FRONTEND_ORIGIN",
    "https://helmiandjustin.github.io",
)


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.get("/health")
def health():
    return jsonify(ok=True)


@app.route("/api/start", methods=["POST", "OPTIONS"])
def start():
    if request.method == "OPTIONS":
        return ("", HTTPStatus.NO_CONTENT)
    if not os.environ.get("CHOCODATA_API_KEY", "").strip():
        return jsonify(error="CHOCODATA_API_KEY belum diatur di hosting."), HTTPStatus.INTERNAL_SERVER_ERROR

    payload = request.get_json(silent=True) or {}
    usernames = payload.get("usernames", [])
    mode = payload.get("mode", "personal")
    if not isinstance(usernames, list) or not usernames:
        return jsonify(error="Username TikTok wajib diisi."), HTTPStatus.BAD_REQUEST
    if mode not in {"personal", "agency", "all"}:
        return jsonify(error="Mode tidak valid."), HTTPStatus.BAD_REQUEST

    targets = [str(item).strip() for item in usernames if str(item).strip()]
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "running", "done": 0, "total": len(targets), "active": [], "results": []}

    def worker():
        def progress(event, username, done, total, result):
            with JOBS_LOCK:
                job = JOBS[job_id]
                active = job["active"]
                if event == "start" and username not in active:
                    active.append(username)
                if event == "done" and username in active:
                    active.remove(username)
                job.update(done=done, total=total, active=list(active))
                if result:
                    job["results"].append(result)

        try:
            results = run_batch_scrape(
                targets,
                workers=5,
                barter_only=mode == "personal",
                api_key=os.environ["CHOCODATA_API_KEY"],
                progress_callback=progress,
            )
            if mode == "agency":
                results = [item for item in results if item.get("email") and not item.get("is_barter")]
            with JOBS_LOCK:
                JOBS[job_id].update(status="done", done=len(targets), active=[], results=results)
        except Exception as exc:
            with JOBS_LOCK:
                JOBS[job_id].update(status="error", error=str(exc), active=[])

    threading.Thread(target=worker, daemon=True).start()
    return jsonify(job_id=job_id)


@app.get("/api/status")
def status():
    job_id = request.args.get("id", "")
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify(error="Job tidak ditemukan."), HTTPStatus.NOT_FOUND
        result = dict(job)
    result.pop("results", None)
    result["percent"] = round(result["done"] / result["total"] * 100) if result["total"] else 0
    return jsonify(result)


@app.get("/api/results")
def results():
    job_id = request.args.get("id", "")
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify(error="Job tidak ditemukan."), HTTPStatus.NOT_FOUND
        return jsonify(results=job.get("results", []))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
