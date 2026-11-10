"""Find people, faces and things in a picture, so a part of it can be cropped into a picture of its own (an anchor
of one person from a group photo).

Faces come from insightface (the face check's model) when it is installed; anything named ("dog, person, tea cup")
comes from Grounding DINO, an open-vocabulary detector that transformers (a ComfyUI requirement) runs. Its weights
(IDEA-Research/grounding-dino-tiny, about 700 MB) are downloaded on request into ComfyUI's models folder, under
reelwright/grounding-dino-tiny. Boxes are [x, y, w, h] as parts of the picture's width and height (0..1), on the
picture as it is shown (EXIF rotation applied)."""

import logging
import os
import re
import threading
import time

import numpy as np
from PIL import Image, ImageOps

log = logging.getLogger("reelwright")

DETECTOR_REPO = "IDEA-Research/grounding-dino-tiny"
DETECTOR_BYTES = 690_000_000  # about the size of its files, for the download progress
DETECTOR_FILES = ["*.json", "*.safetensors", "*.txt"]
BOX_THRESHOLD = 0.3
TEXT_THRESHOLD = 0.25
MAX_BOXES = 24
SMALL_SIDE = 400  # a crop whose short side is smaller reaches H3 blurry

_lock = threading.Lock()
_model = None  # (processor, model, folder)
_download = {"state": "idle", "error": "", "started": 0.0}


def models_dir():
    import folder_paths
    return os.path.join(folder_paths.models_dir, "reelwright", "grounding-dino-tiny")


def detector_ready(folder=None):
    folder = folder or models_dir()
    return os.path.isfile(os.path.join(folder, "config.json")) and any(
        f.endswith(".safetensors") for f in os.listdir(folder)) if os.path.isdir(folder) else False


def _folder_bytes(folder):
    total = 0
    for root, _dirs, files in os.walk(folder):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def status():
    """What Find can do now: faces (insightface) and objects (the detector, downloaded or being downloaded)."""
    from . import continuity
    folder = models_dir()
    ready = detector_ready(folder)
    state = "done" if ready and _download["state"] != "downloading" else _download["state"]
    out = {"faces": {"ready": continuity.available(), "error": continuity.error() or ""},
           "objects": {"ready": ready, "model": DETECTOR_REPO, "folder": folder, "state": state,
                       "error": "" if state == "done" else _download["error"], "bytes": DETECTOR_BYTES}}
    if _download["state"] == "downloading":
        out["objects"]["done"] = min(_folder_bytes(folder), DETECTOR_BYTES)
    return out


def _fetch():
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(DETECTOR_REPO, local_dir=models_dir(), allow_patterns=DETECTOR_FILES)
        _download.update(state="done" if detector_ready() else "error",
                         error="" if detector_ready() else "the download finished without the model's files")
    except Exception as e:  # noqa: BLE001 - reported to the editor
        log.warning("Reelwright: detector download failed: %s", e)
        _download.update(state="error", error="{}: {}".format(type(e).__name__, e)[:300])


def download():
    """Start downloading the detector in the background (status() reports it); nothing when it is there or on its way."""
    if detector_ready() or _download["state"] == "downloading":
        return status()
    os.makedirs(models_dir(), exist_ok=True)
    _download.update(state="downloading", error="", started=time.time())
    threading.Thread(target=_fetch, name="reelwright-detector-download", daemon=True).start()
    return status()


def load_rgb(path):
    with Image.open(path) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def _clamp_box(x1, y1, x2, y2, w, h):
    """[x, y, w, h] as parts of the picture, inside it."""
    x1, x2 = max(0.0, min(float(x1), w)), max(0.0, min(float(x2), w))
    y1, y2 = max(0.0, min(float(y1), h)), max(0.0, min(float(y2), h))
    return [round(x1 / w, 4), round(y1 / h, 4), round(max(0.0, x2 - x1) / w, 4), round(max(0.0, y2 - y1) / h, 4)]


def head_and_shoulders(x1, y1, x2, y2, w, h):
    """A face box widened to the head, hair and shoulders: what an identity anchor wants."""
    fw, fh = x2 - x1, y2 - y1
    return _clamp_box(x1 - 0.7 * fw, y1 - 0.7 * fh, x2 + 0.7 * fw, y2 + 1.1 * fh, w, h)


def find_faces(path):
    """[{box, label: "face", score}], the face's head and shoulders, largest first; insightface's detector."""
    from . import continuity
    im = load_rgb(path)
    w, h = im.size
    faces = continuity.find_faces(np.asarray(im)[:, :, ::-1].copy())
    out = [{"box": head_and_shoulders(*bbox, w, h), "label": "face", "score": round(float(score), 3)}
           for bbox, score in faces]
    return sorted(out, key=lambda x: -x["box"][2] * x["box"][3])[:MAX_BOXES]


def _prompt(queries):
    """Grounding DINO's text: lower case, one phrase per thing, each ending with a full stop ("a dog. tea cup.")."""
    words = [" ".join(q.lower().split()) for q in queries]
    return " ".join(w.rstrip(".") + "." for w in words if w)


