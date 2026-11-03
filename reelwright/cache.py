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


def pass_key(settings_fp, build, pass_, asset_digest, upstream_key, previous_pass_key):
    guides = []
    for g in build["guides"]:
        x = {k: v for k, v in g.items() if k != "asset"}
        if g.get("asset"):
            x["asset"] = asset_digest(g["asset"])
        if g["source"].startswith("prev_scene"):
            x["upstream"] = upstream_key
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


def scene_key(plan, pass_keys):
    return _hash({"kind": plan["kind"], "frames": plan["frames"], "passes": pass_keys,
                  "keep": [[x["keep_in_frames"], x["keep_out_frames"]] for x in plan["passes"]]})


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
