"""Build ffmpeg segment lists for long-scene stitching and the final merge.

added 2026-11-03 v0.6.0: merge_project registers a "merge" job (one per project; a second raises merge.MergeBusy),
can be cancelled (merge.MergeCancelled, partial files removed), makes draft and range cuts, audio stems with an
EBU R128 report, and puts the soundtrack and markers into the OTIO and FCPXML files. cut_plan trims and times each
scene by how it really starts (the plan's start_mode and first-pass overlap, see model.effective_start).
"""

import json  # added 2026-11-03 v0.6.0
import logging  # added 2026-11-05 v0.7.0: merge warnings
import os
import re  # added 2026-11-03 v0.6.0
import shutil  # added 2026-11-03 v0.6.0
import sys  # added 2026-11-03 v0.6.0
import time

from . import cache, jobs  # added 2026-11-03 v0.6.0
from . import merge, spec
# [OLD 2026-11-03 v0.4.3->v0.5.0] from .model import project_index
from . import soundtrack  # added 2026-11-03 v0.5.0
from . import model  # added 2026-11-06 v0.10.0: dialogue_seconds (speech_timed)
from .model import project_index, scene_starts

log = logging.getLogger("reelwright")  # added 2026-11-05 v0.7.0


# [OLD 2026-11-05 v0.7.0->v0.8.0] def pass_segments(plan, pass_files, crossfade_frames):
def pass_segments(plan, pass_files, crossfade_frames, carry_audio=True):
    """Segments that stitch a scene's pass files into the scene video.
    added 2026-11-05 v0.8.0: carry_audio False (Global -> Long scenes): the pass after an overlap seam got no sound
    guide, so its sound is not the same as the pass before's inside the overlap; its sound starts at the overlap's
    first frame (merge's audio_lead_frames) and crossfades with the pass before's over the whole overlap. The picture
    is stitched as before."""
    segs = []
    for x, path in zip(plan["passes"], pass_files):
        seg = {"path": path, "in": x["keep_in"], "out": x["keep_out"], "has_audio": True, "join": "cut", "dur": 0.0}
        if x["index"] == 1:
            seg["join"] = "first"
        elif x["seam_before"] == "overlap":
            cf = min(int(crossfade_frames), x["overlap_frames"])
            seg["in"] = (x["overlap_frames"] - cf) / spec.FPS
            seg["join"] = "xfade" if cf else "cut"
            seg["dur"] = cf / spec.FPS
            if not cf:
                seg["in"] = x["overlap_frames"] / spec.FPS
            if not carry_audio:  # added 2026-11-05 v0.8.0
                seg["audio_lead_frames"] = int(x["overlap_frames"]) - cf
        segs.append(seg)
    return segs


def pick_take(entry, use):
    takes = entry.get("takes") or []
    if use == "latest":
        return takes[-1] if takes else None
    return next((t for t in takes if t["id"] == entry.get("starred")), None) or (takes[-1] if takes else None)


