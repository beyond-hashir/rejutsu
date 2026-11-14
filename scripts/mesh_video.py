"""Inspect a video pair, track original RGB faces, and render on verified depth footage."""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

import av
import cv2
import numpy as np

from mesh_core import FaceAssociator, match_time, transform_xy

ROOT = Path(__file__).resolve().parents[1]


def recorded_at():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def fingerprint(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def probe(path):
    executable = shutil.which("ffprobe")
    if executable is None:
        raise RuntimeError("ffprobe is required")
    result = subprocess.run([executable, "-v", "error", "-show_streams", "-show_format",
                             "-of", "json", str(path)], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def inspect_video(path):
    metadata = probe(path)
    stream = next(item for item in metadata["streams"] if item["codec_type"] == "video")
    rotation = next((item.get("rotation", 0) for item in stream.get("side_data_list", [])
                     if "rotation" in item), float(stream.get("tags", {}).get("rotate", 0)))
    if rotation % 360:
        raise ValueError("Rotated footage needs an orientation-normalized working copy before this workflow")
    if stream.get("sample_aspect_ratio", "1:1") not in ("1:1", "N/A", "0:1"):
        raise ValueError("Non-square pixels require a display-normalized working copy")
    frames = []
    with av.open(str(path)) as container:
        for index, frame in enumerate(container.decode(video=0)):
            if frame.pts is None:
                raise ValueError("Missing presentation timestamp")
            frames.append({"index": index, "pts": frame.pts, "time_base": str(frame.time_base),
                           "absolute_time": float(frame.pts * frame.time_base),
                           "duration": int(frame.duration or 0)})
    if not frames:
        raise ValueError("No decoded video frames")
    start = frames[0]["absolute_time"]
    for frame in frames:
        frame["time"] = frame["absolute_time"] - start
    deltas = [b["time"] - a["time"] for a, b in zip(frames, frames[1:])]
    if any(delta <= 0 for delta in deltas):
        raise ValueError("Video presentation timestamps are not strictly increasing")
    tail_duration = frames[-1]["duration"] * float(Fraction(frames[-1]["time_base"]))
    if tail_duration <= 0:
        tail_duration = float(np.median(deltas)) if deltas else 1 / float(Fraction(stream["avg_frame_rate"]))
    return {"file": fingerprint(path), "width": stream["width"], "height": stream["height"],
            "rotation": rotation, "average_rate": stream["avg_frame_rate"], "time_base": stream["time_base"],
            "decoded_frames": len(frames), "presentation_start": start,
            "duration": frames[-1]["time"] + tail_duration, "frames": frames,
            "large_gaps": [{"index": index, "delta_seconds": delta} for index, delta in enumerate(deltas)
                           if delta > 1.5 * float(np.median(deltas))], "ffprobe": metadata}


def inspect_pair(original, depth, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    data = {"schema_version": 1, "original": inspect_video(original), "depth": inspect_video(depth)}
    original_info, depth_info = data["original"], data["depth"]
    data["same_display_aspect"] = abs(original_info["width"] / original_info["height"] -
                                            depth_info["width"] / depth_info["height"]) < 0.00001
    data["duration_difference_seconds"] = depth_info["duration"] - original_info["duration"]
    data["spatial_verification"] = "Required: review contact sheet; metadata alone does not establish matching crop."
    targets = np.linspace(0, max(0, min(original_info["duration"], depth_info["duration"]) - 0.1), 8)
    tile_w, tile_h = 270, 480
    canvas = np.zeros((4 * (tile_h + 32), 4 * tile_w, 3), dtype=np.uint8)
    for side, key in enumerate(("original", "depth")):
        info = data[key]
        times = [frame["time"] for frame in info["frames"]]
        selected = {target_index: match_time(times, float(target), 0.12) for target_index, target in enumerate(targets)}
        with av.open(str(info["file"]["path"])) as container:
            for index, frame in enumerate(container.decode(video=0)):
                for slot, selected_index in selected.items():
                    if index == selected_index:
                        image = frame.to_ndarray(format="bgr24")
                        factor = min(tile_w / image.shape[1], tile_h / image.shape[0])
                        image = cv2.resize(image, None, fx=factor, fy=factor)
                        x = (slot % 2) * 2 * tile_w + side * tile_w
                        y = (slot // 2) * (tile_h + 32)
                        canvas[y + 32:y + 32 + image.shape[0], x:x + image.shape[1]] = image
                        cv2.putText(canvas, f"{key} {times[index]:.3f}s", (x + 5, y + 22),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(out / "alignment_contact_sheet.jpg"), canvas)
    write_json(out / "compatibility_report.json", data)
    # Never replace a review already recorded for this output directory.
    if not (out / "alignment.json").exists():
        write_json(out / "alignment.json", {
            "schema_version": 1, "visually_verified": False,
            "original_sha256": original_info["file"]["sha256"],
            "depth_sha256": depth_info["file"]["sha256"],
            "normalized_source_to_depth_affine": [[1, 0, 0], [0, 1, 0]],
            "source_time_offset_seconds": 0, "max_timestamp_error_seconds": 0.051,
            "notes": "Proposed identity mapping only. Review alignment_contact_sheet.jpg before setting visually_verified to true."
        })
    print(json.dumps({"original_frames": original_info["decoded_frames"], "depth_frames": depth_info["decoded_frames"],
                      "same_display_aspect": data["same_display_aspect"],
                      "duration_difference_seconds": data["duration_difference_seconds"],
                      "contact_sheet": str(out / "alignment_contact_sheet.jpg")}, indent=2), flush=True)
    return data


def create_landmarker(max_faces, running_mode="VIDEO"):
    import mediapipe as mp
    from mediapipe.tasks import python as task_python
    from mediapipe.tasks.python import vision
    model = ROOT / "models" / "face_landmarker.task"
    manifest = json.loads((ROOT / "models" / "manifest.json").read_text("utf-8-sig"))
    if hashlib.sha256(model.read_bytes()).hexdigest() != manifest["model"]["sha256"]:
        raise RuntimeError("Model integrity check failed")
    options = vision.FaceLandmarkerOptions(
        base_options=task_python.BaseOptions(model_asset_path=str(model), delegate=task_python.BaseOptions.Delegate.CPU),
        running_mode=getattr(vision.RunningMode, running_mode), num_faces=max_faces,
        output_facial_transformation_matrixes=True,
    )
    return mp, vision.FaceLandmarker.create_from_options(options), manifest["model"]


def candidate_cut(previous, current):
    if previous is None:
        return False, 0.0
    change = float(np.mean(np.abs(current.astype(np.float32) - previous.astype(np.float32))) / 255)
    before = cv2.calcHist([previous], [0], None, [32], [0, 256])
    after = cv2.calcHist([current], [0], None, [32], [0, 256])
    histogram_distance = cv2.compareHist(cv2.normalize(before, None), cv2.normalize(after, None), cv2.HISTCMP_BHATTACHARYYA)
    return bool(change > 0.16 and histogram_distance > 0.12), change


def quality_flags(points, pose):
    flags = []
    points = np.asarray(points)
    if not np.isfinite(points).all():
        return ["invalid_landmarks"], False, None
    size = np.ptp(points[:, :2], axis=0)
    if min(size) <= 0.002 or float(np.prod(size)) < 0.0001:
        return ["face_too_small"], False, None
    if np.any(points[:, :2] < 0) or np.any(points[:, :2] > 1):
        flags.append("face_partly_outside_frame")
    yaw = None
    if pose is not None:
        rotation = np.asarray(pose)[:3, :3]
        yaw = math.degrees(math.atan2(-rotation[2, 0], math.hypot(rotation[0, 0], rotation[1, 0])))
        if abs(yaw) > 65:
            flags.append("strong_profile_review")
    return flags, True, yaw


def recover_crop(rgb, previous_face, mp, landmarker):
    """Fresh image detection in a recent face ROI; no extrapolated landmark output."""
    previous = np.asarray(previous_face["raw_landmarks"])
    lo, hi = previous[:, :2].min(axis=0), previous[:, :2].max(axis=0)
    margin = (hi - lo) * 0.5
    height, width = rgb.shape[:2]
    x0, y0 = np.floor(np.maximum(lo - margin, 0) * (width, height)).astype(int)
    x1, y1 = np.ceil(np.minimum(hi + margin, 1) * (width, height)).astype(int)
    crop = np.ascontiguousarray(rgb[y0:y1, x0:x1])
    if crop.size == 0:
        return None
    result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=crop))
    if not result.face_landmarks:
        return None
    points = [[(point.x * (x1 - x0) + x0) / width,
               (point.y * (y1 - y0) + y0) / height,
               point.z * (x1 - x0) / width] for point in result.face_landmarks[0]]
    pose = result.facial_transformation_matrixes[0] if result.facial_transformation_matrixes else None
    flags, valid, yaw = quality_flags(points, pose)
    if not valid or len(points) != 478:
        return None
    return {"raw_landmarks": np.round(points, 7).tolist(), "quality_flags": flags + ["crop_recovery"],
            "estimated_yaw_degrees": None if yaw is None else round(yaw, 2), "origin": "crop_redetection"}


def track(original, out, max_faces=4, smoothing_ms=12):
    if not 1 <= max_faces <= 8:
        raise ValueError("Choose --max-faces between 1 and 8")
    out = Path(out)
    info = inspect_video(original)
    cv2.setNumThreads(2)
    associator = FaceAssociator(smoothing_ms=smoothing_ms if max_faces > 1 else 0)
    mp, landmarker, model = create_landmarker(max_faces)
    recovery_landmarker = None
    frames = []
    cuts = []
    previous = None
    shot_id = 0
    counts = Counter()
    started = time.perf_counter()
    model_timestamp = -1
    try:
        with av.open(str(original)) as container:
            for index, frame in enumerate(container.decode(video=0)):
                meta = info["frames"][index]
                rgb = frame.to_ndarray(format="rgb24")
                thumb = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (96, 96))
                cut, change = candidate_cut(previous, thumb)
                if cut:
                    shot_id += 1
                    cuts.append({"frame": index, "time": meta["time"], "mean_change": change})
                    associator.reset()
                    landmarker.close()
                    mp, landmarker, _ = create_landmarker(max_faces)
                previous = thumb
                infer_scale = min(1.0, 1280 / max(rgb.shape[:2]))
                inference_rgb = cv2.resize(rgb, None, fx=infer_scale, fy=infer_scale) if infer_scale < 1 else rgb
                model_timestamp = max(model_timestamp + 1, round(meta["time"] * 1000))
                result = landmarker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(inference_rgb)),
                    model_timestamp,
                )
                detections = []
                rejected = []
                for face_index, face in enumerate(result.face_landmarks):
                    points = [[float(point.x), float(point.y), float(point.z)] for point in face]
                    pose = result.facial_transformation_matrixes[face_index] if result.facial_transformation_matrixes else None
                    flags, valid, yaw = quality_flags(points, pose)
                    if not valid or len(points) != 478:
                        rejected.append(flags or ["unexpected_landmark_count"])
                        continue
                    detections.append({"raw_landmarks": np.round(points, 7).tolist(), "quality_flags": flags,
                                       "estimated_yaw_degrees": None if yaw is None else round(yaw, 2),
                                       "origin": "full_frame"})
                # One-frame retry only, never across a cut or following another recovery.
                # This is a fresh model detection on current pixels, not a held/interpolated face.
                if not detections and frames and not cut and meta["time"] - frames[-1]["time"] <= 0.051:
                    for previous_face in frames[-1]["faces"]:
                        if previous_face.get("origin") != "full_frame":
                            continue
                        if recovery_landmarker is None:
                            _, recovery_landmarker, _ = create_landmarker(1, "IMAGE")
                        recovered = recover_crop(rgb, previous_face, mp, recovery_landmarker)
                        if recovered is not None:
                            detections.append(recovered)
                faces = associator.update(detections, meta["time"])
                counts[len(faces)] += 1
                frames.append({**meta, "shot_id": shot_id, "faces": faces,
                               "status": "detected" if faces else "no_face_detected", "rejected": rejected})
                if index % 60 == 0:
                    print(f"Tracked {index + 1}/{info['decoded_frames']} frames; {len(faces)} face(s)", flush=True)
    finally:
        landmarker.close()
        if recovery_landmarker is not None:
            recovery_landmarker.close()
    report = {"schema_version": 1, "completed_at_utc": recorded_at(),
              "software": {name: importlib.metadata.version(name) for name in ("mediapipe", "numpy", "av", "opencv-contrib-python")},
              "source": {key: value for key, value in info.items() if key != "ffprobe" and key != "frames"},
              "model": model, "settings": {"max_faces": max_faces, "smoothing_ms": smoothing_ms if max_faces > 1 else 0,
                                           "max_inference_dimension": 1280, "interpolation": "disabled",
                                           "isolated_missing_frame_crop_redetection": True},
              "frames": frames, "summary": {"source_frames": len(frames), "frames_by_face_count": dict(sorted(counts.items())),
                 "shot_boundaries": cuts, "track_ids": sorted({face['track_id'] for entry in frames for face in entry['faces']}),
                 "ambiguous_associations": sum(face["association_ambiguous"] for entry in frames for face in entry["faces"]),
                 "profile_review_frames": sum(any('strong_profile_review' in face['quality_flags'] for face in entry['faces']) for entry in frames),
                 "crop_recoveries": sum(face.get("origin") == "crop_redetection" for entry in frames for face in entry["faces"]),
                 "elapsed_seconds": round(time.perf_counter() - started, 2)}}
    write_json(out / "face_landmarks.json", report)
    write_json(out / "tracking_report.json", {key: value for key, value in report.items() if key != "frames"})
    write_tracking_review(original, out, frames, info["duration"])
    print(json.dumps(report["summary"], indent=2), flush=True)
    return report


