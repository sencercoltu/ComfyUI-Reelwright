"""Per-pass prompt assembly and reference numbering.

The editor refers to assets as @P1 / @V2 / @A1, to cast as @Mara or
@{Old Keeper}, and to the continuation as @tail. Each pass gets its own
numbering in the order MiniMaxH3ReferenceToVideo presents references:
images, then videos (a video's soundtrack takes its <Audio j> number right
before its <Video k>), then standalone audio.
"""

import re

from . import spec
# [OLD 2026-11-02 v0.3.3->v0.3.4] from .model import project_index
from .model import cast_description, project_index
from .planner import continuation_depth

TAG_RE = re.compile(r"@\{([^}]+)\}|@([A-Za-z][\w-]*)")

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
            self.audio_of_asset.setdefault(a["asset"], audio_n)

    @property
    def file_count(self):
        return len(self.images) + len(self.videos) + len(self.audios)


def collect_refs(p, scene, scene_index, pass_, n_passes, mentioned_codes=()):
    idx = project_index(p)
    assets, cast = idx["assets"], idx["cast"]
    refs = PassRefs()

    speakers = [d["speaker"] for d in scene["dialogue"] if d.get("speaker")]
    cast_entries = list(scene["cast"])
    for sp in speakers:
        if sp in cast and not any(c["id"] == sp for c in cast_entries):
            cast_entries.append({"id": sp, "outfit": ""})

    for n, entry in enumerate(e for e in cast_entries if e["id"] in cast):
        c = cast[entry["id"]]
        outfit = next((o for o in c["outfits"] if o["id"] == (entry.get("outfit") or c["default_outfit"])), None)
        anchor_ids = [a for a in c["anchors"] if a in assets and assets[a]["kind"] == "image"]
        if outfit:
            anchor_ids += [a for a in outfit["assets"] if a in assets and assets[a]["kind"] == "image" and a not in anchor_ids]
        first_pic = len(refs.images) + 1
        if anchor_ids and c["pack_sheet"] and len(anchor_ids) > 1:
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
        if c.get("voice") in assets and assets[c["voice"]]["kind"] == "audio":
            refs.audios.append({"asset": c["voice"], "ref": None, "cast": c["id"]})

    guide_only = {"first_frame", "last_frame", "keyframe"}
    for r in scene["refs"]:
        a = assets.get(r["asset"])
        if not a:
            continue
        if r["role"] in guide_only:
            if a["kind"] == "image" and a["code"].upper() in mentioned_codes and not any(a["id"] in img["assets"] for img in refs.images):
                refs.images.append({"assets": [a["id"]], "cast": None, "ref": r["id"]})
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
        if a.get("category") not in SUBJECT_VIDEO_CATEGORIES or a["id"] in refs.subject_of_asset:
            continue
        refs.subjects.append({"cast": None, "ref": v["ref"], "asset": a["id"], "number": len(refs.subjects) + 1,
                              "outfit": None, "pictures": [], "videos": [k]})
        refs.subject_of_asset[a["id"]] = refs.subjects[-1]["number"]

    # guides
    i = pass_["index"]
    depth = continuation_depth(p).get(scene["id"], 0)
    reanchor = depth > int(p["global"]["continuity"]["reanchor_after"])
    if i == 1 and scene_index > 0:
        mode = scene["start"]["mode"]
        if mode == "tail" and pass_["overlap_frames"] and not reanchor:
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


def task_tags(p, scene, refs):
    assets = project_index(p)["assets"]
    tags = set()
    if refs.file_count:
        tags.add("reference generation")
    if any(g["type"] == "image" for g in refs.guides):
        tags.add("keyframe completion")
    if any(g["type"] == "clip" and g["source"] != "asset" for g in refs.guides):
        tags.add("video continuation")
    if any(g["type"] == "clip" and g["source"] == "asset" for g in refs.guides):
        tags.add("keyframe completion")
    ref_by_id = {r["id"]: r for r in scene["refs"]}
    for v in refs.videos:
        a = assets[v["asset"]]
        if a.get("category") == "edit_source":
            tags.add("video editing")
        if v["soundtrack"]:
            ret = _retention(ref_by_id.get(v["ref"], {}), a) if v["ref"] else "reference"
            tags.add("audio reuse" if ret in ("fully_copy", "partially_copy") else "audio reference")
    for au in refs.audios:
        a = assets[au["asset"]]
        ret = _retention(ref_by_id.get(au["ref"], {}), a) if au["ref"] else "reference"
        tags.add("audio reuse" if ret in ("fully_copy", "partially_copy") else "audio reference")
    return [t for t in spec.TASK_TAG_ORDER if t in tags]