# [OLD 2026-11-03 v0.5.1->v0.6.0] trimmed and timed scenes by the declared start mode and the take's overlap: a
# re-anchored tail (guided by the last frame only) was still trimmed as a tail; no range
# def cut_plan(result, store):
#     """Segments + side-file entries for the merge, from the analysis result."""
#     p = result["project"]
#     m = p["global"]["merge"]
#     cf_cont = int(p["global"]["long"]["crossfade_frames"])
#     names = {c["id"]: c["name"] for c in p["cast"]}
#     segments, entries, skipped = [], [], []
#     prev_included = None
#     # added 2026-11-03 v0.5.0: with a soundtrack every scene must end where the timeline says (scene_starts), so
#     # missing scenes become slates, crossfades and dips stop overlapping the scenes, and takes are fitted
#     locked = soundtrack.locked(p)
#     cut_start = scene_starts(p)[0] if locked else {}
#
#     def cut_end(sc):
#         return cut_start[sc["id"]] + float(sc["duration"])
#
#     for i, s in enumerate(p["scenes"]):
#         sr = result["scenes"][s["id"]]
#         take = pick_take(sr, m["use"])
#         path = store.output_path(take["files"]["video"]) if take and take.get("files", {}).get("video") else None
#         if not path or not os.path.isfile(path):
#             if m["missing"] == "block":
#                 raise merge.MergeError("{:02d} {} has no finished take".format(i + 1, s["title"]))
#             if locked:  # added 2026-11-03 v0.5.0
#                 gap = cut_end(s) - merge.plan_timeline(segments)[1]
#                 if gap > 0.5 / spec.FPS:
#                     segments.append({"path": None, "in": 0.0, "out": gap, "join": "first" if not segments else "cut",
#                                      "dur": 0.0})
#                     entries.append(None)
#                 skipped.append(s["id"])
#                 prev_included = i
#                 continue
#             if m["missing"] == "slate":
#                 segments.append({"path": None, "in": 0.0, "out": float(s["duration"]), "join": "cut", "dur": 0.0})
#                 entries.append(None)
#             skipped.append(s["id"])
#             prev_included = None if m["missing"] != "slate" else i
#             continue
#         info = merge.probe(path)
#         length = float(take.get("seconds") or info["duration"])
#         seg = {"path": path, "in": 0.0, "out": length, "has_audio": info["has_audio"], "join": "cut", "dur": 0.0,
#                "scene_id": s["id"]}
#         mode = s["start"]["mode"] if i > 0 else "fresh"
#         overlap = int(take.get("overlap_frames") or 0)
#         adjacent = prev_included == i - 1 and i > 0
#         if not segments:
#             seg["join"] = "first"
#             if mode == "tail" and overlap:
#                 seg["in"] = overlap / spec.FPS
#         elif mode == "tail" and overlap:
#             if adjacent:
#                 cf = min(cf_cont, overlap)
#                 seg["in"] = (overlap - cf) / spec.FPS
#                 seg["join"] = "xfade" if cf else "cut"
#                 seg["dur"] = cf / spec.FPS
#             else:
#                 seg["in"] = overlap / spec.FPS
#         elif mode == "last_frame" and adjacent:
#             seg["in"] = 1 / spec.FPS
#         else:
#             # [OLD 2026-11-02 v0.2.2->v0.3.0] every hard cut used Global -> Merge; now each scene can choose its own
#             # hard = m["hard_cut"]
#             # if hard in ("crossfade", "dip"):
#             #     prev_len = segments[-1]["out"] - segments[-1]["in"]
#             #     d = min(int(m["transition_frames"]) / spec.FPS, prev_len / 2, (length - seg["in"]) / 2)
#             # [/OLD]
#             tr = s.get("transition") or {}
#             hard = tr.get("mode") or m["hard_cut"]
#             frames = tr.get("frames") if tr.get("frames") is not None else m["transition_frames"]
#             if hard in ("crossfade", "dip"):
#                 prev_len = segments[-1]["out"] - segments[-1]["in"]
#                 d = min(int(frames) / spec.FPS, prev_len / 2, (length - seg["in"]) / 2)
#                 # [OLD 2026-11-03 v0.4.3->v0.5.0] if d > 0:
#                 if d > 0 and locked:  # added 2026-11-03 v0.5.0: a dip through black that keeps the timing
#                     segments[-1]["vfade_out"] = d / 2
#                     seg["vfade_in"] = d / 2
#                 elif d > 0:
#                     seg["join"] = "xfade" if hard == "crossfade" else "dip"
#                     seg["dur"] = d
#         afade = (s.get("transition") or {}).get("audio_fade_frames")
#         if afade is not None:
#             seg["fade"] = int(afade) / spec.FPS  # added 2026-11-02 v0.3.0: per-scene audio fade at its cut
#         gap = 0.0
#         if locked:  # added 2026-11-03 v0.5.0: a take of another length (rendered before the scene changed) is fitted
#             at = merge.plan_timeline(segments + [seg])[0][-1]
#             need = cut_end(s) - at
#             if need < seg["out"] - seg["in"] - 0.5 / spec.FPS:
#                 seg["out"] = seg["in"] + max(1.0 / spec.FPS, need)
#             elif need > seg["out"] - seg["in"] + 0.5 / spec.FPS:
#                 gap = need - (seg["out"] - seg["in"])
#         segments.append(seg)
#         lines = [{"t": float(d["t"]), "speaker": names.get(d["speaker"], ""), "text": d["text"]} for d in s["dialogue"]]
#         entries.append({"scene_id": s["id"], "title": "{:02d} {}".format(i + 1, s["title"]), "path": path,
#                         "src_in": seg["in"], "src_out": seg["out"], "src_len": length, "dialogue": lines})
#         if gap:  # added 2026-11-03 v0.5.0: a take shorter than its scene is followed by a slate
#             segments.append({"path": None, "in": 0.0, "out": gap, "join": "cut", "dur": 0.0})
#             entries.append(None)
#         prev_included = i
#     return segments, entries, skipped
# [/OLD]
def scene_range(p, rng):
    """added 2026-11-03 v0.6.0: (first, last) scene indexes of a range merge; the whole film for None/empty."""
    n = len(p["scenes"])
    if not rng:
        return 0, n - 1
    if not isinstance(rng, (list, tuple)) or len(rng) != 2 or not all(isinstance(x, str) for x in rng):
        raise merge.MergeError("range must be [first scene id, last scene id]")
    ids = {s["id"]: k for k, s in enumerate(p["scenes"])}
    if rng[0] not in ids or rng[1] not in ids:
        raise merge.MergeError("the range names a scene that is not in the project")
    return tuple(sorted((ids[rng[0]], ids[rng[1]])))


def scene_join(result, p, i):
    """added 2026-11-03 v0.6.0: (start mode, overlap frames) scene i is cut with: how it really starts (the plan's
    start_mode = model.effective_start: a re-anchored tail, or one under 5 frames, is a last_frame start) and the
    plan's first-pass overlap (capped by the scene's own length and the one before)."""
    s = p["scenes"][i]
    plan = (result["scenes"].get(s["id"]) or {}).get("plan") or {}
    mode = plan.get("start_mode")
    if mode not in ("fresh", "last_frame", "tail"):
        from . import model
        eff = getattr(model, "effective_start", None)
        mode = eff(p, i) if eff else (s["start"]["mode"] if i > 0 else "fresh")
    passes = plan.get("passes") or []
    overlap = int(passes[0].get("overlap_frames") or 0) if passes and mode == "tail" else 0
    if mode == "tail" and overlap < 5:
        mode, overlap = "last_frame", 0
    return mode, overlap


# ---- scene.merge: how each scene sits in the cut (added 2026-11-05 v0.7.0) -----------------------------------------

def scene_merge(s, p=None):
    """The scene's merge settings (model.default_merge's keys); a scene that was not normalised gets them the way
    model.normalize_project would (built from its v0.6 transition and p's Global -> Merge)."""
    mg = s.get("merge")
    if isinstance(mg, dict) and "transition" in mg and isinstance(mg.get("fade_in"), dict):
        return mg
    from . import model
    return model.normalize_project({"scenes": [s], "global": (p or {}).get("global")})["scenes"][0]["merge"]


def _scene_look(seg, mg):
    """The scene's own fades, sound and eq on its segment (merge.build_command reads these keys)."""
    F = spec.FPS
    if mg["fade_in"]["frames"]:
        seg["edge_in"] = dict(mg["fade_in"])
    if mg["fade_out"]["frames"]:
        seg["edge_out"] = dict(mg["fade_out"])
    if mg["audio_fade_in"]:
        seg["afade_in"] = int(mg["audio_fade_in"]) / F
    if mg["audio_fade_out"]:
        seg["afade_out"] = int(mg["audio_fade_out"]) / F
    if mg["mute"]:
        seg["mute"] = True
    elif float(mg["volume_db"]):
        seg["volume_db"] = float(mg["volume_db"])
    look = (float(mg["brightness"]), float(mg["contrast"]), float(mg["saturation"]))
    if look != (0.0, 1.0, 1.0):
        seg["eq"] = look


