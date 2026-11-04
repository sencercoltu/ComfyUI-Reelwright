"""Per-pass prompt assembly and reference numbering.

The editor refers to assets as @P1 / @V2 / @A1, to cast as @Mara or
@{Old Keeper}, and to the continuation as @tail. Each pass gets its own
numbering in the order MiniMaxH3ReferenceToVideo presents references:
images, then videos (a video's soundtrack takes its <Audio j> number right
before its <Video k>), then standalone audio.
"""

import functools  # added 2026-11-03 v0.6.0
import itertools  # added 2026-11-03 v0.6.0
import os  # added 2026-11-03 v0.6.0
import re
import unicodedata  # added 2026-11-03 v0.6.0

from . import spec
from . import model as _model  # added 2026-11-03 v0.6.0: feature-detects newer model helpers (effective_start)
# [OLD 2026-11-02 v0.3.3->v0.3.4] from .model import project_index
# [OLD 2026-11-03 v0.4.3->v0.5.0] from .model import cast_description, project_index
from .model import cast_description, project_index, scene_starts  # scene_starts: added 2026-11-03 v0.5.0
from .planner import continuation_depth
from . import soundtrack  # added 2026-11-03 v0.5.0

# [OLD 2026-11-03 v0.5.1->v0.6.0] any "@word" was a tag (e-mail addresses, @handles), names were ASCII only, @@ was no escape
# TAG_RE = re.compile(r"@\{([^}]+)\}|@([A-Za-z][\w-]*)")
# [/OLD]


# ---- tag syntax (added 2026-11-03 v0.6.0, same rule as the editor's prompttext.js / model.js) --------------------
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


def __getattr__(name):  # added 2026-11-03 v0.6.0: prompt.TAG_RE / TAG_OR_ESCAPE / NAME_RE, built on first use
    if name in ("TAG_RE", "TAG_OR_ESCAPE", "NAME_RE"):
        return _patterns()[name]
    raise AttributeError("module {!r} has no attribute {!r}".format(__name__, name))


def tag_re():
    """The tag pattern: group(1) is a @{braced name}, group(2) a plain name (added 2026-11-03 v0.6.0)."""
    return _patterns()["TAG_RE"]


CODE_LIKE = re.compile(r"[PVA]\d+", re.I)  # added 2026-11-03 v0.6.0: an unknown name like this is a mistyped asset
POSSESSIVE = re.compile(r"^(.+?)(['’][sS])$")  # added 2026-11-03 v0.6.0: "@Mara's coat" -> <Subject 1>'s coat


def name_key(name):
    """Cast names compare without case and with ’ as ' (added 2026-11-03 v0.6.0)."""
    return " ".join(str(name or "").replace("’", "'").split()).lower()


def tag_token(name):
    """"@Mara", "@O'Brien" or "@{Old Keeper}": the plain form when the whole name reads as one tag
    (added 2026-11-03 v0.6.0)."""
    name = str(name or "").strip()
    return "@" + name if _patterns()["NAME_RE"].fullmatch(name) else "@{" + name + "}"

# added 2026-11-02 v0.2.0: wording that follows MiniMax's official Ref2VA prompt guide
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

# added 2026-11-03 v0.4.1: a written line (by hand or by the LLM rewriter) that starts with a label the editor also
# writes automatically replaces the automatic line instead of repeating it. Labels count at the start of the text,
# of a line or of a sentence.
LABEL_START = re.compile(r"(?:^|(?<=\n)|(?<=[.!?] ))[ \t]*(?P<label><(?:Subject|Picture|Video|Audio) \d+>)")
SHOT_START = re.compile(r"(?:^|(?<=\n)|(?<=[.!?] ))[ \t]*(?P<label>\[Shot \d+\])")
DIALOGUE_SPAN = re.compile(r"<d>.*?</d>", re.S)
# [OLD 2026-11-03 v0.5.1->v0.6.0] LEADING_TAGS = re.compile(r"^\s*\[([a-z +]+)\]\s*")  (now any case)
LEADING_TAGS = re.compile(r"^\s*\[([a-z +]+)\]\s*", re.I)
# added 2026-11-03 v0.6.0: written shot lines and pass prompts
SHOT_NUMBER = re.compile(r"\[Shot (\d+)\]")
CLOCK = re.compile(r"\b(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\b")
CUT_LEAD = re.compile(r"^At\s+\d{1,2}:\d{2}(?:\.\d{1,3})?\s*,\s*(?:the\s+shot\s+cuts\s+to\s+)?", re.I)
CONTINUES = "The shot continues seamlessly from the previous moment."


# added 2026-11-03 v0.6.0: what the prompt builder needs about the whole project, computed once per /plan or run
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
    """model.effective_start when model has it (v0.6.0), else the same rule without the 5-frame cap."""
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
        # added 2026-11-02 v0.2.0: reference assets that define reusable visible content are
        # <Subject N> in H3's Ref2VA guide; @P2 then resolves to that subject.
        self.subject_of_asset = {}
        self.song_number = None  # added 2026-11-03 v0.5.0: <Audio N> of the soundtrack segment
        self.guided = set()  # added 2026-11-03 v0.6.0: ids of the scene refs that guide this pass

    def number(self):
        for k, img in enumerate(self.images, 1):
            for a in img["assets"]:
                self.picture_of_asset.setdefault(a, k)
        audio_n = 0
        for k, v in enumerate(self.videos, 1):
            if v["soundtrack"]:
                audio_n += 1
                v["audio_number"] = audio_n
            self.video_of_asset.setdefault(v["asset"], k)
        for a in self.audios:
            audio_n += 1
            # [OLD 2026-11-03 v0.4.3->v0.5.0] self.audio_of_asset.setdefault(a["asset"], audio_n)
            if a.get("song"):  # added 2026-11-03 v0.5.0
                self.song_number = audio_n
            else:
                self.audio_of_asset.setdefault(a["asset"], audio_n)

    @property
    def file_count(self):
        return len(self.images) + len(self.videos) + len(self.audios)


# added 2026-11-03 v0.6.0
GUIDE_KEYS = (("first_frame", "first frame"), ("keyframes", "keyframe"), ("last_frame", "last frame"))


def guided_refs(pass_):
    """Ids of the scene refs that guide this pass (first frame, keyframes, last frame), added 2026-11-03 v0.6.0."""
    return {g["ref"] for key, _ in GUIDE_KEYS for g in pass_.get(key) or []}


