"""Offline media integration checks. Model/GPU and live Colab execution are not simulated as passed."""
import importlib.util
import json
import tempfile
import unittest
import zipfile
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("depth_colab", ROOT / "notebooks/depth_anything_colab_app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class DummyDepthModel:
    def infer_image(self, frame, input_size):
        height, width = frame.shape[:2]
        return np.broadcast_to(np.linspace(1, 10, width, dtype=np.float32), (height, width)).copy()


class ColabMediaTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="depth-colab-qa-", dir=ROOT / "tmp")
        self.folder = Path(self.temp.name)
        self.source = self.folder / "test source.mp4"
        app.run_command([
            "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
            "testsrc2=size=160x96:rate=30000/1001", "-frames:v", "12",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", self.source,
        ])
        self.root_patch = patch.object(app, "ROOT", self.folder)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def test_notebook_is_standalone_and_compiles(self):
        notebook = json.loads((ROOT / "notebooks/Depth_Anything_V2_Video_GUI.ipynb").read_text(encoding="utf-8"))
        self.assertEqual(notebook["nbformat"], 4)
        app_source = (ROOT / "notebooks/depth_anything_colab_app.py").read_text(encoding="utf-8")
        self.assertTrue(any(app_source in "".join(c["source"]) for c in notebook["cells"]))
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), "notebook cell", "exec")
                self.assertIsNone(cell["execution_count"])
                self.assertEqual(cell["outputs"], [])

    def test_full_pipeline_fractional_fps_and_matching_bundle(self):
        progress = []
        with patch.object(app, "load_model", return_value=DummyDepthModel()):
            result = app.convert_video(
                self.source, "Small", 518, "Whole video (fixed contrast)", False, False, 0,
                progress=lambda value, **kw: progress.append(value),
            )
        depth, reference, _, _, bundle, message = result
        rgb, dep = app.probe(reference, True), app.probe(depth, True)
        self.assertEqual(app.frame_rate(dep), Fraction(30000, 1001))
        self.assertEqual(int(dep["nb_read_frames"]), 12)
        self.assertEqual((dep["width"], dep["height"]), (160, 96))
        self.assertEqual(dep["nb_read_frames"], rgb["nb_read_frames"])
        self.assertIn("Done", message)
        self.assertEqual(progress[-1], 1)
        self.assertFalse((Path(depth).parent / "depth_cache").exists())
        cap = cv2.VideoCapture(depth)
        ok, image = cap.read()
        cap.release()
        self.assertTrue(ok)
        self.assertLess(float(image[:, :10].mean()), float(image[:, -10:].mean()))
        self.assertLess(int(np.max(np.abs(image[:, :, 0].astype(int) - image[:, :, 2].astype(int)))), 3)
        with zipfile.ZipFile(bundle) as archive:
            self.assertEqual(set(archive.namelist()), {"depth.mp4", "source_reference.mp4", "report.json", "READ_ME.txt"})
            report = json.loads(archive.read("report.json"))
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["frame_count"], 12)
            self.assertEqual(report["fps"], "30000/1001")
        with self.assertRaisesRegex(RuntimeError, "frame count"):
            app.verify_pair(reference, depth, 13)

    def test_preview_color_and_inverse_export(self):
        with patch.object(app, "load_model", return_value=DummyDepthModel()):
            result = app.convert_video(self.source, "Small", 392, "Per frame (stronger contrast)", True, True, 0.2)
        report = json.loads((Path(result[0]).parent / "report.json").read_text())
        self.assertEqual(report["frame_count"], 6)
        self.assertTrue(report["colored"])
        self.assertEqual(app.frame_rate(app.probe(result[0])), Fraction(30000, 1001))

    def test_rotation_and_pixel_aspect_are_normalized(self):
        rotated = self.folder / "rotated.mp4"
        app.run_command(["ffmpeg", "-v", "error", "-y", "-display_rotation", "90", "-i", self.source,
                         "-c", "copy", rotated])
        self.assertEqual(app.probe(rotated)["side_data_list"][0]["rotation"], 90)
        info = app.normalize_video(rotated, self.folder / "upright.mp4")
        self.assertEqual((info["width"], info["height"]), (96, 160))
        self.assertEqual(info["sample_aspect_ratio"], "1:1")
        anamorphic = self.folder / "sar.mp4"
        app.run_command(["ffmpeg", "-v", "error", "-y", "-i", self.source,
                         "-vf", "setsar=2", "-c:v", "libx264", anamorphic])
        info = app.normalize_video(anamorphic, self.folder / "square.mp4")
        self.assertEqual((info["width"], info["height"]), (320, 96))
        self.assertEqual(info["sample_aspect_ratio"], "1:1")
        odd = self.folder / "odd.mp4"
        app.run_command(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                         "testsrc=size=161x95:rate=30", "-frames:v", "3", "-c:v", "libx264",
                         "-pix_fmt", "yuv444p", odd])
        info = app.normalize_video(odd, self.folder / "even.mp4")
        self.assertEqual((info["width"], info["height"]), (162, 96))

    def test_variable_frame_rate_becomes_matching_constant_timestamps(self):
        vfr = self.folder / "variable.mp4"
        app.run_command([
            "ffmpeg", "-v", "error", "-y", "-i", self.source,
            "-vf", "setpts='if(lt(N,6),N,2*N-6)/(30*TB)'", "-fps_mode", "vfr",
            "-c:v", "libx264", "-video_track_timescale", "30000", vfr,
        ])
        with patch.object(app, "load_model", return_value=DummyDepthModel()):
            result = app.convert_video(vfr, "Small", 392, "Whole video (fixed contrast)", False, False, 0)
        def timestamps(path):
            data = json.loads(app.run_command([
                "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames",
                "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", path,
            ]))
            return np.array([float(f["best_effort_timestamp_time"]) for f in data["frames"]])
        rgb, dep = timestamps(result[1]), timestamps(result[0])
        np.testing.assert_allclose(dep, rgb, atol=1e-6)
        self.assertLess(float(np.ptp(np.diff(rgb))), 2e-6)
        self.assertGreater(float(np.ptp(np.diff(timestamps(vfr)))), 0.01)

    def test_constant_depth_and_invalid_values(self):
        constant = np.full((12, 24), 5, np.float32)
        normal = app.depth_to_bgr(constant, 5, 5)
        reverse = app.depth_to_bgr(constant, 5, 5, True)
        self.assertTrue(np.all(normal == 0))
        self.assertTrue(np.all(reverse == 255))
        with self.assertRaisesRegex(RuntimeError, "invalid depth"):
            app.depth_to_bgr(np.array([[float("nan")]]), 0, 1)

    def test_failed_inference_cleans_cache_and_does_not_deliver(self):
        class InvalidModel:
            def infer_image(self, frame, input_size):
                return np.full(frame.shape[:2], float("nan"), dtype=np.float32)
        with patch.object(app, "load_model", return_value=InvalidModel()):
            with self.assertRaisesRegex(RuntimeError, "Invalid model output"):
                app.convert_video(self.source, "Small", 518, "Whole video (fixed contrast)", False, False, 0)
        self.assertEqual(list((self.folder / "outputs").glob("*/depth_cache")), [])
        self.assertEqual(list((self.folder / "outputs").glob("*/depth_video_bundle.zip")), [])
        with self.assertRaisesRegex(ValueError, "Upload"):
            app.convert_video(None, "Small", 518, "Whole video (fixed contrast)", False, False, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