def cut_plan(result, store, options=None, info=None):
    """Segments + side-file entries for the merge, from the analysis result.
    added 2026-11-03 v0.6.0: options {range: [from_sid, to_sid]} merges only those scenes. `info` (a dict) receives
    {offset: film time of the cut's first frame (with a soundtrack), first, last: scene indexes}.
    added 2026-11-03 v0.6.0 review: offset is set with or without a soundtrack (scene_starts of the first scene in
    the cut + what is trimmed off its start), on the frame grid. With a soundtrack every scene ends on the film frame
    round((start + duration) * 24); a take one frame short holds its last frame, a slate is two frames or more. A
    scene with no frame of its own (all of it repeats the scene before) is left out.
    added 2026-11-05 v0.7.0: each scene's scene.merge sets how it joins the scene before (any transition type, its
    direction, length and dip colour; only where it does not continue that scene) and its own fades, sound level,
    mute and eq (_scene_look). With a soundtrack setting the timing an overlapping transition becomes a dip through
    the scene's colour inside both scenes, so nothing moves. Colour match is set later (color_match)."""
    p = result["project"]
    m = p["global"]["merge"]
    cf_cont = int(p["global"]["long"]["crossfade_frames"])
    names = {c["id"]: c["name"] for c in p["cast"]}
    lo, hi = scene_range(p, (options or {}).get("range"))
    segments, entries, skipped = [], [], []
    prev_included = None
    # added 2026-11-03 v0.5.0: with a soundtrack every scene must end where the timeline says (scene_starts), so
    # missing scenes become slates, crossfades and dips stop overlapping the scenes, and takes are fitted
    locked = soundtrack.locked(p)
    # [OLD 2026-11-03 v0.6.0 review] the film times were only known with a soundtrack, so a range merge without one
    # kept offset 0 and its markers stayed at film time
    # cut_start = scene_starts(p)[0] if locked else {}
    # [/OLD]
    film_start = scene_starts(p)[0]  # added 2026-11-03 v0.6.0 review: for the cut's offset with or without a soundtrack
    cut_start = film_start if locked else {}
    offset = [None]  # film time where the cut starts (later than 0 for a range)
    # added 2026-11-03 v0.6.0 review: the cut is planned on the film's frame grid: its first frame is film frame
    # round(offset * 24) and a scene ends at film frame round((start + duration) * 24), counted from there
    offset_f = [0]
    F = spec.FPS

    def set_offset(t):  # added 2026-11-03 v0.6.0 review
        if offset[0] is None:
            offset_f[0] = merge.frame_index(t)
            offset[0] = offset_f[0] / F

    # [OLD 2026-11-03 v0.6.0 review] exact seconds: sub-frame slates and fitting
    # def cut_end(sc):
    #     return cut_start[sc["id"]] + float(sc["duration"]) - (offset[0] or 0.0)
    # [/OLD]
    def cut_end_f(sc):
        """added 2026-11-03 v0.6.0 review: the cut's frame where scene sc must end (soundtrack-locked)."""
        return merge.frame_index(cut_start[sc["id"]] + float(sc["duration"])) - offset_f[0]

    for i, s in enumerate(p["scenes"]):
        if i < lo or i > hi:
            continue
        sr = result["scenes"][s["id"]]
        mg = scene_merge(s, p)  # added 2026-11-05 v0.7.0
        take = pick_take(sr, m["use"])
        path = store.output_path(take["files"]["video"]) if take and take.get("files", {}).get("video") else None
        if not path or not os.path.isfile(path):
            if m["missing"] == "block":
                raise merge.MergeError("{:02d} {} has no finished take".format(i + 1, s["title"]))
            if locked:
                # [OLD 2026-11-03 v0.6.0 review] a gap of 0.6 frames became a slate, drawn as a whole dark frame
                # if offset[0] is None:
                #     offset[0] = cut_start[s["id"]]
                # gap = cut_end(s) - merge.plan_timeline(segments)[1]
                # if gap > 0.5 / spec.FPS:
                #     segments.append({"path": None, "in": 0.0, "out": gap, "join": "first" if not segments else "cut",
                #                      "dur": 0.0})
                # [/OLD]
                # added 2026-11-03 v0.6.0 review: a slate of whole frames, only when at least one frame is missing
                set_offset(cut_start[s["id"]])
                gap_f = cut_end_f(s) - merge.frame_timeline(segments)[1]
                if gap_f >= 1:
                    # [OLD 2026-11-05 v0.6.1->v0.7.0] segments.append({"path": None, "in": 0.0, "out": gap_f / F,
                    # [OLD 2026-11-05 v0.6.1->v0.7.0]                  "join": "first" if not segments else "cut", "dur": 0.0})
                    # added 2026-11-05 v0.7.0: the slate's sound fade at its cut is the missing scene's (scene.merge)
                    segments.append({"path": None, "in": 0.0, "out": gap_f / F,
                                     "join": "first" if not segments else "cut", "dur": 0.0,
                                     "fade": int(mg["audio_frames"]) / F})
                    entries.append(None)
                skipped.append(s["id"])
                prev_included = i
                continue
            if m["missing"] == "slate":
                if not segments:  # added 2026-11-03 v0.6.0 review: the cut starts with this scene's slate
                    set_offset(film_start[s["id"]])
                # [OLD 2026-11-05 v0.6.1->v0.7.0] segments.append({"path": None, "in": 0.0, "out": float(s["duration"]),
                # [OLD 2026-11-05 v0.6.1->v0.7.0]                  "join": "first" if not segments else "cut", "dur": 0.0})
                # added 2026-11-05 v0.7.0: the slate's sound fade at its cut is the missing scene's (scene.merge)
                segments.append({"path": None, "in": 0.0, "out": float(s["duration"]),
                                 "join": "first" if not segments else "cut", "dur": 0.0,
                                 "fade": int(mg["audio_frames"]) / F})
                entries.append(None)
            skipped.append(s["id"])
            prev_included = None if m["missing"] != "slate" else i
            continue
        info_ = merge.probe(path)
        length = float(take.get("seconds") or info_["duration"])
        seg = {"path": path, "in": 0.0, "out": length, "has_audio": info_["has_audio"], "join": "cut", "dur": 0.0,
               "scene_id": s["id"]}
        mode, overlap = scene_join(result, p, i)
        adjacent = prev_included == i - 1 and i > 0
        if not segments:
            seg["join"] = "first"
            if mode == "tail" and overlap:
                seg["in"] = overlap / spec.FPS
        elif mode == "tail" and overlap:
            if adjacent:
                cf = min(cf_cont, overlap)
                seg["in"] = (overlap - cf) / spec.FPS
                seg["join"] = "xfade" if cf else "cut"
                seg["dur"] = cf / spec.FPS
            else:
                seg["in"] = overlap / spec.FPS
        elif mode == "last_frame" and adjacent:
            seg["in"] = 1 / spec.FPS
        else:
            # [OLD 2026-11-05 v0.6.1->v0.7.0] the transition came from scene.transition or Global -> Merge (crossfade or
            # dip only), and the dip that keeps the timing was always through black
            # tr = s.get("transition") or {}
            # hard = tr.get("mode") or m["hard_cut"]
            # frames = tr.get("frames") if tr.get("frames") is not None else m["transition_frames"]
            # if hard in ("crossfade", "dip"):
            #     prev_len = segments[-1]["out"] - segments[-1]["in"]
            #     # [OLD 2026-11-03 v0.6.0 review] half of a scene's length could be half a frame
            #     # d = min(int(frames) / spec.FPS, prev_len / 2, (length - seg["in"]) / 2)
            #     # added 2026-11-03 v0.6.0 review: whole frames, at most half of either scene
            #     d = min(int(frames), merge.frame_index(prev_len) // 2, merge.frame_index(length - seg["in"]) // 2) / F
            #     if d > 0 and locked:  # a dip through black that keeps the timing
            #         segments[-1]["vfade_out"] = d / 2
            #         seg["vfade_in"] = d / 2
            #     elif d > 0:
            #         seg["join"] = "xfade" if hard == "crossfade" else "dip"
            #         seg["dur"] = d
            # [/OLD]
            # added 2026-11-05 v0.7.0: the scene's own transition (scene.merge), any xfade type. Whole frames, at most
            # half of either scene; with a soundtrack setting the timing, a dip through the scene's colour inside both
            hard, frames = mg["transition"], mg["frames"]
            if hard != "cut":
                prev_len = segments[-1]["out"] - segments[-1]["in"]
                d = min(int(frames), merge.frame_index(prev_len) // 2, merge.frame_index(length - seg["in"]) // 2) / F
                if d > 0 and locked:
                    segments[-1]["vfade_out"] = d / 2
                    segments[-1]["vfade_out_color"] = mg["color"]
                    seg["vfade_in"] = d / 2
                    seg["vfade_in_color"] = mg["color"]
                elif d > 0:
                    seg["join"] = "dip" if hard == "dip" else "xfade"
                    seg["transition"], expr = merge.xfade_transition(hard, mg["direction"], mg["color"])
                    if expr:
                        seg["transition_expr"] = expr
                    seg["dur"] = d
        # [OLD 2026-11-05 v0.6.1->v0.7.0] the sound's fade at a cut came from scene.transition or Global -> Merge
        # afade = (s.get("transition") or {}).get("audio_fade_frames")
        # if afade is not None:
        #     seg["fade"] = int(afade) / spec.FPS
        # [/OLD]
        seg["fade"] = int(mg["audio_frames"]) / F  # added 2026-11-05 v0.7.0: scene.merge, on every segment
        _scene_look(seg, mg)  # added 2026-11-05 v0.7.0
        # [OLD 2026-11-03 v0.6.0 review] a scene whose kept frames all repeat the scene before (a 1-frame scene with a
        # last-frame start) failed the whole merge
        # if seg["out"] - seg["in"] < 0.5 / spec.FPS:  # a take shorter than what is trimmed off it
        #     raise merge.MergeError("{:02d} {}: its take is shorter than the part that repeats the scene before".format(
        #         i + 1, s["title"]))
        # if locked and offset[0] is None:
        #     offset[0] = cut_start[s["id"]] + (seg["in"] if not segments else 0.0)
        # [/OLD]
        # added 2026-11-03 v0.6.0 review: no new frame to show -> the scene is left out (no slate, no error). Its frames
        # are the scene before's, so a scene continuing from it still joins that scene (when it was in the cut).
        if merge.frame_index(seg["out"] - seg["in"]) < 1:
            if adjacent:
                prev_included = i
            continue
        if not segments:  # added 2026-11-03 v0.6.0 review: with or without a soundtrack, film time of the first frame
            set_offset(film_start[s["id"]] + seg["in"])
        # [OLD 2026-11-03 v0.6.0 review] exact seconds: a take 0.2 frames short got a 0.2-frame slate (a dark frame)
        # gap = 0.0
        # if locked:  # a take of another length (rendered before the scene changed) is fitted
        #     at = merge.plan_timeline(segments + [seg])[0][-1]
        #     need = cut_end(s) - at
        #     if need < seg["out"] - seg["in"] - 0.5 / spec.FPS:
        #         seg["out"] = seg["in"] + max(1.0 / spec.FPS, need)
        #     elif need > seg["out"] - seg["in"] + 0.5 / spec.FPS:
        #         gap = need - (seg["out"] - seg["in"])
        # [/OLD]
        # added 2026-11-03 v0.6.0 review: fitted in whole frames. A take one frame short (the 0.2 frames a 7.3 s
        # scene's slot rounds up by) holds its last frame; a slate only fills two frames or more.
        gap_f = 0
        if locked:  # a take of another length (rendered before the scene changed) is fitted
            at_f = merge.frame_timeline(segments + [seg])[0][-1][0]
            need_f = cut_end_f(s) - at_f
            have_f = merge.frame_index(seg["out"] - seg["in"])
            if need_f < 1:  # its slot is already taken by the scenes before
                if adjacent:
                    prev_included = i
                if not segments:  # the cut starts with a later scene
                    offset[0] = None
                continue
            if need_f <= have_f + 1:
                seg["out"] = seg["in"] + need_f / F
            else:
                seg["out"] = seg["in"] + have_f / F
                gap_f = need_f - have_f
        segments.append(seg)
        # [OLD 2026-11-06 v0.8.0] lines = [{"t": float(d["t"]), "speaker": names.get(d["speaker"], ""), "text": d["text"]} for d in s["dialogue"]]
        # added 2026-11-06 v0.8.0: a line's own duration goes to the subtitles too
        lines = [{"t": float(d["t"]), "speaker": names.get(d["speaker"], ""), "text": d["text"], "duration": d.get("duration")}
                 for d in s["dialogue"]]
        # [OLD 2026-11-03 v0.6.0 review] src_out could be a held frame past the end of the file
        # entries.append({"scene_id": s["id"], "title": "{:02d} {}".format(i + 1, s["title"]), "path": path,
        #                 "src_in": seg["in"], "src_out": seg["out"], "src_len": length, "dialogue": lines})
        # [/OLD]
        # added 2026-11-03 v0.6.0 review: a held last frame is not in the file, so the side files end the clip there
        entries.append({"scene_id": s["id"], "title": "{:02d} {}".format(i + 1, s["title"]), "path": path,
                        "src_in": seg["in"], "src_out": min(seg["out"], max(seg["in"], length)), "src_len": length,
                        "dialogue": lines})
        # [OLD 2026-11-03 v0.6.0 review] slates of any fraction of a frame
        # if gap:  # a take shorter than its scene is followed by a slate
        #     segments.append({"path": None, "in": 0.0, "out": gap, "join": "cut", "dur": 0.0})
        # [/OLD]
        if gap_f:  # a take shorter than its scene is followed by a slate (added 2026-11-03 v0.6.0 review: whole frames)
            # [OLD 2026-11-05 v0.6.1->v0.7.0] segments.append({"path": None, "in": 0.0, "out": gap_f / F, "join": "cut", "dur": 0.0})
            # added 2026-11-05 v0.7.0: the sound fade into the slate is the scene's own (scene.merge)
            segments.append({"path": None, "in": 0.0, "out": gap_f / F, "join": "cut", "dur": 0.0,
                             "fade": int(mg["audio_frames"]) / F})
            entries.append(None)
        prev_included = i
    if segments and segments[0]["join"] != "first":
        segments[0]["join"] = "first"
    if info is not None:
        info.update(offset=offset[0] or 0.0, first=lo, last=hi)
    return segments, entries, skipped


def color_match(result, store, segments, cancel=None):
    """added 2026-11-05 v0.7.0: each scene's colour match (scene.merge.color_match) as its segment's "gain":
    previous = the mean colour of the scene before it in the cut, after that scene's own match (slates are passed
    over); scene = the mean colour of the chosen scene's take as rendered (its own match and eq not applied): its part
    in this cut, or, when a range merge leaves it out, its whole take. Gains follow merge.color_gains (0.8 .. 1.25 per
    channel). cancel() is called before each measurement (it may raise). Returns warnings: a reference scene that is
    gone or has no finished take (that scene is not colour matched)."""
    p = result["project"]
    use = p["global"]["merge"]["use"]
    by_id = {s["id"]: (k, s) for k, s in enumerate(p["scenes"])}
    in_cut = {}
    for seg in segments:
        if seg.get("path") and seg.get("scene_id"):
            in_cut.setdefault(seg["scene_id"], seg)
    memo, warnings = {}, []

    def mean(path, a, b):
        key = (path, round(float(a), 6), round(float(b), 6))
        if key not in memo:
            if cancel:
                cancel()
            memo[key] = merge.mean_rgb(path, a, b)
        return memo[key]

    def warn(text):
        if text not in warnings:
            warnings.append(text)

    def reference(sid):
        seg = in_cut.get(sid)
        if seg:
            return mean(seg["path"], seg["in"], seg["out"])
        take = pick_take(result["scenes"].get(sid) or {}, use)
        path = store.output_path(take["files"]["video"]) if take and (take.get("files") or {}).get("video") else None
        if not path or not os.path.isfile(path):
            return None
        return mean(path, 0.0, float(take.get("seconds") or merge.probe(path)["duration"]))

    prev = None
    for seg in segments:
        if not seg.get("path"):
            continue
        k, s = by_id.get(seg.get("scene_id"), (None, None))
        mg = scene_merge(s, p) if s else {}
        mode, target = mg.get("color_match", "off"), None
        if mode == "previous" and prev is not None:
            pm = mean(prev["path"], prev["in"], prev["out"])
            if pm:
                gain = prev.get("gain") or (1.0, 1.0, 1.0)
                target = [pm[c] * gain[c] for c in range(3)]
        elif mode == "scene" and mg.get("color_ref") != s["id"]:
            name = "{:02d} {}".format(k + 1, s["title"])
            ref = by_id.get(mg.get("color_ref"))
            if ref is None:
                warn("{}: its colour reference scene is not in the project, so it is not colour matched".format(name))
            else:
                target = reference(ref[1]["id"])
                if target is None:
                    warn("{}: {:02d} {}, its colour reference, has no finished take, so it is not colour matched".format(
                        name, ref[0] + 1, ref[1]["title"]))
        if target:
            own = mean(seg["path"], seg["in"], seg["out"])
            if own:
                seg["gain"] = merge.match_gain(target, own)
        prev = seg
    return warnings


# [OLD 2026-11-03 v0.5.1->v0.6.0] two merges of a project at once wrote the same cut; no cancel; a failed merge left
# its .chapters.txt behind; no draft, range, stems, soundtrack or markers in the side files
# def merge_project(result, store, progress=None):
#     p = result["project"]
#     m = p["global"]["merge"]
#     segments, entries, skipped = cut_plan(result, store)
#     if not any(s.get("path") for s in segments):
#         raise merge.MergeError("no scene has a finished take yet")
#     starts, total = merge.plan_timeline(segments)
#     real = []
#     for seg, e, st in zip(segments, entries, starts):
#         if e:
#             e["start"] = st
#             real.append(e)
#     if m["color_match"]:
#         ref_sid = m.get("color_ref_scene")
#         ref_index = next((k for k, s in enumerate(segments) if s.get("scene_id") == ref_sid), 0)
#         for seg, gain in zip(segments, merge.color_gains(segments, ref_index)):
#             seg["gain"] = gain
#     base = store.next_cut_path()
#     files = {"video": base + ".mp4"}
#     chapters = None
#     if m["chapters"]:
#         chapters = base + ".chapters.txt"
#         merge.write_chapters(real, total, chapters)
#         files["chapters"] = chapters
#     # [OLD 2026-11-03 v0.4.3->v0.5.0] score = None
#     # [OLD 2026-11-03 v0.4.3->v0.5.0] if m["score"].get("asset"):
#     # [OLD 2026-11-03 v0.4.3->v0.5.0]     a = project_index(p)["assets"].get(m["score"]["asset"])
#     # [OLD 2026-11-03 v0.4.3->v0.5.0]     if a and a.get("file"):
#     # [OLD 2026-11-03 v0.4.3->v0.5.0]         score = {"path": store.input_path(a["file"]), "volume_db": float(m["score"]["volume_db"]),
#     # [OLD 2026-11-03 v0.4.3->v0.5.0]                  "duck": bool(m["score"]["duck"])}
#     # added 2026-11-03 v0.5.0: the score is a soundtrack track now (model.normalize_project moves it)
#     tracks = []
#     for t in soundtrack.resolved(p):
#         if not t["mix"]:
#             continue
#         path = store.input_path(t["file"])
#         if not os.path.isfile(path):
#             raise merge.MergeError("soundtrack {} is missing: {}".format(t["code"], t["file"]))
#         tracks.append({"path": path, "start": t["start"], "in": t["in"], "length": t["length"],
#                        "volume_db": t["volume_db"], "fade_in": t["fade_in"], "fade_out": t["fade_out"],
#                        "duck": t["duck"], "loop": t["loop"]})
#     sa = m.get("scene_audio") or {"mix": False, "volume_db": -12.0}
#     w, h = p["global"]["output"]["width"], p["global"]["output"]["height"]
#     # [OLD 2026-11-03 v0.4.3->v0.5.0] merge.join(segments, files["video"], w, h, progress=progress, codec=m["codec"], crf=m["crf"],
#     # [OLD 2026-11-03 v0.4.3->v0.5.0]            audio_fade_frames=int(m["audio_fade_frames"]),
#     # [OLD 2026-11-03 v0.4.3->v0.5.0]            loudness=float(m["loudness"]) if m["normalize"] else None,
#     # [OLD 2026-11-03 v0.4.3->v0.5.0]            score=score, chapters_file=chapters)
#     merge.join(segments, files["video"], w, h, progress=progress, codec=m["codec"], crf=m["crf"],
#                audio_fade_frames=int(m["audio_fade_frames"]),
#                loudness=float(m["loudness"]) if m["normalize"] else None,
#                chapters_file=chapters, tracks=tracks,
#                scene_audio={"mix": bool(sa.get("mix")), "volume_db": float(sa.get("volume_db", -12.0))})
#     if m["subtitles"]:
#         files["srt"] = base + ".srt"
#         merge.write_srt(real, files["srt"])
#     if m["otio"]:
#         files["otio"] = base + ".otio"
#         merge.write_otio(p["name"], real, files["otio"])
#     if m["fcpxml"]:
#         files["fcpxml"] = base + ".fcpxml"
#         merge.write_fcpxml(p["name"], real, total, w, h, files["fcpxml"])
#     if m["bundle"]:
#         files["bundle"] = base + ".zip"
#         project_json = os.path.join(store.dir, "project.json")
#         merge.write_bundle(files["bundle"], {os.path.basename(v): v for k, v in files.items() if k != "bundle"} |
#                            {"project.json": project_json})
#     return {"files": {k: store.rel_output(v) for k, v in files.items()}, "duration": total,
#             "skipped": skipped, "created": int(time.time()), "soundtrack": len(tracks)}
# [/OLD]
def _comfy_interrupt():
    """added 2026-11-03 v0.6.0: ComfyUI's Stop, for merges that run inside the node (never imports ComfyUI)."""
    mm = sys.modules.get("comfy.model_management")
    if mm is not None and hasattr(mm, "throw_exception_if_processing_interrupted"):
        mm.throw_exception_if_processing_interrupted()


def _safe_name(x):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(x or "")).strip("_") or "track"


