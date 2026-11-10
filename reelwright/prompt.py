"""Per-pass prompt assembly and reference numbering.

The editor refers to assets as @P1 / @V2 / @A1, to cast as @Mara or
@{Old Keeper}, and to the continuation as @tail. Each pass gets its own
numbering in the order MiniMaxH3ReferenceToVideo presents references:
images, then videos (a video's soundtrack takes its <Audio j> number right
before its <Video k>), then standalone audio.
"""

import functools
import itertools
import os
import re
import unicodedata

from . import model as _model
from . import soundtrack, spec
from .model import cast_description, project_index, scene_starts
from .planner import continuation_depth

# ---- tag syntax (same rule as the editor's prompttext.js / model.js) ---------------------------------------------
# A tag is "@" + a name: runs of Unicode letters, digits, combining marks and "_", joined by single ' ’ - or .
# ("@Anna." is "Anna"; "@O'Brien" and "@Ömer" are whole names). "@{Two Words}" names a cast member with spaces.
# An "@" right after a letter, digit, "_" or "@" starts no tag, so e-mail addresses stay text; "@@" is a literal "@".
# The patterns are built on first use: listing every combining mark takes about 40 ms.

def _mark_class():
    """Every combining mark (Unicode category M) as regex class ranges. Python's \\w has no marks; the editor's
    \\p{M} has them, so "@अनुज" is one tag in both."""
    out, start, last = [], None, None
    cat = unicodedata.category
    for cp in itertools.chain(range(0x300, 0x20000), range(0xE0100, 0xE01F0)):
        if cat(chr(cp))[0] == "M":
            if start is None:
                start = cp
            last = cp
        elif start is not None:
            out.append((start, last))
            start = None
    if start is not None:
        out.append((start, last))
    return "".join("\\U{:08x}".format(a) + ("-\\U{:08x}".format(b) if b > a else "") for a, b in out)


@functools.lru_cache(maxsize=None)
def _patterns():
    marks = _mark_class()
    word = "[\\w" + marks + "]"
    name = word + "+(?:['’.\\-]" + word + "+)*"
    tag = "(?<![\\w" + marks + "@])@(?:\\{([^}\\n]+)\\}|(?!@)(" + name + "))"
    # group 1: the name inside @{...}; group 2: a plain name
    return {"TAG_RE": re.compile(tag), "TAG_OR_ESCAPE": re.compile("@@|" + tag), "NAME_RE": re.compile(name)}


def __getattr__(name):
    if name in ("TAG_RE", "TAG_OR_ESCAPE", "NAME_RE"):
        return _patterns()[name]
    raise AttributeError("module {!r} has no attribute {!r}".format(__name__, name))


def tag_re():
    """The tag pattern: group(1) is a @{braced name}, group(2) a plain name."""
    return _patterns()["TAG_RE"]


CODE_LIKE = re.compile(r"[PVA]\d+", re.I)
POSSESSIVE = re.compile(r"^(.+?)(['’][sS])$")


def name_key(name):
    """Cast names compare without case and with ’ as '."""
    return " ".join(str(name or "").replace("’", "'").split()).lower()


def tag_token(name):
    """"@Mara", "@O'Brien" or "@{Old Keeper}": the plain form when the whole name reads as one tag
   ."""
    name = str(name or "").strip()
    return "@" + name if _patterns()["NAME_RE"].fullmatch(name) else "@{" + name + "}"

# Wording that follows MiniMax's official Ref2VA prompt guide
# (github.com/MiniMax-AI/MiniMax-H3, skills/h3-prompt-writing/references/ref-en.txt).
REF2VA_SECTIONS = ("subject_definitions", "summary", "retention_analysis",
                   "detailed_description", "overall_soundscape", "non_diegetic_music")
SUBJECT_VIDEO_CATEGORIES = ("motion", "style")
SUBJECT_PHRASE = {
    "subject": "the subject shown in {src}", "location": "the location shown in {src}",
    "prop": "the prop shown in {src}", "style": "the visual style of {src}",
    "motion": "the movement performed in {src}",
}
DEFAULT_KEEP = {
    "subject": ["identity", "appearance"], "location": ["layout", "lighting", "materials"],
    "prop": ["shape", "colour", "details"], "style": ["colour palette", "lighting", "texture"],
    "keyframe": ["composition"], "motion": ["movement"], "camera": ["camera movement", "pacing"],
    "edit_source": ["source footage"], "voice": ["voice timbre", "delivery"], "ambience": ["ambience"],
    "music": ["music style", "tempo"], "sfx": ["sound texture"],
}
AUDIO_PHRASE = {"voice": "the voice reference", "ambience": "the ambience reference",
                "music": "the music reference", "sfx": "the sound-effect reference"}

# A written line (by hand or by the LLM rewriter) that starts with a label the editor also
# writes automatically replaces the automatic line instead of repeating it. Labels count at the start of the text,
# of a line or of a sentence.
LABEL_START = re.compile(r"(?:^|(?<=\n)|(?<=[.!?] ))[ \t]*(?P<label><(?:Subject|Picture|Video|Audio) \d+>)")
SHOT_START = re.compile(r"(?:^|(?<=\n)|(?<=[.!?] ))[ \t]*(?P<label>\[Shot \d+\])")
DIALOGUE_SPAN = re.compile(r"<d>.*?</d>", re.S)
LEADING_TAGS = re.compile(r"^\s*\[([a-z +]+)\]\s*", re.I)
# Written shot lines and pass prompts
SHOT_NUMBER = re.compile(r"\[Shot (\d+)\]")
CLOCK = re.compile(r"\b(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\b")
CUT_LEAD = re.compile(r"^At\s+\d{1,2}:\d{2}(?:\.\d{1,3})?\s*,\s*(?:the\s+shot\s+cuts\s+to\s+)?", re.I)
CONTINUES = "The shot continues seamlessly from the previous moment."


# What the prompt builder needs about the whole project, computed once per /plan or run
class Context(dict):
    """prepare(p)'s result: a dict whose entries are worked out on first use and then kept:
    project, index (model.project_index), depth (continuation depth by scene id), starts / total (model.scene_starts),
    start_mode (scene id -> "fresh" | "last_frame" | "tail", the effective start: a re-anchored tail is
    "last_frame"), tracks (soundtrack.resolved), cast_by_key (name_key(name) -> cast member)."""

    def __missing__(self, key):
        p = self["project"]
        if key == "index":
            value = project_index(p)
        elif key == "depth":
            value = (getattr(_model, "continuation_depth", None) or continuation_depth)(p)
        elif key in ("starts", "total"):
            self["starts"], self["total"] = scene_starts(p)
            return self[key]
        elif key == "start_mode":
            value = {s["id"]: _start_mode(p, i, s, self["depth"]) for i, s in enumerate(p["scenes"])}
        elif key == "tracks":
            value = soundtrack.resolved(p)
        elif key == "cast_by_key":
            value = {name_key(c["name"]): c for c in p["cast"] if str(c.get("name") or "").strip()}
        else:
            raise KeyError(key)
        self[key] = value
        return value


def _start_mode(p, i, s, depth=None):
    """model.effective_start when model has it, else the same rule without the 5-frame cap."""
    effective = getattr(_model, "effective_start", None)
    if effective is not None:
        return effective(p, i)
    if i == 0 or s["start"]["mode"] not in ("last_frame", "tail"):
        return "fresh"
    depth = depth if depth is not None else continuation_depth(p)
    if s["start"]["mode"] == "tail" and depth.get(s["id"], 0) > int(p["global"]["continuity"]["reanchor_after"]):
        return "last_frame"  # re-anchored: guided by the last frame only
    return s["start"]["mode"]


def prepare(p):
    """Context for build_pass / lint_project: lookup tables, continuation depth, timeline starts, the effective
    start of every scene and the playable soundtrack tracks (see Context). Build it once per project state and pass
    it as ctx=; without one, every call makes its own, which costs O(scenes) per pass."""
    return Context(project=p)


def _ctx(p, ctx):
    return ctx if ctx is not None and ctx.get("project") is p else prepare(p)


def _index(p, ctx):
    return ctx["index"] if ctx is not None else project_index(p)


def _scene_start_mode(ctx, p, scene_index, scene):
    """The effective start of one scene, without working out every scene's when the context has none yet."""
    if "start_mode" in ctx:
        return ctx["start_mode"].get(scene["id"], "fresh")
    return _start_mode(p, scene_index, scene, ctx["depth"] if "depth" in ctx else None)


def _retention(ref, asset):
    return ref.get("retention") or asset["defaults"].get("retention") or (
        "reference" if asset["kind"] == "audio" else "fully_preserved")


def _keep(ref, asset):
    return list(ref.get("keep") or asset["defaults"].get("keep") or [])


class PassRefs:
    """Ordered references and guides for one pass, plus the tag map."""

    def __init__(self):
        self.images = []        # {"assets": [ids], "cast": id|None, "ref": id|None}
        self.videos = []        # {"asset": id, "soundtrack": bool, "ref": id}
        self.audios = []        # {"asset": id, "ref": id|None, "cast": id|None}
        self.guides = []        # see build_pass
        self.subjects = []      # {"cast": id, "number": n, "pictures": [k]}
        self.tag_map = {}
        self.picture_of_asset = {}
        self.video_of_asset = {}
        self.audio_of_asset = {}
        self.subject_of_asset = {}
        self.video_of_ref = {}
        self.audio_of_ref = {}
        self.subject_of_ref = {}
        self.ref_alias = {}
        self.song_number = None
        self.guided = set()
        self.continuation = None
        self.anchor_notes = []

    def number(self):
        for k, img in enumerate(self.images, 1):
            for a in img["assets"]:
                self.picture_of_asset.setdefault(a, k)
        audio_n = 0
        for k, v in enumerate(self.videos, 1):
            if v["soundtrack"]:
                audio_n += 1
                v["audio_number"] = audio_n
            if v.get("asset"):
                self.video_of_asset.setdefault(v["asset"], k)
                if v.get("ref"):
                    self.video_of_ref.setdefault(v["ref"], k)
        for a in self.audios:
            audio_n += 1
            if a.get("song"):
                self.song_number = audio_n
            else:
                self.audio_of_asset.setdefault(a["asset"], audio_n)
                if a.get("ref"):
                    self.audio_of_ref.setdefault(a["ref"], audio_n)

    @property
    def file_count(self):
        return len(self.images) + len(self.videos) + len(self.audios)


# model.clip_key of an entry already in refs.videos / refs.audios (a voice sample or a
# reference that is not trimmed has no in / out: the whole file)
def _clip_key_of(entry, a):
    if "in" in entry:
        return (a["id"], entry["in"], entry["out"])
    return (a["id"], 0.0, None)


GUIDE_KEYS = (("first_frame", "first frame"), ("keyframes", "keyframe"), ("last_frame", "last frame"))


def guided_refs(pass_):
    """Ids of the scene refs that guide this pass (first frame, keyframes, last frame)."""
    return {g["ref"] for key, _ in GUIDE_KEYS for g in pass_.get(key) or []}


# ---- the continuation as a named reference -------------------------------------------------------------------------
# Global -> Continuity -> name_continuation: the footage a pass continues from is also sent to H3 as reference 1 and
# named in the prompt, as MiniMax's ref-en.txt does for a first-frame picture (2.2) and a continuation video (2.3):
# the last frame of the scene before (a last-frame start, a re-anchored tail too) is <Picture 1>; the tail clip of the
# scene before (tail.mp4, its last 124 frames, with its sound when an audio slot is free) or, after an overlap seam,
# the last 124 frames of the pass before is <Video 1>. Every other picture or video moves up by one. The latent
# anchoring with MiniMaxH3AddGuide stays as it is. model.pass_continuation decides which passes (model.js the same).
CONT_WHAT = {"prev_scene_last": "the last frame of the scene before", "prev_scene_tail": "the tail clip of the scene before",
             "prev_pass_tail": "the end of the pass before"}
# reference numbers a continuation moves (text written with fixed numbers is left as it is, see build_pass)
FIXED_NUMBERS = {"picture": re.compile(r"<Picture \d+>"), "video": re.compile(r"<(?:Video|Audio) \d+>")}
# the editor's own definition of the continuation (a pass prompt edited by hand from a v0.7.0 build has it)
OWN_DEFINITION = re.compile(r"<Picture 1> is the first frame\b|<Video 1> is the end of (?:the scene before|the "
                            r"previous part of this scene)")
