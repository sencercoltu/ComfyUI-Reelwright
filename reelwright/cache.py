"""Cache keys and render status.

A pass key covers everything that changes the pixels: models and LoRAs, size,
sampling, seed, frames, the final prompt, the bytes of every reference file and
whatever the pass continues from. A scene is cached when its starred take was
rendered with the current key.
"""

import hashlib
import json
import os

from . import soundtrack  # added 2026-11-03 v0.5.0

_memo = {}


def file_digest(path):
    try:
        st = os.stat(path)
    except OSError:
        return "missing:" + os.path.basename(path)
    k = (path, st.st_size, st.st_mtime_ns)
    if k not in _memo:
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        _memo[k] = h.hexdigest()
    return _memo[k]


def _hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def settings_fingerprint(settings, wired):
    s = dict(settings)
    s.pop("seed", None)
    if not s.get("sigma_shift"):
        s.pop("shift_video", None)
        s.pop("shift_audio", None)
    for k in ("diffusion", "text_encoder", "video_vae", "audio_vae"):
        if wired.get(k):
            s[k] = "wired"
    return s


# [OLD 2026-11-03 v0.5.1->v0.6.0] the take a scene continues from was not part of its key (fix #11)
# def pass_key(settings_fp, build, pass_, asset_digest, upstream_key, previous_pass_key):
def pass_key(settings_fp, build, pass_, asset_digest, upstream_key, previous_pass_key, upstream_take=None):
    """The key of one pass. `upstream_take` (added 2026-11-03 v0.6.0) is the id of the take the scene continues from;
    with None the key is the one v0.5.1 computed, so older takes can still be matched (see resolve)."""
    guides = []
    for g in build["guides"]:
        x = {k: v for k, v in g.items() if k != "asset"}
        if g.get("asset"):
            x["asset"] = asset_digest(g["asset"])
        if g["source"].startswith("prev_scene"):
            x["upstream"] = upstream_key
            if upstream_take is not None:  # added 2026-11-03 v0.6.0: "New take" upstream makes this scene stale
                x["upstream_take"] = upstream_take
        if g["source"] == "prev_pass_tail":
            x["upstream"] = previous_pass_key
        guides.append(x)
    return _hash({
        "settings": settings_fp,
        "frames": pass_["gen_frames"],
        "seed": pass_["seed"],
        "prompt": build["prompt"],
        "images": [[asset_digest(a) for a in img["assets"]] for img in build["images"]],
        "videos": [[asset_digest(v["asset"]), v["soundtrack"]] for v in build["videos"]],
        # [OLD 2026-11-03 v0.4.3->v0.5.0] "audios": [asset_digest(a["asset"]) for a in build["audios"]],
        # added 2026-11-03 v0.5.0: the soundtrack segment is keyed by what it plays, so moving or trimming a track
        # re-renders only the passes it covers
        "audios": [soundtrack.digest(a["song"], asset_digest) if a.get("song") else asset_digest(a["asset"])
                   for a in build["audios"]],
        "guides": guides,
    })


# [OLD 2026-11-03 v0.5.1->v0.6.0] Global -> Long scenes -> crossfade changed the stitched take but not its key
# def scene_key(plan, pass_keys):
#     return _hash({"kind": plan["kind"], "frames": plan["frames"], "passes": pass_keys,
#                   "keep": [[x["keep_in_frames"], x["keep_out_frames"]] for x in plan["passes"]]})
# [/OLD]
def scene_key(plan, pass_keys, crossfade_frames=None):
    """The take's key. `crossfade_frames` (added 2026-11-03 v0.6.0) counts only when passes are joined with overlap
    seams (that is where the crossfade is used); None gives the v0.5.1 key."""
    data = {"kind": plan["kind"], "frames": plan["frames"], "passes": pass_keys,
            "keep": [[x["keep_in_frames"], x["keep_out_frames"]] for x in plan["passes"]]}
    if crossfade_frames is not None and any(x.get("seam_before") == "overlap" for x in plan["passes"]):
        data["crossfade"] = int(crossfade_frames)
    return _hash(data)


# ---- pass cache (added 2026-11-03 v0.6.0) ------------------------------------------------------------------------
# Finished passes are kept under <scene_dir>/passes/<file key>.mp4 (+ .json), shared by the scene's takes. A file key
# is the pass key plus the seed the pass was sampled with, plus the file key of the pass it continues from (an overlap
# seam), so a take with other seeds never picks up another take's passes.

