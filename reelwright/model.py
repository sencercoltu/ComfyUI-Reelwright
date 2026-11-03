"""Project schema 1: defaults, normalization and effective settings.

Kept in step with web/rw/model.js. The editor fills defaults for instant
feedback; this module is what the renderer trusts.
"""

import copy
import hashlib
import json
import re
import secrets

from . import spec
from . import soundtrack as _soundtrack  # added 2026-11-03 v0.5.0

SECTION_KEYS = ("subject_definitions", "summary", "retention_analysis",
                "detailed_description", "overall_soundscape", "non_diegetic_music")
# [OLD 2026-11-02 v0.2.2->v0.3.0] OVERRIDE_KEYS = ("seed", "steps", "sampler", "scheduler", "width", "height",
#                  "diffusion", "text_encoder", "video_vae", "audio_vae")
OVERRIDE_KEYS = ("seed", "steps", "sampler", "scheduler", "width", "height",
                 "diffusion", "text_encoder", "video_vae", "audio_vae", "quality")
TRANSITIONS = ("cut", "crossfade", "dip")  # added 2026-11-02 v0.3.0: per-scene hard-cut transition
CODE_PREFIX = {"image": "P", "video": "V", "audio": "A"}


def new_id(prefix):
    return prefix + "_" + secrets.token_hex(4)


def slugify(name):
    s = re.sub(r"[^\w\s-]", "", str(name or "").lower(), flags=re.ASCII).strip()
    s = re.sub(r"[\s-]+", "_", s).strip("_")
    return s or "untitled"


def default_global():
    return {
        "models": {
            "diffusion": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
            "weight_dtype": "default",
            "text_encoder": "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
            "clip_device": "default",
            "video_vae": "minimax_h3_video_vae_int8_convrot.safetensors",
            "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
            "latent_upscaler": "",
        },
        "loras": [],
        "output": {"aspect": "16:9", "width": 1344, "height": 768, "ref_image_size": "match"},
        "sampling": {"steps": 20, "sampler": "res_multistep", "scheduler": "simple", "seed": 104729,
                     "seed_mode": "increment", "sigma_shift": False, "shift_video": 12.0, "shift_audio": 3.0},
        "quality": "final",
        "draft": {"scale": 0.5, "steps": 8, "lora": "", "lora_strength": 1.0},
        "defaults": {"duration": 8.0, "start_mode": "last_frame", "overlap_frames": 39, "language": "English"},
        "long": {"max_pass_frames": 362, "overlap_frames": 39, "crossfade_frames": 12,
                 "seam_mode": "auto", "cut_snap_seconds": 2.0},
        "memory": {"policy": "free_cache", "encode_first": True, "group_by_lora": True},
        "continuity": {"reanchor_after": 2, "face_check": False, "face_threshold": 0.8, "on_drift": "flag"},
        # [OLD 2026-11-02 v0.1.0->v0.2.0] no switch for sending MiniMax's prompt guides
        # "llm": {"base_url": "", "model": "", "temperature": 0.4, "max_tokens": 2048, "preset": "h3_ref2va"},
        # [/OLD]
        # [OLD 2026-11-02 v0.3.1->v0.3.2] no thinking switch
        # "llm": {"base_url": "", "model": "", "temperature": 0.4, "max_tokens": 2048, "preset": "h3_ref2va",
        #         "include_guides": True},
        # [/OLD]
        # [OLD 2026-11-03 v0.4.1->v0.4.2] no limits: a fixed 180 s timeout, Import used max(Max tokens, 6000) for the whole script
        # "llm": {"base_url": "", "model": "", "temperature": 0.4, "max_tokens": 2048, "preset": "h3_ref2va",
        #         "include_guides": True, "thinking": "auto"},  # thinking: auto (model default) | off
        # [/OLD]
        "llm": {"base_url": "", "model": "", "temperature": 0.4, "max_tokens": 2048, "preset": "h3_ref2va",
                "include_guides": True, "thinking": "auto",  # thinking: auto (model default) | off
                # added 2026-11-03 v0.4.2: limits. timeout_s: no data from the server for this long ends a request;
                # max_wait_s: longest a request may take; retries: extra attempts after a timeout, a cut-off or
                # unreadable reply or a server error; context_tokens: the model's context window, 0 = ask the server
                "timeout_s": 120, "max_wait_s": 900, "retries": 2, "context_tokens": 0,
                # script import: the script is sent in parts of about this many characters (0 = all at once),
                # each part may answer with up to import_max_tokens; import_thinking: same | off;
                # import_guides: also send MiniMax's H3 guides (about 10k tokens) with every part
                "import_part_chars": 3000, "import_max_tokens": 16384, "import_thinking": "same",
                "import_guides": False},
        "merge": {"use": "starred", "missing": "skip", "hard_cut": "cut", "transition_frames": 12,
                  "audio_fade_frames": 6, "loudness": -16.0, "normalize": True,
                  "score": {"asset": "", "volume_db": -12.0, "duck": True},  # v0.5.0: moved to p["soundtrack"] on load
                  # added 2026-11-03 v0.5.0: the scenes' own sound under a soundtrack (off: only the soundtrack plays)
                  "scene_audio": {"mix": False, "volume_db": -12.0},
                  "color_match": False, "color_ref_scene": "", "codec": "h264", "crf": 16,
                  "subtitles": True, "chapters": True, "otio": True, "fcpxml": True, "bundle": False,
                  "auto_after_render": True},
    }


