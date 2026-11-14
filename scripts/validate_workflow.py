"""Local integration checks using a generated moving two-portrait fixture.

This is a controlled test, not real multiple-person or occlusion footage.
Python socket connections/DNS are rejected during this process. Native library
networking and other processes are outside that guard's scope.
"""
from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import av
import cv2
import numpy as np

import mesh_video as workflow

ROOT = workflow.ROOT
OUT = ROOT / "outputs" / "validation"


def deny_python_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.bind", "socket.sendto"):
        raise RuntimeError(f"Python network operation rejected during validation: {event}")


def strict_decode(path):
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path),
                    "-map", "0:v:0", "-f", "null", "-"], check=True, capture_output=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sys.addaudithook(deny_python_network)
    portrait = cv2.imread(str(ROOT / "assets" / "portrait.jpg"))
    if portrait is None:
        raise RuntimeError("Local test portrait is missing")
    portrait = cv2.resize(portrait, (512, 640))
    composite = np.ascontiguousarray(np.concatenate(
        (portrait, np.zeros((640, 64, 3), np.uint8), portrait[:, ::-1]), axis=1))
    original, depth = OUT / "two_faces_original.mp4", OUT / "two_faces_depth.mp4"
    tb = Fraction(1, 25)
    with av.open(str(original), "w") as rgb_out, av.open(str(depth), "w") as depth_out:
        rgb_stream = workflow.add_stream(rgb_out, 1088, 640, 25, tb, 18)
        depth_stream = workflow.add_stream(depth_out, 544, 320, 25, tb, 18)
        for index in range(24):
            image = np.full((640, 1088, 3), 24, np.uint8)
            if 3 <= index < 21:
                shift = round(2 * np.sin((index - 3) / 5))
                image = cv2.warpAffine(composite, np.float32([[1, 0, shift], [0, 1, 0]]), (1088, 640))
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            depth_image = cv2.cvtColor(cv2.resize(gray, (544, 320)), cv2.COLOR_GRAY2BGR)
            workflow.encode_image(rgb_out, rgb_stream, image, index, tb)
            workflow.encode_image(depth_out, depth_stream, depth_image, index, tb)
        workflow.flush_stream(rgb_out, rgb_stream)
        workflow.flush_stream(depth_out, depth_stream)
    pair = workflow.inspect_pair(original, depth, OUT)
    alignment = {
        "schema_version": 1, "visually_verified": True,
        "original_sha256": pair["original"]["file"]["sha256"],
        "depth_sha256": pair["depth"]["file"]["sha256"],
        "normalized_source_to_depth_affine": [[1, 0, 0], [0, 1, 0]],
        "source_time_offset_seconds": 0, "max_timestamp_error_seconds": .001,
        "notes": "Generated test fixture with a known half-resolution transform; not OpenArt evidence."
    }
    workflow.write_json(OUT / "alignment.json", alignment)
    tracking = workflow.track(original, OUT, max_faces=4)
    counts = [len(frame["faces"]) for frame in tracking["frames"]]
    if counts != [0] * 3 + [2] * 18 + [0] * 3:
        raise AssertionError(f"Unexpected controlled-fixture detections: {counts}")
    ids = [tuple(face["track_id"] for face in frame["faces"]) for frame in tracking["frames"][3:21]]
    if len(set(ids)) != 1 or len(set(ids[0])) != 2:
        raise AssertionError(f"Two moving tracks lost continuity: {ids}")
    # Render must consume cached landmarks; creating an inference session fails.
    with patch.object(workflow, "create_landmarker", side_effect=AssertionError("Render invoked inference")):
        rendered = workflow.render(original, depth, OUT, OUT / "alignment.json", debug_preview=False)
    if rendered["frames"] != 24 or rendered["frames_with_mesh"] != 18:
        raise AssertionError("Renderer lost frames or froze a mesh over blank frames")
    strict_decode(OUT / "depth_with_mesh.mp4")
    bad_alignment = dict(alignment, depth_sha256="0" * 64)
    workflow.write_json(OUT / "wrong_alignment.json", bad_alignment)
    try:
        workflow.render(original, depth, OUT, OUT / "wrong_alignment.json", debug_preview=False)
    except ValueError as error:
        if "differs" not in str(error):
            raise
    else:
        raise AssertionError("Mismatched alignment input was accepted")
    report = {
        "status": "passed", "completed_at_utc": workflow.recorded_at(),
        "checks": {"moving_two_portrait_frames": 18, "blank_frames_without_mesh": 6,
                   "stable_separate_track_ids": list(ids[0]), "render_from_json_without_inference": True,
                   "wrong_input_hash_rejected": True, "full_ffmpeg_strict_decode": True,
                   "python_socket_guard_enabled": True},
        "limitations": ["Controlled moving portrait composite, not real multiple-person footage.",
                        "Python networking is guarded; no OS firewall or native-code isolation was tested.",
                        "Filmora import, real crossings and long occlusions need user footage/manual review."]
    }
    workflow.write_json(OUT / "validation_report.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
