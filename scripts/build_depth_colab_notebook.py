"""Build the standalone Colab notebook using only Python's standard library."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "notebooks" / "Depth_Anything_V2_Video_GUI.ipynb"


def markdown(text):
    return dict(cell_type="markdown", metadata={}, source=text.strip().splitlines(keepends=True))


def code(text, title):
    return dict(cell_type="code", execution_count=None, outputs=[],
                metadata={"cellView": "form"}, source=(f"#@title {title}\n" + text.strip() + "\n").splitlines(keepends=True))


SETUP = r'''
import os
import subprocess
import sys
from pathlib import Path

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

import torch
import torchvision
if not torch.cuda.is_available():
    raise RuntimeError("Enable a GPU: Runtime > Change runtime type > T4 GPU, save, then rerun this cell.")
print("GPU:", torch.cuda.get_device_name(0))
print("Using Colab's matching PyTorch / torchvision:", torch.__version__, torchvision.__version__)

def setup_run(args):
    subprocess.run(args, check=True)

# Keep Colab's existing torch/torchvision and NumPy. No xformers build or API key required.
setup_run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
           "gradio==5.49.1", "huggingface-hub==0.36.0", "opencv-python-headless==4.11.0.86"])
import shutil
if not all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe", "git")):
    setup_run(["apt-get", "update", "-qq"])
    setup_run(["apt-get", "install", "-y", "-qq", "ffmpeg", "git"])

ROOT = Path("/content/depth_anything_gui")
ROOT.mkdir(parents=True, exist_ok=True)
os.environ["DEPTH_COLAB_ROOT"] = str(ROOT)
repo = ROOT / "Depth-Anything-V2"
revision = "e5a2732d3ea2cddc081d7bfd708fc0bf09f812f1"
if not (repo / ".git").is_dir():
    setup_run(["git", "clone", "https://github.com/DepthAnything/Depth-Anything-V2.git", str(repo)])
setup_run(["git", "-C", str(repo), "checkout", "--detach", revision])
if str(repo) not in sys.path:
    sys.path.insert(0, str(repo))

import cv2
import gradio as gr
from depth_anything_v2.dpt import DepthAnythingV2
assert gr.__version__ == "5.49.1", "A different Gradio version is already imported. Restart the session and run all again."
print("Setup complete. The next cell builds your video interface.")
'''

LAUNCH = r'''
# Rerun this cell if you close the interface. Use the printed link if the inline view is blank.
if "depth_demo" in globals():
    depth_demo.close()
depth_demo = build_gui()
depth_demo.launch(share=True, inline=True, show_error=True, debug=False)
'''

cells = [
    markdown('''
# Depth Anything V2 — Video to Depth Map GUI

**Upload this `.ipynb` directly to Google Colab. No companion files, API keys, or local installation needed.**

1. Open [Google Colab](https://colab.research.google.com/) → **File → Upload notebook** and select this file.
2. Choose **Runtime → Change runtime type → T4 GPU** (or another available NVIDIA GPU), then save.
3. Choose **Runtime → Run all**. Wait for setup and the interface to appear.
4. Upload your video in the GUI and click **Generate depth video**. Start with **Small / 518**, grayscale, whole-video contrast.
5. Preview and download `depth.mp4`, or download the complete ZIP with the matching reference video.

The first generation downloads the chosen official model. Try **Preview: 5 seconds** before a long video.
The GUI supports Small, Base, and Large; larger models need more GPU memory. Use Small / 392 if memory runs out.

**Your motion-transfer workflow:** download **both `source_reference.mp4` and `depth.mp4`** and use them as a pair in Mesh Studio.
The notebook normalizes rotation, sample aspect ratio and variable frame rate once, before generating depth.
Both outputs have the same dimensions, decoded frame count and constant FPS. Both outputs are silent.
Odd dimensions receive up to one extra pixel at the right/bottom. Variable-rate input may gain/lose frames during normalization.
Use the exported reference when compositing; the uploaded original may have different timing or orientation.

**Know the output:** this is an 8-bit, compressed relative inverse-depth visualization, not measured distances or raw scientific depth.
V2 estimates each frame independently, so flicker/scale drift may remain; fixed contrast does not add temporal consistency.
The output preserves the prepared reference's resolution; prediction frames are limited to 1280 pixels on the long side.
For models explicitly trained for temporal consistency, see the authors' separate [Video Depth Anything](https://github.com/DepthAnything/Video-Depth-Anything) project.

**Session:** keep Colab connected and download before the session ends. Videos run on your Colab runtime.
The Gradio share link is public to anyone who has it, so keep it private; stop the interface using the last cell when finished.
Long videos need temporary disk space for float32 predictions; those intermediate files are deleted after each run.
'''),
    code(SETUP, "1 · Install and check the GPU"),
    code((ROOT / "notebooks" / "depth_anything_colab_app.py").read_text(encoding="utf-8"), "2 · Prepare the video GUI"),
    code(LAUNCH, "3 · Open the GUI — upload your video here"),
    markdown('''
## Help

- **No GPU:** select a GPU runtime, then run all again. Availability depends on your Colab account and current allocation.
- **Out of memory:** use Small / 392. If necessary, restart the session and rerun all cells.
- **Interface blank:** open the `gradio.live` link printed above. Leave the Colab tab connected.
- **Download too large:** download each MP4 separately. All completed runs are also in the Colab Files sidebar under `/content/depth_anything_gui/outputs/`.
- **Upload too large:** upload using Colab's Files sidebar, then use the optional fallback cell below with its `/content/...` path.
- **Flicker:** compare fixed whole-video contrast and per-frame contrast; neither guarantees temporal consistency.
- **Color map:** grayscale is the default for the motion-reference workflow. Color is mainly for visualization.
- **Fresh session:** files and models stored only on Colab's temporary disk can disappear when the session resets.

The optional cells below are **not needed for the GUI**. They are comments only until you uncomment the lines you want.
'''),
    code('''
# Optional fallback if the GUI upload fails. Upload using Colab's Files sidebar first.
# Run setup and the GUI-preparation cells above before using this.
# from google.colab import files
# results = convert_video(
#     "/content/my_video.mp4", "Small", 518,
#     "Whole video (fixed contrast)", False, False, 0,
#     progress=lambda value, desc="": print(f"{value:.0%} {desc}")
# )
# files.download(results[4])  # Complete ZIP
''', "Optional · Process a file from Colab's Files sidebar"),
    code('''
# Optional: uncomment to close the public interface when finished.
# depth_demo.close()
''', "Optional · Stop the interface"),
    markdown('''
## Sources and model licenses

Uses the authors' [official Depth Anything V2 implementation](https://github.com/DepthAnything/Depth-Anything-V2),
pinned at [e5a2732](https://github.com/DepthAnything/Depth-Anything-V2/commit/e5a2732d3ea2cddc081d7bfd708fc0bf09f812f1),
and official checkpoints: [Small](https://huggingface.co/depth-anything/Depth-Anything-V2-Small),
[Base](https://huggingface.co/depth-anything/Depth-Anything-V2-Base),
[Large](https://huggingface.co/depth-anything/Depth-Anything-V2-Large).
The checkpoint revision is resolved at download time and recorded in each bundle's `report.json`.

The authors license **Small under Apache-2.0** and **Base/Large under CC-BY-NC-4.0**.
See the [official license section](https://github.com/DepthAnything/Depth-Anything-V2#license).
The interface uses [Gradio](https://www.gradio.app/).

Notebook prepared 2026-11-14. Setup keeps Colab's existing PyTorch/torchvision pair;
future Colab runtime changes may require dependency updates.
'''),
]

for index, cell in enumerate(cells):
    cell["id"] = f"depth-colab-{index:02d}"
notebook = {
    "nbformat": 4, "nbformat_minor": 5,
    "metadata": {
        "colab": {"name": OUT.name, "provenance": []},
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
        "accelerator": "GPU", "gpuClass": "standard",
    },
    "cells": cells,
}
OUT.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(OUT)
