"""RefMods: saved MiniMax H3 references made with ComfyUI-MiniMaxH3Mod (github.com/Luisacaotica/ComfyUI-MiniMaxH3Mod).

A RefMod is a .safetensors file in a refmods folder (models/refmods, a folder registered as "refmods" in
extra_model_paths.yaml, or the older models/audio_refmods): a VAE latent with JSON metadata in the file's header
(refmod_meta). It holds one reference, kind image ([1,24,1,H,W]), video ([1,24,T,H,W], such as stacked photos) or audio
([1,32,2,T]), in the tensor "latent", or a bundle of several (kind "bundle", "members", tensors ref_0, ref_1, ...).
Older files keep the metadata under audio_refmod_meta or in a .json beside the file. Reelwright reads the files
itself: the pack makes them, rendering needs only the files.

A cast member's look RefMod and voice RefMod (model.py: look_parts, voice_parts) are sent like any reference. At
render, PassMods joins them to what MiniMaxH3ReferenceToVideo sends, in the order the prompt numbers them: the DiT gets
the latent (below strength 1 mixed toward a blurred copy, as the pack's Apply node does) and Qwen a picture or frames
decoded from it under the same <Picture n> / <Video n> / <Audio n> label (as the pack's Text Encode node does).
"""

import json
import logging
import math
import os
import struct
import threading

from . import model as _model

log = logging.getLogger("reelwright")

META_KEYS = ("refmod_meta", "audio_refmod_meta")
SKIP_DIRS = {"graph_presets", ".git", "__pycache__"}
MAX_FILES = 4000          # a refmods folder scanned for the list holds at most this many .safetensors
MAX_HEADER = 16 << 20     # bytes of a safetensors header
REFERENCE_FPS = 24        # frames per second of a decoded video RefMod (Qwen sees it at 2 fps)
BLUR_FACTOR = 8

_lock = threading.Lock()
_headers = {}             # (path, size, mtime_ns) -> header dict
_listing = {"key": None, "value": []}


def roots():
    """The refmods folders, in the order a name is looked up (the first that has it wins)."""
    try:
        import folder_paths
    except ImportError:
        return []
    dirs = []
    try:
        dirs += list(folder_paths.get_folder_paths("refmods"))
    except Exception:  # noqa: BLE001 - not registered: ComfyUI-MiniMaxH3Mod is not installed
        pass
    base = getattr(folder_paths, "models_dir", "")
    for d in (os.path.join(base, "refmods"), os.path.join(base, "audio_refmods")):
        if base and d not in dirs:
            dirs.append(d)
    return [d for d in dirs if os.path.isdir(d)]


# ---- reading a file's header ----------------------------------------------------------------------------------------
def _header(path):
    """The JSON header of a safetensors file (tensor names -> dtype, shape, offsets; "__metadata__")."""
    st = os.stat(path)
    key = (path, st.st_size, st.st_mtime_ns)
    with _lock:
        if key in _headers:
            return _headers[key]
    with open(path, "rb") as f:
        raw = f.read(8)
        if len(raw) != 8:
            raise ValueError("not a safetensors file")
        n = struct.unpack("<Q", raw)[0]
        if n <= 0 or n > MAX_HEADER:
            raise ValueError("not a safetensors file")
        head = json.loads(f.read(n).decode("utf-8"))
    if not isinstance(head, dict):
        raise ValueError("not a safetensors file")
    with _lock:
        if len(_headers) > 1024:
            _headers.clear()
        _headers[key] = head
    return head


def _meta(path, head):
    """The RefMod metadata of a file: from its header, else the .json beside it; None when it has none."""
    md = head.get("__metadata__") if isinstance(head.get("__metadata__"), dict) else {}
    for k in META_KEYS:
        if isinstance(md.get(k), str):
            try:
                m = json.loads(md[k])
            except ValueError:
                return None
            return m if isinstance(m, dict) else None
    side = path[:-len(".safetensors")] + ".json"
    if os.path.isfile(side):
        try:
            with open(side, encoding="utf-8") as f:
                m = json.load(f)
            return m if isinstance(m, dict) else None
        except (OSError, ValueError):
            return None
    return None


