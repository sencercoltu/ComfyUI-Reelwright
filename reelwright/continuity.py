"""Optional identity drift check: face similarity between a render and its anchors.

Needs the `insightface` and `onnxruntime` packages. The first use downloads the
buffalo_l face model into ~/.insightface (a one-time download the user enables
by switching face check on). Without the packages the check reports itself as
unavailable and nothing else changes.
"""

import importlib.util
import logging  # added 2026-11-03 v0.4.1
import os
import sys  # added 2026-11-03 v0.4.1
import types  # added 2026-11-03 v0.4.1

import numpy as np

from .model import project_index

log = logging.getLogger("reelwright")  # added 2026-11-03 v0.4.1
_app = None
_anchor_cache = {}
_error = None  # added 2026-11-03 v0.4.1: why insightface could not be loaded (shown in Global → About)


# [OLD 2026-11-03 v0.4.0->v0.4.1] installed was taken to mean usable; a broken dependency only showed up after a render, as a crash
# def available():
#     return importlib.util.find_spec("insightface") is not None and importlib.util.find_spec("onnxruntime") is not None
def available():
    return _error is None and importlib.util.find_spec("insightface") is not None and importlib.util.find_spec("onnxruntime") is not None


def error():
    """The last reason face checks could not run, or None."""
    return _error


# added 2026-11-03 v0.4.1: insightface 0.7.x imports insightface.app.mask_renderer unconditionally, which imports
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
        # [OLD 2026-11-03 v0.4.0->v0.4.1] from insightface.app import FaceAnalysis
        try:
            FaceAnalysis = _face_analysis_class()
        except Exception as e:
            _error = "{}: {}".format(type(e).__name__, e)
            raise
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