CONT_CITE = {"picture": "The shot begins from {label}.",
             "video": "The shot continues seamlessly from the final frames of {label}."}


def continuation_of(p, scene, scene_index, pass_, ctx=None):
    """What this pass sends as reference 1 for the footage it continues from: None, or
    {"kind": "picture"|"video", "source": "prev_scene_last"|"prev_scene_tail"|"prev_pass_tail", "frames": n}
    (frames: of the clip; 1 for the picture). None when Global -> Continuity -> name_continuation is off.
    Also None for a pass after an overlap seam when Global -> Long scenes -> seam_video_ref is
    off (model.pass_continuation reads it, default True, so the budget, lint and render agree); the tail clip a
    continuing scene starts from is still sent."""
    ctx = _ctx(p, ctx)
    mode = _scene_start_mode(ctx, p, scene_index, scene)
    kind = _model.pass_continuation(p, scene_index, pass_, mode)
    if not kind:
        return None
    if kind == "picture":
        return {"kind": "picture", "source": "prev_scene_last", "frames": 1}
    return {"kind": "video", "source": "prev_pass_tail" if int(pass_["index"]) > 1 else "prev_scene_tail",
            "frames": _model.continuation_frames(p, scene_index, pass_, mode)}


# What a pass sends so far, as model.scene_media_counts counts it, for pick_video_anchors
def _sent_counts(refs, assets):
    def secs(entry, a):
        if entry.get("continuation"):
            return float(entry.get("frames") or 0) / spec.FPS
        if entry.get("song"):
            return float(entry["song"]["length"])
        if "seconds" in entry:
            return float(entry["seconds"] or 0)
        return float((a or {}).get("duration") or 0)
    video = [(v, secs(v, assets.get(v.get("asset")))) for v in refs.videos]
    audio = [secs(x, assets.get(x.get("asset"))) for x in refs.audios]
    return {"videos": len(refs.videos), "video_seconds": sum(t for _, t in video),
            "audio": len(refs.audios) + sum(1 for v, _ in video if v["soundtrack"]),
            "audio_seconds": sum(audio) + sum(t for v, t in video if v["soundtrack"]), "files": refs.file_count}


# What build_pass says about the video anchors of a pass (refs.anchor_notes)
ANCHOR_LEFT = {
    "videos": "H3 takes {} videos and the pass sends that many already".format(spec.MAX_REF_VIDEOS),
    "files": "H3 takes {} files and the pass sends that many already".format(spec.MAX_REF_FILES),
    "seconds": "H3 takes {:g} s of video in all and less than {:g} s are left".format(spec.REF_MEDIA_TOTAL_SECONDS,
                                                                                   spec.REF_MEDIA_MIN_SECONDS),
    "clip": "its From / To leave no clip (Cast -> Video anchors)",
    "short": "its clip is under {:g} s (H3 video references are {:g}-{:g} s)".format(
        spec.REF_MEDIA_MIN_SECONDS, spec.REF_MEDIA_MIN_SECONDS, spec.REF_MEDIA_MAX_SECONDS),
}


def anchor_issues(refs, idx):
    out = []
    for x in refs.anchor_notes:
        c, a = idx["cast"].get(x["cast"]), idx["assets"].get(x["asset"])
        what = "{}'s video anchor {}".format(c["name"] if c else "a cast member", a["code"] if a else "")
        if "why" in x:
            out.append({"level": "warn", "tag": "", "message": "{} is not sent: {}".format(what, ANCHOR_LEFT[x["why"]])})
            continue
        if x["cut"]:
            out.append({"level": "info", "tag": "", "message": "{} is sent as its first {:.2f} s: H3 takes {:g} s of "
                        "video in all".format(what, x["seconds"], spec.REF_MEDIA_TOTAL_SECONDS)})
        if x["mute"]:
            out.append({"level": "info", "tag": "", "message": "{} is sent without its sound: the {} audio slots (or "
                        "{:g} s of audio) are taken".format(what, spec.MAX_REF_AUDIOS, spec.REF_MEDIA_TOTAL_SECONDS)})
    return out


def over_budget(refs):
    """(pictures, videos, files) of a pass when they are more than H3 takes (9, 3, 12), else None."""
    n = (len(refs.images), len(refs.videos), refs.file_count)
    return n if n[0] > spec.MAX_REF_IMAGES or n[1] > spec.MAX_REF_VIDEOS or n[2] > spec.MAX_REF_FILES else None


def _cont_before(c):
    return "the previous part of this scene" if c["source"] == "prev_pass_tail" else "the scene before"


def _cont_label(c):
    return "<Picture 1>" if c["kind"] == "picture" else "<Video 1>"


def _labelled(text, label):
    """Does a line or sentence of text start with this label (a definition or retention line of it)?"""
    return any(m.group("label") == label for m in LABEL_START.finditer(text or ""))


def _cont_definitions(c, shot="[Shot 1]"):
    """The definition line of the continuation, and of its sound when that is sent."""
    out = [continuation_definition(c, shot)]
    if c.get("audio_number"):
        out.append("<Audio {}> is the synchronized audio track of {}.".format(c["audio_number"], c["label"]))
    return out


def continuation_definition(c, shot="[Shot 1]"):
    """The subject_definitions line of the continuation (shot None: the text has no [Shot N] lines)."""
    if c["kind"] == "picture":
        return "{} is the first frame of {}, the last frame of the scene before.".format(
            c["label"], shot or "the target video")
    return "{} is the end of {}; the target video continues from its final frames.".format(c["label"], _cont_before(c))


def continuation_retention(c, shot="[Shot 1]"):
    """The retention_analysis line(s) of the continuation (and of its sound)."""
    if c["kind"] == "picture":
        return ["{} ({}first frame): fully_preserved - the target video starts on this frame and continues from "
                "it.".format(c["label"], shot + " " if shot else "")]
    out = ["{} (continuation source): fully_preserved - its final frames are kept as they are, and the subjects, "
           "setting, lighting and motion carry on from them.".format(c["label"])]
    if c.get("audio_number"):
        out.append("<Audio {0}>: reference - the target video's sound carries on from <Audio {0}> without copying "
                   "the original signal.".format(c["audio_number"]))
    return out


def _cite_continuation(lines, c):
    """detailed_description lines with the continuation cited in [Shot 1] (ref-en.txt 5.3: "the shot begins from
    <Picture 1>"), unless that shot names it already; a [Shot 1] that "continues seamlessly from the previous moment"
    says from what. Without a [Shot 1], one is added before the first [Shot N] (or at the end)."""
    sentence = CONT_CITE[c["kind"]].format(label=c["label"])
    for k, x in enumerate(lines):
        m = SHOT_START.match(x)
        if not m or m.group("label") != "[Shot 1]":
            continue
        if c["label"] in x:
            return lines
        body = x[m.end("label"):].strip()
        if c["kind"] == "video" and CONTINUES in body:
            body = body.replace(CONTINUES, sentence, 1)
        else:
            body = (sentence + " " + body).strip()
        return lines[:k] + [x[:m.end("label")] + " " + body] + lines[k + 1:]
    first = next((k for k, x in enumerate(lines) if SHOT_START.match(x)), len(lines))
    return lines[:first] + ["[Shot 1] " + sentence] + lines[first:]


def _name_in_written(text, refs):
    """A prompt written whole (raw mode, a pass edited by hand, a Split answer) with the continuation named: in the
    six-section form its definition and retention lines go first in their sections and [Shot 1] cites it; any other
    text gets the definition in front. Parts that name the label already are left as they are."""
    c = refs.continuation
    found = list(SECTION_LABEL.finditer(text))
    labels = {m.group(1) for m in found}
    if len(labels) < 2 or not labels & {"subject_definitions", "retention_analysis", "detailed_description"}:
        if _labelled(text, c["label"]):
            return text
        text = _strip_task_tags(text).strip()  # place_task_tags puts them back in front
        pre, chunks = _chunks(text, SHOT_START)
        shot = "[Shot 1]" if any(label == "[Shot 1]" for label, _ in chunks) else None
        if shot:
            text = "\n".join(_cite_continuation(([pre] if pre else []) + [chunk for _, chunk in chunks], c))
        return (" ".join(_cont_definitions(c, shot)) + "\n" + text).strip()
    spans = {}
    for k, m in enumerate(found):
        spans.setdefault(m.group(1), (m.end(), found[k + 1].start() if k + 1 < len(found) else len(text)))
    has_shot = "detailed_description" in spans or None

    def section(name, body):
        core = body.strip()
        if name == "detailed_description":
            pre, chunks = _chunks("" if core == "N/A" else core, SHOT_START)
            return "\n".join(_cite_continuation(([pre] if pre else []) + [chunk for _, chunk in chunks], c))
        if _labelled(core, c["label"]):
            return core
        if name == "subject_definitions":
            new = _cont_definitions(c, "[Shot 1]" if has_shot else None)
        else:
            new = continuation_retention(c, "[Shot 1]" if has_shot else None)
        return "\n".join(new + ([core] if core and core != "N/A" else []))

    for name in sorted(spans, key=lambda x: spans[x][0], reverse=True):  # from the end, so offsets stay valid
        if name not in ("subject_definitions", "retention_analysis", "detailed_description"):
            continue
        a, b = spans[name]
        body = text[a:b]
        lead = body[:len(body) - len(body.lstrip())] or "\n"
        trail = body[len(body.rstrip()):]
        text = text[:a] + lead + section(name, body) + trail + text[b:]
    if "subject_definitions" not in spans:  # it is defined in a section of its own, in front of the others
        at = found[0].start()
        text = text[:at] + "subject_definitions:\n{}\n\n".format(
            "\n".join(_cont_definitions(c, "[Shot 1]" if has_shot else None))) + text[at:]
    return text