def _tensor_key(meta, head, i):
    """The tensor of member i: ref_i in a bundle, else "latent" (or the file's only tensor)."""
    if meta.get("kind") == "bundle":
        return "ref_{}".format(i)
    if "latent" in head:
        return "latent"
    keys = [k for k in head if k != "__metadata__"]
    return keys[0] if len(keys) == 1 else "latent"


def _member(kind, shape):
    """{"kind", "t", "h", "w"} of one reference from its kind and tensor shape; kind "" when Reelwright cannot send it."""
    shape = list(shape or [])
    if kind == "audio":
        ok = len(shape) == 4 and shape[:3] == [1, 32, 2] and shape[3] > 0
        return {"kind": "audio" if ok else "", "t": shape[3] if ok else 1, "h": 0, "w": 0}
    ok = kind in ("image", "video") and len(shape) == 5 and shape[:2] == [1, 24] and all(x > 0 for x in shape[2:]) \
        and shape[3] % 2 == 0 and shape[4] % 2 == 0 and (kind != "image" or shape[2] == 1)
    if not ok:
        return {"kind": "", "t": 1, "h": 0, "w": 0}
    return {"kind": kind, "t": shape[2], "h": shape[3], "w": shape[4]}


def members_of(meta, head):
    """The references a RefMod file holds, in order ([{"kind", "t", "h", "w"}]), as model.norm_refmod keeps them."""
    raw = meta.get("members") if meta.get("kind") == "bundle" else [meta]
    out = []
    for i, m in enumerate(raw if isinstance(raw, list) else []):
        if i >= _model.REFMOD_MAX_MEMBERS:
            break
        kind = m.get("kind") if isinstance(m, dict) else ""
        t = head.get(_tensor_key(meta, head, i))
        out.append(_member(kind, t.get("shape") if isinstance(t, dict) else None))
    return out


def _read(path):
    """(meta, members) of a RefMod file, or None when it is not one."""
    try:
        head = _header(path)
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    meta = _meta(path, head)
    if not meta or meta.get("kind") not in ("image", "video", "audio", "bundle"):
        return None
    return meta, members_of(meta, head)


# ---- names ------------------------------------------------------------------------------------------------------------
def _check_name(name):
    name = _model.refmod_name(name)
    parts = name.split("/")
    if not name or ":" in name or any(x in ("", ".", "..") for x in parts) or any(x in SKIP_DIRS for x in parts):
        raise ValueError("RefMod {!r}: expected a name under a refmods folder, like characters/birten".format(name))
    return name


def find(name):
    """The file of RefMod `name` (the first refmods folder that has it); FileNotFoundError when none does."""
    name = _check_name(name)
    for d in roots():
        root = os.path.realpath(d)
        path = os.path.join(d, *name.split("/")) + ".safetensors"
        target = os.path.realpath(path)
        try:
            inside = os.path.commonpath((root, target)) == root
        except ValueError:
            inside = False
        if inside and os.path.isfile(path):
            return path
    raise FileNotFoundError("RefMod {} is not in models/refmods ({})".format(
        name, ", ".join(roots()) or "no refmods folder"))


def summary(name):
    """The members RefMod `name` holds now, or None when it is missing or no RefMod."""
    try:
        r = _read(find(name))
    except (FileNotFoundError, ValueError):
        return None
    return r[1] if r else None


def digest(name):
    """What a pass key holds for RefMod `name`: the file's sha1, "missing:<name>" without one."""
    from . import cache
    try:
        return cache.file_digest(find(name))
    except (FileNotFoundError, ValueError):
        return "missing:" + str(name)


