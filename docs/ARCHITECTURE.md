# Reelwright — architecture and contracts

```
ComfyUI-Reelwright/
  __init__.py            ComfyUI entry: comfy_entrypoint() + WEB_DIRECTORY + routes
  reelwright/
    __init__.py          VERSION
    spec.py              H3 constants and frame/canvas math (pure)
    model.py             project defaults, migration, effective settings (pure)
    planner.py           scene -> passes (long/short), seams, re-based shots (pure)
    prompt.py            per-pass prompt assembly and tag numbering (pure)
    validate.py          lint rules (pure)
    cache.py             cache keys, take index, staleness (pure + file hashing)
    storage.py           folders, path containment, autosave/versions (pure + fs)
    media.py             load images/video/audio to tensors, write files (comfy)
    render.py            render run using the native H3 nodes (comfy + torch)
    merge.py             ffmpeg merge, srt/chapters/otio/fcpxml/color match (ffmpeg)
    llm.py               OpenAI-compatible client and prompt templates (aiohttp)
    scriptparts.py       cuts a long script into parts for the import (v0.4.2); imported scene length vs shots (v0.4.3) (pure)
    continuity.py        optional face-match drift check (insightface)
    routes.py            /reelwright/* HTTP routes
    profiles.py          saved Global settings in user/reelwright/profiles.json
    node.py              the V3 node
  web/
    reelwright.js        ComfyUI extension: registers the DOM widget
    rw/*.js, rw/reelwright.css
  tests/                 pytest for the pure modules and merge
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
    "loras": [ { "id": "l_1", "name": "film_grain_v2.safetensors", "strength": 0.6, "enabled": true } ],
    "output": { "aspect": "16:9", "width": 1344, "height": 768, "ref_image_size": "match" },
    "sampling": { "steps": 20, "sampler": "res_multistep", "scheduler": "simple",
                  "seed": 104729, "seed_mode": "increment",          // fixed | increment | random
                  "sigma_shift": false, "shift_video": 12.0, "shift_audio": 3.0 },
    "quality": "final",                                              // final | draft
    "draft": { "scale": 0.5, "steps": 8, "lora": "", "lora_strength": 1.0 },
    "defaults": { "duration": 8.0, "start_mode": "last_frame", "overlap_frames": 39, "language": "English" },
    "long": { "max_pass_frames": 362, "overlap_frames": 39, "crossfade_frames": 12,
              "seam_mode": "auto", "cut_snap_seconds": 2.0 },       // auto | cuts | overlap
    "memory": { "policy": "free_cache", "encode_first": true, "group_by_lora": true },  // keep | free_cache | unload_all
    "continuity": { "reanchor_after": 2, "face_check": false, "face_threshold": 0.8, "on_drift": "flag" }, // flag | retake
    "llm": { "base_url": "", "model": "", "temperature": 0.4, "max_tokens": 2048, "preset": "h3_ref2va",
             "include_guides": true,                      // v0.2.0: send MiniMax's guides when downloaded
             "thinking": "auto",                          // v0.3.2: auto | off (chat_template_kwargs enable_thinking=false)
             "timeout_s": 120, "max_wait_s": 900,         // v0.4.2: stall timeout (no data), longest request
             "retries": 2, "context_tokens": 0,           // v0.4.2: extra attempts; context window, 0 = ask GET /models
             "import_part_chars": 3000,                   // v0.4.2: script import part size, 0 = whole script
             "import_max_tokens": 16384, "import_thinking": "same", "import_guides": false },  // same | off
    "merge": { "use": "starred", "missing": "skip",                 // skip | slate | block
               "hard_cut": "cut", "transition_frames": 12,           // cut | crossfade | dip
               "audio_fade_frames": 6, "loudness": -16.0, "normalize": true,
               "score": { "asset": "", "volume_db": -12.0, "duck": true },  // v0.5.0: moved to "soundtrack" on load
               "scene_audio": { "mix": false, "volume_db": -12.0 },          // v0.5.0: the scenes' sound under the soundtrack
               "color_match": false, "color_ref_scene": "",
               "codec": "h264", "crf": 16,
               "subtitles": true, "chapters": true, "otio": true, "fcpxml": true, "bundle": false,
               "auto_after_render": true }
  },
  "assets": [
    { "id": "a_1", "code": "P1", "kind": "image",             // image | video | audio
      "name": "Mara — portrait", "file": "reelwright/harbor_lights/mara.png",   // relative to ComfyUI input dir
      "duration": 0, "width": 1024, "height": 1365, "category": "subject",
      "defaults": { "role": "reference", "retention": "fully_preserved", "keep": ["face", "hair"], "soundtrack": false },
      "notes": "",
      "description": "" }                                  // v0.2.0: the asset's subject line; read live by every scene,
                                                           //   and by a cast member without its own description (v0.3.4)
  ],
  "cast": [
    { "id": "c_1", "kind": "character",                 // character | location | prop
      "name": "Mara", "speaker": "S1", "description": "Woman, early 30s, …",   // speaker is legacy: S-IDs are per clip since v0.2.0
      "anchors": ["a_1"], "pack_sheet": true,  // true (one sheet), false (separate) or "auto" (v0.4.1: a sheet only when the pass would not fit 9 pictures)
      "outfits": [ { "id": "o_1", "name": "Navy pea coat", "retention": "fully_preserved", "keep": ["face","hair","coat"], "assets": [] } ],
      "default_outfit": "o_1",
      "voice": "a_7", "language": "English",
      "lora": { "name": "", "strength": 0.8 } }
  ],
  "camera_presets": [ { "id": "k_1", "name": "Slow push-in", "text": "slow push-in" } ],
  "scenes": [
    { "id": "s_1", "title": "Harbor at dusk", "duration": 8.0,
      "color": "",                                        // optional tint for the timeline block
      "start": { "mode": "fresh", "overlap_frames": 39 },  // fresh | last_frame | tail
      "transition": { "mode": "", "frames": null,          // fresh starts only: "" (merge default) | cut | crossfade | dip
                      "audio_fade_frames": null },         //   null = use Global → Merge
      "trim": { "keep": "start", "in": 0.0 },             // short scenes: start | middle | end | custom
      "refs": [ { "id": "r_1", "asset": "a_2", "role": "reference",   // reference | first_frame | last_frame | keyframe
                  "time": 0.0, "retention": "weak_reference", "keep": [], "soundtrack": false } ],
      "cast": [ { "id": "c_1", "outfit": "o_1" } ],
      "shots": [ { "id": "h_1", "t": 0.0, "camera": "Wide · slow push-in", "text": "The harbor at dusk…" } ],
      "dialogue": [ { "id": "d_1", "speaker": "c_1", "t": 3.5, "language": "English", "delivery": "calls out", "text": "Is anyone still out there?" } ],
      "prompt": { "mode": "structured",                   // structured | raw
                  "auto": { "subjects": true, "retention": true, "shots": true },
                  "sections": { "subject_definitions": "", "summary": "", "retention_analysis": "",
                                "detailed_description": "", "overall_soundscape": "", "non_diegetic_music": "" },
                  "raw": "",
                  "pass_prompts": {} },                     // long scenes: {"1": "...", "2": "..."} overrides per pass
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
  "ui": { "tab": "timeline", "selected": "s_1", "zoom": 22, "playhead": 0.0, "snap": true, "ripple": true }
}
```