# [OLD 2026-11-03 v0.5.1->v0.6.0] def collect_refs(p, scene, scene_index, pass_, n_passes, mentioned_codes=()):
#     idx = project_index(p)
# [/OLD]
def collect_refs(p, scene, scene_index, pass_, n_passes, mentioned_codes=(), ctx=None):  # ctx: added 2026-11-03 v0.6.0
    ctx = _ctx(p, ctx)
    idx = ctx["index"]
    assets, cast = idx["assets"], idx["cast"]
    refs = PassRefs()
    # added 2026-11-03 v0.6.0: a first/last/keyframe picture or clip named in the text is sent only to the pass it guides
    guided = guided_refs(pass_)
    speaking = {d.get("speaker") for d in pass_["dialogue"]}

    speakers = [d["speaker"] for d in scene["dialogue"] if d.get("speaker")]
    cast_entries = list(scene["cast"])
    for sp in speakers:
        if sp in cast and not any(c["id"] == sp for c in cast_entries):
            cast_entries.append({"id": sp, "outfit": ""})

    # added 2026-11-03 v0.4.1: anchors first, so "auto" packing can count every picture of the pass
    entries = []
    for entry in (e for e in cast_entries if e["id"] in cast):
        c = cast[entry["id"]]
        outfit = next((o for o in c["outfits"] if o["id"] == (entry.get("outfit") or c["default_outfit"])), None)
        anchor_ids = [a for a in c["anchors"] if a in assets and assets[a]["kind"] == "image"]
        if outfit:
            anchor_ids += [a for a in outfit["assets"] if a in assets and assets[a]["kind"] == "image" and a not in anchor_ids]
        entries.append((entry, c, outfit, anchor_ids))
    # [OLD 2026-11-03 v0.5.1->v0.6.0] a mentioned guide picture counted in every pass
    # unpacked = len({a for *_, ids in entries for a in ids}) + len(
    #     {r["asset"] for r in scene["refs"] if r["asset"] in assets and assets[r["asset"]]["kind"] == "image" and
    #      (r["role"] == "reference" or assets[r["asset"]]["code"].upper() in mentioned_codes)} -
    #     {a for *_, ids in entries for a in ids})
    # [/OLD]
    unpacked = len({a for *_, ids in entries for a in ids}) + len(
        {r["asset"] for r in scene["refs"] if r["asset"] in assets and assets[r["asset"]]["kind"] == "image" and
         (r["role"] == "reference" or (r["id"] in guided and assets[r["asset"]]["code"].upper() in mentioned_codes))} -
        {a for *_, ids in entries for a in ids})
    auto_pack = unpacked > spec.MAX_REF_IMAGES

    # [OLD 2026-11-03 v0.4.0->v0.4.1] for n, entry in enumerate(e for e in cast_entries if e["id"] in cast):
    #     c = cast[entry["id"]]
    #     outfit = next((o for o in c["outfits"] if o["id"] == (entry.get("outfit") or c["default_outfit"])), None)
    #     anchor_ids = [a for a in c["anchors"] if a in assets and assets[a]["kind"] == "image"]
    #     if outfit:
    #         anchor_ids += [a for a in outfit["assets"] if a in assets and assets[a]["kind"] == "image" and a not in anchor_ids]
    #     first_pic = len(refs.images) + 1
    #     if anchor_ids and c["pack_sheet"] and len(anchor_ids) > 1:
    # added 2026-11-03 v0.5.0: the part of the soundtrack this pass covers. It carries the singing, so the cast
    # voice references are left out when it is sent.
    # [OLD 2026-11-03 v0.5.1->v0.6.0] song = soundtrack.pass_soundtrack(p, scene_starts(p)[0][scene["id"]], pass_)  (starts from ctx)
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
        # [OLD 2026-11-02 v0.1.0->v0.2.0] subjects now carry ref/asset/videos keys for reference subjects
        # refs.subjects.append({"cast": c["id"], "number": n + 1, "outfit": outfit,
        #                       "pictures": list(range(first_pic, len(refs.images) + 1))})
        # [/OLD]
        refs.subjects.append({"cast": c["id"], "ref": None, "asset": None, "number": n + 1, "outfit": outfit,
                              "pictures": list(range(first_pic, len(refs.images) + 1)), "videos": []})
        # [OLD 2026-11-03 v0.4.3->v0.5.0] if c.get("voice") in assets and assets[c["voice"]]["kind"] == "audio":
        # [OLD 2026-11-03 v0.5.1->v0.6.0] if c.get("voice") in assets and assets[c["voice"]]["kind"] == "audio" and not song:  (a voice went to every pass, spoken or not)
        # added 2026-11-03 v0.6.0: a voice reference only goes to the passes where that character speaks (the
        # reference budget counts it the same way, model.scene_media_counts / model.js sceneBudget)
        if c.get("voice") in assets and assets[c["voice"]]["kind"] == "audio" and not song and c["id"] in speaking:
            refs.audios.append({"asset": c["voice"], "ref": None, "cast": c["id"]})
    if song:
        refs.audios.append({"asset": None, "ref": None, "cast": None, "song": song})

    guide_only = {"first_frame", "last_frame", "keyframe"}
    for r in scene["refs"]:
        a = assets.get(r["asset"])
        if not a:
            continue
        if r["role"] in guide_only:
            # [OLD 2026-11-03 v0.5.1->v0.6.0] a guide picture named anywhere in the scene's text went to every pass; a guide clip never
            # if a["kind"] == "image" and a["code"].upper() in mentioned_codes and not any(a["id"] in img["assets"] for img in refs.images):
            #     refs.images.append({"assets": [a["id"]], "cast": None, "ref": r["id"]})
            # [/OLD]
            if r["id"] not in guided or a["code"].upper() not in mentioned_codes:
                continue
            if a["kind"] == "image" and not any(a["id"] in img["assets"] for img in refs.images):
                refs.images.append({"assets": [a["id"]], "cast": None, "ref": r["id"]})
            elif a["kind"] == "video" and not any(v["asset"] == a["id"] for v in refs.videos):
                # added 2026-11-03 v0.6.0: a guide clip named in the text is also sent as <Video k> (ref-en.txt 2.3:
                # the clip the target continues from), described by its place in the pass
                refs.videos.append({"asset": a["id"], "soundtrack": False, "ref": r["id"], "guide": True})
            continue
        if a["kind"] == "image":
            # added 2026-11-02 v0.2.0: an asset already sent (cast anchor or another ref) is not sent twice
            if any(a["id"] in img["assets"] for img in refs.images):
                continue
            refs.images.append({"assets": [a["id"]], "cast": None, "ref": r["id"]})
        elif a["kind"] == "video":
            refs.videos.append({"asset": a["id"], "soundtrack": bool(r.get("soundtrack")), "ref": r["id"]})
        elif a["kind"] == "audio" and not any(x["asset"] == a["id"] for x in refs.audios):
            refs.audios.append({"asset": a["id"], "ref": r["id"], "cast": None})
    refs.guided = guided  # added 2026-11-03 v0.6.0
    refs.number()

    # added 2026-11-02 v0.2.0: reference pictures and content videos become subjects (ref-en.txt 2.1-2.3).
    # Keyframe-category pictures stay standalone <Picture N> composition anchors; camera and
    # edit-source videos stay <Video N> structure references.
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
        a = assets[v["asset"]]
        # [OLD 2026-11-03 v0.5.1->v0.6.0] if a.get("category") not in SUBJECT_VIDEO_CATEGORIES or a["id"] in refs.subject_of_asset:  (guide clips are no subjects)
        if v.get("guide") or a.get("category") not in SUBJECT_VIDEO_CATEGORIES or a["id"] in refs.subject_of_asset:
            continue
        refs.subjects.append({"cast": None, "ref": v["ref"], "asset": a["id"], "number": len(refs.subjects) + 1,
                              "outfit": None, "pictures": [], "videos": [k]})
        refs.subject_of_asset[a["id"]] = refs.subjects[-1]["number"]

    # guides
    i = pass_["index"]
    # [OLD 2026-11-03 v0.5.1->v0.6.0] the re-anchor rule was worked out here; the planner trims by model.effective_start, so both use it now
    # depth = continuation_depth(p).get(scene["id"], 0)
    # reanchor = depth > int(p["global"]["continuity"]["reanchor_after"])
    # if i == 1 and scene_index > 0:
    #     mode = scene["start"]["mode"]
    #     if mode == "tail" and pass_["overlap_frames"] and not reanchor:
    #         refs.guides.append({"type": "clip", "source": "prev_scene_tail", "frames": pass_["overlap_frames"],
    #                             "frame_idx": 0, "audio": True})
    #     elif mode in ("last_frame", "tail"):
    #         refs.guides.append({"type": "image", "source": "prev_scene_last", "frame_idx": 0})
    # [/OLD]
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


