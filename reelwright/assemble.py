"""Build ffmpeg segment lists for long-scene stitching and the final merge."""

import os
import time

from . import merge, spec
from .model import project_index


def pass_segments(plan, pass_files, crossfade_frames):
    """Segments that stitch a scene's pass files into the scene video."""
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
        segs.append(seg)
    return segs


def pick_take(entry, use):
    takes = entry.get("takes") or []
    if use == "latest":
        return takes[-1] if takes else None
    return next((t for t in takes if t["id"] == entry.get("starred")), None) or (takes[-1] if takes else None)


def cut_plan(result, store):
    """Segments + side-file entries for the merge, from the analysis result."""
    p = result["project"]
    m = p["global"]["merge"]
    cf_cont = int(p["global"]["long"]["crossfade_frames"])
    names = {c["id"]: c["name"] for c in p["cast"]}
    segments, entries, skipped = [], [], []
    prev_included = None
    for i, s in enumerate(p["scenes"]):
        sr = result["scenes"][s["id"]]
        take = pick_take(sr, m["use"])
        path = store.output_path(take["files"]["video"]) if take and take.get("files", {}).get("video") else None
        if not path or not os.path.isfile(path):
            if m["missing"] == "block":
                raise merge.MergeError("{:02d} {} has no finished take".format(i + 1, s["title"]))
            if m["missing"] == "slate":
                segments.append({"path": None, "in": 0.0, "out": float(s["duration"]), "join": "cut", "dur": 0.0})
                entries.append(None)
            skipped.append(s["id"])
            prev_included = None if m["missing"] != "slate" else i
            continue
        info = merge.probe(path)
        length = float(take.get("seconds") or info["duration"])
        seg = {"path": path, "in": 0.0, "out": length, "has_audio": info["has_audio"], "join": "cut", "dur": 0.0,
               "scene_id": s["id"]}
        mode = s["start"]["mode"] if i > 0 else "fresh"
        overlap = int(take.get("overlap_frames") or 0)
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
            # [OLD 2026-11-02 v0.2.2->v0.3.0] every hard cut used Global -> Merge; now each scene can choose its own
            # hard = m["hard_cut"]
            # if hard in ("crossfade", "dip"):
            #     prev_len = segments[-1]["out"] - segments[-1]["in"]
            #     d = min(int(m["transition_frames"]) / spec.FPS, prev_len / 2, (length - seg["in"]) / 2)
            # [/OLD]
            tr = s.get("transition") or {}
            hard = tr.get("mode") or m["hard_cut"]
            frames = tr.get("frames") if tr.get("frames") is not None else m["transition_frames"]
            if hard in ("crossfade", "dip"):
                prev_len = segments[-1]["out"] - segments[-1]["in"]
                d = min(int(frames) / spec.FPS, prev_len / 2, (length - seg["in"]) / 2)
                if d > 0:
                    seg["join"] = "xfade" if hard == "crossfade" else "dip"
                    seg["dur"] = d
        afade = (s.get("transition") or {}).get("audio_fade_frames")
        if afade is not None:
            seg["fade"] = int(afade) / spec.FPS  # added 2026-11-02 v0.3.0: per-scene audio fade at its cut
        segments.append(seg)
        lines = [{"t": float(d["t"]), "speaker": names.get(d["speaker"], ""), "text": d["text"]} for d in s["dialogue"]]
        entries.append({"scene_id": s["id"], "title": "{:02d} {}".format(i + 1, s["title"]), "path": path,
                        "src_in": seg["in"], "src_out": seg["out"], "src_len": length, "dialogue": lines})
        prev_included = i
    return segments, entries, skipped


def merge_project(result, store, progress=None):
    p = result["project"]
    m = p["global"]["merge"]
    segments, entries, skipped = cut_plan(result, store)
    if not any(s.get("path") for s in segments):
        raise merge.MergeError("no scene has a finished take yet")
    starts, total = merge.plan_timeline(segments)
    real = []
    for seg, e, st in zip(segments, entries, starts):
        if e:
            e["start"] = st
            real.append(e)
    if m["color_match"]:
        ref_sid = m.get("color_ref_scene")
        ref_index = next((k for k, s in enumerate(segments) if s.get("scene_id") == ref_sid), 0)
        for seg, gain in zip(segments, merge.color_gains(segments, ref_index)):
            seg["gain"] = gain
    base = store.next_cut_path()
    files = {"video": base + ".mp4"}
    chapters = None
    if m["chapters"]:
        chapters = base + ".chapters.txt"
        merge.write_chapters(real, total, chapters)
        files["chapters"] = chapters
    score = None
    if m["score"].get("asset"):
        a = project_index(p)["assets"].get(m["score"]["asset"])
        if a and a.get("file"):
            score = {"path": store.input_path(a["file"]), "volume_db": float(m["score"]["volume_db"]),
                     "duck": bool(m["score"]["duck"])}
    w, h = p["global"]["output"]["width"], p["global"]["output"]["height"]
    merge.join(segments, files["video"], w, h, progress=progress, codec=m["codec"], crf=m["crf"],
               audio_fade_frames=int(m["audio_fade_frames"]),
               loudness=float(m["loudness"]) if m["normalize"] else None,
               score=score, chapters_file=chapters)
    if m["subtitles"]:
        files["srt"] = base + ".srt"
        merge.write_srt(real, files["srt"])
    if m["otio"]:
        files["otio"] = base + ".otio"
        merge.write_otio(p["name"], real, files["otio"])
    if m["fcpxml"]:
        files["fcpxml"] = base + ".fcpxml"
        merge.write_fcpxml(p["name"], real, total, w, h, files["fcpxml"])
    if m["bundle"]:
        files["bundle"] = base + ".zip"
        project_json = os.path.join(store.dir, "project.json")
        merge.write_bundle(files["bundle"], {os.path.basename(v): v for k, v in files.items() if k != "bundle"} |
                           {"project.json": project_json})
    return {"files": {k: store.rel_output(v) for k, v in files.items()}, "duration": total,
            "skipped": skipped, "created": int(time.time())}
