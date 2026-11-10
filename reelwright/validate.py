"""Lint rules. Problems are reported, never fixed silently; only errors block a render."""

import inspect

from . import model as _model
from . import prompt as _prompt
from . import soundtrack, spec
from .model import cast_description


def _issue(level, message, scene_id=None):
    x = {"level": level, "message": message}
    if scene_id:
        x["scene_id"] = scene_id
    return x


# ---- helpers -----------------------------------------------------------------------------------------------------

GUIDE_ROLES = (("first_frame", "first frame"), ("keyframes", "keyframe"), ("last_frame", "last frame"))
# A video guide longer than the room in its pass: the renderer shortens it (render.fit_clip), so it is a warning.
# Set "error" to stop such scenes in pre-flight instead.
CLIP_FIT_LEVEL = "warn"


def clip_frames(seconds):
    """Frames a video guide anchors: what render loads (at most 15 s at 24 fps), cut to 17k+5 like
    MiniMaxH3AddGuide; fewer than 5 frames anchor only the first picture."""
    n = int(round(min(float(seconds), spec.REF_MEDIA_MAX_SECONDS) * spec.FPS))
    return spec.align_frames_down(n) if n >= 5 else 1


def _sent_assets(b):
    """Asset ids one pass build sends: pictures, videos, audio, guide pictures and clips, the song's pieces."""
    out = set()
    for img in b["images"]:
        out.update(img["assets"])
    out.update(v["asset"] for v in b["videos"] if v.get("asset"))
    for au in b["audios"]:
        if au.get("song"):
            out.update(x["asset"] for x in au["song"].get("pieces") or [])
        elif au.get("asset"):
            out.add(au["asset"])
    out.update(g["asset"] for g in b["guides"] if g.get("asset"))
    return out


def _media_counts(p, scene, pass_, b, ctx):
    """Budget of one pass: model.scene_media_counts (the editor shows the same numbers) plus the guide pictures and
    clips the prompt names, which are sent too; counted from the build when model has no scene_media_counts."""
    assets = ctx["index"]["assets"]
    counts = getattr(_model, "scene_media_counts", None)
    if counts is not None:
        mode = ctx["start_mode"].get(scene["id"])
        kw = {"video_anchors": False} if "video_anchors" in inspect.signature(counts).parameters else {}
        c = dict(counts(p, scene, pass_, starts=ctx["starts"], mode=mode, **kw))
        sent = next((x for x in b["images"] + b["videos"] if x.get("continuation")), None)
        kind = "" if not sent else "picture" if sent in b["images"] else "video_audio" if sent["soundtrack"] else "video"
        if c.get("continuation", "") != kind:
            c = dict(counts(p, scene, pass_, starts=ctx["starts"], mode=mode, continuation=False, **kw))
            c["continuation"] = kind
            c["pictures" if kind == "picture" else "videos"] += 1 if kind else 0
            c["files"] += 1 if kind else 0
            if kind.startswith("video"):
                c["video_seconds"] += float(sent.get("frames") or 0) / spec.FPS
            if kind == "video_audio":
                c["audio"] += 1
                c["audio_seconds"] += float(sent.get("frames") or 0) / spec.FPS
        roles = {r["id"]: r["role"] for r in scene["refs"]}
        for img in b["images"]:
            if img["ref"] and roles.get(img["ref"]) in ("first_frame", "last_frame", "keyframe"):
                c["pictures"] += 1
                c["files"] += 1
        for v in b["videos"]:
            if v.get("guide"):
                c["videos"] += 1
                c["video_seconds"] += float(assets[v["asset"]].get("duration") or 0)
                c["files"] += 1
            if v.get("anchor") and kw:
                c["videos"] += 1
                c["files"] += 1
                c["video_seconds"] += float(v.get("seconds") or 0)
                if v["soundtrack"]:
                    c["audio"] += 1
                    c["audio_seconds"] += float(v.get("seconds") or 0)
        return c
    c = {"pictures": len(b["images"]), "videos": len(b["videos"]), "audio": len(b["audios"]),
         "video_seconds": sum(float(assets[v["asset"]].get("duration") or 0) for v in b["videos"]),
         "audio_seconds": 0.0, "song": any(a.get("song") for a in b["audios"])}
    for v in b["videos"]:
        if v["soundtrack"]:
            c["audio"] += 1
            c["audio_seconds"] += float(assets[v["asset"]].get("duration") or 0)
    for au in b["audios"]:
        c["audio_seconds"] += au["song"]["length"] if au.get("song") else float(assets[au["asset"]].get("duration") or 0)
    c["files"] = c["pictures"] + c["videos"] + len(b["audios"])
    return c