def _label(text, queries):
    """The thing a box was found for: the query its words match best ("a dog" -> "dog")."""
    t = " ".join(re.sub(r"\[\w+\]", " ", str(text or "").lower()).replace(".", " ").split())
    for article in ("a ", "an ", "the "):
        if t.startswith(article):
            t = t[len(article):]
    best = max(queries, key=lambda q: len(set(q.lower().split()) & set(t.split())), default="")
    return best if best and set(best.lower().split()) & set(t.split()) else (t or "thing")


def _iou(a, b):
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw, ih = max(0.0, min(ax2, bx2) - max(a[0], b[0])), max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def _dedupe(found, iou=0.7):
    """The best box of each group of near-identical boxes with the same label."""
    keep = []
    for f in sorted(found, key=lambda x: -x["score"]):
        if all(k["label"] != f["label"] or _iou(k["box"], f["box"]) < iou for k in keep):
            keep.append(f)
    return keep


def _detector(folder):
    global _model
    if _model is None or _model[2] != folder:
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        processor = AutoProcessor.from_pretrained(folder)
        model = AutoModelForZeroShotObjectDetection.from_pretrained(folder).eval()
        _model = (processor, model, folder)
    return _model


def _device():
    try:
        import comfy.model_management as mm
        return mm.get_torch_device()
    except Exception:  # noqa: BLE001 - outside ComfyUI (tests)
        return "cpu"


def _post(processor, outputs, input_ids, size, box_threshold, text_threshold):
    """The processor's boxes: transformers 4.51+ takes `threshold`, older versions `box_threshold`."""
    try:
        return processor.post_process_grounded_object_detection(
            outputs, input_ids, threshold=box_threshold, text_threshold=text_threshold, target_sizes=[size])[0]
    except TypeError:
        return processor.post_process_grounded_object_detection(
            outputs, input_ids, box_threshold=box_threshold, text_threshold=text_threshold, target_sizes=[size])[0]


def find_objects(path, queries, folder=None, box_threshold=BOX_THRESHOLD, text_threshold=TEXT_THRESHOLD):
    """[{box, label, score}] for each thing named in queries (["dog", "person", "tea cup"]), best first."""
    import torch
    queries = [" ".join(str(q).split()) for q in queries if str(q).strip()][:12]
    if not queries:
        raise ValueError("Name what to find, for example: person, dog, tea cup")
    folder = folder or models_dir()
    if not detector_ready(folder):
        raise ValueError("The object finder is not downloaded yet (about 700 MB): press Download in the crop window")
    im = load_rgb(path)
    w, h = im.size
    with _lock:
        processor, model, _ = _detector(folder)
        device = _device()
        try:
            model.to(device)
            inputs = processor(images=im, text=_prompt(queries), return_tensors="pt").to(device)
            with torch.no_grad():
                outputs = model(**inputs)
            r = _post(processor, outputs, inputs["input_ids"], (h, w), box_threshold, text_threshold)
        finally:
            model.to("cpu")
            try:
                import comfy.model_management as mm
                mm.soft_empty_cache()
            except Exception:  # noqa: BLE001 - outside ComfyUI
                pass
    labels = r.get("text_labels") if r.get("text_labels") is not None else r.get("labels")
    found = []
    for box, score, text in zip(r["boxes"].tolist(), r["scores"].tolist(), list(labels or [])):
        b = _clamp_box(*box, w, h)
        if b[2] > 0.005 and b[3] > 0.005:
            found.append({"box": b, "label": _label(text, queries), "score": round(float(score), 3)})
    return _dedupe(found)[:MAX_BOXES]


def faces_with_detector(path, folder=None):
    """Faces from the object finder (when insightface is not installed), widened to head and shoulders."""
    w, h = load_rgb(path).size
    found = find_objects(path, ["face"], folder)
    for f in found:
        x, y, bw, bh = f["box"]
        f["box"] = head_and_shoulders(x * w, y * h, (x + bw) * w, (y + bh) * h, w, h)
        f["label"] = "face"
    return found


def crop(path, box, dst):
    """Cut box ([x, y, w, h], parts of the picture) out of the picture at path into a PNG at dst; (width, height)."""
    im = load_rgb(path)
    w, h = im.size
    x, y, bw, bh = (float(v) for v in box)
    x1, y1 = int(round(max(0.0, min(1.0, x)) * w)), int(round(max(0.0, min(1.0, y)) * h))
    x2, y2 = int(round(max(0.0, min(1.0, x + bw)) * w)), int(round(max(0.0, min(1.0, y + bh)) * h))
    if x2 - x1 < 8 or y2 - y1 < 8:
        raise ValueError("The box is too small to crop (at least 8 pixels each way)")
    out = im.crop((x1, y1, x2, y2))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp.png"
    out.save(tmp, format="PNG")
    os.replace(tmp, dst)
    return out.size
