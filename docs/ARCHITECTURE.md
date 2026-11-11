# Reelwright — architecture and contracts

```
ComfyUI-Reelwright/
  __init__.py            ComfyUI entry: comfy_entrypoint() + WEB_DIRECTORY + routes
  reelwright/
    __init__.py          VERSION
    spec.py              H3 constants and frame/canvas math (pure)
    model.py             project defaults, normalisation, effective settings, timing, seeds, budgets (pure)
    planner.py           scene -> passes (long/short), seams, re-based shots (pure)
    prompt.py            per-pass prompt assembly and tag numbering (pure)
    validate.py          lint rules (pure)
    soundtrack.py        soundtrack tracks: resolve them, the part each pass gets (pure)
    analysis.py          plan, prompts, keys and status of every scene; /plan's answer (pure + file hashing); v0.8.0: long-scene settings, drift meter
    cache.py             cache keys, pass cache keys, staleness (pure + file hashing)
    storage.py           folders, path containment, take lists, autosave/versions, cut numbers (pure + fs)
    jobs.py              v0.6.0: per-project locks and running jobs (render, merge) (pure)
    files.py             Files tab: disk-use tree and deleting (pure + fs)
    media.py             load images/video/audio to tensors, write files (comfy); v0.8.0: lossless pass files, exact reads (PyAV)
    render.py            render run using the native H3 nodes (comfy + torch); v0.8.0: guide VAE, latent hand-off, drift
    assemble.py          the cut plan and merge_project: takes -> merge.join (ffmpeg); v0.7.0: scene.merge, per-scene colour match
    merge.py             ffmpeg merge, srt/chapters/otio/fcpxml/color match, loudness (ffmpeg); v0.7.0: transitions, fades, filmstrips
    beats.py             v0.6.0: tempo, beats and bar starts of an audio file (numpy + ffmpeg)
    llm.py               OpenAI-compatible client and prompt templates (aiohttp); v0.8.0: Write prompts (write_passes)
    scriptparts.py       cuts a long script into parts for the import (v0.4.2); imported scene length vs shots (v0.4.3) (pure)
    continuity.py        optional face-match drift check (insightface)
    detect.py            v0.20.0: the crop window's Find (insightface faces, Grounding DINO things) and crop
    routes.py            /reelwright/* HTTP routes
    profiles.py          saved Global settings in user/reelwright/profiles.json
    node.py              the V3 node
  web/
    reelwright.js        ComfyUI extension: registers the DOM widget
    rw/*.js, rw/tabs/*.js, rw/reelwright.css
    rw/cut.js            v0.7.0: scene.merge helpers shared by the Scene tab's In the cut card and the timeline
    rw/passes.js         v0.8.0: pass layout, pass texts, shot/line rows, camera options, the Write prompts runner
  tests/                 pytest for the pure modules, merge, routes and the JS model (test_model_parity.py)
  web-test/              mock backend (mock.js), interaction checks (interact.py), screenshots (shoot.py)
```

The pure modules import nothing from ComfyUI or torch, so they can be tested
outside ComfyUI.

## Project JSON (schema 1)

The node's hidden `project` widget holds the project as JSON. The editor owns
this state. Anything that comes from rendering (takes, stars, face scores)
lives on disk.

```jsonc
{
  "schema": 1,
  "id": "p_8f3a…",                       // stable id
  "project_id": "p_8f3a…",               // v0.6.0: who owns the folder (see "Project identity"); older projects use their `id`
  "name": "Harbor Lights",
  "slug": "harbor_lights",               // folder name; [a-z0-9_-], derived from name if empty
  "global": {
    "models": {
      "diffusion": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
      "weight_dtype": "default",         // default | fp8_e4m3fn | fp8_e4m3fn_fast | fp8_e5m2
      "text_encoder": "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
      "clip_device": "default",          // default | cpu
      "video_vae": "minimax_h3_video_vae_int8_convrot.safetensors",
      "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
      "latent_upscaler": ""
    },
    "loras": [ { "id": "l_1", "name": "film_grain_v2.safetensors", "strength": 0.6, "enabled": true,
                 "trigger": "" } ],                   // v0.21.0: trigger word(s), "" for none (every LoRA has one)
    "output": { "aspect": "16:9", "width": 1344, "height": 768, "ref_image_size": "match" },
    "sampling": { "steps": 20, "sampler": "res_multistep", "scheduler": "simple",
                  "seed": 104729, "seed_mode": "increment",          // fixed | increment | random
                  "sigma_shift": false, "shift_video": 12.0, "shift_audio": 3.0 },
    "quality": "final",                                              // final | draft
    "draft": { "scale": 0.5, "steps": 8, "lora": "", "lora_strength": 1.0, "lora_trigger": "" },
    "defaults": { "duration": 8.0, "start_mode": "last_frame", "overlap_frames": 39, "language": "English" },
    "long": { "max_pass_frames": 362, "overlap_frames": 39, "crossfade_frames": 12,
              "seam_mode": "auto", "cut_snap_seconds": 2.0,        // auto | cuts | overlap
              "guide_vae": "",                 // v0.8.0: VAE file that does every encode; "" = the video VAE
              "carry_audio": true,              // v0.8.0: anchor the pass before's sound at overlap seams
              "seam_video_ref": true,           // v0.8.0: the end of the pass before as <Video 1> at overlap seams
              "handoff": "pixels",             // v0.8.0: pixels | latent (experimental)
              "pass_cache": "near_lossless" },  // v0.8.0: near_lossless (H.264 CRF 4) | lossless (RGB qp 0 + FLAC)
    "memory": { "policy": "free_cache", "encode_first": true, "group_by_lora": true },  // keep | free_cache | unload_all
    "continuity": { "reanchor_after": 2, "face_check": false, "face_threshold": 0.8, "on_drift": "flag", // flag | retake
                    "name_continuation": true,    // v0.7.0: send the frame / clip a pass continues from as <Picture 1> / <Video 1>
                    "describe_voices": true },    // v0.10.0: write each character's voice_desc at their first line in every pass
    "llm": { "base_url": "", "model": "", "temperature": 0.4, "max_tokens": 2048, "preset": "h3_ref2va",
             "include_guides": true,                      // v0.2.0: send MiniMax's guides when downloaded
             "thinking": "auto",                          // v0.3.2: auto | off (chat_template_kwargs enable_thinking=false)
             "timeout_s": 120, "max_wait_s": 900,         // v0.4.2: stall timeout (no data), longest request
             "retries": 2, "context_tokens": 0,           // v0.4.2: extra attempts; context window, 0 = ask GET /models
             "import_part_chars": 3000,                   // v0.4.2: script import part size, 0 = whole script
             "import_max_tokens": 24576, "import_thinking": "same", "import_guides": false },  // same | off; v0.8.0: 24576 (was 16384)
    "merge": { "use": "starred", "missing": "skip",                 // skip | slate | block
               "hard_cut": "cut", "transition_frames": 12,           // cut | crossfade | dip; v0.7.0: deprecated, see scene.merge
               "audio_fade_frames": 6, "loudness": -16.0, "normalize": true,   // audio_fade_frames: v0.7.0 deprecated
               "score": { "asset": "", "volume_db": -12.0, "duck": true },  // v0.5.0: moved to "soundtrack" on load
               "scene_audio": { "mix": false, "volume_db": -12.0 },          // v0.5.0: the scenes' sound under the soundtrack
               "color_match": false, "color_ref_scene": "",          // v0.7.0: deprecated (read only by the scene.merge migration)
               "codec": "h264", "crf": 16,
               "subtitles": true, "chapters": true, "otio": true, "fcpxml": true, "bundle": false,
               "subtitle_timing": "speech",                           // v0.10.0: speech (follow the speech in each take) | planned
               "auto_after_render": true }
  },
  "assets": [
    { "id": "a_1", "code": "P1", "kind": "image",             // image | video | audio
      "name": "Mara — portrait", "file": "reelwright/harbor_lights/mara.png",   // relative to ComfyUI input dir
      "duration": 0, "width": 1024, "height": 1365, "category": "subject",
      "defaults": { "role": "reference", "retention": "fully_preserved", "keep": ["face", "hair"], "soundtrack": false },
      "notes": "",
      "description": "",                                   // v0.2.0: the asset's subject line; read live by every scene,
                                                           //   and by a cast member without its own description (v0.3.4)
      "group": "g_1",                                      // v0.9.0: an asset_groups id or "" (no group)
      "tags": ["identity", "face"],                        // v0.9.0: cleaned by asset_tags (one space, ≤ 60 chars, no repeats)
      "crop_of": { "asset": "a_0", "box": [0.1, 0.05, 0.4, 0.9] } }   // v0.20.0, optional: cut from that picture, box [x, y, w, h]
                                                           //   as parts of it (0..1, EXIF rotation applied); only for Adjust crop
  ],
  "asset_groups": [                                        // v0.9.0: Assets tab only (never in a prompt, plan or cache key)
    { "id": "g_1", "name": "Mara", "description": "Every picture of Mara and her voice." }
  ],
  "cast": [
    { "id": "c_1", "kind": "character",                 // character | location | prop
      "name": "Mara", "speaker": "S1", "description": "Woman, early 30s, …",   // speaker is legacy: S-IDs are per clip since v0.2.0
      "anchors": ["a_1"], "pack_sheet": true,  // true (one sheet), false (separate) or "auto" (v0.4.1: a sheet only when the pass would not fit 9 pictures)
      "outfits": [ { "id": "o_1", "name": "Navy pea coat", "retention": "fully_preserved", "keep": ["face","hair","coat"], "assets": [] } ],
      "default_outfit": "o_1",
      "voice": "a_7", "language": "English",
      "voice_desc": "a deep, warm male voice, slow and measured",  // v0.10.0: written at the first line in every pass ("" = nothing)
      "lora": { "name": "", "strength": 0.8, "trigger": "" } }   // v0.21.0: the identity LoRA's trigger word
  ],
  "camera_presets": [ { "id": "k_1", "name": "Push In", "text": "the camera pushes in" } ],  // v0.8.0: H3's 20 moves (DEFAULT_CAMERA)
  "camera_version": 2,                    // v0.8.0: below 2, the official moves the presets lack are appended once
  "scenes": [
    { "id": "s_1", "title": "Harbor at dusk", "duration": 8.0,   // 1/24 .. 600 s
      "seed_n": 0,                                        // v0.6.0: the scene's seed number ("+1 per scene" mode), see "Seeds"
      "color": "",                                        // optional tint for the timeline block
      "start": { "mode": "fresh", "overlap_frames": 39 },  // fresh | last_frame | tail
      "transition": { "mode": "", "frames": null,          // fresh starts only: "" (merge default) | cut | crossfade | dip
                      "audio_fade_frames": null },         //   null = use Global → Merge. v0.7.0: deprecated, read only by the migration
      "merge": {                                           // v0.7.0: how the scene sits in the cut (see "Merge: scene.merge")
        "transition": "cut",       // cut | crossfade | dip | wipe | slide | circle | dissolve | pixelize | radial | zoom (fresh starts)
        "direction": "left",       // left | right | up | down (wipe, slide)
        "frames": 12,              // transition length; frame counts are whole frames 0 .. 14400
        "color": "#000000",        // dip colour, "#rrggbb" (anything else → "#000000")
        "audio_frames": 6,         // the sound's fade out / in at a plain cut into this scene
        "fade_in": { "frames": 0, "color": "#000000" },   // picture fades in from the colour at the first frame
        "fade_out": { "frames": 0, "color": "#000000" },  // picture fades out to the colour at the last frame
        "audio_fade_in": 0, "audio_fade_out": 0,          // the scene's own sound, frames
        "volume_db": 0.0, "mute": false,                  // the scene's own sound; -60 .. 24 dB
        "color_match": "off",      // off | previous | scene
        "color_ref": "",           // scene id when color_match is "scene"
        "brightness": 0.0, "contrast": 1.0, "saturation": 1.0 },  // ffmpeg eq: -1 .. 1, 0 .. 2, 0 .. 3
      "trim": { "keep": "start", "in": 0.0 },             // short scenes: start | middle | end | custom
      "refs": [ { "id": "r_1", "asset": "a_2", "role": "reference",   // reference | first_frame | last_frame | keyframe
                  "time": 0.0, "retention": "weak_reference", "keep": [], "soundtrack": false } ],
      "cast": [ { "id": "c_1", "outfit": "o_1" } ],
      "shots": [ { "id": "h_1", "t": 0.0, "camera": "the camera pushes in", "text": "The harbor at dusk…",
                   "camera_amp": "small",       // v0.8.0: "" | small | large ("" = not said)
                   "camera_speed": "slow",      // v0.8.0: "" | slow | fast
                   "framing": "wide" } ],       // v0.8.0: "" | one of model.FRAMINGS (extreme wide … dutch angle)
      "dialogue": [ { "id": "d_1", "speaker": "c_1", "t": 3.5, "language": "English", "delivery": "calls out", "text": "Is anyone still out there?",
                      "duration": null } ],   // v0.8.0: seconds > 0 (≤ 600), null = estimated (dialogue_seconds)
      "prompt": { "mode": "structured",                   // structured | raw
                  "auto": { "subjects": true, "retention": true, "shots": true },
                  "sections": { "subject_definitions": "", "summary": "", "retention_analysis": "",
                                "detailed_description": "", "overall_soundscape": "", "non_diegetic_music": "" },
                  "raw": "",
                  "pass_prompts": {},                      // long scenes: {"1": "...", "2": "..."} overrides per pass
                  "passes": [ { "start": 0.0, "end": 14.375,  // v0.8.0: each pass's own sections, index = pass - 1;
                                "sections": { … the six … } } ] },  //   start/end = its range (scene s) when written
      "overrides": {},                                     // any of: quality (draft|final), seed, steps, sampler, scheduler, width, height,
                                                           //   diffusion, video_vae, audio_vae, text_encoder,
                                                           //   loras: { "mode": "add"|"replace", "items": [ {id,name,strength,enabled} ],
                                                           //            "strengths": { "<global lora id>": 0.35 } }
      "lock": false, "notes": "" }
  ],
  "soundtrack": [                                         // v0.5.0: audio laid on the cut (soundtrack.py)
    { "id": "t_1", "asset": "a_9",
      "start": 0.0,                                        // film (cut) seconds, may be negative
      "in": 0.0, "out": 0.0,                               // file seconds; out 0 = end of the file
      "volume_db": 0.0, "fade_in": 0.0, "fade_out": 0.0,  // merge and monitor only
      "mute": false, "loop": false, "duck": false,
      "mix": true,                                         // play unchanged in the merge
      "sync": true, "marker": "fully_copy" } ],            // send each pass the part it covers
  "markers": [ { "id": "m_1", "t": 12.0, "text": "music swell", "color": "amber" } ],
  "ui": { "tab": "timeline", "selected": "s_1", "zoom": 22, "playhead": 0.0, "snap": true, "ripple": true,
          "beats": true, "beatSnap": false, "autoRoll": true, // v0.6.0, set by the toolbar; missing = these defaults
          // v0.9.0, layout and monitor (kept as they are; the editor clamps them; missing = the defaults):
          "tl_top": 340, "tl_mon": 0.42, "files_prev": 380, "shots_h": 380, "lines_h": 300,
          "captions": true, "mon_volume": 1, "mon_muted": false,
          "collapsed": { "shots": true } }                  // v0.10.0: folded Scene-tab cards (shots | dialogue | h3)
}
```