def mentioned_codes(text):
    return {(m.group(2) or "").upper() for m in TAG_RE.finditer(text or "") if m.group(2)}


def substitute(text, p, refs, unknown):
    idx = project_index(p)
    subject_of_cast = {s["cast"]: s["number"] for s in refs.subjects}

    def repl(m):
        name = m.group(1) or m.group(2)
        key = name.upper()
        a = idx["codes"].get(key) if m.group(2) else None
        if a:
            # added 2026-11-02 v0.2.0: assets that became subjects resolve to their <Subject N>
            if a["id"] in refs.subject_of_asset:
                return "<Subject {}>".format(refs.subject_of_asset[a["id"]])
            if a["kind"] == "image" and a["id"] in refs.picture_of_asset:
                return "<Picture {}>".format(refs.picture_of_asset[a["id"]])
            if a["kind"] == "video" and a["id"] in refs.video_of_asset:
                return "<Video {}>".format(refs.video_of_asset[a["id"]])
            if a["kind"] == "audio" and a["id"] in refs.audio_of_asset:
                return "<Audio {}>".format(refs.audio_of_asset[a["id"]])
            unknown.append(m.group(0))
            return m.group(0)
        if name.lower() == "tail":
            return "the end of the previous shot"
        c = idx["cast_by_name"].get(name.strip().lower())
        if c and c["id"] in subject_of_cast:
            return "<Subject {}>".format(subject_of_cast[c["id"]])
        unknown.append(m.group(0))
        return m.group(0)

    return TAG_RE.sub(repl, text or "")


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


def _appears(p, refs, pass_, subj):
    """'appears in [Shot 1], [Shot 3]' from @mentions in shot text and spoken lines."""
    shots = pass_["shots"] or [{"t": 0.0, "camera": "", "text": ""}]
    idx = project_index(p)
    hits = set()
    if subj["cast"]:
        name = idx["cast"][subj["cast"]]["name"].strip().lower()
        match = lambda m: (m.group(1) or m.group(2) or "").strip().lower() == name
    else:
        code = idx["assets"][subj["asset"]]["code"].upper()
        match = lambda m: (m.group(2) or "").upper() == code
    for i, sh in enumerate(shots, 1):
        if any(match(m) for m in TAG_RE.finditer("{} {}".format(sh.get("camera", ""), sh.get("text", "")))):
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


def subject_definitions(p, scene, refs, pass_, ids):
    idx = project_index(p)
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
        what = role or ("a composition reference" if a.get("category") == "keyframe" else "a reference image")
        lines.append("<Picture {}> is {}{}.".format(k, what, ", showing " + desc if desc else ""))
    for k, v in enumerate(refs.videos, 1):
        if any(k in s["videos"] for s in refs.subjects):
            continue
        a = assets[v["asset"]]
        desc = (a.get("description") or "").strip().rstrip(".")
        if a.get("category") == "edit_source":
            lines.append("<Video {}> is the source video for the target video edit.".format(k))
        else:
            lines.append("<Video {}> is the camera-movement and pacing reference{}.".format(k, ", showing " + desc if desc else ""))
    sub_of_cast = {s["cast"]: s["number"] for s in refs.subjects if s["cast"]}
    for v_k, v in enumerate(refs.videos, 1):
        if v["soundtrack"]:
            lines.append("<Audio {}> is the synchronized audio track of <Video {}>.".format(v["audio_number"], v_k))
    for au in refs.audios:
        a = assets[au["asset"]]
        n = refs.audio_of_asset[au["asset"]]
        if au["cast"]:
            spk = " ({})".format(ids[au["cast"]]) if au["cast"] in ids else ""
            lines.append("<Audio {}> is the voice-timbre reference for <Subject {}>{}.".format(n, sub_of_cast.get(au["cast"], "?"), spk))
        else:
            desc = (a.get("description") or "").strip().rstrip(".")
            lines.append("<Audio {}> is {}.".format(n, desc or AUDIO_PHRASE.get(a.get("category"), "the audio reference")))
    return lines


def retention_analysis(p, scene, refs, pass_):
    idx = project_index(p)
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
        lines.append("<Subject {}> ({}): {} - {}.".format(s["number"], _appears(p, refs, pass_, s), ret, _keep_phrase(keep, ret)))
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