def write_tracking_review(original, out, frames, duration):
    """Record gaps and show actual current pixels at gaps and crop retries."""
    ranges = []
    start = None
    for index in range(len(frames) + 1):
        missing = index < len(frames) and not frames[index]["faces"]
        if missing and start is None:
            start = index
        if not missing and start is not None:
            ranges.append({"first": start, "last": index - 1,
                           "start_s": frames[start]["time"], "end_s": frames[index - 1]["time"],
                           "end_exclusive_s": frames[index]["time"] if index < len(frames) else duration})
            start = None
    write_json(Path(out) / "missing_detection_ranges.json", ranges)
    selected = {}
    for gap in ranges[:8]:
        for index in (gap["first"], (gap["first"] + gap["last"]) // 2, gap["last"]):
            selected[index] = "no detection"
    for entry in frames:
        if len(selected) < 30 and any(face.get("origin") == "crop_redetection" for face in entry["faces"]):
            selected[entry["index"]] = "fresh crop detection"
    if not selected:
        selected[0] = "no missing detections"
    selected = dict(sorted(selected.items()))
    sheet = np.zeros((math.ceil(len(selected) / 3) * 512, 810, 3), np.uint8)
    with av.open(str(original)) as container:
        for index, frame in enumerate(container.decode(video=0)):
            if index not in selected:
                continue
            slot = list(selected).index(index)
            x, y = slot % 3 * 270, slot // 3 * 512
            image = frame.to_ndarray(format="bgr24")
            image = draw_faces(image, frames[index]["faces"], [[1, 0, 0], [0, 1, 0]], connections("contours"))
            factor = min(270 / image.shape[1], 480 / image.shape[0])
            image = cv2.resize(image, None, fx=factor, fy=factor)
            sheet[y + 32:y + 32 + image.shape[0], x:x + image.shape[1]] = image
            cv2.putText(sheet, f"{frames[index]['time']:.3f}s {selected[index]}", (x + 3, y + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, .42, (255, 255, 255), 1, cv2.LINE_AA)
    if not cv2.imwrite(str(Path(out) / "tracking_review.jpg"), sheet):
        raise RuntimeError("Could not write tracking review image")


def connections(style):
    from mediapipe.tasks.python import vision
    topology = vision.FaceLandmarksConnections
    edges = []
    if style == "mesh":
        edges.extend(topology.FACE_LANDMARKS_TESSELATION)
    elif style == "contours":
        for name in ("FACE_LANDMARKS_LIPS", "FACE_LANDMARKS_LEFT_EYE", "FACE_LANDMARKS_RIGHT_EYE",
                     "FACE_LANDMARKS_LEFT_EYEBROW", "FACE_LANDMARKS_RIGHT_EYEBROW", "FACE_LANDMARKS_FACE_OVAL"):
            edges.extend(getattr(topology, name))
    return sorted({tuple(sorted((edge.start, edge.end))) for edge in edges})


def draw_faces(image, faces, matrix, edges, opacity=0.8, thickness=1, dots=False, debug=False, color=(255, 255, 0)):
    overlay = image.copy()
    height, width = image.shape[:2]
    for face in faces:
        xy = transform_xy(face["landmarks"], matrix, width, height)
        for start, end in edges:
            cv2.line(overlay, tuple(xy[start]), tuple(xy[end]), color, thickness, cv2.LINE_AA)
        if dots or not edges:
            for point in xy:
                cv2.circle(overlay, tuple(point), 1, color, -1, cv2.LINE_AA)
    result = cv2.addWeighted(overlay, opacity, image, 1 - opacity, 0)
    if debug:
        for face in faces:
            xy = transform_xy(face["landmarks"], matrix, width, height)
            x, y = np.maximum(xy.min(axis=0), (0, 22))
            label = f"Track {face['track_id']}" + (" ?" if face['association_ambiguous'] else "")
            cv2.putText(result, label, (int(x), int(y) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (0, 255, 255), 1, cv2.LINE_AA)
    return result


def add_stream(container, width, height, rate, time_base, crf):
    stream = container.add_stream("libx264", rate=rate)
    stream.width, stream.height = width, height
    stream.pix_fmt = "yuv420p"
    stream.time_base = time_base
    stream.codec_context.time_base = time_base
    stream.codec_context.thread_count = 2
    stream.options = {"crf": str(crf), "preset": "fast"}
    return stream


def encode_image(container, stream, image, pts, time_base):
    frame = av.VideoFrame.from_ndarray(image, format="bgr24")
    frame.pts, frame.time_base = pts, time_base
    for packet in stream.encode(frame):
        container.mux(packet)


def flush_stream(container, stream):
    for packet in stream.encode():
        container.mux(packet)


def render(original, depth, out, alignment_path, style="mesh", opacity=0.8, thickness=1, dots=False,
           debug_preview=True, only_tracks=None, color=(255, 255, 0), allow_assumed_alignment=False):
    out = Path(out)
    alignment = json.loads(Path(alignment_path).read_text("utf-8-sig"))
    assumed = allow_assumed_alignment and alignment.get("mapping_policy") == "assume_matching_framing"
    if not alignment.get("visually_verified") and not assumed:
        raise ValueError("Review the pair's contact sheet and record visually_verified in the alignment file first")
    tracking = json.loads((out / "face_landmarks.json").read_text("utf-8"))
    original_hash = fingerprint(original)["sha256"]
    if original_hash != tracking["source"]["file"]["sha256"] or original_hash != alignment["original_sha256"]:
        raise ValueError("Original video differs from the reviewed/tracked input")
    info = inspect_video(depth)
    if info["file"]["sha256"] != alignment["depth_sha256"]:
        raise ValueError("Depth video differs from the reviewed input")
    matrix = alignment["normalized_source_to_depth_affine"]
    transform_xy([[0, 0, 0]], matrix, info["width"], info["height"])
    times = [entry["time"] for entry in tracking["frames"]]
    offset = float(alignment.get("source_time_offset_seconds", 0))
    tolerance = float(alignment.get("max_timestamp_error_seconds", 0.051))
    if abs(info["duration"] - tracking["source"]["duration"]) > 0.075 and not alignment.get("allow_duration_difference", False):
        raise ValueError("Duration mismatch requires an explicit reviewed time mapping")
    mapping = [match_time(times, frame["time"] + offset, tolerance) for frame in info["frames"]]
    expected_times = [frame["time"] for frame in info["frames"]]
    frame_errors = [abs(times[index] - expected_times[depth_index] - offset) for depth_index, index in enumerate(mapping)]
    edges = connections(style)
    selected = set(only_tracks or [])
    clean_path = out / "depth_with_mesh.mp4"
    temporary = out / "depth_with_mesh.partial.mp4"
    preview_path = out / "comparison_preview.mp4"
    preview_temporary = out / "comparison_preview.partial.mp4"
    source = av.open(str(original))
    source_decoder = iter(source.decode(video=0))
    source_index = -1
    source_image = None
    input_start_pts = info["frames"][0]["pts"]
    time_base = Fraction(info["time_base"])
    rate = Fraction(info["average_rate"])
    samples = set(np.linspace(0, len(mapping) - 1, 8, dtype=int).tolist())
    sheet = np.zeros((4 * 512, 1080, 3), dtype=np.uint8)
    sample_number = 0
    frames_with_mesh = 0
    face_counts = Counter()
    preview = av.open(str(preview_temporary), "w") if debug_preview else None
    preview_stream = add_stream(preview, 720, 672, rate, time_base, 20) if preview else None
    started = time.perf_counter()
    try:
        with av.open(str(depth)) as input_container, av.open(str(temporary), "w") as output:
            output_stream = add_stream(output, info["width"], info["height"], rate, time_base, 18)
            for index, frame in enumerate(input_container.decode(video=0)):
                source_target = mapping[index]
                while source_index < source_target:
                    source_frame = next(source_decoder)
                    source_index += 1
                    source_image = source_frame.to_ndarray(format="bgr24")
                faces = tracking["frames"][source_target]["faces"]
                if selected:
                    faces = [face for face in faces if face["track_id"] in selected]
                image = frame.to_ndarray(format="bgr24")
                drawn = draw_faces(image, faces, matrix, edges, opacity, thickness, dots, color=color)
                frames_with_mesh += bool(faces)
                face_counts[len(faces)] += 1
                output_pts = frame.pts - input_start_pts
                encode_image(output, output_stream, drawn, output_pts, time_base)
                if preview:
                    left = cv2.resize(source_image, (360, 640))
                    left = draw_faces(left, faces, [[1, 0, 0], [0, 1, 0]], edges, opacity, thickness, dots, True, color)
                    right = cv2.resize(drawn, (360, 640))
                    preview_image = np.zeros((672, 720, 3), dtype=np.uint8)
                    preview_image[32:, :360], preview_image[32:, 360:] = left, right
                    cv2.putText(preview_image, f"Original {times[source_target]:.3f}s", (5, 22),
                                cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1, cv2.LINE_AA)
                    cv2.putText(preview_image, f"Depth + mesh {expected_times[index]:.3f}s", (365, 22),
                                cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1, cv2.LINE_AA)
                    encode_image(preview, preview_stream, preview_image, output_pts, time_base)
                if index in samples:
                    x, y = (sample_number % 2) * 540, (sample_number // 2) * 512
                    sheet[y + 32:y + 512, x:x + 270] = cv2.resize(source_image, (270, 480))
                    sheet[y + 32:y + 512, x + 270:x + 540] = cv2.resize(drawn, (270, 480))
                    cv2.putText(sheet, f"{expected_times[index]:.3f}s  faces={len(faces)}", (x + 5, y + 22),
                                cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1, cv2.LINE_AA)
                    sample_number += 1
                if index % 60 == 0:
                    print(f"Rendered {index + 1}/{len(mapping)} depth frames", flush=True)
            flush_stream(output, output_stream)
        if preview:
            flush_stream(preview, preview_stream)
    finally:
        source.close()
        if preview:
            preview.close()
    output_info = inspect_video(temporary)
    actual_times = [entry["time"] for entry in output_info["frames"]]
    if len(actual_times) != len(expected_times):
        raise RuntimeError("Output frame count differs from the decoded depth input")
    errors = [abs(a - b) for a, b in zip(actual_times, expected_times)]
    if max(errors) > float(time_base) + 0.000001:
        raise RuntimeError("Output timestamp validation failed")
    if abs(output_info["duration"] - info["duration"]) > max(float(time_base), 0.001):
        raise RuntimeError("Output duration validation failed")
    if preview:
        preview_info = inspect_video(preview_temporary)
        preview_times = [entry["time"] for entry in preview_info["frames"]]
        if len(preview_times) != len(expected_times) or any(abs(a - b) > float(time_base) + 0.000001 for a, b in zip(preview_times, expected_times)):
            raise RuntimeError("Preview frame count/timestamp validation failed")
    temporary.replace(clean_path)
    if preview:
        preview_temporary.replace(preview_path)
    cv2.imwrite(str(out / "mesh_contact_sheet.jpg"), sheet)
    duplicate_mappings = [index for index in range(1, len(mapping)) if mapping[index] == mapping[index - 1]]
    report = {"status": "passed", "completed_at_utc": recorded_at(),
              "tracking_sha256": fingerprint(out / "face_landmarks.json")["sha256"],
              "original": tracking["source"]["file"], "depth": info["file"],
              "alignment": alignment, "style": {"name": style, "opacity": opacity, "thickness": thickness, "dots": dots,
                                                 "color_rgb": list(reversed(color))},
              "output": str(clean_path), "silent": True, "resolution": [info["width"], info["height"]],
              "frames": len(actual_times), "duration_seconds": output_info["duration"],
              "frames_with_mesh": frames_with_mesh, "frames_by_face_count": dict(sorted(face_counts.items())),
              "max_source_matching_error_ms": round(max(frame_errors) * 1000, 3),
              "max_encoded_timestamp_error_ms": round(max(errors) * 1000, 6),
              "source_frames_reused_at_depth_indices": duplicate_mappings,
              "elapsed_seconds": round(time.perf_counter() - started, 2),
              "validation": "Full output decode, frame count, duration and per-frame presentation timestamps checked.",
              "limitations": ["Track IDs are geometric and shot-local, not identity recognition.",
                              "Model-estimated hidden facial points are not an occlusion mask.",
                              "Filmora import and OS-level network-isolation have not been verified."]}
    write_json(out / "render_report.json", report)
    print(json.dumps({key: value for key, value in report.items() if key not in ("alignment", "original", "depth")}, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "track", "render", "run"))
    parser.add_argument("--original", type=Path, default=ROOT / "original.mp4")
    parser.add_argument("--depth", type=Path, default=ROOT / "depth video.mp4")
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "video_test")
    parser.add_argument("--alignment", type=Path)
    parser.add_argument("--max-faces", type=int, default=4)
    parser.add_argument("--smoothing-ms", type=float, default=12)
    parser.add_argument("--style", choices=("mesh", "contours", "dots"), default="mesh")
    parser.add_argument("--opacity", type=float, default=0.8)
    parser.add_argument("--thickness", type=int, default=1)
    parser.add_argument("--dots", action="store_true")
    parser.add_argument("--color", default="00FFFF", help="Wireframe RGB hex, e.g. FFFFFF for white")
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--only-tracks", type=int, nargs="+")
    args = parser.parse_args()
    if not 0 <= args.opacity <= 1 or not 1 <= args.thickness <= 8 or not math.isfinite(args.smoothing_ms) or args.smoothing_ms < 0:
        parser.error("Invalid opacity, thickness or smoothing value")
    try:
        value = args.color.lstrip("#")
        if len(value) != 6:
            raise ValueError()
        color = tuple(bytes.fromhex(value)[::-1])
    except ValueError:
        parser.error("Color must contain six hexadecimal RGB digits")
    args.out.mkdir(parents=True, exist_ok=True)
    if args.command == "run":
        alignment_path = args.alignment or args.out / "alignment.json"
        if not alignment_path.exists():
            parser.error("Run inspect first and review the contact sheet; a verified alignment.json is required")
        alignment = json.loads(alignment_path.read_text("utf-8-sig"))
        if not alignment.get("visually_verified") or fingerprint(args.original)["sha256"] != alignment.get("original_sha256") or fingerprint(args.depth)["sha256"] != alignment.get("depth_sha256"):
            parser.error("Alignment review is missing or belongs to different input files")
    status = {"status": "running", "command": args.command, "started_at_utc": recorded_at()}
    status_path = args.out / "workflow_status.json"
    try:
        if args.command in ("inspect", "run"):
            status["stage"] = "inspect"
            write_json(status_path, status)
            inspect_pair(args.original, args.depth, args.out)
        if args.command in ("track", "run"):
            status["stage"] = "track"
            write_json(status_path, status)
            track(args.original, args.out, args.max_faces, args.smoothing_ms)
        if args.command in ("render", "run"):
            status["stage"] = "render"
            write_json(status_path, status)
            alignment_path = args.alignment or args.out / "alignment.json"
            render(args.original, args.depth, args.out, alignment_path, args.style, args.opacity,
                   args.thickness, args.dots, not args.no_preview, args.only_tracks, color)
    except Exception as error:
        write_json(status_path, {**status, "status": "failed", "finished_at_utc": recorded_at(), "error": str(error)})
        raise
    write_json(status_path, {**status, "status": "complete", "finished_at_utc": recorded_at()})


if __name__ == "__main__":
    main()