# [OLD 2026-11-03 v0.5.1->v0.6.0] def task_tags(p, scene, refs):
#     assets = project_index(p)["assets"]
# [/OLD]
def task_tags(p, scene, refs, ctx=None):  # ctx: added 2026-11-03 v0.6.0
    assets = (ctx["index"] if ctx is not None else project_index(p))["assets"]
    tags = set()
    if refs.file_count:
        tags.add("reference generation")
    if any(g["type"] == "image" for g in refs.guides):
        tags.add("keyframe completion")
    # [OLD 2026-11-03 v0.5.1->v0.6.0] a clip from an asset counted as keyframe completion, which ref-en.txt keeps for pictures
    # if any(g["type"] == "clip" and g["source"] != "asset" for g in refs.guides):
    #     tags.add("video continuation")
    # if any(g["type"] == "clip" and g["source"] == "asset" for g in refs.guides):
    #     tags.add("keyframe completion")
    # [/OLD]
    if any(g["type"] == "clip" for g in refs.guides):
        tags.add("video continuation")  # the target continues from (or passes through) existing footage
    ref_by_id = {r["id"]: r for r in scene["refs"]}
    for v in refs.videos:
        a = assets[v["asset"]]
        if a.get("category") == "edit_source":
            tags.add("video editing")
        if v["soundtrack"]:
            ret = _retention(ref_by_id.get(v["ref"], {}), a) if v["ref"] else "reference"
            tags.add("audio reuse" if ret in ("fully_copy", "partially_copy") else "audio reference")
    for au in refs.audios:
        if au.get("song"):  # added 2026-11-03 v0.5.0
            tags.add("audio reuse" if au["song"]["marker"] in ("fully_copy", "partially_copy") else "audio reference")
            continue
        a = assets[au["asset"]]
        ret = _retention(ref_by_id.get(au["ref"], {}), a) if au["ref"] else "reference"
        tags.add("audio reuse" if ret in ("fully_copy", "partially_copy") else "audio reference")
    return [t for t in spec.TASK_TAG_ORDER if t in tags]


def mentioned_codes(text):
    # [OLD 2026-11-03 v0.5.1->v0.6.0] return {(m.group(2) or "").upper() for m in TAG_RE.finditer(text or "") if m.group(2)}
    out = set()
    for m in tag_re().finditer(text or ""):
        if m.group(2):
            out.add(m.group(2).upper())
            base = POSSESSIVE.match(m.group(2))
            if base:
                out.add(base.group(1).upper())
    return out


