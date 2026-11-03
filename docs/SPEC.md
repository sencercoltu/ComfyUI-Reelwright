# Reelwright — feature specification

Reelwright is a single ComfyUI node with a built-in timeline editor. You use it to make
videos of any length with MiniMax H3 ref2va. It splits a project into scenes,
renders them with the native H3 nodes, and keeps every finished scene on
disk. Changing one scene re-renders only what depends on it. **Merge scenes**
joins the finished scenes into one film.

Status markers: ✅ implemented in v0.1 · 🧪 implemented, needs real-model
validation · 🗺️ roadmap.

## 1. Node

| | |
|---|---|
| ✅ Node id | `Reelwright` (category `video/Reelwright`) |
| ✅ Optional inputs | `model`, `clip`, `vae`, `audio_vae`. A wired input replaces the matching Global-tab loader for the whole run. |
| ✅ Outputs | `video` (the merged cut, or the last rendered scene), `last_frame`, `audio`, `scene_plan` (JSON) |
| ✅ Editor | Timeline · Scene · Assets · Cast · Render · Global tabs inside the node |
| ✅ Pickers | Every drop-down is a type-to-filter combobox (every typed word must match); language and LLM model also accept values that are not in the list |
| ✅ Help | Every control has a hover tooltip; every section has a **?** button with a longer explanation that opens beside the icon, stays inside the node and can be dragged by its header |
| ✅ Storage | Settings are saved in the workflow, plus an autosave with versions on disk. Renders live under `output/reelwright/<project>/` |

The node does not output a frame batch for the whole film. A 90 s film at
1344×768 would need about 27 GB of RAM. The scene files on disk are the
output, and `video` points at them.

## 2. Global settings (Global tab)

- ✅ Project name, output folder name.
- ✅ Models: diffusion model (ref2va), text encoder (Qwen3-VL, `minimax` CLIP type), video VAE, audio VAE, optional latent upscaler. Weight dtype and CLIP device are selectable.
- ✅ Global LoRA stack: enable, strength, order. Applied to every scene first.
- ✅ Output: aspect presets (21:9, 16:9, 4:3, 1:1, 3:4, 9:16) using the native H3 canvas rule (768 short edge, 768×1344 area cap, multiples of 32), or a custom width × height. Reference image size can be set to `match` or `max`.
- ✅ Sampling: steps, sampler (default `res_multistep`), scheduler (`simple`), seed and seed mode (fixed / +1 per scene / random), optional H3 sigma shifts (video 12, audio 3). CFG is fixed at 1.0 because H3 is CFG-distilled.
- ✅ Draft mode: lower resolution, fewer steps and an optional turbo LoRA, with the same seeds. Use it for fast previews, then render Final.
- ✅ New-scene defaults: duration, how a scene starts, overlap frames, dialogue language.
- ✅ Long-scene settings: longest pass, overlap, crossfade, seam mode, how far a seam may move to land on a cut.
- ✅ Memory policy and the "encode all prompts first" switch (see §8).
- ✅ LLM settings: OpenAI-compatible base URL, model, temperature, max tokens and presets. The API key is stored in the ComfyUI user folder, never in the workflow.
- ✅ Profiles: save the whole Global tab under a name and apply it to any project; update, delete and mark one as the default for new nodes. Stored in `user/reelwright/profiles.json` (never the API key) and shared by every Reelwright node on the server. A new node starts with the default profile and shows a banner to pick another.
- ✅ Override matrix: shows which scenes override which global setting.
- ✅ Autosaved versions: list them (date, time, size), restore one, delete one or delete all. The project's latest autosave (`project.json`) is never deleted.

## 3. Scenes (Timeline + Scene tabs)

- ✅ Unlimited scenes. Add, duplicate, delete, reorder, split at the playhead. Deleting asks for confirmation; deleting the only scene resets it to an empty scene.
- ✅ Right-click a scene (timeline or Scene tab strip) or an asset for its own menu; ComfyUI's node menu does not open inside the editor.
- ✅ Duration: drag the right edge of a scene on the timeline, or type it. Any length is allowed (see §5).
- ✅ How a scene starts:
  - **Fresh start**: hard cut, nothing carried over.
  - **Last frame**: the previous scene's final frame becomes guide frame 0 (fully preserved).
  - **Tail clip**: the previous scene's last N frames (17k+5) become a guide clip at frame 0, plus its audio. The overlap is trimmed in the final cut, so motion, light and sound continue.
