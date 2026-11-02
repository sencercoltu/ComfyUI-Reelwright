"""Optional identity drift check: face similarity between a render and its anchors.

Needs the `insightface` and `onnxruntime` packages. The first use downloads the
buffalo_l face model into ~/.insightface (a one-time download the user enables
by switching face check on). Without the packages the check reports itself as
unavailable and nothing else changes.
"""

import importlib.util
import os

import numpy as np

from .model import project_index

_app = None
_anchor_cache = {}


def available():
    return importlib.util.find_spec("insightface") is not None and importlib.util.find_spec("onnxruntime") is not None


def _analyzer():
    global _app
    if _app is None:
        from insightface.app import FaceAnalysis
        _app = FaceAnalysis(name="buffalo_l", allowed_modules=["detection", "recognition"])
        _app.prepare(ctx_id=0, det_size=(640, 640))
    return _app


def _embeddings(bgr):
    return [f.normed_embedding for f in _analyzer().get(bgr)]


def _anchor_embeddings(path):
    st = os.stat(path)
    key = (path, st.st_mtime_ns)
    if key not in _anchor_cache:
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            rgb = np.asarray(ImageOps.exif_transpose(im).convert("RGB"))
        _anchor_cache[key] = _embeddings(rgb[:, :, ::-1].copy())
    return _anchor_cache[key]


def _sample_frames(video_path, samples):
    import av
    frames = []
    with av.open(video_path) as c:
        stream = c.streams.video[0]
        total = stream.frames or 0
        wanted = {int(total * (i + 0.5) / samples) for i in range(samples)} if total else None
        for i, frame in enumerate(c.decode(stream)):
            if wanted is None or i in wanted:
                frames.append(frame.to_ndarray(format="bgr24"))
                if wanted is None and len(frames) >= samples:
                    break
    return frames


def check_scene(p, scene, store, video_path, samples=8):
    """{cast_id: score} where score is the mean best cosine similarity per sampled frame."""
    idx = project_index(p)
    anchors = {}
    for entry in scene["cast"]:
        c = idx["cast"].get(entry["id"])
        if not c or c["kind"] != "character":
            continue
        embs = []
        for aid in c["anchors"]:
            a = idx["assets"].get(aid)
            if a and a["kind"] == "image":
                path = store.input_path(a["file"])
                if os.path.isfile(path):
                    embs += _anchor_embeddings(path)
        if embs:
            anchors[c["id"]] = np.stack(embs)
    if not anchors:
        return {}
    frames = _sample_frames(video_path, samples)
    scores = {cid: [] for cid in anchors}
    for bgr in frames:
        faces = _embeddings(bgr)
        if not faces:
            continue
        faces = np.stack(faces)
        for cid, ref in anchors.items():
            scores[cid].append(float((faces @ ref.T).max()))
    return {cid: round(sum(v) / len(v), 3) for cid, v in scores.items() if v}