def _remove(path):
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        elif os.path.lexists(path):
            os.remove(path)
    except OSError:
        pass


def merge_project(result, store, progress=None, options=None, job_id=None):
    """Merge the project's takes into one cut (added 2026-11-03 v0.6.0: rewritten).

    Only one merge per project runs at a time: another raises merge.MergeBusy. The merge registers a "merge" job
    (jobs.exclusive) under `job_id` (or a new id); jobs.cancel(job id) stops ffmpeg and raises merge.MergeCancelled
    after removing every file this merge wrote. options:
      draft: bool   half size, x264 veryfast, CRF 28, file <slug>_cut_vN_draft.mp4
      range: [from_scene_id, to_scene_id]   only those scenes (file ..._sAA-BB.mp4)
      stems: bool   also <base>_stems/{scenes.wav, track_<id>.wav, mix.wav} and <base>_loudness.json (EBU R128)
      interruptible: bool   ComfyUI's Stop also stops it (default: True when job_id is None, as from the node)
    Returns {files, duration, skipped, created, soundtrack, job, draft, range, loudness?}."""
    o = dict(options or {})
    if "interruptible" not in o:
        o["interruptible"] = job_id is None
    try:
        with jobs.exclusive(store.slug, "merge", job_id) as job:
            return merge_with_job(result, store, job, progress, o)
    except jobs.Busy as e:
        raise merge.MergeBusy("another merge of this project is running; wait for it or cancel it") from e


