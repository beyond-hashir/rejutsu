# Development and testing

[← README](../README.md) · [Full workflow](WORKFLOW.md)

## Source layout

```text
motion-transfer/
├── .agent/skills/local-motion-transfer/  Agent workflow and stage references
├── AGENTS.md                            Routes agents to the bundled skill
├── Start-Mesh-Studio.cmd                 Double-click browser launcher
├── Start-Mesh-Studio.ps1                 PowerShell browser launcher
├── Mesh-Video.ps1                        CLI wrapper
├── Ensure-Environment.ps1                Check setup and repair if needed
├── Check-Environment.ps1                 Environment smoke check
├── requirements.in / requirements.lock   Direct inputs and hashed package lock
├── scripts/                             Setup, engine, HTTP server, and tests
├── web/                                 Local browser interface
├── notebooks/                           Standalone Colab notebook and its source
└── docs/                                User and developer guides
```

Setup creates `.runtime/`, `.venv/`, `.cache/`, `models/`, and `assets/`. Uploads, exports, and test artifacts go under `outputs/` or `tmp/`. These directories are ignored and are not source dependencies to copy from another computer.

## Environment checks

Run from PowerShell in the project root on Windows x64:

```powershell
.\Ensure-Environment.ps1
.\Check-Environment.ps1
```

`Ensure-Environment.ps1` runs the check first and repairs missing or broken setup using `scripts/setup.ps1`. The smoke check verifies project-local Python 3.12.13, locked package versions, model SHA-256, single/two-face CPU inference, drawing, H.264 encoding/decoding, and ffprobe frame counting. Setup's sample portrait is downloaded from Google's published assets; it is not an author's input clip.

For direct Python commands, discover project-local FFmpeg tools in the current process first:

```powershell
. .\scripts\project_environment.ps1
```

To provision the pinned local uv and FFmpeg binaries even if working system tools exist:

```powershell
.\scripts\setup.ps1 -PreferLocalTools
```

Do not copy `.venv/` between PCs. Setup preserves an incompatible copied environment under `tmp/` and rebuilds it. Download verification and package hashes should remain enabled.

## Automated checks

```powershell
. .\scripts\project_environment.ps1
& '.\.venv\Scripts\python.exe' -m unittest discover -s scripts -p 'test_*.py'
& '.\.venv\Scripts\python.exe' scripts\validate_workflow.py
```

| Check | Coverage |
| --- | --- |
| `test_mesh_core.py` | Timestamp matching, mapping, invalid coordinates, association, gaps, shot resets, and ambiguity |
| `test_web_server.py` | Local HTTP session/origin checks, upload lifecycle, cancellation, file boundaries, range/download responses, settings, and restart recovery |
| `test_depth_colab_notebook.py` | Standalone notebook structure, code compilation, synthetic video conversion, matching bundles, exact timestamps at standard/unusual fractional FPS, variable FPS, rotation/pixel normalization, and failure cleanup |
| `validate_workflow.py` | Generated moving two-portrait fixture, full tracking/rendering, cached-landmark rendering with inference disabled, input-hash rejection, and full decoding |

Unit-test discovery includes localhost HTTP tests. The integration validator rejects Python socket connection/DNS/bind/send operations during its process; this does not establish an OS firewall or native-code network isolation.

Tests use generated fixtures and the downloaded smoke-test portrait. Personal videos and previous output folders are not required. Generated integration reports are written under `outputs/validation/`.

These checks do not establish performance on all real multi-person crossings, small faces, or long occlusions. Colab media tests substitute a deterministic depth model to verify video handling; they do not execute real GPU inference or prove a live Colab session works. Editor import and downstream generation require their own manual review.

## Maintaining the Colab notebook

The standalone notebook embeds `notebooks/depth_anything_colab_app.py`. Edit that source and the notebook builder as needed, then regenerate:

```powershell
& '.\.venv\Scripts\python.exe' scripts\build_depth_colab_notebook.py
& '.\.venv\Scripts\python.exe' -m unittest discover -s scripts -p 'test_depth_colab_notebook.py'
```

Commit both the source and regenerated `.ipynb`. Keep all notebook outputs cleared and execution counts null before publishing. The notebook's inference dependencies are separate from the local mesh engine's lockfile.

## Sharing changes

Keep `.agent/`, the launchers, source, web files, lockfile, and guides together. Inspect the staged file list before committing. The ignore rules exclude video/audio/raster media, credentials, input/output directories, runtime downloads, and private development notes. Only deliberately authored documentation SVGs are included as visual assets.

When reporting an issue, include reproducible steps and relevant versions. Redact personal paths, filenames, tokens, and media from diagnostic snippets. Do not attach somebody else's footage to a public issue without permission.