def collect_refs(p, scene, scene_index, pass_, n_passes, mentioned_codes=(), ctx=None, continuation=None):
    """continuation: continuation_of(...) to send as reference 1, None for none."""
    ctx = _ctx(p, ctx)
    idx = ctx["index"]
    assets = idx["assets"]
    refs = PassRefs()
    cont = dict(continuation) if continuation else None
    if cont and cont["kind"] == "picture":
        refs.images.append({"assets": [], "cast": None, "ref": None, "source": cont["source"], "continuation": True})
    if cont and cont["kind"] == "video":
        refs.videos.append({"asset": None, "soundtrack": False, "ref": None, "source": cont["source"],
                            "frames": cont["frames"], "continuation": True})
    guided = guided_refs(pass_)
    speaking = {d.get("speaker") for d in pass_["dialogue"]}

    people = _model.scene_people(p, scene, idx)[0]
    entries = [(x["entry"], x["cast"], x["outfit"], x["ids"]) for x in people]
    parts_of = {x["cast"]["id"]: x["parts"] for x in people}
    own_of = {x["cast"]["id"]: set(x["own"]) for x in people}
    poses = _model.pose_refs(p, scene, pass_, people, idx) if hasattr(_model, "pose_refs") else []
    unpacked = len({a for *_, ids in entries for a in ids}) + len(
        ({r["asset"] for r in scene["refs"] if r["asset"] in assets and assets[r["asset"]]["kind"] == "image" and
          (r["role"] == "reference" or (r["id"] in guided and assets[r["asset"]]["code"].upper() in mentioned_codes))} |
         {a["id"] for _, a, _ in poses}) - {a for *_, ids in entries for a in ids})
    auto_pack = unpacked + (1 if cont and cont["kind"] == "picture" else 0) > spec.MAX_REF_IMAGES

    song = soundtrack.pass_soundtrack(p, ctx["starts"][scene["id"]], pass_) if any(
        t.get("sync") for t in ctx["tracks"]) else None
    for n, (entry, c, outfit, anchor_ids) in enumerate(entries):
        first_pic = len(refs.images) + 1
        pack = auto_pack if c.get("pack_sheet", True) == "auto" else bool(c.get("pack_sheet", True))
        if anchor_ids and pack and len(anchor_ids) > 1:
            refs.images.append({"assets": anchor_ids, "cast": c["id"], "ref": None})
        else:
            for a in anchor_ids:
                refs.images.append({"assets": [a], "cast": c["id"], "ref": None})
        pics = list(range(first_pic, len(refs.images) + 1))
        own = own_of.get(c["id"], set())
        parts = []
        for part in parts_of.get(c["id"], []):
            shown = [] if len(pics) == 1 and len(anchor_ids) > 1 else \
                [first_pic + anchor_ids.index(a) for a in part["ids"] if a not in own and a in anchor_ids]
            parts.append({"cast": part["cast"]["id"], "outfit": part["outfit"], "pictures": sorted(set(shown))})
        refs.subjects.append({"cast": c["id"], "ref": None, "asset": None, "number": n + 1, "outfit": outfit,
                              "pictures": pics, "videos": []})
        if parts:  # only then, so a scene without parts keeps its build (and cache key) exactly
            refs.subjects[-1]["parts"] = parts
        if c.get("voice") in assets and assets[c["voice"]]["kind"] == "audio" and not song and c["id"] in speaking:
            refs.audios.append({"asset": c["voice"], "ref": None, "cast": c["id"]})  # a whole file (clip_key: start 0, no end)
    if song:
        refs.audios.append({"asset": None, "ref": None, "cast": None, "song": song})
    for r, a, c in poses:
        if not any(a["id"] in img["assets"] for img in refs.images):
            refs.images.append({"assets": [a["id"]], "cast": None, "ref": r["id"], "pose": c["id"]})

    guide_only = {"first_frame", "last_frame", "keyframe"}
    for r in scene["refs"]:
        a = assets.get(r["asset"])
        if not a:
            continue
        if r["role"] == "pose":
            continue
        if r["role"] in guide_only:
            if r["id"] not in guided or a["code"].upper() not in mentioned_codes:
                continue
            if a["kind"] == "image" and not any(a["id"] in img["assets"] for img in refs.images):
                refs.images.append({"assets": [a["id"]], "cast": None, "ref": r["id"]})
            elif a["kind"] == "video" and not any(v["asset"] == a["id"] for v in refs.videos):
                refs.videos.append({"asset": a["id"], "soundtrack": False, "ref": r["id"], "guide": True})
            continue
        if a["kind"] == "image":
            if any(a["id"] in img["assets"] for img in refs.images):
                continue
            refs.images.append({"assets": [a["id"]], "cast": None, "ref": r["id"]})
        elif a["kind"] in ("video", "audio"):
            if a["kind"] == "audio":
                key = _model.clip_key(r, a)
                same = next((x for x in refs.audios if x.get("asset") == a["id"] and _clip_key_of(x, a) == key), None)
                if same:
                    if same.get("ref"):
                        refs.ref_alias[r["id"]] = same["ref"]
                    continue
            entry = {"asset": a["id"], "soundtrack": bool(r.get("soundtrack")), "ref": r["id"]} if a["kind"] == "video" \
                else {"asset": a["id"], "ref": r["id"], "cast": None}
            if _model.ref_trimmed(r):
                c = _model.ref_clip(r, a)
                entry.update({"in": c["start"], "out": c["end"], "seconds": c["seconds"]})
            (refs.videos if a["kind"] == "video" else refs.audios).append(entry)
    refs.guided = guided
    if cont and cont["kind"] == "video":
        refs.videos[0]["soundtrack"] = sum(1 for v in refs.videos if v["soundtrack"]) + len(refs.audios) < \
            spec.MAX_REF_AUDIOS
    if any(x["cast"].get("video_anchors") for x in people):
        picked, left = _model.pick_video_anchors(people, assets, _sent_counts(refs, assets))
        for x in picked:
            refs.videos.append({"asset": x["asset"], "soundtrack": x["sound"], "ref": None, "cast": x["cast"],
                                "anchor": x["anchor"], "in": x["in"], "out": x["in"] + x["seconds"],
                                "seconds": x["seconds"]})
        refs.anchor_notes = picked + left
    refs.number()
    for k, v in enumerate(refs.videos, 1):
        if v.get("anchor"):
            subj = next((x for x in refs.subjects if x["cast"] == v["cast"]), None)
            if subj is not None:
                subj["videos"].append(k)
    for r, a, c in poses:
        subj = next((x for x in refs.subjects if x["cast"] == c["id"]), None)
        k = refs.picture_of_asset.get(a["id"])
        if subj and k:
            t = _model.pose_time(r, scene) - float(pass_["start"])
            subj.setdefault("poses", []).append({"ref": r["id"], "picture": k,
                                                 "shot": _shot_index(pass_["shots"], t) if pass_["shots"] else 1})
    if cont:
        first = refs.images[0] if cont["kind"] == "picture" else refs.videos[0]
        refs.continuation = dict(cont, label="<{} 1>".format("Picture" if cont["kind"] == "picture" else "Video"),
                                 audio_number=first.get("audio_number") if first.get("soundtrack") else None)

    ref_by_id = {r["id"]: r for r in scene["refs"]}
    for img in refs.images:
        r = ref_by_id.get(img["ref"]) if img["ref"] else None
        if img["cast"] or not r or r["role"] != "reference":
            continue
        a = assets[img["assets"][0]]
        if a.get("category") == "keyframe" or a["id"] in refs.subject_of_asset:
            continue
        refs.subjects.append({"cast": None, "ref": r["id"], "asset": a["id"], "number": len(refs.subjects) + 1,
                              "outfit": None, "pictures": [refs.picture_of_asset[a["id"]]], "videos": []})
        refs.subject_of_asset[a["id"]] = refs.subjects[-1]["number"]
    for k, v in enumerate(refs.videos, 1):
        if v.get("continuation"):
            continue
        a = assets[v["asset"]]
        if v.get("guide") or a.get("category") not in SUBJECT_VIDEO_CATEGORIES:
            continue
        if v.get("anchor"):
            continue
        twin = next((s for s in refs.subjects if s.get("asset") == a["id"] and not s["cast"] and s["videos"] and
                     _clip_key_of(refs.videos[s["videos"][0] - 1], a) == _clip_key_of(v, a)), None)
        if twin:  # the same clip again: the same subject, shown in both
            twin["videos"].append(k)
            if v.get("ref"):
                refs.subject_of_ref[v["ref"]] = twin["number"]
            continue
        refs.subjects.append({"cast": None, "ref": v["ref"], "asset": a["id"], "number": len(refs.subjects) + 1,
                              "outfit": None, "pictures": [], "videos": [k]})
        refs.subject_of_asset.setdefault(a["id"], refs.subjects[-1]["number"])
        if v.get("ref"):
            refs.subject_of_ref[v["ref"]] = refs.subjects[-1]["number"]

    # guides
    i = pass_["index"]
    if i == 1 and scene_index > 0:
        mode = _scene_start_mode(ctx, p, scene_index, scene)  # fresh | last_frame | tail (re-anchored tail: last_frame)
        if mode == "tail" and pass_["overlap_frames"]:
            refs.guides.append({"type": "clip", "source": "prev_scene_tail", "frames": pass_["overlap_frames"],
                                "frame_idx": 0, "audio": True})
        elif mode in ("last_frame", "tail"):
            refs.guides.append({"type": "image", "source": "prev_scene_last", "frame_idx": 0})
    if i > 1 and pass_["seam_before"] == "overlap":
        refs.guides.append({"type": "clip", "source": "prev_pass_tail", "frames": pass_["overlap_frames"],
                            "frame_idx": 0, "audio": True})
    for key in ("first_frame", "keyframes", "last_frame"):
        for k in pass_[key]:
            r = next((x for x in scene["refs"] if x["id"] == k["ref"]), None)
            if r and r["asset"] in assets and assets[r["asset"]]["kind"] in ("image", "video"):
                refs.guides.append({"type": "image" if assets[r["asset"]]["kind"] == "image" else "clip",
                                    "source": "asset", "asset": r["asset"], "frame_idx": k["frame_idx"],
                                    "audio": False})
    return refs


def task_tags(p, scene, refs, ctx=None):
    assets = (ctx["index"] if ctx is not None else project_index(p))["assets"]
    tags = set()
    cont = refs.continuation
    if refs.file_count - (1 if cont else 0):
        tags.add("reference generation")
    if cont:
        tags.add("keyframe completion" if cont["kind"] == "picture" else "video continuation")
        if cont.get("audio_number"):
            tags.add("audio reference")
    if any(g["type"] == "image" for g in refs.guides):
        tags.add("keyframe completion")
    if any(g["type"] == "clip" for g in refs.guides):
        tags.add("video continuation")  # the target continues from (or passes through) existing footage
    ref_by_id = {r["id"]: r for r in scene["refs"]}
    for v in refs.videos:
        if v.get("continuation"):
            continue
        a = assets[v["asset"]]
        if a.get("category") == "edit_source":
            tags.add("video editing")
        if v["soundtrack"]:
            ret = _retention(ref_by_id.get(v["ref"], {}), a) if v["ref"] else "reference"
            tags.add("audio reuse" if ret in ("fully_copy", "partially_copy") else "audio reference")
    for au in refs.audios:
        if au.get("song"):
            tags.add("audio reuse" if au["song"]["marker"] in ("fully_copy", "partially_copy") else "audio reference")
            continue
        a = assets[au["asset"]]
        ret = _retention(ref_by_id.get(au["ref"], {}), a) if au["ref"] else "reference"
        tags.add("audio reuse" if ret in ("fully_copy", "partially_copy") else "audio reference")
    return [t for t in spec.TASK_TAG_ORDER if t in tags]


def mentioned_codes(text):
    out = set()
    for m in tag_re().finditer(text or ""):
        if m.group(2):
            out.add(m.group(2).upper())
            base = POSSESSIVE.match(m.group(2))
            if base:
                out.add(base.group(1).upper())
            nth = NTH_CLIP.fullmatch(m.group(2))
            if nth:
                out.add(nth.group(1).upper())
    return out


# How each tag reads in one pass, and what is said about tags that don't resolve
def _asset_words(a):
    """Plain words for an asset that is not sent with this pass: its description, else its name."""
    desc = (a.get("description") or "").strip().rstrip(".")
    if desc:
        first = desc.split(" ", 1)[0]
        return desc[0].lower() + desc[1:] if first in ("A", "An", "The") else desc
    name = os.path.splitext((a.get("name") or "").strip())[0].strip()
    if name:
        return "the " + name
    return {"video": "the reference clip", "audio": "the reference sound"}.get(a.get("kind"), "the reference picture")


def _scene_asset_role(a, p, scene, idx):
    """How asset `a` belongs to the scene other than as one of its references:
    ("voice", cast) for the voice of a cast member in the scene (or one who speaks in it), ("picture", cast) for an
    anchor or an asset of the outfit the scene gives them, ("song", None) for a soundtrack track's file; else None."""
    if scene:
        entries = [e for e in scene.get("cast") or [] if isinstance(e, dict)]
        ids = {e.get("id") for e in entries}
        entries += [{"id": d.get("speaker"), "outfit": ""} for d in scene.get("dialogue") or []
                    if isinstance(d, dict) and d.get("speaker") and d.get("speaker") not in ids]
        for e in entries:
            c = idx["cast"].get(e.get("id"))
            if not c:
                continue
            if c.get("voice") == a["id"]:
                return "voice", c
            outfit = next((o for o in c.get("outfits") or []
                           if o.get("id") == (e.get("outfit") or c.get("default_outfit"))), None)
            if a["id"] in (c.get("anchors") or []) or (outfit and a["id"] in (outfit.get("assets") or [])):
                return "picture", c
    if any(isinstance(t, dict) and t.get("asset") == a["id"] for t in p.get("soundtrack") or []):
        return "song", None
    return None


def _voice_words(a, c):
    """A cast voice not sent with this pass, in words: its description, else
    "<name>'s voice"."""
    desc = (a.get("description") or "").strip().rstrip(".")
    if desc:
        return _asset_words(a)
    return "{}'s voice".format(c.get("name") or "the character")


# "@V1.2" names the second reference of V1 in the scene (model.ref_tokens)
NTH_CLIP = re.compile(r"([PVA]\d+)\.(\d+)", re.I)


def _nth_clip(name, refs, scene, idx):
    """(text, level, message) for "@V1.2" style names, or None when the name is no such tag."""
    m = NTH_CLIP.fullmatch(name)
    a = idx["codes"].get(m.group(1).upper()) if m else None
    if not a:
        return None
    n = int(m.group(2))
    ids = _model.media_ref_ids(scene, a["id"]) if a["kind"] in ("video", "audio") else []
    words = _asset_words(a)
    if not 1 <= n <= len(ids):
        if a["kind"] not in ("video", "audio"):
            why = "only video and audio references are numbered like this"
        else:
            why = "this scene has {} reference{} of {}".format(len(ids), "" if len(ids) == 1 else "s", a["code"])
        return words, "warn", "@{}: {}, so it is written as “{}”".format(name, why, words)
    rid = ids[n - 1]
    rid = refs.ref_alias.get(rid, rid)
    for table, label in ((refs.subject_of_ref, "Subject"), (refs.video_of_ref, "Video"), (refs.audio_of_ref, "Audio")):
        if rid in table:
            return "<{} {}>".format(label, table[rid]), None, None
    return words, "info", "@{} is not sent with this pass, so it names it in words: “{}”".format(name, words)