def pass_file_keys(pass_keys, builds, seeds):
    """File keys (32 hex characters) of a take's passes."""
    out, prev = [], None
    for k, b, seed in zip(pass_keys, builds, seeds):
        chained = any(g.get("source") == "prev_pass_tail" for g in b.get("guides") or [])
        prev = _hash({"pass": k, "seed": int(seed), "prev": prev if chained else None})[:32]
        out.append(prev)
    return out


def upstream_dependent(builds, continuing):
    """[bool] per pass: does the pass change when the take the scene continues from changes? Pass 1 of a
    continuing scene does, and every later pass joined to it by an overlap seam."""
    out, dep = [], False
    for n, b in enumerate(builds):
        guides = b.get("guides") or []
        if n == 0:
            dep = bool(continuing) and any(str(g.get("source", "")).startswith("prev_scene") for g in guides)
        else:
            dep = dep and any(g.get("source") == "prev_pass_tail" for g in guides)
        out.append(dep)
    return out


# ---- status (added 2026-11-03 v0.6.0) ----------------------------------------------------------------------------

def manual_star(index):
    """True when the starred take was picked by hand. Renders record the take they star in index["auto_star"];
    an index from before v0.6.0 has no such field, and there a render always starred the take it added (the
    newest one)."""
    takes = index.get("takes") or []
    starred = index.get("starred")
    if not starred or not takes:
        return False
    if "auto_star" in index:
        return index.get("auto_star") != starred
    return takes[-1].get("id") != starred


def resolve(scene, index, key, has_errors, legacy_key=None, upstream=None):
    """Status of a scene and the takes involved:
    {status, match, starred, manual, provided}. `provided` is the take the next scene continues from (None when this
    scene is going to be rendered). `legacy_key` is the key v0.5.1 computed: a take made before v0.6.0 (no "upstream"
    field) with that key still counts, unless the take it would continue from (`upstream`) is newer than it.
    A scene with lint errors (added 2026-11-03 v0.6.0 review) is never rendered or re-starred by a run, so it provides
    its starred take: that is the take a render of the next scene and a merge use."""
    takes = index.get("takes") or []
    starred = next((t for t in takes if t.get("id") == index.get("starred")), None)

    def fits(t):
        if t.get("key") == key:
            return True
        if legacy_key and "upstream" not in t and t.get("key") == legacy_key:
            return upstream is None or int(t.get("created") or 0) >= int(upstream.get("created") or 0)
        return False

    match = starred if starred and fits(starred) else next((t for t in reversed(takes) if fits(t)), None)
    manual = bool(starred) and match is not starred and manual_star(index)
    if scene.get("lock") and starred:
        status, match, provided = "locked", starred, starred
    elif not takes:
        status, provided = "missing", None
    elif match:
        status, provided = "cached", (starred if manual else match)
    else:
        status, provided = "stale", None
    if has_errors:
        status = "error"
        # added 2026-11-03 v0.6.0 review: `provided` stayed the matching take (None when stale), but no run renders or
        # re-stars an error scene, so the next scene was keyed against one take and rendered from another (the
        # starred one): stale after every run, and reuse() could star a take made from a different upstream take
        provided = starred
    return {"status": status, "match": match, "starred": starred, "manual": manual, "provided": provided}


def status_of(scene, index, key, has_errors):
    """cached | stale | missing | locked | error, plus the take that matches."""
    takes = index.get("takes", [])
    starred = next((t for t in takes if t["id"] == index.get("starred")), None)
    match = next((t for t in reversed(takes) if t.get("key") == key), None)
    if has_errors:
        return "error", match
    if scene.get("lock") and starred:
        return "locked", starred
    if not takes:
        return "missing", None
    if starred and starred.get("key") == key:
        return "cached", starred
    if match:
        return "cached", match
    return "stale", None


def used_key(scene, index, key):
    """The key downstream scenes depend on: a locked scene keeps its starred take."""
    if scene.get("lock"):
        starred = next((t for t in index.get("takes", []) if t["id"] == index.get("starred")), None)
        if starred:
            return starred.get("key", key)
    return key
