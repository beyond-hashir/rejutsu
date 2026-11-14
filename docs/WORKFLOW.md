# Complete motion-transfer workflow

[← README](../README.md) · [Depth generator](COLAB.md) · [Mesh Studio](WEB_UI.md) · [Development](DEVELOPMENT.md)

## 1. Prepare the reference pair

Start with a color reference and the depth video derived from that same reference. Preserve crop, orientation, timing, speed, and cuts. A resolution difference is supported when the normalized framing matches; matching dimensions alone do not prove alignment.

If you need depth, use the [Colab guide](COLAB.md) and keep its exported `source_reference.mp4` and `depth.mp4` together. Other depth tools can be used if their exports match the color reference.

The local engine rejects rotated video and non-square pixels. Make normalized working copies before processing those formats and derive depth from the normalized reference. Keep your original files.

## 2. Create the facial wireframe

The [browser route](WEB_UI.md) is the quickest option for a pair with identical framing and start time. For reviewed alignment or a measured transform, use the CLI below.

### Command-line processing

Open PowerShell in the project directory. The following paths are examples: put your own videos there or replace them with quoted absolute paths. Choose a fresh output directory for each pair.

```powershell
.\Ensure-Environment.ps1
.\Mesh-Video.ps1 -Action inspect -Original 'inputs\source_reference.mp4' -Depth 'inputs\depth.mp4' -OutputDirectory 'outputs\my-shot'
```

Inspection creates `compatibility_report.json`, `alignment_contact_sheet.jpg`, and a proposed `alignment.json`. It leaves `visually_verified` false.

1. Review corresponding frames near the start, middle, end, recognizable movements, and cuts.
2. Compare face placement, silhouettes, crop, mirroring, borders, and the start moment. Check for timing drift.
3. If framing is identical, keep the identity affine matrix. If a measured transform or constant offset is needed, use the mapping section below.
4. Edit `alignment.json` in a text editor. Set `visually_verified` to `true` only after review, and explain the evidence in `notes`. Keep the recorded input hashes unchanged.
5. Run the same pair into the same inspected folder:

```powershell
.\Mesh-Video.ps1 -Action run -Original 'inputs\source_reference.mp4' -Depth 'inputs\depth.mp4' -OutputDirectory 'outputs\my-shot' -MaxFaces 4
```

The launcher checks the environment, tracks the color reference, saves landmarks, and renders onto the depth timeline. It does not generate the depth input. Reusing an output folder can replace generated files; separate versions need separate folders.

### Coordinate and time mapping

Normalized color-video landmarks pass through `normalized_source_to_depth_affine`, a 2 × 3 matrix in `alignment.json`, before scaling to depth pixels.

| Mapping | Matrix |
| --- | --- |
| Identical normalized framing, including a pure resolution change | `[[1, 0, 0], [0, 1, 0]]` |
| Horizontal mirror | `[[-1, 0, 1], [0, 1, 0]]` |
| Crop or padding | Measured scale/translation for your actual pair |

Depth time `t` maps to source time `t + source_time_offset_seconds`, measured from each clip's first decoded frame. A positive offset means depth time zero corresponds to a later color-reference moment. The nearest source presentation timestamp is used; ties prefer the earlier frame.

`max_timestamp_error_seconds` bounds an acceptable timestamp match. Increasing it does not fix drift. A constant affine transform and time offset cannot represent arbitrary nonlinear timing, missing sections, or shot-dependent crop changes. Prepare corrected inputs or separate aligned sections in those cases. New input hashes require a new review.

### Appearance and track selection

Use `render` with the same paths and existing landmark JSON to change appearance without another inference pass:

```powershell
.\Mesh-Video.ps1 -Action render -Original 'inputs\source_reference.mp4' -Depth 'inputs\depth.mp4' -OutputDirectory 'outputs\my-shot' -Style contours -Color FFFFFF -Opacity 0.8
```

| Option | Meaning |
| --- | --- |
| `-Style mesh`, `contours`, or `dots` | Dense topology, facial contours, or landmark points |
| `-Color 00FFFF` | RGB hex; default cyan |
| `-Opacity 0.8` | Wireframe opacity, 0–1 |
| `-Thickness 1` | Line thickness, 1–8 depth pixels |
| `-MaxFaces 4` | Detection limit, 1–8; does not guarantee every face is detected |
| `-OnlyTracks 1,2` | Render selected shot-local track IDs |
| `-SmoothingMs 12` | Temporal filtering setting used during tracking |
| `-Dots` | Add landmark dots |
| `-NoPreview` | Skip the comparison-video render |
| `-Alignment 'path\alignment.json'` | Use a separately reviewed alignment file |

`track` and `render` can also run separately. `run` tracks again, so use `render` for appearance-only changes. Track IDs follow geometric continuity, not identity recognition or rotoscope selection. A person may get a new ID after a cut or occlusion; review before filtering IDs.

## 3. Review the export

Browser runs are under `outputs/web/<run-id>/`. CLI runs use your specified output directory.