def resolve_tag(name, braced, p, refs, ctx, scene=None):
    """(text, level, message) for one tag in this pass: level None when it resolves to a label; otherwise the
    words written instead and why. text None means the tag stays as typed."""
    idx = ctx["index"]
    nth = None if braced or idx["codes"].get(name.upper()) else _nth_clip(name, refs, scene, idx)
    if nth:
        return nth
    a = None if braced else idx["codes"].get(name.upper())
    if a:
        if a["id"] in refs.subject_of_asset:
            return "<Subject {}>".format(refs.subject_of_asset[a["id"]]), None, None
        if a["kind"] == "image" and a["id"] in refs.picture_of_asset:
            return "<Picture {}>".format(refs.picture_of_asset[a["id"]]), None, None
        if a["kind"] == "video" and a["id"] in refs.video_of_asset:
            return "<Video {}>".format(refs.video_of_asset[a["id"]]), None, None
        if a["kind"] == "audio" and a["id"] in refs.audio_of_asset:
            return "<Audio {}>".format(refs.audio_of_asset[a["id"]]), None, None
        mine = [r for r in (scene or {}).get("refs", []) if r.get("asset") == a["id"]]
        if mine:
            words = _asset_words(a)
            why = "guides another pass" if any(r.get("role") in ("first_frame", "last_frame", "keyframe") and
                                               r.get("id") not in refs.guided for r in mine) else "is not sent with it"
            return words, "info", "@{} {}, so this pass names it in words: “{}”".format(a["code"], why, words)
        own = _scene_asset_role(a, p, scene, idx)
        if own:
            kind, c = own
            if kind == "song":
                song = next((x["song"] for x in refs.audios if x.get("song")), None)
                if song and refs.song_number and any(x.get("asset") == a["id"] for x in song.get("pieces") or []):
                    return "<Audio {}>".format(refs.song_number), None, None
                return "the soundtrack", "info", "@{} is the soundtrack and this pass gets no part of it, so it is " \
                                                 "written as “the soundtrack”".format(a["code"])
            if kind == "voice":
                words = _voice_words(a, c)
                return words, "info", "@{} is {}'s voice, sent only with the passes where {} speaks, so this pass " \
                                      "names it in words: “{}”".format(a["code"], c["name"], c["name"], words)
            words = _asset_words(a)
            return words, "info", "@{} is not sent with this pass, so it names it in words: “{}”".format(a["code"], words)
        return None, "error", "@{} is not a reference of this scene (add it under References)".format(a["code"])
    low = name.strip().lower()
    if low == "tail" and not braced:
        if getattr(refs, "continuation", None):
            return refs.continuation["label"], None, None
        if scene is not None and _scene_start_mode(ctx, p, idx["scenes"].get(scene["id"], 0), scene) == "fresh":
            return "the end of the previous shot", "warn", "@tail: this scene starts fresh, so there is no previous " \
                                                           "shot to continue"
        return "the end of the previous shot", None, None
    if low in ("soundtrack", "song") and not braced:
        if refs.song_number:
            return "<Audio {}>".format(refs.song_number), None, None
        if not any(t.get("sync") for t in ctx["tracks"]):
            return "the soundtrack", "warn", "@{}: no soundtrack track is sent to H3 (Timeline: Soundtrack, Send to " \
                                             "H3), so it is written as “the soundtrack”".format(name)
        return "the soundtrack", "info", "@{}: this pass gets no part of the soundtrack (less than 2 s of it plays " \
                                         "here), so it is written as “the soundtrack”".format(name)
    c = ctx["cast_by_key"].get(name_key(name))
    owner = _model.part_owner(c, idx["cast"]) if c and hasattr(_model, "part_owner") else ""
    if owner:
        subject = next((s["number"] for s in refs.subjects if s["cast"] == owner), None)
        oname = idx["cast"][owner]["name"]
        if subject:
            words = "<Subject {}>'s {}".format(subject, c["name"])
            if any(x["cast"] == c["id"] for s in refs.subjects for x in s.get("parts") or []):
                return words, None, None
            return words, "info", "@{} is part of {} but not in this scene's cast, so its pictures are not sent " \
                                  "(add it to the scene to send them)".format(name, oname)
        return c["name"], "warn", "@{} is part of {}, who is not in this scene's cast, so it is written as the name " \
                                  "“{}”".format(name, oname, c["name"])
    if c:
        subject = next((s["number"] for s in refs.subjects if s["cast"] == c["id"]), None)
        if subject:
            return "<Subject {}>".format(subject), None, None
        return c["name"], "warn", "@{} is not in this scene's cast, so it is written as the name “{}” (add " \
                                  "{} to the scene to send their pictures)".format(name, c["name"], c["name"])
    if not braced and CODE_LIKE.fullmatch(name):
        return None, "error", "@{} matches no asset of this project".format(name)
    return None, "warn", "@{} is not a cast member, asset or @soundtrack, so it is written as plain text (write @@ " \
                         "for a literal @)".format(name)


def substitute(text, p, refs, unknown, ctx=None, scene=None, issues=None):
    """Tags -> this pass's labels; "@@" -> "@". unknown gets the tags that are errors; issues (optional) gets
    {"level", "tag", "message"} for every tag that does not resolve to a label."""
    ctx = _ctx(p, ctx)

    def repl(m):
        if m.group(0) == "@@":
            return "@"
        braced = m.group(1) is not None
        name = m.group(1) if braced else m.group(2)
        text_, level, message = resolve_tag(name, braced, p, refs, ctx, scene)
        suffix = ""
        if level and not braced:  # "@Mara's" -> <Subject 1>'s
            base = POSSESSIVE.match(name)
            if base:
                t2, l2, m2 = resolve_tag(base.group(1), False, p, refs, ctx, scene)
                if t2 is not None and l2 != "error":
                    text_, level, message, suffix = t2, l2, m2, base.group(2)
        if level:
            if level == "error":
                unknown.append(m.group(0))
            if issues is not None and not any(x["message"] == message for x in issues):
                issues.append({"level": level, "tag": m.group(0), "message": message})
        return (m.group(0) if text_ is None else text_) + suffix

    return _patterns()["TAG_OR_ESCAPE"].sub(repl, text or "")


# ---- Ref2VA writers ----------------------------------------------------------------------

def _join_and(items):
    items = [str(x).strip() for x in items if str(x).strip()]
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return "{} and {}".format(*items)
    return "{}, and {}".format(", ".join(items[:-1]), items[-1])


def _sentence(text):
    """Capitalised, with a full stop when the text has no end mark."""
    t = (text or "").strip()
    if not t:
        return ""
    if t[0].islower():
        t = t[0].upper() + t[1:]
    return t if t[-1] in ".!?\"'" else t + "."


def _lower_lead(text):
    """'A close-up of ...' -> 'a close-up of ...' so it reads after 'the shot cuts to'."""
    t = (text or "").strip()
    first = t.split(" ", 1)[0]
    if first and first[0].isupper() and first[1:] == first[1:].lower() and first.isalpha() and len(first) > 1:
        return t[0].lower() + t[1:]
    if first in ("A", "I"):
        return t if first == "I" else "a" + t[1:]
    return t


def _keep_phrase(keep, ret):
    text = _join_and(keep) or "the referenced features"
    be = "are" if len([k for k in keep if str(k).strip()]) > 1 else "is"
    return {
        "fully_preserved": "{} {} retained".format(text, be),
        "partially_preserved": "{} {} partly retained".format(text, be),
        "attribute_transfer": "{} {} transferred to the target subject".format(text, be),
        "weak_reference": "only a broad similarity in {} is kept".format(text),
        "fully_copy": "the complete signal is reused as the final audio track",
        "partially_copy": "{} {} copied".format(text, be),
        "reference": "{} {} referenced without copying the original signal".format(text, be),
    }.get(ret, "{} {} retained".format(text, be))


def _labels(kind, numbers):
    return _join_and("<{} {}>".format(kind, k) for k in numbers)


# see LABEL_START
def _chunks(text, pattern):
    """(text before the first label, [(label, chunk)]) where each chunk runs up to the next label."""
    text = "\n".join(line.strip() for line in (text or "").strip().splitlines())
    found = list(pattern.finditer(text))
    if not found:
        return text.strip(), []
    out = []
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(text)
        out.append((m.group("label"), text[m.start("label"):end].strip()))
    return text[:found[0].start()].strip(), out


def _merge(auto, written, pattern, fix=None, pre_first=False):
    """auto: [(label, line)] from the editor; written: the section's own text. A written chunk replaces the
    automatic line with the same label; written chunks with other labels follow. Unlabelled text comes first when
    nothing is automatic or pre_first is set (style sentences before [Shot 1]), last otherwise.
    fix(label, chunk, auto_line) may amend a chunk."""
    fix = fix or (lambda label, chunk, line: chunk)
    pre, chunks = _chunks(written, pattern)
    if not auto:
        return ([pre] if pre else []) + [fix(label, c, None) for label, c in chunks]
    mine = {}
    for label, c in chunks:
        mine.setdefault(label, []).append(c)
    out = []
    for label, line in auto:
        if label in mine:
            out += [fix(label, c, line) for c in mine.pop(label)]
        else:
            out.append(line)
    out += [fix(label, c, None) for label, c in chunks if label in mine]
    if not pre:
        return out
    return [pre] + out if pre_first else out + [pre]


def _with_sources(refs):
    """fix() for subject lines: a written <Subject N> line that names none of the subject's pictures or videos
    gets ", shown in <Picture k>" so H3 still knows which reference it is (the rewriter used to drop it)."""
    src = {"<Subject {}>".format(s["number"]): (["<Picture {}>".format(k) for k in s["pictures"]] +
                                                ["<Video {}>".format(k) for k in s["videos"]],
                                                _labels("Picture", s["pictures"]) or _labels("Video", s["videos"]))
           for s in refs.subjects}

    def fix(label, chunk, line):
        labels, phrase = src.get(label, ([], ""))
        if not phrase or any(x in chunk for x in labels):
            return chunk
        body = chunk.rstrip()
        end = body[-1] if body and body[-1] in ".!?" else ""
        return "{}, shown in {}{}".format(body[:-1] if end else body, phrase, end or ".")
    return fix


def speaker_ids(pass_):
    """(S1), (S2)... in the order voices are heard in this pass (ref-en.txt 5.4)."""
    ids = {}
    for d in pass_["dialogue"]:
        key = d.get("speaker") or ""
        if key not in ids:
            ids[key] = "S{}".format(len(ids) + 1)
    return ids


def _shot_index(shots, t):
    n = 1
    for i, sh in enumerate(shots, 1):
        if float(sh["t"]) <= float(t) + 1e-6:
            n = i
    return n


def _appears(p, refs, pass_, subj, ctx=None):
    """'appears in [Shot 1], [Shot 3]' from @mentions in shot text and spoken lines."""
    shots = pass_["shots"] or [{"t": 0.0, "camera": "", "text": ""}]
    idx = _index(p, ctx)
    hits = set()
    if subj["cast"]:
        names = {name_key(idx["cast"][subj["cast"]]["name"])} | {
            name_key(idx["cast"][x["cast"]]["name"]) for x in subj.get("parts") or [] if x["cast"] in idx["cast"]}

        def match(m):
            said = m.group(1) if m.group(1) is not None else m.group(2)
            base = POSSESSIVE.match(said) if m.group(2) else None
            return name_key(said) in names or bool(base and name_key(base.group(1)) in names)
    else:
        code = idx["assets"][subj["asset"]]["code"].upper()

        def match(m):
            base = POSSESSIVE.match(m.group(2) or "")
            return (m.group(2) or "").upper() == code or bool(base and base.group(1).upper() == code)
    for i, sh in enumerate(shots, 1):
        if any(match(m) for m in tag_re().finditer("{} {}".format(sh.get("camera", ""), sh.get("text", "")))):
            hits.add(i)
    if subj["cast"]:
        for d in pass_["dialogue"]:
            if d.get("speaker") == subj["cast"]:
                hits.add(_shot_index(shots, d["t"]))
    if not hits:
        hits = set(range(1, len(shots) + 1))
    return "appears in " + ", ".join("[Shot {}]".format(i) for i in sorted(hits))