# added 2026-11-06 v0.10.0: subtitles that follow the speech of the takes
def speech_timed(entries):
    """Copies of the merge entries whose dialogue lines are timed to the speech found in their take (speech.align):
    t = where the line's speech starts, duration = how long it lasts, in the take's time (= the scene's). A take whose
    sound can't be read, or that has no clear speech, keeps the planned times. Lines are matched within the part of the
    take that is in the cut (src_in .. src_out)."""
    from . import speech
    ff = merge.ffmpeg_bin()
    out = []
    for e in entries:
        lines = [d for d in e.get("dialogue") or [] if str(d.get("text") or "").strip()]
        if not lines or not e.get("path") or not ff:
            out.append(e)
            continue
        try:
            asked = [{"id": str(i), "t": float(d["t"]), "duration": model.dialogue_seconds(d)} for i, d in enumerate(lines)]
            timed = speech.timed_lines(e["path"], ff, asked, e["src_in"], e["src_out"])
        except (OSError, speech.SpeechError, ValueError) as err:
            log.warning("Reelwright: speech timing of %s skipped: %s", e.get("path"), err)
            out.append(e)
            continue
        by_id = {x["id"]: x for x in timed}
        new_lines = []
        for i, d in enumerate(lines):
            x = by_id.get(str(i))
            new_lines.append(dict(d, t=max(e["src_in"], x["t"]), duration=max(0.3, x["end"] - x["t"])) if x else d)
        out.append(dict(e, dialogue=new_lines))
    return out