Ids are short random strings with a type prefix. Missing keys are filled in by
`model.normalize_project()`, which runs in both Python and JS (`rw/model.js`
mirrors the defaults).

`ui` is view state: it is saved with the project but is not part of undo (v0.6.0).
`ui.autoRoll` only matters while a soundtrack track is in the cut or sent to H3.

### Normalisation (v0.6.0)

`normalize_project` (Python) and `normalizeProject` (JS) never raise and give the
same result. `tests/test_model_parity.py` runs `web/rw/model.js` under node on
fixtures, malformed ones and a fixed-seed fuzz, and compares the output, the
timing, overlaps, visible starts, frame counts, seeds, slugs and budgets.

- A non-object, or `scenes` that is not a list, gives the default project. So does JSON text that doesn't parse, including NaN or Infinity (as `JSON.parse` refuses them).
- Global is coerced key by key to the default's type: numbers may be given as text (`"12.5"`), bools come from bools or numbers, strings from strings or numbers. Unknown keys are kept.
- List items that are not objects are dropped. A cast entry given as a string becomes `{id, outfit: ""}`; a `start` given as a string becomes `{mode}`; a `prompt` given as a string becomes a raw prompt.
- Durations are clamped to 1/24 .. 600 s. Shots and dialogue are sorted by `t`. Frame counts use banker's rounding in both languages.
- Duplicate ids get `_2`, `_3`…: scene ids project-wide, ref, shot and line ids per scene, track ids per project. Duplicate asset codes (compared without case, across kinds) get the next free code.
- Slugs: a valid slug is kept as typed; otherwise `slugify(slug or name)`: NFKD transliteration ("Ömer" → "omer"), at most 64 characters, `untitled` when no Latin letter is left.
- `project_id`: Python keeps a string or uses `""` (it never invents one, so normalising twice agrees). JS keeps a non-empty string or creates one; the store first copies a pre-0.6 project's stable `id` into it.
- A pre-0.5 `merge.score` becomes a soundtrack track in both (`migrate_score` / `migrateScore`), also when a Global profile is applied.
- `scene.merge` (v0.7.0, `_norm_merge` / `normMerge`, run on every scene after the seed repair). A scene whose `merge` is missing or not an object gets one built from its v0.6.1 settings (`_migrated_merge` / `migratedMerge`), so it merges as before:
  - `transition` = `scene.transition.mode`, else `global.merge.hard_cut` (a value other than cut / crossfade / dip is `cut`, as v0.6.1 treated it);
  - `frames` = `scene.transition.frames` ?? `global.merge.transition_frames`; `audio_frames` = `scene.transition.audio_fade_frames` ?? `global.merge.audio_fade_frames`;
  - when `global.merge.color_match` is `true`: the reference is `color_ref_scene` if it names a scene of the project, else the first scene; every other scene gets `color_match: "scene"`, `color_ref: <reference>`.

  Then every field is coerced: an unknown transition is `cut`, direction `left`, colour match `off`; frame counts are whole numbers 0 .. 14400 (fractions cut off); colours `#rrggbb` in lower case, else `#000000`; `volume_db` −60 .. 24, `brightness` −1 .. 1, `contrast` 0 .. 2, `saturation` 0 .. 3; missing fields take `default_merge()`. It is idempotent, and applying a Global profile does not migrate again (the scenes already have `merge`). `scene.transition` and the Global keys stay in the JSON; nothing else reads them. A scene inserted without `merge` gets one at the next normalise, so the UI reads it through `cut.js mergeOf()`.
- `global.continuity.name_continuation` (v0.7.0) is a bool like the other Global keys; missing is `true`.
- v0.8.0 (`normalize_global`, `_norm_scene` and `normalize_project`; JS the same; `tests/test_model_parity.py` adds `v080_fixtures()` and malformed `global.long` fixtures):
  - `global.long`: the five new keys follow the usual rules (strings from strings or numbers, bools from bools or numbers); an unknown `handoff` is `"pixels"`, an unknown `pass_cache` `"near_lossless"`. Missing keys take the defaults, which keep v0.7.0's behaviour.
  - shot `camera_amp`, `camera_speed`, `framing`: only the exact values (`CAMERA_AMPS`, `CAMERA_SPEEDS`, `FRAMINGS`) are kept, anything else is `""`.
  - dialogue `duration`: a number > 0, at most 600 (`DIALOGUE_MAX_SECONDS`), else `null`.
  - `prompt.passes` (`_norm_pass_text` / `normPassText`): a non-list is `[]`; an item that is not an object becomes `{start: 0, end: 0, sections: <six empty strings>}`, so later indexes never shift; `start` / `end` are floats, every section a string; extra keys are kept.
  - `camera_version` (`_migrate_camera` / `migrateCamera`): below 2, missing or junk, the `DEFAULT_CAMERA` moves whose name the presets lack (compared without case and outer spaces) are appended once and it becomes 2; user presets stay first and unchanged. 2 or more is kept (a whole number, at most 1e6), so presets deleted later stay deleted.

### Seeds (v0.6.0)

In "+1 per scene" mode a scene's seed is Global seed + `seed_n`, so adding,
removing or moving scenes changes no other scene's seed. A new scene gets
`next_seed_n(p)` (1 + the highest, 0 for the first); split, duplicate, paste
and script import do the same (JS `nextSeedN`, `actions.insertScenes`).
Normalisation keeps a valid `seed_n` (a whole number 0 .. 2³¹−1) unless an
earlier scene has it; a scene without one gets its list index, which is the
seed it had before v0.6.0, or the next free number when that is taken. Each
pass adds its pass index; a take adds `offset × 1000003` (see Takes).

### Timing: effective start, overlap, visible start (v0.6.0)

One rule, in `model.py` and `model.js`, used by the planner, prompts, cache keys,
the merge's trimming and the timeline:

- `effective_start(p, i)` → `"fresh" | "last_frame" | "tail"`. Scene 0 is fresh. A `tail` start whose continuation depth is above `global.continuity.reanchor_after` is re-anchored: it is guided by the last frame only, so it is planned, trimmed and timed as `last_frame`.
- `tail_overlap_frames(p, i)` = `min(align_down(max(5, overlap_frames)), 124, align_down(own frames), align_down(previous scene's frames))`, 0 unless the effective start is `tail`. When fewer than 5 frames are left, the start is `last_frame`. 124 is the length of `tail.mp4`.
- `scene_overlap_at(p, i)` (seconds): tail frames / 24, 1/24 for `last_frame`, 0 for fresh. The old `scene_overlap(scene, index)` / `overlapSeconds(scene)` stay, deprecated and unchanged.
- `scene_starts(p)` → `(starts, total)`: a scene starts `scene_overlap_at` seconds before the scene before ends. `visible_start(p, sid)` = start + overlap, where the scene first shows new content. The scene on screen at film time t (JS `sceneAt`) is the one whose `[visibleStart, start + duration)` holds t.
- The planner's `plan_scene` reports the effective `start_mode` and the scene's own `declared_start_mode`; pass 1's `overlap_frames` is `tail_overlap_frames`. Dialogue, shots and keyframes before 0 s or in the last half frame are clamped into the scene.
- JS memo: `sceneStarts`, `planScene`, `playingTracks`, `resolvedTracks` and `sceneHasSong` are cached per `project.__rwv` (a non-enumerable number the store bumps on every update and load). Without `__rwv` they are computed fresh. Callers must not mutate the cached results.

### Reference budget (v0.6.0)

`model.scene_media_counts(p, scene, pass_=None, starts=None)` and JS
`sceneBudget(project, scene, pass)` count the same way: anchors and outfit
pictures (a packed sheet counts 1) and reference pictures; a video ref with
`soundtrack: true` uses one audio slot and its seconds; a voice only in passes
where that character speaks (and not when the pass gets the song); the song only
where `pass_soundtrack` gives the pass a part of it. Without a pass, each count is
the most any one pass uses. `validate.py` adds the guide pictures and clips the
text names.