def list_refmods():
    """Every RefMod in the refmods folders, for the editor: [{"name", "kind", "members", "description"}] by name."""
    dirs = roots()
    found, sig = [], []
    for d in dirs:
        for top, subdirs, files in os.walk(d):
            subdirs[:] = sorted(s for s in subdirs if s not in SKIP_DIRS and not s.startswith("."))
            for fn in sorted(files):
                if not fn.endswith(".safetensors") or len(found) >= MAX_FILES:
                    continue
                path = os.path.join(top, fn)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                name = os.path.relpath(path[:-len(".safetensors")], d).replace(os.sep, "/")
                found.append((name, path))
                sig.append((path, st.st_size, st.st_mtime_ns))
    key = (tuple(dirs), tuple(sig))
    with _lock:
        if _listing["key"] == key:
            return _listing["value"]
    out, seen = [], set()
    for name, path in found:
        if name in seen:
            continue
        seen.add(name)  # the first folder that has a name is the one find() uses
        r = _read(path)
        if not r:
            continue
        meta, members = r
        out.append({"name": name, "kind": meta.get("kind"), "members": members,
                    "description": str(meta.get("description") or meta.get("concept_type") or "")[:200]})
    out.sort(key=lambda x: x["name"].lower())
    with _lock:
        _listing.update(key=key, value=out)
    return out


# ---- the checks a plan makes (analysis.analyze) -----------------------------------------------------------------------
def issues(p, builds, read=None):
    """Errors for the RefMods the passes send: the file is gone, or no longer holds what it held when it was picked
    (the prompt numbers its references by what the project keeps). read: name -> members or None (summary)."""
    read = read or summary
    cast = {c["id"]: c for c in p["cast"]}
    titles = {s["id"]: "{:02d} {}".format(i + 1, s["title"]) for i, s in enumerate(p["scenes"])}
    out, known, said = [], {}, set()
    for sid, bs in builds.items():
        for b in bs:
            for x in (b.get("images") or []) + (b.get("videos") or []) + (b.get("audios") or []):
                m = x.get("refmod") if isinstance(x, dict) else None
                c = cast.get(x.get("cast")) if m else None
                if not c:
                    continue
                which = "voice_refmod" if m["kind"] == "audio" else "refmod"
                kept = c[which]["members"]
                if m["name"] not in known:
                    known[m["name"]] = read(m["name"])
                now = known[m["name"]]
                if now == kept or (sid, c["id"], which) in said:
                    continue
                said.add((sid, c["id"], which))
                what = "voice RefMod" if which == "voice_refmod" else "RefMod"
                if now is None:
                    msg = "{}: {}'s {} {} is not in models/refmods (Cast -> {})".format(
                        titles.get(sid, sid), c["name"], what, m["name"], c["name"])
                else:
                    msg = "{}: {}'s {} {} has changed since it was picked: press Update under Cast -> {} -> RefMod".format(
                        titles.get(sid, sid), c["name"], what, m["name"], c["name"])
                out.append({"level": "error", "message": msg, "scene_id": sid, "code": "refmod"})
    return out


# ---- render -------------------------------------------------------------------------------------------------------------
def load(name, member, expect=None):
    """The latent of member `member` of RefMod `name` (a CPU float tensor). expect: the member as the project keeps
    it; a file that no longer holds that raises ValueError."""
    from safetensors import safe_open
    path = find(name)
    r = _read(path)
    if not r:
        raise ValueError("RefMod {} has no RefMod metadata".format(name))
    meta, members = r
    if not 0 <= member < len(members) or not members[member]["kind"]:
        raise ValueError("RefMod {} has no reference {} that Reelwright can send".format(name, member + 1))
    if expect is not None and any(members[member][k] != expect.get(k) for k in ("kind", "t", "h", "w")):
        raise ValueError("RefMod {} has changed since it was picked: press Update under Cast -> RefMod".format(name))
    head = _header(path)
    with safe_open(path, framework="pt", device="cpu") as f:
        z = f.get_tensor(_tensor_key(meta, head, member)).clone()
    return z.float()