def _tail_overlap(p, i, plan):
    """Seconds at the start of scene i that repeat the tail of the scene before (trimmed in the cut)."""
    frames = getattr(_model, "tail_overlap_frames", None)
    if frames is not None:
        return frames(p, i) / spec.FPS
    if plan.get("start_mode") == "tail" and plan["passes"]:
        return plan["passes"][0]["overlap_frames"] / spec.FPS
    return 0.0


def _colour_name(c):
    return {"#000000": "black", "#ffffff": "white"}.get(str(c or "").lower(), str(c or "black"))


def _merge_issues(p, i, s, name, ctx, locked, scene_ids):
    """Problems with how scene i sits in the cut (scene.merge): a fade out on a scene the
    next one continues from, a fade in on a continuing scene, a colour reference scene that is not in the project,
    and (info) a transition that a soundtrack setting the timing turns into a dip inside both scenes."""
    out = []
    mg = s.get("merge") if isinstance(s.get("merge"), dict) else {}
    sid = s["id"]
    starts = ctx["start_mode"]
    mode = starts.get(sid, "fresh") if i > 0 else "fresh"
    nxt = p["scenes"][i + 1] if i + 1 < len(p["scenes"]) else None
    next_mode = starts.get(nxt["id"]) if nxt is not None else None
    if (mg.get("fade_out") or {}).get("frames") and next_mode in ("tail", "last_frame"):
        out.append(_issue("warn", "{}: it fades out to {}, but the next scene continues from its {}, which {} not "
                                  "faded, so the picture jumps back from the colour".format(
                                      name, _colour_name(mg["fade_out"].get("color")),
                                      "last frame" if next_mode == "last_frame" else "last frames",
                                      "is" if next_mode == "last_frame" else "are"), sid))
    if (mg.get("fade_in") or {}).get("frames") and mode in ("tail", "last_frame"):
        out.append(_issue("warn", "{}: it fades in from {}, but it continues the scene before, so the picture jumps "
                                  "from that scene to the colour".format(name, _colour_name(mg["fade_in"].get("color"))),
                          sid))
    if mg.get("color_match") == "scene" and mg.get("color_ref") not in scene_ids:
        out.append(_issue("warn", "{}: its colour match names a scene that is not in the project, so it is not colour "
                                  "matched; choose another scene".format(name), sid))
    kind = mg.get("transition") or "cut"
    if locked and i > 0 and mode == "fresh" and kind != "cut" and mg.get("frames"):
        colour = _colour_name(mg.get("color"))
        if kind == "dip":
            text = "its dip through {} plays inside both scenes (nothing overlaps)".format(colour)
        else:
            text = "its {} plays as a dip through {} inside both scenes (nothing overlaps)".format(kind, colour)
        out.append(_issue("info", "{}: with the soundtrack setting the timing, {}".format(name, text), sid))
    return out


def _cut_seam_hint(p, s, plan, name):
    """An info line for a long scene with overlap seams and no shot cuts: each
    overlap seam re-encodes the end of the pass before (decode -> encode), so later passes can drift; a shot cut near
    a seam makes it a plain cut (Seams: Auto or Cuts). None when it does not apply."""
    seams = [x for x in plan["passes"] if x.get("seam_before") == "overlap"]
    d = float(s["duration"])
    if not seams or any(0 < float(sh.get("t") or 0) < d for sh in s.get("shots") or []):
        return None
    lg = (p.get("global") or {}).get("long") or {}
    times = ", ".join("{:.2f} s".format(float(x["start"]) + int(x["overlap_frames"]) / spec.FPS) for x in seams)
    snap = float(lg.get("cut_snap_seconds") or 0)
    where = "up to {:g} s before a seam".format(snap) if snap > 0 else "at a seam"
    mode = "" if lg.get("seam_mode") != "overlap" else " and set Global → Long scenes → Seams to Auto or Cuts"
    return ("{}: its passes are joined by {} overlap seam{} (at {}); each re-encodes the end of the pass before, so "
            "later passes can drift. Add shot cuts {}{} to make them plain cuts.".format(
                name, len(seams), "" if len(seams) == 1 else "s", times, where, mode))