- ✅ References: any asset, with a role (reference / first frame / last frame / keyframe at time t), a retention label, the features to keep, and whether to use a video's soundtrack.
- ✅ Retention labels follow the H3 guide. Visual: `fully_preserved`, `partially_preserved`, `attribute_transfer`, `weak_reference`. Audio: `fully_copy`, `partially_copy`, `reference`, `weak_reference`.
- ✅ Shots: list of shots with start time, camera and action. Shot ticks show inside the scene block on the timeline and can be dragged. They are written as `[Shot 1] A wide shot: …`, `[Shot 2] At 00:05.000, the shot cuts to …`, as in MiniMax's Ref2VA guide.
- ✅ Dialogue lines: speaker (from the Cast), time, language, delivery and text. Written as `<Subject n> (S1) whispers, <d>[English] …</d>`. Speaker IDs follow speaking order inside each clip (first voice S1, next new voice S2), as the guide asks. The language is picked from H3's 11 stable languages or typed freely.
- ✅ Camera: per-shot camera wording from presets, or a reference clip (uses a video slot).
- ✅ Prompt editor with two views:
  - **Structured**: six sections (subject definitions, summary, retention analysis, detailed description, soundscape, music). Each can be auto-filled from refs, cast, shots and dialogue.
  - The built prompt follows MiniMax's Ref2VA guide (`ref-en.txt`): the labels `subject_definitions:`, `summary:`, `retention_analysis:`, `detailed_description:`, `overall_soundscape:`, `non_diegetic_music:` each on their own line, in that order, with `N/A` for empty sections. Reference pictures that define a character, place, prop or style become `<Subject N>` lines (`<Subject 2> is the wooden pier at dusk, shown in <Picture 3>.`); standalone `<Picture N>` is kept for frame anchors. Retention lines name the shots a subject appears in (`<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - identity and appearance are retained.`).
  - Info lints point at the guide's advice: a short detailed description, an empty soundscape (N/A means silence), a reference asset without a description.
  - **Raw**.
  - In both views, refer to assets as `@P1`, `@V2`, `@A1`, to cast members as `@Mara` or `@{Old Keeper}`, and to the continuation clip as `@tail`. Each pass renumbers these into `<Picture k>`, `<Video k>`, `<Audio k>`, `<Subject n>`, in the order the native node presents references.
- ✅ Task tags are derived automatically: `reference generation`, `keyframe completion`, `video continuation`, `audio reference`, `audio reuse`, `video editing`.
- ✅ Prompt preview shows exactly what each pass will send.
- ✅ Per-scene overrides of any global setting: quality (draft or final), seed, steps, sampler, resolution, video VAE, audio VAE, diffusion model, LoRA stack (add to or replace Global, per-LoRA strength override). A hollow dot means the setting follows Global; a coral dot means it is overridden. "Reset to Global" clears them.
- ✅ Scene notes, timeline markers, lock (keep the current take even when what it continues from changes).

## 4. Prompt rewriter (LLM)

