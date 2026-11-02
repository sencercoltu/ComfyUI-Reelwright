# Changelog

## v0.2.0 — 2026-11-02

Prompts now follow MiniMax's official Ref2VA guide, and the editor gets searchable pickers, ComfyUI file browsing and vision descriptions.

- Prompt format (MiniMax H3 `ref-en.txt`):
  - six labelled sections, each label on its own line: `subject_definitions:`, `summary:`, `retention_analysis:`, `detailed_description:`, `overall_soundscape:`, `non_diegetic_music:` (empty ones are `N/A`);
  - reference pictures that define a character, place, prop or style become `<Subject N>`, with a subject line from the asset's new description;
  - retention lines name the shots a subject appears in;
  - shots read `[Shot 1] A wide shot: …` and `[Shot 2] At 00:06.000, the shot cuts to …`;
  - speaker IDs follow speaking order in each clip (S1, S2…), so the Cast tab no longer has a Speaker ID field;
  - info lints for a short detailed description, an empty soundscape and an undescribed reference asset.
- LLM:
  - **Download** MiniMax's official H3 guides (Ref2VA and base) into `user/reelwright/guides/`; they are sent with rewrite, split and script import when *H3 guides* is on, otherwise a built-in summary is sent;
  - Rewrite now sees the built pass-1 prompt;
  - **Describe with LLM** for assets (picture, or three video frames) and **From anchors** for cast entries, with your own question; the answer is a suggestion you can use or append.
- Assets: **From ComfyUI** browses ComfyUI's input and output folders (filter by path and kind, multi-select); output files are linked into the project's input folder.
- Pickers: every drop-down is a type-to-filter combobox. Language and LLM model also accept typed values.
- Help: **?** popovers open beside their icon, stay inside the node at any canvas zoom, and can be dragged by the header; tooltips are clamped to the node.
- Render tab: **Merge** moved from the tab bar to the scenes-and-takes table, with a link to the last cut; a **File** column shows each scene's rendered video.
- Take videos are named `<project>_<NN>_<scene title>_<take>.mp4` instead of `video.mp4` (older takes keep their names).
- New routes: `/reelwright/llm/guides`, `/reelwright/llm/describe`, `/reelwright/files`, `/reelwright/import`.

## v0.1.0 — 2026-11-02

First version.

- Reelwright node with an editor inside it: Timeline, Scene, Assets, Cast, Render and Global tabs.
- Scenes of any length: planner on the H3 17k+5 grid (124–362 frames per pass).
  - Long scenes are split at shot cuts or with guided overlaps.
  - Short scenes are trimmed from the shortest pass, keeping handles.
- Scene starts: fresh, last frame of the previous scene, or tail clip of the previous scene (`MiniMaxH3AddGuide` clip and audio).
- Global settings with per-scene overrides: models, VAEs, LoRA stack (add or replace), seed, steps, sampler, size.
- Cast: anchor sheets, outfits, voice, speaker IDs, identity LoRA.
  - Re-anchor rule.
  - Optional insightface drift check.
- References, renumbered per pass in native order:
  - retention labels, keyframes, first and last frames;
  - video soundtracks;
  - budget warnings.
- Structured six-section prompt editor with `@tags`, auto subjects, retention, shots and dialogue, and a per-pass preview.
- Render:
  - content cache keys, takes and stars;
  - resume, lock;
  - render scopes (pending, selected, from playhead, all, new take);
  - draft/final;
  - memory policies, encode-first;
  - live progress.
- Merge (ffmpeg):
  - cut, crossfade, dip, continuation crossfades;
  - loudnorm, ducked score track, colour match;
  - SRT, chapters, OTIO, FCPXML, bundle.
- OpenAI-compatible prompt rewriter, pass splitter and script import. Runs only on click.
- Autosave with versions, undo and redo, keyboard shortcuts, a tooltip and **?** help for every control.