def _passes_label(name, indexes, n_passes):
    if n_passes == 1 or len(indexes) == n_passes:
        return name
    return "{} pass{} {}".format(name, "es" if len(indexes) > 1 else "", ", ".join(str(i) for i in indexes))


# ---- dialogue length, per-pass sections ----------------------------------------------------------------------------

def _numbers(xs):
    """[1, 2, 3] -> "1, 2 and 3"."""
    xs = [str(x) for x in xs]
    return xs[0] if len(xs) == 1 else "{} and {}".format(", ".join(xs[:-1]), xs[-1])


def _dialogue_span_issues(s, plan, name):
    """A dialogue line that runs past the end of its pass (the next pass's prompt does not have it, so H3 cuts it off)
    or past the scene's end; its length is its duration, else the estimate from its words (model.dialogue_spans)."""
    out = []
    for sp, line in zip(_model.dialogue_spans(s, plan), s["dialogue"]):
        if sp["pass"] is None or not str(line.get("text") or "").strip():
            continue  # in no pass, or empty: reported above
        about = "about " if sp["estimated"] else ""
        hint = " (its length is estimated from its words; give it a duration if it is shorter)" if sp["estimated"] else ""
        if sp["seam"] is not None:
            out.append(_issue("warn", "{}: the dialogue line at {:.2f} s runs to {}{:.2f} s, past the pass seam at {:.2f} s "
                                      "where pass {} takes over, so it is cut off; let it end before the seam or start "
                                      "after it{}".format(name, sp["start"], about, sp["end"], sp["seam"],
                                                          sp["pass"] + 1, hint), s["id"]))
        elif sp["past_end"]:
            out.append(_issue("warn", "{}: the dialogue line at {:.2f} s runs to {}{:.2f} s, past the scene's end at "
                                      "{:.2f} s{}".format(name, sp["start"], about, sp["end"], float(s["duration"]),
                                                          hint), s["id"]))
    return out


def _pass_text_issues(p, s, plan, name):
    """Structured prompts: pass texts written for another pass layout (info; Scene tab -> Prompt: Use the new layout),
    and the passes of a multi-pass scene without a summary of their own (one warning per scene)."""
    pr = s["prompt"]
    if pr["mode"] == "raw":
        return []
    out = []
    pt = _model.pass_texts(p, s, plan)
    stored = pr.get("passes") or []
    passes = plan["passes"]

    def span(x):
        x = x if isinstance(x, dict) else {}
        return "{}–{}".format(spec.fmt_time(spec.num(x.get("start"), 0.0)), spec.fmt_time(spec.num(x.get("end"), 0.0)))
    if pt["moved"] or pt["unused"]:
        parts = []
        for k in pt["moved"]:
            parts.append("pass {} ({} now) gets the text written for {}".format(
                k, span(passes[k - 1]), span(stored[pt["entry"][k - 1] - 1])))
        for j in pt["unused"]:
            parts.append("the text written for {} is not used".format(span(stored[j - 1])))
        out.append(_issue("info", "{}: pass texts were written for another pass layout: {} (Scene tab, Prompt: Use the "
                                  "new layout)".format(name, "; ".join(parts)), s["id"]))
    if len(passes) > 1:
        own = pr.get("pass_prompts") or {}
        missing = [k + 1 for k, t in enumerate(pt["texts"])
                   if _model._blank(t["summary"]) and not str(own.get(str(k + 1)) or "").strip()]
        if missing:
            note = _prompt._strip_task_tags(pr["sections"]["summary"]).strip()
            their = "its" if len(missing) == 1 else "their"
            made = "one made from {} shots".format(their) if note or pr["auto"].get("subjects") else \
                "only the task tags as {} summary".format(their)
            out.append(_issue("warn", "{}: pass{} {} {} no summary of {} own; {} {}{}".format(
                name, "es" if len(missing) > 1 else "", _numbers(missing), "has" if len(missing) == 1 else "have",
                "its" if len(missing) == 1 else "their", "it gets" if len(missing) == 1 else "they get", made,
                " (the scene summary is a note for you and the LLM and is not sent)" if note else ""), s["id"]))
    return out


