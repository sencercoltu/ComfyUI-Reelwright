"""Per-pass prompt assembly and reference numbering.

The editor refers to assets as @P1 / @V2 / @A1, to cast as @Mara or
@{Old Keeper}, and to the continuation as @tail. Each pass gets its own
numbering in the order MiniMaxH3ReferenceToVideo presents references:
images, then videos (a video's soundtrack takes its <Audio j> number right
before its <Video k>), then standalone audio.
"""

import re

from . import spec
from .model import project_index
from .planner import continuation_depth

TAG_RE = re.compile(r"@\{([^}]+)\}|@([A-Za-z][\w-]*)")


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
        refs.subjects.append({"cast": c["id"], "number": n + 1, "outfit": outfit,
                              "pictures": list(range(first_pic, len(refs.images) + 1))})
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
            refs.images.append({"assets": [a["id"]], "cast": None, "ref": r["id"]})
        elif a["kind"] == "video":
            refs.videos.append({"asset": a["id"], "soundtrack": bool(r.get("soundtrack")), "ref": r["id"]})
        elif a["kind"] == "audio" and not any(x["asset"] == a["id"] for x in refs.audios):
            refs.audios.append({"asset": a["id"], "ref": r["id"], "cast": None})
    refs.number()

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


def _subject_lines(p, refs):
    cast = project_index(p)["cast"]
    lines = []
    for s in refs.subjects:
        c = cast[s["cast"]]
        pics = ", ".join("<Picture {}>".format(k) for k in s["pictures"])
        head = "<Subject {}>".format(s["number"])
        bits = [c["name"]]
        if c["description"]:
            bits.append(c["description"].rstrip("."))
        if s["outfit"] and s["outfit"]["name"]:
            bits.append("wearing " + s["outfit"]["name"])
        src = (" is shown in " + pics) if pics else ""
        lines.append("{}{}: {}.".format(head, src, ", ".join(bits)))
    return lines


def _retention_lines(p, scene, refs, pass_):
    idx = project_index(p)
    assets, cast = idx["assets"], idx["cast"]
    ref_by_id = {r["id"]: r for r in scene["refs"]}
    shots = pass_["shots"]
    span = "Shots 1-{}".format(len(shots)) if len(shots) > 1 else "Shot 1"
    lines = []
    for s in refs.subjects:
        c = cast[s["cast"]]
        if c["kind"] != "character" and not s["pictures"]:
            continue
        o = s["outfit"]
        ret = (o or {}).get("retention") or "fully_preserved"
        keep = ", ".join((o or {}).get("keep") or ["identity", "appearance"])
        lines.append("<Subject {}> ({}): {} - {}".format(s["number"], span, ret, keep))
    for k, img in enumerate(refs.images, 1):
        if img["cast"] or not img["ref"]:
            continue
        a = assets[img["assets"][0]]
        r = ref_by_id.get(img["ref"], {})
        keep = ", ".join(_keep(r, a)) or a.get("category") or "overall look"
        lines.append("<Picture {}>: {} - {}".format(k, _retention(r, a), keep))
    for k, v in enumerate(refs.videos, 1):
        a = assets[v["asset"]]
        r = ref_by_id.get(v["ref"], {})
        keep = ", ".join(_keep(r, a)) or a.get("category") or "motion"
        lines.append("<Video {}>: {} - {}".format(k, _retention(r, a), keep))
        if v["soundtrack"]:
            lines.append("<Audio {}>: reference - soundtrack of <Video {}>".format(v["audio_number"], k))
    for au in refs.audios:
        a = assets[au["asset"]]
        n = refs.audio_of_asset[au["asset"]]
        if au["cast"]:
            c = cast[au["cast"]]
            subj = next((s["number"] for s in refs.subjects if s["cast"] == c["id"]), None)
            lines.append("<Audio {}>: reference - voice timbre and delivery of <Subject {}>".format(n, subj))
        else:
            r = ref_by_id.get(au["ref"], {})
            keep = ", ".join(_keep(r, a)) or a.get("category") or "sound"
            lines.append("<Audio {}>: {} - {}".format(n, _retention(r, a), keep))
    return lines