# added 2026-11-03 v0.6.0: how each tag reads in one pass, and what is said about tags that don't resolve
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
    """added 2026-11-03 v0.6.0 review: how asset `a` belongs to the scene other than as one of its references:
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
    """added 2026-11-03 v0.6.0 review: a cast voice not sent with this pass, in words: its description, else
    "<name>'s voice"."""
    desc = (a.get("description") or "").strip().rstrip(".")
    if desc:
        return _asset_words(a)
    return "{}'s voice".format(c.get("name") or "the character")


def resolve_tag(name, braced, p, refs, ctx, scene=None):
    """(text, level, message) for one tag in this pass: level None when it resolves to a label; otherwise the
    words written instead and why. text None means the tag stays as typed."""
    idx = ctx["index"]
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
        # added 2026-11-03 v0.6.0 review: a cast voice goes only to the passes where that character speaks, so @A1
        # (Mara's voice) in another pass was an error that blocked the render. An asset of the scene (a cast
        # member's voice, anchor or outfit asset, a soundtrack file) not sent with this pass is written in words.
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


# [OLD 2026-11-03 v0.5.1->v0.6.0] every tag that did not resolve was an error, @soundtrack in a pass without the song too
# def substitute(text, p, refs, unknown):
#     idx = project_index(p)
#     subject_of_cast = {s["cast"]: s["number"] for s in refs.subjects}
#
#     def repl(m):
#         name = m.group(1) or m.group(2)
#         key = name.upper()
#         a = idx["codes"].get(key) if m.group(2) else None
#         if a:
#             # added 2026-11-02 v0.2.0: assets that became subjects resolve to their <Subject N>
#             if a["id"] in refs.subject_of_asset:
#                 return "<Subject {}>".format(refs.subject_of_asset[a["id"]])
#             if a["kind"] == "image" and a["id"] in refs.picture_of_asset:
#                 return "<Picture {}>".format(refs.picture_of_asset[a["id"]])
#             if a["kind"] == "video" and a["id"] in refs.video_of_asset:
#                 return "<Video {}>".format(refs.video_of_asset[a["id"]])
#             if a["kind"] == "audio" and a["id"] in refs.audio_of_asset:
#                 return "<Audio {}>".format(refs.audio_of_asset[a["id"]])
#             unknown.append(m.group(0))
#             return m.group(0)
#         if name.lower() == "tail":
#             return "the end of the previous shot"
#         if name.lower() in ("soundtrack", "song") and refs.song_number:  # added 2026-11-03 v0.5.0
#             return "<Audio {}>".format(refs.song_number)
#         c = idx["cast_by_name"].get(name.strip().lower())
#         if c and c["id"] in subject_of_cast:
#             return "<Subject {}>".format(subject_of_cast[c["id"]])
#         unknown.append(m.group(0))
#         return m.group(0)
#
#     return TAG_RE.sub(repl, text or "")
# [/OLD]
def substitute(text, p, refs, unknown, ctx=None, scene=None, issues=None):
    """Tags -> this pass's labels; "@@" -> "@". unknown gets the tags that are errors; issues (optional) gets
    {"level", "tag", "message"} for every tag that does not resolve to a label. (Rewritten 2026-11-03 v0.6.0.)"""
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


# [OLD 2026-11-02 v0.1.0->v0.2.0] replaced by the Ref2VA-guide writers below: the old output used
# "Subjects:"/"Retention:"/"Shots:" headings, [Shot1] without a space, project-wide speaker IDs and a
# "Single continuous take" line, none of which match MiniMax's ref-en.txt.
# def _subject_lines(p, refs):
#     cast = project_index(p)["cast"]
#     lines = []
#     for s in refs.subjects:
#         c = cast[s["cast"]]
#         pics = ", ".join("<Picture {}>".format(k) for k in s["pictures"])
#         head = "<Subject {}>".format(s["number"])
#         bits = [c["name"]]
#         if c["description"]:
#             bits.append(c["description"].rstrip("."))
#         if s["outfit"] and s["outfit"]["name"]:
#             bits.append("wearing " + s["outfit"]["name"])
#         src = (" is shown in " + pics) if pics else ""
#         lines.append("{}{}: {}.".format(head, src, ", ".join(bits)))
#     return lines
#
#
# def _retention_lines(p, scene, refs, pass_):
#     idx = project_index(p)
#     assets, cast = idx["assets"], idx["cast"]
#     ref_by_id = {r["id"]: r for r in scene["refs"]}
#     shots = pass_["shots"]
#     span = "Shots 1-{}".format(len(shots)) if len(shots) > 1 else "Shot 1"
#     lines = []
#     for s in refs.subjects:
#         c = cast[s["cast"]]
#         if c["kind"] != "character" and not s["pictures"]:
#             continue
#         o = s["outfit"]
#         ret = (o or {}).get("retention") or "fully_preserved"
#         keep = ", ".join((o or {}).get("keep") or ["identity", "appearance"])
#         lines.append("<Subject {}> ({}): {} - {}".format(s["number"], span, ret, keep))
#     for k, img in enumerate(refs.images, 1):
#         if img["cast"] or not img["ref"]:
#             continue
#         a = assets[img["assets"][0]]
#         r = ref_by_id.get(img["ref"], {})
#         keep = ", ".join(_keep(r, a)) or a.get("category") or "overall look"
#         lines.append("<Picture {}>: {} - {}".format(k, _retention(r, a), keep))
#     for k, v in enumerate(refs.videos, 1):
#         a = assets[v["asset"]]
#         r = ref_by_id.get(v["ref"], {})
#         keep = ", ".join(_keep(r, a)) or a.get("category") or "motion"
#         lines.append("<Video {}>: {} - {}".format(k, _retention(r, a), keep))
#         if v["soundtrack"]:
#             lines.append("<Audio {}>: reference - soundtrack of <Video {}>".format(v["audio_number"], k))
#     for au in refs.audios:
#         a = assets[au["asset"]]
#         n = refs.audio_of_asset[au["asset"]]
#         if au["cast"]:
#             c = cast[au["cast"]]
#             subj = next((s["number"] for s in refs.subjects if s["cast"] == c["id"]), None)
#             lines.append("<Audio {}>: reference - voice timbre and delivery of <Subject {}>".format(n, subj))
#         else:
#             r = ref_by_id.get(au["ref"], {})
#             keep = ", ".join(_keep(r, a)) or a.get("category") or "sound"
#             lines.append("<Audio {}>: {} - {}".format(n, _retention(r, a), keep))
#     return lines
#
#
# def _shot_lines(p, scene, refs, pass_):
#     cast = project_index(p)["cast"]
#     subject_of_cast = {s["cast"]: s["number"] for s in refs.subjects}
#     shots = pass_["shots"]
#     lines = []
#     if not shots:
#         shots = [{"number": 1, "continuing": False, "t": 0.0, "camera": "", "text": ""}]
#     for n, sh in enumerate(shots, 1):
#         nxt = shots[n]["t"] if n < len(shots) else None
#         head = "[Shot{}]".format(n)
#         if n > 1:
#             head += " At {}, cut to".format(spec.fmt_time(sh["t"]))
#         elif sh["continuing"]:
#             head += " Continuing the same shot,"
#         body = sh["camera"].strip()
#         if sh["text"].strip():
#             body = (body + ": " if body else "") + sh["text"].strip()
#         if body and body[-1] not in ".!?":
#             body += "."
#         parts = [head + (" " + body if body else "")]
#         for d in pass_["dialogue"]:
#             if d["t"] < sh["t"] or (nxt is not None and d["t"] >= nxt):
#                 continue
#             c = cast.get(d["speaker"])
#             who = "<Subject {}> ({})".format(subject_of_cast[c["id"]], c["speaker"] or "S?") if c and c["id"] in subject_of_cast else "A voice off-screen"
#             verb = d["delivery"].strip() or "says"
#             parts.append("At {}, {} {} <d>[{}] {}</d>.".format(spec.fmt_time(d["t"]), who, verb,
#                                                              d["language"] or "English", d["text"].strip()))
#         lines.append(" ".join(parts))
#     if len(shots) == 1:
#         lines.append("Single continuous take, no cuts.")
#     return lines
# [/OLD]


# ---- Ref2VA writers (added 2026-11-02 v0.2.0) --------------------------------------------

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


# added 2026-11-03 v0.4.1 (see LABEL_START)
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


# [OLD 2026-11-03 v0.5.1->v0.6.0] def _appears(p, refs, pass_, subj):
def _appears(p, refs, pass_, subj, ctx=None):  # ctx: added 2026-11-03 v0.6.0
    """'appears in [Shot 1], [Shot 3]' from @mentions in shot text and spoken lines."""
    shots = pass_["shots"] or [{"t": 0.0, "camera": "", "text": ""}]
    # [OLD 2026-11-03 v0.5.1->v0.6.0] idx = project_index(p)
    idx = _index(p, ctx)
    hits = set()
    # [OLD 2026-11-03 v0.5.1->v0.6.0] names compared by lower() only, codes without the possessive form
    # if subj["cast"]:
    #     name = idx["cast"][subj["cast"]]["name"].strip().lower()
    #     match = lambda m: (m.group(1) or m.group(2) or "").strip().lower() == name
    # else:
    #     code = idx["assets"][subj["asset"]]["code"].upper()
    #     match = lambda m: (m.group(2) or "").upper() == code
    # [/OLD]
    if subj["cast"]:
        name = name_key(idx["cast"][subj["cast"]]["name"])

        def match(m):
            said = m.group(1) if m.group(1) is not None else m.group(2)
            base = POSSESSIVE.match(said) if m.group(2) else None
            return name_key(said) == name or bool(base and name_key(base.group(1)) == name)
    else:
        code = idx["assets"][subj["asset"]]["code"].upper()

        def match(m):
            base = POSSESSIVE.match(m.group(2) or "")
            return (m.group(2) or "").upper() == code or bool(base and base.group(1).upper() == code)
    for i, sh in enumerate(shots, 1):
        # [OLD 2026-11-03 v0.5.1->v0.6.0] if any(match(m) for m in TAG_RE.finditer("{} {}".format(sh.get("camera", ""), sh.get("text", "")))):
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


# added 2026-11-03 v0.6.0: a guide clip named in the text is sent as <Video k>; this says where it sits in the pass
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


# [OLD 2026-11-03 v0.5.1->v0.6.0] def subject_definitions(p, scene, refs, pass_, ids):
#     idx = project_index(p)
# [/OLD]
def subject_definitions(p, scene, refs, pass_, ids, ctx=None):  # ctx: added 2026-11-03 v0.6.0
    idx = _index(p, ctx)
    assets, cast = idx["assets"], idx["cast"]
    lines = []
    for s in refs.subjects:
        head = "<Subject {}>".format(s["number"])
        src = _labels("Picture", s["pictures"]) or _labels("Video", s["videos"])
        if s["cast"]:
            c = cast[s["cast"]]
            # [OLD 2026-11-02 v0.3.3->v0.3.4] anchor pictures' descriptions were never used
            # bits = [c["name"]] + ([c["description"].strip().rstrip(".")] if c["description"].strip() else [])
            desc, _ = cast_description(c, assets)
            bits = [c["name"]] + ([desc] if desc else [])
            text = "{} is {}".format(head, ", ".join(bits))
            if src:
                text += ", shown in " + src
            o = s["outfit"]
            if o and o.get("name") and o["name"].strip().lower() != "default":
                text += ", wearing " + o["name"].strip()
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
        a = assets[img["assets"][0]]
        desc = (a.get("description") or "").strip().rstrip(".")
        role, _ = _guide_of_picture(scene, refs, pass_, k)
        # [OLD 2026-11-03 v0.5.1->v0.6.0] what = role or ("a composition reference" if a.get("category") == "keyframe" else "a reference image")  ("is first frame of")
        what = ("the " + role) if role else ("a composition reference" if a.get("category") == "keyframe" else "a reference image")
        lines.append("<Picture {}> is {}{}.".format(k, what, ", showing " + desc if desc else ""))
    for k, v in enumerate(refs.videos, 1):
        if any(k in s["videos"] for s in refs.subjects):
            continue
        a = assets[v["asset"]]
        desc = (a.get("description") or "").strip().rstrip(".")
        if v.get("guide"):  # added 2026-11-03 v0.6.0
            lines.append("<Video {}> is {}{}.".format(k, _guide_of_clip(pass_, v["ref"])[0],
                                                      ", showing " + desc if desc else ""))
        elif a.get("category") == "edit_source":  # [OLD 2026-11-03 v0.5.1->v0.6.0] if a.get("category") == "edit_source":
            lines.append("<Video {}> is the source video for the target video edit.".format(k))
        else:
            lines.append("<Video {}> is the camera-movement and pacing reference{}.".format(k, ", showing " + desc if desc else ""))
    sub_of_cast = {s["cast"]: s["number"] for s in refs.subjects if s["cast"]}
    for v_k, v in enumerate(refs.videos, 1):
        if v["soundtrack"]:
            lines.append("<Audio {}> is the synchronized audio track of <Video {}>.".format(v["audio_number"], v_k))
    for au in refs.audios:
        if au.get("song"):  # added 2026-11-03 v0.5.0
            lines.append("<Audio {}> is the song this part of the film is cut to; it plays unchanged as the final "
                         "soundtrack.".format(refs.song_number))
            continue
        a = assets[au["asset"]]
        n = refs.audio_of_asset[au["asset"]]
        if au["cast"]:
            spk = " ({})".format(ids[au["cast"]]) if au["cast"] in ids else ""
            lines.append("<Audio {}> is the voice-timbre reference for <Subject {}>{}.".format(n, sub_of_cast.get(au["cast"], "?"), spk))
        else:
            desc = (a.get("description") or "").strip().rstrip(".")
            lines.append("<Audio {}> is {}.".format(n, desc or AUDIO_PHRASE.get(a.get("category"), "the audio reference")))
    return lines


# [OLD 2026-11-03 v0.5.1->v0.6.0] def retention_analysis(p, scene, refs, pass_):
#     idx = project_index(p)
# [/OLD]
def retention_analysis(p, scene, refs, pass_, ctx=None):  # ctx: added 2026-11-03 v0.6.0
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
        # [OLD 2026-11-03 v0.5.1->v0.6.0] lines.append("<Subject {}> ({}): {} - {}.".format(s["number"], _appears(p, refs, pass_, s), ret, _keep_phrase(keep, ret)))
        lines.append("<Subject {}> ({}): {} - {}.".format(s["number"], _appears(p, refs, pass_, s, ctx), ret,
                                                          _keep_phrase(keep, ret)))
    for k, img in enumerate(refs.images, 1):
        if img["cast"] or any(k in s["pictures"] for s in refs.subjects):
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
        a = assets[v["asset"]]
        r = ref_by_id.get(v["ref"], {})
        if v.get("guide"):  # added 2026-11-03 v0.6.0: its frames are placed in the target as they are
            lines.append("<Video {}> ({}): fully_preserved - its frames are kept as they are.".format(
                k, _guide_of_clip(pass_, v["ref"])[1]))
            continue
        ret = _retention(r, a)
        what = "source video" if a.get("category") == "edit_source" else "camera movement and pacing"
        keep = _keep(r, a) or DEFAULT_KEEP.get(a.get("category") or "camera", DEFAULT_KEEP["camera"])
        lines.append("<Video {}> ({}): {} - {}.".format(k, what, ret, _keep_phrase(keep, ret)))
    for k, v in enumerate(refs.videos, 1):
        if v["soundtrack"]:
            r = ref_by_id.get(v["ref"], {})
            ret = r.get("soundtrack_retention") or "reference"
            lines.append("<Audio {}>: {} - {}.".format(v["audio_number"], ret, _keep_phrase(["the soundtrack of <Video {}>".format(k)], ret)))
    sub_of_cast = {s["cast"]: s["number"] for s in refs.subjects if s["cast"]}
    for au in refs.audios:
        if au.get("song"):  # added 2026-11-03 v0.5.0
            ret = au["song"]["marker"]
            lines.append("<Audio {}>: {} - {}; singing lip movements, gestures, motion and cuts follow its vocals "
                         "and beat.".format(refs.song_number, ret, _keep_phrase(["its vocals, rhythm and beat"], ret)))
            continue
        a = assets[au["asset"]]
        n = refs.audio_of_asset[au["asset"]]
        if au["cast"]:
            lines.append("<Audio {}>: reference - the voice timbre and delivery of <Subject {}> follow <Audio {}> "
                         "without copying the original signal.".format(n, sub_of_cast.get(au["cast"], "?"), n))
        else:
            r = ref_by_id.get(au["ref"], {})
            ret = _retention(r, a)
            keep = _keep(r, a) or DEFAULT_KEEP.get(a.get("category"), ["sound"])
            lines.append("<Audio {}>: {} - {}.".format(n, ret, _keep_phrase(keep, ret)))
    return lines


# [OLD 2026-11-03 v0.5.1->v0.6.0] def _dialogue_sentence(p, refs, d, ids):
#     cast = project_index(p)["cast"]
# [/OLD]
def _dialogue_sentence(p, refs, d, ids, ctx=None):  # ctx: added 2026-11-03 v0.6.0
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
    if "voiceover" in verb.lower().replace("-", "").replace(" ", ""):
        return "{} says in an off-screen voiceover: <d>[{}] {}</d> while their lips remain completely closed.".format(who, lang, line)
    return "{} {}, <d>[{}] {}</d>".format(who, verb, lang, line)


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


# [OLD 2026-11-03 v0.5.1->v0.6.0] def shot_descriptions(p, scene, refs, pass_, ids, unknown):
def shot_descriptions(p, scene, refs, pass_, ids, unknown, ctx=None):  # ctx: added 2026-11-03 v0.6.0
    """[Shot 1] ... / [Shot N] At MM:SS.mmm, the shot cuts to ... with the lines spoken in each shot."""
    # [OLD 2026-11-03 v0.4.0->v0.4.1] the lines were built here; the body moved to shot_parts(), which keeps each
    # shot's spoken lines apart so a written [Shot N] can keep them
    # [OLD 2026-11-03 v0.5.1->v0.6.0] return [" ".join([x["text"]] + x["dialogue"]) for x in shot_parts(p, scene, refs, pass_, ids, unknown)]
    return [" ".join([x["text"]] + x["dialogue"]) for x in shot_parts(p, scene, refs, pass_, ids, unknown, ctx=ctx)]


# added 2026-11-03 v0.4.1: one entry per shot: {label, text (without dialogue), dialogue: [sentences]}
# [OLD 2026-11-03 v0.5.1->v0.6.0] def shot_parts(p, scene, refs, pass_, ids, unknown):
def shot_parts(p, scene, refs, pass_, ids, unknown, ctx=None, issues=None):  # ctx, issues: added 2026-11-03 v0.6.0
    shots = pass_["shots"] or [{"number": 1, "continuing": False, "t": 0.0, "camera": "", "text": ""}]
    # [OLD 2026-11-03 v0.5.1->v0.6.0] sub = lambda t: substitute(t, p, refs, unknown).strip()
    sub = lambda t: substitute(t, p, refs, unknown, ctx=ctx, scene=scene, issues=issues).strip()
    out = []
    for n, sh in enumerate(shots, 1):
        nxt = shots[n]["t"] if n < len(shots) else None
        cam, body = sub(sh.get("camera", "")), sub(sh.get("text", ""))
        parts = ["[Shot {}]".format(n)]
        short = _camera_phrase(cam)
        if n == 1:
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
        spoken = []
        for d in pass_["dialogue"]:
            if float(d["t"]) < float(sh["t"]) - 1e-6 and n > 1:
                continue
            if nxt is not None and float(d["t"]) >= float(nxt) - 1e-6:
                continue
            # [OLD 2026-11-03 v0.4.0->v0.4.1] parts.append(_dialogue_sentence(p, refs, d, ids))
            # [OLD 2026-11-03 v0.5.1->v0.6.0] spoken.append(_dialogue_sentence(p, refs, d, ids))
            spoken.append(_dialogue_sentence(p, refs, d, ids, ctx))
        # [OLD 2026-11-03 v0.4.0->v0.4.1] out.append(" ".join(parts))
        out.append({"label": "[Shot {}]".format(n), "text": " ".join(parts), "dialogue": spoken})
    return out


def _keep_dialogue(parts):
    """fix() for shot lines: a written [Shot N] that left out a spoken line gets it back (word for word)."""
    spoken = {x["label"]: x["dialogue"] for x in parts}

    def fix(label, chunk, line):
        missing = [d for d in spoken.get(label, []) if line is not None and
                   not any(span in chunk for span in DIALOGUE_SPAN.findall(d))]
        return " ".join([chunk] + missing)
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
    if refs.song_number:  # added 2026-11-03 v0.5.0
        text += " The picture is cut to <Audio {}>: mouths, movement and cuts follow its vocals and beat.".format(
            refs.song_number)
    return text


# ---- written shot lines and pass prompts (added 2026-11-03 v0.6.0) ------------------------------------------------

def _rebase_clock(text, offset):
    """MM:SS.mmm times written in scene time -> this pass's time (a pass starts `offset` seconds into the scene)."""
    if abs(offset) < 1e-9:
        return text
    return CLOCK.sub(lambda m: spec.fmt_time(max(0.0, int(m.group(1)) * 60 + float(m.group(2)) - offset)), text)


