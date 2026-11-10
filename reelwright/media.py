"""Load references into tensors and write renders. Runs inside ComfyUI."""

import math
import os
from fractions import Fraction

import numpy as np
import torch
from comfy_api.latest import InputImpl, Types
from PIL import Image, ImageOps

from . import merge, spec

# Passes in the pass cache and tail clips are written almost losslessly, so the encode of the
# take (and of the cut) is the only one that loses detail
PASS_CRF = 4
# Global -> Long scenes -> pass cache "lossless": RGB H.264 at qp 0 (libx264rgb) with FLAC
# sound in the same .mp4 name, so the pass cache keeps its file names. Read back with load_video(exact=True) the
# frames are the 8-bit frames that were written, bit for bit (ComfyUI's own reader converts RGB streams through
# swscale's float path, which is off by up to about one level). About 4x the size of CRF 4 and much faster to write.
LOSSLESS_CODEC = "libx264rgb"
LOSSLESS_OPTIONS = {"qp": "0", "preset": "ultrafast"}
RGB_PIX_FMTS = ("gbrp", "bgr0", "rgb24", "bgr24", "rgba", "bgra", "gbrap", "0rgb", "rgb0")

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


def frame_positions(n_src, rate, n_out, first=0):
    """Source frame index of each 24 fps output frame, in exact integer arithmetic
    (floor(i * rate / 24)), starting at source frame `first` and never past the last source frame."""
    rate = Fraction(rate).limit_denominator(1001000) if rate else Fraction(spec.FPS)
    if rate <= 0:
        rate = Fraction(spec.FPS)
    last = max(0, int(n_src) - 1)
    return [min(last, int(first) + (i * rate.numerator) // (spec.FPS * rate.denominator)) for i in range(int(n_out))]


def _window(path, start, duration):
    """(components, start actually used) decoding only [start, start + duration) when this
    ComfyUI's VideoFromFile can trim (duration 0 = to the end), else the whole file with start 0."""
    if start > 0 or duration > 0:
        try:
            return InputImpl.VideoFromFile(path, start_time=float(start), duration=float(duration)).get_components(), start
        except TypeError:  # an older ComfyUI: no trim window
            pass
    return InputImpl.VideoFromFile(path).get_components(), 0.0


def _duration(path):
    try:
        return float(InputImpl.VideoFromFile(path).get_duration())
    except Exception:  # noqa: BLE001 - unknown length: decode from the start
        return None


def load_video(path, last_seconds=None, max_seconds=None, last_frames=None, max_frames=None, exact=False, start=0.0):
    """Frames at 24 fps [N,H,W,3] and the matching audio dict (or None).

    Only the part that is needed is decoded. `last_frames` = the last N frames (tails);
    `max_seconds` / `max_frames` = at most that much from the start (references). Frame positions are integers.
    exact=True (files Reelwright wrote itself: pass cache, tail.mp4) reads an RGB stream (a
    lossless pass cache file) with PyAV straight to 8-bit RGB, so the frames are exactly the ones written; other
    streams are read as before.
    Start = where the part read from the start of the file begins (a reference's From), in
    seconds; max_seconds / max_frames then count from there."""
    if last_frames is None and last_seconds:
        last_frames = int(round(float(last_seconds) * spec.FPS))
    if exact and not max_seconds and not max_frames and is_rgb_video(path):
        return load_video_exact(path, last_frames=last_frames)
    if last_frames:
        n = max(1, int(last_frames))
        dur = _duration(path)
        k0 = max(0, int(round(dur * spec.FPS)) - n - spec.FPS // 2) if dur else 0
        start = max(0.0, (k0 - 0.25) / spec.FPS) if k0 else 0.0  # a quarter frame early: frame k0 is the first kept
        comp, used = _window(path, start, 0.0)
        images = comp.images
        if Fraction(comp.frame_rate or spec.FPS) != spec.FPS and images.shape[0]:
            # not 24 fps: resample the decoded part to 24 fps first
            n24 = int((images.shape[0] - 1) * spec.FPS / float(comp.frame_rate)) + 1
            images = images[frame_positions(images.shape[0], comp.frame_rate, n24)]
        m = images.shape[0]
        frames = images[max(0, m - n):].contiguous()
        audio = None
        if comp.audio is not None:
            first_t = (k0 if used else 0) / spec.FPS - used  # the first decoded frame, from where the audio starts
            a = first_t + max(0, m - n) / spec.FPS
            audio = slice_audio(comp.audio, a, a + frames.shape[0] / spec.FPS)
        return frames, audio
    limit = float(max_seconds) if max_seconds else None
    if max_frames:
        limit = min(limit or float("inf"), int(max_frames) / spec.FPS)
    start = max(0.0, float(start or 0.0))
    comp, used = _window(path, start, limit or 0.0)
    images = comp.images
    skip = max(0.0, start - used)  # seconds decoded before `start`
    if skip > 0 and images.shape[0]:
        images = images[min(images.shape[0], int(round(skip * float(comp.frame_rate or spec.FPS)))):]
    if not images.shape[0]:
        raise ValueError("no video frames could be decoded from {}{}".format(
            os.path.basename(path), " after {:.3f} s".format(start) if start else ""))
    rate = Fraction(comp.frame_rate or spec.FPS)
    src_seconds = images.shape[0] / float(rate) if images.shape[0] else 0.0
    seconds = min(src_seconds, limit) if limit else src_seconds
    n_out = max(1, int(round(seconds * spec.FPS)))
    if max_frames:
        n_out = min(n_out, int(max_frames))
    if images.shape[0]:  # never past the last decoded frame
        n_out = min(n_out, int((images.shape[0] - 1) * spec.FPS / float(rate)) + 1)
    frames = images[frame_positions(images.shape[0], rate, n_out)].contiguous()
    audio = None
    if comp.audio is not None:
        audio = slice_audio(comp.audio, skip, skip + n_out / spec.FPS)
    return frames, audio


def load_audio(path, max_seconds=None, start=0.0):
    """The audio file as {waveform [1,C,S], sample_rate}; with `max_seconds` only its start.
    Start = where to begin (a reference's From), in seconds; max_seconds counts from there."""
    from comfy_extras.nodes_audio import load as load_audio_file
    waveform, sr = load_audio_file(path)
    a = max(0, int(round(float(start or 0.0) * sr)))
    waveform = waveform[..., a:a + int(round(float(max_seconds) * sr))] if max_seconds else waveform[..., a:]
    return {"waveform": waveform[None], "sample_rate": sr}


def slice_audio(audio, start, end):
    sr = audio["sample_rate"]
    w = audio["waveform"]
    a = max(0, int(round(start * sr)))
    b = min(w.shape[-1], int(round(end * sr)))
    return {"waveform": w[..., a:b].contiguous(), "sample_rate": sr}


def save_video(frames, audio, path, crf=16, lossless=False):
    """lossless: see save_video_lossless."""
    if lossless:
        return save_video_lossless(frames, audio, path)
    comp = Types.VideoComponents(images=frames, audio=audio, frame_rate=Fraction(spec.FPS))
    InputImpl.VideoFromComponents(comp).save_to(path, format=Types.VideoContainer.MP4,
                                                codec=Types.VideoCodec.H264, crf=crf)


# ---- lossless pass cache ---------------------------------------------------------------------------------------------

def to_u8(frames):
    """Float frames [N,H,W,3] in 0..1 as uint8, rounded (the lossless writer's 8-bit frames)."""
    return (frames[..., :3].float().clamp(0, 1) * 255.0 + 0.5).to(torch.uint8)


def save_video_lossless(frames, audio, path):
    """An .mp4 holding RGB H.264 at qp 0 (LOSSLESS_CODEC, bit-exact 8-bit RGB) and the sound as FLAC (24-bit), at
    24 fps. load_video(exact=True) gives the frames back exactly (to_u8(frames) / 255)."""
    import av
    n, h, w = int(frames.shape[0]), int(frames.shape[1]), int(frames.shape[2])
    with av.open(path, "w", format="mp4") as out:
        vs = out.add_stream(LOSSLESS_CODEC, rate=spec.FPS)
        vs.width, vs.height = w, h
        vs.pix_fmt = "rgb24"
        vs.options = dict(LOSSLESS_OPTIONS)
        astream, wave, layout = None, None, None
        if audio is not None and audio.get("waveform") is not None and audio["waveform"].shape[-1]:
            sr = int(audio["sample_rate"])
            wave = audio["waveform"][0].float().clamp(-1.0, 1.0)
            wave = wave[:, :math.ceil(sr / spec.FPS * n)]  # as long as the picture, like ComfyUI's writer
            layout = {1: "mono", 2: "stereo"}.get(int(wave.shape[0]), "stereo")
            if layout == "stereo" and wave.shape[0] != 2:
                wave = wave[:2] if wave.shape[0] > 2 else wave.repeat(2, 1)
            astream = out.add_stream("flac", rate=sr, layout=layout)
            astream.format = "s32"
        for k in range(n):
            img = to_u8(frames[k]).cpu().numpy()
            for packet in vs.encode(av.VideoFrame.from_ndarray(img, format="rgb24")):
                out.mux(packet)
        for packet in vs.encode(None):
            out.mux(packet)
        if astream is not None:
            af = av.AudioFrame.from_ndarray(np.ascontiguousarray(wave.cpu().numpy()), format="fltp", layout=layout)
            af.sample_rate = int(audio["sample_rate"])
            af.pts = 0
            for packet in astream.encode(af):
                out.mux(packet)
            for packet in astream.encode(None):
                out.mux(packet)


def is_rgb_video(path):
    """True when the file's first video stream is RGB (a lossless pass cache file or tail clip)."""
    import av
    try:
        with av.open(path) as c:
            v = c.streams.video[0] if c.streams.video else None
            return v is not None and (v.codec_context.pix_fmt or "") in RGB_PIX_FMTS
    except Exception:  # noqa: BLE001 - not readable here: the normal reader reports it
        return False


def load_video_exact(path, last_frames=None):
    """(frames [N,H,W,3] float32 = 8-bit / 255, audio dict or None) of a file Reelwright wrote at 24 fps, decoded
    with PyAV to rgb24 (no float conversion in swscale); last_frames = only the last N frames and their sound."""
    import collections

    import av
    keep = collections.deque(maxlen=int(last_frames)) if last_frames else []
    chunks, sr = [], None
    m = 0
    with av.open(path) as c:
        streams = [c.streams.video[0]] + ([c.streams.audio[0]] if c.streams.audio else [])
        resampler = None
        for packet in c.demux(*streams):
            if packet.stream.type == "video":
                for frame in packet.decode():
                    keep.append(frame.to_ndarray(format="rgb24"))
                    m += 1
            else:
                for frame in packet.decode():
                    if resampler is None:
                        sr = int(frame.sample_rate)
                        resampler = av.AudioResampler(format="fltp", layout=frame.layout.name, rate=sr)
                    for rf in resampler.resample(frame):
                        chunks.append(rf.to_ndarray())
        if resampler is not None:
            for rf in resampler.resample(None):
                chunks.append(rf.to_ndarray())
    if not keep:
        raise ValueError("no video frames could be decoded from {}".format(os.path.basename(path)))
    arr = list(keep)
    frames = torch.empty((len(arr),) + tuple(arr[0].shape), dtype=torch.float32)
    for k, a in enumerate(arr):
        frames[k] = torch.from_numpy(a).float().div_(255.0)
    audio = None
    if chunks:
        wave = torch.from_numpy(np.concatenate(chunks, axis=1)).float()[None]
        audio = {"waveform": wave, "sample_rate": sr}
        if last_frames:
            audio = slice_audio(audio, (m - len(arr)) / spec.FPS, m / spec.FPS)
    return frames, audio


def save_video_atomic(frames, audio, path, crf=16, lossless=False):
    """Write to a temporary name next to `path`, then move it into place, so a stopped or
    failed write never leaves a half-written file under the final name. lossless: see save_video_lossless."""
    tmp = "{}.{}.partial.mp4".format(os.path.splitext(path)[0], os.getpid())
    try:
        save_video(frames, audio, tmp, crf=crf, lossless=lossless)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def trim(frames, audio, keep_in_frames, keep_out_frames):
    f = frames[keep_in_frames:keep_out_frames]
    a = slice_audio(audio, keep_in_frames / spec.FPS, keep_out_frames / spec.FPS) if audio is not None else None
    return f, a


# ---- stills for the vision describer ---------------------------------------------------------

def jpeg_bytes(im, max_side=1024):
    import io
    im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def stills_for_vision(path, max_side=1024, frames=3):
    """[(bytes, mime)] for an image, or `frames` evenly spaced frames of a video."""
    kind = kind_of(path)
    if kind == "image":
        with Image.open(path) as im:
            return [(jpeg_bytes(im, max_side), "image/jpeg")]
    if kind != "video":
        raise ValueError("Only pictures and videos can be described")
    return vision_frames(path, 0.0, None, frames, max_side)


def _ffmpeg_for_vision():
    ff = merge.ffmpeg_bin()
    if not ff:
        raise ValueError("ffmpeg is needed to read a video for the LLM")
    return ff


def clip_range(path, start=0.0, end=None):
    """(start, end) of the part of a video from `start` to `end` (None: its end), inside the video."""
    dur = max(0.1, float(merge.probe(path)["duration"]))
    start = min(max(0.0, float(start or 0.0)), max(0.0, dur - 0.05))
    end = dur if end is None or float(end) <= start else min(dur, float(end))
    return start, end


def vision_frames(path, start=0.0, end=None, n=3, max_side=1024):
    """[(bytes, mime)]: n frames evenly spaced over the part of a video from start to end (None: its end), as JPEG."""
    import subprocess
    import tempfile
    ff = _ffmpeg_for_vision()
    start, end = clip_range(path, start, end)
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(max(1, int(n))):
            t = start + (end - start) * (i + 0.5) / max(1, int(n))
            dst = os.path.join(tmp, "f{}.png".format(i))
            subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", "{:.3f}".format(t), "-i", path,
                            "-frames:v", "1", dst], check=True)
            with Image.open(dst) as im:
                out.append((jpeg_bytes(im, max_side), "image/jpeg"))
    return out


def vision_clip(path, start=0.0, end=None, max_side=640, fps=8):
    """(bytes, "video/mp4"): the part of a video from start to end (None: its end), small enough to send to a
    vision LLM: no sound, at most max_side pixels on its long side, fps frames a second, H.264."""
    import subprocess
    import tempfile
    ff = _ffmpeg_for_vision()
    start, end = clip_range(path, start, end)
    scale = "scale={m}:{m}:force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2".format(m=int(max_side))
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "clip.mp4")
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-ss", "{:.3f}".format(start), "-i", path,
                        "-t", "{:.3f}".format(end - start), "-an", "-vf", "fps={},{}".format(int(fps), scale),
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", dst], check=True)
        with open(dst, "rb") as f:
            return f.read(), "video/mp4"


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