def _guide_of_picture(scene, refs, pass_, k):
    """'the first frame of [Shot 1]' when picture k is also pinned as a guide in this pass."""
    shots = pass_["shots"] or [{"t": 0.0}]
    img = refs.images[k - 1]
    for key, label in (("first_frame", "first frame"), ("keyframes", "keyframe"), ("last_frame", "last frame")):
        for g in pass_[key]:
            r = next((x for x in scene["refs"] if x["id"] == g["ref"]), None)
            if r and r["asset"] in img["assets"]:
                t = g["frame_idx"] / spec.FPS if g["frame_idx"] >= 0 else None
                n = _shot_index(shots, t) if t is not None else len(shots)
                at = " at {}".format(spec.fmt_time(t)) if key == "keyframes" and t is not None else ""
                return "{} of [Shot {}]{}".format(label, n, at), "[Shot {}] {}{}".format(n, label, at)
    return None, None


# A guide clip named in the text is sent as <Video k>; this says where it sits in the pass
def _guide_of_clip(pass_, ref_id):
    """(definition, retention place) for the guide clip of scene ref ref_id in this pass."""
    shots = pass_["shots"] or [{"t": 0.0}]
    for key, _ in GUIDE_KEYS:
        for g in pass_.get(key) or []:
            if g["ref"] != ref_id:
                continue
            t = max(0.0, g["frame_idx"] / spec.FPS)
            n = _shot_index(shots, t)
            if key == "first_frame":
                return ("the opening clip of [Shot {}]; the target video starts on its frames and continues from "
                        "them".format(n), "[Shot {}] opening clip".format(n))
            if key == "last_frame":
                return ("the closing clip of [Shot {}]; the target video ends on its frames".format(n),
                        "[Shot {}] closing clip".format(n))
            return ("the clip placed in [Shot {}] at {}; the target video passes through its frames".format(
                n, spec.fmt_time(t)), "[Shot {}] clip at {}".format(n, spec.fmt_time(t)))
    return "a guide clip", "guide clip"


def subject_definitions(p, scene, refs, pass_, ids, ctx=None):
    idx = _index(p, ctx)
    assets, cast = idx["assets"], idx["cast"]
    lines = []
    for s in refs.subjects:
        head = "<Subject {}>".format(s["number"])
        src = _labels("Picture", s["pictures"]) or _labels("Video", s["videos"])
        if s["cast"]:
            c = cast[s["cast"]]
            desc, _ = cast_description(c, assets)
            bits = [c["name"]] + ([desc] if desc else [])
            text = "{} is {}".format(head, ", ".join(bits))
            parts = s.get("parts") or []
            only_parts = {k for x in parts for k in x["pictures"]}
            own_pics = [k for k in s["pictures"] if k not in only_parts]
            own_src = _labels("Picture", own_pics)
            sheet = len(own_pics) == 1 and len(refs.images[own_pics[0] - 1]["assets"]) > 1
            if sheet:
                own_src += ", " + sheet_words(c, len(refs.images[own_pics[0] - 1]["assets"]))
            vids = _labels("Video", s["videos"])
            if own_src and vids:
                text += ", shown in " + own_src + (", and in " if sheet else " and in ") + vids
            elif own_src or vids:
                text += ", shown in " + (own_src or vids)
            o = s["outfit"]
            if o and o.get("name") and o["name"].strip().lower() != "default":
                text += ", " + outfit_words(o["name"])
            for x in parts:
                text += ", " + part_words(cast[x["cast"]], assets, x["pictures"])
            if s.get("poses"):
                text += ", " + pose_words(s["poses"])
            lines.append(text + ".")
        else:
            a = assets[s["asset"]]
            desc = (a.get("description") or "").strip().rstrip(".")
            if desc:
                lines.append("{} is {}, shown in {}.".format(head, desc, src))
            else:
                phrase = SUBJECT_PHRASE.get(a.get("category"), "the content shown in {src}")
                lines.append("{} is {}.".format(head, phrase.format(src=src)))
    for k, img in enumerate(refs.images, 1):
        if img["cast"] or any(k in s["pictures"] for s in refs.subjects):
            continue
        if img.get("pose"):
            continue
        if img.get("continuation"):
            lines.append(continuation_definition(refs.continuation))
            continue
        a = assets[img["assets"][0]]
        desc = (a.get("description") or "").strip().rstrip(".")
        role, _ = _guide_of_picture(scene, refs, pass_, k)
        what = ("the " + role) if role else ("a composition reference" if a.get("category") == "keyframe" else "a reference image")
        lines.append("<Picture {}> is {}{}.".format(k, what, ", showing " + desc if desc else ""))
    for k, v in enumerate(refs.videos, 1):
        if any(k in s["videos"] for s in refs.subjects):
            continue
        if v.get("continuation"):
            lines.append(continuation_definition(refs.continuation))
            continue
        a = assets[v["asset"]]
        desc = (a.get("description") or "").strip().rstrip(".")
        if v.get("guide"):
            lines.append("<Video {}> is {}{}.".format(k, _guide_of_clip(pass_, v["ref"])[0],
                                                      ", showing " + desc if desc else ""))
        elif a.get("category") == "edit_source":
            lines.append("<Video {}> is the source video for the target video edit.".format(k))
        else:
            lines.append("<Video {}> is the camera-movement and pacing reference{}.".format(k, ", showing " + desc if desc else ""))
    sub_of_cast = {s["cast"]: s["number"] for s in refs.subjects if s["cast"]}
    for v_k, v in enumerate(refs.videos, 1):
        if v["soundtrack"] and v.get("anchor"):
            lines.append("<Audio {}> is the synchronized audio track of <Video {}>, the voice of <Subject {}>.".format(
                v["audio_number"], v_k, sub_of_cast.get(v.get("cast"), "?")))
            continue
        if v["soundtrack"]:
            lines.append("<Audio {}> is the synchronized audio track of <Video {}>.".format(v["audio_number"], v_k))
    for au in refs.audios:
        if au.get("song"):
            lines.append("<Audio {}> is the song this part of the film is cut to; it plays unchanged as the final "
                         "soundtrack.".format(refs.song_number))
            continue
        a = assets[au["asset"]]
        n = refs.audio_of_ref.get(au.get("ref")) or refs.audio_of_asset[au["asset"]]
        if au["cast"]:
            spk = " ({})".format(ids[au["cast"]]) if au["cast"] in ids else ""
            lines.append("<Audio {}> is the voice-timbre reference for <Subject {}>{}.".format(n, sub_of_cast.get(au["cast"], "?"), spk))
        else:
            desc = (a.get("description") or "").strip().rstrip(".")
            lines.append("<Audio {}> is {}.".format(n, desc or AUDIO_PHRASE.get(a.get("category"), "the audio reference")))
    return lines


# What a packed anchor sheet is, in the subject line of its cast member
SHEET_NOUN = {"character": "person", "location": "place", "prop": "object"}


def sheet_words(c, n):
    """"a sheet of 4 views of the same person" (place for a location, object for a prop)."""
    return "a sheet of {} views of the same {}".format(n, SHEET_NOUN.get(c.get("kind"), "subject"))


# A character's pose references in this pass
def pose_words(poses):
    """"whose pose in [Shot 2] comes from <Picture 4>" (and "in [Shot 3] from <Picture 5>" for more)."""
    bits = ["in [Shot {}] {}from <Picture {}>".format(x["shot"], "comes " if i == 0 else "", x["picture"])
            for i, x in enumerate(sorted(poses, key=lambda x: (x["shot"], x["picture"])))]
    return "whose pose " + _join_and(bits)


# Outfit and part wording in a character's subject line
OUTFIT_AS_IS = re.compile(r"^(?:with|in|without|wearing|holding|carrying)\b", re.I)


def outfit_words(name):
    """", wearing <name>" for an outfit's name, unless the name says how already ("with a big beer belly", "in a
    wheelchair", "wearing a grey suit"): then it is written as it is."""
    name = " ".join(str(name or "").split())
    return name if OUTFIT_AS_IS.match(name) else "wearing " + name


def part_words(part, assets, pictures):
    """"with <name> (<description>) shown in <Picture k>" for a prop that is part of a character; the description is
    the prop's own or its first described anchor's (cast_description). No pictures: the character's pictures (one
    sheet) or none show it on its own."""
    desc, _ = cast_description(part, assets)
    name = " ".join(str(part.get("name") or "").split()) or "a part"
    text = "with " + name + (" ({})".format(desc) if desc and name_key(desc) != name_key(name) else "")
    return text + (" shown in " + _labels("Picture", pictures) if pictures else "")


def retention_analysis(p, scene, refs, pass_, ctx=None):
    idx = _index(p, ctx)
    assets = idx["assets"]
    ref_by_id = {r["id"]: r for r in scene["refs"]}
    lines = []
    for s in refs.subjects:
        if s["cast"]:
            o = s["outfit"] or {}
            ret = o.get("retention") or "fully_preserved"
            keep = list(o.get("keep") or DEFAULT_KEEP["subject"])
        else:
            a = assets[s["asset"]]
            r = ref_by_id.get(s["ref"], {})
            ret = _retention(r, a)
            keep = _keep(r, a) or DEFAULT_KEEP.get(a.get("category"), ["overall look"])
        extra = ""
        for x in s.get("parts") or []:
            po = x.get("outfit") or {}
            pret = po.get("retention") or "fully_preserved"
            pkeep = list(po.get("keep") or DEFAULT_KEEP["prop"])
            extra += "; its {}: {} - {}".format(" ".join(str(idx["cast"][x["cast"]].get("name") or "part").split()),
                                                pret, _keep_phrase(pkeep, pret))
        lines.append("<Subject {}> ({}): {} - {}{}.".format(s["number"], _appears(p, refs, pass_, s, ctx), ret,
                                                            _keep_phrase(keep, ret), extra))
    for k, img in enumerate(refs.images, 1):
        if img["cast"] or any(k in s["pictures"] for s in refs.subjects):
            continue
        if img.get("pose"):
            subj = next((x for x in refs.subjects if x["cast"] == img["pose"]), None)
            pose = next((x for x in (subj or {}).get("poses") or [] if x["picture"] == k), None)
            if subj and pose:
                lines.append("<Picture {k}> (pose of <Subject {n}> in [Shot {sh}]): attribute_transfer - the body pose "
                             "is transferred to <Subject {n}>; the person, clothing and setting in <Picture {k}> do not "
                             "appear.".format(k=k, n=subj["number"], sh=pose["shot"]))
            continue
        if img.get("continuation"):
            lines += continuation_retention(refs.continuation)
            continue
        a = assets[img["assets"][0]]
        r = ref_by_id.get(img["ref"], {}) if img["ref"] else {}
        _, where = _guide_of_picture(scene, refs, pass_, k)
        ret = _retention(r, a) if r.get("role") == "reference" else "fully_preserved"
        keep = _keep(r, a) or DEFAULT_KEEP["keyframe"]
        lines.append("<Picture {}> ({}): {} - {}.".format(k, where or "reference image", ret, _keep_phrase(keep, ret)))
    for k, v in enumerate(refs.videos, 1):
        if any(k in s["videos"] for s in refs.subjects):
            continue
        if v.get("continuation"):
            lines.append(continuation_retention(refs.continuation)[0])
            continue
        a = assets[v["asset"]]
        r = ref_by_id.get(v["ref"], {})
        if v.get("guide"):
            lines.append("<Video {}> ({}): fully_preserved - its frames are kept as they are.".format(
                k, _guide_of_clip(pass_, v["ref"])[1]))
            continue
        ret = _retention(r, a)
        what = "source video" if a.get("category") == "edit_source" else "camera movement and pacing"
        keep = _keep(r, a) or DEFAULT_KEEP.get(a.get("category") or "camera", DEFAULT_KEEP["camera"])
        lines.append("<Video {}> ({}): {} - {}.".format(k, what, ret, _keep_phrase(keep, ret)))
    for k, v in enumerate(refs.videos, 1):
        if v["soundtrack"] and v.get("continuation"):
            lines += continuation_retention(refs.continuation)[1:]
            continue
        if v["soundtrack"] and v.get("anchor"):
            subj = next((x["number"] for x in refs.subjects if x["cast"] == v.get("cast")), "?")
            lines.append("<Audio {n}>: reference - the voice timbre and delivery of <Subject {s}> follow the sound of "
                         "<Video {k}> without copying the original signal.".format(n=v["audio_number"], s=subj, k=k))
            continue
        if v["soundtrack"]:
            r = ref_by_id.get(v["ref"], {})
            ret = r.get("soundtrack_retention") or "reference"
            lines.append("<Audio {}>: {} - {}.".format(v["audio_number"], ret, _keep_phrase(["the soundtrack of <Video {}>".format(k)], ret)))
    sub_of_cast = {s["cast"]: s["number"] for s in refs.subjects if s["cast"]}
    for au in refs.audios:
        if au.get("song"):
            ret = au["song"]["marker"]
            lines.append("<Audio {}>: {} - {}; singing lip movements, gestures, motion and cuts follow its vocals "
                         "and beat.".format(refs.song_number, ret, _keep_phrase(["its vocals, rhythm and beat"], ret)))
            continue
        a = assets[au["asset"]]
        n = refs.audio_of_ref.get(au.get("ref")) or refs.audio_of_asset[au["asset"]]
        if au["cast"]:
            lines.append("<Audio {}>: reference - the voice timbre and delivery of <Subject {}> follow <Audio {}> "
                         "without copying the original signal.".format(n, sub_of_cast.get(au["cast"], "?"), n))
        else:
            r = ref_by_id.get(au["ref"], {})
            ret = _retention(r, a)
            keep = _keep(r, a) or DEFAULT_KEEP.get(a.get("category"), ["sound"])
            lines.append("<Audio {}>: {} - {}.".format(n, ret, _keep_phrase(keep, ret)))
    return lines


