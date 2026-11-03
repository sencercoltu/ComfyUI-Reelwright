# Reelwright

A timeline editor node for **MiniMax H3 ref2va** in ComfyUI. Plan a film as
scenes of any length, render them one by one to files on disk, and merge them
into one video. Only what you changed gets rendered again.

- **Unlimited scenes, any length.** H3 makes 5.17–15.08 s per generation.
  Longer scenes are split into passes, with seams placed on your shot cuts or
  covered by guided overlaps. Shorter scenes render the shortest pass and keep
  the window you choose.
- **Continuity.** A scene can start fresh, start from the last frame of the
  previous scene, or continue from its tail clip. A tail clip carries motion,
  light and sound across the cut.
- **Same character everywhere.** Cast members have anchor pictures, outfits, a
  voice and an optional identity LoRA. The same anchors are sent to every
  scene, so scene 10 matches scene 1. An optional face check flags drift.
- **Global settings with per-scene overrides** (models, VAEs, LoRA stack, seed,
  steps, size). Hollow dot = follows Global; coral dot = overridden.
- **Incremental rendering.** Each scene has a cache key built from everything
  that affects its pixels. Edit scene 2 and only scene 2, plus the scenes that
  continue from it, render again. Resume after a crash. Keep several takes per
  scene and star one.
- **Memory friendly.** Every scene is written to MP4 and its frames are freed
  before the next one starts. Prompts can be encoded up front so the 27 GB text
  encoder is unloaded before sampling.
- **Cut to a song.** Lay one or more audio files on the timeline, move and trim
  them there. Each pass of each scene gets exactly the part of the song it
  covers as an H3 audio reference, so lips and movement follow it, and the
  merge plays the song unchanged, with the scenes' own sound under it or off.
- **Merge scenes.** One click, no re-render. Cuts, crossfades or dips to black;
  loudness normalisation; soundtrack tracks (a looping score that ducks too); colour
  match; subtitles (.srt), chapters, and OpenTimelineIO / FCPXML timelines for
  Resolve or Premiere.
- **Prompt tools.** A structured six-section editor with `@P1` / `@Mara` tags
  that are renumbered per pass, a live preview of the exact prompt for each
  pass, and an optional OpenAI-compatible LLM for rewrite, pass splitting and
  script import. The LLM runs only when you click.
- **Help everywhere.** Hover any control for a tooltip; press **?** on any
  section for the longer explanation.

## Install

```
cd ComfyUI/custom_nodes
git clone https://github.com/sencercoltu/ComfyUI-Reelwright
```

Restart ComfyUI. The node is under **video → Reelwright**.

Reelwright is not published to the ComfyUI Registry, so ComfyUI Manager's node
list doesn't show it, even when Manager's "Install via Git URL" installed it.
It still loads normally. Update it with `git pull` in its folder and restart
ComfyUI.

Requirements:

- A ComfyUI build with the native MiniMax H3 nodes (`comfy_extras/nodes_minimax_h3.py`).
- **ffmpeg** on `PATH`. It stitches long scenes and does the merge. Single-pass scenes render without it.
- Optional: `pip install insightface onnxruntime` for the face drift check.

Models (standard ComfyUI folders):

| What | File | Folder |
|---|---|---|
| Diffusion (ref2va) | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `models/diffusion_models` |
| Text encoder | `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` | `models/text_encoders` |
| Video VAE | `minimax_h3_video_vae_int8_convrot.safetensors` | `models/vae` |
| Audio VAE | `minimax_h3_audio_vae_fp32.safetensors` | `models/vae` |
| Latent upscaler (optional) | `minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors` | `models/latent_upscale_models` |

You can also wire your own `model`, `clip`, `vae` and `audio_vae` into the
node. A wired input replaces the matching Global-tab loader.

## Using it

1. **Global tab:** pick the models, the output size and your LoRAs. Save them
   as a **profile** to reuse them; the profile marked *Use for new nodes* fills
   in every new Reelwright node.
2. **Assets tab:** drop in pictures, video and audio. Each asset gets a code
   (P1, V1, A1…) and default settings: role, retention and the features to keep.
   **From ComfyUI** adds files already in ComfyUI's input or output folder, and
   **Describe** asks a vision LLM to write an asset's description.
