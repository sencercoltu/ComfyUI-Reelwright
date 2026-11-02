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
| ✅ Help | Every control has a hover tooltip; every section has a **?** button with a longer explanation |
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
- ✅ Override matrix: shows which scenes override which global setting.
- ✅ Autosaved versions: list them and restore one.

## 3. Scenes (Timeline + Scene tabs)

- ✅ Unlimited scenes. Add, duplicate, delete, reorder, split at the playhead.
- ✅ Duration: drag the right edge of a scene on the timeline, or type it. Any length is allowed (see §5).
- ✅ How a scene starts:
  - **Fresh start**: hard cut, nothing carried over.
  - **Last frame**: the previous scene's final frame becomes guide frame 0 (fully preserved).
  - **Tail clip**: the previous scene's last N frames (17k+5) become a guide clip at frame 0, plus its audio. The overlap is trimmed in the final cut, so motion, light and sound continue.
- ✅ References: any asset, with a role (reference / first frame / last frame / keyframe at time t), a retention label, the features to keep, and whether to use a video's soundtrack.
- ✅ Retention labels follow the H3 guide. Visual: `fully_preserved`, `partially_preserved`, `attribute_transfer`, `weak_reference`. Audio: `fully_copy`, `partially_copy`, `reference`, `weak_reference`.
- ✅ Shots: list of shots with start time, camera and action. Shot ticks show inside the scene block on the timeline and can be dragged. They are written as `[Shot1]`, `[Shot2] At 00:05.000, cut to …`.
- ✅ Dialogue lines: speaker (from the Cast), time, language, delivery and text. Written as `<Subject n> (S1) whispers <d>[English] …</d>`.
- ✅ Camera: per-shot camera wording from presets, or a reference clip (uses a video slot).
- ✅ Prompt editor with two views:
  - **Structured**: six sections (subject definitions, summary, retention analysis, detailed description, soundscape, music). Each can be auto-filled from refs, cast, shots and dialogue.
  - **Raw**.
  - In both views, refer to assets as `@P1`, `@V2`, `@A1`, to cast members as `@Mara` or `@{Old Keeper}`, and to the continuation clip as `@tail`. Each pass renumbers these into `<Picture k>`, `<Video k>`, `<Audio k>`, `<Subject n>`, in the order the native node presents references.
- ✅ Task tags are derived automatically: `reference generation`, `keyframe completion`, `video continuation`, `audio reference`, `audio reuse`, `video editing`.
- ✅ Prompt preview shows exactly what each pass will send.
- ✅ Per-scene overrides of any global setting: seed, steps, sampler, resolution, video VAE, audio VAE, diffusion model, LoRA stack (add to or replace Global, per-LoRA strength override). A hollow dot means the setting follows Global; a coral dot means it is overridden. "Reset to Global" clears them.
- ✅ Scene notes, timeline markers, lock (keep the current take even when what it continues from changes).

## 4. Prompt rewriter (LLM)

- ✅ Runs only when you press a button. Never during a queue run.
- ✅ **Rewrite**: optional instruction plus a preset. Shows a diff, and you Accept, Edit or Discard. Tags and `<d>…</d>` dialogue lines are kept exactly as written; this is checked after the rewrite.
- ✅ **Split prompt**: for long scenes, gives each pass its own prompt with re-based timestamps. A rule-based split is the default; the LLM split is optional.
- ✅ **Script import**: paste a screenplay (Fountain or plain text). The LLM proposes scenes, shots, dialogue and cast. You review them before they are added.
- ✅ **Test connection**, and the model list from `/models`.

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
  - anchor set (any number of angles), optionally packed into one 2×2 or 3×3 sheet so it uses 1 picture slot;
  - description, written into subject definitions;
  - outfits, each with its own retention and features to keep;
  - voice reference and speaker ID (S1, S2…);
  - language;
  - optional identity LoRA, added automatically to every scene the character is in.