# voiced (a set of the cast ids already heard in this pass): at a speaker's first line in the
# pass their voice description (cast voice_desc) is written, when Global -> Continuity -> describe_voices is on, so
# every pass tells H3 the same voice (base-en.txt 4.4: "When a speaker first appears, provide ... gender, pitch,
# timbre, speaking rate, or accent"); without it H3 picked a new voice in every pass
def _dialogue_sentence(p, refs, d, ids, ctx=None, voiced=None):
    cast = (_index(p, ctx))["cast"]
    sub_of_cast = {s["cast"]: s["number"] for s in refs.subjects if s["cast"]}
    sid = ids.get(d.get("speaker") or "", "S?")
    c = cast.get(d.get("speaker"))
    if c and c["id"] in sub_of_cast:
        who = "<Subject {}> ({})".format(sub_of_cast[c["id"]], sid)
    elif c:
        who = "{} ({})".format(c["name"], sid)
    else:
        who = "An off-screen voice ({})".format(sid)
    line = " ".join((d.get("text") or "").split())
    if line and line[-1] not in ".!?…\"'":
        line += "."
    lang = d.get("language") or "English"
    verb = (d.get("delivery") or "").strip() or "says"
    if c and voiced is not None:
        voice = voice_phrase(p, c) if c["id"] not in voiced else ""
        voiced.add(c["id"])
        if voice:
            who = "{}, {},".format(who, voice)
    if "voiceover" in verb.lower().replace("-", "").replace(" ", ""):
        return "{} says in an off-screen voiceover: <d>[{}] {}</d> while their lips remain completely closed.".format(who, lang, line)
    return "{} {}, <d>[{}] {}</d>".format(who, verb, lang, line)


VOICE_LEAD = ("a ", "an ", "the ", "his ", "her ", "their ", "its ")


def voice_phrase(p, c):
    """'with a deep, warm male voice' from cast member c's voice_desc ("" when it is empty or Global -> Continuity ->
    describe_voices is off). A description without an article gets one; one that starts with "with" or "in" is
    kept as it is."""
    if not c or not p["global"]["continuity"].get("describe_voices", True):
        return ""
    v = " ".join(str(c.get("voice_desc") or "").split()).rstrip(" .,;")
    if not v:
        return ""
    v = v[0].lower() + v[1:]
    if v.startswith(("with ", "in ")):
        return v
    if not v.startswith(VOICE_LEAD):
        v = ("an " if v[0] in "aeiou" else "a ") + v
    return "with " + v


CAMERA_NOUNS = ("shot", "close-up", "closeup", "pov", "angle", "view", "insert", "two-shot", "cutaway")


def _camera_phrase(cam):
    """'Wide' -> 'A wide shot'; full camera sentences return '' and are written as they are."""
    words = (cam or "").split()
    if not words or len(words) > 3:
        return ""
    phrase = " ".join(words)
    if not any(w.lower().strip(",.") in CAMERA_NOUNS for w in words):
        phrase += " shot"
    if words[0].lower() in ("a", "an", "the") or phrase.startswith("<"):
        return phrase
    return ("an " if phrase[0].lower() in "aeiou" else "a ") + phrase[0].lower() + phrase[1:]


# H3's camera vocabulary (base-en.txt 4.3: motion type + amplitude + speed, "written as a
# natural English action within the shot"). A shot that sets a framing (shot size / angle), camera_amp or camera_speed:
#   [Shot 1] A close-up: The camera pushes in with small amplitude at slow speed. <shot text>
#   [Shot 2] At 00:05.000, the shot cuts to a close-up: The camera pushes in with small amplitude at slow speed. <text>
#   without a framing: [Shot 1] The camera pushes in with small amplitude at slow speed. <text>
#                      [Shot 2] At 00:05.000, the shot cuts to <text>. The camera pushes in with small amplitude ...
# The camera text may be an official move ("the camera pushes in", model.DEFAULT_CAMERA) or written by hand; amplitude
# and speed are added to it (model.camera_sentence). A shot without any of the three is written exactly as before.
def _framed_shot(n, sh, cam, body):
    """The parts after "[Shot n]" for a shot with framing / camera_amp / camera_speed, else None. cam and body are
    the shot's camera text and text with this pass's labels."""
    framing, amp, speed = sh.get("framing") or "", sh.get("camera_amp") or "", sh.get("camera_speed") or ""
    head = _model.framing_phrase(framing)
    if not head and amp not in ("small", "large") and speed not in ("slow", "fast"):
        return None
    move = _model.camera_sentence(cam, amp, speed)
    rest = " ".join(x for x in (move, _sentence(body)) if x)
    parts = []
    if n == 1:
        if sh.get("continuing"):
            parts.append(CONTINUES)
        if head:
            parts.append(_sentence(head + (": " + rest if rest else "")))
        elif rest:
            parts.append(rest)
        return parts
    at = "At {}, the shot cuts to ".format(spec.fmt_time(float(sh["t"])))
    if head:
        return [_sentence(at + head + (": " + rest if rest else ""))]
    return [x for x in (_sentence(at + _lower_lead(body or "a new angle")), move) if x]


def shot_descriptions(p, scene, refs, pass_, ids, unknown, ctx=None):
    """[Shot 1] ... / [Shot N] At MM:SS.mmm, the shot cuts to ... with the lines spoken in each shot."""
    return [x["line"] for x in shot_parts(p, scene, refs, pass_, ids, unknown, ctx=ctx)]


# One entry per shot: {label, text (without dialogue), dialogue: [sentences]}
def shot_parts(p, scene, refs, pass_, ids, unknown, ctx=None, issues=None):
    shots = pass_["shots"] or [{"number": 1, "continuing": False, "t": 0.0, "camera": "", "text": ""}]
    voiced = set()
    sub = lambda t: substitute(t, p, refs, unknown, ctx=ctx, scene=scene, issues=issues).strip()
    out = []
    for n, sh in enumerate(shots, 1):
        nxt = shots[n]["t"] if n < len(shots) else None
        cam, body = sub(_model.official_camera(sh.get("camera", ""))), sub(sh.get("text", ""))
        body = _rebase_shot(body, float(pass_.get("start") or 0.0), scene.get("duration"))
        timed = ""
        lead = LEAD_CUE.match(body)
        if lead and not CUT_WORDS.match(body, lead.end()):
            timed, body = body, ""
        parts = ["[Shot {}]".format(n)]
        short = _camera_phrase(cam)
        framed = _framed_shot(n, sh, cam, body)
        if framed is not None:
            parts += framed
        elif n == 1:
            if sh.get("continuing"):
                parts.append("The shot continues seamlessly from the previous moment.")
            if short:
                parts.append(_sentence(short + (": " + body if body else "")))
            else:
                parts += [x for x in (_sentence(cam), _sentence(body)) if x]
        else:
            at = "At {}, the shot cuts to ".format(spec.fmt_time(float(sh["t"])))
            if short:
                parts.append(_sentence(at + _lower_lead(short) + (": " + body if body else "")))
            else:
                parts.append(_sentence(at + _lower_lead(body or "a new angle")))
                if cam:
                    parts.append(_sentence(cam))
        if timed:
            parts.append(timed)
        spoken = []
        times = []
        for d in pass_["dialogue"]:
            if float(d["t"]) < float(sh["t"]) - 1e-6 and n > 1:
                continue
            if nxt is not None and float(d["t"]) >= float(nxt) - 1e-6:
                continue
            spoken.append(_timed_line(float(d["t"]), _dialogue_sentence(p, refs, d, ids, ctx, voiced)))
            times.append(float(d["t"]))
        text = " ".join(parts)
        out.append({"label": "[Shot {}]".format(n), "text": text, "dialogue": spoken, "times": times,
                    "line": _place_lines(text, list(zip(times, spoken)))})
    return out


# ---- spoken lines at their time and place in the shot ----------------------------------------------------------
# Every line opens with its time in the pass, the way H3's guide times a cut: "At 00:02.400, <Subject 1> (S1) says,
# <d>[English] …</d>". In the shot's text, a sentence that opens with "At MM:SS.mmm," is a timing cue: a line goes
# after the cues at or before its time and before the later ones; with no cue, after the shot's text (as before).
def _timed_line(t, sentence):
    """'At 00:02.400, <Subject 1> (S1) says, <d>...</d>' ('An off-screen voice' reads 'an off-screen voice')."""
    s = (sentence or "").strip()
    for w in ("An ", "A ", "The "):
        if s.startswith(w):
            s = w.lower() + s[len(w):]
            break
    return "At {}, {}".format(spec.fmt_time(max(0.0, float(t))), s)


def _cue_points(text):
    """[(index, seconds)] of the sentences of `text` that open with "At MM:SS.mmm," (not inside <d>...</d>)."""
    out, pos = [], 0
    for k, x in enumerate(DIALOGUE_SPAN_SPLIT.split(text or "")):
        if k % 2 == 0:
            for m in CUE_AT.finditer(x):
                if CUT_WORDS.match(x, m.end()):
                    continue
                out.append((pos + m.start(2), int(m.group(3)) * 60 + float(m.group(4))))
        pos += len(x)
    return out


def _place_lines(text, lines):
    """`text` (a shot) with `lines` [(t, sentence)] put where they happen: after the sentences of the text that open
    with a time at or before theirs, before the later ones; in their order when they share a place."""
    if not lines:
        return text
    cues = _cue_points(text)
    cuts = [0] + [i for i, _ in cues] + [len(text)]
    slots = [[] for _ in range(len(cues) + 1)]
    for t, s in lines:
        k = sum(1 for _, c in cues if c <= float(t) + 1e-6)
        slots[k].append(s)
    out = []
    for k in range(len(cues) + 1):
        piece = text[cuts[k]:cuts[k + 1]].strip()
        out += ([piece] if piece else []) + slots[k]
    return " ".join(out)


def _keep_dialogue(parts):
    """fix() for shot lines: a written [Shot N] that left out a spoken line gets it back (word for word)."""
    spoken = {x["label"]: list(zip(x.get("times") or [0.0] * len(x["dialogue"]), x["dialogue"])) for x in parts}

    def fix(label, chunk, line):
        missing = [(t, d) for t, d in spoken.get(label, []) if line is not None and
                   not any(span in chunk for span in DIALOGUE_SPAN.findall(d))]
        return _place_lines(chunk, missing)
    return fix


