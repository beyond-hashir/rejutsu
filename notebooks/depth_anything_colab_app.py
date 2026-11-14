"""Source embedded in Depth_Anything_V2_Video_GUI.ipynb; no companion file is needed in Colab."""
import gc
import json
import math
import os
import shutil
import subprocess
import time
import uuid
import zipfile
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

CODE_REVISION = "e5a2732d3ea2cddc081d7bfd708fc0bf09f812f1"
ROOT = Path(os.environ.get("DEPTH_COLAB_ROOT", "/content/depth_anything_gui"))
MODEL_CONFIGS = {
    "Small": dict(encoder="vits", features=64, out_channels=[48, 96, 192, 384]),
    "Base": dict(encoder="vitb", features=128, out_channels=[96, 192, 384, 768]),
    "Large": dict(encoder="vitl", features=256, out_channels=[256, 512, 1024, 1024]),
}
_model = None
_model_name = None
_model_revision = None


def run_command(args):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed:\n{result.stderr[-3000:]}")
    return result.stdout


def probe(path, count=False):
    args = ["ffprobe", "-v", "error", "-select_streams", "v:0"]
    if count:
        args += ["-count_frames"]
    data = json.loads(run_command(args + ["-show_streams", "-show_format", "-of", "json", path]))
    if not data.get("streams"):
        raise ValueError("This file has no readable video track.")
    return data["streams"][0]


def frame_rate(stream):
    for key in ("avg_frame_rate", "r_frame_rate"):
        try:
            rate = Fraction(stream.get(key, "0/1"))
            if 0 < rate <= 240:
                return rate
        except (ValueError, ZeroDivisionError):
            pass
    raise ValueError("Cannot determine a usable frame rate (supported range: up to 240 fps).")


def normalize_video(source, target, seconds=0):
    """Make a square-pixel, upright CFR reference; depth is derived only from this file."""
    rate = frame_rate(probe(source))
    # FFmpeg autorotates phone footage. Respect sample aspect ratio before removing it.
    filters = (
        "scale=w='max(2,round(iw*sar))':h=ih,setsar=1,"
        "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0,"
        f"fps={rate.numerator}/{rate.denominator}"
    )
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror", "-y", "-i", source]
    if seconds > 0:
        args += ["-t", str(seconds)]
    args += [
        "-map", "0:v:0", "-an", "-vf", filters,
        "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
        "-metadata:s:v:0", "rotate=0", "-movflags", "+faststart", target,
    ]
    run_command(args)
    return probe(target, count=True)


def load_model(name):
    global _model, _model_name, _model_revision
    import torch
    from huggingface_hub import HfApi, hf_hub_download
    from depth_anything_v2.dpt import DepthAnythingV2

    if not torch.cuda.is_available():
        raise RuntimeError("Choose Runtime > Change runtime type > T4 GPU, then rerun the notebook.")
    if _model is not None and _model_name == name:
        return _model
    _model = None
    gc.collect()
    torch.cuda.empty_cache()
    config = MODEL_CONFIGS[name]
    repo = f"depth-anything/Depth-Anything-V2-{name}"
    # Resolve main once, then download that exact revision and record it in the report.
    revision = HfApi().model_info(repo).sha
    checkpoint = hf_hub_download(
        repo_id=repo, revision=revision,
        filename=f"depth_anything_v2_{config['encoder']}.pth",
    )
    model = DepthAnythingV2(**config)
    model.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True))
    _model = model.to("cuda").eval()
    _model_name, _model_revision = name, revision
    return _model


