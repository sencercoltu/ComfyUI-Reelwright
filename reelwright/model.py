"""Project schema 1: defaults, normalization and effective settings.

Kept in step with web/rw/model.js. The editor fills defaults for instant
feedback; this module is what the renderer trusts.
"""

import copy
import hashlib
import json
import re
import secrets
import unicodedata  # added 2026-11-03 v0.6.0: slugify transliterates accents (NFKD)

from . import spec
from . import soundtrack as _soundtrack  # added 2026-11-03 v0.5.0

SECTION_KEYS = ("subject_definitions", "summary", "retention_analysis",
                "detailed_description", "overall_soundscape", "non_diegetic_music")
# [OLD 2026-11-02 v0.2.2->v0.3.0] OVERRIDE_KEYS = ("seed", "steps", "sampler", "scheduler", "width", "height",
#                  "diffusion", "text_encoder", "video_vae", "audio_vae")
OVERRIDE_KEYS = ("seed", "steps", "sampler", "scheduler", "width", "height",
                 "diffusion", "text_encoder", "video_vae", "audio_vae", "quality")
TRANSITIONS = ("cut", "crossfade", "dip")  # added 2026-11-02 v0.3.0: per-scene hard-cut transition
# added 2026-11-05 v0.7.0: scene.merge, how a scene sits in the cut (model.js has the same values). TRANSITIONS stays
# for the deprecated scene.transition (read once, by the migration in _norm_merge)
MERGE_TRANSITIONS = ("cut", "crossfade", "dip", "wipe", "slide", "circle", "dissolve", "pixelize", "radial", "zoom")
MERGE_DIRECTIONS = ("left", "right", "up", "down")
COLOR_MATCH_MODES = ("off", "previous", "scene")
MERGE_MAX_FRAMES = 14400  # frame counts in scene.merge: 0 .. 600 s
COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")  # "#rrggbb" (fullmatch)
CODE_PREFIX = {"image": "P", "video": "V", "audio": "A"}
# added 2026-11-03 v0.6.0: what normalize_project enforces (model.js has the same values)
MIN_SCENE_SECONDS = 1.0 / spec.FPS
MAX_SCENE_SECONDS = 600.0
ASSET_KINDS = ("image", "video", "audio")
CAST_KINDS = ("character", "location", "prop")
TRIM_KEEPS = ("start", "middle", "end", "custom")
PROMPT_MODES = ("structured", "raw")
SLUG_MAX = 64
SLUG_RE = re.compile(r"^[a-z0-9_][a-z0-9_-]{0,63}$")  # same as storage.SLUG_RE
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # same as storage.ID_RE: scene ids are folder names
SEED_N_LIMIT = 2 ** 31
DEFAULT_CAMERA = (("Slow push-in", "slow push-in toward the subject"),
                  ("Locked-off", "static locked-off camera"),
                  ("Crane up", "slow crane up revealing the scene"),
                  ("Handheld pan \u2192", "handheld camera panning right"),
                  ("Rack focus", "rack focus from foreground to background"),
                  ("Macro", "macro close-up, shallow depth of field"))


def new_id(prefix):
    return prefix + "_" + secrets.token_hex(4)


# [OLD 2026-11-03 v0.5.1->v0.6.0] no length cap (a long name broke every path), accents dropped whole ("Ömer" -> "mer"),
# names without ASCII letters gave odd folders, and model.js slugified differently
# def slugify(name):
#     s = re.sub(r"[^\w\s-]", "", str(name or "").lower(), flags=re.ASCII).strip()
#     s = re.sub(r"[\s-]+", "_", s).strip("_")
#     return s or "untitled"
# [/OLD]
def slugify(name):
    """Folder name for a project name: lower-case ASCII letters, digits and _, at most 64 characters (storage.SLUG_RE).
    Accents are transliterated ("Ömer" -> "omer"); a name without any ASCII letter gives "untitled". Same as
    model.js slugify."""
    s = unicodedata.normalize("NFKD", spec.text(name)).lower()
    s = re.sub(r"[^a-z0-9_ \t\n\r\f\v-]", "", s).strip(" \t\n\r\f\v")
    s = re.sub(r"[ \t\n\r\f\v-]+", "_", s).strip("_")
    s = s[:SLUG_MAX].strip("_")
    return s if re.search(r"[a-z]", s) else "untitled"


def project_slug(p):
    """The project's folder (added 2026-11-03 v0.6.0): its slug when that is a valid folder name (kept as typed, so
    "untitled-x7k2" stays), else slugify(slug or name)."""
    s = spec.text(p.get("slug"))
    return s if SLUG_RE.fullmatch(s) else slugify(s or p.get("name"))  # fullmatch: re's $ allows a trailing \n


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
        # [OLD 2026-11-05 v0.6.1->v0.7.0] no name_continuation switch
        # "continuity": {"reanchor_after": 2, "face_check": False, "face_threshold": 0.8, "on_drift": "flag"},
        # [/OLD]
        # added 2026-11-05 v0.7.0: name_continuation: the frame or clip a continuing scene (or a pass after an overlap
        # seam) starts from is also sent as reference <Picture 1> / <Video 1> and named in the prompt; False: it is
        # only anchored (MiniMaxH3AddGuide), as in v0.6.1 (see pass_continuation)
        "continuity": {"reanchor_after": 2, "face_check": False, "face_threshold": 0.8, "on_drift": "flag",
                       "name_continuation": True},
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


def default_merge():
    """added 2026-11-05 v0.7.0: scene.merge of a new scene, how it sits in the cut (assemble.cut_plan reads it).
    transition: how a fresh start joins the scene before (MERGE_TRANSITIONS), direction for wipe / slide, frames its
    length, color the dip colour; audio_frames: the sound's fade out / in at a cut; fade_in / fade_out: the picture
    from / to a colour at the scene's first / last frame; audio_fade_in / _out (frames); volume_db and mute: the
    scene's own sound; color_match: off | previous | scene (color_ref: that scene's id); brightness, contrast,
    saturation: ffmpeg eq. model.js defaultMerge is the same."""
    return {"transition": "cut", "direction": "left", "frames": 12, "color": "#000000", "audio_frames": 6,
            "fade_in": {"frames": 0, "color": "#000000"}, "fade_out": {"frames": 0, "color": "#000000"},
            "audio_fade_in": 0, "audio_fade_out": 0, "volume_db": 0.0, "mute": False,
            "color_match": "off", "color_ref": "", "brightness": 0.0, "contrast": 1.0, "saturation": 1.0}


