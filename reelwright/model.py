"""Project schema 1: defaults, normalization and effective settings.

Kept in step with web/rw/model.js. The editor fills defaults for instant
feedback; this module is what the renderer trusts.
"""

import copy
import hashlib
import json
import math
import re
import secrets
import unicodedata

from . import soundtrack as _soundtrack
from . import spec

SECTION_KEYS = ("subject_definitions", "summary", "retention_analysis",
                "detailed_description", "overall_soundscape", "non_diegetic_music")
# hires ("off": this scene skips the latent upscaler), refine_steps, refine_denoise
OVERRIDE_KEYS = ("seed", "steps", "sampler", "scheduler", "width", "height",
                 "diffusion", "text_encoder", "video_vae", "audio_vae", "quality",
                 "hires", "refine_steps", "refine_denoise")
TRANSITIONS = ("cut", "crossfade", "dip")
# scene.merge, how a scene sits in the cut (model.js has the same values). TRANSITIONS stays
# for the deprecated scene.transition (read once, by the migration in _norm_merge)
MERGE_TRANSITIONS = ("cut", "crossfade", "dip", "wipe", "slide", "circle", "dissolve", "pixelize", "radial", "zoom")
MERGE_DIRECTIONS = ("left", "right", "up", "down")
SUBTITLE_TIMING = ("speech", "planned")
COLOR_MATCH_MODES = ("off", "previous", "scene")
MERGE_MAX_FRAMES = 14400  # frame counts in scene.merge: 0 .. 600 s
COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")  # "#rrggbb" (fullmatch)
CODE_PREFIX = {"image": "P", "video": "V", "audio": "A"}
# What normalize_project enforces (model.js has the same values)
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
# The camera moves MiniMax's H3 guide lists (base-en.txt 4.3), name = the guide's label,
# text = the natural phrase written into the shot line ("The camera pushes in with small amplitude at slow speed.").
# Projects saved before get the missing ones appended once (camera_version 2); their own presets stay. model.js has
# the same list.
DEFAULT_CAMERA = (("Zoom In", "the camera zooms in"), ("Zoom Out", "the camera zooms out"),
                  ("Push In", "the camera pushes in"), ("Pull Out", "the camera pulls out"),
                  ("Pan Left", "the camera pans left"), ("Pan Right", "the camera pans right"),
                  ("Truck Left", "the camera trucks left"), ("Truck Right", "the camera trucks right"),
                  ("Tilt Up", "the camera tilts up"), ("Tilt Down", "the camera tilts down"),
                  ("Pedestal Up", "the camera pedestals up"), ("Pedestal Down", "the camera pedestals down"),
                  ("Arc Shot", "the camera arcs around the subject"),
                  ("Tracking Shot", "the camera tracks the moving subject"),
                  ("Static Shot", "the camera holds a static shot"),
                  ("Shake Slightly", "the camera shakes slightly"), ("Shake Strongly", "the camera shakes strongly"),
                  ("POV", "the camera takes the subject's point of view"),
                  ("Roll Clockwise", "the camera rolls clockwise"),
                  ("Roll Counterclockwise", "the camera rolls counterclockwise"))
CAMERA_VERSION = 2
# Shot fields camera_amp / camera_speed / framing ("" = not said), and how they are written
CAMERA_AMPS = ("", "small", "large")
CAMERA_SPEEDS = ("", "slow", "fast")
FRAMINGS = ("", "extreme wide", "wide", "medium wide", "medium", "medium close-up", "close-up", "extreme close-up",
            "over-the-shoulder", "two-shot", "insert", "low angle", "high angle", "overhead", "dutch angle")
FRAMING_PHRASE = {"extreme wide": "an extreme wide shot", "wide": "a wide shot", "medium wide": "a medium-wide shot",
                  "medium": "a medium shot", "medium close-up": "a medium close-up", "close-up": "a close-up",
                  "extreme close-up": "an extreme close-up", "over-the-shoulder": "an over-the-shoulder shot",
                  "two-shot": "a two-shot", "insert": "an insert shot", "low angle": "a low-angle shot",
                  "high angle": "a high-angle shot", "overhead": "an overhead shot",
                  "dutch angle": "a Dutch-angle shot"}
DIALOGUE_MAX_SECONDS = 600.0


def new_id(prefix):
    return prefix + "_" + secrets.token_hex(4)


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
    """The project's folder: its slug when that is a valid folder name (kept as typed, so
    "untitled-x7k2" stays), else slugify(slug or name)."""
    s = spec.text(p.get("slug"))
    return s if SLUG_RE.fullmatch(s) else slugify(s or p.get("name"))  # fullmatch: re's $ allows a trailing \n


# Global -> Long scenes -> hand-off and pass cache (model.js LONG_HANDOFF / LONG_PASS_CACHE)
LONG_HANDOFF = ("pixels", "latent")
LONG_PASS_CACHE = ("near_lossless", "lossless")


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
        "draft": {"scale": 0.5, "steps": 8, "lora": "", "lora_strength": 1.0, "lora_trigger": "", "hires": False},
        "hires": {"enabled": False, "scale": 2.0, "refine_steps": 0, "refine_denoise": 0.35},
        "defaults": {"duration": 8.0, "start_mode": "last_frame", "overlap_frames": 39, "language": "English"},
        "long": {"max_pass_frames": 362, "overlap_frames": 39, "crossfade_frames": 12,
                 "seam_mode": "auto", "cut_snap_seconds": 2.0,
                 "guide_vae": "", "carry_audio": True, "seam_video_ref": True, "handoff": "pixels",
                 "pass_cache": "near_lossless"},
        "memory": {"policy": "free_cache", "encode_first": True, "group_by_lora": True},
        "continuity": {"reanchor_after": 2, "face_check": False, "face_threshold": 0.8, "on_drift": "flag",
                       "name_continuation": True, "describe_voices": True},
        "llm": {"base_url": "", "model": "", "temperature": 0.4, "max_tokens": 2048, "preset": "h3_ref2va",
                "include_guides": True, "thinking": "auto",  # thinking: auto (model default) | off
                # Describe sends a video clip as a video (video), as frames (frames) or tries video first (auto)
                "describe_video": "auto",
                "timeout_s": 120, "max_wait_s": 900, "retries": 2, "context_tokens": 0,
                # script import: the script is sent in parts of about this many characters (0 = all at once),
                # each part may answer with up to import_max_tokens; import_thinking: same | off;
                # import_guides: also send MiniMax's H3 guides (about 10k tokens) with every part
                "import_part_chars": 3000, "import_max_tokens": 24576, "import_thinking": "same",
                "import_guides": False},
        "merge": {"use": "starred", "missing": "skip", "hard_cut": "cut", "transition_frames": 12,
                  "audio_fade_frames": 6, "loudness": -16.0, "normalize": True,
                  "score": {"asset": "", "volume_db": -12.0, "duck": True},
                  "scene_audio": {"mix": False, "volume_db": -12.0},
                  "color_match": False, "color_ref_scene": "", "codec": "h264", "crf": 16,
                  "subtitles": True, "subtitle_timing": "speech", "chapters": True, "otio": True, "fcpxml": True,
                  "bundle": False,
                  "auto_after_render": True},
    }


def default_prompt():
    return {"mode": "structured", "auto": {"subjects": True, "retention": True, "shots": True},
            "sections": {k: "" for k in SECTION_KEYS}, "raw": "", "pass_prompts": {}, "passes": [], "brief": ""}