def lint_project(p, plans, builds, asset_exists, ctx=None):
    """ctx: prompt.prepare(p), shared with build_pass."""
    ctx = ctx if ctx is not None and ctx.get("project") is p else _prompt.prepare(p)
    idx = ctx["index"]
    assets, cast = idx["assets"], idx["cast"]
    issues = []
    depth = ctx["depth"]
    reanchor = int(p["global"]["continuity"]["reanchor_after"])

    known = {}

    def exists(a):
        if a["id"] not in known:
            known[a["id"]] = bool(a.get("file")) and bool(asset_exists(a))
        return known[a["id"]]
    used = {aid for sid in builds for b in builds[sid] for aid in _sent_assets(b)}
    tracks = {t.get("asset") for t in p.get("soundtrack") or [] if not t.get("mute")}
    for a in p["assets"]:
        if not exists(a) and a["id"] not in used:
            issues.append(_issue("error" if a["id"] in tracks else "warn",
                                 "{} ({}) file is missing{}".format(a["code"], a["name"] or a["file"],
                                                                    "" if a["id"] in tracks else " (no scene uses it)")))

    hi = p["global"].get("hires") or {}
    if hi.get("enabled") and not (p["global"]["models"].get("latent_upscaler") or ""):
        issues.append(_issue("error", "Global -> Hires is on but no latent upscaler is chosen: pick one under Global -> "
                                      "Models, or turn Hires off"))

    for c in p["cast"]:
        for va in c.get("video_anchors") or []:
            a = assets.get(va.get("asset"))
            if not a or a["kind"] != "video":
                issues.append(_issue("warn", "{}: a video anchor {} so it is not sent".format(
                    c["name"], "is not a video," if a else "points to a deleted asset,")))
                continue
            clip = _model.ref_clip(va, a)
            if clip["seconds"] is not None and clip["seconds"] <= 0:
                issues.append(_issue("warn", "{}: video anchor {} starts at {} but ends there or before (its length is "
                                             "{}), so it is not sent".format(c["name"], a["code"],
                                                                          spec.fmt_time(clip["start"]),
                                                                          spec.fmt_time(float(a.get("duration") or 0)))))
            elif clip["seconds"] is not None and clip["seconds"] < spec.REF_MEDIA_MIN_SECONDS - 1e-6:
                issues.append(_issue("warn", "{}: video anchor {} is a {:.2f} s clip, so it is not sent (H3 video "
                                             "references are 2-15 s)".format(c["name"], a["code"], clip["seconds"])))
            elif clip["seconds"] is not None and clip["seconds"] > spec.REF_MEDIA_MAX_SECONDS + 1e-6:
                issues.append(_issue("info", "{}: video anchor {} is a {:.1f} s clip, so only its first {:g} s are sent; "
                                             "set its From / To to the part that shows {} best".format(
                                                 c["name"], a["code"], clip["seconds"], spec.REF_MEDIA_MAX_SECONDS,
                                                 c["name"])))

    for n, t in enumerate(p.get("soundtrack") or []):
        a = assets.get(t.get("asset"))
        label = "Soundtrack track {}".format(n + 1) + (" ({})".format(a["code"]) if a else "")
        if not a:
            issues.append(_issue("error" if not t.get("mute") else "warn",
                                 "{}: its audio asset no longer exists".format(label)))
            continue
        if a["kind"] != "audio":
            issues.append(_issue("error", "{}: {} is not an audio file".format(label, a["code"])))
            continue
        if t["out"] and t["out"] <= t["in"]:
            issues.append(_issue("warn", "{}: the trim end is before its start, so it plays to the end of the "
                                         "file".format(label)))
        dur = float(a.get("duration") or 0)
        if dur and t["in"] >= dur:
            issues.append(_issue("error", "{}: it is trimmed past the end of {} ({:.1f} s)".format(label, a["code"], dur)))
        if t["start"] < 0:
            issues.append(_issue("info", "{}: it starts {:.2f} s before the film, so that part is not heard".format(
                label, -t["start"])))
    locked = soundtrack.locked(p)
    scene_ids = {s["id"] for s in p["scenes"]}

    for i, s in enumerate(p["scenes"]):
        sid = s["id"]
        name = "{:02d} {}".format(i + 1, s["title"])
        d = float(s["duration"])
        plan = plans[sid]
        if d <= 0:
            issues.append(_issue("error", "{}: duration must be above 0".format(name), sid))
        if i == 0 and s["start"]["mode"] != "fresh":
            issues.append(_issue("info", "{}: the first scene always starts fresh".format(name), sid))
        if hasattr(_model, "pose_refs"):
            sent = {r["id"] for r, _, _ in _model.pose_refs(p, s, None, None, idx)}
            for r in s["refs"]:
                a = assets.get(r.get("asset"))
                if r.get("role") != "pose" or r["id"] in sent or not a:
                    continue
                c = cast.get(r.get("cast") or "")
                why = ("it is not a picture" if a["kind"] != "image" else
                       "it names no character (pick one under References)" if not c or c["kind"] != "character" else
                       "{} is not in this scene".format(c["name"]))
                issues.append(_issue("warn", "{}: {} is a pose reference but {}, so it is not sent".format(
                    name, a["code"], why), sid))
        if hasattr(_model, "ref_clip"):
            tokens = _model.ref_tokens(p, s, idx)
            for r in s["refs"]:
                a = assets.get(r.get("asset"))
                if not a or a["kind"] not in ("video", "audio") or r.get("role") != "reference" or not _model.ref_trimmed(r):
                    continue
                c = _model.ref_clip(r, a)
                dur = float(a.get("duration") or 0)
                tok = tokens.get(r["id"], "@" + a["code"])
                if dur and c["start"] >= dur - 0.5 / spec.FPS:
                    issues.append(_issue("error", "{}: {} starts at {} but {} is only {} long".format(
                        name, tok, spec.fmt_time(c["start"]), a["code"], spec.fmt_time(dur)), sid))
                elif r.get("out") is not None and float(r["out"]) <= c["start"] + 0.5 / spec.FPS:
                    issues.append(_issue("error", "{}: {} ends at {}, before it starts ({})".format(
                        name, tok, spec.fmt_time(float(r["out"])), spec.fmt_time(c["start"])), sid))
                elif dur and r.get("out") is not None and float(r["out"]) > dur + 0.5 / spec.FPS:
                    issues.append(_issue("info", "{}: {} ends at {}, after the end of {} ({}): it is sent up to its "
                                                 "end".format(name, tok, spec.fmt_time(float(r["out"])), a["code"],
                                                              spec.fmt_time(dur)), sid))
        if hasattr(_model, "scene_people"):
            for part, owner in _model.scene_people(p, s, idx)[1]:
                issues.append(_issue("warn", "{}: {} is part of {}, who is not in this scene, so it is left out (add {} "
                                             "to the scene, or clear its Part of)".format(name, part["name"], owner["name"],
                                                                                       owner["name"]), sid))
        if plan["kind"] == "long":
            issues.append(_issue("info", "{}: split into {} passes".format(name, len(plan["passes"])), sid))
            seam_hint = _cut_seam_hint(p, s, plan, name)
            if seam_hint:
                issues.append(_issue("info", seam_hint, sid))
        if plan["kind"] == "short":
            issues.append(_issue("info", "{}: rendered as {} frames and trimmed to {:.2f} s".format(
                name, spec.MIN_PASS_FRAMES, d), sid))
        if depth.get(sid, 0) > reanchor and s["start"]["mode"] == "tail":
            issues.append(_issue("info", "{}: {} chained continuations, so it continues from the last frame only (re-anchor rule)".format(
                name, depth[sid]), sid))
        elif i > 0 and s["start"]["mode"] == "tail" and ctx["start_mode"].get(sid) == "last_frame":
            issues.append(_issue("info", "{}: it or the scene before is shorter than 5 frames, so it continues from the "
                                         "last frame only".format(name), sid))
        overlap = _tail_overlap(p, i, plan) if i > 0 else 0.0

        for sh in s["shots"]:
            if float(sh["t"]) >= d:
                issues.append(_issue("error", "{}: a shot starts at {:.2f} s, after the scene ends".format(name, float(sh["t"])), sid))
            elif float(sh["t"]) < 0:
                issues.append(_issue("warn", "{}: a shot starts at {:.2f} s, before the scene, so it starts at 0 s".format(
                    name, float(sh["t"])), sid))
            elif 0 < float(sh["t"]) < overlap - 1e-6:
                issues.append(_issue("warn", "{}: a shot starts at {:.2f} s, inside the {:.2f} s tail overlap that the "
                                             "cut trims away; move it to {:.2f} s or later".format(
                                                 name, float(sh["t"]), overlap, overlap), sid))
        spoken = {x["id"] for pass_ in plan["passes"] for x in pass_["dialogue"]}
        for line in s["dialogue"]:
            t = float(line["t"])
            if t >= d:
                issues.append(_issue("error", "{}: a dialogue line at {:.2f} s is after the scene ends".format(name, t), sid))
            elif t < 0:
                issues.append(_issue("warn", "{}: a dialogue line at {:.2f} s starts before the scene, so it is spoken "
                                             "at 0 s".format(name, t), sid))
            elif t < overlap - 1e-6:
                issues.append(_issue("warn", "{}: a dialogue line at {:.2f} s is inside the {:.2f} s tail overlap, which "
                                             "the cut trims away; move it to {:.2f} s or later".format(
                                                 name, t, overlap, overlap), sid))
            elif line.get("id") and line["id"] not in spoken:
                issues.append(_issue("warn", "{}: the dialogue line at {:.2f} s is in no pass, so H3 never hears "
                                             "it".format(name, t), sid))
            if not line["text"].strip():
                issues.append(_issue("warn", "{}: a dialogue line is empty".format(name), sid))
            if not line.get("speaker"):
                issues.append(_issue("warn", "{}: a dialogue line has no speaker".format(name), sid))
            elif line["speaker"] not in cast:
                issues.append(_issue("error", "{}: a dialogue speaker is not in the cast".format(name), sid))
            if not line.get("language"):
                issues.append(_issue("warn", "{}: a dialogue line has no language tag".format(name), sid))
            elif line["language"] not in spec.STABLE_LANGUAGES:
                issues.append(_issue("info", "{}: {} is outside H3's 11 stable dialogue languages".format(name, line["language"]), sid))
        issues += _dialogue_span_issues(s, plan, name)
        issues += _pass_text_issues(p, s, plan, name)

        has_first = False
        for r in s["refs"]:
            a = assets.get(r["asset"])
            if not a:
                issues.append(_issue("error", "{}: a reference points to a deleted asset".format(name), sid))
                continue
            if r["role"] == "keyframe" and not (0 <= float(r["time"]) < d):
                issues.append(_issue("error", "{}: keyframe {} at {:.2f} s is outside the scene".format(name, a["code"], float(r["time"])), sid))
            if r["role"] in ("first_frame", "last_frame", "keyframe") and a["kind"] == "audio":
                issues.append(_issue("error", "{}: audio {} cannot be a {}".format(name, a["code"], r["role"].replace("_", " ")), sid))
            if r["role"] == "first_frame":
                has_first = True
        if has_first and i > 0 and s["start"]["mode"] != "fresh":
            issues.append(_issue("warn", "{}: a first-frame reference and a continuation both anchor frame 0".format(name), sid))
        issues += _merge_issues(p, i, s, name, ctx, locked, scene_ids)

        for entry in s["cast"]:
            c = cast.get(entry["id"])
            if not c:
                issues.append(_issue("error", "{}: a cast member was deleted".format(name), sid))
            elif c["kind"] == "character" and not c["anchors"]:
                issues.append(_issue("warn", "{}: {} has no anchor pictures, so identity is not locked".format(name, c["name"]), sid))
            elif c["kind"] == "character" and set(c["anchors"]) <= set(entry.get("skip") or []):
                issues.append(_issue("warn", "{}: every anchor picture of {} is unticked in this scene (Cast in this "
                                             "scene -> Anchors), so identity is not locked".format(name, c["name"]), sid))

        if hasattr(_model, "tile_pixels"):
            st = _model.resolve_settings(p, s, i)
            small = {}
            for b in builds[sid]:
                for img in b["images"]:
                    if img.get("cast") in cast and len(img["assets"]) > 1:
                        px = _model.tile_pixels([assets[a] for a in img["assets"] if a in assets], st["width"],
                                                st["height"], st["ref_image_size"])
                        if px < _model.SMALL_TILE_PX:
                            small[img["cast"]] = (len(img["assets"]), px)
            for cid, (n, px) in small.items():
                cols, rows = _model.sheet_grid(n)
                issues.append(_issue("warn", "{}: {}'s {} pictures go to H3 as one {}x{} sheet, so each reaches it at "
                                             "about {} px, too small for a reliable identity; send fewer anchors, pick "
                                             "Separate or Auto under Cast -> Anchors{}".format(
                                                 name, cast[cid]["name"], n, cols, rows, px,
                                                 "" if st["ref_image_size"] == "max" else
                                                 ", or set Global -> Output -> Reference images to max"), sid))

        sent = set()
        for b in builds[sid]:
            sent |= _sent_assets(b)
        for aid in sorted(sent, key=lambda x: assets[x]["code"] if x in assets else x):
            a = assets.get(aid)
            if a and not exists(a):
                issues.append(_issue("error", "{}: {} ({}) file is missing".format(name, a["code"], a["name"] or a["file"]), sid))
        n_passes = len(plan["passes"])
        for k, text in sorted((s["prompt"].get("pass_prompts") or {}).items()):
            if isinstance(text, str) and text.strip() and (not str(k).isdigit() or not 1 <= int(k) <= n_passes):
                issues.append(_issue("warn", "{}: the prompt written for pass {} is not used, because the scene has {} "
                                             "pass{} now".format(name, k, n_passes, "es" if n_passes > 1 else ""), sid))
        said = {}
        for b, pass_ in zip(builds[sid], plan["passes"]):
            for x in b.get("issues") or []:
                said.setdefault((x["level"], x["message"]), []).append(pass_["index"])
        for (level, message), where_ in said.items():
            issues.append(_issue(level, "{}: {}".format(_passes_label(name, where_, n_passes), message), sid))

        for b, pass_ in zip(builds[sid], plan["passes"]):
            where = name if len(plan["passes"]) == 1 else "{} pass {}".format(name, pass_["index"])
            n = _media_counts(p, s, pass_, b, ctx)
            if n["pictures"] > spec.MAX_REF_IMAGES:
                issues.append(_issue("warn", "{}: {} pictures (H3 is trained on up to 9)".format(where, n["pictures"]), sid))
            if n["videos"] > spec.MAX_REF_VIDEOS:
                issues.append(_issue("warn", "{}: {} reference videos (up to 3)".format(where, n["videos"]), sid))
            if n["audio"] > spec.MAX_REF_AUDIOS:
                issues.append(_issue("warn", "{}: {} reference audio clips, counting a video's own sound and the "
                                             "soundtrack (up to 3)".format(where, n["audio"]), sid))
            if n["files"] > spec.MAX_REF_FILES:
                issues.append(_issue("warn", "{}: {} reference files (up to 12)".format(where, n["files"]), sid))
            if n["video_seconds"] > spec.REF_MEDIA_TOTAL_SECONDS + 1e-4:
                issues.append(_issue("warn", "{}: video refs total {:.1f} s (max 15 s)".format(where, n["video_seconds"]), sid))
            if n["audio_seconds"] > spec.REF_MEDIA_TOTAL_SECONDS + 1e-4:
                issues.append(_issue("warn", "{}: audio refs total {:.1f} s, counting a video's own sound and the "
                                             "soundtrack (max 15 s)".format(where, n["audio_seconds"]), sid))
            for key, label in GUIDE_ROLES:
                for g in pass_.get(key) or []:
                    r = next((x for x in s["refs"] if x["id"] == g["ref"]), None)
                    a = assets.get(r["asset"]) if r else None
                    if not a or a["kind"] != "video" or not float(a.get("duration") or 0):
                        continue
                    frames = clip_frames(float(a["duration"]))
                    room = g["frame_idx"] + 1 if key == "last_frame" else pass_["gen_frames"] - g["frame_idx"]
                    if frames <= room:
                        continue
                    used = spec.align_frames_down(room) if room >= 5 else 1
                    shorter = "shorten the clip to {:.2f} s".format(used / spec.FPS) if used > 1 else \
                        "use a picture instead (Render tab: promote a frame)"
                    if key == "keyframes":
                        latest = pass_["start"] + (pass_["gen_frames"] - frames) / spec.FPS
                        fix = ("move it to {:.2f} s or earlier, or {}".format(latest, shorter)
                               if latest >= max(0.0, pass_["start"] + pass_["keep_in"]) else shorter)
                    elif key == "last_frame":
                        fix = shorter + ", or make the scene longer"
                    else:
                        fix = shorter
                    issues.append(_issue(CLIP_FIT_LEVEL, "{}: {} {} is a {}-frame clip ({:.2f} s), but the {}-frame pass "
                                                         "has room for {} of them, so only its {} {} frame{} {} used; {}".format(
                                                             where, label, a["code"], frames, frames / spec.FPS,
                                                             pass_["gen_frames"], room,
                                                             "last" if key == "last_frame" else "first", used,
                                                             "s" if used > 1 else "", "are" if used > 1 else "is", fix), sid))
            audio_items = [{"code": "soundtrack", "duration": x["song"]["length"]} if x.get("song") else
                           {"code": assets[x["asset"]]["code"] + " (clip)", "duration": x["seconds"] or 0} if "seconds" in x
                           else assets[x["asset"]] for x in b["audios"]]
            video_items = [{"code": _prompt.CONT_WHAT.get(v.get("source"), "the continuation clip"),
                            "duration": float(v.get("frames") or 0) / spec.FPS} if v.get("continuation")
                           else {"code": assets[v["asset"]]["code"] + " (clip)", "duration": v["seconds"] or 0}
                           if "seconds" in v else assets[v["asset"]] for v in b["videos"]]
            for kind, items in (("video", video_items),
                                ("audio", audio_items)):
                total = 0.0
                for a in items:
                    dur = float(a.get("duration") or 0)
                    total += dur
                    if dur and not (spec.REF_MEDIA_MIN_SECONDS <= dur <= spec.REF_MEDIA_MAX_SECONDS):
                        issues.append(_issue("warn", "{}: {} is {:.1f} s (H3 {} refs are 2-15 s)".format(where, a["code"], dur, kind), sid))
            if s["prompt"]["mode"] == "raw":
                text = (s["prompt"]["pass_prompts"] or {}).get(str(pass_["index"])) or s["prompt"]["raw"]
                for img in b["images"]:
                    for aid in img["assets"]:
                        code = "@" + assets[aid]["code"]
                        if not img["cast"] and code.lower() not in text.lower():
                            issues.append(_issue("info", "{}: {} is attached but never named in the prompt".format(where, code), sid))
            elif not (s["prompt"]["pass_prompts"] or {}).get(str(pass_["index"]), "").strip():
                desc = b["prompt"].split("detailed_description:\n", 1)[-1].split("\n\noverall_soundscape:", 1)[0]
                words = len(desc.split())
                if words < 120:
                    issues.append(_issue("info", "{}: detailed_description has {} words; H3's guide aims for 350-500 "
                                                 "(Rewrite can expand it)".format(where, words), sid))
        if s["prompt"]["mode"] != "raw":
            if not s["prompt"]["sections"]["overall_soundscape"].strip():
                silent = [k + 1 for k, t in enumerate(_model.pass_texts(p, s, plan)["texts"])
                          if not t["overall_soundscape"].strip()]
                if silent:
                    issues.append(_issue("info", "{}: overall_soundscape is empty, so H3 gets N/A, which its guide "
                                                 "reserves for complete silence".format(
                                                     _passes_label(name, silent, n_passes)), sid))
            described = set()
            for b in builds[sid]:
                for subj in b["subjects"]:
                    a = assets.get(subj.get("asset") or "")
                    if a and not (a.get("description") or "").strip() and a["id"] not in described:
                        described.add(a["id"])
                        issues.append(_issue("info", "{}: {} has no description, so its subject line is generic "
                                                     "(Assets tab: Describe with LLM)".format(name, a["code"]), sid))
                    c = idx["cast"].get(subj.get("cast") or "")
                    if c and c["id"] not in described and not cast_description(c, assets)[0]:
                        described.add(c["id"])
                        issues.append(_issue("info", "{}: {} has no description and none of its anchor pictures has "
                                                     "one, so its subject line is only the name (Cast tab or Assets "
                                                     "tab: Describe with LLM)".format(name, c["name"]), sid))
    issues += _voice_issues(p, plans, assets)
    return issues


# H3 picks a voice for every generation; a character heard in more than one pass needs a
# voice reference or a voice description that every pass gets, or the voice can change (a narrator from male to female)
def _voice_issues(p, plans, assets):
    describe = p["global"]["continuity"].get("describe_voices", True)
    heard = {}  # cast id -> number of passes with a line of theirs
    for s in p["scenes"]:
        plan = plans.get(s["id"])
        if not plan:
            continue
        for x in plan["passes"]:
            for cid in {d.get("speaker") for d in x["dialogue"] if str(d.get("text") or "").strip()}:
                heard[cid] = heard.get(cid, 0) + 1
    out = []
    for c in p["cast"]:
        n = heard.get(c["id"], 0)
        if n < 2 or c["kind"] != "character" or (c.get("voice") and c["voice"] in assets):
            continue
        if describe and str(c.get("voice_desc") or "").strip():
            continue
        out.append(_issue("warn", "{} speaks in {} passes with no voice reference{}, so H3 may give them another voice "
                                  "in each pass: describe the voice or cut one from a take (Cast tab)".format(
                                      c["name"] or "A character", n,
                                      " and no voice description" if describe else " (and Describe voices is off)")))
    return out