def default_prompt():
    return {"mode": "structured", "auto": {"subjects": True, "retention": True, "shots": True},
            "sections": {k: "" for k in SECTION_KEYS}, "raw": "", "pass_prompts": {}}


def default_scene(project=None, **patch):
    d = (project or {}).get("global", {}).get("defaults") or default_global()["defaults"]
    first = not project or not project.get("scenes")
    scene = {
        "id": new_id("s"), "title": "New scene", "duration": d["duration"], "color": "",
        "start": {"mode": "fresh" if first else d["start_mode"], "overlap_frames": d["overlap_frames"]},
        "trim": {"keep": "start", "in": 0.0},
        "refs": [], "cast": [], "shots": [], "dialogue": [],
        "prompt": default_prompt(), "overrides": {}, "lock": False, "notes": "",
        # added 2026-11-02 v0.3.0: how the cut into this scene looks; empty/None follow Global -> Merge
        "transition": {"mode": "", "frames": None, "audio_fade_frames": None},
    }
    scene.update(patch)
    return scene


def default_project(name="Untitled"):
    # [OLD 2026-11-03 v0.4.3->v0.5.0] no soundtrack
    # p = {"schema": 1, "id": new_id("p"), "name": name, "slug": slugify(name),
    #      "global": default_global(), "assets": [], "cast": [], "camera_presets": [],
    #      "scenes": [], "markers": [],
    #      "ui": {"tab": "timeline", "selected": "", "zoom": 22, "playhead": 0, "snap": True, "ripple": True}}
    # [/OLD]
    p = {"schema": 1, "id": new_id("p"), "name": name, "slug": slugify(name),
         "global": default_global(), "assets": [], "cast": [], "camera_presets": [],
         "scenes": [], "markers": [], "soundtrack": [],  # soundtrack: added 2026-11-03 v0.5.0 (see soundtrack.py)
         "ui": {"tab": "timeline", "selected": "", "zoom": 22, "playhead": 0, "snap": True, "ripple": True}}
    p["scenes"].append(default_scene(p, title="Scene 1"))
    p["ui"]["selected"] = p["scenes"][0]["id"]
    return p