def merge_with_job(result, store, job, progress=None, options=None):
    """merge_project's work, for a caller that already holds the project's "merge" job (jobs.exclusive), e.g. the
    /merge route, which registers it before autosaving and analysing so Cancel works from the start."""
    o = dict(options or {})
    p = result["project"]
    m = p["global"]["merge"]
    draft, stems = bool(o.get("draft")), bool(o.get("stems"))

    def cancel():
        if job.cancelled.is_set():
            return True
        if o.get("interruptible"):
            _comfy_interrupt()
        return False

    def check():
        if cancel():
            raise merge.MergeCancelled("merge cancelled")

    info = {}
    segments, entries, skipped = cut_plan(result, store, o, info)
    if not any(s.get("path") for s in segments):
        raise merge.MergeError("no scene has a finished take yet")
    starts, total = merge.plan_timeline(segments)
    real = []
    for seg, e, st in zip(segments, entries, starts):
        if e:
            e["start"] = st
            real.append(e)
    # [OLD 2026-11-05 v0.6.1->v0.7.0] one colour reference for the whole cut (Global -> Merge)
    # if m["color_match"]:
    #     ref_sid = m.get("color_ref_scene")
    #     ref_index = next((k for k, s in enumerate(segments) if s.get("scene_id") == ref_sid), 0)
    #     for seg, gain in zip(segments, merge.color_gains(segments, ref_index)):
    #         seg["gain"] = gain
    # [/OLD]
    warnings = color_match(result, store, segments, cancel=check)  # added 2026-11-05 v0.7.0: per scene
    for w_ in warnings:
        log.warning("Reelwright merge of %s: %s", store.slug, w_)
    check()
    offset = float(info.get("offset") or 0.0)
    suffix = ("_draft" if draft else "") + (
        "_s{:02d}-{:02d}".format(info["first"] + 1, info["last"] + 1) if o.get("range") else "")
    base = store.next_cut_path(suffix=suffix)
    made = []  # every file this merge writes, removed again when it fails or is cancelled
    files = {"video": base + ".mp4"}
    try:
        chapters = None
        if m["chapters"]:
            chapters = base + ".chapters.txt"
            made.append(chapters)
            merge.write_chapters(real, total, chapters)
            files["chapters"] = chapters
        # the soundtrack: film times; a range cut starts `offset` seconds into the film
        tracks, export = [], []
        for t in soundtrack.resolved(p):
            if not t["mix"]:
                continue
            path = store.input_path(t["file"])
            if not os.path.isfile(path):
                raise merge.MergeError("soundtrack {} is missing: {}".format(t["code"], t["file"]))
            tracks.append({"path": path, "start": t["start"] - offset, "in": t["in"], "length": t["length"],
                           "volume_db": t["volume_db"], "fade_in": t["fade_in"], "fade_out": t["fade_out"],
                           "duck": t["duck"], "loop": t["loop"]})
            export.append(dict(tracks[-1], id=t["id"], code=t["code"]))
        sa = m.get("scene_audio") or {"mix": False, "volume_db": -12.0}
        w, h = p["global"]["output"]["width"], p["global"]["output"]["height"]
        if draft:
            w, h = max(2, int(w) // 4 * 2), max(2, int(h) // 4 * 2)
        stem_paths, stem_dir = None, None
        if stems:
            stem_dir = base + "_stems"
            tmp_dir = stem_dir + ".partial"
            made += [tmp_dir, stem_dir]
            os.makedirs(tmp_dir, exist_ok=True)
            stem_paths = {"scenes": os.path.join(tmp_dir, "scenes.wav"), "mix": os.path.join(tmp_dir, "mix.wav"),
                          "tracks": [os.path.join(tmp_dir, "track_{}.wav".format(_safe_name(t["id"]))) for t in export]}
        made.append(files["video"])
        # [OLD 2026-11-05 v0.6.1->v0.7.0] the sound's fade at a cut defaulted to Global -> Merge -> audio fade
        # merge.join(segments, files["video"], w, h, progress=progress, cancel=cancel, codec=m["codec"],
        #            crf=28 if draft else m["crf"], preset="veryfast" if draft else "medium",
        #            audio_fade_frames=int(m["audio_fade_frames"]),
        # [/OLD]
        # added 2026-11-05 v0.7.0: every segment carries its scene's own fade (scene.merge.audio_frames)
        merge.join(segments, files["video"], w, h, progress=progress, cancel=cancel, codec=m["codec"],
                   crf=28 if draft else m["crf"], preset="veryfast" if draft else "medium",
                   audio_fade_frames=0,
                   loudness=float(m["loudness"]) if m["normalize"] else None,
                   chapters_file=chapters, tracks=tracks,
                   scene_audio={"mix": bool(sa.get("mix")), "volume_db": float(sa.get("volume_db", -12.0))},
                   stems=stem_paths)
        check()
        loudness = None
        if stems:
            os.replace(tmp_dir, stem_dir)
            files["stems"] = stem_dir
            loudness = {"target": float(m["loudness"]) if m["normalize"] else None}
            names_ = ["mix", "scenes"] + ["track_{}".format(_safe_name(t["id"])) for t in export]
            for name in names_:
                wav = os.path.join(stem_dir, name + ".wav")
                if os.path.isfile(wav):
                    loudness[name] = merge.measure_loudness(wav, cancel=cancel)
            loudness.update({k: v for k, v in loudness["mix"].items()} if loudness.get("mix") else {})
            files["loudness"] = base + "_loudness.json"
            made.append(files["loudness"])
            with open(files["loudness"], "w", encoding="utf-8") as f:
                json.dump(loudness, f, indent=1)
        markers = []
        for mk in p.get("markers") or []:
            try:
                t_ = float(mk.get("t")) - offset
            except (TypeError, ValueError):
                continue
            if 0 <= t_ <= total:
                markers.append({"id": mk.get("id", ""), "t": t_, "text": mk.get("text", ""), "color": mk.get("color", "")})
        for t in export:
            try:
                t["file_duration"] = merge.probe(t["path"])["duration"]
            except merge.MergeError:
                t["file_duration"] = t["in"] + t["length"]
        if m["subtitles"]:
            files["srt"] = base + ".srt"
            made.append(files["srt"])
            # [OLD 2026-11-06 v0.9.0->v0.10.0] merge.write_srt(real, files["srt"])
            # added 2026-11-06 v0.10.0: lines timed to the speech in each take (H3 decides when inside a shot a line
            # is spoken); "planned" keeps the timeline's times
            merge.write_srt(speech_timed(real) if m.get("subtitle_timing", "speech") == "speech" else real, files["srt"])
        if m["otio"]:
            files["otio"] = base + ".otio"
            made.append(files["otio"])
            merge.write_otio(p["name"], real, files["otio"], tracks=export, markers=markers, total=total)
        if m["fcpxml"]:
            files["fcpxml"] = base + ".fcpxml"
            made.append(files["fcpxml"])
            merge.write_fcpxml(p["name"], real, total, w, h, files["fcpxml"], tracks=export, markers=markers)
        if m["bundle"]:
            files["bundle"] = base + ".zip"
            made.append(files["bundle"])
            project_json = os.path.join(store.dir, "project.json")
            parts = {os.path.basename(v): v for k, v in files.items() if k not in ("bundle", "stems")}
            if stem_dir:
                parts.update({"stems/" + x: os.path.join(stem_dir, x) for x in sorted(os.listdir(stem_dir))})
            merge.write_bundle(files["bundle"], dict(parts, **{"project.json": project_json}))
        check()
    except BaseException as e:
        for path in made:
            _remove(path)
        if isinstance(e, jobs.Cancelled):
            raise merge.MergeCancelled("merge cancelled") from e
        raise
    out = {"files": {k: store.rel_output(v) for k, v in files.items()}, "duration": total,
           "skipped": skipped, "created": int(time.time()), "soundtrack": len(tracks), "job": job.id,
           "draft": draft, "range": [p["scenes"][info["first"]]["id"], p["scenes"][info["last"]]["id"]]
           if o.get("range") else None}
    out["warnings"] = warnings  # added 2026-11-05 v0.7.0: e.g. a colour reference scene without a take
    if stems:
        out["loudness"] = loudness
    return out


# ---- the soundtrack excerpt a pass is sent (added 2026-11-03 v0.6.0) ----------------------------------------------

def pass_song(result, store, scene_id, pass_number):
    """(song, wav path) of what H3 hears as the soundtrack for pass `pass_number` (1-based) of a scene: the song
    entry prompt.build_pass made (soundtrack.pass_soundtrack) and the WAV merge.render_segment cuts for it, the same
    calls render.encode makes, so the file is the one a render sends (and is shared with it). (None, None) when the
    pass gets no song."""
    sr = result["scenes"].get(scene_id)
    if not sr:
        raise ValueError("unknown scene")
    builds = sr.get("builds") or []
    if not isinstance(pass_number, int) or not 1 <= pass_number <= len(builds):
        raise ValueError("pass must be 1 to {}".format(len(builds)))
    song = next((a["song"] for a in builds[pass_number - 1].get("audios", []) if a.get("song")), None)
    if not song:
        return None, None
    assets = project_index(result["project"])["assets"]
    pieces = []
    for x in song["pieces"]:
        a = assets.get(x["asset"])
        path = store.input_path(a["file"]) if a and a.get("file") else ""
        if not path or not os.path.isfile(path):
            raise FileNotFoundError("{} is missing: {}".format((a or {}).get("code") or x["asset"], (a or {}).get("file", "")))
        pieces.append({"path": path, "src_in": x["src_in"], "src_out": x["src_out"], "at": x["at"]})
    return song, merge.render_segment(pieces, song["length"], os.path.join(store.dir, "soundtrack"), cache.file_digest)