- ✅ Runs only when you press a button. Never during a queue run.
- ✅ **Rewrite**: optional instruction plus a preset. Shows a diff, and you Accept, Edit or Discard. Tags and `<d>…</d>` dialogue lines are kept exactly as written; this is checked after the rewrite.
- ✅ Written subject and shot lines replace the automatic line with the same label (no duplicates); a subject line keeps a reference to its pictures; a shot keeps its dialogue. Sections the editor writes automatically are not taken from the rewriter.
- ✅ **Split prompt**: for long scenes, gives each pass its own prompt with re-based timestamps. A rule-based split is the default; the LLM split is optional.
- ✅ **Script import**: paste a screenplay (Fountain or plain text). The LLM proposes scenes, shots, dialogue and cast. You review them before they are added, and choose where the scenes go: at the end, right after the selected scene, or in place of all current scenes (asks first; cast, assets and Global stay). Ctrl+Z undoes the import.
- ✅ **Script import in parts** (v0.4.2): a long script is cut at scene headings, table rows, Markdown headings or "Scene N" lines (paragraphs otherwise) into parts of about *Part size* characters; the premise before the first scene and table column headings go with every part, and each part sees the cast found so far. Live progress per part, Stop / Continue, retry a failed part on its own; a part cut off at the token budget is split in two automatically.
- ✅ **Scene length from shots** (v0.4.3): Import asks for each shot's duration; a scene lasts the sum of its shots (`scriptparts.fit_scene`), or is lengthened so no shot or line starts after its end. The Shots card shows each shot's length and offers Lengthen / Fit into for shots after the end; the Issues list lengthens every such scene at once.
- ✅ **Limits** (v0.4.2): stall timeout, give-up time, retries, context window (asked from the server when 0), and Import's own part size, token budget, thinking switch and guides switch. Every request streams; Rewrite and Split show progress and can be stopped.
- ✅ **Test connection**, and the model list from `/models`. The test says when the model thinks before answering.
- ✅ **Thinking models** (Qwen3 and similar): reasoning is read from `reasoning_content` / `reasoning` / `<think>` and never mistaken for the answer. Calls get at least 6000 tokens; if a reply is cut off mid-thought the error says so. *Thinking: Off* sends `chat_template_kwargs: {enable_thinking: false}` (SGLang, vLLM). Describe retries once with thinking off when the budget runs out.

## 5. Any scene length

H3 generates 124–362 frames per pass at 24 fps (5.17–15.08 s, on the 17k+5 frame grid).

- ✅ **Longer scenes** are split into several passes, each no longer than the longest-pass setting. Seams are placed on shot cuts whenever a cut falls within the snap window, so those seams are plain cuts. Otherwise the seam is mid-shot: the next pass is guided by the previous pass's tail (default 39 frames) and the merge crossfades inside the overlap.
  - Shots, dialogue and keyframes are assigned to the pass that contains them, with timestamps re-based to that pass.
  - Cast anchors are re-sent to every pass.
  - Each pass seed is the scene seed plus the pass index.
  - Each pass is saved on its own, so a failed pass re-renders alone.
- ✅ **Shorter scenes** render the shortest valid pass (124 frames) and keep a window: start, middle, end, or a custom in-point. The rest stays on disk as handles, so you can slip the window later without re-rendering.
- ✅ Durations that fall between grid points are rendered on the next grid point up and trimmed exactly.

## 6. Assets (Assets tab)

- ✅ Upload images, video and audio into `input/reelwright/<project>/`. Codes are assigned automatically: P1…, V1…, A1….
- ✅ Delete an asset (inspector button or right-click menu, with confirmation): it is removed from every scene, cast anchor, voice, outfit and the score track. The file stays on disk.
- ✅ Add files that are already in ComfyUI: a browser lists ComfyUI's input folder (imported files) and output folder (generated files), newest first, filterable by path and kind. Input files are used in place; output files are hard-linked (or copied) into `input/reelwright/<project>/from_output/`.
- ✅ Each picture or video has a description that becomes its subject line. It is stored once on the asset and every scene reads it when its prompt is built, so an edit reaches all scenes at once; the inspector lists where it is used, and each scene's References card shows it. **Describe with LLM** sends the picture (or three frames of a video) to a vision-capable model with your own question (“describe the person on the left”, “describe the couch”); the answer is offered as a suggestion to use or append.
- ✅ Each asset has defaults that any scene can override: role, retention, features to keep, soundtrack use, and a category (location, prop, style, keyframe, camera, ambience, music, voice, SFX).
- ✅ Usage list: every scene that uses an asset, with its role and retention, and whether that scene overrides the asset's defaults.
- ✅ Reference budget per scene and per pass:
  - ≤9 pictures;
  - ≤3 videos, each 2–15 s, ≤15 s in total;
  - ≤3 audio clips, each 2–15 s, ≤15 s in total;
  - ≤12 files in all.
  
  Over-budget passes get a warning, not a block. "Auto-trim" shortens an audio ref so it fits.