Ids are short random strings with a type prefix. Missing keys are filled in by
`model.normalize_project()`, which runs in both Python and JS (`rw/model.js`
mirrors the defaults).

## HTTP routes (all JSON unless noted)

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/reelwright/info` | – | `{version, ffmpeg, insightface, insightface_error, h3_nodes}`; `insightface_error` (v0.4.1) is why face checks could not load or run, `""` otherwise |
| GET | `/reelwright/models` | – | `{diffusion_models[], text_encoders[], vae[], loras[], latent_upscale_models[], samplers[], schedulers[]}` |
| POST | `/reelwright/plan` | `{project}` | `{scenes: {<scene_id>: {passes[], status, key, starred, takes[], issues[], prompts[]}}, issues[], timeline: {starts:{id:t}, total}}` |
| POST | `/reelwright/upload` | multipart `file`, `slug` | `{asset}` with kind, file, duration, width, height |
| GET | `/reelwright/takes?slug=` | – | `{scenes: {<id>: {starred, takes:[{id, key, created, quality, seconds, frames, face, files:{video, first, last, tail}}]}}}` |
| POST | `/reelwright/takes/star` | `{slug, scene_id, take_id}` | `{ok}` |
| POST | `/reelwright/takes/delete` | `{slug, scene_id, take_id}` | `{ok}` |
| POST | `/reelwright/merge` | `{project}` | `{ok, files:{video, srt, otio, fcpxml, chapters, bundle}, duration}` |
| POST | `/reelwright/autosave` | `{project}` | `{ok, version}` |
| GET | `/reelwright/versions?slug=` | – | `{versions:[{name, created, size}]}` |
| GET | `/reelwright/version?slug=&name=` | – | `{project}` |
| POST | `/reelwright/versions/delete` | `{slug, names[]}` or `{slug, all: true}` | `{removed, versions}`; only `project_YYYYmmdd_HHMMSS.json` files in `versions/`, never `project.json` |
| GET | `/reelwright/llm/settings` | – | `{base_url, model, has_key, guides:{name:{bytes, fetched}}, guide_urls}` |
| POST | `/reelwright/llm/settings` | `{base_url?, model?, api_key?}` | `{ok}` |
| POST | `/reelwright/llm/models` | `{base_url?}` | `{models[]}` |
| POST | `/reelwright/llm/test` | `{project?}` | `{ok, ms, model, reply, base_url, thinking, note}`; 20 s limit, readable error when the server can't be reached; `thinking` is true when the reply carried reasoning |
| POST | `/reelwright/llm/rewrite` | `{project, scene_id, instruction, job?}` | `{sections?, raw?, warnings[]}` or `{cancelled: true}` |
| POST | `/reelwright/llm/split` | `{project, scene_id, job?}` | `{pass_prompts:{n: text}}` or `{cancelled: true}` |
| POST | `/reelwright/llm/script` | `{project, script, part?, parts?, notes?, known_cast?[], job?, can_split?}` | `{scenes[], cast[], tokens, ms, attempts, budget, input, context}` or `{cancelled: true}`; v0.4.3: shots carry `duration`, and `scriptparts.fit_scene` makes each scene's length fit its shots and dialogue (a changed scene gets `fit_note`); v0.4.2: `script` is one part, `notes` go with every part, `known_cast` keeps names; with `can_split` a cut-off answer is not retried (the editor splits the part) |
| POST | `/reelwright/llm/script/parts` | `{script, part_chars}` | v0.4.2, `scriptparts.split_script`: `{notes, parts:[[block…]], chars, blocks}`; a part's text is its blocks joined by newlines |
| POST | `/reelwright/llm/cancel` | `{job}` | v0.4.2: `{ok, cancelled}`; stops the running rewrite / split / script request with that job id, which then answers `{cancelled: true}` |
| POST | `/reelwright/promote_frame` | `{slug, scene_id, take_id, which: first\|last\|time, t?}` | `{asset}` |
| POST | `/reelwright/cast/export` | `{project, cast_id}` | `{folder, files}` |
| POST | `/reelwright/continuity/check` | `{project, scene_id}` | `{scores:{cast_id: value}, available}` |
| POST | `/reelwright/llm/guides` | `{}` | `{guides}`: downloads MiniMax's `ref-en.txt` and `base-en.txt` into `user/reelwright/guides/` |
| POST | `/reelwright/llm/describe` | `{project, asset_ids[≤4], prompt}` | `{text, ms, model, note}`; pictures as JPEG, videos as 3 frames, OpenAI `image_url` parts; budget max(Max tokens, 6000), or 600 with thinking off; one retry with thinking off when a thinking model runs out of tokens |
| GET | `/reelwright/files?root=input\|output&q=&kind=&limit=` | – | `{files:[{rel, kind, bytes, mtime}], total, truncated}`, newest first |
| POST | `/reelwright/import` | `{slug, root, rel}` | `{asset}`; output files are hard-linked or copied into `input/reelwright/<slug>/from_output/` |
| GET | `/reelwright/profiles` | – | `{profiles:[{id, name, created, updated, global}], default}` |
| POST | `/reelwright/profiles/save` | `{name, global, id?, default?}` | `{profile, profiles, default}`; with `id` it replaces that profile |
| POST | `/reelwright/profiles/delete` | `{id}` | `{profiles, default}` |
| POST | `/reelwright/profiles/default` | `{id}` (`""` clears) | `{profiles, default}` |
| GET | `/reelwright/storage?current=<slug>` | – | v0.4.0, `files.scan`: `{projects:[node], size, current}`; node = `{id, label, kind: project\|group\|scene\|take\|passes\|cut\|version\|asset\|dir\|file, size, count, mtime, note, flags[], del, why?, view?, type?, children[]}`. Ids: `p:<slug>` (whole project), `o:<output-rel>`, `i:<input-rel>`, `cut:<slug>:<stem>` (one merged cut and its side files) |
| GET | `/reelwright/sheet?files=<json list of input-relative paths>&cell=` | – | v0.4.1, JPEG of the anchor sheet `media.sheet_image` builds for those files (≤64, each checked with `safe_join` against the input folder) |
| GET | `/reelwright/waveform?file=<input-relative path>&per_second=` | – | v0.5.0, `merge.waveform_peaks`: binary u8 peak levels (mono, 0–255), headers `X-Per-Second`, `X-Duration`; 10–200 per second, memoised by path, size and mtime |
| POST | `/reelwright/storage/delete` | `{ids[], current}` | `{removed, freed, errors:[{id, error}], deleted[]}`; ids inside another selected id go with it; takes go through `ProjectStore.delete_take`; refuses the open project as a whole, any `project.json`, the open project's `wired.json`, `scenes/*/index.json` and anything outside `reelwright/<slug>/` |

File previews use ComfyUI's own `/view?filename=&subfolder=&type=output|input`.

## Websocket events (`api.addEventListener(name, e => e.detail)`)

| Event | Detail |
|---|---|
| `reelwright.progress` | `{slug, scene_id, pass: 1, passes: 3, step, steps, phase: "encode"\|"sample"\|"decode"\|"save"\|"cached"\|"done"\|"error", message}` |
| `reelwright.run` | `{slug, phase: "start"\|"end", targets: [scene_id], reused: [scene_id], error?}` |
| `reelwright.preview` | `{slug, scene_id, pass, passes, step, steps, image: "data:image/jpeg;base64,…"}` every sampler step, at most one per 0.25 s, always the last step (v0.3.5; v0.3.8 was one a second). The editor turns `image` into a `blob:` URL (`web/rw/preview.js`) before showing it. Made with ComfyUI's own previewer under any extension wrapper (`render.stock_previewer`, v0.3.9; VideoHelperSuite's animated previews wrap it). Replaces ComfyUI's own node preview |
| `reelwright.merge` | `{slug, phase: "start"\|"progress"\|"end", percent?, files?, error?}` |
| `reelwright.llm` | v0.4.2: `{job, phase: "waiting"\|"thinking"\|"writing"\|"done"\|"retry", tokens, reasoning, chars, elapsed, budget, input, context, attempt, attempts, note?, part?, parts?}` about twice a second while an LLM request with a `job` id runs (`llm.chat` streams the answer). `tokens` counts streamed chunks, about one token each; `input` is the estimated prompt size |

## Running a render

The editor writes `{"action": "pending"|"selected"|"from"|"all"|"take", "scenes": [..], "token": <time>}`
into the hidden `run_request` widget, then calls `app.queuePrompt(0, 1)`.
`fingerprint_inputs` hashes project + run_request, so each click re-runs the
node and an unchanged queue does not. After queueing, the editor resets the
request to `{"action": "pending"}`.

## Disk layout

```
output/reelwright/<slug>/
  project.json                       latest autosave
  versions/project_YYYYmmdd_HHMMSS.json
  scenes/<scene_id>/index.json       {starred, takes:[...]}
  scenes/<scene_id>/takes/<take_id>/<slug>_<NN>_<title>_<take_id>.mp4 first.png last.png tail.mp4 meta.json   (video.mp4 before v0.2.0)
  scenes/<scene_id>/takes/<take_id>/passes/p1.mp4 …
  cuts/<slug>_cut_vN.mp4 .srt .otio .fcpxml .chapters.txt .zip
  soundtrack/<hash>.wav              v0.5.0: the part of the soundtrack a pass is sent (48 kHz stereo), made once per content
  cast/<cast_id>/training/…
input/reelwright/<slug>/             uploaded assets (from_output/: files picked from ComfyUI's output)
user/reelwright/llm.json     LLM base URL, model, API key (never in workflows)
user/reelwright/guides/      MiniMax's H3 prompt guides, downloaded on request
user/reelwright/profiles.json  saved Global profiles and the default for new nodes
```

Every path that comes from the project or a request goes through
`storage.safe_join`, which refuses anything outside its root.

## Editor ↔ backend details

- The editor hides the `project` and `run_request` widgets. It attaches a non-serialized DOM widget named `reelwright_editor`.
- Queueing runs only this node: `app.queuePrompt(0, 1, [String(node.id)])`. **Stop** calls `api.interrupt()`.
- `/plan` scene status is one of `cached | stale | missing | locked | error`. The editor adds `queued` and live progress from `reelwright.progress`.
- Take and merge file paths are relative to the output directory. Asset `file` paths are relative to the input directory. Both are previewed through `/view`.
- `scene.prompt.pass_prompts` is keyed by 1-based pass numbers as strings. `scene.overrides.loras.strengths` is keyed by global LoRA id. `scene.trim.in` is seconds inside the generated pass.
- When a render runs, the node writes `wired.json` (which inputs are wired) into the project folder. `/plan` reads it, so its cache keys match the renderer's.