| Artifact | Purpose |
| --- | --- |
| `depth_with_mesh.mp4` | Clean, silent H.264 video for the editor |
| `comparison_preview.mp4` | Side-by-side source and wireframe review; can include debug labels |
| `mesh_contact_sheet.jpg` | Sampled rendered frames |
| `tracking_review.jpg` | Detection-gap and crop-retry samples |
| `face_landmarks.json` | Reusable tracked landmarks and input metadata |
| `tracking_report.json` / `missing_detection_ranges.json` | Detection coverage and half-open missing intervals |
| `compatibility_report.json` / `alignment.json` | Pair checks and spatial/time mapping |
| `render_report.json` | Render validation, settings, and tracking JSON fingerprint |
| `workflow_status.json` | Latest CLI command's stage and completion/failure |
| `job.json`, `web_result.json`, `engine.log` | Browser-run status, result, and diagnostics |

Review placement and timing across the full clip, especially turns, occlusions, crossings, and cuts. Missing detections stay mesh-free. A fresh crop retry can recover a face in the current frame, but does not synthesize hidden motion or freeze old points. Hands/hair can still occlude landmarks; facial tracking does not provide a segmentation mask.

For CLI runs, require `workflow_status.json` to be complete and `render_report.json` to pass. For browser runs, require a completed job and passing render report. The render report's tracking hash identifies the exact landmark JSON used. Older completed files can remain after a failed command; `.partial.mp4` files are unfinished.

If needed, decode a completed export explicitly:

```powershell
. .\scripts\project_environment.ps1
ffmpeg -v error -xerror -i 'outputs\my-shot\depth_with_mesh.mp4' -f null -
if ($LASTEXITCODE -ne 0) { throw 'Output decode failed' }
```

Use the actual export's dimensions and timing in your editor. The clean mesh video contains no alpha channel or audio.

## 4. Composite in your editor

Use Filmora or another editor with rotoscoping/masking and layered video support.

1. Put the **color reference on the lower video track**.
2. Put the **matching depth-plus-wireframe export directly above it**. Align the same moments and retain framing, speed, duration, and cuts.
3. On the upper layer, **keep the character region you intend to replace visible**. Make the rest of that upper layer transparent, revealing the original color background below.
4. Review the matte frame by frame around hair, hands, clothing, carried objects, occlusions, and cuts. Decide which props, shadows, and reflections belong to the replacement region.
5. Export a clean composite at the reference's native display geometry and timing. Omit debug labels, editor UI, comparison framing, and unintended speed changes. Handle audio separately.

The desired composite shows a depth-and-mesh character region against the photographic background. Cutting a hole in the character while leaving the depth background visible reverses the intended mask.

Track filtering in the engine only selects facial lines; it does not create this matte. Repair matte faults in the editor before relying on a prompt.

## 5. Review the composite and write the prompt

The included [agent skill](../.agent/skills/local-motion-transfer/SKILL.md) supports this stage. Supply the finished composite and establish:

- The selected character and exact mask scope, including hair, outfit, props, and reflections.
- What changes and what stays: identity, proportions, wardrobe, environment, performance, expression, camera, cuts, or sound.
- The references you will actually upload and each reference's role. Text-only character descriptions are also possible.
- The generator, model, and mode if attachment syntax or input limits matter.

The default creative direction replaces the selected character while preserving the reference's performance, timing, framing, camera behavior, background, and cuts. A request for a different direction overrides that default.

Write the prompt for the observed actions and chosen references. Use attachment tags only when supported by the chosen platform. The edited composite normally supplies the motion upload; the color reference is for analysis unless you choose to upload it too. The workflow does not launch a paid generation automatically.

## 6. Review the generated video

Compare corresponding moments for performance timing, cuts, identity through turns, body proportions, wardrobe continuity, hand/prop contacts, background/reflections, and matte artifacts. Separate model drift from misleading control media or conflicting references. Revise the specific prompt, reference, or matte that caused the mismatch. Close preservation is a goal; frame-exact AI reconstruction is not guaranteed.

## Common processing failures

| Symptom | What to do |
| --- | --- |
| Python/model import fails or FFmpeg is missing | Run `Ensure-Environment.ps1`; read the exact failing prerequisite if repair fails. |
| Input differs from the reviewed/tracked file | Inspect into a fresh folder, review that actual pair, and track its color reference. |
| Mesh follows the wrong location | Check crop, mirror, rotation, and padding; measure and review the affine mapping. |
| Mesh timing is offset | Compare recognizable gestures and measure the signed offset. Correct drifting inputs rather than widening tolerance. |
| Mesh disappears | Review the source, gap ranges, and tracking sheet. Turns, blur, distance, and occlusion can defeat detection. |
| A second face is missed | Inspect its size and visibility. Raising the face limit alone does not guarantee recovery. |
| Track IDs exchange | Review crossings and ambiguity flags; geometric association is not identity recognition. |
| Export seems stale | Check the latest status and tracking hash; do not use a partial file. |

For launch, upload, and save-dialog issues, see [Mesh Studio troubleshooting](WEB_UI.md#troubleshooting).