# [OLD 2026-11-03 v0.5.1->v0.6.0] no seed_n; a malformed project (global not a dict) crashed here
# def default_scene(project=None, **patch):
#     d = (project or {}).get("global", {}).get("defaults") or default_global()["defaults"]
#     first = not project or not project.get("scenes")
# [/OLD]
def default_scene(project=None, **patch):
    project = project if isinstance(project, dict) else {}
    g = project.get("global")
    d = dict(default_global()["defaults"])
    if isinstance(g, dict) and isinstance(g.get("defaults"), dict):
        d.update(g["defaults"])
    first = not project.get("scenes")
    scene = {
        "id": new_id("s"), "title": "New scene", "duration": d["duration"], "color": "",
        "start": {"mode": "fresh" if first else d["start_mode"], "overlap_frames": d["overlap_frames"]},
        "trim": {"keep": "start", "in": 0.0},
        "refs": [], "cast": [], "shots": [], "dialogue": [],
        "prompt": default_prompt(), "overrides": {}, "lock": False, "notes": "",
        # added 2026-11-02 v0.3.0: how the cut into this scene looks; empty/None follow Global -> Merge
        "transition": {"mode": "", "frames": None, "audio_fade_frames": None},
        # added 2026-11-03 v0.6.0: the scene's number in "+1 per scene" seed mode, fixed at creation
        "seed_n": next_seed_n(project),
        # added 2026-11-05 v0.7.0: how the scene sits in the cut (replaces "transition" and Global -> Merge's
        # transition and colour-match settings)
        "merge": default_merge(),
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
    # [OLD 2026-11-03 v0.5.1->v0.6.0] no project_id, no camera presets (model.js had them)
    # p = {"schema": 1, "id": new_id("p"), "name": name, "slug": slugify(name),
    #      "global": default_global(), "assets": [], "cast": [], "camera_presets": [],
    #      "scenes": [], "markers": [], "soundtrack": [],  # soundtrack: added 2026-11-03 v0.5.0 (see soundtrack.py)
    #      "ui": {"tab": "timeline", "selected": "", "zoom": 22, "playhead": 0, "snap": True, "ripple": True}}
    # [/OLD]
    # project_id: added 2026-11-03 v0.6.0. Only the editor creates one (newId), so the backend leaves it ""
    p = {"schema": 1, "id": new_id("p"), "project_id": "", "name": name, "slug": slugify(name),
         "global": default_global(), "assets": [], "cast": [], "camera_presets": default_camera_presets(),
         "scenes": [], "markers": [], "soundtrack": [],  # soundtrack: added 2026-11-03 v0.5.0 (see soundtrack.py)
         "ui": {"tab": "timeline", "selected": "", "zoom": 22, "playhead": 0, "snap": True, "ripple": True}}
    p["scenes"].append(default_scene(p, title="Scene 1"))
    p["ui"]["selected"] = p["scenes"][0]["id"]
    return p


def default_camera_presets():
    """Camera moves every new project starts with (added 2026-11-03 v0.6.0, as model.js always had)."""
    return [{"id": new_id("k"), "name": n, "text": t} for n, t in DEFAULT_CAMERA]


def _fill(target, defaults):
    for k, v in defaults.items():
        if target.get(k) is None:
            target[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(target[k], dict):
            _fill(target[k], v)
    return target


# [OLD 2026-11-03 v0.5.1->v0.6.0] codes were unique per kind only, but tags look codes up across every kind, ignoring case
# def assign_codes(assets):
#     used = {k: set() for k in CODE_PREFIX}
#     for a in assets:
#         if a.get("code") and a.get("kind") in used:
#             used[a["kind"]].add(a["code"])
#     for a in assets:
#         if a.get("code") or a.get("kind") not in used:
#             continue
#         n = 1
#         while CODE_PREFIX[a["kind"]] + str(n) in used[a["kind"]]:
#             n += 1
#         a["code"] = CODE_PREFIX[a["kind"]] + str(n)
#         used[a["kind"]].add(a["code"])
#     return assets
# [/OLD]
def assign_codes(assets):
    """Give every asset without a code the next free P/V/A number. Codes are unique across kinds, ignoring case."""
    used = {spec.text(a.get("code")).upper() for a in assets if a.get("code")}
    for a in assets:
        if a.get("code") or not isinstance(a.get("kind"), str) or a["kind"] not in CODE_PREFIX:
            continue
        n = 1
        while (CODE_PREFIX[a["kind"]] + str(n)).upper() in used:
            n += 1
        a["code"] = CODE_PREFIX[a["kind"]] + str(n)
        used.add(a["code"].upper())
    return assets


# [OLD 2026-11-03 v0.5.1->v0.6.0] crashed on malformed JSON (scenes:[null], global:"x", refs:{}, prompt:"text",
# soundtrack:5), let cast.name:5 / start:"tail" / NaN durations through to crash analyze, kept duplicate ids and codes,
# and differed from model.js (no sorting there, other slug and defaults)
# def normalize_project(raw):
#     """Parse (if needed) and fill every missing key. Returns a new dict."""
#     p = raw
#     if isinstance(p, str):
#         try:
#             p = json.loads(p) if p.strip() else None
#         except json.JSONDecodeError:
#             p = None
#     if not isinstance(p, dict) or not isinstance(p.get("scenes"), list):
#         return default_project()
#     p = copy.deepcopy(p)
#     base = default_project(p.get("name") or "Untitled")
#     base["scenes"] = []
#     _fill(p, base)
#     p["slug"] = slugify(p.get("slug") or p["name"])
#     p["schema"] = 1
#     lang = p["global"]["defaults"]["language"]
#     for s in p["scenes"]:
#         _fill(s, default_scene(p, id=s.get("id") or new_id("s")))
#         _fill(s["prompt"], default_prompt())
#         for r in s["refs"]:
#             _fill(r, {"id": new_id("r"), "asset": "", "role": "reference", "time": 0.0,
#                       "retention": "", "keep": [], "soundtrack": False})
#         for x in s["shots"]:
#             _fill(x, {"id": new_id("h"), "t": 0.0, "camera": "", "text": ""})
#         for x in s["dialogue"]:
#             _fill(x, {"id": new_id("d"), "speaker": "", "t": 0.0, "language": lang, "delivery": "", "text": ""})
#         for c in s["cast"]:
#             _fill(c, {"id": "", "outfit": ""})
#         s["shots"].sort(key=lambda x: float(x["t"]))
#         s["dialogue"].sort(key=lambda x: float(x["t"]))
#     for a in p["assets"]:
#         _fill(a, {"id": new_id("a"), "code": "", "kind": "image", "name": "", "file": "", "duration": 0,
#                   "width": 0, "height": 0, "category": "",
#                   "defaults": {"role": "reference",
#                                "retention": "reference" if a.get("kind") == "audio" else "fully_preserved",
#                                "keep": [], "soundtrack": False},
#                   "notes": "", "description": ""})  # added 2026-11-02 v0.2.0: description feeds subject_definitions
#     assign_codes(p["assets"])
#     for c in p["cast"]:
#         _fill(c, {"id": new_id("c"), "kind": "character", "name": "", "speaker": "", "description": "",
#                   "anchors": [], "pack_sheet": True, "outfits": [], "default_outfit": "", "voice": "",
#                   "language": lang, "lora": {"name": "", "strength": 0.8}})
#         for o in c["outfits"]:
#             _fill(o, {"id": new_id("o"), "name": "", "retention": "fully_preserved", "keep": [], "assets": []})
#         # added 2026-11-03 v0.4.1: True (one sheet), False (separate pictures) or "auto" (a sheet only when the
#         # pass would not fit H3's 9 pictures otherwise)
#         if c["pack_sheet"] not in (True, False, "auto"):
#             c["pack_sheet"] = True
#     if not p["scenes"]:
#         p["scenes"].append(default_scene(p, title="Scene 1"))
#     # added 2026-11-03 v0.5.0: soundtrack tracks; the old merge score becomes one
#     p["soundtrack"] = [t for t in p["soundtrack"] if isinstance(t, dict)]
#     for t in p["soundtrack"]:
#         _soundtrack.normalize_track(t)
#         t["id"] = t["id"] or new_id("t")
#     _soundtrack.migrate_score(p)
#     return p
# [/OLD]
# added 2026-11-03 v0.6.0: the hardened normaliser. model.js normalizeProject does exactly the same (tests/
# test_model_parity.py runs both on the same JSON); the one difference is project_id, which only the editor creates.
def normalize_project(raw):
    """Parse (if needed), repair and fill every missing key. Returns a new dict; never raises on bad input.

    Values of the wrong type become their default (numbers may be given as text), lists keep only their objects,
    shots and dialogue are sorted by time, scene lengths are clamped to 1/24 .. 600 s, duplicate scene / ref / shot /
    line / track ids get a suffix (_2, _3 ...), duplicate asset codes are re-assigned, every scene gets a seed_n."""
    p = raw
    if isinstance(p, bytes):
        p = p.decode("utf-8", "replace")
    if isinstance(p, str):
        try:
            p = json.loads(p, parse_constant=_no_constant) if p.strip() else None
        except ValueError:
            p = None
    if not isinstance(p, dict) or not isinstance(p.get("scenes"), list):
        return default_project()
    p = copy.deepcopy(p)
    p["schema"] = 1
    p["id"] = spec.text(p.get("id")) or new_id("p")
    p["project_id"] = spec.text(p.get("project_id"))
    p["name"] = "Untitled" if p.get("name") is None else spec.text(p["name"], "Untitled")
    p["slug"] = project_slug(p)
    g = p["global"] = normalize_global(p.get("global"))
    lang = g["defaults"]["language"]

    assets = p["assets"] = _objects(p.get("assets"))
    seen_codes = set()
    for a in assets:
        _norm_asset(a)
        code = a["code"].upper()
        if code in seen_codes:
            a["code"] = ""  # a duplicate gets the next free code below
        elif code:
            seen_codes.add(code)
    assign_codes(assets)

    p["cast"] = _objects(p.get("cast"))
    for c in p["cast"]:
        _norm_cast(c, lang)

    used = set()
    p["scenes"] = _objects(p["scenes"])
    for s in p["scenes"]:
        _norm_scene(s, g["defaults"], lang, used)
    if not p["scenes"]:
        p["scenes"].append(default_scene(p, title="Scene 1"))
    _repair_seed_ns(p["scenes"])
    # added 2026-11-05 v0.7.0: scene.merge; a scene without one gets it from its v0.6 transition and Global -> Merge
    scene_ids = {s["id"] for s in p["scenes"]}
    for s in p["scenes"]:
        _norm_merge(s, g["merge"], p["scenes"][0]["id"], scene_ids)

    p["markers"] = _objects(p.get("markers"))
    for m in p["markers"]:
        m["id"] = spec.text(m.get("id")) or new_id("m")
        m["t"] = spec.num(m.get("t"), 0.0)
        _text_field(m, "text", "")
        _text_field(m, "color", "amber")
    cams = p.get("camera_presets")
    p["camera_presets"] = _objects(cams) if isinstance(cams, list) else default_camera_presets()
    for k in p["camera_presets"]:
        k["id"] = spec.text(k.get("id")) or new_id("k")
        _text_field(k, "name", "")
        _text_field(k, "text", "")

    # v0.5.0 soundtrack tracks; the old merge score becomes one
    p["soundtrack"] = _objects(p.get("soundtrack"))
    for t in p["soundtrack"]:
        _soundtrack.normalize_track(t)
    _soundtrack.migrate_score(p)
    used = set()
    for t in p["soundtrack"]:
        t["id"] = _unique_id(t["id"], "t", used)

    ui = p["ui"] = p["ui"] if isinstance(p.get("ui"), dict) else {}
    _text_field(ui, "tab", "timeline")
    _text_field(ui, "selected", "")
    ui["zoom"] = spec.num(ui.get("zoom"), 22)
    ui["playhead"] = spec.num(ui.get("playhead"), 0)
    ui["snap"] = spec.flag(ui.get("snap"), True)
    ui["ripple"] = spec.flag(ui.get("ripple"), True)
    if not any(s["id"] == ui["selected"] for s in p["scenes"]):
        ui["selected"] = p["scenes"][0]["id"]
    return p


def _no_constant(name):
    raise ValueError("JSON has no " + name)  # NaN / Infinity: JSON.parse rejects them, so Python does too


def _objects(v):
    """The dict items of a list (anything else gives [])."""
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _texts(v):
    """The strings (and numbers, as text) of a list."""
    return [spec.text(x) for x in v if spec.text(x, None) is not None] if isinstance(v, list) else []


def _text_field(o, key, default):
    o[key] = default if o.get(key) is None else spec.text(o[key], default)


def _unique_id(v, prefix, used, pattern=None):
    """v when it is a free id; a taken one gets _2, _3 ...; a missing one a new id. With `pattern`, characters it
    does not allow become "_" (scene ids are folder names)."""
    s = spec.text(v)
    if pattern is not None and s and not pattern.fullmatch(s):
        s = re.sub(r"[^A-Za-z0-9_-]", "_", s)[:64]
    if not s:
        s = new_id(prefix)
        while s in used:
            s = new_id(prefix)
    elif s in used:
        base, n = s[:56], 2
        while "{}_{}".format(base, n) in used:
            n += 1
        s = "{}_{}".format(base, n)
    used.add(s)
    return s


def _like(v, d):
    """v in the shape of the default d: dicts key by key (keys d lacks are kept), lists must be lists, numbers,
    booleans and strings are coerced (spec.num / flag / text), a None default takes anything."""
    if isinstance(d, dict):
        out = v if isinstance(v, dict) else {}
        for k, dv in d.items():
            out[k] = _like(out.get(k), dv)
        return out
    if isinstance(d, list):
        return v if isinstance(v, list) else copy.deepcopy(d)
    if isinstance(d, bool):
        return spec.flag(v, d)
    if isinstance(d, (int, float)):
        return spec.num(v, d)
    if isinstance(d, str):
        return d if v is None else spec.text(v, d)
    return v


def normalize_global(g):
    """Global settings (a project's or a profile's) completed with today's defaults and coerced to their types
    (added 2026-11-03 v0.6.0; model.js normalizeGlobal does the same)."""
    g = _like(copy.deepcopy(g) if isinstance(g, dict) else {}, default_global())
    d = g["defaults"]
    if d["start_mode"] not in spec.START_MODES:
        d["start_mode"] = "last_frame"
    d["duration"] = min(MAX_SCENE_SECONDS, max(MIN_SCENE_SECONDS, d["duration"]))
    d["overlap_frames"] = max(0, int(d["overlap_frames"]))
    g["continuity"]["reanchor_after"] = max(0, int(g["continuity"]["reanchor_after"]))
    g["loras"] = _objects(g["loras"])
    for l in g["loras"]:
        _norm_lora(l)
    return g


def _norm_lora(l):
    l["id"] = spec.text(l.get("id")) or new_id("l")
    _text_field(l, "name", "")
    l["strength"] = spec.num(l.get("strength"), 1.0)
    l["enabled"] = spec.flag(l.get("enabled"), True)


def _norm_asset(a):
    a["kind"] = a["kind"] if a.get("kind") in ASSET_KINDS else "image"
    a["id"] = spec.text(a.get("id")) or new_id("a")
    for k in ("code", "name", "file", "category", "notes", "description"):  # description: v0.2.0, feeds subject lines
        _text_field(a, k, "")
    for k in ("duration", "width", "height"):
        a[k] = max(0, spec.num(a.get(k), 0))
    df = a["defaults"] = a["defaults"] if isinstance(a.get("defaults"), dict) else {}
    df["role"] = df["role"] if df.get("role") in spec.ROLES else "reference"
    _text_field(df, "retention", "reference" if a["kind"] == "audio" else "fully_preserved")
    df["keep"] = _texts(df.get("keep"))
    df["soundtrack"] = spec.flag(df.get("soundtrack"), False)


def _norm_cast(c, lang):
    c["id"] = spec.text(c.get("id")) or new_id("c")
    c["kind"] = c["kind"] if c.get("kind") in CAST_KINDS else "character"
    for k in ("name", "speaker", "description", "default_outfit", "voice"):
        _text_field(c, k, "")
    _text_field(c, "language", lang)
    c["anchors"] = _texts(c.get("anchors"))
    # v0.4.1: True (one sheet), False (separate pictures) or "auto" (a sheet only when the pass would not fit H3's 9
    # pictures otherwise)
    if not (isinstance(c.get("pack_sheet"), bool) or c.get("pack_sheet") == "auto"):
        c["pack_sheet"] = True
    c["outfits"] = _objects(c.get("outfits"))
    for o in c["outfits"]:
        o["id"] = spec.text(o.get("id")) or new_id("o")
        _text_field(o, "name", "")
        _text_field(o, "retention", "fully_preserved")
        o["keep"] = _texts(o.get("keep"))
        o["assets"] = _texts(o.get("assets"))
    lora = c["lora"] = c["lora"] if isinstance(c.get("lora"), dict) else {}
    _text_field(lora, "name", "")
    lora["strength"] = spec.num(lora.get("strength"), 0.8)


def _blank(s):
    return not re.search(r"[^ \t\n\r\f\v]", s)


def _norm_scene(s, d, lang, used_ids):
    """One scene in place. d: Global -> New-scene defaults; used_ids: scene ids taken so far."""
    s["id"] = _unique_id(s.get("id"), "s", used_ids, ID_RE)
    _text_field(s, "title", "New scene")
    s["duration"] = min(MAX_SCENE_SECONDS, max(MIN_SCENE_SECONDS, spec.num(s.get("duration"), d["duration"])))
    _text_field(s, "color", "")
    st = s.get("start")
    st = {"mode": st} if isinstance(st, str) else st if isinstance(st, dict) else {}
    st["mode"] = st["mode"] if st.get("mode") in spec.START_MODES else d["start_mode"]
    st["overlap_frames"] = max(0, int(spec.num(st.get("overlap_frames"), d["overlap_frames"])))
    s["start"] = st
    tr = s["trim"] = s["trim"] if isinstance(s.get("trim"), dict) else {}
    tr["keep"] = tr["keep"] if tr.get("keep") in TRIM_KEEPS else "start"
    tr["in"] = max(0.0, spec.num(tr.get("in"), 0.0))

    used = set()
    s["refs"] = _objects(s.get("refs"))
    for r in s["refs"]:
        r["id"] = _unique_id(r.get("id"), "r", used)
        _text_field(r, "asset", "")
        r["role"] = r["role"] if r.get("role") in spec.ROLES else "reference"
        r["time"] = spec.num(r.get("time"), 0.0)
        _text_field(r, "retention", "")
        r["keep"] = _texts(r.get("keep"))
        r["soundtrack"] = spec.flag(r.get("soundtrack"), False)
    cast = []
    for e in s.get("cast") if isinstance(s.get("cast"), list) else []:
        e = {"id": e, "outfit": ""} if isinstance(e, str) else e
        if isinstance(e, dict):
            _text_field(e, "id", "")
            _text_field(e, "outfit", "")
            cast.append(e)
    s["cast"] = cast
    used = set()
    s["shots"] = _objects(s.get("shots"))
    for x in s["shots"]:
        x["id"] = _unique_id(x.get("id"), "h", used)
        x["t"] = spec.num(x.get("t"), 0.0)
        _text_field(x, "camera", "")
        _text_field(x, "text", "")
    s["shots"].sort(key=lambda x: x["t"])
    used = set()
    s["dialogue"] = _objects(s.get("dialogue"))
    for x in s["dialogue"]:
        x["id"] = _unique_id(x.get("id"), "d", used)
        x["t"] = spec.num(x.get("t"), 0.0)
        for k in ("speaker", "delivery", "text"):
            _text_field(x, k, "")
        _text_field(x, "language", lang)
    s["dialogue"].sort(key=lambda x: x["t"])

    pr = s.get("prompt")
    if isinstance(pr, str):  # a bare prompt text is a raw prompt
        pr = {"mode": "structured" if _blank(pr) else "raw", "raw": pr}
    pr = s["prompt"] = pr if isinstance(pr, dict) else {}
    pr["mode"] = pr["mode"] if pr.get("mode") in PROMPT_MODES else "structured"
    auto = pr["auto"] = pr["auto"] if isinstance(pr.get("auto"), dict) else {}
    for k in ("subjects", "retention", "shots"):
        auto[k] = spec.flag(auto.get(k), True)
    sec = pr["sections"] = pr["sections"] if isinstance(pr.get("sections"), dict) else {}
    for k in SECTION_KEYS:
        _text_field(sec, k, "")
    _text_field(pr, "raw", "")
    pp = pr.get("pass_prompts") if isinstance(pr.get("pass_prompts"), dict) else {}
    pr["pass_prompts"] = {k: spec.text(v) for k, v in pp.items() if spec.text(v, None) is not None}

    o = s["overrides"] = s["overrides"] if isinstance(s.get("overrides"), dict) else {}
    for k in ("seed", "steps", "width", "height"):
        if k in o:
            v = spec.num(o[k], None)
            if v is None:
                del o[k]  # "" or junk: follow Global
            else:
                o[k] = int(v)
    for k in ("sampler", "scheduler", "diffusion", "text_encoder", "video_vae", "audio_vae", "quality"):
        if k in o and not isinstance(o[k], str):
            del o[k]
    if "loras" in o:
        lo = o["loras"]
        if not isinstance(lo, dict):
            del o["loras"]
        else:
            lo["mode"] = lo["mode"] if lo.get("mode") in ("add", "replace") else "add"
            lo["items"] = _objects(lo.get("items"))
            for l in lo["items"]:
                _norm_lora(l)
            sts = lo.get("strengths") if isinstance(lo.get("strengths"), dict) else {}
            lo["strengths"] = {k: spec.num(v) for k, v in sts.items() if spec.num(v, None) is not None}
    s["lock"] = spec.flag(s.get("lock"), False)
    _text_field(s, "notes", "")
    tn = s["transition"] = s["transition"] if isinstance(s.get("transition"), dict) else {}
    tn["mode"] = tn["mode"] if tn.get("mode") in ("",) + TRANSITIONS else ""
    for k in ("frames", "audio_fade_frames"):
        tn[k] = spec.num(tn.get(k), None)


# ---- scene.merge (added 2026-11-05 v0.7.0; model.js normMerge / migratedMerge are the same) ----

def _merge_frames(v, default):
    """A frame count of scene.merge: a whole number 0 .. MERGE_MAX_FRAMES (fractions are cut off)."""
    return min(MERGE_MAX_FRAMES, max(0, int(spec.num(v, default))))


def _merge_color(v):
    """"#rrggbb" in lower case; anything else is black."""
    return v.lower() if isinstance(v, str) and COLOR_RE.fullmatch(v) else "#000000"


def _clamp(v, default, lo, hi):
    return min(hi, max(lo, spec.num(v, default)))


def _migrated_merge(s, gm, first_id, scene_ids):
    """scene.merge for a scene saved before v0.7.0, built so it merges exactly as before: the transition is the
    scene's own transition mode or Global -> Merge -> hard cut (an unknown one was a cut), its length and audio fade
    the scene's own or the global ones; with Global colour match on, every scene but the reference matches the
    reference scene (Global's colour reference scene, or the first scene when that is empty or gone)."""
    tn = s.get("transition") if isinstance(s.get("transition"), dict) else {}
    hard = gm.get("hard_cut")
    m = default_merge()
    m["transition"] = tn.get("mode") or (hard if hard in TRANSITIONS else "cut")
    m["frames"] = tn["frames"] if tn.get("frames") is not None else gm.get("transition_frames")
    m["audio_frames"] = tn["audio_fade_frames"] if tn.get("audio_fade_frames") is not None else gm.get("audio_fade_frames")
    if gm.get("color_match") is True:
        ref = gm.get("color_ref_scene") if gm.get("color_ref_scene") in scene_ids else first_id
        if s["id"] != ref:
            m["color_match"], m["color_ref"] = "scene", ref
    return m


def _norm_merge(s, gm, first_id, scene_ids):
    """scene.merge in place (see default_merge). gm: the normalised Global -> Merge; first_id, scene_ids: the
    project's first scene id and every scene id (for the migration of a scene that has no merge object)."""
    m = s.get("merge")
    if not isinstance(m, dict):
        m = _migrated_merge(s, gm, first_id, scene_ids)
    m["transition"] = m["transition"] if m.get("transition") in MERGE_TRANSITIONS else "cut"
    m["direction"] = m["direction"] if m.get("direction") in MERGE_DIRECTIONS else "left"
    m["frames"] = _merge_frames(m.get("frames"), 12)
    m["color"] = _merge_color(m.get("color"))
    m["audio_frames"] = _merge_frames(m.get("audio_frames"), 6)
    for k in ("fade_in", "fade_out"):
        f = m[k] = m[k] if isinstance(m.get(k), dict) else {}
        f["frames"] = _merge_frames(f.get("frames"), 0)
        f["color"] = _merge_color(f.get("color"))
    for k in ("audio_fade_in", "audio_fade_out"):
        m[k] = _merge_frames(m.get(k), 0)
    m["volume_db"] = _clamp(m.get("volume_db"), 0.0, -60.0, 24.0)
    m["mute"] = spec.flag(m.get("mute"), False)
    m["color_match"] = m["color_match"] if m.get("color_match") in COLOR_MATCH_MODES else "off"
    _text_field(m, "color_ref", "")
    m["brightness"] = _clamp(m.get("brightness"), 0.0, -1.0, 1.0)
    m["contrast"] = _clamp(m.get("contrast"), 1.0, 0.0, 2.0)
    m["saturation"] = _clamp(m.get("saturation"), 1.0, 0.0, 3.0)
    s["merge"] = m


# ---- stable seeds (added 2026-11-03 v0.6.0) ----
# "+1 per scene" seeds used the scene's position, so inserting or moving a scene changed every later seed. Each scene
# now keeps the number it got when it was made: seed = Global seed + seed_n.
def _seed_n_value(v):
    """v when it is a usable seed number (a whole number 0 .. 2**31-1), else None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    x = spec.num(v, None)
    if x is None or x < 0 or x >= SEED_N_LIMIT or x != int(x):
        return None
    return int(x)


def _repair_seed_ns(scenes):
    """A valid seed_n stays unless an earlier scene has it; a scene without one gets its list index (what its seed
    was before seed_n existed), or the next number above the highest when that is taken."""
    used, pending = set(), []
    for i, s in enumerate(scenes):
        n = _seed_n_value(s.get("seed_n"))
        if n is not None and n not in used:
            used.add(n)
            s["seed_n"] = n
        else:
            pending.append((i, s, n is None))
    for i, s, missing in pending:
        n = i if missing and i not in used else max(used, default=-1) + 1
        used.add(n)
        s["seed_n"] = n


def next_seed_n(p):
    """seed_n for a new scene (split, duplicate, paste, add): one above the highest in the project, 0 for the first."""
    scenes = p.get("scenes") if isinstance(p, dict) else None
    vals = []
    for i, s in enumerate(scenes if isinstance(scenes, list) else []):
        n = _seed_n_value(s.get("seed_n")) if isinstance(s, dict) else None
        vals.append(i if n is None else n)
    return max(vals) + 1 if vals else 0


def scene_seed_n(scene, scene_index):
    """The scene's seed number: its seed_n, or its index for a scene that has none (not normalised)."""
    n = _seed_n_value(scene.get("seed_n"))
    return scene_index if n is None else n


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
            # [OLD 2026-11-03 v0.5.1->v0.6.0] base = int(sm["seed"]) + scene_index  (inserting a scene changed later seeds)
            base = int(sm["seed"]) + scene_seed_n(scene, scene_index)
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
    """DEPRECATED (2026-11-03 v0.6.0): use scene_overlap_at(p, i), which knows the scene before (a tail is capped by
    its length) and the re-anchor rule (a re-anchored tail overlaps one frame). Kept unchanged for callers that have
    not switched yet.

    Seconds at the start of a scene that repeat the end of the scene before (added 2026-11-03 v0.5.0): the tail
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


# ---- how scenes join (added 2026-11-03 v0.6.0; model.js has the same functions, tests/test_model_parity.py) ----
def continuation_depth(p):
    """How many continuation links lead into each scene (0 for a fresh start). Moved here from planner.py (which
    re-exports it) in v0.6.0."""
    depth, prev = {}, 0
    for i, s in enumerate(p["scenes"]):
        cont = i > 0 and s["start"]["mode"] in ("last_frame", "tail")
        prev = prev + 1 if cont else 0
        depth[s["id"]] = prev
    return depth


def _depth_at(p, i, scene):
    d, j, cur = 0, i, scene
    while j > 0 and cur["start"]["mode"] in ("last_frame", "tail"):
        d += 1
        j -= 1
        cur = p["scenes"][j]
    return d


def scene_frames(scene):
    """Frames of a scene in the cut (at least 1)."""
    return max(1, spec.frames_of(max(1.0 / spec.FPS, float(scene["duration"]))))


def _start_info(p, i, scene=None, depth=None):
    """(effective start, tail overlap frames) of scene i; `scene` replaces p["scenes"][i] when given."""
    s = p["scenes"][i] if scene is None else scene
    mode = s["start"]["mode"] if i > 0 else "fresh"
    if mode == "last_frame":
        return "last_frame", 0
    if mode != "tail":
        return "fresh", 0
    if depth is None:
        depth = _depth_at(p, i, s)
    if depth > int(p["global"]["continuity"]["reanchor_after"]):
        return "last_frame", 0  # re-anchored: guided by the last frame only, so trimmed and timed as last_frame

    def down(n):  # 17k+5 frames that fit in n frames (0 when not even 5 do)
        return spec.align_frames_down(n) if n >= 5 else 0

    # at most 124 frames: render keeps the last 124 frames of a scene as its tail clip (spec.MIN_PASS_FRAMES)
    n = min(spec.align_frames_down(max(5, int(s["start"]["overlap_frames"]))), spec.MIN_PASS_FRAMES,
            down(scene_frames(s)), down(scene_frames(p["scenes"][i - 1])))
    return ("tail", n) if n >= 5 else ("last_frame", 0)


def effective_start(p, i):
    """How scene i really starts: "fresh", "last_frame" or "tail". The first scene is always fresh; a tail past
    Global -> Continuity -> re-anchor after (continuation depth > reanchor_after), or one where the scene or the scene
    before is shorter than 5 frames, is a "last_frame" start everywhere (planner, overlap, timeline, merge)."""
    return _start_info(p, i)[0]


def tail_overlap_frames(p, i):
    """Frames of the tail clip scene i starts with (17k+5, at least 5), 0 unless effective_start is "tail". Capped by
    the scene's own length, the length of the scene before and 124 frames (the tail clip render keeps)."""
    return _start_info(p, i)[1]


def _overlap_seconds(mode, frames):
    return frames / spec.FPS if mode == "tail" else 1.0 / spec.FPS if mode == "last_frame" else 0.0


def scene_overlap_at(p, i):
    """Seconds at the start of scene i that repeat the end of the scene before: the tail clip, or one frame for a
    last-frame start, 0 for a fresh start."""
    return _overlap_seconds(*_start_info(p, i))


def _timing(p):
    """[(scene id, start, overlap seconds, duration)] in one pass over the scenes."""
    out, t, depth = [], 0.0, 0
    for i, s in enumerate(p["scenes"]):
        depth = depth + 1 if i > 0 and s["start"]["mode"] in ("last_frame", "tail") else 0
        ov = _overlap_seconds(*_start_info(p, i, s, depth))
        t = max(0.0, t - ov)
        out.append((s["id"], t, ov, float(s["duration"])))
        t += float(s["duration"])
    return out, t


# [OLD 2026-11-03 v0.5.1->v0.6.0] used scene_overlap (no cap by the scene before, no re-anchor rule)
# def scene_starts(p):
#     """Start of every scene in the finished cut, and its length (added 2026-11-03 v0.5.0, same as model.js
#     sceneStarts). A scene's time t plays at starts[id] + t."""
#     starts, t = {}, 0.0
#     for i, s in enumerate(p["scenes"]):
#         t = max(0.0, t - scene_overlap(s, i))
#         starts[s["id"]] = t
#         t += float(s["duration"])
#     return starts, t
# [/OLD]
def scene_starts(p):
    """Start of every scene in the finished cut, and the cut's length (same as model.js sceneStarts). A scene's time
    t plays at starts[id] + t; a scene that continues the one before starts inside it by scene_overlap_at."""
    rows, total = _timing(p)
    return {sid: start for sid, start, _, _ in rows}, total


def visible_starts(p):
    """{scene id: film time where the scene first shows new content} (start + overlap)."""
    return {sid: start + ov for sid, start, ov, _ in _timing(p)[0]}


def visible_start(p, sid):
    """Film time where scene `sid` first shows new content (its start plus the overlap it repeats); None for an
    unknown id. Scene k is on screen from visible_start to start + duration."""
    return visible_starts(p).get(sid)


# ---- reference budget (added 2026-11-03 v0.6.0; model.js sceneBudget gives the same numbers) ----
COUNT_KEYS = ("pictures", "videos", "video_seconds", "audio", "audio_seconds", "files")


# ---- the continuation as a named reference (added 2026-11-05 v0.7.0; model.js passContinuation / continuationFrames
# are the same, tests/test_model_parity.py) ----
def pass_continuation(p, i, pass_, mode=None):
    """What pass_ (a planner pass) of scene i sends as reference 1 for the footage it continues from, when Global ->
    Continuity -> name_continuation is on: "picture" (pass 1 of a last-frame start, a re-anchored tail too: the last
    frame of the scene before is <Picture 1>), "video" (pass 1 of a tail start: the tail clip of the scene before is
    <Video 1>; a later pass after an overlap seam: the end of the pass before), else "". The same passes get the
    MiniMaxH3AddGuide anchors (prompt.collect_refs). mode: effective_start(p, i) when the caller has it."""
    if not spec.flag(((p.get("global") or {}).get("continuity") or {}).get("name_continuation", True), True):
        return ""
    if int(spec.num(pass_.get("index"), 1)) > 1:
        return "video" if pass_.get("seam_before") == "overlap" else ""
    if i is None or i <= 0:
        return ""
    if mode is None:
        mode = effective_start(p, i)
    if mode == "tail" and pass_.get("overlap_frames"):
        return "video"
    return "picture" if mode in ("last_frame", "tail") else ""


def continuation_frames(p, i, pass_, mode=None):
    """Frames of the clip pass_continuation sends as <Video 1>: the tail clip render keeps of the scene before (its
    last 124 frames, fewer when that scene is shorter) or the last 124 frames of the pass before; 0 for no clip."""
    if pass_continuation(p, i, pass_, mode) != "video":
        return 0
    if int(spec.num(pass_.get("index"), 1)) > 1:
        return spec.MIN_PASS_FRAMES
    return min(spec.MIN_PASS_FRAMES, scene_frames(p["scenes"][i - 1]))


# [OLD 2026-11-05 v0.6.1->v0.7.0] def scene_media_counts(p, scene, pass_=None, starts=None):
def scene_media_counts(p, scene, pass_=None, starts=None, mode=None, continuation=True):  # mode, continuation: v0.7.0
    """What one pass of `scene` sends H3, counted the way prompt.collect_refs presents references:

    pictures       cast anchors (+ outfit pictures; a packed sheet is 1) and reference pictures, each asset once
    videos         reference videos;                video_seconds: their length
    audio          voice samples of cast members who speak IN THIS PASS (left out when the song is sent),
                   reference audio, one slot per reference video whose sound is used, and the soundtrack segment
                   when soundtrack.pass_soundtrack gives one;   audio_seconds: their length
    files          pictures + videos + audio files (a video's own sound is not a separate file)
    song           True when the pass gets the soundtrack

    pass_ is a planner pass (needs start, gen_frames, dialogue). pass_=None plans the scene and returns, for each
    count, the most any of its passes uses (song: any pass). starts: scene_starts(p)[0] if you have it already.
    Guide pictures (first/last frame, keyframes) that the prompt text names are not counted.

    added 2026-11-05 v0.7.0: the continuation reference (pass_continuation) counts too, as one picture or one video
    (plus an audio slot for its sound when one is free); continuation: "picture" | "video" | "video_audio" (with its
    sound) | "" says which (pass_=None: the first pass that has one). A continuation picture counts for "auto"
    packing; one that still does not fit (pictures <= 9, videos <= 3, files <= 12) is left out, and the pass counts as
    in v0.6.1. mode: effective_start of the scene when known; continuation=False counts as v0.6.1 did."""
    if pass_ is None:
        from .planner import plan_scene  # planner imports model
        i = next((k for k, s in enumerate(p["scenes"]) if s["id"] == scene["id"]), 0)
        # [OLD 2026-11-05 v0.6.1->v0.7.0] outs = [scene_media_counts(p, scene, x, starts) for x in plan_scene(p, scene, i)["passes"]]
        outs = [scene_media_counts(p, scene, x, starts, mode, continuation) for x in plan_scene(p, scene, i)["passes"]]
        out = {k: max(o[k] for o in outs) for k in COUNT_KEYS}
        out["song"] = any(o["song"] for o in outs)
        out["continuation"] = next((o["continuation"] for o in outs if o["continuation"]), "")  # added 2026-11-05 v0.7.0
        return out
    idx = project_index(p)
    assets, cast = idx["assets"], idx["cast"]
    entries = list(scene["cast"])
    for d in scene["dialogue"]:  # a speaker who is not in the scene's cast list still gets anchors
        if d.get("speaker") in cast and not any(e["id"] == d["speaker"] for e in entries):
            entries.append({"id": d["speaker"], "outfit": ""})
    people = []
    for e in entries:
        c = cast.get(e["id"])
        if not c:
            continue
        outfit = next((o for o in c["outfits"] if o["id"] == (e.get("outfit") or c["default_outfit"])), None)
        ids = [a for a in c["anchors"] if a in assets and assets[a]["kind"] == "image"]
        if outfit:
            ids += [a for a in outfit["assets"] if a in assets and assets[a]["kind"] == "image" and a not in ids]
        people.append((c, ids))
    anchors = {a for _, ids in people for a in ids}
    ref_pics = {r["asset"] for r in scene["refs"]
                if r["role"] == "reference" and r["asset"] in assets and assets[r["asset"]]["kind"] == "image"}
    # added 2026-11-05 v0.7.0: the continuation reference of this pass; a picture counts for "auto" packing
    i = next((k for k, s in enumerate(p["scenes"]) if s["id"] == scene["id"]), None)
    cont = pass_continuation(p, i, pass_, mode) if continuation else ""
    # [OLD 2026-11-05 v0.6.1->v0.7.0] auto_pack = len(anchors) + len(ref_pics - anchors) > spec.MAX_REF_IMAGES
    auto_pack = len(anchors) + len(ref_pics - anchors) + (1 if cont == "picture" else 0) > spec.MAX_REF_IMAGES
    if starts is None:
        starts = scene_starts(p)[0]
    song = _soundtrack.pass_soundtrack(p, starts.get(scene["id"], 0.0), pass_)
    speaking = {d.get("speaker") for d in pass_.get("dialogue") or []}
    out = {"pictures": 0, "videos": 0, "video_seconds": 0.0, "audio": 0, "audio_seconds": 0.0, "files": 0,
           "song": bool(song)}
    sent, sounds = set(), []
    for c, ids in people:
        pack = auto_pack if c.get("pack_sheet", True) == "auto" else bool(c.get("pack_sheet", True))
        out["pictures"] += 1 if ids and pack and len(ids) > 1 else len(ids)
        sent.update(ids)
        v = assets.get(c.get("voice"))
        if v and v["kind"] == "audio" and not song and c["id"] in speaking:
            sounds.append(v)
    for r in scene["refs"]:
        a = assets.get(r["asset"])
        if not a or r["role"] != "reference":
            continue
        dur = float(a.get("duration") or 0)
        if a["kind"] == "image":
            if a["id"] not in sent:
                sent.add(a["id"])
                out["pictures"] += 1
        elif a["kind"] == "video":
            out["videos"] += 1
            out["video_seconds"] += dur
            if r.get("soundtrack"):  # the video's sound takes an <Audio j> slot of its own
                out["audio"] += 1
                out["audio_seconds"] += dur
        elif a["kind"] == "audio" and not any(x["id"] == a["id"] for x in sounds):
            sounds.append(a)
    out["audio"] += len(sounds) + (1 if song else 0)
    for a in sounds:
        out["audio_seconds"] += float(a.get("duration") or 0)
    if song:
        out["audio_seconds"] += song["length"]
    out["files"] = out["pictures"] + out["videos"] + len(sounds) + (1 if song else 0)
    # added 2026-11-05 v0.7.0: the continuation reference, when it fits (else the pass counts as in v0.6.1)
    out["continuation"] = ""
    if cont == "picture":
        if out["pictures"] + 1 > spec.MAX_REF_IMAGES or out["files"] + 1 > spec.MAX_REF_FILES:
            return scene_media_counts(p, scene, pass_, starts, mode, continuation=False)
        out["pictures"] += 1
        out["files"] += 1
        out["continuation"] = "picture"
    elif cont == "video" and out["videos"] + 1 <= spec.MAX_REF_VIDEOS and out["files"] + 1 <= spec.MAX_REF_FILES:
        secs = continuation_frames(p, i, pass_, mode) / spec.FPS
        out["videos"] += 1
        out["files"] += 1
        out["video_seconds"] += secs
        out["continuation"] = "video"
        if out["audio"] < spec.MAX_REF_AUDIOS:  # its sound, when an audio slot is free
            out["audio"] += 1
            out["audio_seconds"] += secs
            out["continuation"] = "video_audio"
    return out
