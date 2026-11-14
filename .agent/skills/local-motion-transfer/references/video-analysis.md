# Analyze what the reference actually says

Audit the original for meaning and the finished composite for the cues the
generator will receive. Existing tracking reports are evidence of detections,
not evidence of actions, wardrobe identity, dialogue or emotion. Inspect media
with available video/image tools. If there is no direct video viewer, use the
installed FFmpeg to extract frames into this run's analysis directory and inspect
the images with the host's image-viewing capability. Probe metadata using ffprobe.
Do not claim visual review based only on JSON or a command finishing.

Start with a timeline overview, then inspect every shot and densify sampling at
cuts, rapid gestures, garment changes, occlusions, contacts and tracking gaps.
Representative samples alone do not establish every frame's matte quality. Use
adjacent-frame review or playback for timing and movement uncertainty. For long
media, make manageable segments/contact sheets and cover the complete timeline.
If the host cannot inspect images/video, disclose that and ask for the needed
description/review; don't invent a shot audit. Listen to audio only if supported;
otherwise explicitly leave speech/music content unassessed. A stream's presence
does not tell you what it sounds like.

For example, with actual paths already assigned in PowerShell:

```powershell
. .\scripts\project_environment.ps1
$analysisDirectory = Join-Path $runDirectory 'analysis'
New-Item -ItemType Directory -Path $analysisDirectory -Force | Out-Null
ffmpeg -v error -i $originalPath -vf 'fps=2,scale=480:-2' (Join-Path $analysisDirectory 'original-%05d.jpg')
```

Use higher temporal resolution or selected time ranges for fast motion. Do not
assume two frames per second is sufficient for lips, cuts, fabric contacts or
edge chatter. Do not overwrite previous analysis images accidentally. The run's
alignment/mesh sheets are useful starting points, not full semantic analysis.

## Save a compact, evidence-based shot audit

Record time range, visible action, facing/head direction, facial visibility,
garment state and hand contacts, props/interactions, camera/framing and cuts.
Describe visible performance rather than inventing a story. Separate observed
facts, user explanations, and uncertain interpretations. If the user identifies
an ambiguous hanging object as part of a garment, use that explanation and check
its visible connections instead of inventing an extra limb or unrelated cloth.

Use the original to understand what happens; use the composite to determine which
information is actually available to the generator. Record what is inside the
depth matte, what remains photographic and whether a mirror/reflection contains
an unreplaced source person. Original-only detail can inform prose but cannot be
described as visible in the uploaded reference when it isn't.

## Find actionable conflicts

Discuss only the risks supported by this video. Useful questions:

- Are timing, crop, speed and shot boundaries still aligned after compositing?
  Did an editor add a transition that was absent from the source?
- Does the matte include the complete intended subject and manipulated garments?
  Are there holes, source face/hair remnants, bright halos, jagged/flickering
  boundaries or a double edge? Is there photographic skin visible inside an
  intended full replacement region? Repair significant faults before generation.
- Does a foreground hand/object cross the subject? Facial landmarks alone do not
  supply an occlusion mask. Has the matte flattened a prop, removed its contact
  surface, or hidden the information needed for the target interaction?
- Are multiple people, mirrors or reflections ambiguous? Distinguish an intended
  reflection from a second independent person. Review pose/handedness in screen
  space and anatomical space separately.
- Where does the face mesh disappear? Read actual gap ranges and inspect them.
  A back-facing head must stay back-facing; do not force a frontal face into an
  unseen interval. Preserve identity when it returns without claiming hidden
  expressions were recovered.
- Does the proposed character's build conflict with the depth silhouette? Decide
  whether target proportions or source proportions govern; normally video gives
  pose and reference images give the replacement anatomy.
- Does the target outfit support the existing action? Opening, lifting, removing,
  tying, gripping or pulling requires corresponding garment parts and contacts.
  If they don't exist, ask whether to change the garment or the gesture. Prompting
  cannot make a physically incompatible pair exact.
- Does a background/prop replacement remove the object a hand reaches toward?
  Does new lighting contradict a photographic background that is to remain?
- Does a requested camera move/wider crop require unseen anatomy or scenery? Make
  that an intentional deviation, not an accidental addition to a motion-copy task.

Keep the report useful: what is visible, how it could mislead generation, and what
the user/editor/prompt must decide. A risk is not an observed model failure. Don't
promise depth + mesh is a model-native control signal or guarantees exact copying.
After the composite review, resolve the creative brief and reference roles before
writing the final prompt.
