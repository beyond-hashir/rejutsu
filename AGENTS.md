# Motion transfer workflow

For processing original/depth video pairs, reviewing a rotoscoped motion reference,
or preparing reference-to-video character replacement prompts, read
`.agent/skills/local-motion-transfer/SKILL.md` and follow its stage-specific references.
This is the project's self-contained workflow; do not require the owner's private
skills, previous chats, external drives, or sample videos.

The skill lives in `.agent/` as requested by the project owner. This routing file
lets repository-aware agents find it without assuming `.agent/` is a native skill
discovery directory. Use the existing scripts; do not rebuild the engine to process
a new pair. Run `Ensure-Environment.ps1` before a full processing session.
