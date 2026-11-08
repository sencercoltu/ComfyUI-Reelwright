"""Lint rules. Problems are reported, never fixed silently; only errors block a render."""

from . import spec
from . import model as _model  # added 2026-11-03 v0.6.0: feature-detects scene_media_counts / tail_overlap_frames
# [OLD 2026-11-02 v0.3.3->v0.3.4] from .model import project_index
from .model import cast_description, project_index
from .planner import continuation_depth
from . import prompt as _prompt  # added 2026-11-03 v0.6.0: prompt.prepare (shared context)
from . import soundtrack  # added 2026-11-03 v0.5.0


def _issue(level, message, scene_id=None):
    x = {"level": level, "message": message}
    if scene_id:
        x["scene_id"] = scene_id
    return x


# ---- helpers (added 2026-11-03 v0.6.0) ---------------------------------------------------------------------------

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
    # [OLD 2026-11-05 v0.6.1->v0.7.0] out.update(v["asset"] for v in b["videos"])
    out.update(v["asset"] for v in b["videos"] if v.get("asset"))  # v0.7.0: the continuation clip is no asset
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
        # [OLD 2026-11-05 v0.6.1->v0.7.0] c = dict(counts(p, scene, pass_, starts=ctx["starts"]))
        # added 2026-11-05 v0.7.0: the continuation reference as the build sends it. The model counts it by the same
        # rule, but a pass whose text uses fixed reference numbers, or whose guide pictures named in the text take the
        # room, leaves it out (prompt.build_pass); then the pass counts as in v0.6.1.
        mode = ctx["start_mode"].get(scene["id"])
        c = dict(counts(p, scene, pass_, starts=ctx["starts"], mode=mode))
        sent = next((x for x in b["images"] + b["videos"] if x.get("continuation")), None)
        kind = "" if not sent else "picture" if sent in b["images"] else "video_audio" if sent["soundtrack"] else "video"
        if c.get("continuation", "") != kind:
            c = dict(counts(p, scene, pass_, starts=ctx["starts"], mode=mode, continuation=False))
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
    """added 2026-11-05 v0.7.0"""
    return {"#000000": "black", "#ffffff": "white"}.get(str(c or "").lower(), str(c or "black"))


def _merge_issues(p, i, s, name, ctx, locked, scene_ids):
    """added 2026-11-05 v0.7.0: problems with how scene i sits in the cut (scene.merge): a fade out on a scene the
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
    """added 2026-11-05 v0.8.0 (Agent V): an info line for a long scene with overlap seams and no shot cuts: each
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


# ---- added 2026-11-05 v0.8.0 (Agent P, contract P1): dialogue length, per-pass sections ----------------------------

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


