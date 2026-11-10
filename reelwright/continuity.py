"""Optional identity drift check: face similarity between a render and its anchors.

Needs the `insightface` and `onnxruntime` packages. The first use downloads the
buffalo_l face model into ~/.insightface (a one-time download the user enables
by switching face check on). Without the packages the check reports itself as
unavailable and nothing else changes.
"""

import importlib.util
import logging
import os
import sys
import types

import numpy as np

from .model import project_index

log = logging.getLogger("reelwright")
_app = None
_anchor_cache = {}
_error = None


def available():
    return _error is None and importlib.util.find_spec("insightface") is not None and importlib.util.find_spec("onnxruntime") is not None


def error():
    """The last reason face checks could not run, or None."""
    return _error


def retry():
    """Forget the last setup failure, so the next check tries again (a render calls this at
    its start). A failed model download or a fixed install used to stay "unavailable" until ComfyUI restarted."""
    global _error
    _error = None


def score(face):
    """One number for a take's {cast_id: similarity}: the lowest (the character that drifted
    most), or None when nobody was checked."""
    vals = [float(v) for v in (face or {}).values() if isinstance(v, (int, float))]
    return min(vals) if vals else None


# Insightface 0.7.x imports insightface.app.mask_renderer unconditionally, which imports
# albumentations for its face-mask augmentation. A mismatched albumentations/albucore pair ("cannot import name
# 'median_blur' from 'albucore'") then breaks every `import insightface`, although face analysis never uses it
# (insightface 2.x guards that import). Load it once with a stand-in for albumentations, then put sys.modules back.
def _albumentations_stub():
    root = types.ModuleType("albumentations")
    root.__path__ = []
    core = types.ModuleType("albumentations.core")
    core.__path__ = []
    ti = types.ModuleType("albumentations.core.transforms_interface")

    class ImageOnlyTransform:  # base class of insightface's MaskAugmentation; never instantiated here
        def __init__(self, *args, **kwargs):
            raise RuntimeError("albumentations is not usable in this environment")
    ti.ImageOnlyTransform = ImageOnlyTransform
    root.core, core.transforms_interface = core, ti
    return {"albumentations": root, "albumentations.core": core, "albumentations.core.transforms_interface": ti}


def _face_analysis_class():
    try:
        from insightface.app import FaceAnalysis
        return FaceAnalysis
    except ImportError as e:
        tb, files = e.__traceback__, []
        while tb:
            files.append(tb.tb_frame.f_code.co_filename)
            tb = tb.tb_next
        if not any("albumentations" in f or "albucore" in f for f in files) and "albucore" not in str(e) and "albumentations" not in str(e):
            raise
        cause = e
    saved = {k: v for k, v in sys.modules.items() if k == "albumentations" or k.startswith("albumentations.")}
    for k in list(sys.modules):  # the failed attempt can leave half-imported modules behind
        if k in saved or k == "insightface" or k.startswith("insightface."):
            sys.modules.pop(k, None)
    stub = _albumentations_stub()
    sys.modules.update(stub)
    try:
        from insightface.app import FaceAnalysis
    finally:
        for k, v in stub.items():
            if sys.modules.get(k) is v:
                del sys.modules[k]
        sys.modules.update(saved)
    log.warning("Reelwright: insightface's optional albumentations import failed (%s); face checks load without it. "
                "To repair the environment: python -m pip install -U albumentations albucore", cause)
    return FaceAnalysis


def _analyzer():
    global _app, _error
    if _app is None:
        try:
            FaceAnalysis = _face_analysis_class()
            app = FaceAnalysis(name="buffalo_l", allowed_modules=["detection", "recognition"])
            app.prepare(ctx_id=0, det_size=(640, 640))
        except Exception as e:
            _error = "{}: {}".format(type(e).__name__, e)
            raise
        _app = app
    return _app


def _embeddings(bgr):
    return [f.normed_embedding for f in _analyzer().get(bgr)]


def find_faces(bgr):
    """[((x1, y1, x2, y2), score)] of the faces in a picture (BGR array), for the crop window's Find faces."""
    return [(tuple(float(v) for v in f.bbox), float(f.det_score)) for f in _analyzer().get(bgr)]


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
        skip = set(entry.get("skip") or [])
        for aid in c["anchors"]:
            if aid in skip:
                continue
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
        if not faces:  # nobody on screen: says nothing about drift
            continue
        for cid, value in assign_faces(np.stack(faces), anchors).items():
            scores[cid].append(value)
    return {cid: round(sum(v) / len(v), 3) for cid, v in scores.items() if v}


def assign_faces(faces, anchors):
    """{cast_id: similarity} for one frame. Each face found in the frame goes to the
    character it resembles most, each character takes at most one face (its best), so a character who is not in the
    frame gets no value instead of a low one."""
    sims = {cid: (faces @ ref.T).max(axis=1) for cid, ref in anchors.items()}  # best anchor per face
    pairs = sorted(((float(v), cid, k) for cid, row in sims.items() for k, v in enumerate(row)), reverse=True)
    out, used = {}, set()
    for value, cid, k in pairs:
        if cid in out or k in used:
            continue
        out[cid] = value
        used.add(k)
    return out