def work_dimensions(width, height, maximum=1280):
    scale = min(1.0, maximum / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def depth_to_bgr(depth, low, high, invert=False, colored=False):
    if not np.isfinite(depth).all():
        raise RuntimeError("Model produced invalid depth values. Try a smaller model/input size.")
    gray = np.clip((depth - low) / max(high - low, 1e-8), 0, 1)
    gray = np.rint(gray * 255).astype(np.uint8)
    if invert:
        gray = 255 - gray
    if colored:
        return cv2.applyColorMap(gray, cv2.COLORMAP_INFERNO)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


class VideoEncoder:
    """Pipe frames straight to H.264, avoiding lossy intermediate video files."""
    def __init__(self, path, width, height, rate):
        self.log_path = path.with_suffix(".ffmpeg.log")
        self.log = self.log_path.open("wb")
        try:
            self.process = subprocess.Popen([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pix_fmt", "bgr24", "-s:v", f"{width}x{height}",
                "-r", str(rate), "-i", "pipe:0", "-an", "-c:v", "libx264",
                "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(path),
            ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.log)
        except BaseException:
            self.log.close()
            raise

    def write(self, frame):
        self.process.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self, abort=False):
        try:
            if abort and self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            code = self.process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
            raise RuntimeError("Video encoder timed out.")
        finally:
            self.log.close()
        if code and not abort:
            raise RuntimeError("Video encoding failed:\n" + self.log_path.read_text(errors="replace")[-2500:])
        self.log_path.unlink(missing_ok=True)


def verify_pair(reference, depth, expected_count):
    rgb, dep = probe(reference, True), probe(depth, True)
    for stream in (rgb, dep):
        if int(stream.get("nb_read_frames", 0)) != expected_count:
            raise RuntimeError("Decoded frame count differs from the processed count; output was not delivered.")
    if (rgb["width"], rgb["height"], frame_rate(rgb)) != (dep["width"], dep["height"], frame_rate(dep)):
        raise RuntimeError("Reference and depth geometry or frame rate do not match.")
    # Check complete streams for bitstream/decode errors, not just container metadata.
    for path in (reference, depth):
        run_command(["ffmpeg", "-v", "error", "-xerror", "-i", path, "-f", "null", "-"])
    return dep


def convert_video(upload, model_name, input_size, normalization, invert, colored, seconds,
                  progress=lambda *args, **kwargs: None):
    if not upload or not Path(upload).is_file():
        raise ValueError("Upload a video first.")
    if model_name not in MODEL_CONFIGS:
        raise ValueError("Choose Small, Base, or Large.")
    input_size = int(input_size)
    seconds = float(seconds)
    if input_size not in (280, 392, 518, 700) or not math.isfinite(seconds) or not 0 <= seconds <= 36000:
        raise ValueError("Invalid input size or preview duration.")
    started = time.monotonic()
    job = ROOT / "outputs" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    cache = job / "depth_cache"
    cache.mkdir(parents=True)
    reference, output = job / "source_reference.mp4", job / "depth.mp4"
    reader, writer = None, None
    try:
        progress(0.01, desc="Preparing matching reference video…")
        info = normalize_video(Path(upload), reference, seconds)
        width, height = int(info["width"]), int(info["height"])
        rate = frame_rate(info)
        expected = int(info.get("nb_read_frames", 0))
        if expected < 1:
            raise ValueError("No frames were found. Try exporting your input as MP4.")
        work_w, work_h = work_dimensions(width, height)
        # Float32 cache keeps predictions intact; frames stay on disk rather than in RAM.
        estimate = expected * work_w * work_h * 4
        if shutil.disk_usage(job).free < estimate + 1024**3:
            raise RuntimeError("Not enough temporary disk space. Use a shorter clip or preview duration.")
        progress(0.04, desc=f"Loading {model_name} model (first use downloads weights)…")
        model = load_model(model_name)
        reader = cv2.VideoCapture(str(reference))
        if not reader.isOpened():
            raise RuntimeError("OpenCV could not open the prepared reference video.")
        low, high, count = float("inf"), float("-inf"), 0
        while True:
            ok, frame = reader.read()
            if not ok:
                break
            if shutil.disk_usage(job).free < work_w * work_h * 4 + 256 * 1024**2:
                raise RuntimeError("Temporary disk is full. Retry with a shorter clip.")
            if frame.shape[:2] != (work_h, work_w):
                frame = cv2.resize(frame, (work_w, work_h), interpolation=cv2.INTER_AREA)
            prediction = np.asarray(model.infer_image(frame, input_size), dtype=np.float32)
            if prediction.shape != (work_h, work_w) or not np.isfinite(prediction).all():
                raise RuntimeError("Invalid model output. Try Small with input size 392.")
            low, high = min(low, float(prediction.min())), max(high, float(prediction.max()))
            np.save(cache / f"{count:08d}.npy", prediction, allow_pickle=False)
            count += 1
            progress(0.08 + 0.68 * min(count / expected, 1), desc=f"Estimating depth: {count}/{expected} frames")
        reader.release()
        reader = None
        if count != expected:
            raise RuntimeError(f"Video decoding stopped early ({count}/{expected} frames). No export delivered.")
        writer = VideoEncoder(output, width, height, rate)
        for index in range(count):
            prediction = np.load(cache / f"{index:08d}.npy", allow_pickle=False)
            frame_low, frame_high = low, high
            if normalization == "Per frame (stronger contrast)":
                frame_low, frame_high = float(prediction.min()), float(prediction.max())
            result = depth_to_bgr(prediction, frame_low, frame_high, invert, colored)
            if result.shape[:2] != (height, width):
                result = cv2.resize(result, (width, height), interpolation=cv2.INTER_LINEAR)
            writer.write(result)
            progress(0.76 + 0.18 * (index + 1) / count, desc=f"Encoding depth video: {index + 1}/{count} frames")
        writer.close()
        writer = None
        progress(0.95, desc="Checking both videos and preparing downloads…")
        verified = verify_pair(reference, output, count)
        report = {
            "status": "passed", "model": f"Depth Anything V2 {model_name}",
            "code_revision": CODE_REVISION, "weights_revision": _model_revision,
            "input_filename": Path(upload).name, "input_size": input_size,
            "prediction_dimensions": [work_w, work_h], "output_dimensions": [width, height],
            "frame_count": count, "fps": str(frame_rate(verified)),
            "duration_seconds": float(Fraction(count) / rate),
            "normalization": normalization, "depth_range": [low, high],
            "near_is_white": not invert if not colored else None, "colored": bool(colored),
            "preview_seconds_requested": seconds, "audio": "Both exports are silent.",
            "reference_policy": "Use source_reference.mp4 as the RGB partner of depth.mp4.",
            "timing_policy": "CFR at source average fps; variable-rate sources may have duplicated/dropped frames.",
            "geometry_policy": "Rotation baked in; square pixels; odd dimensions padded right/bottom by one pixel.",
            "depth_type": "Relative inverse depth visualization, 8-bit H.264; not metric/raw depth.",
            "elapsed_seconds": round(time.monotonic() - started, 1),
        }
        report_path = job / "report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        readme = job / "READ_ME.txt"
        readme.write_text(
            "MATCHING VIDEO PAIR\n\nUse source_reference.mp4 (RGB) together with depth.mp4.\n"
            "Both files are silent and have matching frame counts, resolution and constant frame rate.\n"
            "Phone rotation, pixel aspect ratio, odd dimensions and variable timing may have been normalized.\n"
            "For a preview run, both files contain only the requested initial seconds.\n"
            "Depth is a compressed 8-bit relative inverse-depth visualization, not measured meters.\n"
            "Depth Anything V2 predicts individual frames; flicker/scale drift can remain.\n"
            "Whole-video contrast uses one display range; it does not make the model temporally consistent.\n"
            "Small weights: Apache-2.0. Base/Large weights: CC-BY-NC-4.0.\n"
            "Model: https://github.com/DepthAnything/Depth-Anything-V2\n",
            encoding="utf-8",
        )
        archive = job / "depth_video_bundle.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
            for path in (reference, output, report_path, readme):
                bundle.write(path, path.name)
        progress(1, desc="Done")
        status = (
            f"Done — {count} frames · {width} × {height} · {float(rate):.6f} fps · "
            f"{count / float(rate):.2f} s. Download both videos or the complete ZIP. "
            "Use source_reference.mp4 as the matching original in Mesh Studio."
        )
        return str(output), str(reference), str(output), str(reference), str(archive), status
    finally:
        if reader is not None:
            reader.release()
        if writer is not None:
            writer.close(abort=True)
        shutil.rmtree(cache, ignore_errors=True)


def build_gui():
    import gradio as gr

    def process(upload, model_name, input_size, normalization, invert, colored, seconds,
                progress=gr.Progress()):
        try:
            return convert_video(upload, model_name, input_size, normalization, invert, colored, seconds, progress)
        except Exception as exc:
            if "out of memory" in str(exc).lower():
                raise gr.Error("GPU memory is full. Choose Small and input size 392; restart the session if needed.") from exc
            raise gr.Error(str(exc)) from exc

    with gr.Blocks(title="Depth Anything V2 · Video", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            "# Turn a video into a depth map\n"
            "Upload → choose settings → **Generate depth video** → preview and download. "
            "Start with **Small / 518 / Grayscale**. Models download automatically on first use."
        )
        with gr.Row():
            with gr.Column(scale=1):
                upload = gr.File(label="Upload video", type="filepath", file_types=["video"])
                model_name = gr.Dropdown(list(MODEL_CONFIGS), value="Small", label="Model size")
                gr.Markdown("Small: Apache-2.0. Base and Large: noncommercial CC-BY-NC-4.0.")
                input_size = gr.Dropdown([280, 392, 518, 700], value=518, label="Inference size (higher = more detail / GPU memory)")
                normalization = gr.Radio(
                    ["Whole video (fixed contrast)", "Per frame (stronger contrast)"],
                    value="Whole video (fixed contrast)", label="Depth contrast",
                )
                invert = gr.Checkbox(False, label="Invert depth (default: near = white, far = black)")
                colored = gr.Checkbox(False, label="Color heatmap instead of grayscale")
                seconds = gr.Number(value=0, minimum=0, maximum=36000, label="Preview: first N seconds (0 = entire video)")
                submit = gr.Button("Generate depth video", variant="primary")
            with gr.Column(scale=2):
                with gr.Row():
                    depth_preview = gr.Video(label="Depth preview", interactive=False)
                    reference_preview = gr.Video(label="Matching reference", interactive=False)
                status = gr.Textbox(label="Status", value="Upload a video to begin.", interactive=False)
                depth_file = gr.File(label="Download depth.mp4", interactive=False)
                reference_file = gr.File(label="Download source_reference.mp4", interactive=False)
                zip_file = gr.File(label="Download complete bundle (videos + report)", interactive=False)
        gr.Markdown(
            "**For your motion-transfer workflow:** use the exported **source_reference.mp4 + depth.mp4** pair. "
            "Both are silent. Timing is normalized to constant FPS, rotation is baked in, and odd dimensions "
            "are padded to support MP4. Output keeps this reference geometry; predictions use up to 1280 pixels on the long side.\n\n"
            "**Quality:** relative depth, not meters. V2 processes frames individually; flicker can remain. "
            "Whole-video contrast fixes the display range, not temporal model drift. "
            "Intermediate predictions use temporary disk space and are removed after each run. "
            "Download completed files before your Colab session ends."
        )
        outputs = [depth_preview, reference_preview, depth_file, reference_file, zip_file, status]
        event = submit.click(
            lambda: (None, None, None, None, None, "Processing…"), outputs=outputs,
            queue=False, api_name=False,
        )
        event.then(
            process, inputs=[upload, model_name, input_size, normalization, invert, colored, seconds],
            outputs=outputs, concurrency_limit=1, concurrency_id="depth_gpu", api_name=False,
        )
    return demo.queue(max_size=4, default_concurrency_limit=1)
