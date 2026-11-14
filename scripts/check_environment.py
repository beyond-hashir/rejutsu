"""Exercise local model inference, mesh drawing and H.264 video I/O.

This is an environment smoke test, not the production video tracker.
It uses Google's downloaded sample portrait and never uploads files.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "setup"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if sys.version_info[:3] != (3, 12, 13):
        raise RuntimeError("Expected project Python 3.12.13; run scripts/setup.ps1")
    if not Path(sys.base_prefix).resolve().is_relative_to((ROOT / '.runtime' / 'python').resolve()):
        raise RuntimeError("Python environment belongs to another location; run scripts/setup.ps1 to rebuild it")
    for name, expected in re.findall(r'^([a-zA-Z0-9_.-]+)==([^\s\\]+)', (ROOT / 'requirements.lock').read_text(), re.MULTILINE):
        if importlib.metadata.version(name) != expected:
            raise RuntimeError(f"{name} differs from requirements.lock; run scripts/setup.ps1")
    print("Importing native libraries...", flush=True)
    import av
    import cv2
    import mediapipe as mp
    import numpy as np
    from mediapipe.tasks import python as task_python
    from mediapipe.tasks.python import vision

    cv2.setNumThreads(2)
    model_path = ROOT / "models" / "face_landmarker.task"
    manifest = json.loads((ROOT / "models" / "manifest.json").read_text("utf-8-sig"))
    actual_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if actual_hash != '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff' or actual_hash != manifest["model"]["sha256"]:
        raise RuntimeError("Model SHA-256 does not match the download manifest")

    portrait = cv2.imread(str(ROOT / "assets" / "portrait.jpg"))
    if portrait is None:
        raise RuntimeError("Could not decode the sample portrait")
    scale = min(1.0, 640 / max(portrait.shape[:2]))
    portrait = cv2.resize(portrait, None, fx=scale, fy=scale)
    # yuv420p H.264 requires even dimensions.
    portrait = portrait[: portrait.shape[0] // 2 * 2, : portrait.shape[1] // 2 * 2]
    rgb = cv2.cvtColor(portrait, cv2.COLOR_BGR2RGB)
    gap = np.zeros((rgb.shape[0], 64, 3), dtype=np.uint8)
    two_faces = np.ascontiguousarray(np.concatenate((rgb, gap, rgb[:, ::-1]), axis=1))

    inference = {}
    mesh_frame = None
    for label, image, max_faces, expected_faces in (
        ("single_face", rgb, 1, 1),
        ("two_faces", two_faces, 2, 2),
    ):
        print(f"Running {label} CPU inference...", flush=True)
        options = vision.FaceLandmarkerOptions(
            base_options=task_python.BaseOptions(
                model_asset_path=str(model_path),
                delegate=task_python.BaseOptions.Delegate.CPU,
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=max_faces,
        )
        elapsed_ms = []
        counts = []
        with vision.FaceLandmarker.create_from_options(options) as landmarker:
            for timestamp_ms in (0, 40, 80):
                started = time.perf_counter()
                result = landmarker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=image), timestamp_ms
                )
                elapsed_ms.append(round((time.perf_counter() - started) * 1000, 2))
                counts.append(len(result.face_landmarks))
                if counts[-1] != expected_faces:
                    raise RuntimeError(f"{label}: expected {expected_faces} face(s), got {counts[-1]}")
                if any(len(face) != 478 for face in result.face_landmarks):
                    raise RuntimeError("Unexpected landmark count")

        inference[label] = {
            "faces_per_frame": counts,
            "landmarks_per_face": 478,
            "inference_ms": elapsed_ms,
            "note": "Repeated sample images; not a real-motion benchmark or continuity test.",
        }
        drawn = image.copy()
        height, width = image.shape[:2]
        for face in result.face_landmarks:
            points = [(round(point.x * width), round(point.y * height)) for point in face]
            for edge in vision.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION:
                cv2.line(drawn, points[edge.start], points[edge.end], (0, 255, 255), 1, cv2.LINE_AA)
        if label == "two_faces":
            mesh_frame = drawn
        cv2.imwrite(str(OUTPUT / f"{label}_mesh.jpg"), cv2.cvtColor(drawn, cv2.COLOR_RGB2BGR))

    print("Encoding and decoding a short H.264 MP4...", flush=True)
    video_path = OUTPUT / "codec_smoke_test.mp4"
    with av.open(str(video_path), mode="w") as container:
        stream = container.add_stream("libx264", rate=25)
        stream.width = mesh_frame.shape[1]
        stream.height = mesh_frame.shape[0]
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": "18", "preset": "fast"}
        stream.time_base = Fraction(1, 25)
        stream.codec_context.time_base = Fraction(1, 25)
        for index in range(8):
            frame = av.VideoFrame.from_ndarray(mesh_frame, format="rgb24")
            frame.pts = index
            frame.time_base = Fraction(1, 25)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)

    with av.open(str(video_path)) as container:
        frames = list(container.decode(video=0))
        frame_times = [float(frame.pts * frame.time_base) for frame in frames]
    if len(frames) != 8 or any(abs(actual - index / 25) > 0.00001 for index, actual in enumerate(frame_times)):
        raise RuntimeError("Encoded video failed its frame-count/timestamp check")

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe is not available on PATH")
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
         "stream=codec_name,width,height,nb_read_frames,duration", "-of", "json", str(video_path)],
        check=True, capture_output=True, text=True,
    )
    probe_result = json.loads(probe.stdout)
    if probe_result["streams"][0]["nb_read_frames"] != "8":
        raise RuntimeError("Independent ffprobe frame-count check failed")

    report = {
        "status": "passed",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": {dist.metadata["Name"]: dist.version for dist in importlib.metadata.distributions()},
        "model_sha256": actual_hash,
        "inference": inference,
        "opencv": cv2.__version__,
        "pyav_ffmpeg_libraries": {key: list(value) for key, value in av.library_versions.items()},
        "external_ffmpeg": shutil.which("ffmpeg"),
        "external_ffprobe": ffprobe,
        "video_probe": probe_result,
        "decoded_frame_times_seconds": frame_times,
        "limitations": [
            "This check uses sample portraits, not the user's video or its source/depth alignment.",
            "Crossings, long occlusions, editor import and downstream generation need separate review.",
            "This check performs no downloads/uploads; it does not enforce OS-level network isolation.",
        ],
    }
    report_path = OUTPUT / "environment_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "inference": inference, "report": str(report_path)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