# added 2026-11-03 v0.6.0 review: "At MM:SS.mmm," opening a sentence: a time on the shot's timeline
CUE_TIME = re.compile(r"(^\s*|[.!?]\s+)(At\s+)(\d{1,2}):(\d{2}(?:\.\d{1,3})?)(?=\s*,)")


def _rebase_shot(text, offset, limit=None):
    """added 2026-11-03 v0.6.0 review: the times of a written shot line that are on the scene's timeline -> this
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


DIALOGUE_SPAN_SPLIT = re.compile(r"(<d>.*?</d>)", re.S)  # added 2026-11-03 v0.6.0 review


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


def _drop_cut_lead(body):
    """'At 00:14.375, the shot cuts to a medium shot: ...' -> 'A medium shot: ...' (the first shot has no cut)."""
    m = CUT_LEAD.match(body)
    if not m:
        return body
    rest = body[m.end():].strip()
    return rest[:1].upper() + rest[1:]


def written_shots(scene, plan, pass_, text):
    """The part of a written detailed_description that belongs to this pass. Written [Shot N] use the scene's shot
    numbers; each pass numbers its own shots from 1, so:
    - text before [Shot 1] (style sentences) goes to every pass;
    - [Shot N] goes to the pass(es) holding scene shot N, renumbered; its timeline times move to pass time (added
      2026-11-03 v0.6.0 review: the cut lead and "At MM:SS," cues only, see _rebase_shot); the first
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
        # [OLD 2026-11-03 v0.6.0 review] every MM:SS in the line moved, spoken times in <d> too ("at 11:45" -> "at 11:30.625")
        # body = _rebase_clock(chunk[len(label):].strip(), offset)
        # [/OLD]
        # added 2026-11-03 v0.6.0 review: only the cut time and "At MM:SS," timing cues inside the scene
        body = _rebase_shot(chunk[len(label):].strip(), offset, scene.get("duration"))
        if k in local:
            n, sh = local[k]
            if n == 1:
                body = _drop_cut_lead(body)
                if sh.get("continuing") and pass_["index"] > 1 and "continues" not in body.lower():
                    body = (CONTINUES + " " + body).strip()
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