def blurred(z, factor=BLUR_FACTOR):
    """A heavily low-passed copy of a latent (ComfyUI-MiniMaxH3Mod's _blur_latent): what a reference below strength 1
    is mixed toward, so it stays a plausible latent while losing its detail."""
    import torch.nn.functional as F
    if z.dim() == 4:  # audio [1, 32, 2, T]
        b, c, s, t = z.shape
        if t <= 1:
            return z
        flat = z.reshape(b * c * s, 1, t).float()
        down = F.adaptive_avg_pool1d(flat, max(1, t // factor))
        return F.interpolate(down, size=t, mode="linear", align_corners=False).reshape_as(z).to(z.dtype)
    t, h, w = z.shape[2], z.shape[3], z.shape[4]
    down = F.adaptive_avg_pool3d(z.float(), (t, max(1, h // factor), max(1, w // factor)))
    return F.interpolate(down, size=(t, h, w), mode="trilinear", align_corners=False).to(z.dtype)


def weakened(z, strength):
    """strength * z + (1 - strength) * blurred(z); z itself at strength 1."""
    s = min(1.0, max(0.0, float(strength)))
    return z if s >= 1.0 else s * z + (1.0 - s) * blurred(z)


def _pixels(vae, z):
    """Frames decoded from a video latent, as [frames, height, width, 3]."""
    px = vae.decode(z)
    if px.ndim == 5 and px.shape[0] == 1:
        px = px[0]
    if px.ndim != 4 or px.shape[-1] != 3 or px.shape[0] < 1:
        raise ValueError("the H3 video VAE decoded a RefMod to {}, not frames".format(tuple(px.shape)))
    return px


def prepare(entry, vae, load_fn=None):
    """(item for the text encoder, block for the DiT) of one RefMod member a pass sends (an entry's "refmod")."""
    z = (load_fn or load)(entry["name"], entry["member"], entry)
    z = weakened(z, entry["strength"])
    if entry["kind"] == "audio":
        return {"type": "audio"}, {"kind": "audio", "ref_audio_t": int(z.shape[-1]), "audio_latent": z}
    px = _pixels(vae, z)
    h, w = int(z.shape[3]), int(z.shape[4])
    if entry["kind"] == "image":
        return {"type": "image", "data": px[:1].cpu().clone()}, \
            {"kind": "image", "latent_h": h, "latent_w": w, "latent": z}
    times = [i / 2.0 for i in range(max(1, math.ceil(px.shape[0] * 2 / REFERENCE_FPS)))]
    picks = [min(int(round(t * REFERENCE_FPS)), px.shape[0] - 1) for t in times]
    return {"type": "video", "data": px[picks].cpu(), "timestamps": times}, \
        {"kind": "video", "latent_t": int(z.shape[2]), "latent_h": h, "latent_w": w, "ref_audio_t": 0, "latent": z,
         "audio_latent": None}


def sends(build):
    """Does a pass build send a RefMod?"""
    return any(isinstance(x, dict) and x.get("refmod") for k in ("images", "videos", "audios")
               for x in build.get(k) or [])


class PassMods:
    """The RefMods of one pass, joined to what MiniMaxH3ReferenceToVideo sends.

    That node presents its references in a fixed order (pictures; videos, each after its own sound when it has one;
    then audio) to the text encoder (clip.tokenize(..., minimax_ref_items=...)) and to the DiT (conditioning
    "minimax_refs", one block per picture, video and audio in the same order). The build lists the pass's references
    in that order with the RefMods among them, so the prompt numbers both alike. clip() wraps the CLIP so the
    tokenizer gets the RefMods at their places; attach() puts their blocks at the same places in the conditioning.

    sounds: indexes k of build["videos"] whose own sound the node was given (ref_video_audio_k)."""

    def __init__(self, build, sounds, vae, load_fn=None):
        prep = {}

        def slot(x):
            if not (isinstance(x, dict) and x.get("refmod")):
                return None
            m = x["refmod"]
            key = (m["name"], m["member"], m["strength"])
            if key not in prep:
                prep[key] = prepare(m, vae, load_fn)
            return prep[key]
        self.images = [slot(x) for x in build.get("images") or []]
        self.videos = [(slot(x), k in sounds) for k, x in enumerate(build.get("videos") or [])]
        self.audios = [slot(x) for x in build.get("audios") or []]
        self.tokenized = False

    def clip(self, clip):
        return _ClipWithMods(clip, self)

    @staticmethod
    def _out_of_step(what):
        return RuntimeError("Reelwright: the H3 node's {} do not line up with the pass's references; the RefMods "
                            "cannot be placed (update Reelwright)".format(what))

    def items(self, native):
        """The tokenizer's references with the RefMods in place."""
        native = list(native or [])
        n = 0
        while n < len(native) and native[n]["type"] == "image":
            n += 1
        pics, rest = native[:n], native[n:]
        groups, sounds, i = [], [], 0
        while i < len(rest):
            if rest[i]["type"] == "audio" and i + 1 < len(rest) and rest[i + 1]["type"] == "video":
                groups.append(rest[i:i + 2])
                i += 2
            elif rest[i]["type"] == "video":
                groups.append(rest[i:i + 1])
                i += 1
            else:
                sounds.append(rest[i])
                i += 1
        if len(pics) != sum(1 for x in self.images if x is None) or \
                len(groups) != sum(1 for x, _ in self.videos if x is None) or \
                len(sounds) != sum(1 for x in self.audios if x is None) or \
                any(len(g) != (2 if has else 1) for g, (_, has) in zip(groups, [v for v in self.videos if v[0] is None])):
            raise self._out_of_step("references")
        pics, groups, sounds = iter(pics), iter(groups), iter(sounds)
        out = [x[0] if x else next(pics) for x in self.images]
        for x, _ in self.videos:
            out += [x[0]] if x else next(groups)
        out += [x[0] if x else next(sounds) for x in self.audios]
        self.tokenized = True
        return out

    def blocks(self, native):
        """The DiT's references with the RefMods in place."""
        native = list(native or [])
        pics = [b for b in native if b.get("kind") == "image"]
        vids = [b for b in native if b.get("kind") in ("video", "video_audio")]
        sounds = [b for b in native if b.get("kind") == "audio"]
        if len(pics) + len(vids) + len(sounds) != len(native) or \
                len(pics) != sum(1 for x in self.images if x is None) or \
                len(vids) != sum(1 for x, _ in self.videos if x is None) or \
                len(sounds) != sum(1 for x in self.audios if x is None):
            raise self._out_of_step("reference latents")
        pics, vids, sounds = iter(pics), iter(vids), iter(sounds)
        out = [x[1] if x else next(pics) for x in self.images]
        out += [x[1] if x else next(vids) for x, _ in self.videos]
        out += [x[1] if x else next(sounds) for x in self.audios]
        return out

    def attach(self, conditioning):
        """The node's conditioning with the RefMod latents among its references."""
        if not self.tokenized:
            raise self._out_of_step("prompt encoding")
        out = []
        for emb, meta in conditioning:
            meta = dict(meta)
            meta["minimax_refs"] = self.blocks(meta.get("minimax_refs"))
            out.append([emb, meta])
        return out


class _ClipWithMods:
    """The CLIP MiniMaxH3ReferenceToVideo gets: its tokenizer sees the RefMods too; everything else is the CLIP's."""

    def __init__(self, clip, mods):
        self._clip, self._mods = clip, mods

    def tokenize(self, text, *args, minimax_ref_items=None, **kwargs):
        return self._clip.tokenize(text, *args, minimax_ref_items=self._mods.items(minimax_ref_items), **kwargs)

    def __getattr__(self, name):
        return getattr(self._clip, name)