def _shot_lines(p, scene, refs, pass_):
    cast = project_index(p)["cast"]
    subject_of_cast = {s["cast"]: s["number"] for s in refs.subjects}
    shots = pass_["shots"]
    lines = []
    if not shots:
        shots = [{"number": 1, "continuing": False, "t": 0.0, "camera": "", "text": ""}]
    for n, sh in enumerate(shots, 1):
        nxt = shots[n]["t"] if n < len(shots) else None
        head = "[Shot{}]".format(n)
        if n > 1:
            head += " At {}, cut to".format(spec.fmt_time(sh["t"]))
        elif sh["continuing"]:
            head += " Continuing the same shot,"
        body = sh["camera"].strip()
        if sh["text"].strip():
            body = (body + ": " if body else "") + sh["text"].strip()
        if body and body[-1] not in ".!?":
            body += "."
        parts = [head + (" " + body if body else "")]
        for d in pass_["dialogue"]:
            if d["t"] < sh["t"] or (nxt is not None and d["t"] >= nxt):
                continue
            c = cast.get(d["speaker"])
            who = "<Subject {}> ({})".format(subject_of_cast[c["id"]], c["speaker"] or "S?") if c and c["id"] in subject_of_cast else "A voice off-screen"
            verb = d["delivery"].strip() or "says"
            parts.append("At {}, {} {} <d>[{}] {}</d>.".format(spec.fmt_time(d["t"]), who, verb,
                                                             d["language"] or "English", d["text"].strip()))
        lines.append(" ".join(parts))
    if len(shots) == 1:
        lines.append("Single continuous take, no cuts.")
    return lines


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
        sec = {k: substitute(v, p, refs, unknown).strip() for k, v in pr["sections"].items()}
        auto = pr["auto"]
        blocks = []
        head = " ".join(x for x in (tag_line, sec["summary"]) if x)
        if head:
            blocks.append(head)
        subj = (_subject_lines(p, refs) if auto.get("subjects") else []) + ([sec["subject_definitions"]] if sec["subject_definitions"] else [])
        if subj:
            blocks.append("Subjects:\n" + "\n".join(subj))
        ret = (_retention_lines(p, scene, refs, pass_) if auto.get("retention") else []) + ([sec["retention_analysis"]] if sec["retention_analysis"] else [])
        if ret:
            blocks.append("Retention:\n" + "\n".join(ret))
        shots = (_shot_lines(p, scene, refs, pass_) if auto.get("shots") else []) + ([sec["detailed_description"]] if sec["detailed_description"] else [])
        if shots:
            blocks.append("Shots:\n" + "\n".join(shots))
        if sec["overall_soundscape"]:
            blocks.append("Soundscape: " + sec["overall_soundscape"])
        if sec["non_diegetic_music"]:
            blocks.append("Music: " + sec["non_diegetic_music"])
        text = "\n\n".join(blocks)

    tag_map = {}
    idx = project_index(p)
    for aid, k in refs.picture_of_asset.items():
        tag_map["@" + idx["assets"][aid]["code"]] = "<Picture {}>".format(k)
    for aid, k in refs.video_of_asset.items():
        tag_map["@" + idx["assets"][aid]["code"]] = "<Video {}>".format(k)
    for aid, k in refs.audio_of_asset.items():
        tag_map["@" + idx["assets"][aid]["code"]] = "<Audio {}>".format(k)
    for s in refs.subjects:
        tag_map["@" + idx["cast"][s["cast"]]["name"]] = "<Subject {}>".format(s["number"])

    return {"prompt": text, "tags": tags, "tag_map": tag_map, "unknown": sorted(set(unknown)),
            "images": refs.images, "videos": refs.videos, "audios": refs.audios,
            "guides": refs.guides, "subjects": refs.subjects}
