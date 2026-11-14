"""HTTP boundary, upload lifecycle, range, and persistence regression tests."""
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

from web_server import Handler, Jobs, LocalServer, ROOT, validate_settings


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class WebTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tmp", prefix="web-test-")
        self.root = Path(self.temp.name)
        self.jobs = Jobs(self.root)
        self.server = LocalServer(("127.0.0.1", 0), QuietHandler)
        self.server.jobs = self.jobs
        self.server.token = "local-test-token"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .05})
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.jobs.close()
        self.assertTrue(self.root.resolve().is_relative_to((ROOT / "tmp").resolve()))
        self.temp.cleanup()

    def request(self, method, path, value=None, headers=None, raw=None):
        body = raw if raw is not None else json.dumps(value).encode() if value is not None else None
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        fields = {"X-Mesh-Token": self.server.token, **(headers or {})}
        connection.request(method, path, body=body, headers=fields)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def create(self, **extra):
        payload = {"original": {"name": "original.mp4", "size": 8}, "depth": {"name": "depth.mp4", "size": 8}, **extra}
        code, _, body = self.request("POST", "/api/jobs", payload)
        self.assertEqual(code, 201, body)
        return json.loads(body)

    def test_static_and_session_config(self):
        code, headers, body = self.request("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn(b"Create wireframe", body)
        self.assertIn("Content-Security-Policy", headers)
        code, _, body = self.request("GET", "/api/config")
        self.assertEqual(json.loads(body)["token"], self.server.token)

    def test_mutations_require_token_and_same_origin(self):
        code, _, _ = self.request("POST", "/api/jobs", {}, {"X-Mesh-Token": "wrong"})
        self.assertEqual(code, 403)
        code, _, _ = self.request("POST", "/api/jobs", {}, {"Origin": "https://unrelated.example"})
        self.assertEqual(code, 403)
        code, _, _ = self.request("GET", "/api/config", headers={"Host": "unrelated.example"})
        self.assertEqual(code, 403)

    def test_upload_size_and_start_before_both_inputs(self):
        job = self.create()
        base = f"/api/jobs/{job['id']}"
        self.assertEqual(self.request("POST", base + "/start")[0], 400)
        self.assertEqual(self.request("PUT", base + "/uploads/original", raw=b"short")[0], 400)
        self.assertEqual(self.request("PUT", base + "/uploads/original", raw=b"12345678")[0], 200)
        self.assertEqual(self.request("POST", base + "/start")[0], 400)
        self.assertEqual(self.request("PUT", base + "/uploads/original", raw=b"12345678")[0], 400)

    def test_interrupted_upload_leaves_no_completed_input(self):
        job = self.create()
        with self.assertRaisesRegex(ValueError, "interrupted"):
            self.jobs.upload(job["id"], "original", io.BytesIO(b"short"), 8)
        self.assertFalse(self.jobs.get(job["id"])["uploaded"]["original"])
        self.assertFalse(list((self.root / job["id"]).glob("*.upload")))

    def test_cancel_prevents_start_and_further_uploads(self):
        job = self.create()
        base = f"/api/jobs/{job['id']}"
        self.assertEqual(self.request("POST", base + "/cancel")[0], 200)
        self.assertEqual(self.request("POST", base + "/start")[0], 400)
        self.assertEqual(self.request("PUT", base + "/uploads/depth", raw=b"12345678")[0], 400)
        self.assertEqual(self.jobs.get(job["id"])["status"], "cancelled")

    def test_only_completed_allowlisted_artifacts_are_served(self):
        job = self.create()
        base = f"/api/jobs/{job['id']}/files/"
        self.assertEqual(self.request("GET", base + "video")[0], 404)
        (self.root / job["id"] / "depth_with_mesh.mp4").write_bytes(b"0123456789")
        self.jobs.update(job["id"], status="complete")
        self.assertEqual(self.request("GET", base + "job")[0], 404)
        code, headers, body = self.request("GET", base + "video?download=1")
        self.assertEqual(code, 200)
        self.assertEqual(body, b"0123456789")
        self.assertIn("attachment", headers["Content-Disposition"])

    def test_video_ranges_support_seeking_head_and_invalid_ranges(self):
        job = self.create()
        (self.root / job["id"] / "depth_with_mesh.mp4").write_bytes(b"0123456789")
        self.jobs.update(job["id"], status="complete")
        path = f"/api/jobs/{job['id']}/files/video"
        code, headers, body = self.request("GET", path, headers={"Range": "bytes=2-5"})
        self.assertEqual((code, body), (206, b"2345"))
        self.assertEqual(headers["Content-Range"], "bytes 2-5/10")
        self.assertEqual(self.request("GET", path, headers={"Range": "bytes=-3"})[2], b"789")
        self.assertEqual(self.request("HEAD", path)[2], b"")
        self.assertEqual(self.request("GET", path, headers={"Range": "bytes=20-"})[0], 416)
        self.assertEqual(self.request("GET", path, headers={"Range": "bytes=0-1,5-6"})[0], 416)

    def test_names_cannot_escape_job_folder_and_paths_are_not_exposed(self):
        job = self.create(original={"name": "../../outside.mp4", "size": 8})
        self.assertEqual(job["names"]["original"], "outside.mp4")
        self.assertEqual(job["files"]["original"], "original.mp4")
        self.assertEqual(self.request("GET", "/../scripts/web_server.py")[0], 404)

    def test_restart_preserves_completed_runs_and_marks_interrupted_runs(self):
        completed = self.create()
        interrupted = self.create()
        self.jobs.update(completed["id"], status="complete", result={"frames": 24})
        restored = Jobs(self.root)
        try:
            self.assertEqual(restored.get(completed["id"])["status"], "complete")
            self.assertEqual(restored.get(interrupted["id"])["status"], "failed")
        finally:
            restored.close()

    def test_invalid_numeric_settings_are_rejected(self):
        for value in ({"max_faces": True}, {"max_faces": 1.5}, {"opacity": float("nan")}, {"opacity": 2}, {"style": "invalid"}, {"color": "#nothex"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_settings(value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