def _auto_summary(refs, pass_):
    subj = [s for s in refs.subjects]
    shots = len(pass_["shots"]) or 1
    text = "The target video{} unfolds over {} shot{}.".format(
        " shows " + _join_and("<Subject {}>".format(s["number"]) for s in subj) + " and" if subj else "",
        shots, "s" if shots > 1 else "")
    voice = [a for a in refs.audios if a["cast"]]
    if voice:
        text += " " + _join_and("<Audio {}>".format(refs.audio_of_asset[a["asset"]]) for a in voice) + \
                (" provides" if len(voice) == 1 else " provide") + " the voice timbre."
    if refs.song_number:
        text += " The picture is cut to <Audio {}>: mouths, movement and cuts follow its vocals and beat.".format(
            refs.song_number)
    c = refs.continuation
    if c and c["kind"] == "picture":
        text += " It starts on {}, the last frame of the scene before.".format(c["label"])
    elif c:
        text += " It continues seamlessly from the final frames of {}, the end of {}.".format(c["label"], _cont_before(c))
    return text


# ---- the summary of one pass of a multi-pass scene ------------------------------------------------------------------
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _first_sentence(text):
    """The first sentence of a text, on one line, without spoken lines (<d>...</d>)."""
    text = " ".join(DIALOGUE_SPAN.sub(" ", text or "").split())
    return SENTENCE_END.split(text, 1)[0].strip() if text else ""


def pass_summary(p, scene, refs, pass_, unknown, ctx=None, issues=None):
    """The automatic summary of one pass of a multi-pass scene whose scene summary is a whole-scene note: the opening
    of _auto_summary (who is in it, how many shots), this pass's shot flow (the first sentence of each of its shots'
    text, with this pass's labels), who speaks in it, then _auto_summary's voice, song and continuation sentences.
    ref-en.txt 3: the summary describes "the main subjects, shot flow, and roles of the reference assets"."""
    auto = _auto_summary(refs, pass_)
    shots = len(pass_["shots"]) or 1
    head = "The target video{} unfolds over {} shot{}.".format(
        " shows " + _join_and("<Subject {}>".format(s["number"]) for s in refs.subjects) + " and" if refs.subjects
        else "", shots, "s" if shots > 1 else "")
    tail = auto[len(head):] if auto.startswith(head) else ""
    flow = []
    for sh in pass_["shots"]:
        first = _first_sentence(substitute(sh.get("text", ""), p, refs, unknown, ctx=ctx, scene=scene, issues=issues))
        if first:
            flow.append(_sentence(first))
    cast = _index(p, ctx)["cast"]
    sub_of_cast = {s["cast"]: s["number"] for s in refs.subjects if s["cast"]}
    who = []
    for d in pass_["dialogue"]:
        sp = d.get("speaker") or ""
        name = "<Subject {}>".format(sub_of_cast[sp]) if sp in sub_of_cast else \
            cast[sp]["name"] if sp in cast else "an off-screen voice"
        if name not in who:
            who.append(name)
    speak = _sentence(_join_and(who) + (" speaks." if len(who) == 1 else " speak.")) if who else ""
    return " ".join(x for x in [head] + flow + [speak, tail.strip()] if x)


# ---- written shot lines and pass prompts --------------------------------------------------------------------------

def _rebase_clock(text, offset):
    """MM:SS.mmm times written in scene time -> this pass's time (a pass starts `offset` seconds into the scene)."""
    if abs(offset) < 1e-9:
        return text
    return CLOCK.sub(lambda m: spec.fmt_time(max(0.0, int(m.group(1)) * 60 + float(m.group(2)) - offset)), text)


# "At MM:SS.mmm," opening a sentence: a time on the shot's timeline
# Also after "…" and after a colon ("A close-up: At 00:02.000, she turns"), as
# shotfill.js CUES
CUE_TIME = re.compile(r"(^\s*|[.!?…]\s+|:\s+)(At\s+)(\d{1,2}):(\d{2}(?:\.\d{1,3})?)(?=\s*,)")
# A cue that opens a shot ("[Shot 1] At 00:02.000, she turns") is a cue for placing lines too; a
# cut ("At 00:06.000, the shot cuts to") is not
CUE_AT = re.compile(r"(^\s*|[.!?…]\s+|:\s+|\]\s+)(At\s+)(\d{1,2}):(\d{2}(?:\.\d{1,3})?)(?=\s*,)")
CUT_WORDS = re.compile(r"\s*,\s*the\s+(?:shot|camera)\s+(?:cuts|transitions|changes|switches|dissolves|fades)\s+to\b", re.I)
LEAD_CUE = re.compile(r"^At\s+\d{1,2}:\d{2}(?:\.\d{1,3})?(?=\s*,)")


def _rebase_shot(text, offset, limit=None):
    """The times of a written shot line that are on the scene's timeline -> this
    pass's time (a pass starts `offset` seconds into the scene): the cut time of its leading "At MM:SS, the shot cuts
    to", and a sentence that opens with "At MM:SS," (a timing cue such as "At 00:16.000, @Mara mutters") when that
    time lies inside the scene (`limit`, its length). Every other time is left as written: a clock in the action
    ("the clock reading 10:30") and anything inside a spoken line <d>…</d> ("the last ferry leaves at 11:45")."""
    if abs(offset) < 1e-9 or not text:
        return text

    def shift(t):
        return spec.fmt_time(max(0.0, t - offset))
    lead = ""
    m = CUT_LEAD.match(text)
    if m:
        lead = CLOCK.sub(lambda c: shift(int(c.group(1)) * 60 + float(c.group(2))), m.group(0), count=1)
        text = text[m.end():]

    def cue(c):
        t = int(c.group(3)) * 60 + float(c.group(4))
        if limit is not None and t > float(limit) + 1e-6:
            return c.group(0)
        return c.group(1) + c.group(2) + shift(t)
    parts = DIALOGUE_SPAN_SPLIT.split(text)  # odd items are spoken lines
    return lead + "".join(x if k % 2 else CUE_TIME.sub(cue, x) for k, x in enumerate(parts))


DIALOGUE_SPAN_SPLIT = re.compile(r"(<d>.*?</d>)", re.S)


def _cut_object(body):
    """'A medium shot: ...' / 'Rain.' read after 'the shot cuts to': the first word in lower case when it is an
    article or a plain capitalised word (not a <label> or an all-caps word)."""
    body = (body or "").strip()
    if not body:
        return "a new angle."
    word = re.match(r"[A-Za-z]+", body)
    w = word.group(0) if word else ""
    if w == "A" or (len(w) > 1 and w[0].isupper() and w[1:].islower()):
        return body[0].lower() + body[1:]
    return body


# A leading "At MM:SS.mmm," is a cut only with the cut's words or
# when no spoken line follows in its sentence; "At 00:01.500, @Mara (S1) says, <d>…</d>" is that line's time (Write
# prompts asks the LLM for it), which CUT_LEAD (the words optional) would take for the cut
CUT_STRICT = re.compile(r"^At\s+\d{1,2}:\d{2}(?:\.\d{1,3})?\s*,\s*the\s+(?:shot|camera)\s+"
                        r"(?:cuts|transitions|changes|switches|dissolves|fades)\s+to\s+", re.I)
SENTENCE_STOP = re.compile(r"[.!?\u2026](?=\s|$)")


def _lead_kind(body):
    """What a leading "At MM:SS.mmm," of a written shot is: "cut" (with the cut's words), "line" (a spoken line <d>…</d>
    follows in the same sentence: its time), "time" (anything else: read as the cut, as before) or "" (none)."""
    body = (body or "").lstrip()
    m = CUT_LEAD.match(body)
    if not m:
        return ""
    if CUT_STRICT.match(body):
        return "cut"
    rest = body[m.end():]
    d = rest.find("<d>")
    stop = SENTENCE_STOP.search(rest)
    return "line" if d >= 0 and (stop is None or d < stop.start()) else "time"


def _drop_cut_lead(body):
    """'At 00:14.375, the shot cuts to a medium shot: ...' -> 'A medium shot: ...' (the first shot has no cut)."""
    if _lead_kind(body) == "line":
        return body
    m = CUT_LEAD.match(body)
    if not m:
        return body
    rest = body[m.end():].strip()
    return rest[:1].upper() + rest[1:]


def written_shots(scene, plan, pass_, text):
    """The part of a written detailed_description that belongs to this pass. Written [Shot N] use the scene's shot
    numbers; each pass numbers its own shots from 1, so:
    - text before [Shot 1] (style sentences) goes to every pass;
    - [Shot N] goes to the pass(es) holding scene shot N, renumbered; its timeline times move to pass time (the
      cut lead and "At MM:SS," cues only, see _rebase_shot); the first
      shot of a pass loses its cut time (and says it continues when the shot carries on from the pass before);
      a later shot without a cut time gets the pass's;
    - [Shot N] past the scene's shots follows the last pass's shots ("extra");
    - a scene with no shots on the timeline: the lines go to every pass as written ("unplaced" when that is more
      than one pass).
    Returns {"text", "extra": [N], "unplaced": [N]}."""
    pre, chunks = _chunks(text, SHOT_START)
    if not chunks:
        return {"text": text or "", "extra": [], "unplaced": []}
    passes = plan["passes"]
    placed = {sh["number"] for x in passes for sh in x["shots"]}
    numbers = [int(SHOT_NUMBER.match(label).group(1)) for label, _ in chunks]
    if not placed:
        return {"text": text, "extra": [], "unplaced": sorted(set(numbers)) if len(passes) > 1 else []}
    local = {sh["number"]: (n, sh) for n, sh in enumerate(pass_["shots"], 1)}
    last = pass_["index"] == len(passes)
    offset = float(pass_["start"])
    out, extra = ([pre] if pre else []), []
    for k, (label, chunk) in zip(numbers, chunks):
        body = _rebase_shot(chunk[len(label):].strip(), offset, scene.get("duration"))
        if k in local:
            n, sh = local[k]
            if n == 1:
                body = _drop_cut_lead(body)
                if sh.get("continuing") and pass_["index"] > 1 and "continues" not in body.lower():
                    body = (CONTINUES + " " + body).strip()
            elif _lead_kind(body) == "line":
                body = "At {}, the shot cuts to a new angle. {}".format(spec.fmt_time(float(sh["t"])), body)
            elif not CUT_LEAD.match(body):
                body = "At {}, the shot cuts to {}".format(spec.fmt_time(float(sh["t"])), _cut_object(body))
        elif k in placed or not last:
            continue  # another pass holds this shot
        else:
            extra.append(k)
            n = len(pass_["shots"]) + len(extra)
        out.append("[Shot {}] {}".format(n, body).strip())
    return {"text": "\n".join(out), "extra": extra, "unplaced": []}


SUMMARY_LINE = re.compile(r"^[ \t]*summary[ \t]*:[ \t]*", re.M | re.I)


def _strip_task_tags(text):
    """Text without a leading [task + tags] (only when every part is one of H3's task types)."""
    lead = LEADING_TAGS.match(text or "")
    if lead and all(t.strip().lower() in spec.TASK_TAG_ORDER for t in lead.group(1).split("+")):
        return text[lead.end():]
    return text or ""


def place_task_tags(text, tag_line):
    """The task tags exactly once: at the start of the summary of a six-section prompt (a pass edited by hand, a
    Split answer, a raw prompt in Ref2VA form), else at the start of the text. Task tags already written there are
    replaced by the ones this pass needs; "[Shot 1] ..." is not a task tag."""
    if not tag_line:
        return text
    labels = {m.group(1).lower() for m in SECTION_LABEL.finditer(text)}
    m = SUMMARY_LINE.search(text) if len(labels) >= 2 and "summary" in labels else None
    if not m:
        return (tag_line + " " + _strip_task_tags(text).strip()).strip()
    rest = text[m.end():]
    gap = re.match(r"[ \t]*\n?[ \t]*", rest).group(0)
    body = _strip_task_tags(rest[len(gap):])
    if re.match(r"N/A[ \t]*(?:\n|$)", body):
        body = body[3:]
    if body[:1] not in ("", "\n"):
        body = " " + body
    return text[:m.end()] + gap + tag_line + body


