# Changelog

## v0.3.3 — 2026-11-02

- **Mouse wheel scrolls the timeline sideways** when the scenes don't fit. Shift + wheel scrolls up and down; Alt + wheel still zooms.
- **The playhead only moves where you click** (the ruler or an empty part of a lane). It no longer follows the mouse: the ruler's drag tracking used window listeners that could miss the button release inside ComfyUI and keep running. Drags now track the button state and always end.
- **Dragging the timeline pans it**, from the ruler, an empty lane or a scene block; the playhead stays put and the press doesn't select a scene or drag the node. To scrub, drag the playhead's time label.
- Timeline mouse maths (click, pan, scrub, shot ticks, scene resize, dropping an asset) now account for ComfyUI's canvas zoom; at zoom levels other than 100 % they were off.

## v0.3.2 — 2026-11-02

- **Describe with thinking models** (Qwen3 and similar on SGLang or vLLM): Describe gave the model only 400 tokens. A model that reasons first often used them all on reasoning, so the reply had no answer and Describe said "The model returned no text. Is it a vision model?". How long the reasoning runs varies per picture and per try, which is why it worked sometimes.
  - Describe now allows max(Max tokens, 6000) tokens. If the model still runs out while thinking, it asks once more with thinking off and says so under the answer.
  - New **Thinking** setting (Global → Prompt rewriter): *Model default* or *Off*. Off sends `chat_template_kwargs: {"enable_thinking": false}`, which SGLang and vLLM pass to Qwen3-style chat templates; faster, and Describe then uses 600 tokens.
  - Every LLM call reads the reasoning (`reasoning_content`, `reasoning` or an unclosed `<think>`) and `finish_reason`, so a cut-off reply says "used all N tokens thinking" instead of "no text". The "Is it a vision model?" hint only appears when the model really answered with nothing.
  - Test connection notes when the model thinks before answering.

## v0.3.1 — 2026-11-02

- Script import (Global → Import a script) asks where the proposed scenes go: **at the end**, **after the selected scene**, or **replace all scenes**. Replacing asks first; cast, assets and Global settings stay, and rendered takes stay on disk. The first imported scene is selected, the film's first scene always starts fresh, and Ctrl+Z undoes the import.

## v0.3.0 — 2026-11-02

- **Profiles** (Global tab): save the Global settings under a name, apply them to any project, update or delete them, and mark one as the default for new nodes. They live in `user/reelwright/profiles.json` and are shared by every Reelwright node. A new node starts with the default profile and shows a banner to pick another one.
- **Per-scene quality**: a scene can render as Draft or Final regardless of the Global switch (Scene tab → Generation → Quality, or the scene's right-click menu). Draft scenes get a tag on the timeline. Quality is part of the cache key.
- **Per-scene transitions**: a scene that starts fresh can set its own cut, crossfade or dip, its length and its audio fade (Scene tab → Starts from → Cut into this scene). The Merge card's values are now the defaults.
- Deleting a scene asks first. Deleting the only scene resets it to an empty scene instead of leaving it unchanged.
- **Assets can be deleted** from the inspector or their right-click menu (asset cards and the timeline bin), with confirmation. They are removed from every scene, cast anchor, voice, outfit and the score track; the file stays on disk.
- Ctrl + wheel over the node zooms the ComfyUI canvas, as the wheel does over empty space. Over text fields and lists it does nothing. Alt + wheel still zooms the timeline.
- Render progress: the Render tab shows "Scene k of n" with a bar for the scene and one for the whole run, and the node title shows `rendering k/n · NN%`.
- LLM **Test connection** now reports its result under the button and as a message, and gives up after 20 seconds instead of appearing to do nothing. It tests the URL and model shown on the tab.

## v0.2.2 — 2026-11-02

- Right-click inside the editor no longer opens ComfyUI's node menu, where Delete removed the whole node. Scenes, on the timeline and on the Scene tab strip, get their own menu: open, render, new take, split at playhead, duplicate, move, lock and delete. Text fields keep the browser's copy/paste menu.
- Mouse wheel inside the editor scrolls the editor instead of zooming the canvas. This mostly affected ComfyUI's "Nodes 2.0" mode. Alt or Ctrl + wheel on the timeline still zooms the timeline.
- Dropdown lists stay open when you press or drag their scrollbar, and keep what you typed. The list scrollbar is now always visible.

## v0.2.1 — 2026-11-02

Fixes a crash after a render when the automatic merge failed.

- Merge: the final audio is pinned to 48 kHz stereo (`aformat` plus `-ac 2`). Newer ffmpeg builds (for example conda-forge's) failed with "Cannot select channel layout for the link between filters … and format_out".
- Merge writes to `<cut>.partial.mp4` and renames it only on success, so a failed merge no longer leaves a broken `<slug>_cut_vN.mp4`.
- Node: after a failed merge it outputs the last scene's take instead of the newest cut, and skips any video ffprobe can't read. `merge.probe` now raises a readable `MergeError` instead of `CalledProcessError`.
- Editor: a failed automatic merge now shows a toast and the error in the Merge card.

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
