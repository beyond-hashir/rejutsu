---
name: local-motion-transfer
description: Prepare depth videos with facial wireframes from matching originals, guide rotoscoping over the original background, analyze the resulting motion reference, and write custom character-replacement video prompts using this project's local tools.
---

# Local motion transfer

Run this project's existing engine and guide the user from two input videos to a
reviewed, bespoke reference-to-video prompt. All required workflow knowledge is in
this skill and this project. Never require another skill, the owner's prior chat,
personal paths, wardrobe plugin, or prompting plugin. Do not rewrite the shipped
Python files just to change inputs.

The default creative direction is to replace the selected character while matching
the supplied performance: movement, visible expression, head orientation, timing,
framing, camera behavior, interactions, background and cuts. User-requested changes
override these defaults. Request close preservation; do not promise frame-exact AI
generation or reconstruction of hidden facial expressions.

## Locate and resume

Find the project root by the presence of `Mesh-Video.ps1`, `requirements.lock` and
`scripts/mesh_video.py` (normally three directories above this skill). Resolve all
paths from that root, never from an author's drive letter. This is currently a
Windows x64 project; see the processing reference for setup boundaries.

If starting from original + matching depth, begin at stage 1. If the user already
used Mesh Studio, reuse its actual completed run after checking reports and video.
If a composite is supplied, begin at stage 3, inspecting the actual media and
asking for the original only when needed to resolve ambiguity. If only a prompt
revision is requested, use the established brief and inspect new references; do
not rerun tracking unnecessarily.

Keep a small `session.json` in the pair's unique output directory to resume across
turns: stage, absolute input paths, engine output directory, composite path if
supplied, selected subject/matte scope, agreed edits, references and their roles,
unresolved questions, and latest prompt path. Record only known facts. Useful
stages are `preparing`, `awaiting-composite`, `clarifying-edits`, `prompt-ready`, and
`reviewing-result`. Reports establish render success, not this note alone.

## 1. Check tools, process and review

Read [processing.md](references/processing.md). Before each full processing session,
run `Ensure-Environment.ps1`: check this PC, install/repair missing local tools,
Python, locked packages and verified model, then pass the smoke check before
processing. Existing healthy installs work offline. Do not tell a user to manually
recreate source files or install prerequisites the setup script can handle.

Use the provided original RGB and matching depth videos in a fresh output folder.
Inspect and verify their actual spatial/time mapping, track facial landmarks on
the **original RGB**, and render them onto the **depth**. The RGB also supplies
semantic action analysis; depth alone can confuse garments, hair, hands and props.
Review tracking gaps, timing, shot changes and the final clean export.

Read [video-analysis.md](references/video-analysis.md) for the original/composite
audit. Complete the initial original analysis while preparing the wireframe;
save visible action beats and concrete risks for later prompting. Ask only for
missing input information needed to proceed; creative references are not required
to finish the mesh.

## 2. Deliver the wireframe and guide the editor

**Before giving a final generation prompt or a long creative questionnaire**, give
the user the clean `depth_with_mesh.mp4`, a comparison link, and a concise report of
any tracking/alignment limitations. Use actual paths and measured output settings.
Then explain the manual compositing step in Filmora or their chosen editor:

1. Put the original color video on the lower video track.
2. Put the matching depth-plus-wireframe export directly above it; align both to
   the same source moment and preserve framing, duration, speed and cuts.
3. Rotoscope/cut out the **character region to be replaced** in the upper layer,
   keeping that depth-and-mesh region visible and the rest of the upper layer
   transparent. The lower original supplies the photographic background. Do not
   cut a hole in the character and leave the depth background visible.
4. Review the matte frame by frame around hands, hair, loose clothing, props,
   occlusions and cuts. Decide explicitly which belong to the replacement region.
   Track selection in the engine is not a rotoscope mask. The mesh export itself
   has no alpha channel and does not preserve the original color background.
5. Export a clean composite at the actual reference's native display geometry and
   timing; omit editor overlays, comparison labels and accidental speed changes.
   Audio is separate: the mesh export is silent. Preserve or add audio only as
   requested and supported by the eventual generator.

Tell the user the next stage is video creation. Ask them to return the composite
when ready, then establish references and changes based on **what they masked**.
If they already supplied the finished composite and answers, continue directly.
Do not claim to have done a manual edit or watched an unsupplied composite.

## 3. Review the composite, clarify edits and references

Inspect the full composite timeline using [video-analysis.md](references/video-analysis.md).
Compare with the original when available; report concrete cues that could mislead
generation and distinguish observations from likely risks. Prioritize matte faults
that should be repaired in the editor rather than claiming a prompt will fix them.

Ask a concise, adaptive set of questions, skipping answered items:

- Which person/region was rotoscoped? Which hair, garments, carried objects and
  reflections are included or excluded?
- What should change: character, proportions, outfit, location, props, actions,
  camera, cuts, expressions or sound? What must remain? Default to character-only
  replacement with the original performance and edit preserved.
- What character/outfit/location/other references will be uploaded? Inspect them,
  explain each role and resolve conflicts. Reference sheets are optional; use a
  sufficiently clear text description if that is the user's choice.
- Which generator, exact model and mode will be used? Ask only if it affects
  attachment tags, input limits or instructions. Do not silently reinterpret a
  spoken model name or invent mode capabilities. Verify current limits from the
  provider's official documentation when needed; generic prompting can proceed
  without unsupported capability claims.

Wait for answers that determine the replacement or references before finalizing.
If the composite cannot be attached, ask for an explicit matte-scope description
and export confirmation, then disclose that visual composite QA remains unverified.
Do not upload the original RGB by default: it is analysis-only unless the user
chooses otherwise. The final edited composite normally becomes the motion upload.

## 4. Write a bespoke prompt

Read [prompting.md](references/prompting.md). Write new prose for this video's
actual actions, masking choices, changes and inspected references. There is no
ready-made scene prompt to fill in. Reuse only universal constraints that apply.
Do not copy the owner's successful example, its character, outfit, room, duration,
aspect ratio, face-gap times or attachment order into unrelated work.

Deliver the confirmed attachment-to-tag map, one ready-to-paste prompt, and a short
list of the most important result checks. Save `prompt.txt` and the final reference
roles/brief beside the session record. No unfilled placeholders or invented tags.
If provider-specific tagging is unconfirmed, state the assumption outside the
prompt or use plain asset names. Do not imply every platform supports `@image1`.

Do not launch a paid generation, upload media, create accounts, or install a
commercial editor merely to deliver a prompt. Those require a user's request and
available access. Installation here covers the shipped local processing engine.

## 5. Review a generation when supplied

Compare result and reference by corresponding moments: performance timing, cuts,
identity after turns, physique, wardrobe continuity, hand/prop contacts, matte
artifacts and background/reflections. Distinguish model drift from bad control
media or a conflicting reference. Revise the specific instruction/reference/matte
that caused the mismatch; do not accumulate unrelated negative constraints. Keep
the latest prompt and agreed changes in the same session.
