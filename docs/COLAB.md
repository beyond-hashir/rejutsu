# Generate a matching depth pair in Colab

[← README](../README.md) · [Mesh Studio](WEB_UI.md) · [Full workflow](WORKFLOW.md)

The optional notebook turns a color clip into an 8-bit relative inverse-depth video using Depth Anything V2. It also exports the exact color reference used to create that depth video, ready to pair in Mesh Studio. You can skip this guide if you already have a matching pair.

## Start the notebook

1. [Open the notebook in Google Colab](https://colab.research.google.com/github/hashiro-cloud/motion-transfer/blob/main/notebooks/Depth_Anything_V2_Video_GUI.ipynb). Alternatively, download [`Depth_Anything_V2_Video_GUI.ipynb`](../notebooks/Depth_Anything_V2_Video_GUI.ipynb) and choose **File → Upload notebook** in Colab. The notebook is standalone; no companion source file is needed.
2. Choose **Runtime → Change runtime type → T4 GPU**, or another available NVIDIA GPU, and save. GPU availability depends on your Colab allocation.
3. Choose **Runtime → Run all**. Setup installs the interface dependencies and fetches a pinned revision of the official model code. The first generation downloads the selected checkpoint.
4. Wait for the interface, upload your video, and start with **Small / 518**, grayscale, whole-video contrast. Try a **5-second preview** first.
5. Click **Generate depth video**, review the previews, and download the complete ZIP or both MP4s.

## Choose settings

| Setting | How to choose |
| --- | --- |
| Model | Start with **Small**. Base/Large need more GPU memory and have different license terms. |
| Inference size | **518** is a starting point; use **392** if GPU memory runs out. |
| Contrast | Whole-video contrast keeps a shared visualization scale; per-frame contrast stretches each frame separately. Compare results if your scene changes substantially. |
| Grayscale / color | Use grayscale for the depth-and-mesh reference. Color is useful for visualization. |
| Invert | Reverses bright/dark depth visualization. Keep the convention consistent across your chosen workflow. |
| Preview | Process a short segment before spending time on a full clip. Switch back to the full clip for final delivery. |

The model estimates each frame independently. Fixed contrast does not guarantee temporal consistency, and depth can flicker or drift. This is a compressed relative-depth visualization, not metric distance or scientific raw depth. Prediction frames are limited to 1280 pixels on the long side; exports retain the prepared reference's dimensions.

## Download and use the right files

| File in the ZIP | Purpose |
| --- | --- |
| `source_reference.mp4` | Color input for Mesh Studio, source for analysis, and lower layer in the editor |
| `depth.mp4` | Matching depth input for Mesh Studio |
| `report.json` | Export settings, model revision, geometry, timing, and verification status |
| `READ_ME.txt` | Bundle handoff notes |

**Use the exported pair together.** The notebook normalizes rotation, sample aspect ratio, and variable frame rate before depth generation. It can add a pixel on the right/bottom for even dimensions, and frame-rate normalization can change the frame count. The uploaded original may therefore differ from the prepared reference. Both exported videos are silent.

Download before the Colab session ends. Runtime files are temporary; completed runs appear under `/content/depth_anything_gui/outputs/`. Float32 prediction caches use additional temporary disk space during processing and are cleaned after each run.

Next, [open Mesh Studio](WEB_UI.md) on your Windows PC and select `source_reference.mp4` and `depth.mp4`.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| No GPU | Select a GPU runtime, save, and run all again. If unavailable, retry when your account has GPU allocation. |
| Out of memory | Use Small / 392. Restart the session and rerun the cells if necessary. |
| Setup version assertion | Restart the runtime and run all in order so a previously imported Gradio version is cleared. |
| Blank interface | Open the printed Gradio link and keep the notebook connected. |
| Upload fails | Use Colab's Files sidebar and the commented fallback cell in the notebook. |
| ZIP is too large | Download the two MP4s separately from the interface or Colab Files sidebar. |
| Flickering depth | Compare whole-video and per-frame contrast. Neither adds temporal modeling. |
| Mesh later seems offset | Confirm you selected the exported color reference rather than the pre-normalization upload. |

## Hosted processing and model licenses

Video processing happens on your Colab runtime. The Gradio share link is accessible to anyone who has it; keep it private and run `depth_demo.close()` in the notebook when finished. Local Mesh Studio processing is a separate stage on your PC.

The notebook uses the [official Depth Anything V2 implementation](https://github.com/DepthAnything/Depth-Anything-V2), pinned at [`e5a2732`](https://github.com/DepthAnything/Depth-Anything-V2/commit/e5a2732d3ea2cddc081d7bfd708fc0bf09f812f1). The checkpoint revision is recorded in each report. Small weights are Apache-2.0; Base/Large weights are CC-BY-NC-4.0. Check the [upstream license section](https://github.com/DepthAnything/Depth-Anything-V2#license) for your intended use.

The notebook keeps Colab's supplied PyTorch/torchvision pair. Future hosted runtime changes may require dependency updates. Local media tests do not prove live Colab GPU inference has passed; see [Development and testing](DEVELOPMENT.md).