def _dialogue_sentence(p, refs, d, ids):
    cast = project_index(p)["cast"]
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


def shot_descriptions(p, scene, refs, pass_, ids, unknown):
    """[Shot 1] ... / [Shot N] At MM:SS.mmm, the shot cuts to ... with the lines spoken in each shot."""
    shots = pass_["shots"] or [{"number": 1, "continuing": False, "t": 0.0, "camera": "", "text": ""}]
    sub = lambda t: substitute(t, p, refs, unknown).strip()
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
        for d in pass_["dialogue"]:
            if float(d["t"]) < float(sh["t"]) - 1e-6 and n > 1:
                continue
            if nxt is not None and float(d["t"]) >= float(nxt) - 1e-6:
                continue
            parts.append(_dialogue_sentence(p, refs, d, ids))
        out.append(" ".join(parts))
    return out


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
    return text


def build_pass(p, scene, scene_index, plan, pass_):
    """Return the prompt and reference plan for one pass."""
    pr = scene["prompt"]
    override = (pr.get("pass_prompts") or {}).get(str(pass_["index"]), "")
    sources = [override] if override.strip() else (
        [pr["raw"]] if pr["mode"] == "raw" else list(pr["sections"].values()))
    mentioned = set()
    for t in sources:
        mentioned |= mentioned_codes(t)
    refs = collect_refs(p, scene, scene_index, pass_, len(plan["passes"]), mentioned)
    tags = task_tags(p, scene, refs)
    tag_line = "[{}]".format(" + ".join(tags)) if tags else ""
    unknown = []

    if override.strip() or pr["mode"] == "raw":
        body = substitute(override if override.strip() else pr["raw"], p, refs, unknown).strip()
        text = body if body.startswith("[") or not tag_line else (tag_line + " " + body).strip()
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
        sec = {k: substitute(v, p, refs, unknown).strip() for k, v in pr["sections"].items()}
        auto = pr["auto"]
        ids = speaker_ids(pass_)
        subj = (subject_definitions(p, scene, refs, pass_, ids) if auto.get("subjects") else []) + \
            ([sec["subject_definitions"]] if sec["subject_definitions"] else [])
        summary = sec["summary"] or (_auto_summary(refs, pass_) if auto.get("subjects") else "")
        summary = " ".join(x for x in (tag_line, summary) if x)
        ret = (retention_analysis(p, scene, refs, pass_) if auto.get("retention") else []) + \
            ([sec["retention_analysis"]] if sec["retention_analysis"] else [])
        desc = ([sec["detailed_description"]] if sec["detailed_description"] else []) + \
            (shot_descriptions(p, scene, refs, pass_, ids, unknown) if auto.get("shots") else [])
        body = {
            "subject_definitions": "\n".join(subj), "summary": summary, "retention_analysis": "\n".join(ret),
            "detailed_description": "\n".join(desc), "overall_soundscape": sec["overall_soundscape"],
            "non_diegetic_music": sec["non_diegetic_music"],
        }
        text = "\n\n".join("{}:\n{}".format(k, body[k].strip() or "N/A") for k in REF2VA_SECTIONS)

    tag_map = {}
    idx = project_index(p)
    for aid, k in refs.picture_of_asset.items():
        tag_map["@" + idx["assets"][aid]["code"]] = "<Picture {}>".format(k)
    for aid, k in refs.video_of_asset.items():
        tag_map["@" + idx["assets"][aid]["code"]] = "<Video {}>".format(k)
    for aid, k in refs.audio_of_asset.items():
        tag_map["@" + idx["assets"][aid]["code"]] = "<Audio {}>".format(k)
    # [OLD 2026-11-02 v0.1.0->v0.2.0] reference subjects have no cast entry
    # for s in refs.subjects:
    #     tag_map["@" + idx["cast"][s["cast"]]["name"]] = "<Subject {}>".format(s["number"])
    # [/OLD]
    for s in refs.subjects:
        if s["cast"]:
            tag_map["@" + idx["cast"][s["cast"]]["name"]] = "<Subject {}>".format(s["number"])
        else:
            tag_map["@" + idx["assets"][s["asset"]]["code"]] = "<Subject {}>".format(s["number"])

    return {"prompt": text, "tags": tags, "tag_map": tag_map, "unknown": sorted(set(unknown)),
            "images": refs.images, "videos": refs.videos, "audios": refs.audios,
            "guides": refs.guides, "subjects": refs.subjects}