v0.7.0: `scene_media_counts(p, scene, pass_=None, starts=None, mode=None, continuation=True)`
and `sceneBudget(project, scene, pass = null, continuation = true)` also count the
continuation reference (`pass_continuation`, see "Continuation as a named
reference"): one picture, or one video with `continuation_frames / 24` seconds plus
an audio slot for its sound when fewer than 3 are used. They return a key
`continuation`: `"picture" | "video" | "video_audio" | ""` (without a pass: the first
pass that has one). A continuation picture counts for *Auto* packing (JS
`sceneAutoPacks` too). When the pass still has more than 9 pictures or 12 files
(picture), or 3 videos or 12 files (clip), the continuation is left out and the pass
counts as in v0.6.1, matching what `build_pass` sends. `mode` is the scene's
effective start when the caller has it; `continuation=False` counts as v0.6.1.
v0.8.0: with `global.long.seam_video_ref` off, a pass after an overlap seam has no
continuation (`pass_continuation` returns `""`), so it counts as in v0.6.1.

### Tag syntax (v0.6.0)

A tag is `@` + a name: runs of Unicode letters, digits, combining marks and `_`,
joined by single `'`, `’`, `-` or `.` (a trailing one is not part of the name:
"@Anna." is `Anna`). `@{Two Words}` names a cast member with spaces. An `@` right
after a letter, digit, `_` or `@` starts no tag, so e-mail addresses are text.
`@@` is a literal `@`.

- Python (`prompt.tag_re()`, built on first use): `(?<![\w<marks>@])@(?:\{([^}\n]+)\}|(?!@)(<name>))`, where `<marks>` lists every combining mark (Python's `\w` has none).
- JS (`prompttext.js TAG_SOURCE`, flags `gu`): `(?<![\p{L}\p{N}\p{M}_@])@(?!@)(?:\{([^}\n]+)\}|([\p{L}\p{N}\p{M}_]+(?:['’.\-][\p{L}\p{N}\p{M}_]+)*))`.
- Names compare without case and with `’` read as `'`. `@X's` that does not resolve but `@X` does is `@X` + `'s`. The canonical token is `@Name` when the whole name matches the name rule, else `@{Name}` (`prompt.tag_token`, `model.js tagCandidates`).
- Resolution per pass: an asset sent with this pass → its label; an asset of the scene that guides another pass → its words (info); an asset code not attached to the scene, or an unknown name like `P3`/`V1`/`A2` → error; `@tail` → "the end of the previous shot" (warn when the scene starts fresh; v0.7.0: in a pass that names the continuation, its label `<Picture 1>` / `<Video 1>`, and `tag_map["@tail"]` is set so Rewrite turns the label back into `@tail`); `@soundtrack` / `@song` → `<Audio n>`, or "the soundtrack" when the pass gets no song (info; warn when no track is sent to H3); a cast member in the pass → `<Subject n>`; a cast member not in the scene → the name (warn); anything else → left as typed (warn).

### LoRA trigger words (v0.21.0)

Every LoRA has a `trigger` (`global.loras[]`, `overrides.loras.items[]`, `cast[].lora`; the draft LoRA's is
`global.draft.lora_trigger`): one line, single spaces, ≤ 120 characters (`model.trigger_text`, `model.js triggerText`).
`model.lora_triggers(p, scene)` lists `{trigger, cast}` for the LoRAs the scene actually loads (`_lora_entries`, the
same rules as `effective_loras`: Replace Global, enabled, the draft LoRA only in a draft; a later entry for the same
file takes over a non-empty trigger), each word once. `prompt.build_pass` writes the ones the pass's prompt lacks
(`has_word`: any case, whole words): an identity LoRA's after its character's name in the automatic subject line
("<Subject 1> is Birten (ohwx man), …") when the character is a subject of the pass; the others, and an identity word
the subject line does not carry (own subject definitions, raw prompts), at the start of the summary right after the
task tags (`place_trigger_words`; a raw prompt without sections: after its leading tags). No trigger set: the prompt,
and so every cache key, is unchanged.

## HTTP routes (all JSON unless noted)

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/reelwright/info` | – | `{version, ffmpeg, insightface, insightface_error, h3_nodes, h3_error}`; `insightface_error` (v0.4.1) is why face checks could not load or run, `""` otherwise; v0.6.0: `h3_nodes` is whether `render.py` could import the H3 nodes (`render.h3_available()`), `h3_error` why not |
| GET | `/reelwright/models` | – | `{diffusion_models[], text_encoders[], vae[], loras[], latent_upscale_models[], samplers[], schedulers[]}` |
| POST | `/reelwright/plan` | `{project}` | `{scenes: {<scene_id>: {passes[], status, key, starred, match, kind, takes[], issues[], prompts[], tags[], tag_maps[], settings, loras[], upstream_take, upstream_changed, manual_star, estimate_seconds, starred_prompts, cached_passes}}, issues[], timeline: {starts:{id:t}, total}, estimate: {seconds, scenes, unknown}}`; the v0.6.0 fields are under "Plan fields"; v0.8.0: `takes[]` carry `drift` and `long` (see Takes) |
| POST | `/reelwright/upload` | multipart: one `file` part and `slug`, any order | `{asset}` with kind, file, duration, width, height. v0.6.0: streamed in 1 MB chunks to `input/reelwright/.uploads/` off the event loop, checked to decode (PIL for pictures, ffprobe for a video's picture or an audio's sound), then moved into `input/reelwright/<slug>/`; 400 for an unreadable or empty file or several file parts |
| GET | `/reelwright/takes?slug=` | – | `{scenes: {<id>: {starred, auto_star?, project_id?, takes:[{id, key, created, quality, seconds, frames, face, files:{video, first, last, tail, passes}, …}]}}}`; take fields under "Takes"; per-pass `prompts` are left out (v0.6.0); folders whose name is not an id are skipped |
| POST | `/reelwright/takes/star` | `{slug, scene_id, take_id}` | `{ok}` |
| POST | `/reelwright/takes/delete` | `{slug, scene_id, take_id}` | `{ok}`; when the starred take goes, the newest left is starred and recorded as `auto_star` (v0.6.0). v0.6.1: under the lock the take folder is renamed to `takes/.deleting-<id>-<hex>` (repair and index rebuilds skip it; `new_take_id` still counts it), then removed after the lock |
| POST | `/reelwright/merge` | `{project, draft?, range?: [from_scene_id, to_scene_id], stems?, job?}` | `{ok: true, files:{video, chapters?, srt?, otio?, fcpxml?, bundle?, stems?, loudness?}, duration, skipped[], created, soundtrack, job, draft, range: [first_id, last_id]\|null, loudness?}`. v0.6.0: one merge per project: 409 `{error: "busy", message}`; cancelled → 200 `{ok: false, cancelled: true, job}`; autosaves with the owner check first, so 409 `{error, reason: "slug_conflict", other}` too. `loudness` (with `stems`) = `{target, integrated, lra, true_peak, mix, scenes, "track_<id>"}` (LUFS, LU, dBTP; null = silent). v0.7.0: `warnings: [text]`, e.g. a scene whose colour reference scene is gone or has no finished take (it is not colour matched); also written to the server log, not sent with the `reelwright.merge` event |
| POST | `/reelwright/merge/cancel` | `{job}`, or `{slug}` for any merge of the project (the one after a render) | v0.6.0: `{ok: true, cancelled: bool}`; ffmpeg is killed and the merge's files are removed |
| POST | `/reelwright/autosave` | `{project, version?, force?}` | `{ok, version}`. v0.6.0: 409 `{error, reason: "slug_conflict", other: {id, name}}` when the folder's `project.json` has another non-empty `project_id`, unless `force: true`; a folder without one adopts the incoming id |
| GET | `/reelwright/versions?slug=` | – | `{versions:[{name, created, size}]}` |
| GET | `/reelwright/version?slug=&name=` | – | `{project}` |
| POST | `/reelwright/versions/delete` | `{slug, names[]}` or `{slug, all: true}` | `{removed, versions}`; only `project_YYYYmmdd_HHMMSS.json` files in `versions/`, never `project.json` |
| GET | `/reelwright/llm/settings` | – | `{base_url, model, has_key, guides:{name:{bytes, fetched}}, guide_urls}` |
| POST | `/reelwright/llm/settings` | `{base_url?, model?, api_key?}` | `{ok}` |
| POST | `/reelwright/llm/models` | `{base_url?}` | `{models[]}`; v0.6.0: the base URL is normalised (`http://` added, a pasted `/chat/completions` removed, other schemes refused); a server error answers 502 `{error, reason}` |
| POST | `/reelwright/llm/test` | `{project?}` | `{ok, ms, model, reply, base_url, thinking, note}`; 20 s limit, readable error when the server can't be reached; `thinking` is true when the reply carried reasoning |
| POST | `/reelwright/llm/rewrite` | `{project, scene_id, instruction, job?}` | `{sections?, raw?, warnings[]}` or `{cancelled: true}` |
| POST | `/reelwright/llm/split` | `{project, scene_id, job?}` | `{pass_prompts:{n: text}}` or `{cancelled: true}`; v0.6.0: `llm.split_prompts` accepts keys `"2"`, `"02"`, `"pass 2"`, `"Pass_2"`, `"P2"`, a list, `{"passes": …}`, and object values (written out as text) |
| POST | `/reelwright/llm/script` | `{project, script, part?, parts?, notes?, known_cast?[], job?, can_split?}` | `{scenes[], cast[], warnings[], tokens, ms, attempts, budget, input, context}` or `{cancelled: true}`; v0.6.0: `llm.coerce_script` gives every field the editor's type and leaves out bad items, with a line in `warnings`; v0.4.3: shots carry `duration`, and `scriptparts.fit_scene` makes each scene's length fit its shots and dialogue (a changed scene gets `fit_note`); v0.4.2: `script` is one part, `notes` go with every part, `known_cast` keeps names; with `can_split` a cut-off answer is not retried (the editor splits the part) |
| POST | `/reelwright/llm/script/parts` | `{script, part_chars}` | v0.4.2, `scriptparts.split_script`: `{notes, parts:[[block…]], chars, blocks}`; a part's text is its blocks joined by newlines |
| POST | `/reelwright/llm/passes` | `{project, scene_id, passes: [1-based] \| null, instruction?, job?}` | v0.8.0, `llm.write_passes` (see "Write prompts"): `{scene_id, pass_count, passes: [{index, start, end, sections: {six}}], warnings: ["Pass k: …"], tokens, ms}`. `passes` null, missing or `[]` = every pass; written in ascending order, one request each. `start` / `end` = the planner's pass range in scene seconds. A request that fails after a pass was written: 200 with the passes so far plus `error`, `reason`, `failed` (the pass number) and a warning. Stopped (`/llm/cancel`): `{cancelled: true, passes, warnings, tokens, ms, scene_id?, pass_count?}`. 400: `passes` not a list of whole numbers ≥ 1, `instruction` not text, an unknown scene or pass, a raw-mode scene, no base URL; 502 `{error, reason}` when the first pass fails |
| POST | `/reelwright/llm/cancel` | `{job}` | v0.4.2: `{ok, cancelled}`; stops the running rewrite / split / script request with that job id, which then answers `{cancelled: true}` (v0.8.0: also `/llm/passes`, which answers with the passes written so far) |
| POST | `/reelwright/promote_frame` | `{slug, scene_id, take_id, which: first\|last\|time, t?}` | `{asset}` |
| POST | `/reelwright/cast/export` | `{project, cast_id}` | `{folder, files}` |
| POST | `/reelwright/continuity/check` | `{project, scene_id}` | `{scores:{cast_id: value}, available}` |
| POST | `/reelwright/llm/guides` | `{}` | `{guides}`: downloads MiniMax's `ref-en.txt` and `base-en.txt` into `user/reelwright/guides/` |
| POST | `/reelwright/llm/describe` | `{project, asset_ids[≤4], prompt, clips?[≤3]: [{asset, in, out}]}` | `{text, ms, model, note, video}`; pictures as JPEG `image_url` parts; v0.19.5: videos (whole assets, or clips: a cast member's video anchors) get frames over their range (`media.vision_frames`: 6 for one video, 3 / 2 each for more, 10 pictures in all), and the first one up to 20 s also a small silent H.264 clip (`media.vision_clip`, 640 px, 8 fps) sent as a `video_url` part when `llm.video_wanted` (Global → Prompt rewriter → `describe_video` auto / video / frames); on Auto an HTTP or server error sends frames instead and `llm._VIDEO_REFUSED` remembers the server and model (a context error falls back without that); `video` says whether a video was taken; `note` says how each video went; budget max(Max tokens, 6000), or 600 with thinking off; one retry with thinking off when a thinking model runs out of tokens |
| GET | `/reelwright/files?root=input\|output&q=&kind=&limit=` | – | `{files:[{rel, kind, bytes, mtime}], total, truncated}`, newest first |
| POST | `/reelwright/import` | `{slug, root, rel}` | `{asset}`; output files are hard-linked or copied into `input/reelwright/<slug>/from_output/` |
| GET | `/reelwright/profiles` | – | `{profiles:[{id, name, created, updated, global}], default}` |
| POST | `/reelwright/profiles/save` | `{name, global, id?, default?}` | `{profile, profiles, default}`; with `id` it replaces that profile; an unknown `id` is refused (400 "unknown profile", v0.6.1) |
| POST | `/reelwright/profiles/delete` | `{id}` | `{profiles, default}` |
| POST | `/reelwright/profiles/default` | `{id}` (`""` clears) | `{profiles, default}` |
| GET | `/reelwright/storage?current=<slug>` | – | v0.4.0, `files.scan`: `{projects:[node], size, current}`; node = `{id, label, kind: project\|group\|scene\|take\|passes\|cut\|version\|asset\|dir\|file, size, count, mtime, note, flags[], del, why?, view?, type?, children[]}`. Ids: `p:<slug>` (whole project), `o:<output-rel>`, `i:<input-rel>`, `cut:<slug>:<stem>` (one merged cut and its side files). v0.6.0: a scene folder not in the project is `orphan` only when it is this project's (index.json `project_id`, else the autosaved versions), else `other_project` (the note names the project) or `unknown_owner`; each scene's pass cache is a `passes` node labelled "Pass cache" with flag `cache`; draft and range cuts are their own groups with flags `draft` / `range` and may hold a `stems` folder and `_loudness.json`; `cuts/.next` is shown with `del: false`; the open project is read with `load_project()` |
| GET | `/reelwright/sheet?files=<json list of input-relative paths>&cell=` | – | v0.4.1, JPEG of the anchor sheet `media.sheet_image` builds for those files (≤64, each checked with `safe_join` against the input folder) |
| GET | `/reelwright/waveform?file=<input-relative path>&per_second=` | – | v0.5.0, `merge.waveform_peaks`: binary u8 peak levels (mono, 0–255), headers `X-Per-Second`, `X-Duration`; 10–200 per second, memoised by path, size and mtime |
| POST | `/reelwright/storage/delete` | `{ids[], current}` | `{removed, freed, errors:[{id, error}], deleted[]}`; ids inside another selected id go with it; takes go through `ProjectStore.delete_take`; refuses the open project as a whole, any `project.json`, the open project's `wired.json`, `scenes/*/index.json` and anything outside `reelwright/<slug>/`. v0.6.0, checked on the server: anything of a project while it renders or merges (`jobs.is_busy`), a take's own files ("part of a take; delete the take"; its old `passes/` may go), `cuts/.next`, a path part with `:` or NUL; a linked project folder is unlinked, its target kept |
| POST | `/reelwright/storage/repair` | `{slug}` | v0.6.0, `ProjectStore.repair`: `{ok, repaired:[scene_id], takes_found, added, dropped, project: "ok"\|"missing"\|"damaged"}`; re-lists every scene's takes from their `meta.json` (a missing or damaged index.json is rebuilt, unlisted finished takes are added, takes whose folder is gone are dropped, a lost star moves to the newest take); the pass cache is not a take |
| GET | `/reelwright/beats?file=<input-relative path>` | – | v0.6.0, `beats.cached`: `{bpm, beats:[s], downbeats:[s], duration, file}`; `bpm` 0 and empty lists for silence or under 2 s; 400 without the file or ffmpeg. Cached in memory and in `user/reelwright/cache/beats/<content digest>.json` |
| POST | `/reelwright/soundtrack/excerpt` | `{slug, scene_id, pass (1-based), project?}` | v0.6.0, `assemble.pass_song`: the WAV H3 gets as the soundtrack for that pass, made with the calls a render makes (the same file under `soundtrack/`): `{url: "/view?…&type=output", file, start, length, codes[], marker, pieces:[{asset, src_in, src_out, at}]}`, or `{url: null, file: null, reason}` when the pass gets no song. Without `project` the saved `project.json` is used |
| GET | `/reelwright/filmstrip?file=<output-relative video>&h=` | – | v0.7.0, `merge.filmstrip`: `{file, url, interval, count, tile_w, tile_h, duration}`. One JPEG row of `count` tiles, each `tile_w` × `tile_h` (`h` 16–256, default 54; the video's aspect, even width); tile k is about the frame at k × `interval` s (ffmpeg `fps`). `interval` is 0.25 s up to 150 s of video, else duration / 600; when the row would pass 65,500 px (the widest JPEG ffmpeg writes) there are fewer tiles, further apart. `file` is the sprite, output-relative (`<video name>.filmstrip_<h>.jpg` next to the video, with a `.json` of the layout); `url` is its `/view` URL plus `&v=<video mtime_ns>`. Made once and reused while the video's size and mtime are unchanged; written through a temporary file under a per-sprite lock; at most 2 filmstrip ffmpeg runs at a time (a `threading.BoundedSemaphore`). 400: `file` not under `output/reelwright/`, not a video extension, a bad `h`, or a file ffmpeg can't read; 404: no such file |
| POST | `/reelwright/speech` | `{file (output-relative video), lines: [{id, t, duration}], start?, end?}` | v0.10.0, `speech.timed_lines`: `{lines: [{id, t, end, matched, planned}], segments: [[start, end]]}` in file seconds; the take's segments are cached by path, size and mtime |
| POST | `/reelwright/voice_from_take` | `{slug, scene_id, take_id, cast_id, lines: [{id, t, duration}]}` | v0.10.0: the lines timed to the take's speech, cut (−0.08/+0.12 s), joined with 0.25 s gaps (≤ 15 s), peak-normalised into `input/reelwright/<slug>/voice_<cast>_<scene>_<take>.wav`: `{asset: {file, kind: "audio", duration, name, category: "voice"}, used: [line ids], seconds}`; 400 under 2 s |
| POST | `/reelwright/crop` | `{slug, file (an input-relative picture), box: [x, y, w, h] (0..1), name}` | v0.20.0, `detect.crop`: `{asset: {file, kind: "image", width, height, name, category: "subject"}, small}`; written to `input/reelwright/<folder>/crops/<slugified name>_<key>.png`, the key a hash of the picture, its mtime and the box (the same box gives the same file); `small` when the short side is under 400 px; a video, a missing file or a box outside the picture answers 400 |
| GET | `/reelwright/detect/status` | – | v0.20.0, `detect.status`: `{faces: {ready, error}, objects: {ready, model, folder, state: idle\|downloading\|done\|error, error, bytes, done?}}`; `done` (bytes in the folder) while downloading |
| POST | `/reelwright/detect/download` | `{}` | v0.20.0, `detect.download`: starts `huggingface_hub.snapshot_download("IDEA-Research/grounding-dino-tiny", allow_patterns=["*.json", "*.safetensors", "*.txt"])` into `models/reelwright/grounding-dino-tiny` in a thread; answers the status |
| POST | `/reelwright/detect` | `{slug, file, mode: faces\|objects, queries?[≤12]}` | v0.20.0: `{boxes: [{box: [x, y, w, h], label, score}], engine: insightface\|grounding-dino, ms}`, best first, ≤ 24. Faces: insightface (`continuity.find_faces`), else the object finder asked for "face"; each widened to head and shoulders (`detect.head_and_shoulders`). Objects: `detect.find_objects` (Grounding DINO, box 0.3 / text 0.25 thresholds, near-identical boxes of one label merged); the model is loaded once, moved to ComfyUI's device for a search and back to the CPU after; 400 when it is not downloaded |

Errors (v0.6.0): a body that is not a JSON object, or a field of the wrong type, answers 400 with the reason.
`SlugConflict` and `MergeBusy` answer 409, LLM failures 502 `{error, reason}`.

File previews use ComfyUI's own `/view?filename=&subfolder=&type=output|input`.

## Websocket events (`api.addEventListener(name, e => e.detail)`)

| Event | Detail |
|---|---|
| `reelwright.progress` | `{slug, run_id, scene_id, pass: 1, passes: 3, step, steps, phase: "encode"\|"sample"\|"decode"\|"save"\|"reuse"\|"done"\|"error"\|"skipped", message}`. v0.6.0: `reuse` = the pass came from the pass cache (message "pass N from the pass cache"); `save` may say "joining N passes" or "face check skipped: …"; `done` has the take id as message and can come twice for a scene ("v5 starred (best face match of 3)", "v4 starred (better face match)"); `error` (pass 0, message = the error, last 600 characters) and `skipped` (pass 0, message like "it continues from 01 Harbor at dusk, which failed") end a scene. The editor treats `done`, `cached`, `error` and `skipped` as final (`ctx.isFinal`) |
| `reelwright.run` | v0.6.0: `{slug, run_id, phase: "start", targets: [scene_id], reused: [scene_id]}`; `{slug, run_id, phase: "end", targets, reused, rendered: [scene_id], failed: [{scene_id, error}], skipped: [{scene_id, reason}], warnings: [{scene_id, message}], interrupted: bool, error?}`, always sent (`warnings`: a drift retake or an extra variant that failed after the scene's first take was made; the scene still counts as rendered) (from a `finally` that also catches ComfyUI's Stop, a BaseException); `error` only when the run itself stopped ("Stopped." with `interrupted: true`, else the exception text); per-scene failures are only in `failed`. `{slug, run_id?, phase: "rejected", error}` when a check fails before any GPU work (node setup, pre-flight, an unknown action); the node then raises. After `end`, the node raises when `failed` is not empty |
| `reelwright.preview` | `{slug, scene_id, pass, passes, step, steps, image: "data:image/jpeg;base64,…"}` every sampler step, at most one per 0.25 s, always the last step (v0.3.5; v0.3.8 was one a second). The editor turns `image` into a `blob:` URL (`web/rw/preview.js`) before showing it. Made with ComfyUI's own previewer under any extension wrapper (`render.stock_previewer`, v0.3.9; VideoHelperSuite's animated previews wrap it). Replaces ComfyUI's own node preview |
| `reelwright.merge` | `{slug, job, phase: "start"\|"progress"\|"end"\|"error", …}`. From `/merge`: `start` `{draft, range, stems}`, `progress` `{percent}`, `end` `{files, duration, loudness, draft, range}`, `end` `{cancelled: true}` or `end` `{error}`. From the automatic merge after a render (job `merge-<run_id>`): `start`, `progress`, `end` `{files, duration}`, `end` `{cancelled: true}`, `error` `{error}`. `job` is v0.6.0 |
| `reelwright.llm` | v0.4.2: `{job, phase: "waiting"\|"thinking"\|"writing"\|"done"\|"retry", tokens, reasoning, chars, elapsed, budget, input, context, attempt, attempts, note?, part?, parts?}` about twice a second while an LLM request with a `job` id runs (`llm.chat` streams the answer). `tokens` counts streamed chunks, about one token each; `input` is the estimated prompt size. v0.8.0: `/llm/passes` adds `scene_id`, `pass` (1-based), `passes` (the scene's count), `item` / `items` (place in this batch) and `completed`; `done` comes once per pass, and the HTTP answer ends the job |

## Running a render

The editor writes `{"action": "pending"|"selected"|"from"|"all"|"take", "scenes": [..], "token": <time>}`
into the hidden `run_request` widget, then calls `app.queuePrompt(0, 1)`.
`fingerprint_inputs` hashes project + run_request, so each click re-runs the
node and an unchanged queue does not. After queueing, the editor resets the
request to `{"action": "pending"}`. v0.6.0: queue calls run one after another
(a double click no longer resets the first request while ComfyUI reads it), and
`ctx.actions.run(action, scenes, extra)` ignores clicks while a request is on its way.

New actions (v0.6.0):

- `{"action": "pass_retake", "scene_id": sid, "pass": k}` (1-based): a new seed offset for pass k only, higher than any offset the scene's takes with the same key used. The other passes keep the starred take's offsets; earlier passes come from the pass cache; later passes joined by an overlap seam are guided and sampled again; later passes after a shot cut are reused. The new take is starred. An unknown scene or a pass out of range is `rejected`.
- `{"action": "variants", "scene_ids": [sid], "n": 3}` (`scenes` also accepted; n 1–8, default 2; the editor offers 2–8): n takes per scene with consecutive take ids. With the face check on, the best `face_score` is starred; otherwise the first new take stays starred. Scenes run in project order, so a later scene continues from the starred variant.

What a run does (v0.6.0, `render.Renderer.run`):

1. Registers a `"render"` job for the project (`jobs.running`), picks and orders the targets.
2. Pre-flight, before any GPU work: the H3 nodes import (`render.h3_available()`; render.py imports them lazily, so the extension loads without them), the slug is valid, lint errors of the targets ("fix these first"), model files, every reference / anchor / voice / song-piece / guide file of every pass, each continuing scene has a starred upstream take with `last` and `tail` or `video` (or its upstream renders earlier in this run), asset video guides fit their pass (`fit_clip`), ffmpeg when a target has several passes or a song. Every problem in one `RuntimeError`, sent as `rejected`. v0.8.0: `missing_models` also checks `global.long.guide_vae` ("vae/<name> (the guide VAE)").
3. Re-stars cached scenes whose matching take is not starred, except where the star was picked by hand (`cache.manual_star`). Sends `start`.
4. Renders scene by scene. A failing scene sends `error` and the run goes on; a scene that continues from a failed or skipped scene sends `skipped`. Memory is freed after every scene (`_free(policy)`), also after a failure. Encode-first skips passes the pass cache will provide. v0.7.0: it also leaves for render time every pass whose continuation reference is made in this run (`Renderer._late_encode`: a pass that names the pass before, or a continuing scene whose scene before is a target of this run). Those passes are encoded just before they sample (`encode(scene, sr, n, upstream, prev_pass)`), after encode-first has dropped the text encoder, so it is loaded again (from disk once, then kept in `Models.clips` for the run). v0.8.0: with `seam_video_ref` off a pass after an overlap seam names nothing, so it is encoded first again.
5. Sends `end`; raises `"Reelwright: N scene(s) failed: …"` when any failed.

`fit_clip(frame_idx, clip_frames, gen_frames, role)` places a video guide: a
`last_frame` clip ends on the guided frame (its last frames are kept), other clips
start there and are shortened to the room left (1 frame when fewer than 5 are
left). Reference videos are decoded only up to 15 s; audio refs are cut to 15 s.

The node (`node.py`) autosaves with the owner check before rendering, so a folder
that holds another project refuses the render. The automatic merge after a render
uses job `merge-<run_id>`, is interruptible by ComfyUI's Stop, and any error in it
is reported without failing the node. The `video` output is this run's merge,
else the newest full cut `<slug>_cut_vN.mp4` (never `_draft`, a range or a
`.partial.` file), else the last starred take. After a failed or stopped merge
the last starred take comes before the older cuts.

### Pass cache (v0.6.0)

Long and short scenes keep every finished pass in `scenes/<id>/passes/<file key>.mp4`
plus `<file key>.json` (`{key, pass_key, scene_id, pass, seed, frames, width, height,
created, from?}`), shared by the scene's takes. A file key (32 hex characters,
`cache.pass_file_keys`) hashes the pass key, the seed it was sampled with and, for
a pass joined by an overlap seam, the file key of the pass before. Passes are
written at CRF 4 (`media.PASS_CRF`) through a temporary file; the `.json` is
written last, so a pass counts once both exist. A pass is read back instead of
sampled after Stop or a failure, after a short scene's keep window moves (re-trim
only), for the passes a pass retake keeps, and for the passes of a long scene
whose key did not change (a pass prompt edited for one pass leaves the passes before
it, and those after a shot cut, as they were). A pass whose frame count does not
match, or that can't be read, is rendered again. Pass files a v0.5.1 take kept in `takes/<id>/passes/pN.mp4` are
used when the pass key in its `meta.json` and the seeds match (not for passes that
depend on the upstream take). After each finished take the cache is pruned to the
passes some take uses. Single-pass scenes that are not short don't use the cache.

While a long scene renders, the frames of a pass are handed to the next pass when they
are joined by an overlap seam: only the overlap (v0.6.1), or v0.7.0, when the next pass
names the pass before (`<Video 1>`), its last max(overlap, 124) frames (about 1.5 GB of
float32 at 1344×768) with the pass's sound. v0.8.0: with latent hand-off, also the pass's
sampled video latents (see "Long-scene continuity").

v0.8.0: with `global.long.pass_cache: "lossless"` pass files (and `tail.mp4`) are written by
`media.save_video_lossless`, and the pass `.json` gets `"codec": "lossless" | "near_lossless"`
and `"drift"` (the pass's drift entry, so a pass reused from the cache keeps the numbers it was
rendered with). With latent hand-off a pass keeps `<file key>.latent.safetensors` beside it
(`save_handoff`); pruning removes it with its pass. Reelwright's own files are read with
`media.load_video(exact=True)`.

Before a new take, take folders that are not in `index.json` and have no
`meta.json` (stopped renders) are removed. `Store.new_take_id` skips every number
listed or on disk and creates the folder at once, so an id is never reused.

### Cache keys (v0.6.0)

- `cache.pass_key(…, upstream_take=None)`: a `prev_scene*` guide also holds the id of the take the scene continues from, so a new upstream take makes it stale. The take is the one the scene before *provides*: its matching take when it is cached (its starred take when that was picked by hand), its starred take when it is locked, none when it is stale or missing and will be rendered (then `analysis.rekey` computes the keys at render time from the take just made).
- `cache.scene_key(plan, keys, crossfade_frames)`: the long-scene crossfade counts when the plan has overlap seams.
- The v0.5.1 key (no upstream take, no crossfade) is computed beside it. A take without an `upstream` field (made before v0.6.0) with that key still matches, unless the take it continues from is newer than it (`cache.resolve`). So upgrading does not make every continuing scene stale.
- v0.7.0: `cache.py` is unchanged. A continuation reference hashes as a picture with no assets (`[]`) or a video with no asset (`asset_digest(None)`); what it is made from is already in the key (the guides' upstream key, the upstream take, the previous pass's file key), and the prompt text differs. With `name_continuation` off every key is v0.6.1's (`tests/test_continuation.py` compares against builds stored from v0.6.1 in `tests/data/v061_continuation.json`). With it on, continuing scenes and the passes after an overlap seam get new keys; fresh scenes, and the passes before the first named pass, keep theirs.
- v0.8.0: `cache.pass_key(…, extra=None)` adds `"long": extra` only when `extra` is not empty; `cache.long_pass_extra(long, settings, build)` gives `guide_vae` (a file other than the scene's video VAE, for a pass with any reference or guide to encode) and `handoff: "latent"` (a pass with a `prev_pass_tail` guide), `{}` at the defaults. `carry_audio` off reaches the pass key through the build's guides (`analysis.apply_long` sets `"audio": False` on `prev_pass_tail` guides) and the take key through `cache.scene_key(…, carry_audio=False)` (scenes with overlap seams). `seam_video_ref` counts through the prompt and references. `pass_cache` is in no key. `analysis` keeps the extras per scene (`sr["_extras"]`) for `rekey`. `tests/test_long_continuity.py::test_defaults_keep_every_v070_key` recomputes the v0.7.0 formula. Separately, `build_pass` sends new summaries for multi-pass scenes with a written scene summary (see "Per-pass prompts"); `tests/test_continuation.py` shows that only those passes change.
- `cache.manual_star(index)`: the star was picked by hand when it differs from `index.auto_star` (the take a render or a fallback starred); an index without `auto_star` (before v0.6.0) counts the newest take as automatic. A hand-picked star is kept by runs, and it is the take the next scene continues from.

### Plan fields (v0.6.0, `analysis.plan_response`)

Per scene:

- `upstream_take`: take id this scene continues from (null: fresh start, or the upstream will be rendered).
- `upstream_changed`: the starred take continued from another take than `upstream_take` (for a take made before v0.6.0: the upstream take is newer than it, or will be rendered again).
- `manual_star`: the star was picked by hand and differs from the matching take; runs keep it.
- `estimate_seconds`: time for a new take, from `render_seconds / sampled_frames` of earlier takes with the same quality, size and steps (else scaled by pixels × steps, else the same quality); null without history. Encode-first time is not included.
- `starred_prompts`: the starred take's per-pass prompts (index entry, else its `meta.json`), for the Render tab's "why?" diff.
- `cached_passes`: for a stale or missing scene, how many passes a pending render finds in the pass cache.
- `takes[]` leave out per-pass `prompts` (size).

Top level: `estimate: {seconds, scenes, unknown}` for the stale and missing
scenes, minus cached passes; `unknown` counts pending scenes without history;
`seconds` is null when none has any.

### Takes (v0.6.0)

Each take's `index.json` entry and `meta.json` hold, besides `id, key, created,
quality, seconds, frames, overlap_frames, seeds, face, files:{video, first, last,
tail, passes}`:

- `variant` (the highest offset) and `offsets` (per-pass seed offsets; a pass's seed = plan seed + offset × 1000003);
- `pass_keys` (the pass cache file keys; `files.passes` point into `scenes/<id>/passes/`);
- `start_mode` (the effective start), `upstream: {scene_id, take_id} | null`;
- `prompts` (per pass), `render_seconds`, `generated_frames`, `sampled_frames` (cache hits not counted), `cached_passes`, `width`, `height`, `steps`;
- `face_score` (the lowest face similarity, or null);
- v0.8.0: `drift` (`[]` for fresh scenes; see "Long-scene continuity") and `long` (the take's `guide_vae`, `carry_audio`, `seam_video_ref`, `handoff`, `pass_cache`, `render.LONG_TAKE_KEYS`). `TAKE_FIELDS_NOT_IN_PLAN` is unchanged, so `/plan` has both.
- v0.19.2, render times (`render.PassClock`, fed by `Renderer.progress` and `Renderer.phase`): `render_seconds` is now measured to the end of the face check; `pass_times` `[{pass, seconds, cached, phases?}]` per pass, where `phases` (sampled passes only, phases under 0.05 s left out) splits the pass into `encode`, `guides` (references and hand-off before sampling, again before a refine), `sample`, `upscale`, `refine`, `decode` (also the drift measure) and `save` (the pass cache, a one-pass take's video); `encode_seconds` (only when > 0: the encode-first time of the passes this take sampled, `Renderer.encode_times`, counted once, in the pass's `seconds` and its `encode` phase, not in `render_seconds`); `finish_seconds` (joining the passes, first/last frames, tail clip, face check). The Render tab shows `render_seconds + encode_seconds`.

`meta.json` also has `passes[n].key` (the plan pass key), `settings` and `loras`.
`index.json` gains `auto_star` (the take a render starred) and `project_id` (the
project that rendered into it, from `project.json`, for the Files tab).

`tail.mp4` is the last 124 frames (`render.TAIL_FRAMES = spec.MIN_PASS_FRAMES`) of
the whole scene at CRF 4: from memory for one pass, decoded from the end of the
joined video for several. `last.png` is its last frame. A tail guide that needs
more frames than an older `tail.mp4` holds is cut from the end of the take's video.
v0.7.0: a tail start's `<Video 1>` is the upstream take's whole `tail.mp4` with its
sound (`Renderer._upstream_tail_clip`); for a take made before v0.6.0 (a 60-frame
tail) the last 124 frames of its video are used when they are more. A last-frame
start's `<Picture 1>` is the upstream take's `last.png`, the same picture its guide uses.

## Disk layout

```
output/reelwright/<slug>/
  project.json                       latest autosave (v0.6.0: holds project_id, the folder's owner)
  versions/project_YYYYmmdd_HHMMSS.json
  scenes/<scene_id>/index.json       {starred, takes:[...], auto_star?, project_id?}   (v0.6.0: auto_star, project_id)
  scenes/<scene_id>/takes/<take_id>/<slug>_<NN>_<title>_<take_id>.mp4 first.png last.png tail.mp4 meta.json   (video.mp4 before v0.2.0)
  scenes/<scene_id>/takes/<take_id>/<video name>.filmstrip_<h>.jpg .json   v0.7.0: the timeline's filmstrip
                                                      (merge.filmstrip; .partial files while one is written)
  scenes/<scene_id>/takes/<take_id>/passes/p1.mp4 …   before v0.6.0 only; still read (see Pass cache)
  scenes/<scene_id>/passes/<file key>.mp4 .json       v0.6.0: pass cache, shared by the scene's takes
  scenes/<scene_id>/passes/<file key>.latent.safetensors   v0.8.0: the pass's sampled latents (latent hand-off)
                                                      (<key>.<pid>.partial.mp4 while one is written)
  cuts/<slug>_cut_vN.mp4 .srt .otio .fcpxml .chapters.txt .zip
  cuts/<slug>_cut_vN_draft.mp4 …     v0.6.0: draft merge (half size, veryfast, CRF 28)
  cuts/<slug>_cut_vN[_draft]_sAA-BB.mp4 …   v0.6.0: range merge, scenes AA to BB (1-based)
  cuts/<base>_stems/scenes.wav mix.wav track_<id>.wav   v0.6.0: audio stems (written as <base>_stems.partial first)
  cuts/<base>_loudness.json          v0.6.0: EBU R128 report of the stems
  cuts/.next                         v0.6.0: the next cut number; numbers are never reused
  soundtrack/<hash>.wav              v0.5.0: the part of the soundtrack a pass is sent (48 kHz stereo), made once per content
  wired.json                         which node inputs were wired at the last render
  cast/<cast_id>/training/…
input/reelwright/<slug>/             uploaded assets (from_output/: files picked from ComfyUI's output)
input/reelwright/<slug>/crops/       v0.20.0: crops (<slugified name>_<key>.png)
models/reelwright/grounding-dino-tiny/   v0.20.0: the object finder's weights, downloaded on request
input/reelwright/.uploads/           v0.6.0: uploads being received and checked (temporary)
user/reelwright/llm.json     LLM base URL, model, API key (never in workflows)
user/reelwright/guides/      MiniMax's H3 prompt guides, downloaded on request
user/reelwright/profiles.json  saved Global profiles and the default for new nodes
user/reelwright/cache/beats/<content digest>.json   v0.6.0: beat analysis of an audio file
```

All cuts of a project share one counter, so a draft, a range and a full merge
never get the same N. A merge writes `<cut>.partial.mp4` and renames it on
success; a failed or cancelled merge removes every file it wrote.

Every path that comes from the project or a request goes through
`storage.safe_join`, which refuses anything outside its root.

## Concurrency and safe writes (v0.6.0)

ComfyUI runs the node on its execution thread; routes run on the event loop or
in worker threads. `reelwright/jobs.py` keeps them apart:

- `jobs.lock(slug)`: the project's re-entrant lock. Every read-modify-write of `index.json`, `project.json` or the cut counter holds it: `add_take`, `star`, `delete_take`, `write_index`, `new_take_id`, `autosave`, `delete_versions`, `next_cut_path`, `repair`, placing an upload, the continuity check's index write.
- `jobs.running(slug, kind)`: registers a job for a block. A render holds a `"render"` job for its whole run.
- `jobs.exclusive(slug, kind, job_id)`: checks and registers in one step; raises `jobs.Busy` when a job of that kind runs for the project. `assemble.merge_project` holds a `"merge"` job this way (busy → `merge.MergeBusy`); the `/merge` route registers it before the autosave and the analysis, so Cancel works from the first moment.
- `jobs.cancel(job_id)` sets the job's flag; `merge.run_ffmpeg` polls it five times a second, kills ffmpeg and raises `merge.MergeCancelled`. With `interruptible` (the node's merges) ComfyUI's Stop also kills it. `jobs.is_busy(slug, kind)` lets the Files tab refuse deletes.

`storage.write_json` writes `<file>.<pid>.<uuid>.tmp`, fsyncs it and
`os.replace`s it (retried on Windows). `read_json` falls back to its default on
damaged JSON and logs it; `read_index` rebuilds a damaged take list from the
takes' `meta.json`; `load_project()` falls back to the newest readable version.
`merge.run_ffmpeg` reads stdout and stderr in threads (a chatty ffmpeg can't
block) and passes the filter graph in a file (`-filter_complex_script`, or
`-/filter_complex` on ffmpeg 7+), so long merges fit the Windows command line.

## Project identity (v0.6.0)

`project_id` says which project owns a folder. `/autosave` (and the merge and the
node, with `owner_check`) refuse to overwrite a `project.json` whose non-empty
`project_id` differs from the incoming one (`storage.SlugConflict`, 409
`slug_conflict`), unless `force: true`. A folder from an older version (no id)
adopts the incoming id. The editor then offers "Use a separate project" (the first
free `<slug>-N`) or "Take over this folder" (`force`); until then it pauses
autosaving for that slug and the footer shows "Folder in use".

- New nodes (`editor.startNew`): name "Untitled", slug `untitled-<4 random [a-z0-9]>`, a new `project_id`. A rename on the Global tab moves an automatic folder (the name's slug, or `untitled-xxxx`) to the new name's slug only when that folder's take list was read and is empty.
- Copy detection (`web/reelwright.js checkCopy`, after `onConfigure`): when another Reelwright node that is in a graph and was created earlier has the same `project_id`, this node is a paste or duplicate. `editor.forkProject(usedSlugs)` gives it a new `project_id`, the first free `<slug>-N` and new scene ids, and shows a toast; takes stay with the original. ComfyUI's own copy clone (a node that never joins a graph) is detached after 5 s and never writes.

## Prompt context (v0.6.0)

`prompt.prepare(p)` returns a `Context`: a dict whose entries are computed on
first use and kept: `project`, `index` (`project_index`), `depth`
(continuation depth), `starts` / `total` (`scene_starts`), `start_mode` (the
effective start of every scene), `tracks` (`soundtrack.resolved`) and
`cast_by_key`. `build_pass(p, scene, i, plan, pass_, ctx=None)`, its helpers and
`validate.lint_project(p, plans, builds, asset_exists, ctx=None)` take it;
`analysis.analyze` builds one per analysis. A ctx made from another project dict
is ignored. `build_pass` results gain `issues: [{level, tag, message}]`.

Per pass the build sends: a cast member's voice only when that character speaks
in the pass (and the pass gets no song); a first-frame, last-frame or keyframe
picture named in the text only to the pass it guides (other passes name it in
words); a guide video named in the text as a reference video too
(`videos[i].guide = True`). Pass prompts edited by hand, Split prompts and raw
prompts get the task tags once (`place_task_tags`). Written `[Shot N]` lines go
to the pass that holds that shot, renumbered, with times moved to pass time
(`written_shots`).

## Continuation as a named reference (v0.7.0)

With `global.continuity.name_continuation` on (the default), the footage a pass
continues from is also sent to `MiniMaxH3ReferenceToVideo` as reference 1 and named
in the prompt, as MiniMax's `ref-en.txt` does for a first-frame picture (2.2) and a
continued video (2.3). The `MiniMaxH3AddGuide` anchoring is unchanged.

- Which passes: `model.pass_continuation(p, i, pass_, mode=None)` (JS `passContinuation`) → `"picture" | "video" | ""`. `""` when the switch is off, for scene 0 and for fresh starts. Pass 1 of an effective `tail` start with an overlap → `"video"`; pass 1 of an effective `last_frame` start (a re-anchored tail too) → `"picture"`; a later pass → `"video"` when `seam_before` is `"overlap"` (v0.8.0: and `global.long.seam_video_ref` is on), else `""`. `continuation_frames(...)` (JS `continuationFrames`): 124 after a pass seam, min(124, frames of the scene before) for a tail start, 0 for no clip.
- Refs: `prompt.continuation_of(p, scene, i, pass_, ctx)` → `{kind, source, frames}` or None; `source` is `prev_scene_last`, `prev_scene_tail` or `prev_pass_tail`. `collect_refs(…, continuation=)` puts it first: `images[0] = {"assets": [], "source": "prev_scene_last", "continuation": True, …}` or `videos[0] = {"asset": None, "source", "frames", "soundtrack", "continuation": True, …}`. The clip's `soundtrack` (its sound as `<Audio N>`) is true when the pass's other video sounds and audio refs leave one of the 3 audio slots. `PassRefs.continuation` = `{kind, source, frames, label: "<Picture 1>" | "<Video 1>", audio_number}`. Every other number follows (`number()`), so subjects, `@P` / `@V` / `@A` labels and `tag_map` move up by one.
- `build_pass` builds the pass as in v0.6.1 (anchor only), with an issue, when:
  - the written text (pass prompt, raw prompt, written sections, shots) holds `<Picture N>` (picture continuation) or `<Video N>` / `<Audio N>` (clip) and not the editor's own definition (`OWN_DEFINITION`, so a hand-edited copy of a v0.7.0 build is kept): `info`;
  - `over_budget(refs)`: more than 9 pictures, 3 videos or 12 files even after *Auto* packing: `warn`, with the counts.

  A clip without a free audio slot goes without its sound (`info`). `build_pass` returns `continuation` (`PassRefs.continuation`, or None).
- Text: `continuation_definition` (subject_definitions), `continuation_retention` (`fully_preserved`; the clip's sound is `reference`), `_cite_continuation` (`[Shot 1] The shot begins from <Picture 1>.` / `… continues seamlessly from the final frames of <Video 1>.`; a `[Shot 1]` that "continues seamlessly from the previous moment" says from what; without a `[Shot 1]`, one is added before the first `[Shot N]`), and the automatic summary. Written prompts go through `_name_in_written`: six-section text gets the lines in their sections (a missing subject_definitions section is added); other text gets the definition in front, after the task tags. Lines that already start with the label are left alone. `task_tags` adds *keyframe completion* (picture) or *video continuation* (+ *audio reference* for its sound) and does not count it for *reference generation*.
- Render: `Renderer.encode(scene, sr, n, upstream=None, prev_pass=None)` sends it as `ref_image_0`, or `ref_video_0` (+ `ref_video_audio_0`). `_continuation_ref`: `prev_scene_last` → the upstream take's `last.png`; `prev_scene_tail` → `_upstream_tail_clip(take)` (see Takes); `prev_pass_tail` → the last ≤ 124 frames of the pass before and the matching end of its sound. Encode-first leaves such passes for render time when their source is made in the same run (`_late_encode`, see "Running a render").
- Lint: `validate._sent_assets` skips the asset-less clip; `_media_counts` passes the effective start, so the budget matches what the build sends; the 2–15 s video check names the clip by its source ("the tail clip of the scene before is 1.0 s").
- Tests: `tests/test_continuation.py` (off gives the stored v0.6.1 builds and keys; on changes only the passes that continue), parity fixtures in `tests/test_model_parity.py`.

## Per-pass prompts (v0.8.0)

`scene.prompt.passes[k-1]` holds pass k's own six sections and the range (scene seconds) it was written for.
`model.py` and `model.js` share the helpers (parity-tested):

- `pass_texts(p, scene, plan=None)` / `passTexts(project, scene, plan = null)` → `{texts: [six sections per current pass], moved: [1-based passes whose text was written for another range], unused: [1-based stored entries with text no current pass gets], same, stored, entry: [per current pass: the 1-based stored entry its text came from, or null]}`. `same` when every stored entry with text has an index below the pass count and a range within one frame (1/24 s + 1e-9) of that pass's; a one-pass scene is `same` unless entries after the first have text. Otherwise greedy matching: every (pass, entry with text) pair that overlaps in time, largest overlap first (ties: lower pass, then lower entry), each used once.
- `relayout_pass_texts` / `relayoutPassTexts` → a new `prompt.passes`: one entry per current pass with its `start` / `end` and `texts[k]`; `unused` text is dropped ("Use the new layout").
- `pass_sections(p, scene, plan, k)` / `passSections(…)` (k 1-based) → `{own, used, source}`; `source` per section: `"pass"` (own text), `"auto"` (the summary in a multi-pass scene, or an empty summary; `used` is `""`), `"split"` (detailed_description in a multi-pass scene without own text: the scene text, split per pass by the build), else `"scene"` (shared).
- JS only, for edits inside `ctx.actions.edit`: `setPassSection(project, scene, plan, k, key, value)` and `writePassTexts(project, scene, plan, [{index, sections}])`. Both relayout first, so index = pass number − 1 always holds after an edit.
- `dialogue_seconds(d)` / `dialogueSeconds(d)`: `duration` when > 0 (at most 600), else max(1.0, (words + CJK characters / 4) / 2.5) (`WORDS_PER_SECOND`, `CJK_PER_WORD`; words are runs between spaces that hold a letter or digit). `dialogue_spans(scene, plan)` / `dialogueSpans` → per line `{id, pass, start, end, seconds, estimated, seam, past_end}` (`seam`: the end of a pass that is not the last when the line runs past it).
- `camera_sentence(camera, amp, speed)` / `cameraSentence` → "The camera pushes in with small amplitude at slow speed." (`""` without camera text; trailing `.!?` dropped before amplitude and speed; capitalised; full stop). `framing_phrase(f)` / `framingPhrase` → "a close-up", "a low-angle shot", `""`.

`prompt.build_pass`, structured mode, no `pass_prompts[k]` override:

- each section is `pass_sections(…).used` (extra keys of `scene.prompt.sections` are kept, as before);
- summary: the pass's own when written. A single-pass scene: else the scene summary (unchanged). A multi-pass scene never sends the scene summary and reads no tags from it. A pass without its own summary gets `prompt.pass_summary(…)` when the scene summary is written ("The target video shows <Subject 1> and unfolds over 2 shots." + the first sentence of each of the pass's shots, labels substituted, `<d>` spans removed + "<Subject 1> speaks." + the voice, song and continuation sentences of the automatic summary; made even with automatic subjects off), else the v0.7.0 automatic summary (so those scenes keep their keys);
- detailed_description: the pass's own text as written (its own `[Shot N]` numbering and pass times, merged with the automatic shot lines by label, spoken lines kept); else `written_shots` splits the scene text as before;
- a shot with `framing`, `camera_amp` or `camera_speed` (planner pass shots carry them) is written by `prompt._framed_shot`: `[Shot 1] A close-up: The camera pushes in with small amplitude at slow speed. <text>.`, `[Shot 2] At 00:05.000, the shot cuts to a close-up: …`; without a framing the move follows the text in later shots. A shot without them is written exactly as before.

A hand-edited or Split pass prompt (`pass_prompts[k]`) still replaces the whole pass; pass texts are the structured layer under it.

Lint (`validate.py`): `_pass_text_issues` (info: texts written for another pass layout, naming moved and unused ranges; warning, one per multi-pass scene: the passes without a summary of their own and without an override), `_dialogue_span_issues` (warning: a line past a pass seam or the scene's end, "about" and a hint when its length is estimated; empty lines and lines in no pass are skipped); the empty-soundscape info names only the passes without one. Tests: `tests/test_pass_prompts.py`, `tests/test_continuation.py` (`test_v080_changes_only_the_summary_of_multi_pass_scenes_with_a_written_summary`).

## Long-scene continuity (v0.8.0)

Later passes of a long scene lose quality through decode → encode round trips at overlap seams (the
VAEs keep no state between calls): the anchored overlap and its sound, the 124-frame `<Video 1>`, the
int8 video VAE's encoder, and CRF 4 4:2:0 pass-cache read-backs. `global.long` has a switch for each;
at the defaults behaviour and every key are v0.7.0's (`analysis.long_settings(p)` fills missing keys).

- **guide_vae**: `render.Models.encoder_vae(settings, guide_vae)` returns the VAE that encodes the `MiniMaxH3ReferenceToVideo` references (pictures, clips, the continuation) and every `MiniMaxH3AddGuide` guide; the video VAE still decodes. `""` or the scene's own video VAE file = the video VAE (wired or file). Loaded through `Models.vae`, once per run. `check_guide_vae` refuses a VAE whose model is not `MiniMaxH3VideoVAE` or has no encoder.
- **carry_audio** false: `analysis.apply_long(p, builds)` sets `"audio": False` on `prev_pass_tail` guides, so render anchors the picture only. `assemble.pass_segments(plan, files, crossfade, carry_audio=False)` gives the pass after an overlap seam `audio_lead_frames = overlap − crossfade`; `merge.build_command` (`_audio_lead`) starts its sound at the overlap's first frame and `acrossfade`s over crossfade + lead frames. Picture, timing and length are unchanged; 0 or a missing key gives the old graph. A tail start's guide keeps its sound.
- **seam_video_ref** false: `model.pass_continuation` / `passContinuation` return `""` for a pass after an overlap seam, so `prompt.continuation_of`, the budget, lint and render all leave out `<Video 1>` (the prompt writes "[Shot 1] The shot continues seamlessly from the previous moment."); the pass is still anchored, is encoded first again and only the overlap frames are kept between passes. Pass 1 of a tail start is unaffected.
- **handoff** `"latent"` (experimental): the guide a pass after an overlap seam gets from the pass before is that pass's sampled video latents for the overlap (`latent_guide`; the last 5j+2 latents for 17j+5 frames, 12 for 39), added to `minimax_keyframes` as `MiniMaxH3AddGuide` adds an encoded clip (`add_latent_guide`: `{"resolved_frame_index": 0, "latent": slice}`); the sound, when carried, is a second, audio-only `AddGuide` at the same frame. `_generate` also returns the video latent; `save_handoff` / `load_handoff` keep it beside the pass in the pass cache, so a retake reading the pass before from the cache hands off the same latents. Valid because the encoder takes 17-frame chunks with no state between them and an aligned overlap starts on a chunk boundary (`test_h3_vae_latents_of_an_aligned_overlap_are_a_slice`, random-initialised encoder, difference 0.0). Falls back to pixels (logged; the drift entry gets `handoff: "pixels"` and `handoff_reason`) for an overlap or a pass before off the 17k+5 grid, a guide not at frame 0, another canvas size or channel count, a latent that is not an H3 AV latent, or a pass before from the cache without its `.latent.safetensors`. Not covered: the sound (the audio encoder's causal attention spans the whole clip), the `<Video 1>` reference (the node needs pixels), tail starts between scenes, the first pass.
- **pass_cache** `"lossless"`: `media.save_video(lossless=)` / `save_video_lossless` write `libx264rgb` (`LOSSLESS_CODEC`, qp 0, preset ultrafast, rgb24) with 24-bit FLAC in the same `.mp4` names; `media.load_video(exact=True)` / `load_video_exact` decode RGB streams with PyAV to rgb24 (`is_rgb_video`, `RGB_PIX_FMTS`), bit-identical (ComfyUI's reader is off by up to 1.13 levels on RGB streams). `tail.mp4` is written lossless too: from the last pass in memory when its 124 frames all lie past the blended overlap, else from the joined CRF 16 video, as before. About 4× the disk of CRF 4 in a test; faster to write.
- **Drift meter**: for each pass with a `prev_pass_tail`, `prev_scene_tail` or `prev_scene_last` guide, `render_scene` calls `analysis.drift_metrics(guide, gen)` on up to `DRIFT_SAMPLES` = 3 anchored frames (first, middle, last), 0–255 scale: `anchor_diff` (mean |gen − guide|), `color_shift` (length of the mean RGB difference) and `rgb_shift` (per channel, gen − guide), `sharpness` (Laplacian variance gen / guide; null for a flat guide). `drift_level` → `"ok" | "warn" | "bad"` against `DRIFT_LIMITS` (anchor 8 / 16, colour 4 / 10, sharpness 0.8–1.25 / 0.6–1.6; starting values). Entry: `{pass, source, frames, anchor_diff, color_shift, rgb_shift, sharpness, level, handoff?, handoff_reason?, pass_cache?}` in `take["drift"]` and each pass cache `.json` (`pass_cache: true` when reused).
- Lint: `validate._cut_seam_hint` (info) for a scene with overlap seams and no shot cuts: the seam times and "Add shot cuts up to N s before a seam", plus "set Global → Long scenes → Seams to Auto or Cuts" when Seams is Overlap only.
- Tests: `tests/test_long_continuity.py`, the v0.8.0 tests at the end of `tests/test_render_flow.py` (stubs record which VAE each node gets), `global.long` fixtures in `tests/test_model_parity.py`.

## Write prompts (v0.8.0)

`llm.write_passes(cfg, p, scene, wanted=None, instruction="", progress=None, state=None, plan=None, builds=None)` writes
each wanted pass (1-based; None = all) of a normalised project's scene, one request per pass, in ascending order;
each request sees the passes written before it in the batch. `state` fills as it goes (`{scene_id, pass_count,
passes, warnings, tokens, ms}`), so a Stop keeps what was written; a failure after the first pass ends the batch with
`error`, `reason`, `failed`; a failure before it raises. Raw-mode scenes raise ("switch it to Structured").
`llm.scene_builds` re-plans the scene (planner + `prompt.build_pass`, no file hashing).

- System prompt, the same for every pass (a server's prefix cache reuses it): `H3_RULES`, MiniMax's guides when downloaded and Global → Prompt rewriter → guides is on, the preset, `PASS_RULES` (this pass only, `[Shot N]` from 1 per pass, "At MM:SS.mmm, the shot cuts to" in pass time, 350–500 words in detailed_description, spoken lines word for word with (S1)…, overlap seam continuation, @ tokens only, JSON with six keys).
- `pass_request(…)`: `scene_context`, the whole-scene note, "Write the prompt of pass k of n" with its range, frames and seam; its shots (pass and scene times, length, framing, camera, amplitude, speed, text) and lines (pass and scene time, shot, speaker token and (S1), delivery, `dialogue_seconds`, `<d>[Lang] text</d>`); the references it sends (`pass_guides`: frame guides with the guide's phrasing), the scene's tokens it does not send, its task types; the pass before (just written, else stored via `pass_texts`, else as built now) and its last line; the pass after (summary, shots, lines); what H3 receives now (`build_pass`); the instruction (default "Write this pass's prompt following the guide.").
- `pass_budget(cfg)`: max(Max tokens, 8192), or 4096 with Thinking off; `ask` retries a cut-off answer with twice the budget up to 32,768, and 429 after Retry-After.
- Parsing (`pass_sections`, `tidy_pass`): the six keys, `{sections}`, `{passes: […]}` or a list (the entry for k, or the only one), `{"2": …}` / `{"pass 2": …}`, `{prompt: "<labelled text>"}` or labelled text; labels → @ tokens through the pass's `tag_map`; the task-type prefix removed from the summary; `"N/A"` = empty except for the soundscape and music; with one `[Shot N]` per timeline shot they are renumbered 1..m and every later shot's "At MM:SS.mmm," set to the timeline's pass time. `subject_definitions` / `retention_analysis` are `""` while their automatic parts are on. Warnings (each "Pass k: …"): moved cut times (> 0.05 s), renumbered or miscounted shots, a description under 300 or over 650 words, spoken lines missing or invented, unknown @ names, fixed labels left as written, a frame guide not named, a `pass_prompts[k]` override.
- Script import (`script_part`): the same JSON; the prompt asks for 2–4 sentences per shot and a 2–4 sentence whole-scene `summary`. `coerce_script` joins a shot answered as separate keys (`_shot_text`: composition, framing, subject, appearance, position, then text / action / description, then environment, lighting, camera_movement, movement, sound, audio; parts under 3 words left out). `IMPORT_MAX_TOKENS = 24576` is the default of `limits()` and `script_part`.
- Spoken lines the LLM writes (v0.20.1): `free_lines(scene, plan)` = `writes_shots` and no `scene.dialogue`; then the request lets it write the lines the note or brief asks for, a later pass gets "The spoken lines written so far …" (`_line_sentences` of the passes before, written or stored), and `tidy_pass(free_lines=True)` keeps them, dropping only a second copy by the same speaker (`_line_speaker`: last @name, else (S#)). `scene_times_to_pass` moves a later pass's "At MM:SS" times to pass time when one is past the pass's length and all lie in its scene range (outside `<d>` spans). The editor puts them on the timeline: `shotfill.writeShots` (one pass), `takePassShots` → `addPassLines` (several; pass time + `x.start`, an overlap repeat once).
- Split (`/llm/split`) and Rewrite are unchanged. Tests: `tests/test_llm.py`, `tests/test_routes.py::test_llm_passes_route`.

## Merge: scene.merge (v0.7.0)

Each scene's `merge` object sets how it sits in the cut; `assemble.scene_merge(s, p)`
returns it (normalising a scene that was not). `cut_plan` turns it into segment keys,
`color_match` adds the gains, and `merge.build_command` reads them. The Global
transition, audio fade and colour-match keys are no longer read by the merge.

- Joins in `cut_plan` (unchanged rules for continuations):
  - the first segment of a cut is `join: "first"` (a tail scene starts after its overlap);
  - an effective `tail` start with an overlap, right after the scene before in the cut: crossfade over min(`global.long.crossfade_frames`, overlap) inside the overlap; not right after it: a cut after the overlap;
  - an effective `last_frame` start right after the scene before: a cut one frame in;
  - otherwise (a fresh start, or a last-frame scene whose scene before is not right before it): `merge.transition`. For anything but `cut`, d = min(`frames`, half the scene before, half this scene) in whole frames. With `soundtrack.locked(p)`: `vfade_out` + `vfade_out_color` on the segment before and `vfade_in` + `vfade_in_color` on this one, d/2 each, through `merge.color` (the join stays a cut, so nothing moves). Otherwise `join: "dip"` or `"xfade"`, `transition` (+ `transition_expr`) from `merge.xfade_transition(kind, direction, color)` and `dur` d.
- Every segment gets `fade = audio_frames / 24` (a slate takes its missing scene's) and, from `_scene_look`: `edge_in` / `edge_out` (`{frames, color}`), `afade_in` / `afade_out` (seconds), `mute` or `volume_db`, and `eq` (brightness, contrast, saturation) when it is not the default. `merge_with_job` calls `merge.join(…, audio_fade_frames=0)`.
- `xfade_transition`: crossfade → `fade`, dissolve, wipe / slide → `wipeleft` … `slidedown`, circle → `circleopen`, pixelize, radial, zoom → `zoomin`; dip → `fadeblack` (black), `fadewhite` (white), or `custom` with `_dip_expr(color)` for any other colour: the colour in yuv420p values (`yuv_of`, BT.601 limited range, as ffmpeg's `fade` and colour source give it); the picture before reaches the colour in the first fifth and the next comes out of it over the rest. The expression is written out without `st()` / `ld()`, whose variables xfade's slice threads share. Both inputs of a custom xfade get `format=yuv420p` first, because a fade to a colour other than black or a colour-match gain leaves a segment in RGB.
- `assemble.color_match(result, store, segments, cancel)` sets each segment's `gain` (`merge.match_gain`, per channel 0.8 .. 1.25): *previous* = the mean colour of the segment before (slates skipped) times its own gain; *scene* = the mean of `color_ref`'s segment in this cut, else of the whole video of its picked take (`global.merge.use`), as rendered. `color_ref` equal to the scene's own id does nothing. A reference that is gone or has no take gives a warning text. Means are memoised per file and range; `cancel()` runs before each.
- `build_command`, per scene. Picture: trim → fit to the canvas → `colorchannelmixer` (gain) → `eq` → own fades (`fade` from / to the colour; the first or last frame is the colour; black is written `black`, so v0.6.1 graphs are unchanged, other colours `0xrrggbb`) → the timing dip (`_vfades`). Sound: mute (silence) → `volume` → own fades (`afade`) → the cut fades (`fade`, at most half the segment, only at plain cuts). Overlapping joins use `xfade` and `acrossfade` over the same frames.
- The merge answer gains `warnings` (also logged). FCPXML and OTIO are unchanged: overlapping scenes are cut where the next one starts.
- Tests: `tests/test_scene_merge.py`. `test_a_v061_project_merges_exactly_as_before` loads the v0.6.1 code from `REELWRIGHT_BASE_V061` (skipped when it is missing) and compares the ffmpeg arguments, filter graph, entries and timing of a converted project, with and without a soundtrack; the only difference is the identity `colorchannelmixer=rr=1:gg=1:bb=1` v0.6.1 ran on the reference scene.
- v0.8.0: `cut_plan`'s entries pass each line's `duration` to `merge.subtitle_cues`; a line with one (> 0) is shown that long (at least 0.3 s), still cut 0.05 s before the next line and at the scene's end; other lines keep the reading-time length. `build_command` reads a segment's `audio_lead_frames` (the pass stitch with `carry_audio` off, see "Long-scene continuity").

## Editor ↔ backend details

- The editor hides the `project` and `run_request` widgets. It attaches a non-serialized DOM widget named `reelwright_editor`.
- Queueing runs only this node: `app.queuePrompt(0, 1, [<execution id>])` (v0.6.0: the node's full execution id; `String(node.id)` before). **Stop** calls `api.interrupt()`; a running merge is stopped with `POST /reelwright/merge/cancel`.
- `/plan` scene status is one of `cached | stale | missing | locked | error`. The editor adds `queued` and live progress from `reelwright.progress`. A scene whose star was picked by hand stays `cached` when some take matches.
- Take and merge file paths are relative to the output directory. Asset `file` paths are relative to the input directory. Both are previewed through `/view`.
- `scene.prompt.pass_prompts` is keyed by 1-based pass numbers as strings; `scene.prompt.passes` (v0.8.0) is a list, index = pass number − 1. `scene.overrides.loras.strengths` is keyed by global LoRA id. `scene.trim.in` is seconds inside the generated pass.
- When a render runs, the node writes `wired.json` (which inputs are wired) into the project folder. `/plan` reads it, so its cache keys match the renderer's.
- Keys (v0.5.1): ComfyUI's ChangeTracker has a capture-phase `keydown` listener on `window`; it reads `document.activeElement` at once and runs the workflow undo/redo (which rebuilds the graph) unless that element is an INPUT, TEXTAREA or contenteditable. The editor therefore keeps keyboard focus on a hidden read-only `input.rw-keys` (`root.focus()` is redirected to it; focus landing on the root or on a mouse-clicked button goes back to it), and its own `keydown` handler on the root treats that field as "not typing".
- Graph rebuilds (v0.5.1): with Vue nodes, a rebuilt node with the same id can stay displayed through the old node's DOM widget element. `web/reelwright.js` remembers a removed node's element for 10 s, and a 250 ms check moves the new editor root into whichever of the two elements is on the page.
- Run state (v0.6.0): the editor clears a run on `reelwright.run` `end` or `rejected`, and also on ComfyUI's `execution_error`, `execution_interrupted`, `execution_success` or `executing` with no node, for the prompt that executed (or cached) this node. A queued run whose node never executes ends when ComfyUI's queue runs dry (with a warning). `eph.lastRun` keeps the last run's `{run_id, rendered, failed, skipped, reused, interrupted, rejected, error}`; `ctx.sceneRunResult(id)` gives a scene's failure or skip.
- Execution ids (v0.6.0): a node inside a subgraph runs as `<instance path>:<id>`. `host.isOwnNode(id)`, the preview redirect and `queuePrompt` use the full execution ids, so a sampler inside a subgraph is not taken for Reelwright.
- ChangeTracker notice (v0.6.0): when the editor writes the `project` widget, `host.changed()` calls the active workflow's `changeTracker.captureCanvasState()` (or `checkState()`), so ComfyUI marks the workflow as modified and keeps the edit in its own undo and in the state a workflow switch restores. During a serialize the call is deferred; during node removal it is skipped. `node.onSerialize` flushes a pending widget write and patches `widgets_values`, so a save or workflow switch carries an edit made less than 200 ms ago.

## Frontend store and editor contract (v0.6.0)

`web/rw/store.js createStore(project, {persist, onConflict})`:

- `update(fn, {label, history, coalesce, plan, render, autosave})`: `label` names the step in the History menu ("Edit" when missing). Up to 150 steps; edits with the same `coalesce` key within 1.2 s are one step.
- Undo, redo, `history()` → `[{k, label, at, done}]` and `jumpTo(k)` restore the project but keep the current `ui` (tab, zoom, snap, ripple, playhead, selection, beats, auto-roll); the selection falls back when its scene is gone.
- `project.__rwv`: a non-enumerable number stamped on every update, undo, redo and load (`stampVersion`); model.js memoises per value.
- Autosave (v0.6.1): one `/autosave` request at a time. A save asked for while one is on its way is sent after it with the latest state (several requests merge into one); answers of an older request never change `saveState`.
- `flush()` writes a pending widget value now. `saveNow({force})` → `{ok}` or `{ok: false, error, conflict}`; Ctrl+S waits for it. `dispose()` flushes, sends a pending autosave and stops every timer; later calls do nothing.
- `load(json, {persist})` normalises (pre-0.6 projects get their `id` as `project_id`, `withProjectId`) and clears history. `replaceProject(next, {label})` (version restore) is one undo step.
- A 409 `slug_conflict` from `/autosave` sets `eph.saveState = "conflict"`, `eph.conflict = {slug, other}`, calls `onConflict` and pauses autosave for that slug.

Editor (`web/rw/editor.js`):

- `host.on(type, cb)` returns an unsubscribe function; `destroy()` calls them all, stops playback and timers, closes an open dialog or menu, and disposes the store.
- Tabs may export `onProgress(ctx, d)`. For progress events of the active tab the editor calls it instead of re-rendering, and re-renders only when a scene starts or ends, or its phase or pass changes (the footer at most 4 times a second). Tabs without it get the old throttled re-render.
- `ctx.actions.edit(fn, {label, …})`, `run(action, scenes, extra)`, `merge({draft, range, stems})`, `cancelMerge()`, `insertScenes(scenes, afterId, {label})` (fresh ids and `seed_n`), `saveNow()`, `showHistory(anchor)`, `resolveConflict()`; `ctx.isFinal(phase)`; `ctx.eph.merge` `{phase, job, draft, range, stems, files?, loudness?, percent?, error?}`; `ctx.eph.takesSlug` (the folder `eph.takes` came from; takes are read again whenever the slug changes and after every load, never for the mount-time project).
- Dialogs: `ui.confirmDialog(root, {title, message, okLabel, cancelLabel, danger, help})` → Promise<bool> and `ui.choiceDialog(root, {title, message, choices, cancelValue, focus, danger, help})` → value are the only confirmation UI (`confirmInline` is unused and deprecated). Enter presses the focused button, danger dialogs open with Cancel focused, Tab stays inside, Ctrl+Z is swallowed.
- Focus: give inputs a stable `key` (`text({key})`, `h(tag, {key})` → `data-key`), built from ids (`shot-t-<id>`, `dlg-text-<id>`). After a re-render the focused field is found by `data-key`, else by help id and the same text, else by position. `ui.focusGuard` keeps focus inside the editor (a click on `<video controls>`, a closed dropdown or dialog hands it back to the key field); `ui.keepFocus(el)` does it by hand. Keys of an IME composition are ignored, and the code editor reports its value on `compositionend`.

### Cut settings, filmstrips and the Merge card (v0.7.0)

- `web/rw/cut.js`: `TRANSITIONS` (value, label, short timeline tag), `DIRECTIONS`, `DIRECTED` (wipe, slide), `mergeDefaults()` (model.js `defaultMerge()`), `mergeOf(scene)` (a complete copy, for reading), `ensureMerge(scene)` (completes `scene.merge` in place, for an edit), `joinOf(p, i)` → `{kind: "first" | "continuation" | "cut" | "transition", mode, m, overlap?, crossfade?, asDip?}` (`asDip`: a soundtrack sets the timing), `transitionLabel(m)`.
- Scene tab `cutCard` (In the cut): input keys `cut-<field>-<sceneId>`; every edit has a History label ("Transition", "Fade in colour", "Scene sound level", "Mute scene sound", "Colour match scene", "Reset …"); **Apply to all…** is a `choiceDialog` and one `edit` step ("Cut settings → all scenes" / "Cut settings → later scenes"); a copy whose `color_ref` is the target scene gets `color_match: "off"`. The Merge card's **In the cut** button sets `eph.scrollToCut` and opens the Scene tab, whose `afterRender` scrolls the card into view and flashes it.
- Render tab: the Merge card's Hard cuts, Transition, Audio fade, Colour match and reference controls are gone; the version diff reports "in the cut" when `scene.merge` differs and no longer compares `scene.transition`.
- Timeline filmstrips (`tabs/timeline.js`): a `WeakMap` ctx → `{map, takes, queue, live, timer}`, keyed `<video>|<take.created>`. Asked for only from `sceneBlock` (so only for blocks the lane window builds), at most 3 requests at a time, tile height 54. The sprite is preloaded with `new Image()` before an entry counts as ready; arrivals are batched into one `store.notify()` after 40 ms, and only while the Timeline tab shows. When `eph.takes` changes (not to null), entries whose take is no longer starred or was rendered again, and failed entries, are dropped. Cells are 44 px × `tile_w / tile_h` wide; a cell shows tile round(t / `interval`), t = the block's visible offset + the cell's middle / zoom; only cells inside `ctx.tl.window` are built, and cells past the take's length are dimmed. The take's `first.png` stays underneath. Cut marks (`cutMarks`) use `joinOf`.
- `api.js`: `rw.filmstrip(file, h = 54)`; `viewURL(rel, type, version)` puts an optional `version` in the query as `rwv=` (the timeline passes the take's `created`, so a sprite rewritten at the same path is loaded again).
- `editor.forkProject` maps each scene's `merge.color_ref` to the new scene ids.
- The editor does not show the merge answer's `warnings` yet; they are in the answer and the server log.

### Pass tabs, rows, Write prompts, follow and drift (v0.8.0)

- `web/rw/passes.js`: `passLayout` (model.js `planScene`), `passTextsOf` (`passTexts` plus `movedPasses`), `adoptLayout` (`relayoutPassTexts`), `setPassSection`, `applyWritten` (an `/llm/passes` answer: `writePassTexts` when its start / end match the current passes within a frame, else relayout first and keep the written ranges, so the card offers "Use the new layout"; a single-pass scene's answer goes into `scene.prompt.sections`, empty answered sections keep the scene's text, and `scene.prompt.passes` is cleared), `dialogueSecs`, `lineSeam`, `shotSeams`, `cameraOptions` (`DEFAULT_CAMERA` first, then the project's presets), `stillMove` (Static Shot, POV, the shakes), `framingOptions`, `runWrite` / `stopWrite` (the Write prompts runner in `eph.passWrite`: one `/llm/passes` call per scene, the live project each time, one undo step per scene, Retry asks only for the passes left). Every model.js helper is feature-detected, with a fallback that follows the same rules.
- Scene tab (`tabs/scene.js`): `promptCard` (Whole scene + `passPane` per pass, `singlePassNote`, `writeRow`, `writeToast`), `shotsCard` / `shotRow`, `dialogueCard` / `dialogueRow`. Row keys `shot-…` / `dlg-…`, in a pass tab `p<k>-shot-…` / `p<k>-dlg-…`. Text fields are `codeEditor({cls: "sans"})` with @tag autocomplete. Labelled History steps: "Pass 3 summary" (coalesced while typing), "Write prompts", "Write pass 2", "Write prompts: <title>" (batch), "Use the new pass layout". Picking a pass tab opens that pass in What H3 receives.
- Global tab (`tabs/global.js`): `seamFields` (Pass seams: guide VAE combobox from `/models` `vae[]` without audio VAEs, carry sound, `<Video 1>` at seams, disabled while `name_continuation` is off, hand-off, pass cache, a note line); `writeBatchBox` after a script import (`eph.imported = {ids}`).
- Timeline (`tabs/timeline.js`): `followPlayhead` runs in the playback loop and sets only `scrollLeft` (the middle of the view, in steps of `FOLLOW_STEP` = 4 px; clamped at the ends), so a long film is rebuilt only near the edge of the built lanes. `pauseFollow` on a drag, `followScrolled` on a scroll the follow did not make (a zoom resets `play.sl` first), `resumeFollow` from the transport's Follow button; Play sets `follow: true`; while paused, the playhead crossing the middle of the view resumes it. The lanes' scroll handler ignores an element that is no longer on the page (a replaced element still got its last scroll event and read 0, rebuilding the lanes every frame). The Camera lane label is framing · preset name · amplitude speed.
- Render tab (`tabs/render.js`): `driftView` per take (`● P2 4.2 · 1.1 · 0.95`, the light from the server's `level`, else the same starting limits), `driftWorst` for the Passes column (starred take), `longView` (the take's non-default `long` settings as a tag).
- `api.js`: `rw.llmPasses(project, scene_id, passes, job, instruction = "")`. `ui.number({placeholder})`; `codeEditor({cls, spellcheck})`.
- `help.js`: new and replaced entries for the pass tabs, rows, camera picker, Write prompts, Pass seams settings, drift and follow.
- Harness: `web-test/mock.js` plans `/plan` passes with model.js `planScene`, builds pass prompts with per-pass texts, serves `/llm/passes` with progress events and Stop (flags `passCalls`, `passesMs`, `passesFail`), and gives demo takes drift; `web-test/interact.py v080_checks()`; `shoot.py` adds `scene_pass.png` and `scene_rows.png`.

### Panels, captions, lists and asset groups (v0.9.0)

- `ui.js`: `splitter({dir: "x"|"y", sign, onStart, onMove, onEnd, onReset, help, key})` (a focusable bar; pointer drag in CSS px of the editor via `rootScale`, arrow keys 16 px, double-click resets); `resizableList({height, min, max, scroll, onResize, children})` (a `max-height` box and a grip); `uiNum(p, key, dflt, lo, hi)`. A combobox option may carry `pre` (shown dimmed before the label, searched, never the value). Callers look up the live panel (`ctx.root.querySelector`) while dragging, because a redraw can replace it mid-drag.
- Timeline (`tabs/timeline.js`): `render` builds `.rw-tl-top` (`.rw-mon-col` with the persistent monitor and the transport, a `splitter`, the inspector) over a `splitter` and `.rw-tl-main`. The monitor's `m.overlay(scene, local)` sets the frame count and the caption (`captionAt`: the merge's `subtitle_cues` timing) and is called by `setPlayhead` on every frame; `nowAt` fills the inspector's "At the playhead" (`summaryBlock`). `applyVolume` = `sceneVolume × soundtrack.monitorGain`; `syncAudio` scales the tracks by `monitorGain` too. `volumeControl` changes the sound while dragging without a redraw. There is no asset bin (the Assets tab has the assets).
- Scene tab (`tabs/scene.js`): `promptTabOf(ctx, s, plan, anyMode)` is the one rule for the Prompt card's tab, which cards show (`render`) and what `previewCard` shows (every pass on Whole scene). `rowsBox(ctx, "shots"|"lines", scrollKey, rows)` wraps shot and dialogue rows (scene cards and pass panes).
- Assets tab (`tabs/assets.js`): `grid` → `tagRow`, `groupsView` / `kindsView`, `groupSection` (drop target for `application/x-rw-asset`), `assetCard`; `addGroup` (exported; the asset menu uses it), `moveGroup`, `deleteGroup`, `pickGroup`. model.js `assetGroupName` feeds every asset picker's `pre` and `tagCandidates`' labels; `assetTags` / `model.asset_tags` clean tags; `normAssetGroups` / `_norm_asset_groups` normalise both.
- Files tab (`tabs/files.js`): `filesMain(ctx, tree, pane)` puts a `splitter` (sign −1) between the tree and the preview.
- Harness: the demo project has three groups and some tags; `web-test/interact.py` `v090_checks()`.

### Speech timing, voices, seam fixes, copy and import (v0.10.0)

- `reelwright/speech.py` (numpy, imported when needed): `decode(path, ffmpeg, start, length)` (mono float32 at 16 kHz), `segments(y)` (speech-band level 300–3400 Hz every 10 ms in 25 ms Hann windows; voiced = above the 15th percentile + max(6 dB, 40 % of the way to the 97th) with most of the energy in the band; a 5-frame vote, gaps under 0.25 s closed, runs under 0.2 s dropped, runs over 1.5 s whose level hardly moves dropped; no segments when the take's loud and quiet parts are < 8 dB apart), `align(lines, segs, end)` (in-order dynamic programming: a match costs how far it moves the line, at most `WINDOW` 4 s; an unmatched line costs `MISS` 2.5 and keeps its time; a line ends where its speech ends, later segments within 0.7 s join it, before the next line), `take_segments` (cache) and `timed_lines`.
- `assemble.speech_timed(entries)`: the cut's entries with each line's `t` / `duration` from the take's speech (a take that can't be read keeps the planned times); the merge writes the .srt from it when `merge.subtitle_timing` is `"speech"`.
- Prompts: `prompt.voice_phrase(p, c)` ("with a …", empty when `describe_voices` is off or the description is empty); `shot_parts` keeps a `voiced` set per pass, so `_dialogue_sentence` writes it at the speaker's first line only. `llm.pass_voices(p, pass)` lists them in the Write prompts request; `PASS_RULES` asks for them at the first line and forbids other passes' lines and repeats; `llm.drop_foreign_lines(text, belongs)` removes them (with the sentence) in `tidy_pass`. `llm.coerce_script` reads a cast entry's `voice` / `voice_desc` / `voice_description` (characters only). `validate._voice_issues` warns about a character heard in ≥ 2 passes with nothing that fixes the voice.
- Editor:
  - `ui.kept(ctx, slot, src, make)` returns the same element for the same slot and source while it stays in `ctx.keptMedia` (≤ 800), so a redraw does not reload a picture.
  - Tabs without `onProgress` redraw on a phase, pass or take change only.
  - `section({collapse: {ctx, id, summary}})` (state in `ui.collapsed`).
  - `h(…, {detail})` sets `data-detail`, which the tooltip shows above the help text; `data-copy` is what Copy text copies.
  - `ui.copyText` (clipboard API on a secure page, else a hidden textarea and `execCommand("copy")`), `copyWithToast` (`root.__rwToast`), `copyButton`, `copyMenuItems(target, root, {explicitOnly})`; `editor.js`'s context-menu guard adds them to an element's own menu (explicit text only) or shows them alone.
- Scene tab:
  - `passes.seamFixes(plan, s, d)` → `{seam, earlier, later}` (frame times) and `seamFixTime` (the smaller move); `seamNote`, `fixSeamLines`.
  - `rewriteCard` on a pass tab calls `rw.llmPasses(project, scene_id, [k], job, instruction)` and accepts with `applyWritten`.
  - `render` leaves the rewriter out on Whole scene of a structured scene with several passes.
- Cast tab: `voiceFromTake(ctx, c)` (a `choiceDialog` of the scenes whose starred take has the character's lines) → `rw.voiceFromTake` → one undo step that adds the audio asset and sets `voice`; the Voice description field; Continuity rules → Voices.
- Timeline: `speechOf(ctx, scene)` asks `/reelwright/speech` once per take and line set (a `WeakMap` per editor) and redraws the caption when it answers; `captionAt(p, scene, local, timed)`.
- Global → Project: `projectIO` (Export: a Blob download; Copy JSON; Import: `parseProjectText` accepts a project or `{project}`, `importProject` normalises it, asks with `choiceDialog` and calls `store.replaceProject`, keeping this node's `slug` and `project_id` unless *Use <folder>* is chosen).
- Render tab: the Passes light and each take's pass lights carry `data-detail` (`driftSummary`, `DRIFT_WORDS`).
- Harness: `web-test/mock.js` serves `/reelwright/speech` (lines heard `speechShift` s late; `speechCalls`) and `/reelwright/voice_from_take` (`voiceCuts`), and records the instruction of `/llm/passes`; `web-test/interact.py` `v0100_checks()`.
