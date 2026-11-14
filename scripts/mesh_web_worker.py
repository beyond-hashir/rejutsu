"""Isolated job runner for the local Mesh Studio interface."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback

import mesh_video as mesh
from mesh_core import match_time


def event(stage, progress, message, **extra):
    print("MESH_EVENT " + json.dumps({"stage": stage, "progress": progress, "message": message, **extra}), flush=True)


class ProgressWriter:
    def __init__(self, stream):
        self.stream = stream
        self.pending = ""

    def write(self, value):
        import re
        self.stream.write(value)
        self.pending += value
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            match = re.match(r"(Tracked|Rendered) (\d+)/(\d+)", line)
            if match:
                mode, done, total = match.groups()
                fraction = int(done) / int(total)
                if mode == "Tracked":
                    event("tracking", round(12 + fraction * 38), f"Tracking facial motion · {done} of {total} frames")
                else:
                    event("rendering", round(52 + fraction * 40), f"Drawing your wireframe · {done} of {total} frames")
        return len(value)

    def flush(self):
        self.stream.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job", type=Path)
    args = parser.parse_args()
    config = json.loads(args.job.read_text("utf-8"))
    out = args.job.parent
    original, depth = out / config["files"]["original"], out / config["files"]["depth"]
    settings = config["settings"]
    # Output interception only adds progress events; the existing engine remains authoritative.
    sys.stdout = ProgressWriter(sys.stdout)
    try:
        event("checking", 4, "Checking video timing and dimensions")
        pair = mesh.inspect_pair(original, depth, out)
        source, target = pair["original"], pair["depth"]
        if not pair["same_display_aspect"]:
            raise ValueError("These clips have different framing proportions. Export the depth video with the same aspect ratio as the original, then try again.")
        if target["width"] % 2 or target["height"] % 2:
            raise ValueError("The depth video needs even pixel dimensions for MP4 export. Resize it by one pixel, then try again.")
        if abs(pair["duration_difference_seconds"]) > .075:
            raise ValueError("The clips have different lengths. Use the untrimmed original and its matching depth export.")
        times = [frame["time"] for frame in source["frames"]]
        for frame in target["frames"]:
            match_time(times, frame["time"], .051)
        alignment = {
            "schema_version": 1, "visually_verified": False,
            "mapping_policy": "assume_matching_framing",
            "original_sha256": source["file"]["sha256"], "depth_sha256": target["file"]["sha256"],
            "normalized_source_to_depth_affine": [[1, 0, 0], [0, 1, 0]],
            "source_time_offset_seconds": 0, "max_timestamp_error_seconds": .051,
            "notes": "Local UI one-button workflow: user supplies a matching original/depth pair. Dimensions and timing checked; identical crop/framing is assumed, not visually verified. Review the output preview."
        }
        mesh.write_json(out / "alignment.json", alignment)
        event("tracking", 12, "Finding faces in your original video")
        tracking = mesh.track(original, out, settings["max_faces"], settings["smoothing_ms"])
        if not any(frame["faces"] for frame in tracking["frames"]):
            raise ValueError("No faces were detected in the original video. Try a clip with a larger, clearly visible face.")
        event("rendering", 52, "Drawing the wireframe on your depth video")
        report = mesh.render(original, depth, out, out / "alignment.json",
                             style=settings["style"], opacity=settings["opacity"], thickness=settings["thickness"],
                             color=tuple(bytes.fromhex(settings["color"])[::-1]),
                             debug_preview=True, allow_assumed_alignment=True)
        event("verifying", 96, "Checking your finished videos")
        missing = report["frames"] - report["frames_with_mesh"]
        result = {
            "width": target["width"], "height": target["height"], "frames": report["frames"],
            "duration": report["duration_seconds"], "mesh_frames": report["frames_with_mesh"],
            "missing_frames": missing, "bytes": (out / "depth_with_mesh.mp4").stat().st_size,
            "notes": ([f"No mesh on {missing} frames where a face wasn't detected. Review turns and obscured faces."] if missing else [])
                     + ["Framing is assumed to match. Check the comparison if either clip was cropped, mirrored or trimmed."]
        }
        mesh.write_json(out / "web_result.json", result)
        event("complete", 100, "Your wireframe video is ready", result=result)
    except Exception as error:
        event("failed", 0, str(error))
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