- ✅ Camera presets: name plus the wording that is inserted into shot lines.

## 7. Cast and continuity (Cast tab)

- ✅ Story bible: characters, locations and props.
- ✅ Character:
  - anchor set (any number of angles). Packing: *Auto* (one sheet only when the pass would not fit 9 pictures otherwise), *One sheet* (always) or *Separate* (never). A sheet uses 1 picture slot and has no size limit (ceil(√n) columns; cells take the median shape of the anchors); the Cast tab shows the sheet and the pixels each anchor gets, and the Scene tab avatar shows it when packed;
  - description, written into subject definitions, optionally drafted from the anchors with a vision LLM; when it is empty, the description of the first anchor picture that has one is used;
  - outfits, each with its own retention and features to keep;
  - voice reference (speaker IDs are numbered per clip by the prompt builder);
  - language;
  - optional identity LoRA, added automatically to every scene the character is in.
- ✅ Identity always comes from the anchors, never through a chain of rendered frames. Scene 10 gets the same identity inputs as scene 1.
- ✅ "Re-anchor after N chained scenes": continuation stops passing identity after N scenes in a chain.
- 🧪 Drift check (optional, needs the `insightface` package): after a render, face similarity against the anchors is compared with a threshold. On drift it flags the scene, or re-renders it with a new seed if you choose that. Without the package the check is shown as unavailable. A check that fails to load or run never fails the render: the take is kept and the reason is shown (Global → About, render progress).
- ✅ "Promote a rendered frame" turns a frame from a finished take into a new anchor.
- ✅ Export training set: copies the anchors and the best frames into a folder for ai-toolkit LoRA training.

## 8. Rendering (Render tab)

- ✅ Cache key per pass. It hashes:
  - model, text encoder and VAE names, plus the LoRA stack;
  - resolution, frames, steps, sampler, scheduler, shifts and seed;
  - quality (draft or final, per scene when a scene overrides it);
  - the final prompt text;
  - the content of every reference file;
  - for a continuing scene, the key and take of the scene it continues from.
  
  Only scenes with a changed key, plus the scenes chained after them, are pending.