def _fill(target, defaults):
    for k, v in defaults.items():
        if target.get(k) is None:
            target[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(target[k], dict):
            _fill(target[k], v)
    return target


def assign_codes(assets):
    used = {k: set() for k in CODE_PREFIX}
    for a in assets:
        if a.get("code") and a.get("kind") in used:
            used[a["kind"]].add(a["code"])
    for a in assets:
        if a.get("code") or a.get("kind") not in used:
            continue
        n = 1
        while CODE_PREFIX[a["kind"]] + str(n) in used[a["kind"]]:
            n += 1
        a["code"] = CODE_PREFIX[a["kind"]] + str(n)
        used[a["kind"]].add(a["code"])
    return assets


def normalize_project(raw):
    """Parse (if needed) and fill every missing key. Returns a new dict."""
    p = raw
    if isinstance(p, str):
        try:
            p = json.loads(p) if p.strip() else None
        except json.JSONDecodeError:
            p = None
    if not isinstance(p, dict) or not isinstance(p.get("scenes"), list):
        return default_project()
    p = copy.deepcopy(p)
    base = default_project(p.get("name") or "Untitled")
    base["scenes"] = []
    _fill(p, base)
    p["slug"] = slugify(p.get("slug") or p["name"])
    p["schema"] = 1
    lang = p["global"]["defaults"]["language"]
    for s in p["scenes"]:
        _fill(s, default_scene(p, id=s.get("id") or new_id("s")))
        _fill(s["prompt"], default_prompt())
        for r in s["refs"]:
            _fill(r, {"id": new_id("r"), "asset": "", "role": "reference", "time": 0.0,
                      "retention": "", "keep": [], "soundtrack": False})
        for x in s["shots"]:
            _fill(x, {"id": new_id("h"), "t": 0.0, "camera": "", "text": ""})
        for x in s["dialogue"]:
            _fill(x, {"id": new_id("d"), "speaker": "", "t": 0.0, "language": lang, "delivery": "", "text": ""})
        for c in s["cast"]:
            _fill(c, {"id": "", "outfit": ""})
        s["shots"].sort(key=lambda x: float(x["t"]))
        s["dialogue"].sort(key=lambda x: float(x["t"]))
    for a in p["assets"]:
        _fill(a, {"id": new_id("a"), "code": "", "kind": "image", "name": "", "file": "", "duration": 0,
                  "width": 0, "height": 0, "category": "",
                  "defaults": {"role": "reference",
                               "retention": "reference" if a.get("kind") == "audio" else "fully_preserved",
                               "keep": [], "soundtrack": False},
                  "notes": "", "description": ""})  # added 2026-11-02 v0.2.0: description feeds subject_definitions
    assign_codes(p["assets"])
    for c in p["cast"]:
        _fill(c, {"id": new_id("c"), "kind": "character", "name": "", "speaker": "", "description": "",
                  "anchors": [], "pack_sheet": True, "outfits": [], "default_outfit": "", "voice": "",
                  "language": lang, "lora": {"name": "", "strength": 0.8}})
        for o in c["outfits"]:
            _fill(o, {"id": new_id("o"), "name": "", "retention": "fully_preserved", "keep": [], "assets": []})
        # added 2026-11-03 v0.4.1: True (one sheet), False (separate pictures) or "auto" (a sheet only when the
        # pass would not fit H3's 9 pictures otherwise)
        if c["pack_sheet"] not in (True, False, "auto"):
            c["pack_sheet"] = True
    if not p["scenes"]:
        p["scenes"].append(default_scene(p, title="Scene 1"))
    # added 2026-11-03 v0.5.0: soundtrack tracks; the old merge score becomes one
    p["soundtrack"] = [t for t in p["soundtrack"] if isinstance(t, dict)]
    for t in p["soundtrack"]:
        _soundtrack.normalize_track(t)
        t["id"] = t["id"] or new_id("t")
    _soundtrack.migrate_score(p)
    return p


def project_index(p):
    """Lookup tables used everywhere."""
    return {
        "assets": {a["id"]: a for a in p["assets"]},
        "codes": {a["code"].upper(): a for a in p["assets"] if a.get("code")},
        "cast": {c["id"]: c for c in p["cast"]},
        "cast_by_name": {c["name"].strip().lower(): c for c in p["cast"] if c.get("name")},
        "scenes": {s["id"]: i for i, s in enumerate(p["scenes"])},
    }


# added 2026-11-02 v0.3.4: a cast member without its own description is described by its anchor pictures,
# so an asset's description reaches every scene the character is in
def cast_description(c, assets):
    """(text, asset_id) used for a cast member's subject line. The cast member's own description wins; otherwise
    the description of its first anchor picture that has one. asset_id is None when the text is the cast's own."""
    own = (c.get("description") or "").strip().rstrip(".")
    if own:
        return own, None
    for aid in c.get("anchors") or []:
        a = assets.get(aid)
        d = ((a or {}).get("description") or "").strip().rstrip(".")
        if a and a.get("kind") == "image" and d:
            return d, aid
    return "", None


def scene_seed(p, scene, scene_index, take_number=0):
    o = scene["overrides"]
    if o.get("seed") is not None:
        base = int(o["seed"])
    else:
        sm = p["global"]["sampling"]
        mode = sm["seed_mode"]
        if mode == "fixed":
            base = int(sm["seed"])
        elif mode == "random":
            h = hashlib.sha256((str(sm["seed"]) + scene["id"]).encode()).hexdigest()
            base = int(h[:12], 16)
        else:
            base = int(sm["seed"]) + scene_index
    return (base + take_number * 1000003) % (2 ** 63)


def effective_loras(p, scene):
    """Ordered [(name, strength)] for a scene: global stack (with per-scene strength
    overrides), scene LoRAs, draft LoRA and the identity LoRAs of its cast."""
    g = p["global"]
    ov = scene["overrides"].get("loras") or {}
    mode = ov.get("mode", "add")
    strengths = ov.get("strengths") or {}
    out = []
    if mode != "replace":
        for l in g["loras"]:
            if l.get("enabled", True) and l.get("name"):
                out.append((l["name"], float(strengths.get(l["id"], l["strength"]))))
    for l in ov.get("items") or []:
        if l.get("enabled", True) and l.get("name"):
            out.append((l["name"], float(l["strength"])))
    cast = project_index(p)["cast"]
    for sc in scene["cast"]:
        c = cast.get(sc["id"])
        if c and c["lora"].get("name"):
            out.append((c["lora"]["name"], float(c["lora"]["strength"])))
    # [OLD 2026-11-02 v0.2.2->v0.3.0] if g["quality"] == "draft" and g["draft"].get("lora"):
    if scene_quality(p, scene) == "draft" and g["draft"].get("lora"):
        out.append((g["draft"]["lora"], float(g["draft"]["lora_strength"])))
    seen = {}
    for name, strength in out:
        seen[name] = strength  # later entries win, so a scene item can retune a global LoRA
    return list(seen.items())


def scene_quality(p, scene):
    """"draft" or "final": the scene's own choice, else Global (added 2026-11-02 v0.3.0)."""
    q = (scene.get("overrides") or {}).get("quality")
    return q if q in ("draft", "final") else p["global"]["quality"]


def resolve_settings(p, scene, scene_index):
    """Everything the renderer needs for one scene, with overrides and quality applied."""
    g = p["global"]
    o = scene["overrides"]
    m = g["models"]
    s = g["sampling"]
    width = int(o.get("width") or g["output"]["width"])
    height = int(o.get("height") or g["output"]["height"])
    steps = int(o.get("steps") or s["steps"])
    quality = scene_quality(p, scene)  # [OLD 2026-11-02 v0.2.2->v0.3.0] was g["quality"] for every scene
    if quality == "draft":
        width, height = spec.snap_canvas(width * g["draft"]["scale"], height * g["draft"]["scale"])
        steps = int(g["draft"]["steps"])
    return {
        "diffusion": o.get("diffusion") or m["diffusion"],
        "weight_dtype": m["weight_dtype"],
        "text_encoder": o.get("text_encoder") or m["text_encoder"],
        "clip_device": m["clip_device"],
        "video_vae": o.get("video_vae") or m["video_vae"],
        "audio_vae": o.get("audio_vae") or m["audio_vae"],
        "width": width, "height": height,
        "ref_image_size": g["output"]["ref_image_size"],
        "steps": steps,
        "sampler": o.get("sampler") or s["sampler"],
        "scheduler": o.get("scheduler") or s["scheduler"],
        "sigma_shift": bool(s["sigma_shift"]),
        "shift_video": float(s["shift_video"]), "shift_audio": float(s["shift_audio"]),
        "seed": scene_seed(p, scene, scene_index),
        "loras": effective_loras(p, scene),
        # [OLD 2026-11-02 v0.2.2->v0.3.0] "quality": g["quality"],
        "quality": quality,
    }


# [OLD 2026-11-03 v0.4.3->v0.5.0] scenes end to end: a tail continuation repeats the end of the scene before, and a last-frame start repeats
# its last frame, so the finished cut was shorter than this and a soundtrack would drift against it
# def scene_starts(p):
#     """Timeline start of every scene (the editor lays scenes end to end)."""
#     starts, t = {}, 0.0
#     for s in p["scenes"]:
#         starts[s["id"]] = t
#         t += float(s["duration"])
#     return starts, t
# [/OLD]
def scene_overlap(scene, index):
    """Seconds at the start of a scene that repeat the end of the scene before (added 2026-11-03 v0.5.0): the tail
    clip it continues from (the same 17k+5 frames the planner uses), or the one last frame it starts from."""
    if index == 0:
        return 0.0
    mode = scene["start"]["mode"]
    if mode == "tail":
        total = max(1, spec.frames_of(max(1.0 / spec.FPS, float(scene["duration"]))))
        n = min(spec.align_frames_down(max(5, int(scene["start"]["overlap_frames"]))), spec.align_frames_down(total))
        return n / spec.FPS
    if mode == "last_frame":
        return 1.0 / spec.FPS
    return 0.0


def scene_starts(p):
    """Start of every scene in the finished cut, and its length (added 2026-11-03 v0.5.0, same as model.js
    sceneStarts). A scene's time t plays at starts[id] + t."""
    starts, t = {}, 0.0
    for i, s in enumerate(p["scenes"]):
        t = max(0.0, t - scene_overlap(s, i))
        starts[s["id"]] = t
        t += float(s["duration"])
    return starts, t