def build_pass(p, scene, scene_index, plan, pass_, ctx=None):
    """Return the prompt and reference plan for one pass. ctx: prepare(p), shared by every scene and pass of the
    same project state."""
    ctx = _ctx(p, ctx)
    pr = scene["prompt"]
    override = (pr.get("pass_prompts") or {}).get(str(pass_["index"]), "")
    override = override if isinstance(override, str) else ""
    shots_written = None
    eff, rich = None, False
    if override.strip():
        sources = [override]
    elif pr["mode"] == "raw":
        sources = [pr["raw"]]
    else:
        ps = _model.pass_sections(p, scene, plan, pass_["index"])
        eff = dict(pr["sections"])  # keys other than the six stay, as before
        eff.update(ps["used"])
        if ps["source"]["detailed_description"] == "pass":  # written for this pass: [Shot N] in its own numbering
            shots_written = {"text": eff["detailed_description"], "extra": [], "unplaced": []}
        else:
            # only the written shot lines of this pass, and its timeline shots, can name a guide picture or clip
            shots_written = written_shots(scene, plan, pass_, pr["sections"]["detailed_description"])
        rich = len(plan["passes"]) > 1 and ps["source"]["summary"] != "pass" and \
            bool(_strip_task_tags(pr["sections"]["summary"]).strip())
        sources = [v for k, v in eff.items() if k != "detailed_description"] + [shots_written["text"]]
        if pr["auto"].get("shots") or rich:  # rich: pass_summary quotes the shots
            sources += ["{} {}".format(sh.get("camera", ""), sh.get("text", "")) for sh in pass_["shots"]]
    mentioned = set()
    for t in sources:
        mentioned |= mentioned_codes(t)
    issues = []
    cont = continuation_of(p, scene, scene_index, pass_, ctx)
    written_text = "\n".join(t for t in sources if isinstance(t, str))
    if cont and FIXED_NUMBERS[cont["kind"]].search(written_text) and not OWN_DEFINITION.search(written_text):
        issues.append({"level": "info", "tag": "", "message": "{} is only anchored, not named {}: the prompt uses fixed "
                       "reference numbers (<Picture N>, <Video N>, <Audio N>) that naming it would move; write @tags "
                       "instead (@tail for it)".format(CONT_WHAT[cont["source"]], _cont_label(cont))})
        cont = None
    refs = collect_refs(p, scene, scene_index, pass_, len(plan["passes"]), mentioned, ctx=ctx, continuation=cont)
    over = over_budget(refs) if cont else None
    if over:
        refs = collect_refs(p, scene, scene_index, pass_, len(plan["passes"]), mentioned, ctx=ctx)
        issues.append({"level": "warn", "tag": "", "message": "{} is only anchored, not named {}: with it this pass "
                       "would send {} pictures, {} videos and {} files (H3 takes up to 9, 3 and 12); pack cast pictures "
                       "into a sheet or remove a reference to make room".format(
                           CONT_WHAT[cont["source"]], _cont_label(cont), *over)})
    elif refs.continuation and refs.continuation["kind"] == "video" and not refs.continuation["audio_number"]:
        issues.append({"level": "info", "tag": "", "message": "{} is sent as <Video 1> without its sound: the {} audio "
                       "slots are taken".format(CONT_WHAT[cont["source"]], spec.MAX_REF_AUDIOS)})
    issues += anchor_issues(refs, ctx["index"])
    tags = task_tags(p, scene, refs, ctx=ctx)
    tag_line = "[{}]".format(" + ".join(tags)) if tags else ""
    unknown = []

    def sub(t):
        return substitute(t, p, refs, unknown, ctx=ctx, scene=scene, issues=issues)

    if override.strip() or pr["mode"] == "raw":
        body = sub(override if override.strip() else pr["raw"]).strip()
        if refs.continuation:
            body = _name_in_written(body, refs)
        text = place_task_tags(body, tag_line)
    else:
        sec = {k: sub(v).strip() for k, v in eff.items() if k != "detailed_description"}
        sec["detailed_description"] = sub(shots_written["text"]).strip()
        for k in shots_written["extra"]:
            issues.append({"level": "info", "tag": "", "message": "a written [Shot {}] has no shot on the timeline "
                           "(the scene has {}), so it follows the last shot".format(k, len(scene["shots"]))})
        if shots_written["unplaced"]:
            issues.append({"level": "warn", "tag": "", "message": "the written [Shot N] lines go to every pass, because "
                           "the scene has no shots on the timeline; add the shots there so each pass gets its own"})
        auto = pr["auto"]
        ids = speaker_ids(pass_)
        labelled = lambda lines, pattern: [((pattern.match(x).group("label") if pattern.match(x) else ""), x) for x in lines]
        subj = _merge(labelled(subject_definitions(p, scene, refs, pass_, ids, ctx), LABEL_START) if auto.get("subjects") else [],
                      sec["subject_definitions"], LABEL_START, _with_sources(refs))
        written = _strip_task_tags(sec["summary"]).strip()  # the task tags are always added below
        if rich:
            summary = pass_summary(p, scene, refs, pass_, unknown, ctx=ctx, issues=issues)
        else:
            summary = written or (_auto_summary(refs, pass_) if auto.get("subjects") else "")
        summary = " ".join(x for x in (tag_line, summary) if x)
        ret = _merge(labelled(retention_analysis(p, scene, refs, pass_, ctx), LABEL_START) if auto.get("retention") else [],
                     sec["retention_analysis"], LABEL_START)
        parts = shot_parts(p, scene, refs, pass_, ids, unknown, ctx=ctx, issues=issues) if auto.get("shots") else []
        desc = _merge([(x["label"], x["line"]) for x in parts],
                      sec["detailed_description"], SHOT_START, _keep_dialogue(parts), pre_first=True)
        c = refs.continuation
        if c:
            desc = _cite_continuation(desc, c)
            if not any(_labelled(x, c["label"]) for x in subj):
                subj = _cont_definitions(c) + subj
            if not any(_labelled(x, c["label"]) for x in ret):
                ret = continuation_retention(c) + ret
        body = {
            "subject_definitions": "\n".join(subj), "summary": summary, "retention_analysis": "\n".join(ret),
            "detailed_description": "\n".join(desc), "overall_soundscape": sec["overall_soundscape"],
            "non_diegetic_music": sec["non_diegetic_music"],
        }
        text = "\n\n".join("{}:\n{}".format(k, body[k].strip() or "N/A") for k in REF2VA_SECTIONS)

    tag_map = {}
    idx = ctx["index"]
    for aid, k in refs.picture_of_asset.items():
        tag_map["@" + idx["assets"][aid]["code"]] = "<Picture {}>".format(k)
    for aid, k in refs.video_of_asset.items():
        tag_map["@" + idx["assets"][aid]["code"]] = "<Video {}>".format(k)
    for aid, k in refs.audio_of_asset.items():
        tag_map["@" + idx["assets"][aid]["code"]] = "<Audio {}>".format(k)
    for rid, tok in _model.ref_tokens(p, scene, idx).items():
        if "." not in tok:
            continue
        r2 = refs.ref_alias.get(rid, rid)
        for table, label in ((refs.subject_of_ref, "Subject"), (refs.video_of_ref, "Video"), (refs.audio_of_ref, "Audio")):
            if r2 in table:
                tag_map[tok] = "<{} {}>".format(label, table[r2])
                break
    if refs.song_number:
        tag_map["@soundtrack"] = "<Audio {}>".format(refs.song_number)
    if refs.continuation:
        tag_map["@tail"] = refs.continuation["label"]
    for s in refs.subjects:
        if s["cast"]:
            tag_map["@" + idx["cast"][s["cast"]]["name"]] = "<Subject {}>".format(s["number"])
        elif refs.subject_of_asset.get(s["asset"]) == s["number"]:
            tag_map["@" + idx["assets"][s["asset"]]["code"]] = "<Subject {}>".format(s["number"])

    # continuation: refs.continuation, the reference 1 this pass continues from, or None;
    # its entry in images / videos has "continuation": True and a "source" (prev_scene_last, prev_scene_tail,
    # prev_pass_tail) instead of an asset
    return {"prompt": text, "tags": tags, "tag_map": tag_map, "unknown": sorted(set(unknown)), "issues": issues,
            "images": refs.images, "videos": refs.videos, "audios": refs.audios,
            "guides": refs.guides, "subjects": refs.subjects, "continuation": refs.continuation}


# Clean up what the LLM rewriter returns before it is offered as a proposal.
SECTION_LABEL = re.compile(r"^[ \t]*(subject_definitions|summary|retention_analysis|detailed_description|"
                           r"overall_soundscape|non_diegetic_music)[ \t]*:[ \t]*", re.M)


def _token(key):
    """'@Old Keeper' -> '@{Old Keeper}' (tag_map keys hold the plain name)."""
    return tag_token(key[1:])  # same name rule as the tags themselves ("@O'Brien" stays plain)


# LLM answers sometimes hold a list or an object where text belongs
def as_text(value):
    """Readable text for any JSON value: lists become lines, objects "key: value" lines (a {"text"/"prompt": …}
    object its text, six sections their labelled layout); never a Python repr."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return "" if value != value else ("{:g}".format(value) if isinstance(value, float) else str(value))
    if isinstance(value, (list, tuple)):
        return "\n".join(t for t in (as_text(v).strip() for v in value) if t)
    if isinstance(value, dict):
        if any(k in value for k in REF2VA_SECTIONS):
            return "\n\n".join("{}:\n{}".format(k, as_text(value.get(k)).strip() or "N/A") for k in REF2VA_SECTIONS)
        for k in ("prompt", "text", "content", "value"):
            if isinstance(value.get(k), str):
                return value[k]
        return "\n".join("{}: {}".format(k, as_text(v).strip()) for k, v in value.items() if as_text(v).strip())
    return str(value)


def tidy_rewrite(proposal, before, auto, tag_map=None, new_shots=False):
    """proposal / before: the six sections. auto: the scene's automatic parts. tag_map: pass 1's "@P1" -> "<Picture 1>".

    - a whole six-section prompt returned inside one key is split back into its sections;
    - a value that starts with its own label ("summary: ...") loses the label;
    - <Subject N>, <Picture N>, <Video N>, <Audio N> are turned back into the @ tokens they stand for, so the text
      still works when a pass numbers references differently;
    - parts the editor writes automatically are not taken from the LLM: subject definitions and retention lines
      keep their previous text, and detailed_description keeps only what comes before [Shot 1], plus the [Shot N]
      lines that were written by hand before (the LLM's version of them when it returned one; v0.6.0);
    - new_shots: the scene has no shots on the timeline and the LLM was asked to write
      them, so detailed_description keeps every [Shot N] line it wrote (the editor puts them on the timeline).
    """
    out = {k: as_text(proposal.get(k)) for k in REF2VA_SECTIONS}
    given = {k for k in REF2VA_SECTIONS if proposal.get(k) is not None}
    for k in REF2VA_SECTIONS:
        found = list(SECTION_LABEL.finditer(out[k]))
        if len(found) >= 2:  # the whole prompt in one key
            text = out[k]
            for i, m in enumerate(found):
                end = found[i + 1].start() if i + 1 < len(found) else len(text)
                body = text[m.end():end].strip()
                if m.group(1) == k or not out[m.group(1)].strip():
                    out[m.group(1)] = body
                    given.add(m.group(1))
        elif len(found) == 1 and found[0].start() == len(out[k]) - len(out[k].lstrip()) and found[0].group(1) == k:
            out[k] = out[k][found[0].end():]
    inverse = {}
    for key, label in (tag_map or {}).items():
        if key.startswith("@"):
            inverse.setdefault(label, _token(key))
    if inverse:
        pattern = re.compile("|".join(re.escape(x) for x in sorted(inverse, key=len, reverse=True)))
        out = {k: pattern.sub(lambda m: inverse[m.group(0)], v) for k, v in out.items()}
    if auto.get("subjects"):
        out["subject_definitions"] = str(before.get("subject_definitions") or "")
    if auto.get("retention"):
        out["retention_analysis"] = str(before.get("retention_analysis") or "")
    if auto.get("shots"):
        pre, theirs = _chunks(out["detailed_description"], SHOT_START)
        _, mine = _chunks(str(before.get("detailed_description") or ""), SHOT_START)
        rewritten = {}
        for label, chunk in theirs:
            rewritten.setdefault(label, chunk)
        if "detailed_description" not in given:
            pre = _chunks(str(before.get("detailed_description") or ""), SHOT_START)[0]
        if new_shots and theirs and "detailed_description" in given:
            out["detailed_description"] = "\n".join([pre] + [chunk for label, chunk in theirs]).strip()
        else:
            out["detailed_description"] = "\n".join([pre] + [rewritten.get(label, chunk) for label, chunk in mine]).strip()
        given.add("detailed_description")
    for k in REF2VA_SECTIONS:  # sections the reply left out keep their text
        if k not in given:
            out[k] = str(before.get(k) or "")
    return {k: v.strip() for k, v in out.items()}