- ✅ Identity always comes from the anchors, never through a chain of rendered frames. Scene 10 gets the same identity inputs as scene 1.
- ✅ "Re-anchor after N chained scenes": continuation stops passing identity after N scenes in a chain.
- 🧪 Drift check (optional, needs the `insightface` package): after a render, face similarity against the anchors is compared with a threshold. On drift it flags the scene, or re-renders it with a new seed if you choose that. Without the package the check is shown as unavailable.
- ✅ "Promote a rendered frame" turns a frame from a finished take into a new anchor.
- ✅ Export training set: copies the anchors and the best frames into a folder for ai-toolkit LoRA training.

## 8. Rendering (Render tab)

- ✅ Cache key per pass. It hashes:
  - model, text encoder and VAE names, plus the LoRA stack;
  - resolution, frames, steps, sampler, scheduler, shifts and seed;
  - quality (draft or final);
  - the final prompt text;
  - the content of every reference file;
  - for a continuing scene, the key and take of the scene it continues from.
  
  Only scenes with a changed key, plus the scenes chained after them, are pending.
- ✅ Resume: after a crash or restart, a run reuses everything on disk whose key still matches.
- ✅ Render scope: pending only, selected scenes, from the playhead on, everything, or a new take of one scene.
- ✅ Takes: every render is kept as a take. Star one; it is used for continuation and merge. Compare two takes side by side in the A/B view.
- ✅ Disk layout per take: `video.mp4`, `first.png`, `last.png`, `tail.mp4`, `meta.json`, plus `passes/` for long scenes.
- ✅ Memory policy between scenes: keep models / free cache but keep models (default) / unload everything. "Encode all prompts first" encodes every pass with the text encoder, then unloads it (about 27 GB) before sampling starts.
- ✅ Groups scenes with the same LoRA stack together when they don't depend on each other, so fewer LoRA re-patches are needed.
- ✅ Live progress on the timeline blocks (pass, step) through websocket events. Interrupting from ComfyUI stops the run cleanly.
- ✅ Seam inspector: last frame of scene N against first frame of scene N+1, side by side or as an onion skin.
- 🗺️ Render farm: send independent scenes to several ComfyUI instances.

## 9. Merge (Render tab)

- ✅ **Merge scenes** button. It doesn't re-render anything; it uses the starred takes. Scenes that aren't ready can be skipped, shown as a slate, or block the merge.
- ✅ Seams: plain cut, crossfade or dip to black for hard cuts. Continuation seams trim the overlap and crossfade inside it. Each seam can be overridden.
- ✅ Audio:
  - a short fade at every seam;
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

## 10. Editor

- ✅ Keyboard (when the node has focus):
  - Space play/pause; J/K/L back/stop/forward; I/O in/out; ←/→ step one frame;
  - S split; D duplicate; Delete remove;
  - Ctrl+Z / Ctrl+Shift+Z undo/redo; Ctrl+S save; ? opens the help.
- ✅ Undo/redo history, autosave.
- ✅ Lint panel: missing or unused tags, dialogue without a language, timestamps past the end of a scene, over-budget references, missing files, a continuation without a previous scene, cast without anchors.
- ✅ Zoom, snap to the frame grid, ripple edit.

## 11. MiniMax H3 facts used

- Frame grid 17k+5 at 24 fps; trained range 124–362 frames. Audio 32 kHz stereo (40 latent frames/s).
- Canvas: 768 short edge, area cap 768×1344, multiples of 32.
- References: up to 9 images, 3 videos (2–15 s), 3 audio clips. Prompt numbering follows the native node: images first, then videos (each video's soundtrack takes an `<Audio j>` number right before its `<Video k>`), then standalone audio.
- `MiniMaxH3AddGuide` anchors images, clips (17k+5 frames) and audio at any frame; negative indices count from the end.
- CFG-distilled: CFG 1.0. Native blueprint: `res_multistep` sampler, `simple` scheduler, 20 steps.
