"""Turn a scene of any length into valid H3 passes.

A pass is one generation of 124-362 frames (17k+5). Scenes shorter than a pass
render the shortest pass and keep a window; longer scenes are split, with
seams on shot cuts where possible and guided overlaps elsewhere.

All times in a pass dict are seconds unless the key ends in `_frames`.
`start` is the scene time of the pass's generated frame 0 (negative for the
handle before a short scene's window).
"""

from . import spec
from .model import scene_seed


def _overlap_frames(n):
    return spec.align_frames_down(max(5, int(n)))


def _cut_frames(scene, total):
    cuts = []
    for sh in scene["shots"][1:]:
        f = spec.frames_of(float(sh["t"]))
        if 0 < f < total:
            cuts.append(f)
    return sorted(set(cuts))


def _passes_needed(frames, max_f, ov):
    if frames <= max_f:
        return 1
    return 1 + -(-(frames - max_f) // (max_f - ov))


def _segments(scene, total, max_f, ov, seam_mode, snap_f, first_overlap):
    """[(start_frame, gen_frames, keep_frames, seam_before, overlap_in)] covering 0..total."""
    cuts = _cut_frames(scene, total)
    out = []
    s, seam, ov_in = 0, "none", first_overlap
    while True:
        remaining = total - s
        if remaining <= max_f:
            out.append((s, spec.clamp_pass_frames(remaining), remaining, seam, ov_in))
            return out
        limit = s + max_f
        cut = None
        if seam_mode != "overlap":
            candidates = [c for c in cuts if s + spec.MIN_PASS_FRAMES <= c <= limit]
            if seam_mode == "auto":
                # a cut wins when it is close to the natural seam, or when using it
                # does not add a pass compared with an overlap seam
                baseline = _passes_needed(remaining, max_f, ov)
                candidates = [c for c in candidates
                              if c >= limit - snap_f or 1 + _passes_needed(total - c, max_f, ov) <= baseline]
            if candidates:
                cut = max(candidates)
        if cut is not None:
            length = cut - s
            out.append((s, spec.clamp_pass_frames(length), length, seam, ov_in))
            s, seam, ov_in = cut, "cut", 0
            continue
        gen = max_f
        left_after = remaining - (gen - ov)
        if 0 < left_after < spec.MIN_PASS_FRAMES:
            # balance the last two passes instead of padding a tiny tail
            gen = min(max_f, max(spec.MIN_PASS_FRAMES, spec.align_frames_up((remaining + ov) // 2)))
        out.append((s, gen, gen, seam, ov_in))
        s, seam, ov_in = s + gen - ov, "overlap", ov


def _shot_ranges(scene, total):
    shots = scene["shots"]
    ranges = []
    for i, sh in enumerate(shots):
        a = spec.frames_of(float(sh["t"]))
        b = spec.frames_of(float(shots[i + 1]["t"])) if i + 1 < len(shots) else total
        ranges.append((i + 1, sh, a, max(a, b)))
    return ranges


def plan_scene(p, scene, scene_index):
    g = p["global"]
    lg = g["long"]
    duration = max(1.0 / spec.FPS, float(scene["duration"]))
    total = max(1, spec.frames_of(duration))
    seed = scene_seed(p, scene, scene_index)
    mode = scene["start"]["mode"] if scene_index > 0 else "fresh"
    first_overlap = _overlap_frames(scene["start"]["overlap_frames"]) if mode == "tail" else 0
    if mode == "tail":
        first_overlap = min(first_overlap, spec.align_frames_down(total))

    keep_in_frames = 0
    if total < spec.MIN_PASS_FRAMES:
        kind = "short"
        gen = spec.MIN_PASS_FRAMES
        spare = gen - total
        keep = scene["trim"]["keep"] if mode == "fresh" else "start"
        if keep == "middle":
            keep_in_frames = spare // 2
        elif keep == "end":
            keep_in_frames = spare
        elif keep == "custom":
            keep_in_frames = min(spare, max(0, spec.frames_of(float(scene["trim"]["in"]))))
        segments = [(0, gen, total, "none", first_overlap)]
    else:
        max_f = spec.align_frames_down(min(spec.MAX_PASS_FRAMES, int(lg["max_pass_frames"])))
        max_f = max(spec.MIN_PASS_FRAMES, max_f)
        ov = min(_overlap_frames(lg["overlap_frames"]), spec.align_frames_down(max_f // 2))
        segments = _segments(scene, total, max_f, ov, lg["seam_mode"],
                             spec.frames_of(float(lg["cut_snap_seconds"])), first_overlap)
        kind = "single" if len(segments) == 1 else "long"

    shot_ranges = _shot_ranges(scene, total)
    refs = scene["refs"]
    passes = []
    for i, (s, gen, keep_frames, seam, ov_in) in enumerate(segments):
        end = s + keep_frames
        fresh_from = s + ov_in if i > 0 else s
        pass_shots = []
        for number, sh, a, b in shot_ranges:
            if b <= s or a >= end:
                continue
            pass_shots.append({"id": sh["id"], "number": number, "continuing": a < s,
                               "t": (max(a, s) - s + keep_in_frames) / spec.FPS,
                               "camera": sh["camera"], "text": sh["text"]})
        lines = []
        for d in scene["dialogue"]:
            f = spec.frames_of(float(d["t"]))
            if fresh_from <= f < end:
                lines.append(dict(d, t=(f - s + keep_in_frames) / spec.FPS))
        keyframes, firsts, lasts = [], [], []
        for r in refs:
            if r["role"] == "keyframe":
                f = spec.frames_of(float(r["time"]))
                if fresh_from <= f < end:
                    keyframes.append({"ref": r["id"], "frame_idx": f - s + keep_in_frames})
            elif r["role"] == "first_frame" and i == 0:
                firsts.append({"ref": r["id"], "frame_idx": keep_in_frames})
            elif r["role"] == "last_frame" and i == len(segments) - 1:
                lasts.append({"ref": r["id"], "frame_idx": keep_in_frames + keep_frames - 1})
        passes.append({
            "index": i + 1,
            "start": (s - keep_in_frames) / spec.FPS,
            "end": end / spec.FPS,
            "gen_frames": gen,
            "keep_in": keep_in_frames / spec.FPS,
            "keep_out": (keep_in_frames + keep_frames) / spec.FPS,
            "keep_in_frames": keep_in_frames,
            "keep_out_frames": keep_in_frames + keep_frames,
            "seam_before": seam,
            "overlap_frames": ov_in,
            "seed": seed + i,
            "shots": pass_shots,
            "dialogue": lines,
            "keyframes": keyframes,
            "first_frame": firsts,
            "last_frame": lasts,
        })
    return {"scene_id": scene["id"], "kind": kind, "duration": duration, "frames": total,
            "start_mode": mode, "seed": seed, "passes": passes,
            "generated_frames": sum(x["gen_frames"] for x in passes)}


def continuation_depth(p):
    """How many continuation links lead into each scene (0 for a fresh start)."""
    depth, prev = {}, 0
    for i, s in enumerate(p["scenes"]):
        cont = i > 0 and s["start"]["mode"] in ("last_frame", "tail")
        prev = prev + 1 if cont else 0
        depth[s["id"]] = prev
    return depth


def plan_project(p):
    return {s["id"]: plan_scene(p, s, i) for i, s in enumerate(p["scenes"])}
