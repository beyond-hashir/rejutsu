"""Coordinate, timeline and short-term face association helpers."""
from __future__ import annotations

from bisect import bisect_left
from functools import lru_cache
import math

import numpy as np


def match_time(times: list[float], target: float, tolerance: float = 0.051) -> int:
    """Nearest presentation timestamp, preferring the earlier frame on a tie."""
    if not times:
        raise ValueError("Empty source timeline")
    if any(not math.isfinite(value) for value in (target, tolerance)) or tolerance < 0:
        raise ValueError("Invalid timestamp/tolerance")
    pos = bisect_left(times, target)
    candidates = [index for index in (pos - 1, pos) if 0 <= index < len(times)]
    best = min(candidates, key=lambda index: (round(abs(times[index] - target), 9), index))
    if abs(times[best] - target) > tolerance + 1e-9:
        raise ValueError(f"No source frame within {tolerance:.3f}s of depth time {target:.6f}s")
    return best


def transform_xy(points, matrix, width: int, height: int) -> np.ndarray:
    """Normalized source coordinates -> normalized affine -> depth pixels."""
    points = np.asarray(points, dtype=np.float64)
    matrix = np.asarray(matrix, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] < 2 or matrix.shape != (2, 3):
        raise ValueError("Expected Nx2/3 points and a 2x3 normalized affine matrix")
    if not np.isfinite(points).all() or not np.isfinite(matrix).all() or min(width, height) <= 0:
        raise ValueError("Non-finite coordinates or invalid dimensions")
    xy = np.column_stack((points[:, :2], np.ones(len(points)))) @ matrix.T
    return np.rint(xy * np.array([width, height])).astype(np.int32)


def face_features(points):
    points = np.asarray(points, dtype=np.float64)
    lo, hi = points[:, :2].min(axis=0), points[:, :2].max(axis=0)
    center = (lo + hi) / 2
    size = np.maximum(hi - lo, 1e-5)
    shape = (points[[1, 33, 263, 61, 291], :2] - center) / size
    return center, size, shape


class FaceAssociator:
    """Short-term geometric tracks; does not recognize or re-identify people."""

    def __init__(self, max_gap: float = 0.25, smoothing_ms: float = 12):
        self.max_gap = max_gap
        self.smoothing_ms = smoothing_ms
        self.tracks = {}
        self.next_id = 1

    def reset(self):
        self.tracks.clear()

    def update(self, detections: list[dict], timestamp: float) -> list[dict]:
        self.tracks = {key: value for key, value in self.tracks.items()
                       if 0 <= timestamp - value["time"] <= self.max_gap}
        ids = sorted(self.tracks)
        features = [face_features(item["raw_landmarks"]) for item in detections]
        costs = np.full((len(ids), len(detections)), np.inf)
        for row, track_id in enumerate(ids):
            track = self.tracks[track_id]
            dt = timestamp - track["time"]
            predicted = track["center"] + track["velocity"] * dt
            for col, (center, size, shape) in enumerate(features):
                distance = np.linalg.norm(center - predicted) / max(np.linalg.norm(track["size"]), 0.025)
                size_change = abs(math.log(float(np.prod(size) / np.prod(track["size"]))))
                if distance < 1.2 and size_change < 1.8:
                    shape_change = float(np.mean(np.abs(shape - track["shape"])))
                    costs[row, col] = 0.75 * distance + 0.15 * size_change + 0.2 * shape_change

        @lru_cache(None)
        def assign(row, mask):
            if row == len(ids):
                return 0.7 * (len(detections) - mask.bit_count()), ()
            tail_cost, tail = assign(row + 1, mask)
            best = (0.7 + tail_cost, (-1,) + tail)
            for col in range(len(detections)):
                if not mask & (1 << col) and np.isfinite(costs[row, col]):
                    tail_cost, tail = assign(row + 1, mask | (1 << col))
                    option = (float(costs[row, col]) + tail_cost, (col,) + tail)
                    if option[0] < best[0]:
                        best = option
            return best

        matches = {col: ids[row] for row, col in enumerate(assign(0, 0)[1]) if col >= 0}
        results = []
        for index, detection in enumerate(detections):
            raw = np.asarray(detection["raw_landmarks"], dtype=np.float64)
            center, size, shape = features[index]
            track_id = matches.get(index)
            previous = self.tracks.get(track_id)
            if track_id is None:
                track_id = self.next_id
                self.next_id += 1
            alternatives = sorted(value for value in costs[:, index] if np.isfinite(value))
            ambiguous = len(alternatives) > 1 and alternatives[1] - alternatives[0] < 0.12
            filtered = raw.copy()
            velocity = np.zeros(2)
            smoothed = False
            if previous is not None:
                dt = timestamp - previous["time"]
                if dt > 0:
                    velocity = (center - previous["center"]) / dt
                    if self.smoothing_ms > 0 and dt <= 0.051 and not ambiguous:
                        alpha = 1 - math.exp(-dt / (self.smoothing_ms / 1000))
                        filtered = previous["filtered"] + alpha * (raw - previous["filtered"])
                        smoothed = True
            self.tracks[track_id] = {"time": timestamp, "center": center, "size": size,
                                     "shape": shape, "velocity": velocity, "filtered": filtered}
            results.append({**detection, "track_id": track_id,
                            "landmarks": np.round(filtered, 7).tolist(),
                            "association_ambiguous": bool(ambiguous), "smoothed": smoothed,
                            "interpolated": False})
        return results