3. **Cast tab:** create your characters, give each anchor pictures, a
   description and a voice.
4. **Timeline:**
   - add scenes and drag their right edge to set the length;
   - drag shot ticks inside a block to move cuts;
   - click the round chip between two scenes to choose how the second one
     starts (fresh, last frame or tail clip).
5. **Scene tab:** add shots, dialogue and references, and write the prompt.
   Refer to assets as `@P1` and to cast members as `@Mara` (or `@{Old Keeper}`).
   The preview shows the exact prompt for each pass.
6. **Render pending.** Only new or changed scenes render. Watch progress on the
   timeline blocks, the Render tab ("Scene 2 of 5") and the node title. A scene
   can render as Draft or Final on its own (Scene tab → Generation → Quality).
7. **Merge scenes.** The cut, plus any side files you enabled, is written to
   `output/reelwright/<project>/cuts/`. Transitions default to the Merge card;
   a scene that starts fresh can choose its own cut, crossfade or dip.

Everything is stored in the workflow. The project is also autosaved, with
versions, under `output/reelwright/<project>/`.

The **Files** tab shows what every project takes on disk (takes, pass videos,
cuts, autosaves, assets) as a tree, and deletes what you tick.

### How continuation works

H3 places guide frames at any frame of a generation (`MiniMaxH3AddGuide`).

- **Tail clip:** the previous scene's last 39 frames and their audio are fixed
  at frame 0 of the new scene. The new scene continues the motion, and the merge
  crossfades inside that overlap.
- **Last frame:** the previous scene's final frame becomes frame 0.
- Identity always comes from the cast anchors, not from a chain of rendered
  frames. After a set number of chained scenes, a tail continuation falls back
  to last frame only (the re-anchor rule).

### Long and short scenes

The planner works on the H3 grid (17k+5 frames, 24 fps, 124–362 frames per
pass). A seam goes on one of your shot cuts when one is close enough, or when
cutting there doesn't add a pass. Otherwise the next pass starts from the
previous pass's tail and the two are crossfaded. Shots, dialogue and keyframes
go to the pass they fall in, with their timestamps re-based to that pass.

### Prompt rewriter

In **Global → Prompt rewriter**, set an OpenAI-compatible base URL (OpenAI,
LM Studio, vLLM, SGLang, Ollama's `/v1`…) and a model. The API key is stored in
`user/reelwright/llm.json`, never in the workflow. The rewriter never
runs during a queue run. It keeps every `@tag` and `<d>…</d>` dialogue line, and
warns you if the model changed one.

Press **Download** next to *H3 guides* to fetch MiniMax's official H3 prompt
guides (the Ref2VA guide and the base guide) from the MiniMax-H3 GitHub
repository into `user/reelwright/guides/`. They are sent to the LLM with every
rewrite, split and script import (about 10,000 tokens; turn it off for small
local models). They are not bundled because of their licence; until you
download them a short built-in summary is sent instead.

## Keyboard (when the node has focus)

| Key | Action |
|---|---|
| Space | play / pause |
| J / K / L | back 1 s / stop / play |
| ← / → | one frame (Shift: 1 s) |
| I / O | loop in / out |
| S | split at playhead |
| D | duplicate |
| N | new scene |
| M | marker |
| Delete | remove scene (asks first) |
| Ctrl+Z / Ctrl+Shift+Z | undo / redo |
| ? | help |
| Wheel / Shift + wheel | scroll the timeline sideways / up and down |
| Drag on the timeline | pan (the playhead stays) |
| Click on the ruler or an empty lane | move the playhead |
| Drag the playhead's time label | scrub |
| Alt + wheel | zoom the timeline |
| Ctrl + wheel | zoom the ComfyUI canvas (not over text fields) |

Right-click a scene or an asset for its menu (open, render, duplicate, draft/final,
delete…).

## Development

```
python -m pytest -c tests/pytest.ini tests     # core, planner, prompts, cache, ffmpeg merge
python web-test/shoot.py                        # editor screenshots against a mock backend
```

`docs/SPEC.md` lists every feature. `docs/ARCHITECTURE.md` describes the project
JSON, the HTTP routes and the disk layout.

## License

MIT. MiniMax H3 weights have their own license. Check it before commercial
use.
