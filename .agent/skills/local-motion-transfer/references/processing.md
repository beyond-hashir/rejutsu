# Local setup and processing

Use the shipped source files. Commands below run in PowerShell from the resolved
project root. Example variables represent real supplied paths; assign them before
execution. Paths with spaces must stay quoted. Always provide the actual input
paths and a fresh output directory; do not accept launcher sample defaults for a new pair.

## Preflight on every full processing session

```powershell
.\Ensure-Environment.ps1
```

This runs `Check-Environment.ps1`, which checks both command-line media tools,
project Python location/version, locked package versions, the model's SHA-256,
single/two-face native CPU inference, mesh drawing, H.264 encoding/decoding and
ffprobe frame counting. A failed check triggers `scripts/setup.ps1` followed by
the smoke check. Stop processing if setup/check still fails. Read the error rather
than repeating the same failed install indefinitely. No stale report proves the
current session passed; require the current command's success.

Setup can download missing uv and FFmpeg/ffprobe to `.runtime/`, install project
Python 3.12.13 and `.venv/`, sync `requirements.lock` with package hashes, and obtain
the pinned MediaPipe model and smoke-test portrait. Bootstrap archives have pinned
publisher SHA-256 values. Existing working system uv/FFmpeg may be reused. Local
tool discovery modifies only the current process PATH; no administrator or global
package manager is needed. `scripts/setup.ps1 -PreferLocalTools` can provision the
pinned local binaries even when system tools exist. Package downloads use uv's
project cache. Missing assets are downloaded from the URLs in setup, not invented
mirrors; keep publisher license/readme files with downloaded tools.

The automatic installer supports Windows x64 with Windows PowerShell 5.1+ or
PowerShell 7. Do not claim macOS/Linux/ARM compatibility. On unsupported systems,
explain the limitation rather than installing incompatible binaries or silently
rewriting the engine. Initial setup requires network access and disk space for
Python, wheels, model, tools and video outputs. Healthy installed processing is
local and needs neither a GPU nor an API key. Offline missing dependencies,
blocked publisher downloads, permissions or disk failures must be reported with
the exact failed prerequisite. Never bypass checksum verification. A future
unavailable pinned release needs an explicit, verified project maintenance update.

If a copied `.venv` points to another computer's Python, setup preserves it under
`tmp/venv-before-setup-*` and rebuilds it here. Do not ship virtual environments or
require the recipient to reproduce an author's absolute runtime path. The source,
lockfile, scripts, web files, documentation, AGENTS.md and `.agent/` skill must
travel together; the skill alone is not the processing engine. `models/` and
`assets/` can be downloaded by setup. Sample media and previous outputs are not
dependencies. An external rotoscoping editor and a hosted generation account are
user-selected tools, not prerequisites for this local mesh engine.

## Agent route: original + matching depth

Set `$originalPath`, `$depthPath`, and a unique `$runDirectory` from the current
request. Use absolute paths for uploaded media. Both inputs must exist locally;
if only one is supplied, ask for its matching partner. Depth creation is not a
capability of this engine.

```powershell
.\Mesh-Video.ps1 -Action inspect -Original $originalPath -Depth $depthPath -OutputDirectory $runDirectory
```

Read `compatibility_report.json` and inspect `alignment_contact_sheet.jpg`, then
review additional matching motion moments near cuts or suspected offsets. The
inspection decodes the clips and proposes `alignment.json`; it deliberately leaves
`visually_verified: false`. Equal resolution, duration or aspect ratio does not
prove identical framing or timing.

For verified identical framing, retain the identity affine matrix. Pure resolution
change with identical normalized framing is fine. Check crop, mirror, padding,
rotation, trim/start moment and drift. If measured crop/padding/mirror or constant
time offset is needed, consult `docs/WORKFLOW.md` and set the mapping from evidence.
`source_time_offset_seconds` maps depth time `t` to original time `t + offset`.
Set `visually_verified: true` and meaningful `notes` only after actual review; leave
the current input hashes intact. If you cannot visually inspect, request review
or alignment evidence rather than falsely marking it verified.

This implementation rejects rotated/non-square-pixel media and cannot describe
arbitrary nonlinear timing or shot-dependent spatial remapping. Prepare separate
normalized working copies or correct inputs when needed; retain original files.
Do not hide mismatch by stretching time or increasing tolerance. Run into a fresh
folder if an existing alignment belongs to other input hashes.

```powershell
.\Mesh-Video.ps1 -Action run -Original $originalPath -Depth $depthPath -OutputDirectory $runDirectory
```

The launcher repeats preflight, tracks the original, saves reusable landmarks and
renders to the depth timeline. Optional `-MaxFaces` is 1 through 8 (default 4),
`-OnlyTracks` takes shot-local IDs, and `-Style mesh`, `-Color 00FFFF`, `-Opacity 0.8`,
`-Thickness 1` are default appearance settings. Change them only when useful for
the current footage or requested by the user. Track IDs are geometric continuity,
not person recognition or matte selection. The same person may receive a new ID
after a cut/occlusion. Inspect before filtering IDs.

For appearance-only changes, use `-Action render` with the same input/output paths
and existing landmark JSON; no retracking is needed. `-Action track` can be used
separately when replacing tracking data is intentional. The `run` action tracks
again, so avoid running it just to change line color.

## Existing browser route

`Start-Mesh-Studio.cmd` or `Start-Mesh-Studio.ps1` runs preflight automatically and
starts the existing local backend. Do not send a CLI-preferring user to the UI.
Opening `web/index.html` alone cannot execute Python. If the user already generated
a pair in the UI, locate that specific `outputs/web/<id>/` run and inspect
`job.json`, `web_result.json`, `render_report.json`, `alignment.json` and the videos.
The UI explicitly assumes identical framing and start point, with
`mapping_policy: assume_matching_framing` and `visually_verified: false`. Treat it
as an assumption until visually checked; do not retroactively claim CLI review
occurred. A valid completed web run does not need retracking solely because its
alignment policy differs from the CLI.

## Verify and hand off

For CLI output require current `workflow_status.json` complete and
`render_report.json` passed. For web output require completed job and a passed
render report. Confirm the render's `tracking_sha256` matches `face_landmarks.json`
and the alignment/input fingerprints belong to the supplied pair. Read
`tracking_report.json` and `missing_detection_ranges.json` (half-open intervals),
review `tracking_review.jpg`, `mesh_contact_sheet.jpg` and `comparison_preview.mp4`.
Check mesh placement/timing around changes of view and shots. If additional
verification is needed, run a strict full decode with the discovered ffmpeg:

```powershell
. .\scripts\project_environment.ps1
ffmpeg -v error -xerror -i (Join-Path $runDirectory 'depth_with_mesh.mp4') -f null -
if ($LASTEXITCODE -ne 0) { throw 'Output decode failed' }
```

Never deliver `.partial.mp4`, a comparison with debug labels as generation media,
or an older export left behind after a failed run. The clean MP4 contains depth
plus facial lines, no transparency and no audio. Report measured dimensions,
duration/timing and actual gap ranges; do not reuse the example pair's statistics.
Missing faces remain mesh-free, without frozen/interpolated hidden motion. If a
render is technically complete but visibly misaligned, repair it before handoff.
Link the clean video and optional comparison, then follow the editor handoff in
SKILL.md. Rotoscoping is a separate stage.