def default_merge():
    """scene.merge of a new scene, how it sits in the cut (assemble.cut_plan reads it).
    transition: how a fresh start joins the scene before (MERGE_TRANSITIONS), direction for wipe / slide, frames its
    length, color the dip colour; audio_frames: the sound's fade out / in at a cut; fade_in / fade_out: the picture
    from / to a colour at the scene's first / last frame; audio_fade_in / _out (frames); volume_db and mute: the
    scene's own sound; color_match: off | previous | scene (color_ref: that scene's id); brightness, contrast,
    saturation: ffmpeg eq. model.js defaultMerge is the same."""
    return {"transition": "cut", "direction": "left", "frames": 12, "color": "#000000", "audio_frames": 6,
            "fade_in": {"frames": 0, "color": "#000000"}, "fade_out": {"frames": 0, "color": "#000000"},
            "audio_fade_in": 0, "audio_fade_out": 0, "volume_db": 0.0, "mute": False,
            "color_match": "off", "color_ref": "", "brightness": 0.0, "contrast": 1.0, "saturation": 1.0}


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
        "transition": {"mode": "", "frames": None, "audio_fade_frames": None},
        "seed_n": next_seed_n(project),
        "merge": default_merge(),
        "pass_names": {},
    }
    scene.update(patch)
    return scene


def default_project(name="Untitled"):
    p = {"schema": 1, "id": new_id("p"), "project_id": "", "name": name, "slug": slugify(name),
         "global": default_global(), "assets": [], "cast": [], "camera_presets": default_camera_presets(),
         "asset_groups": [],
         "camera_version": CAMERA_VERSION,
         "scenes": [], "markers": [], "soundtrack": [],
         "ui": {"tab": "timeline", "selected": "", "zoom": 22, "playhead": 0, "snap": True, "ripple": True}}
    p["scenes"].append(default_scene(p, title="Scene 1"))
    p["ui"]["selected"] = p["scenes"][0]["id"]
    return p


def default_camera_presets():
    """Camera moves every new project starts with (as model.js always had)."""
    return [{"id": new_id("k"), "name": n, "text": t} for n, t in DEFAULT_CAMERA]


def _camera_key(name):
    """A preset name compared without case and surrounding ASCII spaces (model.js the same)."""
    return spec.text(name).strip(" \t\n\r").lower()


def _migrate_camera(p):
    """A project saved before v0.8.0 (camera_version below 2) gets H3's official camera moves
    it does not have yet (compared by name) appended to its presets, once; its own presets stay as they are. Then
    camera_version is 2 (a higher whole number is kept). model.js migrateCamera is the same."""
    cv = spec.num(p.get("camera_version"), 0)
    if cv < CAMERA_VERSION:
        have = {_camera_key(k["name"]) for k in p["camera_presets"]}
        for name, text in DEFAULT_CAMERA:
            if _camera_key(name) not in have:
                p["camera_presets"].append({"id": new_id("k"), "name": name, "text": text})
        p["camera_version"] = CAMERA_VERSION
    else:
        p["camera_version"] = int(min(cv, 1000000))


