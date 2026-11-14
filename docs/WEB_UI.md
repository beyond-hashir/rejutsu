# Mesh Studio browser interface

[← README](../README.md) · [Depth generator](COLAB.md) · [Full workflow](WORKFLOW.md)

## Launch and use

Double-click `Start-Mesh-Studio.cmd` from the project folder. The launcher checks the environment and installs/repairs missing tools before opening the default browser at `http://127.0.0.1:8765`; first setup needs internet on Windows x64. It keeps the Python backend running in its console window. Closing that window stops the app. Run `Start-Mesh-Studio.ps1 -Port 8766` if another app occupies the default port. The server binds only to this computer's loopback address.

Add the original color video and its exact matching depth export, then click **Create wireframe**. File selection and drag-and-drop both work. The page previews the two inputs, reports progress, and displays the finished silent MP4. **Comparison** shows the source and mesh-over-depth together. **Save video** saves the preview currently selected, so the comparison can be saved too.

When supported, Save video opens the browser's native save picker before streaming the output to the selected file. Otherwise it uses a standard MP4 download. Enable your browser's “Ask where to save each file” download preference yourself if you want a location choice for every fallback download. An embedded browser may support fewer native file dialogs than Chrome or Edge.

The app is an HTML/CSS/JavaScript frontend with a small Python standard-library server. Opening the HTML as a `file://` page cannot execute the native Python pipeline. The launcher supplies that backend; no web framework installation, cloud account or API credential is required.

## Matching assumptions

The one-button UI accepts the two uploads as a matching pair. It checks aspect ratio, duration and every timestamp match before tracking. Unexplained timing differences and unsupported rotation/display geometry stop the run with an error. Pure resolution changes are supported.

The interface assumes identical crop/framing, no mirroring and zero trim offset. It records `visually_verified: false` and `mapping_policy: assume_matching_framing` in each run's alignment report. Only the web worker explicitly opts into that policy; the ordinary CLI still requires a reviewed alignment. The output preview is the place to check the spatial match. For a measured affine transform or time offset, use the documented command-line alignment workflow.

Face detection can fail on turned, small, blurred or obscured faces. Result notes report omitted meshes. A higher maximum face count does not guarantee detection or identity continuity. The app does not synthesize hidden facial movement or audio.

## Runs and recovery

Uploads and results live in `outputs/web/<run-id>/`. Each run has separate input copies, completed MP4s, landmark data, compatibility/alignment reports, `engine.log`, and persisted `job.json`. Each browser run gets a fresh folder and leaves your selected original files unchanged. Retained videos and JSON consume disk space; nothing is automatically deleted. Stop the server before manually removing an old run folder. These folders are excluded from Git.

One worker processes runs sequentially, with up to four active uploads/queued/running jobs accepted. **Cancel run** cancels queued work or terminates its worker; partial files are never offered as finished videos. Completed runs remain in **Recent runs** after server restarts. An interrupted server marks incomplete runs as failed on restart instead of presenting stale partial output as complete. Reloading during processing reconnects to the active run; reloading during an unfinished upload requires selecting the files again.

Video responses support byte ranges for browser playback and seeking. Only completed, explicitly listed output artifacts can be retrieved. Mutating requests require the current page session token and matching loopback origin. These measures keep the local app scoped to the browser page without exposing a file-system API.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Page says engine offline | Start the launcher and refresh the page. Do not open `web/index.html` directly. |
| Address already in use | Reuse the existing Mesh Studio tab, or launch with a different port. |
| Engine setup needs attention | Run `Check-Environment.ps1`; repair missing packages/model with `scripts/setup.ps1`. |
| PowerShell says scripts are disabled | After reviewing the downloaded project, open PowerShell in its folder and run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Mesh-Studio.ps1`. This applies to that process only; organization policy may still prevent execution. |
| Input preview unavailable | Some browser codecs are unsupported. The native engine still checks and may process that video. |
| Duration/framing proportion error | Supply the exact untrimmed original/depth pair with the same aspect ratio. |
| Mesh is spatially offset | Check crop/padding/mirror differences in Comparison; use a reviewed CLI alignment for transformed inputs. |
| Save opens a download instead of a picker | Use Chrome/Edge for native picker support or your browser's download location preference. |
| Upload connection interrupted | Keep the server window running, select both files again and create a new run. |
| Processing fails | Read the message in the page. `engine.log` in that run's folder provides native error details. |

## Verification

See [Development and testing](DEVELOPMENT.md) for the automated HTTP, alignment, media, and integration checks. Tests create their own temporary fixtures; no personal footage or previous run reports are required. Review each actual output visually before using it in an editor or generator.
