"""Load references into tensors and write renders. Runs inside ComfyUI."""

import math
import os
from fractions import Fraction

import numpy as np
import torch
from PIL import Image, ImageOps

from comfy_api.latest import InputImpl, Types
from comfy_extras.nodes_audio import load as load_audio_file

from . import merge, spec

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus"}


def kind_of(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    return None


def describe(path):
    kind = kind_of(path)
    if kind == "image":
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            return {"kind": kind, "duration": 0, "width": im.width, "height": im.height}
    info = merge.probe(path)
    return {"kind": kind, "duration": round(info["duration"], 3), "width": info["width"], "height": info["height"]}


def load_image(path):
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        arr = np.asarray(im, dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None]


# [OLD 2026-11-03 v0.4.0->v0.4.1] square cells, so portrait anchors were letterboxed (about a fifth of each
# cell was background); the grid itself is unchanged (columns = ceil(sqrt(n)), any number of pictures)
# def make_sheet(paths, cell=768):
#     """Pack several anchor pictures into one grid image (one reference slot)."""
#     n = len(paths)
#     cols = math.ceil(math.sqrt(n))
#     rows = math.ceil(n / cols)
#     sheet = Image.new("RGB", (cols * cell, rows * cell), (21, 23, 28))
#     for i, path in enumerate(paths):
#         with Image.open(path) as im:
#             im = ImageOps.exif_transpose(im).convert("RGB")
#             im = ImageOps.contain(im, (cell, cell), Image.LANCZOS)
#             x = (i % cols) * cell + (cell - im.width) // 2
#             y = (i // cols) * cell + (cell - im.height) // 2
#             sheet.paste(im, (x, y))
#     return torch.from_numpy(np.asarray(sheet, dtype=np.float32) / 255.0)[None]
# [/OLD]
def sheet_grid(n):
    """Columns and rows of an anchor sheet: ceil(sqrt(n)) columns, as many rows as needed. No upper limit."""
    cols = max(1, math.ceil(math.sqrt(n)))
    return cols, max(1, math.ceil(n / cols))


def sheet_image(paths, cell=768):
    """The anchor sheet as a PIL image: cells take the median shape of the pictures, each picture centred."""
    pics = []
    for path in paths:
        with Image.open(path) as im:
            pics.append(ImageOps.exif_transpose(im).convert("RGB"))
    ratios = sorted(max(0.5, min(2.0, im.width / max(1, im.height))) for im in pics) or [1.0]
    ratio = ratios[len(ratios) // 2]
    cw, ch = round(cell * math.sqrt(ratio)), round(cell / math.sqrt(ratio))
    cols, rows = sheet_grid(len(pics))
    sheet = Image.new("RGB", (cols * cw, rows * ch), (21, 23, 28))
    for i, im in enumerate(pics):
        im = ImageOps.contain(im, (cw, ch), Image.LANCZOS)
        sheet.paste(im, ((i % cols) * cw + (cw - im.width) // 2, (i // cols) * ch + (ch - im.height) // 2))
    return sheet


def make_sheet(paths, cell=768):
    """Pack several anchor pictures into one grid image (one reference slot)."""
    return torch.from_numpy(np.asarray(sheet_image(paths, cell), dtype=np.float32) / 255.0)[None]


def frame_to_png(frame, path):
    arr = (frame.clamp(0, 1).cpu().numpy() * 255.0 + 0.5).astype(np.uint8)
    Image.fromarray(arr).save(path)


def load_video(path, last_seconds=None, max_seconds=None):
    """Frames at 24 fps [N,H,W,3] and the matching audio dict (or None)."""
    comp = InputImpl.VideoFromFile(path).get_components()
    images = comp.images
    rate = float(comp.frame_rate)
    duration = images.shape[0] / rate
    start = max(0.0, duration - last_seconds) if last_seconds else 0.0
    end = min(duration, start + max_seconds) if max_seconds else duration
    n_out = max(1, int(round((end - start) * spec.FPS)))
    idx = [min(images.shape[0] - 1, int((start + i / spec.FPS) * rate)) for i in range(n_out)]
    frames = images[idx].contiguous()
    audio = None
    if comp.audio is not None:
        audio = slice_audio(comp.audio, start, end)
    return frames, audio


def load_audio(path):
    waveform, sr = load_audio_file(path)
    return {"waveform": waveform[None], "sample_rate": sr}


def slice_audio(audio, start, end):
    sr = audio["sample_rate"]
    w = audio["waveform"]
    a = max(0, int(round(start * sr)))
    b = min(w.shape[-1], int(round(end * sr)))
    return {"waveform": w[..., a:b].contiguous(), "sample_rate": sr}


def save_video(frames, audio, path, crf=16):
    comp = Types.VideoComponents(images=frames, audio=audio, frame_rate=Fraction(spec.FPS))
    InputImpl.VideoFromComponents(comp).save_to(path, format=Types.VideoContainer.MP4,
                                                codec=Types.VideoCodec.H264, crf=crf)


def trim(frames, audio, keep_in_frames, keep_out_frames):
    f = frames[keep_in_frames:keep_out_frames]
    a = slice_audio(audio, keep_in_frames / spec.FPS, keep_out_frames / spec.FPS) if audio is not None else None
    return f, a


# ---- stills for the vision describer (added 2026-11-02 v0.2.0) -------------------------------

def jpeg_bytes(im, max_side=1024):
    import io
    im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def stills_for_vision(path, max_side=1024, frames=3):
    """[(bytes, mime)] for an image, or `frames` evenly spaced frames of a video."""
    import subprocess
    import tempfile
    kind = kind_of(path)
    if kind == "image":
        with Image.open(path) as im:
            return [(jpeg_bytes(im, max_side), "image/jpeg")]
    if kind != "video":
        raise ValueError("Only pictures and videos can be described")
    ff = merge.ffmpeg_bin()
    if not ff:
        raise ValueError("ffmpeg is needed to grab frames from a video")
    dur = max(0.1, float(merge.probe(path)["duration"]))
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(frames):
            t = dur * (i + 0.5) / frames
            dst = os.path.join(tmp, "f{}.png".format(i))
            subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", "{:.3f}".format(t), "-i", path,
                            "-frames:v", "1", dst], check=True)
            with Image.open(dst) as im:
                out.append((jpeg_bytes(im, max_side), "image/jpeg"))
    return out


def list_media(root, query="", kind="", limit=400, scan_cap=20000):
    """Media files under `root`, newest first: [{rel, kind, bytes, mtime}]."""
    terms = [t for t in (query or "").lower().split() if t]
    found, scanned = [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in filenames:
            scanned += 1
            if scanned > scan_cap:
                break
            k = kind_of(name)
            if not k or (kind and kind != "all" and k != kind):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if terms and not all(t in rel.lower() for t in terms):
                continue
            try:
                st = os.stat(full)
            except OSError:
                continue
            found.append({"rel": rel, "kind": k, "bytes": st.st_size, "mtime": int(st.st_mtime)})
        if scanned > scan_cap:
            break
    found.sort(key=lambda x: -x["mtime"])
    return {"files": found[:limit], "total": len(found), "truncated": scanned > scan_cap or len(found) > limit}