def _fill(target, defaults):
    for k, v in defaults.items():
        if target.get(k) is None:
            target[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(target[k], dict):
            _fill(target[k], v)
    return target


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


# The hardened normaliser. model.js normalizeProject does exactly the same (tests/
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
    _norm_asset_groups(p, assets)

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
    _migrate_camera(p)

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
    (model.js normalizeGlobal does the same)."""
    g = _like(copy.deepcopy(g) if isinstance(g, dict) else {}, default_global())
    d = g["defaults"]
    if d["start_mode"] not in spec.START_MODES:
        d["start_mode"] = "last_frame"
    d["duration"] = min(MAX_SCENE_SECONDS, max(MIN_SCENE_SECONDS, d["duration"]))
    d["overlap_frames"] = max(0, int(d["overlap_frames"]))
    g["continuity"]["reanchor_after"] = max(0, int(g["continuity"]["reanchor_after"]))
    lg = g["long"]
    if lg["handoff"] not in LONG_HANDOFF:
        lg["handoff"] = "pixels"
    if lg["pass_cache"] not in LONG_PASS_CACHE:
        lg["pass_cache"] = "near_lossless"
    if g["merge"]["subtitle_timing"] not in SUBTITLE_TIMING:
        g["merge"]["subtitle_timing"] = "speech"
    hi = g["hires"]
    hi["scale"] = min(HIRES_MAX_SCALE, max(1.0, float(hi["scale"])))
    hi["refine_steps"] = min(100, max(0, int(hi["refine_steps"])))
    hi["refine_denoise"] = min(1.0, max(0.01, float(hi["refine_denoise"])))
    g["loras"] = _objects(g["loras"])
    for l in g["loras"]:
        _norm_lora(l)
    g["draft"]["lora_trigger"] = trigger_text(g["draft"]["lora_trigger"])
    return g


def trigger_text(v):
    """A LoRA's trigger word(s): one line, single spaces, at most 120 characters ("" for none)."""
    return " ".join(spec.text(v, "").split())[:120].strip()


def _norm_lora(l):
    l["id"] = spec.text(l.get("id")) or new_id("l")
    _text_field(l, "name", "")
    l["strength"] = spec.num(l.get("strength"), 1.0)
    l["enabled"] = spec.flag(l.get("enabled"), True)
    l["trigger"] = trigger_text(l.get("trigger"))


def _norm_asset(a):
    a["kind"] = a["kind"] if a.get("kind") in ASSET_KINDS else "image"
    a["id"] = spec.text(a.get("id")) or new_id("a")
    for k in ("code", "name", "file", "category", "notes", "description"):
        _text_field(a, k, "")
    for k in ("duration", "width", "height"):
        a[k] = max(0, spec.num(a.get(k), 0))
    df = a["defaults"] = a["defaults"] if isinstance(a.get("defaults"), dict) else {}
    df["role"] = df["role"] if df.get("role") in spec.ROLES else "reference"
    _text_field(df, "retention", "reference" if a["kind"] == "audio" else "fully_preserved")
    df["keep"] = _texts(df.get("keep"))
    df["soundtrack"] = spec.flag(df.get("soundtrack"), False)
    # a picture cut out of another one (the crop window): {asset: the source's id, box: [x, y, w, h] as parts of it}
    co = a.get("crop_of")
    box = co.get("box") if isinstance(co, dict) else None
    if isinstance(box, list) and len(box) == 4 and spec.text(co.get("asset")) and \
            all(spec.num(v, None) is not None for v in box):
        a["crop_of"] = {"asset": spec.text(co.get("asset")), "box": [min(1.0, max(0.0, spec.num(v, 0.0))) for v in box]}
    else:
        a.pop("crop_of", None)


def _norm_asset_groups(p, assets):
    """The asset groups, in their order: {id, name, description}
    with unique ids; each asset's group is one of their ids or "" (no group), and its tags are cleaned by asset_tags.
    Groups and tags only sort the Assets tab: no prompt, plan or cache key reads them."""
    groups = p["asset_groups"] = _objects(p.get("asset_groups"))
    ids = set()
    for gr in groups:
        gr["id"] = _unique_id(gr.get("id"), "g", ids)
        _text_field(gr, "name", "")
        _text_field(gr, "description", "")
    for a in assets:
        _text_field(a, "group", "")
        if a["group"] not in ids:
            a["group"] = ""
        a["tags"] = asset_tags(a.get("tags"))


TAG_MAX = 60
PASS_NAME_MAX = 60


def pass_names(v):
    """
    scene.pass_names, {"<pass number>": name}: numbers 1-999 as text, names with runs of spaces, tabs and line breaks
    made one space, cut to 60 characters and trimmed; empty names are dropped. A name belongs to the pass number, so
    it stays when the pass layout changes. Only the editor shows it ("Pass 2 · Harbour"); nothing sent to H3 or the
    LLM, and no cache key, reads it. model.js passNames is the same."""
    out = {}
    if not isinstance(v, dict):
        return out
    for k, x in v.items():
        key = spec.text(k)
        t = spec.text(x, None)
        if not re.fullmatch(r"[1-9][0-9]{0,2}", key) or t is None:
            continue
        t = re.sub(r"[ \t\n\r]+", " ", t)[:PASS_NAME_MAX].strip(" ")
        if t:
            out[key] = t
    return out


def asset_tags(v):
    """The strings (and numbers) of a list with runs of spaces, tabs and
    line breaks made one space, cut to 60 characters and trimmed; empty and repeated tags (same spelling) are dropped."""
    out = []
    for x in _texts(v):
        t = re.sub(r"[ \t\n\r]+", " ", x)[:TAG_MAX].strip(" ")
        if t and t not in out:
            out.append(t)
    return out


def _norm_cast(c, lang):
    c["id"] = spec.text(c.get("id")) or new_id("c")
    c["kind"] = c["kind"] if c.get("kind") in CAST_KINDS else "character"
    for k in ("name", "speaker", "description", "default_outfit", "voice", "voice_desc"):
        _text_field(c, k, "")
    _text_field(c, "part_of", "")
    _text_field(c, "language", lang)
    c["anchors"] = _texts(c.get("anchors"))
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
    lora["trigger"] = trigger_text(lora.get("trigger"))
    c["refmod"] = norm_refmod(c.get("refmod"))
    c["voice_refmod"] = norm_refmod(c.get("voice_refmod"))
    c["video_anchors"] = _objects(c.get("video_anchors"))
    used = set()
    for va in c["video_anchors"]:
        va["id"] = _unique_id(va.get("id"), "va", used)
        _text_field(va, "asset", "")
        va["in"] = snap_frame(max(0.0, spec.num(va.get("in"), 0.0)))
        o = spec.num(va.get("out"), None)
        va["out"] = None if o is None or o <= 0 else snap_frame(o)
        va["soundtrack"] = spec.flag(va.get("soundtrack"), False)
        fr = spec.num(va.get("frame"), None)
        va["frame"] = None if fr is None or fr < 0 else snap_frame(fr)
        _text_field(va, "frame_asset", "")


def _blank(s):
    return not re.search(r"[^ \t\n\r\f\v]", s)


def _norm_pass_text(x):
    """One entry of scene.prompt.passes: {"start", "end" (scene seconds of the pass when its
    text was written), "sections": the six sections as text}; anything else becomes an empty entry (0, 0)."""
    x = x if isinstance(x, dict) else {}
    x["start"] = float(spec.num(x.get("start"), 0.0))
    x["end"] = float(spec.num(x.get("end"), 0.0))
    sec = x["sections"] = x["sections"] if isinstance(x.get("sections"), dict) else {}
    for k in SECTION_KEYS:
        _text_field(sec, k, "")
    return x


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
        _text_field(r, "cast", "")
        _text_field(r, "retention", "")
        r["keep"] = _texts(r.get("keep"))
        r["soundtrack"] = spec.flag(r.get("soundtrack"), False)
        r["in"] = snap_frame(max(0.0, spec.num(r.get("in"), 0.0)))
        o = spec.num(r.get("out"), None)
        r["out"] = None if o is None or o <= 0 else snap_frame(o)
    cast = []
    for e in s.get("cast") if isinstance(s.get("cast"), list) else []:
        e = {"id": e, "outfit": ""} if isinstance(e, str) else e
        if isinstance(e, dict):
            _text_field(e, "id", "")
            _text_field(e, "outfit", "")
            e["skip"] = list(dict.fromkeys(_texts(e.get("skip"))))
            cast.append(e)
    s["cast"] = cast
    used = set()
    s["shots"] = _objects(s.get("shots"))
    for x in s["shots"]:
        x["id"] = _unique_id(x.get("id"), "h", used)
        x["t"] = spec.num(x.get("t"), 0.0)
        _text_field(x, "camera", "")
        _text_field(x, "text", "")
        for k, allowed in (("camera_amp", CAMERA_AMPS), ("camera_speed", CAMERA_SPEEDS), ("framing", FRAMINGS)):
            x[k] = x[k] if x.get(k) in allowed else ""
    s["shots"].sort(key=lambda x: x["t"])
    used = set()
    s["dialogue"] = _objects(s.get("dialogue"))
    for x in s["dialogue"]:
        x["id"] = _unique_id(x.get("id"), "d", used)
        x["t"] = spec.num(x.get("t"), 0.0)
        for k in ("speaker", "delivery", "text"):
            _text_field(x, k, "")
        _text_field(x, "language", lang)
        dur = spec.num(x.get("duration"), None)
        x["duration"] = float(min(dur, DIALOGUE_MAX_SECONDS)) if dur is not None and dur > 0 else None
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
    _text_field(pr, "brief", "")
    pp = pr.get("pass_prompts") if isinstance(pr.get("pass_prompts"), dict) else {}
    pr["pass_prompts"] = {k: spec.text(v) for k, v in pp.items() if spec.text(v, None) is not None}
    pr["passes"] = [_norm_pass_text(x) for x in pr["passes"]] if isinstance(pr.get("passes"), list) else []

    o = s["overrides"] = s["overrides"] if isinstance(s.get("overrides"), dict) else {}
    for k in ("seed", "steps", "width", "height", "refine_steps"):
        if k in o:
            v = spec.num(o[k], None)
            if v is None:
                del o[k]  # "" or junk: follow Global
            else:
                o[k] = int(v)
    for k in ("sampler", "scheduler", "diffusion", "text_encoder", "video_vae", "audio_vae", "quality"):
        if k in o and not isinstance(o[k], str):
            del o[k]
    if "refine_steps" in o:
        o["refine_steps"] = min(100, max(0, o["refine_steps"]))
    if "refine_denoise" in o:
        v = spec.num(o["refine_denoise"], None)
        if v is None:
            del o["refine_denoise"]
        else:
            o["refine_denoise"] = min(1.0, max(0.01, float(v)))
    if "hires" in o and o["hires"] != "off":
        del o["hires"]  # only "off" means something; anything else follows Global
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
    s["pass_names"] = pass_names(s.get("pass_names"))
    tn = s["transition"] = s["transition"] if isinstance(s.get("transition"), dict) else {}
    tn["mode"] = tn["mode"] if tn.get("mode") in ("",) + TRANSITIONS else ""
    for k in ("frames", "audio_fade_frames"):
        tn[k] = spec.num(tn.get(k), None)


# ---- scene.merge (model.js normMerge / migratedMerge are the same) -----------------------------

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


# ---- stable seeds ------------------------------
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


# A cast member without its own description is described by its anchor pictures,
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


# A prop can be part of a character (Cast -> Prop -> Part of): a beer belly, a tattoo, a
# prosthetic arm. Every cast member in a scene used to be a <Subject N> of its own, and H3 puts each subject in the
# shot as a separate thing. A part's pictures and
# description now go into its character's subject. It counts in a scene only when the prop is in the scene's cast
# and so is its character (in the cast list or speaking); without the character it is left out (validate warns).
def part_owner(c, cast):
    """The id of the character that prop `c` is part of, or "" (not a prop, no part_of, or part_of is not a character
    in `cast`, a dict id -> cast member)."""
    if not isinstance(c, dict) or c.get("kind") != "prop":
        return ""
    owner = cast.get(c.get("part_of") or "")
    if isinstance(owner, dict) and owner.get("kind") == "character" and owner.get("id") != c.get("id"):
        return owner["id"]
    return ""


def entry_skip(entry):
    """The anchors a scene's cast entry leaves out (scene.cast[].skip: picture asset ids and
    video anchor ids, and REFMOD_SKIP for the look RefMod), as a set; model.js entrySkip is the same."""
    return set((entry or {}).get("skip") or [])


# ---- RefMods: saved MiniMax H3 references made with ComfyUI-MiniMaxH3Mod (models/refmods/<name>.safetensors, one
# reference or a bundle of several). A cast member's look RefMod (cast.refmod) goes instead of its anchors: its
# pictures (image members) and videos (video members, such as stacked photos) are the subject's references, and its
# anchor pictures and video anchors are not sent (outfit pictures still are), unless the scene unticks the RefMod
# (scene.cast[].skip holds REFMOD_SKIP). A voice RefMod (cast.voice_refmod) goes instead of the voice sample, in the
# passes where the character speaks. The project keeps what the file held when it was picked (members: kind and latent
# size), so plans need no disk; refmods.py reads the files and checks they still hold that. model.js has the same.
REFMOD_SKIP = "refmod"
REFMOD_KINDS = ("image", "video", "audio")
REFMOD_AUDIO_RATE = 40  # audio latent frames per second (32 kHz H3 audio VAE)
REFMOD_MAX_MEMBERS = 64
REFMOD_NAME_MAX = 240


def refmod_name(v):
    """A RefMod's name as ComfyUI-MiniMaxH3Mod lists it: the path under a refmods folder with "/" and without
    .safetensors ("characters/birten")."""
    n = spec.text(v, "").replace("\\", "/").strip()
    if n.lower().endswith(".safetensors"):
        n = n[:-len(".safetensors")]
    return n.strip("/ ")[:REFMOD_NAME_MAX]


def norm_refmod(v):
    """cast.refmod / cast.voice_refmod: {"name", "strength" (0-1), "members": [{"kind", "t", "h", "w"}]} (members:
    the file's references in order, kind "" for one Reelwright cannot send)."""
    v = v if isinstance(v, dict) else {}
    out = {"name": refmod_name(v.get("name")), "strength": min(1.0, max(0.0, spec.num(v.get("strength"), 1.0))),
           "members": []}
    for m in _objects(v.get("members"))[:REFMOD_MAX_MEMBERS]:
        kind = m.get("kind") if m.get("kind") in REFMOD_KINDS else ""
        audio = kind == "audio"
        out["members"].append({"kind": kind, "t": max(1, int(spec.num(m.get("t"), 1))),
                               "h": 0 if audio else max(0, int(spec.num(m.get("h"), 0))),
                               "w": 0 if audio else max(0, int(spec.num(m.get("w"), 0)))})
    return out


def refmod_parts(r, visual):
    """[(member index, member)] of RefMod r that go to H3: its pictures and videos (visual) or its audio; none
    without a name or at strength 0."""
    if not isinstance(r, dict) or not r.get("name") or not spec.num(r.get("strength"), 0.0) > 0:
        return []
    kinds = ("image", "video") if visual else ("audio",)
    return [(i, m) for i, m in enumerate(r.get("members") or []) if isinstance(m, dict) and m.get("kind") in kinds]


def look_parts(c, entry=None):
    """The look RefMod members cast member c sends in a scene (its cast entry): none when the scene unticks it."""
    if REFMOD_SKIP in entry_skip(entry):
        return []
    return refmod_parts((c or {}).get("refmod"), True)


def voice_parts(c):
    """The voice RefMod members c sends instead of its voice sample."""
    return refmod_parts((c or {}).get("voice_refmod"), False)


def refmod_frames(t):
    """Pixel frames of t video latent frames (H3: 1 frame, then 4 per latent, the 1 again every 5th)."""
    t = max(0, int(t))
    return (t + 4) // 5 + 4 * (t - (t + 4) // 5)


def refmod_seconds(m):
    """How long a RefMod member counts in H3's 15 s of video or audio references."""
    if m.get("kind") == "video":
        return refmod_frames(m["t"]) / spec.FPS
    if m.get("kind") == "audio":
        return m["t"] / float(REFMOD_AUDIO_RATE)
    return 0.0


def refmod_tokens(m):
    """Reference tokens of a RefMod member in the DiT (pictures and videos: t x h/2 x w/2; audio: 2 per frame)."""
    if m.get("kind") == "audio":
        return 2 * m["t"]
    return m["t"] * (m["h"] // 2) * (m["w"] // 2)


def refmod_entry(r, i, m):
    """What a pass build holds for one RefMod member it sends (render and the cache key read it)."""
    return {"name": r["name"], "member": i, "kind": m["kind"], "t": m["t"], "h": m["h"], "w": m["w"],
            "strength": r["strength"]}


def cast_pictures(c, entry, assets, look=False):
    """(outfit, picture ids) a cast member sends in a scene: its anchor pictures, then the pictures of the outfit the
    scene entry gives it (else its default outfit) that are not anchors already. Images only. look: the cast member
    sends its look RefMod here, so its anchors stay out (the outfit's pictures still go)."""
    outfit = next((o for o in c["outfits"] if o["id"] == ((entry or {}).get("outfit") or c["default_outfit"])), None)
    skip = entry_skip(entry)
    ids = [] if look else [a for a in c["anchors"] if a in assets and assets[a]["kind"] == "image" and a not in skip]
    if outfit:
        ids += [a for a in outfit["assets"] if a in assets and assets[a]["kind"] == "image" and a not in ids]
    return outfit, ids


# ---- video anchors of a cast member (cast.video_anchors). H3 can define a subject by a video
# as well as by pictures (ref-en.txt 2.1: "<Subject 1> is the man in <Video 1>"), so a character's clips show how it
# moves, talks and looks from every side. They go to every pass of a scene the character is in, after everything else
# the pass sends, while H3's budget has room: 3 videos, 15 s of video in all, 12 files; a clip is shortened to the
# seconds left when at least 2 s are. Its sound goes too only when asked and an audio slot (and 15 s of audio) is free.
# prompt.collect_refs sends them; scene_media_counts counts them; model.js pickVideoAnchors is the same.
def video_anchors_of(c, assets):
    """[(anchor, asset)]: c's video anchors whose asset is a video of the project, in order."""
    return [(va, assets[va["asset"]]) for va in c.get("video_anchors") or []
            if va.get("asset") in assets and assets[va["asset"]]["kind"] == "video"]


def pick_video_anchors(recs, assets, n):
    """The video anchors one pass sends after everything else. recs: scene_people records (cast members that are no
    part), in order; n: the pass's counts so far ({"videos", "video_seconds", "audio", "audio_seconds", "files"}),
    updated with what is picked. Returns (picked, left):
    picked: [{"cast", "anchor", "asset", "in", "seconds", "sound", "cut", "mute"}] (cut: shortened to the seconds
    left; mute: its sound was asked for but no audio slot was free); left: [{"cast", "anchor", "asset", "why"}], why
    "videos" | "files" | "seconds" (under 2 s left) | "clip" (the clip has no length) | "short" (a clip under 2 s,
    )."""
    picked, left = [], []
    for x in recs:
        c = x["cast"]
        if x.get("look"):  # its look RefMod goes instead of its anchors
            continue
        skip = entry_skip(x.get("entry"))
        for va, a in video_anchors_of(c, assets):
            if va["id"] in skip:
                continue
            clip = ref_clip(va, a)
            full = min(spec.REF_MEDIA_MAX_SECONDS, clip["seconds"] if clip["seconds"] is not None else
                       spec.REF_MEDIA_MAX_SECONDS)
            room = spec.REF_MEDIA_TOTAL_SECONDS - n["video_seconds"]
            secs = full if full <= room + 1e-6 else math.floor(room * spec.FPS + 1e-6) / spec.FPS
            cut = secs < full - 1e-6
            why = ("clip" if full <= 0 else "short" if full < spec.REF_MEDIA_MIN_SECONDS - 1e-6 else
                   "videos" if n["videos"] >= spec.MAX_REF_VIDEOS else
                   "files" if n["files"] >= spec.MAX_REF_FILES else
                   "seconds" if secs <= 0 or (cut and secs < spec.REF_MEDIA_MIN_SECONDS - 1e-6) else "")
            if why:
                left.append({"cast": c["id"], "anchor": va["id"], "asset": a["id"], "why": why})
                continue
            sound = bool(va.get("soundtrack")) and n["audio"] < spec.MAX_REF_AUDIOS and \
                n["audio_seconds"] + secs <= spec.REF_MEDIA_TOTAL_SECONDS + 1e-4
            n["videos"] += 1
            n["files"] += 1
            n["video_seconds"] += secs
            if sound:
                n["audio"] += 1
                n["audio_seconds"] += secs
            picked.append({"cast": c["id"], "anchor": va["id"], "asset": a["id"], "in": clip["start"], "seconds": secs,
                           "sound": sound, "cut": cut, "mute": bool(va.get("soundtrack")) and not sound})
    return picked, left


# ---- how big one picture of a packed anchor sheet reaches H3 (model.js tilePixels gives the
# same number). The sheet is ceil(sqrt(n)) columns of 768-pixel cells shaped like the median picture (media.sheet_image);
# the H3 node scales the whole sheet down to the output's pixel area ("match") or to a 2048 px short edge ("max").
SHEET_CELL = 768
SMALL_TILE_PX = 300  # under this a face in the sheet is too small for a reliable identity


def sheet_grid(n):
    """Columns and rows of a sheet of n pictures (as media.sheet_grid)."""
    cols = max(1, math.ceil(math.sqrt(n)))
    return cols, max(1, math.ceil(n / cols))


def tile_pixels(pics, width, height, ref_size="match"):
    """About how many pixels the short side of one picture of a sheet of `pics` (assets with width / height) has when
    H3 gets it, at an output of width x height; 0 without pictures."""
    if not pics:
        return 0
    ratios = sorted(max(0.5, min(2.0, (spec.num(a.get("width"), 0) or 1) / (spec.num(a.get("height"), 0) or 1)))
                    for a in pics)
    r = ratios[len(ratios) // 2]
    cols, rows = sheet_grid(len(pics))
    cw, ch = SHEET_CELL * math.sqrt(r), SHEET_CELL / math.sqrt(r)
    w, h = cols * cw, rows * ch
    scale = min(1.0, 2048.0 / min(w, h)) if ref_size == "max" else min(1.0, math.sqrt(width * height / (w * h)))
    return int(math.floor(min(cw, ch) * scale + 0.5))


def scene_people(p, scene, idx=None):
    """The cast a scene sends, as prompt.collect_refs and scene_media_counts use it: its cast list plus the speakers
    missing from it, in that order. Returns (people, left_out):
    people: [{"entry", "cast", "outfit", "own", "ids", "parts", "look"}], one per cast member that is no part. own:
    its pictures (cast_pictures); ids: own, then the pictures of its parts in this scene that are not in it yet.
    parts: [{"entry", "cast", "outfit", "ids"}] (ids: all of that part's pictures). look: look_parts, the RefMod
    members it sends instead of its anchors ([] for none).
    left_out: [(part, owner)] for the props in the scene that are part of a character who is not in it."""
    idx = idx or project_index(p)
    assets, cast = idx["assets"], idx["cast"]
    entries = list(scene["cast"])
    for d in scene["dialogue"]:  # a speaker who is not in the scene's cast list still gets anchors
        if d.get("speaker") in cast and not any(e["id"] == d["speaker"] for e in entries):
            entries.append({"id": d["speaker"], "outfit": ""})
    present = {e["id"] for e in entries if e["id"] in cast}
    people, parts, left_out = [], {}, []
    for e in entries:
        c = cast.get(e["id"])
        if not c:
            continue
        owner = part_owner(c, cast)
        look = [] if owner else look_parts(c, e)
        outfit, ids = cast_pictures(c, e, assets, bool(look))
        if owner:
            if owner in present:
                parts.setdefault(owner, []).append({"entry": e, "cast": c, "outfit": outfit, "ids": ids})
            else:
                left_out.append((c, cast[owner]))
            continue
        people.append({"entry": e, "cast": c, "outfit": outfit, "own": ids, "ids": ids, "parts": [], "look": look})
    for x in people:
        for part in parts.get(x["cast"]["id"], []):
            x["parts"].append(part)
            x["ids"] = x["ids"] + [a for a in part["ids"] if a not in x["ids"]]
    return people, left_out


# ---- clips of video and audio references: the same asset can be a reference of a scene several times, each with
# its own From / To and with or without its sound. model.js has the same functions (snapFrame, refClip, refTrimmed,
# refTokens; tests/test_model_parity.py compares them).

def snap_frame(t):
    """t seconds on the nearest whole frame (half a frame rounds up, as Math.round in the editor)."""
    return math.floor(float(t) * spec.FPS + 0.5) / spec.FPS


def ref_trimmed(r):
    """Does reference r send only part of its asset (a From after 0 or a To)?"""
    return isinstance(r, dict) and (spec.num(r.get("in"), 0.0) > 0 or spec.num(r.get("out"), 0.0) > 0)


def ref_clip(r, a):
    """{"start", "end", "seconds"} of the part of video or audio asset `a` that reference r sends: start = its From,
    end = its To, else the asset's end, never past the asset's end; seconds = end - start (0 when it ends before it
    starts). end and seconds are None when neither a To nor the asset's length is known."""
    start = max(0.0, spec.num((r or {}).get("in"), 0.0))
    o = spec.num((r or {}).get("out"), 0.0)
    dur = spec.num((a or {}).get("duration"), 0.0)
    end = o if o > 0 else (dur if dur > 0 else None)
    if end is not None and dur > 0:
        end = min(end, dur)
    return {"start": start, "end": end, "seconds": None if end is None else max(0.0, end - start)}


def clip_key(r, a):
    """What makes two references the same clip: (asset id, start, end), end None for a reference that is not trimmed
    (so it matches a cast voice sample, which is always the whole file)."""
    c = ref_clip(r, a)
    return (a["id"], c["start"], c["end"] if ref_trimmed(r) else None)


def media_ref_ids(scene, aid):
    """Ids of the scene's reference-role references on asset aid, in the scene's order: @V1 names the first, @V1.2
    the second and so on."""
    return [r.get("id") for r in (scene or {}).get("refs") or [] if isinstance(r, dict) and r.get("asset") == aid
            and r.get("role", "reference") == "reference"]


def ref_tokens(p, scene, idx=None):
    """{ref id: "@V1" | "@V1.2"} for the scene's video and audio references: the first reference of an asset is its
    code, the next ones its code with .2, .3 ..."""
    idx = idx or project_index(p)
    out, seen = {}, {}
    for r in (scene or {}).get("refs") or []:
        a = idx["assets"].get(r.get("asset"))
        if not a or a.get("kind") not in ("video", "audio") or r.get("role", "reference") != "reference" or not a.get("code"):
            continue
        n = seen[a["id"]] = seen.get(a["id"], 0) + 1
        out[r["id"]] = "@" + a["code"] + ("" if n == 1 else ".{}".format(n))
    return out


def pose_in_pass(t, pass_, duration):
    """Does scene time t fall in this pass (start <= t < end; a time at or after the end of the last pass counts for
    it)? Overlapping passes both hold the overlap."""
    s, e = float(pass_["start"]), float(pass_["end"])
    return s <= t < e or (t >= e and e >= float(duration) - 1e-6)


def pose_time(r, scene):
    """A pose reference's time, kept inside the scene."""
    return min(max(float(r.get("time") or 0.0), 0.0), float(scene["duration"]))


def pose_refs(p, scene, pass_=None, people=None, idx=None):
    """The pose references a scene sends: [(ref, asset, character)] where the asset is a picture and the character is
    one the scene sends (scene_people, not a part). pass_: only those whose time falls in that pass. people: the
    first result of scene_people when you have it."""
    idx = idx or project_index(p)
    if people is None:
        people = scene_people(p, scene, idx)[0]
    chars = {x["cast"]["id"]: x["cast"] for x in people if x["cast"].get("kind") == "character"}
    out = []
    for r in scene["refs"]:
        if r.get("role") != "pose":
            continue
        a = idx["assets"].get(r.get("asset"))
        c = chars.get(r.get("cast") or "")
        if not a or a["kind"] != "image" or not c:
            continue
        if pass_ is not None and not pose_in_pass(pose_time(r, scene), pass_, scene["duration"]):
            continue
        out.append((r, a, c))
    return out


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
            base = int(sm["seed"]) + scene_seed_n(scene, scene_index)
    return (base + take_number * 1000003) % (2 ** 63)


def _lora_entries(p, scene):
    """The LoRAs a scene is sampled with, in application order: global stack (with per-scene strength overrides),
    scene LoRAs, the identity LoRAs of its cast, the draft LoRA. One entry per file: a later one sets the strength
    (a scene item can retune a global LoRA) and, when it has one, the trigger. [{name, strength, trigger, cast}]."""
    g = p["global"]
    ov = scene["overrides"].get("loras") or {}
    mode = ov.get("mode", "add")
    strengths = ov.get("strengths") or {}
    out = []
    if mode != "replace":
        for l in g["loras"]:
            if l.get("enabled", True) and l.get("name"):
                out.append((l["name"], float(strengths.get(l["id"], l["strength"])), l.get("trigger") or "", None))
    for l in ov.get("items") or []:
        if l.get("enabled", True) and l.get("name"):
            out.append((l["name"], float(l["strength"]), l.get("trigger") or "", None))
    cast = project_index(p)["cast"]
    for sc in scene["cast"]:
        c = cast.get(sc["id"])
        if c and c["lora"].get("name"):
            out.append((c["lora"]["name"], float(c["lora"]["strength"]), c["lora"].get("trigger") or "", c["id"]))
    if scene_quality(p, scene) == "draft" and g["draft"].get("lora"):
        out.append((g["draft"]["lora"], float(g["draft"]["lora_strength"]), g["draft"].get("lora_trigger") or "", None))
    seen = {}
    for name, strength, trigger, cast_id in out:
        e = seen.setdefault(name, {"name": name, "strength": strength, "trigger": "", "cast": None})
        e["strength"] = strength
        if trigger:
            e["trigger"], e["cast"] = trigger, cast_id
    return list(seen.values())


def effective_loras(p, scene):
    """Ordered [(name, strength)] for a scene: global stack (with per-scene strength
    overrides), scene LoRAs, draft LoRA and the identity LoRAs of its cast."""
    return [(e["name"], e["strength"]) for e in _lora_entries(p, scene)]


def lora_triggers(p, scene):
    """[{trigger, cast}] of the scene's LoRAs that have a trigger word, in application order, each word once (cast:
    the character whose identity LoRA it is, else None). The prompt builder writes the ones a pass's prompt lacks
    (prompt.lora_trigger_words)."""
    out, seen = [], set()
    for e in _lora_entries(p, scene):
        key = e["trigger"].lower()
        if e["trigger"] and key not in seen:
            seen.add(key)
            out.append({"trigger": e["trigger"], "cast": e["cast"]})
    return out


def scene_quality(p, scene):
    """"draft" or "final": the scene's own choice, else Global."""
    q = (scene.get("overrides") or {}).get("quality")
    return q if q in ("draft", "final") else p["global"]["quality"]


# ---- Global -> Hires (the latent upscaler). model.js hiresSize / sceneHires are the same.
HIRES_MAX_SCALE = 4.0


def _snap32(v):
    """v on H3's 32-pixel canvas grid, half up (model.js snap32; spec.snap_canvas rounds half to even)."""
    return max(spec.CANVAS_MULTIPLE, int(math.floor(float(v) / spec.CANVAS_MULTIPLE + 0.5)) * spec.CANVAS_MULTIPLE)


def hires_size(g):
    """The size every take of the project ends at: Global -> Output x Hires scale on the 32-pixel grid while Hires is
    on (with a scale above 1), else Global -> Output. g: the project's global settings."""
    w, h = int(g["output"]["width"]), int(g["output"]["height"])
    hi = g.get("hires") or {}
    if not hi.get("enabled") or float(hi.get("scale") or 1.0) <= 1.0:
        return w, h
    s = float(hi["scale"])
    return _snap32(w * s), _snap32(h * s)


def project_output_size(p):
    """The merged film's size (assemble.merge_project): hires_size of the project."""
    return hires_size(p["global"])


def scene_hires(p, scene, width, height, quality):
    """What the latent upscaler does to a scene sampled at width x height with this quality, or None (Hires off, the
    scene turns it off, a draft while Global -> Draft -> hires is off, or nothing to enlarge): {"model", "width",
    "height"} (the size it is enlarged to: the scene's size fitted into hires_size, on the grid) plus "refine_steps" /
    "refine_denoise" when the big latent is sampled again (never for a draft). Only present keys change cache keys."""
    g = p["global"]
    hi = g["hires"]
    o = scene.get("overrides") or {}
    if not hi.get("enabled") or o.get("hires") == "off" or (quality == "draft" and not g["draft"].get("hires")):
        return None
    fw, fh = hires_size(g)
    s = min(fw / float(width), fh / float(height))
    if s <= 1.0 + 1e-9:
        return None
    tw, th = min(fw, _snap32(width * s)), min(fh, _snap32(height * s))
    out = {"model": g["models"].get("latent_upscaler") or "", "width": tw, "height": th}
    steps = int(o["refine_steps"]) if o.get("refine_steps") is not None else int(hi["refine_steps"])
    if quality != "draft" and steps > 0:
        d = o.get("refine_denoise")
        out["refine_steps"] = steps
        out["refine_denoise"] = round(float(d if d is not None else hi["refine_denoise"]), 4)
    return out


def resolve_settings(p, scene, scene_index):
    """Everything the renderer needs for one scene, with overrides and quality applied."""
    g = p["global"]
    o = scene["overrides"]
    m = g["models"]
    s = g["sampling"]
    width = int(o.get("width") or g["output"]["width"])
    height = int(o.get("height") or g["output"]["height"])
    steps = int(o.get("steps") or s["steps"])
    quality = scene_quality(p, scene)
    if quality == "draft":
        width, height = spec.snap_canvas(width * g["draft"]["scale"], height * g["draft"]["scale"])
        steps = int(g["draft"]["steps"])
    out = {
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
        "quality": quality,
    }
    hires = scene_hires(p, scene, width, height, quality)
    if hires:
        out["hires"] = hires
    return out


def scene_overlap(scene, index):
    """DEPRECATED: use scene_overlap_at(p, i), which knows the scene before (a tail is capped by
    its length) and the re-anchor rule (a re-anchored tail overlaps one frame). Kept unchanged for callers that have
    not switched yet.

    Seconds at the start of a scene that repeat the end of the scene before: the tail
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


# ---- how scenes join (model.js has the same functions, tests/test_model_parity.py) -----------------------------
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


# ---- reference budget (model.js sceneBudget gives the same numbers) -----------------------------
COUNT_KEYS = ("pictures", "videos", "video_seconds", "audio", "audio_seconds", "files")


# ---- the continuation as a named reference (model.js passContinuation / continuationFrames are the same,
# tests/test_model_parity.py) ----
def pass_continuation(p, i, pass_, mode=None):
    """What pass_ (a planner pass) of scene i sends as reference 1 for the footage it continues from, when Global ->
    Continuity -> name_continuation is on: "picture" (pass 1 of a last-frame start, a re-anchored tail too: the last
    frame of the scene before is <Picture 1>), "video" (pass 1 of a tail start: the tail clip of the scene before is
    <Video 1>; a later pass after an overlap seam: the end of the pass before), else "". The same passes get the
    MiniMaxH3AddGuide anchors (prompt.collect_refs). mode: effective_start(p, i) when the caller has it."""
    if not spec.flag(((p.get("global") or {}).get("continuity") or {}).get("name_continuation", True), True):
        return ""
    if int(spec.num(pass_.get("index"), 1)) > 1:
        seam_ref = spec.flag(((p.get("global") or {}).get("long") or {}).get("seam_video_ref", True), True)
        return "video" if pass_.get("seam_before") == "overlap" and seam_ref else ""
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


def scene_media_counts(p, scene, pass_=None, starts=None, mode=None, continuation=True, video_anchors=True):
    """What one pass of `scene` sends H3, counted the way prompt.collect_refs presents references:

    pictures       cast anchors (+ outfit pictures; a packed sheet is 1) and reference pictures, each asset once; the
                   pictures of a look RefMod (instead of the anchors)
    videos         reference videos and the videos of a look RefMod;   video_seconds: their length
    audio          voice samples (or voice RefMods) of cast members who speak IN THIS PASS (left out when the song is sent),
                   reference audio, one slot per reference video whose sound is used, and the soundtrack segment
                   when soundtrack.pass_soundtrack gives one;   audio_seconds: their length
    files          pictures + videos + audio files (a video's own sound is not a separate file)
    song           True when the pass gets the soundtrack

    pass_ is a planner pass (needs start, gen_frames, dialogue). pass_=None plans the scene and returns, for each
    count, the most any of its passes uses (song: any pass). starts: scene_starts(p)[0] if you have it already.
    Guide pictures (first/last frame, keyframes) that the prompt text names are not counted.

    The continuation reference (pass_continuation) counts too, as one picture or one video
    (plus an audio slot for its sound when one is free); continuation: "picture" | "video" | "video_audio" (with its
    sound) | "" says which (pass_=None: the first pass that has one). A continuation picture counts for "auto"
    packing; one that still does not fit (pictures <= 9, videos <= 3, files <= 12) is left out, and the pass counts as
    in v0.6.1. mode: effective_start of the scene when known; continuation=False counts as v0.6.1 did."""
    if pass_ is None:
        from .planner import plan_scene  # planner imports model
        i = next((k for k, s in enumerate(p["scenes"]) if s["id"] == scene["id"]), 0)
        outs = [scene_media_counts(p, scene, x, starts, mode, continuation, video_anchors)
                for x in plan_scene(p, scene, i)["passes"]]
        out = {k: max(o[k] for o in outs) for k in COUNT_KEYS}
        out["song"] = any(o["song"] for o in outs)
        out["continuation"] = next((o["continuation"] for o in outs if o["continuation"]), "")
        return out
    idx = project_index(p)
    assets = idx["assets"]
    recs = scene_people(p, scene, idx)[0]
    people = [(x["cast"], x["ids"], x["look"]) for x in recs]
    anchors = {a for _, ids, _ in people for a in ids}
    look_pics = sum(1 for *_, look in people for _, m in look if m["kind"] == "image")
    ref_pics = {r["asset"] for r in scene["refs"]
                if r["role"] == "reference" and r["asset"] in assets and assets[r["asset"]]["kind"] == "image"}
    pose_pics = list(dict.fromkeys(a["id"] for _, a, _ in pose_refs(p, scene, pass_, recs, idx)))
    i = next((k for k, s in enumerate(p["scenes"]) if s["id"] == scene["id"]), None)
    cont = pass_continuation(p, i, pass_, mode) if continuation else ""
    auto_pack = len(anchors) + look_pics + len((ref_pics | set(pose_pics)) - anchors) + (1 if cont == "picture" else 0) > \
        spec.MAX_REF_IMAGES
    if starts is None:
        starts = scene_starts(p)[0]
    song = _soundtrack.pass_soundtrack(p, starts.get(scene["id"], 0.0), pass_)
    speaking = {d.get("speaker") for d in pass_.get("dialogue") or []}
    out = {"pictures": 0, "videos": 0, "video_seconds": 0.0, "audio": 0, "audio_seconds": 0.0, "files": 0,
           "song": bool(song)}
    sent, sounds, mod_sounds = set(), [], []
    for c, ids, look in people:
        pack = not look and (auto_pack if c.get("pack_sheet", True) == "auto" else bool(c.get("pack_sheet", True)))
        out["pictures"] += 1 if ids and pack and len(ids) > 1 else len(ids)
        sent.update(ids)
        for _, m in look:
            if m["kind"] == "image":
                out["pictures"] += 1
            else:
                out["videos"] += 1
                out["video_seconds"] += refmod_seconds(m)
        if not song and c["id"] in speaking:
            voice = voice_parts(c)
            v = assets.get(c.get("voice"))
            if voice:
                mod_sounds += [refmod_seconds(m) for _, m in voice]
            elif v and v["kind"] == "audio":
                sounds.append(v)
    for aid in pose_pics:
        if aid not in sent:
            sent.add(aid)
            out["pictures"] += 1
    sounds = [((a["id"], 0.0, None), float(a.get("duration") or 0)) for a in sounds]
    for r in scene["refs"]:
        a = assets.get(r["asset"])
        if not a or r["role"] != "reference":
            continue
        if a["kind"] == "image":
            if a["id"] not in sent:
                sent.add(a["id"])
                out["pictures"] += 1
        elif a["kind"] == "video":
            secs = ref_clip(r, a)["seconds"] or 0.0
            out["videos"] += 1
            out["video_seconds"] += secs
            if r.get("soundtrack"):  # the video's sound takes an <Audio j> slot of its own
                out["audio"] += 1
                out["audio_seconds"] += secs
        elif a["kind"] == "audio":
            key = clip_key(r, a)
            if not any(x[0] == key for x in sounds):
                sounds.append((key, ref_clip(r, a)["seconds"] or 0.0))
    out["audio"] += len(sounds) + len(mod_sounds) + (1 if song else 0)
    for _, secs in sounds:
        out["audio_seconds"] += secs
    out["audio_seconds"] += sum(mod_sounds)
    if song:
        out["audio_seconds"] += song["length"]
    out["files"] = out["pictures"] + out["videos"] + len(sounds) + len(mod_sounds) + (1 if song else 0)
    out["continuation"] = ""
    if cont == "picture":
        if out["pictures"] + 1 > spec.MAX_REF_IMAGES or out["files"] + 1 > spec.MAX_REF_FILES:
            return scene_media_counts(p, scene, pass_, starts, mode, continuation=False, video_anchors=video_anchors)
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
    if video_anchors:
        pick_video_anchors(recs, assets, out)
    return out


# ---- camera wording, dialogue length, per-pass prompt sections (model.js has the same functions: cameraSentence,
# framingPhrase, dialogueSeconds, dialogueSpans, passTexts, relayoutPassTexts, passSections;
# tests/test_model_parity.py compares them) ----

def framing_phrase(framing):
    """"close-up" -> "a close-up", "low angle" -> "a low-angle shot"; "" for no framing (FRAMINGS)."""
    return FRAMING_PHRASE.get(framing, "") if isinstance(framing, str) else ""


# A shot whose camera is just an official move's name ("Push In", "tracking
# shot", "POV") is written with that move's phrase ("the camera pushes in"), not as the name
_MOVE_BY_NAME = {n.lower(): t for n, t in DEFAULT_CAMERA}


def official_camera(camera):
    """The phrase of an official H3 camera move when `camera` is just its name (any case, an end stop allowed),
    else the text unchanged."""
    t = spec.text(camera)
    return _MOVE_BY_NAME.get(t.strip(" \t\n\r").rstrip(".").strip().lower(), t)


def camera_sentence(camera, amp="", speed=""):
    """A shot's camera text as one sentence in the form of H3's guide (base-en.txt 4.3): "the camera pushes in" with
    amp "small" and speed "slow" -> "The camera pushes in with small amplitude at slow speed." Medium amplitude and
    normal speed ("") are not written; hand-written text works the same way. "" when there is no camera text."""
    t = official_camera(camera).strip(" \t\n\r")
    extra = (" with {} amplitude".format(amp) if amp in ("small", "large") else "") + \
            (" at {} speed".format(speed) if speed in ("slow", "fast") else "")
    if extra:
        t = t.rstrip(" \t\n\r.!?")
        t = t + extra if t else ""
    if not t:
        return ""
    t = t[:1].upper() + t[1:]
    return t if t[-1] in ".!?\"'" else t + "."


# a dialogue line's length when it has none: the words at 2.5 a second, CJK characters (Han, kana, Hangul) counting
# as a quarter word each; at least 1 s
CJK_RANGES = ((0x1100, 0x11FF), (0x3040, 0x30FF), (0x3130, 0x318F), (0x31F0, 0x31FF), (0x3400, 0x4DBF),
              (0x4E00, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF), (0xFF66, 0xFF9F), (0x20000, 0x2FFFF))
WORDS_PER_SECOND = 2.5
CJK_PER_WORD = 4
SPACES_RE = re.compile("[ \t\n\r\f\v\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+")


def _is_cjk(cp):
    return any(a <= cp <= b for a, b in CJK_RANGES)


def dialogue_seconds(d):
    """How long dialogue line d is spoken: its duration (seconds > 0), else max(1.0, words / 2.5), where words are
    the runs between spaces that hold a letter or digit, plus the CJK characters / 4."""
    d = d if isinstance(d, dict) else {}
    dur = spec.num(d.get("duration"), None)
    if dur is not None and dur > 0:
        return float(min(dur, DIALOGUE_MAX_SECONDS))
    cjk, rest = 0, []
    for ch in spec.text(d.get("text")):
        if _is_cjk(ord(ch)):
            cjk += 1
            rest.append(" ")
        else:
            rest.append(ch)
    words = sum(1 for w in SPACES_RE.split("".join(rest))
                if any(unicodedata.category(c)[0] in ("L", "N") for c in w))
    return max(1.0, (words + cjk / CJK_PER_WORD) / WORDS_PER_SECOND)


def dialogue_spans(scene, plan):
    """Where each dialogue line of the scene is spoken, in the scene's order: [{"id", "pass" (1-based; None when the
    line is in no pass), "start", "end" (scene seconds; start is where the planner put it), "seconds",
    "estimated" (no duration given), "seam" (scene time of the pass seam the line runs past, else None),
    "past_end" (it runs past the scene's end)}]. plan: planner.plan_scene of the scene."""
    where = {}
    for x in plan["passes"]:
        for d in x["dialogue"]:
            where.setdefault(d.get("id"), (x, d))
    n = len(plan["passes"])
    out = []
    for d in scene["dialogue"]:
        seconds = dialogue_seconds(d)
        given = spec.num(d.get("duration"), None)
        hit = where.get(d.get("id"))
        start = hit[0]["start"] + hit[1]["t"] if hit else spec.num(d.get("t"), 0.0)
        end = start + seconds
        seam = hit[0]["end"] if hit and hit[0]["index"] < n and end > hit[0]["end"] + 1e-6 else None
        out.append({"id": d.get("id"), "pass": hit[0]["index"] if hit else None, "start": start, "end": end,
                    "seconds": seconds, "estimated": not (given is not None and given > 0), "seam": seam,
                    "past_end": end > float(plan["duration"]) + 1e-6})
    return out


FRAME_SECONDS = 1.0 / spec.FPS


def empty_sections():
    return {k: "" for k in SECTION_KEYS}


def _entry_sections(x):
    sec = x.get("sections") if isinstance(x, dict) and isinstance(x.get("sections"), dict) else {}
    return {k: spec.text(sec.get(k)) for k in SECTION_KEYS}


def _close(a, b):
    """Two (start, end) ranges within a frame of each other."""
    return abs(a[0] - b[0]) <= FRAME_SECONDS + 1e-9 and abs(a[1] - b[1]) <= FRAME_SECONDS + 1e-9


def _plan_of(p, scene, plan):
    if plan is not None:
        return plan
    from .planner import plan_scene  # planner imports model
    i = next((k for k, s in enumerate(p["scenes"]) if s is scene or s.get("id") == scene.get("id")), 0)
    return plan_scene(p, scene, i)


def pass_texts(p, scene, plan=None):
    """The six sections written for each pass of the scene's CURRENT layout (scene.prompt.passes, stored with the
    start / end the pass had when they were written). When the stored ranges match the layout (within a frame;
    entries without text and a one-pass scene always match), entry k is pass k. Otherwise each pass gets the text of
    the stored entry it overlaps most in time, each entry used once (largest overlap first).
    Returns {"texts": [six sections per current pass], "moved": [1-based passes whose text was written for another
    range], "unused": [1-based stored entries with text that no pass gets], "same": the layout matches,
    "stored": any entry has text, "entry": [per current pass, the 1-based stored entry its text comes from, or None]}."""
    plan = _plan_of(p, scene, plan)
    raw = (scene.get("prompt") or {}).get("passes")
    stored = [x if isinstance(x, dict) else {} for x in raw] if isinstance(raw, list) else []
    secs = [_entry_sections(x) for x in stored]
    has = [any(not _blank(v) for v in s.values()) for s in secs]
    ranges = [(spec.num(x.get("start"), 0.0), spec.num(x.get("end"), 0.0)) for x in stored]
    cur = [(x["start"], x["end"]) for x in plan["passes"]]
    n = len(cur)
    if n == 1:
        same = not any(has[1:])
    else:
        same = all(not has[j] or (j < n and _close(ranges[j], cur[j])) for j in range(len(stored)))
    if same:
        texts = [dict(secs[k]) if k < len(stored) else empty_sections() for k in range(n)]
        return {"texts": texts, "moved": [], "unused": [], "same": True, "stored": any(has),
                "entry": [k + 1 if k < len(stored) and has[k] else None for k in range(n)]}
    pairs = []
    for k, (a, b) in enumerate(cur):
        for j, (c, d) in enumerate(ranges):
            if has[j]:
                ov = min(b, d) - max(a, c)
                if ov > 1e-9:
                    pairs.append((-ov, k, j))
    pairs.sort()
    take, used = {}, set()
    for _, k, j in pairs:
        if k not in take and j not in used:
            take[k] = j
            used.add(j)
    texts = [dict(secs[take[k]]) if k in take else empty_sections() for k in range(n)]
    moved = [k + 1 for k in range(n) if k in take and not _close(ranges[take[k]], cur[k])]
    unused = [j + 1 for j in range(len(stored)) if has[j] and j not in used]
    return {"texts": texts, "moved": moved, "unused": unused, "same": False, "stored": any(has),
            "entry": [take[k] + 1 if k in take else None for k in range(n)]}


def relayout_pass_texts(p, scene, plan=None):
    """scene.prompt.passes for the current layout ("Use the new layout"): one entry per pass with its start / end
    and the text pass_texts gives it (text no pass gets is dropped)."""
    plan = _plan_of(p, scene, plan)
    texts = pass_texts(p, scene, plan)["texts"]
    return [{"start": float(x["start"]), "end": float(x["end"]), "sections": texts[k]}
            for k, x in enumerate(plan["passes"])]


def pass_sections(p, scene, plan, k):
    """What pass k (1-based) of a structured prompt is built from: {"own": the six sections written for it
    (pass_texts), "used": the text each section is built from, "source": {section: "pass" (its own), "scene" (the
    scene's, shared by every pass), "auto" (the summary: made by the prompt builder; a multi-pass scene never sends
    the scene summary), "split" (detailed_description of a multi-pass scene: the scene's [Shot N] lines of this
    pass)}}. prompt.build_pass uses it."""
    plan = _plan_of(p, scene, plan)
    n = len(plan["passes"])
    texts = pass_texts(p, scene, plan)["texts"]
    own = texts[k - 1] if 1 <= k <= n else empty_sections()
    sec = _entry_sections(scene.get("prompt") or {})
    used, source = {}, {}
    for key in SECTION_KEYS:
        if not _blank(own[key]):
            used[key], source[key] = own[key], "pass"
        elif key == "summary" and (n > 1 or _blank(sec[key])):
            used[key], source[key] = "", "auto"
        elif key == "detailed_description" and n > 1:
            used[key], source[key] = sec[key], "split"
        else:
            used[key], source[key] = sec[key], "scene"
    return {"own": own, "used": used, "source": source}
