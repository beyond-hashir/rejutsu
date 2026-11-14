# Write from the footage and agreed edit

This is a set of decisions and checks, not a scene-prompt template. Draft fresh
prose after examining the composite, original analysis, requested changes and
actual reference images. Include only clauses that apply. A reference-driven
replacement task does not need invented dramatic goals, emotional reversals,
cinematic lens changes or a new storyline.

## Establish a single authority for each attribute

Confirm attachment names and upload order before assigning tags. In platforms
that support them, `@video1` can identify the edited composite and `@image1`,
`@image2` etc. the actual uploaded images. Those numbers are examples of syntax,
not permanent assignments. Use the selected provider/mode's supported syntax.
The original RGB normally stays analysis-only; do not instruct the generator to
read a video the user will not upload. Sheet panels depict views of one subject
or garment, not extra people or an output collage.

Set roles according to the user's brief:

| Attribute | Usual authority | Conflict to resolve |
| --- | --- | --- |
| Motion, pose, visible expression, camera/framing and edit | Edited composite video | User may deliberately change an action, crop, cut or performance. |
| Identity, face, hair, skin details and physique | Character images or agreed description | A source silhouette does not automatically override the requested build. |
| Garments, materials, fit and design | Outfit images or agreed clothing | Outfit reference overrides incidental clothes on an identity sheet when so agreed. |
| Environment, reflections, props and light | Photographic composite regions by default | A replacement location/prop can contradict preserved contacts or lighting. |
| Sound/voice/music | User-approved audio/reference or explicit direction | Mesh export is silent; platform audio support and original audio must be confirmed. |

Inspect all supplied images. A portrait may govern the face while front/back
views govern proportions and markings. Resolve contradictory hairstyles,
tattoo sides, body builds or garments; do not hide unresolved differences behind
"follow all references." Ask one focused question when the answer changes the
output. If the user delegates a choice, state the chosen priority outside the
prompt and apply it consistently. Request additional views only when missing
information matters for the footage, such as a back view during long rear shots.

## Describe the intended replacement region and preservation

Open with the actual transformation in plain language: the selected character or
characters become the agreed target while the agreed motion and scene persist.
For a partial matte, describe exactly what changes and how the new region joins
the remaining photographic body, clothing or props. Do not say "replace the whole
person" when only a head or garment was masked. If the matte and requested scope
conflict, resolve or repair it before finalizing.

In a standard full-character replacement, assign depth/mesh to performance and
spatial guidance, and target references to photographic appearance. Say the depth
surface, colored facial lines and masking outlines should become the finished
subject. Keep the photographic background authoritative when it remains in the
composite. Prompting is not a substitute for repairing missing or corrupted matte
regions.

User edits override preservation only where specified. For a character with
different proportions, preserve pose, contact, framing and timing while fitting
the action to the target anatomy. Do not simultaneously demand identical source
body shape and a conflicting target physique. For a new background, specify how
retained props, reflections and lighting relate to the new space.

## Transfer the visible performance

Describe the actual ordered actions and interactions that carry this video's
meaning. Call out ambiguous or failure-prone moments rather than repeating every
sampled frame. Use timestamps or shot-local descriptions when they improve
precision; measure them on the final uploaded composite, not an older edit.

Preserve the observed timing of weight shifts, torso turns, limbs, hand contacts,
head orientation, eye direction and visible expression changes. A still portrait's
smile or gaze defines neither the entire performance nor every head angle. Let
the video control expression over time. Do not add talking, smiling, blinking
patterns, seductive behavior, emotional escalation or unrelated gestures unless
requested or visibly present.

For faces, distinguish visible gaze/expression from head pose and from inferred
emotion. Keep attention and reactions aligned with what the person is visibly
doing. During occlusions or mesh gaps, preserve the same identity, respect the
visible head/body orientation and hidden face, and recover consistent identity
on reappearance. Avoid claiming exact absent facial motion. If changed dialogue
or acting is requested, establish delivery, listener/eyeline, timing and visible
responses for those moments without importing an external acting skill.

Preserve hard cuts, shot order, shot start/end poses and framing when those are
part of the brief. Clothing state may reset at a cut if it does so in the source.
Do not turn a montage into one continuous take or invent transitions and camera
motion. Match actual aspect ratio and visible field of view; never default every
project to vertical, a particular frame rate, duration or lens.

## Make wardrobe physically legible

Identify relevant garment parts, material behavior, fit, layers and closures from
the references. State which remains worn, which is manipulated, where hands grip,
and how tension, folds, gravity and occlusion follow the motion. Loose fabric
belongs to its garment, with attached panels, sleeves, cuffs, hood, straps and hem
as appropriate; do not describe disconnected pieces when they are one item.

Only include parts that actually exist. Do not make a pullover unzip, transfer an
outerwear-removal action to a rigid dress without an agreed adaptation, or retain
the source outfit merely because it appears in the depth silhouette. Establish
layer order and intended coverage for garment opening/removal. Front/back design,
patterns, straps and markings should remain coherent through turns. Account for
loose clothing inside/outside the matte; excluded original fabric cannot also
become a different outfit without an explicit edit plan.

Use specific construction/color/material facts rather than generic fashion
adjectives. The user's actual clothing references control the outfit; do not
require a wardrobe skill or automatically generate clothing sheets.

## Preserve space, identity and object contact

Keep distinguishing features attached to the right anatomical location, through
turns and mirror views. Screen-left in a mirrored image is not a reliable synonym
for anatomical right. If side is ambiguous, describe the inspected reference's
placement and orientation instead of inventing it. Consistent skin, hair, body
shape and markings should survive cuts and face reappearance.

State the intended subject count and reflection arrangement if ambiguous. Avoid
"one person, no duplicates" if the scene requires multiple people or a visible
mirror reflection. Maintain original scene geometry, object positions, contact
and light when preserved. If a prop is replaced/removed, adjust the related
interaction as agreed. Include photographic skin, hair and fabric integration
when photorealism is wanted; do not force that style on a deliberately stylized
request. Do not add an anamorphic/film look to a faithful reference copy by habit.

## Final prompt check and delivery

The final text may use short sections for complex footage or connected prose for
a simple shot. Structure follows the case, not a mandatory heading sequence.
Apply only relevant, universal constraints, such as maintaining identity through
occlusion, preserving agreed cuts/contacts, making garment connections coherent,
and removing visible guidance graphics. Avoid an accumulating negative-prompt list.

Before delivery verify:

- Every attachment/tag exists, maps to the intended file and has a clear role.
  No original-only image/video is referenced as uploaded without agreement.
- Edits match the matte and user brief. Reference priorities are unambiguous.
- All named actions, garment parts, props, sides, timings and output settings are
  supported by the actual media or the user's explicit instruction.
- Preservation and requested changes do not contradict each other; uncovered
  limitations are stated outside the prompt rather than disguised as certainty.
- There are no sample-character details, fixed example timings, placeholders,
  private skill dependencies, platform-specific invented features, or unintended
  instructions to recreate a reference sheet's panels/labels/background.

Deliver the confirmed upload map, a single copyable prompt, then the few checks
that most affect this generation. Targeted checks might include identity returning
after a turn, target build retention, a particular garment connection, a hand/prop
contact, cuts or reflection consistency. Exact output is a generation test, not
something a prompt can guarantee. When a result is supplied, inspect the evidence
and revise only what needs correction.