# [OLD 2026-11-03 v0.5.1->v0.6.0] tags were added in front of any prompt that did not start with "[" (twice for a pass edited by hand,
# none for a raw prompt starting with [Shot 1]); written [Shot N] lines went to every pass; @soundtrack without the song was an error
# def build_pass(p, scene, scene_index, plan, pass_):
#     """Return the prompt and reference plan for one pass."""
#     pr = scene["prompt"]
#     override = (pr.get("pass_prompts") or {}).get(str(pass_["index"]), "")
#     sources = [override] if override.strip() else (
#         [pr["raw"]] if pr["mode"] == "raw" else list(pr["sections"].values()))
#     mentioned = set()
#     for t in sources:
#         mentioned |= mentioned_codes(t)
#     refs = collect_refs(p, scene, scene_index, pass_, len(plan["passes"]), mentioned)
#     tags = task_tags(p, scene, refs)
#     tag_line = "[{}]".format(" + ".join(tags)) if tags else ""
#     unknown = []
#
#     if override.strip() or pr["mode"] == "raw":
#         body = substitute(override if override.strip() else pr["raw"], p, refs, unknown).strip()
#         text = body if body.startswith("[") or not tag_line else (tag_line + " " + body).strip()
#     else:
# [/OLD]
def build_pass(p, scene, scene_index, plan, pass_, ctx=None):
    """Return the prompt and reference plan for one pass. ctx: prepare(p), shared by every scene and pass of the
    same project state (added 2026-11-03 v0.6.0)."""
    ctx = _ctx(p, ctx)
    pr = scene["prompt"]
    override = (pr.get("pass_prompts") or {}).get(str(pass_["index"]), "")
    override = override if isinstance(override, str) else ""
    shots_written = None
    if override.strip():
        sources = [override]
    elif pr["mode"] == "raw":
        sources = [pr["raw"]]
    else:
        # only the written shot lines of this pass, and its timeline shots, can name a guide picture or clip
        shots_written = written_shots(scene, plan, pass_, pr["sections"]["detailed_description"])
        sources = [v for k, v in pr["sections"].items() if k != "detailed_description"] + [shots_written["text"]]
        if pr["auto"].get("shots"):
            sources += ["{} {}".format(sh.get("camera", ""), sh.get("text", "")) for sh in pass_["shots"]]
    mentioned = set()
    for t in sources:
        mentioned |= mentioned_codes(t)
    refs = collect_refs(p, scene, scene_index, pass_, len(plan["passes"]), mentioned, ctx=ctx)
    tags = task_tags(p, scene, refs, ctx=ctx)
    tag_line = "[{}]".format(" + ".join(tags)) if tags else ""
    unknown, issues = [], []

    def sub(t):
        return substitute(t, p, refs, unknown, ctx=ctx, scene=scene, issues=issues)

    if override.strip() or pr["mode"] == "raw":
        body = sub(override if override.strip() else pr["raw"]).strip()
        text = place_task_tags(body, tag_line)
    else:
        # [OLD 2026-11-02 v0.1.0->v0.2.0] headings did not follow H3's Ref2VA guide (see writers above)
        # sec = {k: substitute(v, p, refs, unknown).strip() for k, v in pr["sections"].items()}
        # auto = pr["auto"]
        # blocks = []
        # head = " ".join(x for x in (tag_line, sec["summary"]) if x)
        # if head:
        #     blocks.append(head)
        # subj = (_subject_lines(p, refs) if auto.get("subjects") else []) + ([sec["subject_definitions"]] if sec["subject_definitions"] else [])
        # if subj:
        #     blocks.append("Subjects:\n" + "\n".join(subj))
        # ret = (_retention_lines(p, scene, refs, pass_) if auto.get("retention") else []) + ([sec["retention_analysis"]] if sec["retention_analysis"] else [])
        # if ret:
        #     blocks.append("Retention:\n" + "\n".join(ret))
        # shots = (_shot_lines(p, scene, refs, pass_) if auto.get("shots") else []) + ([sec["detailed_description"]] if sec["detailed_description"] else [])
        # if shots:
        #     blocks.append("Shots:\n" + "\n".join(shots))
        # if sec["overall_soundscape"]:
        #     blocks.append("Soundscape: " + sec["overall_soundscape"])
        # if sec["non_diegetic_music"]:
        #     blocks.append("Music: " + sec["non_diegetic_music"])
        # text = "\n\n".join(blocks)
        # [/OLD]
        # added 2026-11-02 v0.2.0: the six labelled sections of ref-en.txt, always in order.
        # [OLD 2026-11-03 v0.5.1->v0.6.0] sec = {k: substitute(v, p, refs, unknown).strip() for k, v in pr["sections"].items()}
        sec = {k: sub(v).strip() for k, v in pr["sections"].items() if k != "detailed_description"}
        sec["detailed_description"] = sub(shots_written["text"]).strip()  # added 2026-11-03 v0.6.0: this pass's lines
        for k in shots_written["extra"]:
            issues.append({"level": "info", "tag": "", "message": "a written [Shot {}] has no shot on the timeline "
                           "(the scene has {}), so it follows the last shot".format(k, len(scene["shots"]))})
        if shots_written["unplaced"]:
            issues.append({"level": "warn", "tag": "", "message": "the written [Shot N] lines go to every pass, because "
                           "the scene has no shots on the timeline; add the shots there so each pass gets its own"})
        auto = pr["auto"]
        ids = speaker_ids(pass_)
        # [OLD 2026-11-03 v0.4.0->v0.4.1] automatic lines and written sections were simply stacked, so a section the rewriter also wrote
        # (or a summary that already started with the task tags) appeared twice
        # subj = (subject_definitions(p, scene, refs, pass_, ids) if auto.get("subjects") else []) + \
        #     ([sec["subject_definitions"]] if sec["subject_definitions"] else [])
        # summary = sec["summary"] or (_auto_summary(refs, pass_) if auto.get("subjects") else "")
        # summary = " ".join(x for x in (tag_line, summary) if x)
        # ret = (retention_analysis(p, scene, refs, pass_) if auto.get("retention") else []) + \
        #     ([sec["retention_analysis"]] if sec["retention_analysis"] else [])
        # desc = ([sec["detailed_description"]] if sec["detailed_description"] else []) + \
        #     (shot_descriptions(p, scene, refs, pass_, ids, unknown) if auto.get("shots") else [])
        # [/OLD]
        # added 2026-11-03 v0.4.1: written lines replace the automatic line with the same label
        labelled = lambda lines, pattern: [((pattern.match(x).group("label") if pattern.match(x) else ""), x) for x in lines]
        # [OLD 2026-11-03 v0.5.1->v0.6.0] subj = _merge(labelled(subject_definitions(p, scene, refs, pass_, ids), LABEL_START) if auto.get("subjects") else [],
        subj = _merge(labelled(subject_definitions(p, scene, refs, pass_, ids, ctx), LABEL_START) if auto.get("subjects") else [],
                      sec["subject_definitions"], LABEL_START, _with_sources(refs))
        # [OLD 2026-11-03 v0.5.1->v0.6.0] written tags were only stripped when written in lower case
        # written = sec["summary"]
        # lead = LEADING_TAGS.match(written)
        # if lead and all(t.strip() in spec.TASK_TAG_ORDER for t in lead.group(1).split("+")):
        #     written = written[lead.end():]  # the task tags are always added below
        # [/OLD]
        written = _strip_task_tags(sec["summary"]).strip()  # the task tags are always added below
        summary = written or (_auto_summary(refs, pass_) if auto.get("subjects") else "")
        summary = " ".join(x for x in (tag_line, summary) if x)
        # [OLD 2026-11-03 v0.5.1->v0.6.0] ret = _merge(labelled(retention_analysis(p, scene, refs, pass_), LABEL_START) if auto.get("retention") else [],
        ret = _merge(labelled(retention_analysis(p, scene, refs, pass_, ctx), LABEL_START) if auto.get("retention") else [],
                     sec["retention_analysis"], LABEL_START)
        # [OLD 2026-11-03 v0.5.1->v0.6.0] parts = shot_parts(p, scene, refs, pass_, ids, unknown) if auto.get("shots") else []
        parts = shot_parts(p, scene, refs, pass_, ids, unknown, ctx=ctx, issues=issues) if auto.get("shots") else []
        desc = _merge([(x["label"], " ".join([x["text"]] + x["dialogue"])) for x in parts],
                      sec["detailed_description"], SHOT_START, _keep_dialogue(parts), pre_first=True)
        body = {
            "subject_definitions": "\n".join(subj), "summary": summary, "retention_analysis": "\n".join(ret),
            "detailed_description": "\n".join(desc), "overall_soundscape": sec["overall_soundscape"],
            "non_diegetic_music": sec["non_diegetic_music"],
        }
        text = "\n\n".join("{}:\n{}".format(k, body[k].strip() or "N/A") for k in REF2VA_SECTIONS)

    tag_map = {}
    idx = ctx["index"]  # [OLD 2026-11-03 v0.5.1->v0.6.0] idx = project_index(p)
    for aid, k in refs.picture_of_asset.items():
        tag_map["@" + idx["assets"][aid]["code"]] = "<Picture {}>".format(k)
    for aid, k in refs.video_of_asset.items():
        tag_map["@" + idx["assets"][aid]["code"]] = "<Video {}>".format(k)
    for aid, k in refs.audio_of_asset.items():
        tag_map["@" + idx["assets"][aid]["code"]] = "<Audio {}>".format(k)
    if refs.song_number:  # added 2026-11-03 v0.5.0
        tag_map["@soundtrack"] = "<Audio {}>".format(refs.song_number)
    # [OLD 2026-11-02 v0.1.0->v0.2.0] reference subjects have no cast entry
    # for s in refs.subjects:
    #     tag_map["@" + idx["cast"][s["cast"]]["name"]] = "<Subject {}>".format(s["number"])
    # [/OLD]
    for s in refs.subjects:
        if s["cast"]:
            tag_map["@" + idx["cast"][s["cast"]]["name"]] = "<Subject {}>".format(s["number"])
        else:
            tag_map["@" + idx["assets"][s["asset"]]["code"]] = "<Subject {}>".format(s["number"])

    # [OLD 2026-11-03 v0.5.1->v0.6.0] return {"prompt": text, "tags": tags, "tag_map": tag_map, "unknown": sorted(set(unknown)),
    # issues (added 2026-11-03 v0.6.0): [{"level": "error"|"warn"|"info", "tag", "message"}] about tags that did not
    # resolve to a label and about written shot lines; validate.lint_project reports them
    return {"prompt": text, "tags": tags, "tag_map": tag_map, "unknown": sorted(set(unknown)), "issues": issues,
            "images": refs.images, "videos": refs.videos, "audios": refs.audios,
            "guides": refs.guides, "subjects": refs.subjects}


