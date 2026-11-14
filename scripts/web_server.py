"""Mesh Studio: dependency-free local upload/job/media server. Bind to loopback only."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import uuid
from urllib.parse import urlsplit, parse_qs
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
JOBS_ROOT = ROOT / "outputs" / "web"
MAX_UPLOAD = 4 * 1024**3
EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
ARTIFACTS = {"video": "depth_with_mesh.mp4", "comparison": "comparison_preview.mp4",
             "report": "render_report.json", "landmarks": "face_landmarks.json",
             "alignment": "alignment_contact_sheet.jpg", "tracking": "tracking_review.jpg"}


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def clean_name(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Choose both video files first.")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    if len(name) > 240 or Path(name).suffix.lower() not in EXTENSIONS:
        raise ValueError("Choose an MP4, MOV, MKV, WebM, M4V or AVI video.")
    return name


def validate_settings(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid export settings.")
    settings = {"style": value.get("style", "mesh"), "color": str(value.get("color", "00FFFF")).lstrip("#").upper(),
                "max_faces": value.get("max_faces", 4), "thickness": value.get("thickness", 1),
                "opacity": value.get("opacity", .8), "smoothing_ms": value.get("smoothing_ms", 12)}
    if settings["style"] not in ("mesh", "contours", "dots") or not re.fullmatch(r"[0-9A-F]{6}", settings["color"]):
        raise ValueError("Invalid wireframe style or color.")
    for name, lo, hi in (("max_faces", 1, 8), ("thickness", 1, 8), ("opacity", 0, 1), ("smoothing_ms", 0, 1000)):
        item = settings[name]
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or not lo <= item <= hi:
            raise ValueError(f"Invalid {name.replace('_', ' ')}.")
        if name in ("max_faces", "thickness") and not isinstance(item, int):
            raise ValueError(f"{name} must be a whole number.")
    return settings


class Jobs:
    def __init__(self, root=JOBS_ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.items = {}
        self.processes = {}
        self.uploading = set()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mesh-job")
        for folder in self.root.iterdir():
            if not folder.is_dir() or not re.fullmatch(r"[0-9a-f]{32}", folder.name):
                continue
            try:
                job = json.loads((folder / "job.json").read_text("utf-8"))
                if job["id"] != folder.name:
                    continue
                if job["status"] not in ("complete", "failed", "cancelled"):
                    job.update(status="failed", stage="failed", message="The local server was restarted. Select your videos to start a new run.")
                    write_json(folder / "job.json", job)
                self.items[job["id"]] = job
            except (OSError, ValueError, KeyError):
                continue

    def folder(self, job_id):
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise KeyError("Unknown run")
        return self.root / job_id

    def get(self, job_id):
        with self.lock:
            return json.loads(json.dumps(self.items[job_id]))

    def update(self, job_id, **values):
        with self.lock:
            job = self.items[job_id]
            job.update(values, updated_at=now())
            write_json(self.folder(job_id) / "job.json", job)

    def create(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Invalid upload request")
        names, sizes = {}, {}
        for kind in ("original", "depth"):
            entry = payload.get(kind, {})
            if not isinstance(entry, dict):
                raise ValueError("Choose both videos")
            names[kind] = clean_name(entry.get("name"))
            size = entry.get("size")
            if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_UPLOAD:
                raise ValueError("Each video must be nonempty and no larger than 4 GB.")
            sizes[kind] = size
        settings = validate_settings(payload.get("settings", {}))
        with self.lock:
            active = sum(item["status"] in ("uploading", "queued", "running") for item in self.items.values())
            if active >= 4:
                raise ValueError("Four runs are already active. Wait for one to finish or cancel a run.")
            job_id = uuid.uuid4().hex
            folder = self.folder(job_id)
            folder.mkdir()
            job = {"id": job_id, "created_at": now(), "updated_at": now(), "status": "uploading", "stage": "uploading",
                   "progress": 0, "message": "Waiting for both videos", "names": names, "sizes": sizes,
                   "files": {kind: kind + Path(name).suffix.lower() for kind, name in names.items()},
                   "uploaded": {"original": False, "depth": False}, "settings": settings}
            self.items[job_id] = job
            write_json(folder / "job.json", job)
            return self.get(job_id)

    def upload(self, job_id, kind, stream, size):
        with self.lock:
            job = self.items[job_id]
            if kind not in ("original", "depth") or job["status"] != "uploading":
                raise ValueError("This run is not accepting uploads.")
            if size != job["sizes"][kind] or not 0 < size <= MAX_UPLOAD:
                raise ValueError("The upload size does not match the selected video. Choose the file again.")
            key = (job_id, kind)
            if key in self.uploading or job["uploaded"][kind]:
                raise ValueError("This video is already uploading or uploaded.")
            self.uploading.add(key)
            path = self.folder(job_id) / job["files"][kind]
        temporary = path.with_suffix(path.suffix + ".upload")
        try:
            remaining = size
            with temporary.open("wb") as handle:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("The upload was interrupted. Select your videos and try again.")
                    handle.write(chunk)
                    remaining -= len(chunk)
            with self.lock:
                if self.items[job_id]["status"] != "uploading":
                    raise ValueError("This upload was cancelled.")
                temporary.replace(path)
                self.items[job_id]["uploaded"][kind] = True
                self.update(job_id, message=f"{kind.capitalize()} video received")
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            with self.lock:
                self.uploading.discard(key)

    def start(self, job_id):
        with self.lock:
            job = self.items[job_id]
            if job["status"] != "uploading" or not all(job["uploaded"].values()):
                raise ValueError("Upload both videos before starting this run.")
            self.update(job_id, status="queued", stage="queued", message="Waiting for the local engine", progress=0)
            self.executor.submit(self.work, job_id)

    def cancel(self, job_id):
        with self.lock:
            if self.items[job_id]["status"] not in ("uploading", "queued", "running"):
                return
            self.update(job_id, status="cancelled", stage="cancelled", message="Run cancelled")
            process = self.processes.get(job_id)
            if process is not None:
                process.terminate()

    def work(self, job_id):
        folder = self.folder(job_id)
        try:
            with self.lock:
                if self.items[job_id]["status"] == "cancelled":
                    return
                self.update(job_id, status="running", stage="checking", progress=2, message="Starting the local engine")
                process = subprocess.Popen([sys.executable, "-u", str(ROOT / "scripts" / "mesh_web_worker.py"), str(folder / "job.json")],
                                           cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, encoding="utf-8", errors="replace",
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.processes[job_id] = process
            result = None
            failure = None
            with (folder / "engine.log").open("w", encoding="utf-8") as log:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    if not line.startswith("MESH_EVENT "):
                        continue
                    data = json.loads(line[len("MESH_EVENT "):])
                    with self.lock:
                        if self.items[job_id]["status"] == "cancelled":
                            continue
                        if data["stage"] == "complete":
                            result = data["result"]
                        elif data["stage"] == "failed":
                            failure = data["message"]
                        else:
                            self.update(job_id, **data)
            code = process.wait()
            process.stdout.close()
            with self.lock:
                if self.items[job_id]["status"] == "cancelled":
                    return
                if code == 0 and result and (folder / ARTIFACTS["video"]).exists():
                    self.update(job_id, status="complete", stage="complete", progress=100,
                                message="Your wireframe video is ready", result=result)
                else:
                    self.update(job_id, status="failed", stage="failed", message=failure or "Processing stopped unexpectedly. Try again or check this run's engine.log.")
        except Exception as error:
            with self.lock:
                if self.items[job_id]["status"] != "cancelled":
                    self.update(job_id, status="failed", stage="failed", message=str(error))
        finally:
            with self.lock:
                self.processes.pop(job_id, None)

    def close(self):
        with self.lock:
            for job_id in list(self.processes):
                self.cancel(job_id)
            for job_id, job in self.items.items():
                if job["status"] == "queued":
                    self.cancel(job_id)
        self.executor.shutdown(wait=True, cancel_futures=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "MeshStudio/1.0"

    def log_message(self, fmt, *args):
        # Do not log session tokens or filenames into the console.
        if args and str(args[0]).startswith('"GET /api/jobs'):
            return
        super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
        super().end_headers()

    def trusted(self, mutate=False):
        hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if host not in hosts or (origin and origin not in {"http://" + item for item in hosts}) or self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.reply(403, {"error": "Open Mesh Studio from its local address."})
            return False
        if mutate and not secrets.compare_digest(self.headers.get("X-Mesh-Token", ""), self.server.token):
            self.reply(403, {"error": "Refresh the page to reconnect to the local engine."})
            return False
        return True

    def reply(self, code, value):
        body = json.dumps(value, allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if not 0 < length <= 16384:
            raise ValueError("Invalid request size")
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        if not self.trusted():
            return
        path = urlsplit(self.path).path
        try:
            if path == "/api/config":
                ready = (ROOT / "models" / "face_landmarker.task").is_file() and shutil.which("ffprobe") is not None
                return self.reply(200, {"token": self.server.token, "ready": ready, "max_upload_bytes": MAX_UPLOAD,
                                        "message": "Local engine ready" if ready else "Run Check-Environment.ps1 to repair the local setup."})
            if path == "/api/jobs":
                with self.server.jobs.lock:
                    jobs = sorted(self.server.jobs.items.values(), key=lambda x: x["created_at"], reverse=True)[:30]
                    return self.reply(200, jobs)
            match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})(?:/files/([a-z]+))?", path)
            if match:
                job_id, artifact = match.groups()
                job = self.server.jobs.get(job_id)
                if artifact is None:
                    return self.reply(200, job)
                if artifact not in ARTIFACTS or job["status"] != "complete":
                    return self.reply(404, {"error": "This result is not ready."})
                filename = ARTIFACTS[artifact]
                download = parse_qs(urlsplit(self.path).query).get("download") == ["1"]
                return self.send_file(self.server.jobs.folder(job_id) / filename, download=download)
            static = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/styles.css": "styles.css", "/favicon.svg": "favicon.svg"}
            if path in static:
                return self.send_file(WEB / static[path])
            self.reply(404, {"error": "Not found"})
        except (KeyError, FileNotFoundError):
            self.reply(404, {"error": "Run or file not found"})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    do_HEAD = do_GET

    def do_POST(self):
        if not self.trusted(mutate=True):
            return
        path = urlsplit(self.path).path
        try:
            if path == "/api/jobs":
                return self.reply(201, self.server.jobs.create(self.read_json()))
            match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/(start|cancel)", path)
            if not match:
                return self.reply(404, {"error": "Not found"})
            job_id, action = match.groups()
            getattr(self.server.jobs, action)(job_id)
            self.reply(200, self.server.jobs.get(job_id))
        except KeyError:
            self.reply(404, {"error": "Run not found"})
        except (ValueError, TypeError) as error:
            self.reply(400, {"error": str(error)})
        except OSError:
            self.reply(500, {"error": "Could not write this run. Check available disk space and try again."})

    def do_PUT(self):
        if not self.trusted(mutate=True):
            return
        try:
            match = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/uploads/(original|depth)", urlsplit(self.path).path)
            if not match:
                return self.reply(404, {"error": "Not found"})
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("A known upload length is required")
            job_id, kind = match.groups()
            self.connection.settimeout(120)
            self.server.jobs.upload(job_id, kind, self.rfile, int(self.headers.get("Content-Length", "0")))
            self.reply(200, {"uploaded": kind})
        except KeyError:
            self.reply(404, {"error": "Run not found"})
        except (ValueError, TimeoutError) as error:
            self.reply(400, {"error": str(error)})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except OSError:
            self.reply(500, {"error": "Could not save your upload. Check available disk space and try again."})

    def send_file(self, path, download=False):
        size = path.stat().st_size
        start, end = 0, size - 1
        partial = self.headers.get("Range")
        if partial:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", partial)
            if not match or not any(match.groups()):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), end) if last else end
            else:
                start = max(0, size - int(last))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        self.send_response(206 if partial else 200)
        mime = {".js": "text/javascript", ".css": "text/css", ".html": "text/html", ".svg": "image/svg+xml", ".mp4": "video/mp4"}.get(path.suffix, mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    server = LocalServer(("127.0.0.1", args.port), Handler)
    server.token = secrets.token_urlsafe(32)
    server.jobs = Jobs()
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Mesh Studio is ready at {url}", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        server.jobs.close()


if __name__ == "__main__":
    main()
