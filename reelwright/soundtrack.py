"""Soundtrack: audio files laid on the film's timeline (added 2026-11-03 v0.5.0).

A music video is cut to a song that must play unchanged. Each track places part of an audio asset on the film:
`start` is where it begins in the film, `in` / `out` trim the source file. A track can

- `mix`: play in the finished cut, untouched (volume and fades are optional, 0 dB and no fade by default);
- `sync`: send, to every pass of every scene, the part of the song that pass covers, as an H3 audio reference
  (`marker`, fully_copy by default), so lips, movement and cuts follow it.

Times are film (cut) times: see model.scene_starts. Pure Python, no ComfyUI imports.
"""

from . import spec

MARKERS = spec.AUDIO_RETENTION
TRACK_DEFAULTS = {"id": "", "asset": "", "start": 0.0, "in": 0.0, "out": 0.0, "volume_db": 0.0, "fade_in": 0.0,
                  "fade_out": 0.0, "mute": False, "sync": True, "marker": "fully_copy", "mix": True, "duck": False,
                  "loop": False}


# [OLD 2026-11-03 v0.5.1->v0.6.0] float() also read "inf", "1_000" and True; model.js reads numbers differently
# def _f(v, default=0.0):
#     try:
#         v = float(v)
#     except (TypeError, ValueError):
#         return default
#     return v if v == v and abs(v) != float("inf") else default
# [/OLD]
def _f(v, default=0.0):
    return float(spec.num(v, default))


# [OLD 2026-11-03 v0.5.1->v0.6.0] id/asset could stay numbers or lists, bool("false") was True, JS did not coerce bools
# def normalize_track(t):
#     """Fill and clean one track in place."""
#     for k, v in TRACK_DEFAULTS.items():
#         if t.get(k) is None:
#             t[k] = v
#     for k in ("start", "in", "out", "volume_db", "fade_in", "fade_out"):
#         t[k] = _f(t[k])
#     t["in"] = max(0.0, t["in"])
#     t["fade_in"], t["fade_out"] = max(0.0, t["fade_in"]), max(0.0, t["fade_out"])
#     for k in ("mute", "sync", "mix", "duck", "loop"):
#         t[k] = bool(t[k])
#     if t["marker"] not in MARKERS:
#         t["marker"] = "fully_copy"
#     return t
# [/OLD]
def normalize_track(t):
    """Fill and clean one track in place (same result as model.js normalizeTrack, except that JS also gives a track
    without an id a new one; model.normalize_project does that here)."""
    for k, v in TRACK_DEFAULTS.items():
        if t.get(k) is None:
            t[k] = v
    for k in ("start", "in", "out", "volume_db", "fade_in", "fade_out"):
        t[k] = _f(t[k])
    t["in"] = max(0.0, t["in"])
    t["fade_in"], t["fade_out"] = max(0.0, t["fade_in"]), max(0.0, t["fade_out"])
    for k in ("mute", "sync", "mix", "duck", "loop"):
        t[k] = spec.flag(t[k], TRACK_DEFAULTS[k])
    for k in ("id", "asset"):
        t[k] = spec.text(t[k])
    if t["marker"] not in MARKERS:
        t["marker"] = "fully_copy"
    return t


def track_length(t, asset):
    """Seconds of the source the track plays: in..out, or in..end of the file when out is not set."""
    out = t["out"] if t["out"] > t["in"] else _f((asset or {}).get("duration"))
    return max(0.0, out - t["in"])


def resolved(p):
    """Tracks that can play: not muted, an audio asset that exists and some length. Each is a copy with the
    asset's `file`, `code` and the track's `length`."""
    assets = {a["id"]: a for a in p.get("assets", [])}
    out = []
    for t in p.get("soundtrack") or []:
        a = assets.get(t.get("asset"))
        if t.get("mute") or not a or a.get("kind") != "audio" or not a.get("file"):
            continue
        length = track_length(t, a)
        if length <= 0:
            continue
        out.append(dict(t, file=a["file"], code=a.get("code", ""), length=length))
    return out


def locked(p):
    """A soundtrack sets the film's timing: transitions must not shift scenes, missing scenes keep their length."""
    return any(t["mix"] or t["sync"] for t in resolved(p))