# added 2026-11-03 v0.4.1: clean up what the LLM rewriter returns before it is offered as a proposal.
SECTION_LABEL = re.compile(r"^[ \t]*(subject_definitions|summary|retention_analysis|detailed_description|"
                           r"overall_soundscape|non_diegetic_music)[ \t]*:[ \t]*", re.M)


def _token(key):
    """'@Old Keeper' -> '@{Old Keeper}' (tag_map keys hold the plain name)."""
    # [OLD 2026-11-03 v0.5.1->v0.6.0] name = key[1:]
    # return "@{" + name + "}" if re.search(r"[^\w-]", name) else key
    # [/OLD]
    return tag_token(key[1:])  # same name rule as the tags themselves ("@O'Brien" stays plain)


# added 2026-11-03 v0.6.0: LLM answers sometimes hold a list or an object where text belongs
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


def tidy_rewrite(proposal, before, auto, tag_map=None):
    """proposal / before: the six sections. auto: the scene's automatic parts. tag_map: pass 1's "@P1" -> "<Picture 1>".

    - a whole six-section prompt returned inside one key is split back into its sections;
    - a value that starts with its own label ("summary: ...") loses the label;
    - <Subject N>, <Picture N>, <Video N>, <Audio N> are turned back into the @ tokens they stand for, so the text
      still works when a pass numbers references differently;
    - parts the editor writes automatically are not taken from the LLM: subject definitions and retention lines
      keep their previous text, and detailed_description keeps only what comes before [Shot 1], plus the [Shot N]
      lines that were written by hand before (the LLM's version of them when it returned one; v0.6.0).
    """
    # [OLD 2026-11-03 v0.5.1->v0.6.0] out = {k: str(proposal.get(k) or "") for k in REF2VA_SECTIONS}  (a list or object became a repr)
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
        # [OLD 2026-11-03 v0.5.1->v0.6.0] every [Shot N] line was dropped, the ones written by hand too
        # pre, _ = _chunks(out["detailed_description"], SHOT_START)
        # out["detailed_description"] = pre
        # [/OLD]
        pre, theirs = _chunks(out["detailed_description"], SHOT_START)
        _, mine = _chunks(str(before.get("detailed_description") or ""), SHOT_START)
        rewritten = {}
        for label, chunk in theirs:
            rewritten.setdefault(label, chunk)
        if "detailed_description" not in given:
            pre = _chunks(str(before.get("detailed_description") or ""), SHOT_START)[0]
        out["detailed_description"] = "\n".join([pre] + [rewritten.get(label, chunk) for label, chunk in mine]).strip()
        given.add("detailed_description")
    for k in REF2VA_SECTIONS:  # sections the reply left out keep their text
        # [OLD 2026-11-04 v0.6.0->v0.6.1] with auto subjects / retention off, a reply without the key emptied the hand-written text
        # if k not in given and k not in ("subject_definitions", "retention_analysis"):
        # added 2026-11-04 v0.6.1: every left-out section keeps its text (an automatic one already holds `before`'s)
        if k not in given:
            out[k] = str(before.get(k) or "")
    return {k: v.strip() for k, v in out.items()}