- ✅ Resume: after a crash or restart, a run reuses everything on disk whose key still matches.
- ✅ Render scope: pending only, selected scenes, from the playhead on, everything, or a new take of one scene.
- ✅ Takes: every render is kept as a take. Star one; it is used for continuation and merge. Compare two takes side by side in the A/B view.
- ✅ Disk layout per take: `<project>_<NN>_<scene title>_<take>.mp4` (e.g. `harbor_lights_02_mara_on_the_pier_v2.mp4`), `first.png`, `last.png`, `tail.mp4`, `meta.json`, plus `passes/` for long scenes. The Render tab shows each scene's file and opens it.
- ✅ Memory policy between scenes: keep models / free cache but keep models (default) / unload everything. "Encode all prompts first" encodes every pass with the text encoder, then unloads it (about 27 GB) before sampling starts.
- ✅ Groups scenes with the same LoRA stack together when they don't depend on each other, so fewer LoRA re-patches are needed.
- ✅ Live progress on the timeline blocks (pass, step) through websocket events. The Render tab shows "Scene k of n" with a bar for the scene and one for the run; the node title shows `rendering k/n · NN%`. A small latent preview (every sampler step, at most four a second, using ComfyUI's preview method; decoded off-screen and swapped in place, so it never shows a broken image) shows next to the bars; ComfyUI no longer paints it over the node. Interrupting from ComfyUI stops the run cleanly.
- ✅ Seam inspector: last frame of scene N against first frame of scene N+1, side by side or as an onion skin.
- 🗺️ Render farm: send independent scenes to several ComfyUI instances.

## 9. Merge (Render tab)

- ✅ **Merge** button next to the scenes-and-takes table (and in the Merge card). It doesn't re-render anything; it uses the starred takes. Scenes that aren't ready can be skipped, shown as a slate, or block the merge.
- ✅ Seams: plain cut, crossfade or dip to black for hard cuts. Continuation seams trim the overlap and crossfade inside it. The Merge card sets the defaults; a scene that starts fresh can set its own transition, length and audio fade (Scene tab → Starts from → Cut into this scene).
- ✅ Audio:
  - a short fade at every seam (per-scene override for fresh starts);
  - loudness normalisation (EBU R128, target LUFS);
  - an optional score track across the whole film that ducks under dialogue.
- ✅ Colour match: per-scene RGB gain matched to a reference scene, to even out jumps between scenes.
- ✅ Output: H.264 or H.265 MP4 with a CRF setting.
- ✅ Extras:
  - `.srt` subtitles from dialogue lines;
  - a chapter per scene;
  - OpenTimelineIO `.otio` and `.fcpxml` timelines for Resolve or Premiere;
  - optional project bundle `.zip`.
- ✅ Can merge automatically after a queue run (Global → Merge).

## 9a. Files on disk (Files tab, v0.4.0)

- ✅ A tree of everything Reelwright wrote, for every project on the server (the open one first): scenes and their takes (with the starred take marked and pass videos as their own folder), merged cuts grouped by version, autosaved versions, cast training sets and the project's asset folder. Sizes add up from the bottom; each row shows its share of the level above, its file count and date.
- ✅ Flags: starred, newest cut, not in the project (deleted scenes, cast members or assets), not in the take list (stopped renders), unfinished merge leftovers, hard links (free nothing alone), intermediate pass videos, assets used or unused.
- ✅ Tick rows (a folder or take takes everything in it) and delete them, or use the bin on one row. Quick selections: unstarred takes, pass videos, older cuts, autosaves, things the project no longer lists. A confirmation shows the total and what it means for the open project.
- ✅ Deleting a take also removes it from the scene's take list (the newest remaining take becomes starred). Deleting asset files the open project uses also removes those assets from the project (undoable; the files are not).
- ✅ Preview (v0.4.1): a file's name or a row's eye shows it beside the tree: picture, video (a take or cut shows its video), audio, or text (first 200 KB).
- ✅ Safety: only `output/reelwright/<slug>` and `input/reelwright/<slug>` are reachable; every id is checked again on the server; the open project can't be deleted as a whole and its `project.json` is kept; links are removed, not their targets; the open project's rows are locked while it renders.

## 10. Editor

- ✅ Keyboard (when the node has focus):
  - Space play/pause; J/K/L back/stop/forward; I/O in/out; ←/→ step one frame;
  - S split; D duplicate; Delete remove;
  - Ctrl+Z / Ctrl+Shift+Z undo/redo; Ctrl+S save; ? opens the help.
- ✅ Undo/redo history, autosave.
- ✅ Lint panel: missing or unused tags, dialogue without a language, timestamps past the end of a scene, over-budget references, missing files, a continuation without a previous scene, cast without anchors.
- ✅ Zoom, snap to the frame grid, ripple edit. Alt + wheel zooms the timeline; Ctrl + wheel anywhere on the node zooms the ComfyUI canvas, except over a text field or list.
- ✅ Timeline navigation: the mouse wheel scrolls sideways when the film is wider than the lanes (Shift + wheel scrolls up and down). Dragging anywhere on the lanes pans and leaves the playhead alone. A click on the ruler or an empty part of a lane moves the playhead; dragging the playhead's time label scrubs. Mouse distances account for ComfyUI's canvas zoom.

## 11. MiniMax H3 facts used

- Frame grid 17k+5 at 24 fps; trained range 124–362 frames. Audio 32 kHz stereo (40 latent frames/s).
- Canvas: 768 short edge, area cap 768×1344, multiples of 32.
- References: up to 9 images, 3 videos (2–15 s), 3 audio clips. Prompt numbering follows the native node: images first, then videos (each video's soundtrack takes an `<Audio j>` number right before its `<Video k>`), then standalone audio.
- `MiniMaxH3AddGuide` anchors images, clips (17k+5 frames) and audio at any frame; negative indices count from the end.
- CFG-distilled: CFG 1.0. Native blueprint: `res_multistep` sampler, `simple` scheduler, 20 steps.