def pieces(tracks, t0, length):
    """The parts of `tracks` heard in film time t0..t0+length: [{asset, file, src_in, src_out, at}], where `at` is
    the offset inside the window. Looping tracks repeat."""
    out = []
    for t in tracks:
        reps = [0]
        if t.get("loop"):
            if t["length"] <= 1e-3:  # added 2026-11-03 v0.6.0: no repeat could last over 1 ms; a tiny loop hung here
                continue
            first = int(max(0.0, t0 - t["start"]) // t["length"])
            reps = range(first, first + int(length // t["length"]) + 2)
        for r in reps:
            begin = t["start"] + r * t["length"]
            a, b = max(t0, begin), min(t0 + length, begin + t["length"])
            if b - a > 1e-3:
                out.append({"asset": t["asset"], "file": t["file"], "src_in": round(t["in"] + (a - begin), 4),
                            "src_out": round(t["in"] + (b - begin), 4), "at": round(a - t0, 4)})
    return out


def pass_window(start, pass_):
    """Film time of the pass's generated frame 0 and the reference length (at most 15 s)."""
    return start + pass_["start"], min(spec.REF_MEDIA_MAX_SECONDS, pass_["gen_frames"] / spec.FPS)


def pass_soundtrack(p, scene_start, pass_):
    """The song for one pass, or None: what the `sync` tracks play over the pass's generated frames, from film time
    scene_start + pass start, silence where nothing plays. Left out when less than 2 s of it has sound."""
    tracks = [t for t in resolved(p) if t["sync"]]
    if not tracks:
        return None
    t0, length = pass_window(scene_start, pass_)
    ps = pieces(tracks, t0, length)
    if sum(x["src_out"] - x["src_in"] for x in ps) < spec.REF_MEDIA_MIN_SECONDS:
        return None
    first = next(t for t in tracks if any(x["asset"] == t["asset"] for x in ps))
    return {"start": round(t0, 4), "length": round(length, 4), "pieces": ps, "marker": first["marker"],
            "codes": sorted({t["code"] for t in tracks if any(x["asset"] == t["asset"] for x in ps)})}


def digest(item, asset_digest):
    """What the cache key needs to know about a pass's song segment."""
    return {"length": item["length"], "marker": item["marker"],
            "pieces": [[asset_digest(x["asset"]), x["src_in"], x["src_out"], x["at"]] for x in item["pieces"]]}


def migrate_score(p):
    """The v0.4 merge score (one looping music bed) becomes a soundtrack track, in place."""
    m = p.get("global", {}).get("merge", {})
    score = m.get("score") or {}
    if not score.get("asset"):
        return False
    # [OLD 2026-11-03 v0.5.1->v0.6.0] p.setdefault("soundtrack", []).append(normalize_track({
    # [OLD 2026-11-03 v0.5.1->v0.6.0]     "id": "t_score", "asset": score["asset"], "volume_db": _f(score.get("volume_db"), -12.0),
    # [OLD 2026-11-03 v0.5.1->v0.6.0]     "sync": False, "mix": True, "duck": bool(score.get("duck", True)), "loop": True}))
    # duck: read like model.js migrateScore (a null or non-bool duck means the default, True)
    # added 2026-11-03 v0.6.0: a unique id (an old profile applied twice gave two "t_score" tracks)
    used = {t.get("id") for t in p.get("soundtrack") or [] if isinstance(t, dict)}
    tid, k = "t_score", 2
    while tid in used:
        tid, k = "t_score_{}".format(k), k + 1
    # [OLD 2026-11-03 v0.5.1->v0.6.0]     "id": "t_score", "asset": score["asset"], (fixed id)
    p.setdefault("soundtrack", []).append(normalize_track({
        "id": tid, "asset": score["asset"], "volume_db": _f(score.get("volume_db"), -12.0),
        "sync": False, "mix": True, "duck": spec.flag(score.get("duck"), True), "loop": True}))
    score["asset"] = ""
    m["scene_audio"] = {"mix": True, "volume_db": 0.0}  # the scenes' sound stays on top, as it was with the score
    return True