# [OLD 2026-11-03 v0.5.1->v0.6.0] def lint_project(p, plans, builds, asset_exists):
#     idx = project_index(p)
#     assets, cast = idx["assets"], idx["cast"]
#     issues = []
#     depth = continuation_depth(p)
#     reanchor = int(p["global"]["continuity"]["reanchor_after"])
#
#     for a in p["assets"]:
#         if not a.get("file") or not asset_exists(a):
#             issues.append(_issue("error", "{} ({}) file is missing".format(a["code"], a["name"] or a["file"])))
# [/OLD]
def lint_project(p, plans, builds, asset_exists, ctx=None):
    """ctx: prompt.prepare(p), shared with build_pass (added 2026-11-03 v0.6.0)."""
    ctx = ctx if ctx is not None and ctx.get("project") is p else _prompt.prepare(p)
    idx = ctx["index"]
    assets, cast = idx["assets"], idx["cast"]
    issues = []
    depth = ctx["depth"]
    reanchor = int(p["global"]["continuity"]["reanchor_after"])

    # added 2026-11-03 v0.6.0: a missing file is an error on every scene that sends it (so pre-flight stops that
    # scene before any GPU work); the project-wide line is left for files no scene uses
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

    # [OLD 2026-11-03 v0.4.3->v0.5.0] score = p["global"]["merge"]["score"].get("asset")
    # [OLD 2026-11-03 v0.4.3->v0.5.0] if score and score not in assets:
    # [OLD 2026-11-03 v0.4.3->v0.5.0]     issues.append(_issue("warn", "Merge score track asset no longer exists"))
    # added 2026-11-03 v0.5.0: soundtrack tracks replace the merge score
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
    # [OLD 2026-11-05 v0.6.1->v0.7.0] one line for the project, from scene.transition / Global -> Merge (now per scene,
    # from scene.merge, in _merge_issues)
    # if soundtrack.locked(p):
    #     hard = [(s.get("transition") or {}).get("mode") or p["global"]["merge"]["hard_cut"]
    #             for i, s in enumerate(p["scenes"]) if i > 0 and s["start"]["mode"] == "fresh"]
    #     if any(h in ("crossfade", "dip") for h in hard):
    #         issues.append(_issue("info", "Crossfades and dips play as a dip through black inside the scenes, so the "
    #                                      "soundtrack keeps its timing"))
    #     # the Merge card says that scenes not rendered yet become slates; as an issue it showed on every project
    # [/OLD]
    locked = soundtrack.locked(p)  # added 2026-11-05 v0.7.0
    scene_ids = {s["id"] for s in p["scenes"]}  # added 2026-11-05 v0.7.0

    for i, s in enumerate(p["scenes"]):
        sid = s["id"]
        name = "{:02d} {}".format(i + 1, s["title"])
        d = float(s["duration"])
        plan = plans[sid]
        if d <= 0:
            issues.append(_issue("error", "{}: duration must be above 0".format(name), sid))
        if i == 0 and s["start"]["mode"] != "fresh":
            issues.append(_issue("info", "{}: the first scene always starts fresh".format(name), sid))
        # added 2026-11-12 v0.12.0: a pose reference goes out only with a picture and a character of this scene
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
        # added 2026-11-12 v0.14.0: the clip of a video or audio reference (From / To) must lie inside its asset
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
        # added 2026-11-08 v0.11.0: a prop that is part of a character is left out of a scene its character is not in
        if hasattr(_model, "scene_people"):
            for part, owner in _model.scene_people(p, s, idx)[1]:
                issues.append(_issue("warn", "{}: {} is part of {}, who is not in this scene, so it is left out (add {} "
                                             "to the scene, or clear its Part of)".format(name, part["name"], owner["name"],
                                                                                       owner["name"]), sid))
        if plan["kind"] == "long":
            issues.append(_issue("info", "{}: split into {} passes".format(name, len(plan["passes"])), sid))
            seam_hint = _cut_seam_hint(p, s, plan, name)  # added 2026-11-05 v0.8.0 (Agent V)
            if seam_hint:
                issues.append(_issue("info", seam_hint, sid))
        if plan["kind"] == "short":
            issues.append(_issue("info", "{}: rendered as {} frames and trimmed to {:.2f} s".format(
                name, spec.MIN_PASS_FRAMES, d), sid))
        if depth.get(sid, 0) > reanchor and s["start"]["mode"] == "tail":
            issues.append(_issue("info", "{}: {} chained continuations, so it continues from the last frame only (re-anchor rule)".format(
                name, depth[sid]), sid))
        # added 2026-11-03 v0.6.0: a tail next to a scene shorter than 5 frames starts from the last frame too
        elif i > 0 and s["start"]["mode"] == "tail" and ctx["start_mode"].get(sid) == "last_frame":
            issues.append(_issue("info", "{}: it or the scene before is shorter than 5 frames, so it continues from the "
                                         "last frame only".format(name), sid))
        overlap = _tail_overlap(p, i, plan) if i > 0 else 0.0  # added 2026-11-03 v0.6.0

        for sh in s["shots"]:
            if float(sh["t"]) >= d:
                issues.append(_issue("error", "{}: a shot starts at {:.2f} s, after the scene ends".format(name, float(sh["t"])), sid))
            # added 2026-11-03 v0.6.0
            elif float(sh["t"]) < 0:
                issues.append(_issue("warn", "{}: a shot starts at {:.2f} s, before the scene, so it starts at 0 s".format(
                    name, float(sh["t"])), sid))
            elif 0 < float(sh["t"]) < overlap - 1e-6:
                issues.append(_issue("warn", "{}: a shot starts at {:.2f} s, inside the {:.2f} s tail overlap that the "
                                             "cut trims away; move it to {:.2f} s or later".format(
                                                 name, float(sh["t"]), overlap, overlap), sid))
        spoken = {x["id"] for pass_ in plan["passes"] for x in pass_["dialogue"]}  # added 2026-11-03 v0.6.0
        for line in s["dialogue"]:
            t = float(line["t"])
            if t >= d:
                issues.append(_issue("error", "{}: a dialogue line at {:.2f} s is after the scene ends".format(name, t), sid))
            # added 2026-11-03 v0.6.0: lines before the scene, inside the trimmed tail overlap, or left out of every pass
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
        issues += _dialogue_span_issues(s, plan, name)  # added 2026-11-05 v0.8.0: past a pass seam or the scene's end
        issues += _pass_text_issues(p, s, plan, name)  # added 2026-11-05 v0.8.0: per-pass sections (P1)

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
        issues += _merge_issues(p, i, s, name, ctx, locked, scene_ids)  # added 2026-11-05 v0.7.0: scene.merge

        for entry in s["cast"]:
            c = cast.get(entry["id"])
            if not c:
                issues.append(_issue("error", "{}: a cast member was deleted".format(name), sid))
            elif c["kind"] == "character" and not c["anchors"]:
                issues.append(_issue("warn", "{}: {} has no anchor pictures, so identity is not locked".format(name, c["name"]), sid))

        # added 2026-11-03 v0.6.0: files this scene sends that are missing (an error here stops the scene before rendering)
        sent = set()
        for b in builds[sid]:
            sent |= _sent_assets(b)
        for aid in sorted(sent, key=lambda x: assets[x]["code"] if x in assets else x):
            a = assets.get(aid)
            if a and not exists(a):
                issues.append(_issue("error", "{}: {} ({}) file is missing".format(name, a["code"], a["name"] or a["file"]), sid))
        # added 2026-11-03 v0.6.0: a prompt written for a pass the scene no longer has
        n_passes = len(plan["passes"])
        for k, text in sorted((s["prompt"].get("pass_prompts") or {}).items()):
            if isinstance(text, str) and text.strip() and (not str(k).isdigit() or not 1 <= int(k) <= n_passes):
                issues.append(_issue("warn", "{}: the prompt written for pass {} is not used, because the scene has {} "
                                             "pass{} now".format(name, k, n_passes, "es" if n_passes > 1 else ""), sid))
        # added 2026-11-03 v0.6.0: what the prompt builder says about tags and written shot lines, once per scene
        said = {}
        for b, pass_ in zip(builds[sid], plan["passes"]):
            for x in b.get("issues") or []:
                said.setdefault((x["level"], x["message"]), []).append(pass_["index"])
        for (level, message), where_ in said.items():
            issues.append(_issue(level, "{}: {}".format(_passes_label(name, where_, n_passes), message), sid))

        for b, pass_ in zip(builds[sid], plan["passes"]):
            where = name if len(plan["passes"]) == 1 else "{} pass {}".format(name, pass_["index"])
            # [OLD 2026-11-03 v0.5.1->v0.6.0] every unresolved tag was an error here; build_pass's issues say why each one did not resolve
            # for tag in b["unknown"]:
            #     issues.append(_issue("error", "{}: {} does not match an asset or cast member in this scene".format(where, tag), sid))
            # [/OLD]
            # [OLD 2026-11-03 v0.5.1->v0.6.0] counted from the build: a video's own sound took no audio slot (see _media_counts)
            # n_img, n_vid, n_aud = len(b["images"]), len(b["videos"]), len(b["audios"])
            # if n_img > spec.MAX_REF_IMAGES:
            #     issues.append(_issue("warn", "{}: {} pictures (H3 is trained on up to 9)".format(where, n_img), sid))
            # if n_vid > spec.MAX_REF_VIDEOS:
            #     issues.append(_issue("warn", "{}: {} reference videos (up to 3)".format(where, n_vid), sid))
            # if n_aud > spec.MAX_REF_AUDIOS:
            #     issues.append(_issue("warn", "{}: {} reference audio clips (up to 3)".format(where, n_aud), sid))
            # if n_img + n_vid + n_aud > spec.MAX_REF_FILES:
            #     issues.append(_issue("warn", "{}: {} reference files (up to 12)".format(where, n_img + n_vid + n_aud), sid))
            # [/OLD]
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
            # added 2026-11-03 v0.6.0: a guide clip has to fit its pass. MiniMaxH3AddGuide refused one mid-run; the
            # renderer now fits it (render.fit_clip: a last-frame clip ends on the last frame, any other is shortened
            # to the frames left), so this says how much of the clip is used and how to keep all of it
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
            # [OLD 2026-11-03 v0.4.3->v0.5.0] for kind, items in (("video", [assets[v["asset"]] for v in b["videos"]]),
            # [OLD 2026-11-03 v0.4.3->v0.5.0]                     ("audio", [assets[x["asset"]] for x in b["audios"]])):
            # added 2026-11-03 v0.5.0: the soundtrack segment counts as an audio ref of its own length
            # [OLD 2026-11-12 v0.13.1->v0.14.0] audio_items = [{"code": "soundtrack", "duration": x["song"]["length"]} if x.get("song") else assets[x["asset"]]
            # [OLD 2026-11-12 v0.13.1->v0.14.0]                for x in b["audios"]]
            # added 2026-11-12 v0.14.0: a trimmed clip by its own length
            audio_items = [{"code": "soundtrack", "duration": x["song"]["length"]} if x.get("song") else
                           {"code": assets[x["asset"]]["code"] + " (clip)", "duration": x["seconds"] or 0} if "seconds" in x
                           else assets[x["asset"]] for x in b["audios"]]
            # added 2026-11-05 v0.7.0: the continuation clip (no asset) by its length
            video_items = [{"code": _prompt.CONT_WHAT.get(v.get("source"), "the continuation clip"),
                            "duration": float(v.get("frames") or 0) / spec.FPS} if v.get("continuation")
                           # [OLD 2026-11-12 v0.13.1->v0.14.0] else assets[v["asset"]] for v in b["videos"]]
                           else {"code": assets[v["asset"]]["code"] + " (clip)", "duration": v["seconds"] or 0}
                           if "seconds" in v else assets[v["asset"]] for v in b["videos"]]  # added 2026-11-12 v0.14.0
            # [OLD 2026-11-05 v0.6.1->v0.7.0] for kind, items in (("video", [assets[v["asset"]] for v in b["videos"]]),
            for kind, items in (("video", video_items),
                                ("audio", audio_items)):
                total = 0.0
                for a in items:
                    dur = float(a.get("duration") or 0)
                    total += dur
                    if dur and not (spec.REF_MEDIA_MIN_SECONDS <= dur <= spec.REF_MEDIA_MAX_SECONDS):
                        issues.append(_issue("warn", "{}: {} is {:.1f} s (H3 {} refs are 2-15 s)".format(where, a["code"], dur, kind), sid))
                # [OLD 2026-11-03 v0.5.1->v0.6.0] totals moved up (_media_counts: a video's own sound counts as audio)
                # if total > spec.REF_MEDIA_TOTAL_SECONDS:
                #     issues.append(_issue("warn", "{}: {} refs total {:.1f} s (max 15 s)".format(where, kind, total), sid))
                # [/OLD]
            if s["prompt"]["mode"] == "raw":
                text = (s["prompt"]["pass_prompts"] or {}).get(str(pass_["index"])) or s["prompt"]["raw"]
                for img in b["images"]:
                    for aid in img["assets"]:
                        code = "@" + assets[aid]["code"]
                        if not img["cast"] and code.lower() not in text.lower():
                            issues.append(_issue("info", "{}: {} is attached but never named in the prompt".format(where, code), sid))
            # added 2026-11-02 v0.2.0: hints from MiniMax's Ref2VA prompt guide (ref-en.txt)
            elif not (s["prompt"]["pass_prompts"] or {}).get(str(pass_["index"]), "").strip():
                desc = b["prompt"].split("detailed_description:\n", 1)[-1].split("\n\noverall_soundscape:", 1)[0]
                words = len(desc.split())
                if words < 120:
                    issues.append(_issue("info", "{}: detailed_description has {} words; H3's guide aims for 350-500 "
                                                 "(Rewrite can expand it)".format(where, words), sid))
        if s["prompt"]["mode"] != "raw":
            # [OLD 2026-11-05 v0.7.0->v0.8.0] the scene's soundscape only (a pass may have its own now)
            # if not s["prompt"]["sections"]["overall_soundscape"].strip():
            #     issues.append(_issue("info", "{}: overall_soundscape is empty, so H3 gets N/A, which its guide "
            #                                  "reserves for complete silence".format(name), sid))
            # [/OLD]
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
                    # added 2026-11-02 v0.3.4: a character with no description and no described anchor
                    c = idx["cast"].get(subj.get("cast") or "")
                    if c and c["id"] not in described and not cast_description(c, assets)[0]:
                        described.add(c["id"])
                        issues.append(_issue("info", "{}: {} has no description and none of its anchor pictures has "
                                                     "one, so its subject line is only the name (Cast tab or Assets "
                                                     "tab: Describe with LLM)".format(name, c["name"]), sid))
    issues += _voice_issues(p, plans, assets)  # added 2026-11-06 v0.10.0
    return issues


# added 2026-11-06 v0.10.0: H3 picks a voice for every generation; a character heard in more than one pass needs a
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
