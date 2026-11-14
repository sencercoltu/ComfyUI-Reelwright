"""Render pending scenes with the native MiniMax H3 nodes. Runs inside ComfyUI.

Per pass: MiniMaxH3ReferenceToVideo builds conditioning and the AV latent,
MiniMaxH3AddGuide anchors continuation clips and keyframes, a Basic guider
samples it (H3 is CFG-distilled), and the video/audio VAEs decode it. Every
scene is written to disk before the next one starts.
"""

import base64
import gc
import io
import json
import logging
import os
import re
import shutil
import time
import uuid

import comfy.model_management as mm
import comfy.nested_tensor
import comfy.sample
import comfy.samplers
import comfy.utils
import folder_paths
import latent_preview
import node_helpers
import nodes
from comfy_extras.nodes_custom_sampler import Guider_Basic, Noise_RandomNoise
from server import PromptServer

try:
    from comfy_extras.nodes_audio import vae_decode_audio
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3AddGuide, MiniMaxH3ReferenceToVideo, MiniMaxH3SigmaShift
    H3_ERROR = None
except ImportError as _e:  # noqa: N816
    vae_decode_audio = MiniMaxH3AddGuide = MiniMaxH3ReferenceToVideo = MiniMaxH3SigmaShift = None
    H3_ERROR = "{}: {}".format(type(_e).__name__, _e)
try:
    from comfy_extras.nodes_hunyuan import LatentUpscaleModelLoader
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3LatentUpscaleWithModel
    UPSCALE_ERROR = None
except ImportError as _e:  # noqa: N816
    LatentUpscaleModelLoader = MiniMaxH3LatentUpscaleWithModel = None
    UPSCALE_ERROR = "{}: {}".format(type(_e).__name__, _e)

from . import assemble, cache, continuity, jobs, media, merge, refmods, spec
from .analysis import _take_meta, analyze, continues, drift_metrics, long_settings, rekey, short_upstream_tail
from .model import normalize_project, previews_whole, project_index, slugify
from .storage import check_slug, write_json

log = logging.getLogger("reelwright")

TAIL_FRAMES = spec.MIN_PASS_FRAMES  # tail.mp4: the last 124 frames of the scene (covers any tail overlap)
SEED_STEP = 1000003                 # seed offset between takes
REF_MAX_FRAMES = int(spec.REF_MEDIA_MAX_SECONDS * spec.FPS)  # at most 15 s of a reference video is decoded


def clip_window(entry):
    """(start, seconds) of a build's video or audio reference: a trimmed one carries in and
    seconds (prompt.collect_refs), others start at 0; never more than 15 s, and at least one frame."""
    start = max(0.0, float(entry.get("in") or 0.0))
    secs = entry.get("seconds")
    secs = spec.REF_MEDIA_MAX_SECONDS if secs is None else min(float(secs), spec.REF_MEDIA_MAX_SECONDS)
    return start, max(1.0 / spec.FPS, secs)
MAX_VARIANTS = 8
# The Global -> Long scenes choices a take records (take["long"])
LONG_TAKE_KEYS = ("guide_vae", "carry_audio", "seam_video_ref", "handoff", "pass_cache")


def h3_available():
    """True when this ComfyUI has the MiniMax H3 nodes."""
    return MiniMaxH3ReferenceToVideo is not None


def h3_error():
    """Why the H3 nodes could not be imported, or None."""
    return H3_ERROR


def is_interrupt(e):
    """ComfyUI's Stop (InterruptProcessingException derives from BaseException)."""
    cls = getattr(mm, "InterruptProcessingException", None)
    return (cls is not None and isinstance(e, cls)) or isinstance(e, KeyboardInterrupt)


def fit_clip(frame_idx, clip_frames, gen_frames, role="keyframe"):
    """Where a video guide goes in a pass, as (frame_idx, first source frame, frame count).
    H3's AddGuide takes 1 frame or 17k+5 frames and the clip has to end inside the pass; it used to stop the run with
    "does not fit" for a video used as last frame, or as a keyframe near the end of a pass. A last-frame video ends on
    the guided frame (its last frames); any other video starts there and is shortened to the room that is left
    (one frame when fewer than 5 are left). Raises ValueError when the frame is outside the pass."""
    gen, clip, idx = int(gen_frames), int(clip_frames), int(frame_idx)
    if idx < 0:
        idx += gen
    if clip < 1:
        raise ValueError("the video has no frames")
    if not 0 <= idx < gen:
        raise ValueError("frame {} is outside the pass's {} frames".format(frame_idx, gen))
    if role == "last_frame":
        n = min(clip, idx + 1)
        n = spec.align_frames_down(n) if n >= 5 else 1
        return idx - n + 1, clip - n, n
    n = min(clip, gen - idx)
    n = spec.align_frames_down(n) if n >= 5 else 1
    return idx, 0, n


# ---- long-scene continuity ------------------------------------------------------------------------------------------
FOOTAGE_SOURCES = ("prev_scene_last", "prev_scene_tail", "prev_pass_tail")  # guides made from footage (drift meter)


def guide_count(n):
    """Frames MiniMaxH3AddGuide anchors of an n-frame image batch: 1 below 5, else the largest 17k+5 <= n."""
    n = int(n)
    return 1 if n < 5 else spec.align_frames_down(n)


def latent_count(frames):
    """Video latents of a 17k+5-frame clip in the H3 VAE: 5k+2 (2 for 5 frames)."""
    return (int(frames) - 5) // 17 * 5 + 2


def latent_frames(t):
    """Frames of a video latent with t latents (FRAME_PER_TOKEN 1, 4, 4, 4, 4 per block of 5)."""
    return sum((1, 4, 4, 4, 4)[k % 5] for k in range(int(t)))


def latent_guide(g, latent, prev_latent):
    """The latent hand-off of an overlap guide g (source prev_pass_tail): (the pass before's last latents, None), or
    (None, why not). Valid only when they are exactly what encoding the overlap frames would give the same latent
    slots:
    - the H3 video VAE encodes every 17-frame chunk on its own (causal inside the chunk: the chunk's first latent holds
      1 frame, the next four hold 4 each; a 5-frame tail chunk keeps 2 latents) and keeps no state between chunks;
    - a pass has 17m+5 frames and the overlap 17j+5, so the overlap starts on a chunk boundary of the pass before
      (frame 17(m-j)) and its 5j+2 latents are exactly the pass before's last 5j+2;
    - an overlap that is not 17j+5 frames would start inside a chunk, where the pass before has no latent that begins
      with a 1-frame "first" latent (the causal first-latent problem), and the canvas sizes must match.
    prev_latent: {"video": [1, 24, T, h, w] the pass before's last T latents, "gen_frames": its frames} or None."""
    if prev_latent is None or prev_latent.get("video") is None:
        return None, "no latents of the pass before (it came from the pass cache without them)"
    k = int(g.get("frames") or 0)
    if k < 5 or k % 17 != 5:
        return None, "the overlap is {} frames, not 17k+5".format(k)
    gen = int(prev_latent.get("gen_frames") or 0)
    if gen < k or gen % 17 != 5:
        return None, "the pass before has {} frames, not 17m+5 of at least the overlap".format(gen)
    if int(g.get("frame_idx") or 0) != 0:
        return None, "the guide is not at frame 0"
    lat = prev_latent["video"]
    need = latent_count(k)
    samples = latent.get("samples") if isinstance(latent, dict) else None
    if samples is None or not getattr(samples, "is_nested", False) or len(samples.tensors) != 2:
        return None, "the pass's latent is not a MiniMax H3 AV latent"
    video = samples.tensors[0]
    if getattr(lat, "ndim", 0) != 5 or video.ndim != 5 or lat.shape[2] < need:
        return None, "fewer latents of the pass before were kept than the overlap needs"
    if lat.shape[1] != video.shape[1] or tuple(lat.shape[3:]) != tuple(video.shape[3:]):
        return None, "the pass before has another canvas size"
    if k > latent_frames(video.shape[2]):
        return None, "the overlap is longer than the pass"
    return lat[:, :, lat.shape[2] - need:].clone(), None


def add_latent_guide(positive, frame_idx, lat):
    """What MiniMaxH3AddGuide adds for a picture guide, with the latent given instead of VAE-encoded: a keyframe
    {resolved_frame_index, latent} appended to the conditioning's minimax_keyframes. A sound guide at the same frame
    is a second keyframe right after it (the packed layout is the same as one keyframe with both)."""
    keyframes = list(positive[0][1].get("minimax_keyframes", []))
    keyframes.append({"resolved_frame_index": int(frame_idx), "latent": lat})
    return node_helpers.conditioning_set_values(positive, {"minimax_keyframes": keyframes})


def save_handoff(path, handoff):
    """The last latents of a pass ({"video": tensor, "gen_frames": n}) next to its pass cache file, written through a
    temporary name (safetensors, no pickle)."""
    from safetensors.torch import save_file
    tmp = "{}.{}.partial".format(path, os.getpid())
    try:
        save_file({"video": handoff["video"].detach().to("cpu").contiguous()}, tmp,
                  metadata={"gen_frames": str(int(handoff["gen_frames"]))})
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def load_handoff(path):
    """save_handoff's latents, or None when the file is missing or unreadable."""
    if not os.path.isfile(path):
        return None
    try:
        from safetensors import safe_open
        with safe_open(path, framework="pt") as f:
            meta = f.metadata() or {}
            return {"video": f.get_tensor("video"), "gen_frames": int(meta.get("gen_frames") or 0)}
    except Exception as e:  # noqa: BLE001 - the hand-off falls back to the decoded frames
        log.warning("Reelwright: latent hand-off file %s is unreadable (%s)", path, e)
        return None


def _names_code(message, code):
    """Does the message name this asset code as a whole word ("A1" is not in "A10")?"""
    return bool(code) and re.search(r"(?<![\w@]){}(?!\w)".format(re.escape(str(code))), message) is not None


def _take_file_exists(store, files, which):
    """A take's file is on disk; a path outside the output folder counts as missing."""
    rel = files.get(which) if isinstance(files, dict) else None
    if not isinstance(rel, str) or not rel:
        return False
    try:
        return os.path.isfile(store.output_path(rel))
    except ValueError:
        return False


def send(event, data):
    PromptServer.instance.send_sync(event, data)


def _err(e):
    """An exception as a short message (as Renderer._fail shows it)."""
    return (str(e) or type(e).__name__).strip()[-600:]


def check_guide_vae(vae, name):
    """A guide VAE must load as the MiniMax H3 video VAE and have an encoder; anything else
    would put its latents in another space. Objects without first_stage_model (test stubs) are not checked."""
    fsm = getattr(vae, "first_stage_model", None)
    if fsm is None:
        return
    if type(fsm).__name__ != "MiniMaxH3VideoVAE":
        raise RuntimeError("The guide VAE {} is not a MiniMax H3 video VAE ({}). Pick a variant of the H3 video VAE in "
                           "Global -> Long scenes, or leave it on the video VAE.".format(name, type(fsm).__name__))
    if getattr(fsm, "encoder", None) is None:
        raise RuntimeError("The guide VAE {} has no encoder (a decoder-only file). Pick an H3 video VAE file that "
                           "has one.".format(name))


class Models:
    """Loads each model once per run and applies LoRA stacks."""

    def __init__(self, wired):
        self.wired = wired
        self.unets, self.clips, self.vaes, self.patched, self.lora_loaders = {}, {}, {}, {}, {}
        self.upscalers = {}

    def clip(self, settings):
        if self.wired.get("clip") is not None:
            return self.wired["clip"]
        key = (settings["text_encoder"], settings["clip_device"])
        if key not in self.clips:
            self.clips[key] = nodes.CLIPLoader().load_clip(settings["text_encoder"], "minimax", settings["clip_device"])[0]
        return self.clips[key]

    def vae(self, name, wired_key):
        if self.wired.get(wired_key) is not None:
            return self.wired[wired_key]
        if name not in self.vaes:
            self.vaes[name] = nodes.VAELoader().load_vae(name)[0]
        return self.vaes[name]

    def encoder_vae(self, settings, guide_vae=""):
        """The VAE that encodes a pass's references, guides and continuation clips: Global ->
        Long scenes -> guide VAE when it is set and is not the scene's video VAE, else the video VAE (wired or file).
        Loaded once per run through the same cache. It must be a MiniMax H3 video VAE with an encoder (the full file,
        the int8 one, a LightVAE/encoder-only variant): the same latent space the video VAE decodes."""
        name = str(guide_vae or "")
        if not name or name == settings["video_vae"]:
            return self.vae(settings["video_vae"], "vae")
        vae = self.vae(name, None)
        check_guide_vae(vae, name)
        return vae


    def model(self, settings):
        loras = tuple(settings["loras"])
        shift = (settings["shift_video"], settings["shift_audio"]) if settings["sigma_shift"] else None
        key = (settings["diffusion"], settings["weight_dtype"], loras, shift)
        if key in self.patched:
            return self.patched[key]
        if self.wired.get("model") is not None:
            m = self.wired["model"]
        else:
            ukey = (settings["diffusion"], settings["weight_dtype"])
            if ukey not in self.unets:
                self.unets[ukey] = nodes.UNETLoader().load_unet(settings["diffusion"], settings["weight_dtype"])[0]
            m = self.unets[ukey]
        for name, strength in loras:
            loader = self.lora_loaders.setdefault(name, nodes.LoraLoaderModelOnly())
            m = loader.load_lora_model_only(m, name, strength)[0]
        if shift:
            m = MiniMaxH3SigmaShift.execute(m, shift[0], shift[1]).result[0]
        self.patched = {key: m}  # keep one patched model; LoRA patches are cheap to rebuild
        return m

    def drop_clips(self):
        self.clips.clear()

    # Global -> Hires: a latent upscale model from models/latent_upscale_models, loaded once
    def upscaler(self, name):
        if name not in self.upscalers:
            self.upscalers[name] = LatentUpscaleModelLoader.execute(name).result[0]
        return self.upscalers[name]


# One sampling step's latent as a small JPEG data URL for the Render tab
PREVIEW_MAX_SIDE = 480
# The shortest gap between two previews. It used to be one second; H3 steps usually take
# longer than this, so in practice every sampler step now shows up in the Render tab.
PREVIEW_MIN_INTERVAL = 0.25


# ComfyUI's own previewer, not an extension's wrapper of it.
# VideoHelperSuite's "Display animated previews when sampling" replaces latent_preview.get_previewer with a wrapper
# whose previewer sends its own animated frames to the frontend (as the executing node, so under Reelwright) and
# returns no image. That put a preview back under the node after v0.3.5, gave the Render tab VHS's frames with a
# 24-byte header in front ("could not be decoded"), and left preview_jpeg with nothing to show.
# Wrappers made with functools (VHS's `hook`) keep the original in __wrapped__.
def stock_previewer(device, latent_format):
    fn = latent_preview.get_previewer
    for _ in range(16):
        inner = getattr(fn, "__wrapped__", None)
        if inner is None:
            break
        fn = inner
    return fn(device, latent_format)


def preview_jpeg(previewer, x0, frame=None):
    """frame: the latent frame of a video latent to show. ComfyUI's previewers show the first one, and in a pass that
    starts from a frame or clip (a continuation, a first-frame guide) the first frame is fixed from the first step, so
    the preview barely changed; the render shows the middle of the part the pass makes new."""
    if getattr(x0, "is_nested", False):  # H3 latents carry video and audio; the first is the video
        x0 = x0.tensors[0]
    if frame is not None and getattr(x0, "ndim", 0) == 5 and x0.shape[2] > 1:
        k = max(0, min(int(frame), int(x0.shape[2]) - 1))
        x0 = x0[:, :, k:k + 1]
    out = previewer.decode_latent_to_preview_image("JPEG", x0)
    if not out:
        raise RuntimeError("the previewer ({}) returned no image".format(type(previewer).__name__))
    _, img, _ = out
    img = img.convert("RGB")
    if max(img.size) > PREVIEW_MAX_SIDE:
        img.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# The latent frame in the middle of the part of pass x that H3 makes new: after an overlap
# with the pass before, or after the cut's start (an H3 latent holds 1 frame, then 4 frames per latent frame)
def preview_frame(x):
    try:
        start = int(x.get("overlap_frames") or 0) if x.get("seam_before") == "overlap" else int(x.get("keep_in_frames") or 0)
        end = int(x.get("keep_out_frames") or x.get("gen_frames") or 0)
    except (TypeError, ValueError, AttributeError):
        return None
    if end <= start:
        return None
    mid = (start + end) // 2
    return 0 if mid <= 0 else 1 + (mid - 1) // 4


def _sample(model, positive, latent, seed, settings, on_step):
    guider = Guider_Basic(model)
    guider.set_conds(positive)
    latent_image = comfy.sample.fix_empty_latent_channels(guider.model_patcher, latent["samples"])
    noise = Noise_RandomNoise(seed).generate_noise({"samples": latent_image})
    sigmas = comfy.samplers.calculate_sigmas(model.get_model_object("model_sampling"),
                                             settings["scheduler"], settings["steps"]).cpu()
    sampler = comfy.samplers.sampler_object(settings["sampler"])
    steps = sigmas.shape[-1] - 1
    # the user's preview method (--preview-method / the frontend setting) still decides how, or whether, to preview
    previewer = stock_previewer(guider.model_patcher.load_device, guider.model_patcher.model.latent_format)
    pbar = comfy.utils.ProgressBar(steps)  # ComfyUI's queue progress, without an image

    frame = settings.get("preview_frame")

    def callback(step, x0, x, total_steps):
        pbar.update_absolute(step + 1, total_steps, None)
        on_step(step + 1, total_steps, (lambda: preview_jpeg(previewer, x0, frame)) if previewer else None)

    samples = guider.sample(noise, latent_image, sampler, sigmas, callback=callback,
                            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED, seed=seed)
    out = latent.copy()
    out["samples"] = samples.to(mm.intermediate_device())
    return out


# Global -> Hires -> refine: the enlarged latent sampled again for `steps` steps, starting from
# `denoise` of the noise (the last steps+1 sigmas of a schedule of steps / denoise steps, as KSampler's denoise does).
# The sound is not refined: the caller keeps the sound of the first sampling.
def refine_sigmas(model, scheduler, steps, denoise):
    total = max(int(steps), int(round(int(steps) / max(0.01, min(1.0, float(denoise))))))
    sigmas = comfy.samplers.calculate_sigmas(model.get_model_object("model_sampling"), scheduler, total).cpu()
    return sigmas[-(int(steps) + 1):]


def _refine(model, positive, latent, seed, settings, steps, denoise, on_step):
    guider = Guider_Basic(model)
    guider.set_conds(positive)
    latent_image = comfy.sample.fix_empty_latent_channels(guider.model_patcher, latent["samples"])
    noise = Noise_RandomNoise(seed).generate_noise({"samples": latent_image})
    sigmas = refine_sigmas(model, settings["scheduler"], steps, denoise)
    sampler = comfy.samplers.sampler_object(settings["sampler"])
    previewer = stock_previewer(guider.model_patcher.load_device, guider.model_patcher.model.latent_format)
    pbar = comfy.utils.ProgressBar(sigmas.shape[-1] - 1)
    frame = settings.get("preview_frame")

    def callback(step, x0, x, total_steps):
        pbar.update_absolute(step + 1, total_steps, None)
        on_step(step + 1, total_steps, (lambda: preview_jpeg(previewer, x0, frame)) if previewer else None)

    samples = guider.sample(noise, latent_image, sampler, sigmas, callback=callback,
                            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED, seed=seed)
    out = latent.copy()
    out["samples"] = samples.to(mm.intermediate_device())
    return out


def _with_audio_of(latent, source):
    """latent with the sound latent of `source` (both MiniMax H3 AV latents)."""
    a, b = latent.get("samples"), source.get("samples")
    if not (getattr(a, "is_nested", False) and getattr(b, "is_nested", False)):
        return latent
    out = latent.copy()
    out["samples"] = comfy.nested_tensor.NestedTensor((a.tensors[0], b.tensors[1]))
    return out


def output_size(st):
    """(width, height) of the frames a scene's passes decode to: the latent upscaler's size
    while it runs (st["hires"]), else the sampling size."""
    hi = st.get("hires")
    return (int(hi["width"]), int(hi["height"])) if hi else (int(st["width"]), int(st["height"]))


def _free(policy):
    gc.collect()
    if policy == "unload_all":
        mm.unload_all_models()
    if policy in ("free_cache", "unload_all"):
        mm.soft_empty_cache()


class PassClock:
    """Wall time of one pass of a take, split by the phases it went through (the progress phases, plus "guides"
    for building the references and hand-off before sampling)."""

    def __init__(self, phase="guides"):
        self.t0 = self.at = time.time()
        self.phase = phase
        self.phases = {}

    def mark(self, phase):
        now = time.time()
        if phase != self.phase:
            if self.phase:
                self.phases[self.phase] = self.phases.get(self.phase, 0.0) + now - self.at
            self.phase, self.at = phase, now

    def stop(self, n, cached=False, encoded=0.0):
        """{pass, seconds, cached, phases}; `encoded` is the time encode-first spent on this pass before the take
        started (counted in the pass and as its "encode" phase)."""
        self.mark(None)
        phases = dict(self.phases)
        if encoded:
            phases["encode"] = phases.get("encode", 0.0) + encoded
        out = {"pass": n + 1, "seconds": round(time.time() - self.t0 + encoded, 1), "cached": bool(cached)}
        if not cached:
            out["phases"] = {k: round(v, 1) for k, v in phases.items() if v >= 0.05}
        return out


PASS_PHASES = ("encode", "sample", "upscale", "refine", "decode", "save", "reuse")


class Renderer:
    def __init__(self, project, store, wired, run_request):
        self.store = store
        self.wired = wired
        self.wired_flags = {"diffusion": wired.get("model") is not None, "text_encoder": wired.get("clip") is not None,
                            "video_vae": wired.get("vae") is not None, "audio_vae": wired.get("audio_vae") is not None}
        # "preview": the first seconds of the chosen scenes (planner.preview_plan: pass 1 at the shortest length H3 is
        # trained on), planned and keyed as such; a scene no longer than a preview renders whole (a normal take)
        self.preview = (run_request or {}).get("action") == "preview"
        self.whole, cut = set(), set()
        self.previews = []  # {scene_id, take_id, video, seconds, of_seconds} of the previews made
        if self.preview:
            project = normalize_project(project)
            chosen = set(run_request.get("scenes") or [])
            self.whole = {s["id"] for s in project["scenes"] if s["id"] in chosen and previews_whole(s)}
            self.full_seconds = {s["id"]: float(s["duration"]) for s in project["scenes"]}
            cut = chosen - self.whole
        self.result = analyze(project, store, self.wired_flags, previews=cut)
        self.p = self.result["project"]
        self.idx = project_index(self.p)
        self.request = run_request
        self.models = Models(wired)
        self.slug = self.p["slug"]
        self.memory = self.p["global"]["memory"]
        self.run_id = None
        self.target_set = set()
        self.long = long_settings(self.p)
        self.footage = []
        self.handoff_notes = []
        self.clock = None  # the PassClock of the pass being rendered
        self.encode_times = {}  # (scene id, pass index) -> seconds encode-first spent on it

    # ---- helpers --------------------------------------------------------------
    def label(self, sid):
        i = self.result["scenes"][sid]["index"]
        return "{:02d} {}".format(i + 1, self.p["scenes"][i]["title"])

    def prev_id(self, sid):
        """The scene this one continues from, or None."""
        i = self.result["scenes"][sid]["index"]
        return self.p["scenes"][i - 1]["id"] if continues(self.p, i) else None

    # ---- selection -------------------------------------------------------
    def targets(self):
        req = self.request
        action = req.get("action", "pending")
        chosen = set(req.get("scenes") or [])
        order = [s["id"] for s in self.p["scenes"]]
        if action == "pass_retake":
            sid = req.get("scene_id")
            if sid not in self.result["scenes"]:
                raise ValueError("Pass retake: this project has no scene {!r}".format(sid))
            count = len(self.result["scenes"][sid]["plan"]["passes"])
            try:
                k = int(req.get("pass"))
            except (TypeError, ValueError):
                k = 0
            if not 1 <= k <= count:
                raise ValueError("Pass retake: {} has {} pass{}, there is no pass {}".format(
                    self.label(sid), count, "" if count == 1 else "es", req.get("pass")))
            return [sid], action
        if action == "variants":
            wanted = req.get("scene_ids") or req.get("scenes") or []
            unknown = [x for x in wanted if x not in self.result["scenes"]]
            if unknown or not wanted:
                raise ValueError("Variants: no such scene {}".format(", ".join(map(repr, unknown))) if unknown
                                 else "Variants: no scene chosen")
            return [x for x in order if x in set(wanted)], action
        out = []
        for i, sid in enumerate(order):
            sr = self.result["scenes"][sid]
            scene = self.p["scenes"][i]
            if action == "pending":
                pick = sr["status"] in ("stale", "missing")
            elif action in ("selected", "take", "preview"):
                pick = sid in chosen
            elif action == "from":
                start = next((k for k, x in enumerate(order) if x in chosen), 0)
                pick = i >= start and (not scene["lock"] or sid in chosen)
            elif action == "all":
                pick = not scene["lock"]
            else:
                raise ValueError("unknown run action {!r}".format(action))
            if pick:
                out.append(sid)
        return out, action

    def order(self, targets):
        """Keep continuation chains in order; optionally group independent chains by LoRA stack."""
        if not self.memory.get("group_by_lora"):
            return targets
        chains, cur = [], []
        for sid in targets:
            if cur and continues(self.p, self.result["scenes"][sid]["index"]) and \
                    self.result["scenes"][cur[-1]]["index"] == self.result["scenes"][sid]["index"] - 1:
                cur.append(sid)
            else:
                if cur:
                    chains.append(cur)
                cur = [sid]
        if cur:
            chains.append(cur)
        chains.sort(key=lambda c: repr(self.result["scenes"][c[0]]["settings"]["loras"]))
        # chains that depend on another target must still run after it
        flat, done = [], set()
        pending = list(chains)
        while pending:
            for c in pending:
                first = self.result["scenes"][c[0]]["index"]
                prev = self.p["scenes"][first - 1]["id"] if first > 0 else None
                needs = continues(self.p, first) and prev in targets and prev not in done
                if not needs:
                    flat += c
                    done.update(c)
                    pending.remove(c)
                    break
            else:
                flat += [x for c in pending for x in c]
                break
        return flat

    # ---- references -------------------------------------------------------
    def _asset_path(self, aid):
        a = self.idx["assets"][aid]
        path = self.store.input_path(a["file"])
        if not os.path.isfile(path):
            raise FileNotFoundError("{} ({}) is missing: {}".format(a["code"], a["name"], a["file"]))
        return path

    def _song_path(self, song):
        """The part of the soundtrack a pass covers, as a WAV made once and kept under
        output/reelwright/<project>/soundtrack/."""
        pieces = []
        for x in song["pieces"]:
            path = self._asset_path(x["asset"])
            pieces.append({"path": path, "src_in": x["src_in"], "src_out": x["src_out"], "at": x["at"]})
        return merge.render_segment(pieces, song["length"], os.path.join(self.store.dir, "soundtrack"),
                                    cache.file_digest)

    def encode(self, scene, sr, n, upstream=None, prev_pass=None):
        """upstream, prev_pass: the take the scene continues from and (frames, audio) of the
        pass before, for the continuation reference (see _continuation_ref); found when not given."""
        b = sr["builds"][n]
        x = sr["plan"]["passes"][n]
        st = sr["settings"]
        images = {}
        for k, img in enumerate(b["images"]):
            if img.get("refmod"):  # refmods.PassMods puts it in its place
                continue
            if img.get("continuation"):
                images["ref_image_{}".format(k)] = self._continuation_ref(sr, n, img, upstream, prev_pass)[0]
                continue
            paths = [self._asset_path(a) for a in img["assets"]]
            images["ref_image_{}".format(k)] = media.make_sheet(paths) if len(paths) > 1 else media.load_image(paths[0])
        videos, video_audios = {}, {}
        for k, v in enumerate(b["videos"]):
            if v.get("refmod"):
                continue
            if v.get("continuation"):
                frames, audio = self._continuation_ref(sr, n, v, upstream, prev_pass)
                videos["ref_video_{}".format(k)] = frames
                if v["soundtrack"] and audio is not None:
                    video_audios["ref_video_audio_{}".format(k)] = audio
                continue
            start, secs = clip_window(v)
            frames, audio = media.load_video(self._asset_path(v["asset"]), max_seconds=secs, max_frames=REF_MAX_FRAMES,
                                             start=start)
            videos["ref_video_{}".format(k)] = frames
            if v["soundtrack"] and audio is not None:
                video_audios["ref_video_audio_{}".format(k)] = audio
        audios = {"ref_audio_{}".format(k): media.load_audio(self._song_path(a["song"]), max_seconds=spec.REF_MEDIA_MAX_SECONDS)
                  if a.get("song") else media.load_audio(self._asset_path(a["asset"]), max_seconds=clip_window(a)[1],
                                                         start=clip_window(a)[0])
                  for k, a in enumerate(b["audios"]) if not a.get("refmod")}
        clip = self.models.clip(st)
        mods = None
        if refmods.sends(b):  # saved H3 references of the cast (look / voice RefMods)
            sounds = {int(name.rsplit("_", 1)[-1]) for name in video_audios}
            mods = refmods.PassMods(b, sounds, self.models.vae(st["video_vae"], "vae"))
            clip = mods.clip(clip)
        out = MiniMaxH3ReferenceToVideo.execute(
            clip=clip, prompt=b["prompt"], width=st["width"], height=st["height"],
            length=x["gen_frames"], ref_image_size=st["ref_image_size"],
            vae=self.models.encoder_vae(st, self.long["guide_vae"]),
            audio_vae=self.models.vae(st["audio_vae"], "audio_vae"),
            ref_images=images or None, ref_videos=videos or None,
            ref_video_audios=video_audios or None, ref_audios=audios or None)
        positive, latent = out.result
        if mods:
            positive = mods.attach(positive)
        return positive, latent

    def _upstream_take(self, scene_index):
        prev = self.p["scenes"][scene_index - 1]
        take = self.store.starred_take(prev["id"])
        if not take:
            raise RuntimeError("{:02d} {} continues from {:02d} {}, which has no take yet".format(
                scene_index + 1, self.p["scenes"][scene_index]["title"], scene_index, prev["title"]))
        return take

    def _planned_upstream(self, sid, prev):
        """The take of `prev` that `sid` will continue from when `prev` is not
        rendered earlier in this run: the take analysis keyed `sid` against (cache.resolve's `provided`; reuse() stars
        it before any render), else the starred take of `prev`. Pre-flight runs before reuse(), so the starred take
        alone could be a take reuse() is about to replace."""
        want = self.result["scenes"][sid].get("upstream_take")
        if want:
            take = next((t for t in self.store.read_index(prev).get("takes") or [] if t.get("id") == want), None)
            if take:
                return take
        return self.store.starred_take(prev)

    def _upstream_tail(self, take, frames):
        """The last `frames` frames (and sound) of the take a scene continues from. tail.mp4
        holds 124 frames since v0.6.0; an older one held 60, so a longer overlap is cut from the take's video."""
        image, audio = None, None
        for which in ("tail", "video"):
            rel = (take.get("files") or {}).get(which)
            if not rel:
                continue
            path = self.store.output_path(rel)
            if not os.path.isfile(path):
                continue
            image, audio = media.load_video(path, last_frames=frames, exact=True)
            if image.shape[0] >= frames:
                break
        if image is None:
            raise RuntimeError("take {} has no tail clip or video to continue from".format(take.get("id")))
        if image.shape[0] < frames:
            raise RuntimeError("take {} has only {} frames, but the scene that continues from it needs a {}-frame tail "
                               "clip. Render that take's scene again, or use a shorter tail overlap or a last-frame "
                               "start.".format(take.get("id"), image.shape[0], frames))
        return image[-frames:], audio

    # ---- the continuation as a named reference -------------------------------------------------------------------
    def _upstream_tail_clip(self, take):
        """The tail clip a tail start sends as <Video 1>, with its sound: the take's tail.mp4 (the last 124 frames of
        the scene, fewer when the scene is shorter). A take from before v0.6.0 kept 60 frames there, so the last 124
        frames of its video are used when they are more."""
        best = None
        for which in ("tail", "video"):
            rel = (take.get("files") or {}).get(which)
            try:
                path = self.store.output_path(rel) if rel else None
            except ValueError:
                path = None
            if not path or not os.path.isfile(path):
                continue
            image, audio = media.load_video(path, last_frames=TAIL_FRAMES, exact=True)
            if best is None or image.shape[0] > best[0].shape[0]:
                best = (image, audio)
            if image.shape[0] >= TAIL_FRAMES:
                break
        if best is None:
            raise RuntimeError("take {} has no tail clip or video to continue from".format(take.get("id")))
        return best

    def _continuation_ref(self, sr, n, ref, upstream=None, prev_pass=None):
        """(image or frames, audio) of the continuation reference `ref` of pass n (an entry of the build's images or
        videos with "continuation"): the last frame of the take the scene continues from (last.png, as its guide),
        that take's tail clip (_upstream_tail_clip), or the last 124 frames of the pass before with their sound."""
        source = ref.get("source")
        if source == "prev_scene_last":
            take = upstream or self._upstream_take(sr["index"])
            return media.load_image(self.store.output_path(take["files"]["last"])), None
        if source == "prev_scene_tail":
            return self._upstream_tail_clip(upstream or self._upstream_take(sr["index"]))
        if source == "prev_pass_tail":
            if not prev_pass:
                raise RuntimeError("pass {} continues from the pass before, which has not been rendered".format(n + 1))
            frames, aud = prev_pass
            count = min(TAIL_FRAMES, int(frames.shape[0]))
            audio = None
            if aud is not None:
                dur = aud["waveform"].shape[-1] / aud["sample_rate"]
                audio = media.slice_audio(aud, max(0.0, dur - count / spec.FPS), dur)
            return frames[-count:], audio
        raise ValueError("unknown continuation source {!r}".format(source))

    def _names_continuation(self, sid, n, sources=("prev_scene_last", "prev_scene_tail", "prev_pass_tail")):
        """Does pass n of scene sid send a continuation reference from one of these sources?"""
        b = self.result["scenes"][sid]["builds"][n]
        return any(x.get("continuation") and x.get("source") in sources for x in b["images"] + b["videos"])

    def _late_encode(self, sid, n):
        """Pass n needs footage made in this run for its references, so encode-first leaves it for render time: the
        end of the pass before, or the last frame / tail clip of a scene rendered earlier in this run."""
        if self._names_continuation(sid, n, ("prev_pass_tail",)):
            return True
        return self._names_continuation(sid, n, ("prev_scene_last", "prev_scene_tail")) and \
            self.prev_id(sid) in self.target_set

    def _guide_role(self, sr, n, g):
        """first_frame | last_frame | keyframe for an asset guide (the prompt module may say
        so in g["role"]; otherwise the planner's lists of the pass tell)."""
        if g.get("role"):
            return g["role"]
        x = sr["plan"]["passes"][n]
        refs = {r["id"]: r for r in self.p["scenes"][sr["index"]]["refs"]}
        for role, key in (("last_frame", "last_frame"), ("first_frame", "first_frame"), ("keyframe", "keyframes")):
            for k in x.get(key) or []:
                r = refs.get(k.get("ref"))
                if r and r.get("asset") == g.get("asset") and k.get("frame_idx") == g.get("frame_idx"):
                    return role
        return "keyframe"

    def _clip_frames(self, path):
        """Frames a video guide can have (24 fps, at most 15 s), from its length on disk."""
        info = merge.probe(path)
        if info.get("has_video") is False:
            return 0
        frames = info.get("video_frames")
        if not frames:
            dur = float(info.get("video_duration") or info.get("duration") or 0)
            frames = max(1, int(round(dur * spec.FPS)))
        return min(REF_MAX_FRAMES, int(frames))

    # Guide VAE, latent hand-off, carry_audio (through the build's guide "audio"), drift record
    def guide(self, scene, sr, n, positive, latent, prev_pass, upstream=None, prev_latent=None):
        """Anchor the pass's guides with MiniMaxH3AddGuide (the guide VAE encodes them, Global -> Long scenes).
        With handoff "latent", the guide a pass after an overlap seam gets from the pass before is prev_latent's last
        latents (_latent_guide; no decode -> encode), its sound (when carried) still goes through AddGuide; when the
        latents can't be used it falls back to the decoded frames. Sets self.footage [(source, frame_idx, frames
        anchored)] for the drift meter and self.handoff_notes [{source, mode, reason?}]."""
        st = sr["settings"]
        vae = self.models.encoder_vae(st, self.long["guide_vae"])
        avae = self.models.vae(st["audio_vae"], "audio_vae")
        x = sr["plan"]["passes"][n]
        self.footage, self.handoff_notes = [], []
        for g in sr["builds"][n]["guides"]:
            image, audio = None, None
            frame_idx = g["frame_idx"]
            if g["source"] == "prev_scene_last":
                take = upstream or self._upstream_take(sr["index"])
                image = media.load_image(self.store.output_path(take["files"]["last"]))
            elif g["source"] == "prev_scene_tail":
                take = upstream or self._upstream_take(sr["index"])
                image, audio = self._upstream_tail(take, int(g["frames"]))
            elif g["source"] == "prev_pass_tail":
                frames, aud = prev_pass
                image = frames[-g["frames"]:]
                if aud is not None:
                    dur = aud["waveform"].shape[-1] / aud["sample_rate"]
                    audio = media.slice_audio(aud, dur - g["frames"] / spec.FPS, dur)
                if self.long["handoff"] == "latent":
                    lat, why = latent_guide(g, latent, prev_latent)
                    if lat is not None:
                        positive = add_latent_guide(positive, frame_idx, lat)
                        if g.get("audio") and audio is not None:  # the sound is not handed off as latents
                            positive = MiniMaxH3AddGuide.execute(
                                positive=positive, latent=latent, frame_idx=frame_idx, vae=None, audio_vae=avae,
                                image=None, audio=audio).result[0]
                        self.footage.append((g["source"], frame_idx, image[:guide_count(image.shape[0])]))
                        self.handoff_notes.append({"source": g["source"], "mode": "latent"})
                        continue
                    log.info("Reelwright: %s pass %d: latent hand-off not possible (%s); using the decoded frames",
                             self.label(self.p["scenes"][sr["index"]]["id"]), n + 1, why)
                    self.handoff_notes.append({"source": g["source"], "mode": "pixels", "reason": why})
            elif g["type"] == "image":
                image = media.load_image(self._asset_path(g["asset"]))
            else:
                clip, _ = media.load_video(self._asset_path(g["asset"]), max_seconds=spec.REF_MEDIA_MAX_SECONDS,
                                           max_frames=REF_MAX_FRAMES)
                frame_idx, first, count = fit_clip(g["frame_idx"], clip.shape[0], x["gen_frames"],
                                                   self._guide_role(sr, n, g))
                image = clip[first:first + count]
            positive = MiniMaxH3AddGuide.execute(
                positive=positive, latent=latent, frame_idx=frame_idx, vae=vae,
                audio_vae=avae if (g.get("audio") and audio is not None) else None,
                image=image, audio=audio if g.get("audio") else None).result[0]
            if g["source"] in FOOTAGE_SOURCES:
                self.footage.append((g["source"], frame_idx, image[:guide_count(image.shape[0])]))
        return positive

    def missing_models(self, targets):
        missing = set()
        checks = (("diffusion_models", "diffusion", "model"), ("text_encoders", "text_encoder", "clip"),
                  ("vae", "video_vae", "vae"), ("vae", "audio_vae", "audio_vae"))
        for sid in targets:
            st = self.result["scenes"][sid]["settings"]
            for folder, key, wired_key in checks:
                if self.wired.get(wired_key) is None and st[key] not in folder_paths.get_filename_list(folder):
                    missing.add("{}/{}".format(folder, st[key] or "(none selected)"))
            for name, _ in st["loras"]:
                if name not in folder_paths.get_filename_list("loras"):
                    missing.add("loras/" + name)
            up = (st.get("hires") or {}).get("model")
            if st.get("hires") and (not up or up not in folder_paths.get_filename_list("latent_upscale_models")):
                missing.add("latent_upscale_models/{} (Global -> Hires; pick it under Global -> Models)".format(
                    up or "(none selected)"))
        gv = str(self.long.get("guide_vae") or "")
        if targets and gv and gv not in folder_paths.get_filename_list("vae"):
            missing.add("vae/{} (the guide VAE)".format(gv))
        return sorted(missing)

    # ---- pre-flight ---------------------------------------------------------
    def _build_assets(self, b):
        """Every asset id a pass build reads from the input folder."""
        out = []
        for img in b.get("images") or []:
            out += list(img.get("assets") or [])
        out += [v["asset"] for v in b.get("videos") or [] if v.get("asset")]
        for a in b.get("audios") or []:
            if a.get("song"):
                out += [x["asset"] for x in a["song"].get("pieces") or [] if x.get("asset")]
            elif a.get("asset"):
                out.append(a["asset"])
        out += [g["asset"] for g in b.get("guides") or [] if g.get("source") == "asset" and g.get("asset")]
        return list(dict.fromkeys(out))

    def preflight(self, targets):
        """Everything that can be checked before any GPU work: H3 nodes, folder name, lint errors, model files,
        reference files, the take each continuing scene starts from (or its upstream renders earlier in this run),
        video guides that fit their pass, ffmpeg. Raises RuntimeError with every problem found."""
        problems = []
        if not h3_available():
            problems.append("This ComfyUI has no MiniMax H3 nodes ({}). Update ComfyUI.".format(H3_ERROR))
        elif UPSCALE_ERROR and any(self.result["scenes"][sid]["settings"].get("hires") for sid in targets):
            problems.append("This ComfyUI has no MiniMax H3 latent upscale node ({}). Update ComfyUI, or turn Global -> "
                            "Hires off.".format(UPSCALE_ERROR))
        try:
            check_slug(self.slug)
            if getattr(self.store, "slug", self.slug) != self.slug:
                problems.append("The project folder {!r} does not match the project ({!r}).".format(self.store.slug, self.slug))
        except ValueError as e:
            problems.append("The project's folder name is not valid: {}".format(e))
        # scenes with errors: "fix these first"
        for sid in targets:
            if self.result["scenes"][sid]["status"] == "error":
                problems += [x["message"] for x in self.result["scenes"][sid]["issues"] if x["level"] == "error"]
        need_ffmpeg, earlier, checked = False, set(), {}
        for sid in targets:
            sr = self.result["scenes"][sid]
            i = sr["index"]
            if len(sr["plan"]["passes"]) > 1:
                need_ffmpeg = True
            for n, b in enumerate(sr["builds"]):
                for aid in self._build_assets(b):
                    if aid in checked:
                        continue
                    a = self.idx["assets"].get(aid)
                    try:
                        checked[aid] = bool(a) and bool(a.get("file")) and os.path.isfile(self.store.input_path(a["file"]))
                    except ValueError:
                        checked[aid] = False
                    if not checked[aid] and not (a and any(_names_code(m, a["code"]) and "missing" in m for m in problems)):
                        problems.append("{}: {} is missing: {}".format(
                            self.label(sid), "{} ({})".format(a["code"], a["name"]) if a else "a deleted asset",
                            (a or {}).get("file") or "no file"))
                if any(a.get("song") for a in b.get("audios") or []):
                    need_ffmpeg = True
                for g in b.get("guides") or []:
                    if g.get("source") != "asset" or g.get("type") != "clip" or not checked.get(g.get("asset")):
                        continue
                    a = self.idx["assets"][g["asset"]]
                    role = self._guide_role(sr, n, g)
                    try:
                        fit_clip(g["frame_idx"], self._clip_frames(self.store.input_path(a["file"])),
                                 sr["plan"]["passes"][n]["gen_frames"], role)
                    except (ValueError, merge.MergeError, OSError) as e:
                        problems.append("{} pass {}: the video {} ({}) cannot be used as {}: {}".format(
                            self.label(sid), n + 1, a["code"], a["name"], role.replace("_", " "), e))
            prev = self.prev_id(sid)
            if prev and prev not in earlier:
                take = self._planned_upstream(sid, prev)
                files = (take or {}).get("files") or {}
                have = lambda k: _take_file_exists(self.store, files, k)  # noqa: E731
                if not take:
                    problems.append("{} continues from {}, which has no take yet. Render {} first, or both together."
                                    .format(self.label(sid), self.label(prev), self.label(prev)))
                elif not have("last") or not (have("tail") or have("video")):
                    problems.append("{} continues from {}, whose starred take {} is missing its files. Render {} again."
                                    .format(self.label(sid), self.label(prev), take.get("id"), self.label(prev)))
                short_tail = short_upstream_tail(self.p, i, sr["builds"], take) if take else None
                if short_tail:
                    problems.append(short_tail)
            earlier.add(sid)
        if need_ffmpeg and not merge.ffmpeg_bin():
            problems.append("ffmpeg was not found. Long scenes and soundtrack parts need it: install ffmpeg and put it "
                            "on PATH.")
        models = self.missing_models(targets)
        parts = []
        if problems:
            parts.append("Reelwright: fix these first:\n" + "\n".join(dict.fromkeys(problems)))
        if models:
            parts.append(("" if parts else "Reelwright: ") + "these model files are missing:\n" + "\n".join(models))
        if parts:
            raise RuntimeError("\n\n".join(parts))

    # ---- stars --------------------------------------------------------------
    def _mark_auto(self, sid, take_id):
        """Remember that the render (not the user) starred this take, so a later run may replace the star."""
        with jobs.lock(self.slug):
            idx = self.store.read_index(sid)
            if idx.get("starred") == take_id and idx.get("auto_star") != take_id:
                idx["auto_star"] = take_id
                self.store.write_index(sid, idx)

    def _star(self, sid, take_id):
        self.store.star(sid, take_id)
        self._mark_auto(sid, take_id)

    def reuse(self):
        """Star the take that matches the current settings where another take is starred (an undone edit), except
        where the user picked the star by hand."""
        reused = []
        for s in self.p["scenes"]:
            sr = self.result["scenes"][s["id"]]
            if sr["status"] == "cached" and sr["match"] and sr["match"] != sr["starred"] and not sr.get("manual_star"):
                self._star(s["id"], sr["match"])
                reused.append(s["id"])
        return reused

    # ---- run ---------------------------------------------------------------
    def progress(self, sid, n, passes, phase, step=0, steps=0, message="", warning=False):
        if phase in PASS_PHASES:
            self.phase(phase)
        data = {"slug": self.slug, "run_id": self.run_id, "scene_id": sid, "pass": n,
                "passes": passes, "step": step, "steps": steps, "phase": phase, "message": message}
        if warning:
            data["warning"] = True
        send("reelwright.progress", data)

    def phase(self, phase):
        """The pass being rendered enters `phase` (its time is counted there until the next phase)."""
        if self.clock is not None:
            self.clock.mark(phase)

    def run(self):
        """Render the requested scenes; returns the ids of the scenes that got a take.

        Events: `rejected` when a check before any GPU work fails (then raises); otherwise `start`, and `end` always
        (also after Stop or an error, sent from a finally). A failing scene does not stop the others: the scenes
        that continue from it are skipped, and the run raises at the end.
        `end` also lists `warnings` [{scene_id, message}]: extra takes (a drift
        retake, variants 2..n) that failed after the scene's first take was made; the scene still counts as rendered."""
        with jobs.running(self.slug, "render"):
            return self._run()

    def _run(self):
        self.run_id = uuid.uuid4().hex[:12]
        try:
            targets, action = self.targets()
            targets = self.order(targets)
            self.preflight(targets)
        except Exception as e:
            send("reelwright.run", {"slug": self.slug, "run_id": self.run_id, "phase": "rejected", "error": str(e)})
            raise
        self.target_set = set(targets)
        if self.p["global"]["continuity"]["face_check"]:
            continuity.retry()  # a model setup that failed last time is tried again
        reused = [] if self.preview else self.reuse()  # a preview run stars nothing
        send("reelwright.run", {"slug": self.slug, "run_id": self.run_id, "phase": "start", "targets": targets,
                                "reused": reused})
        state = {"slug": self.slug, "run_id": self.run_id, "phase": "end", "targets": targets, "reused": reused,
                 "rendered": [], "failed": [], "skipped": [], "warnings": [], "interrupted": False}
        if self.preview:
            state["previews"] = self.previews
            state["whole"] = sorted(self.whole)  # rendered whole: no longer than a preview
        try:
            self._render_all(targets, action, state)
        except BaseException as e:  # Stop is an InterruptProcessingException, which is not an Exception
            state["interrupted"] = is_interrupt(e)
            state["error"] = "Stopped." if state["interrupted"] else (str(e) or type(e).__name__)
            raise
        finally:
            send("reelwright.run", state)
        if state["failed"]:
            lines = ["{}: {}".format(self.label(x["scene_id"]), x["error"]) for x in state["failed"]]
            lines += ["{}: skipped, {}".format(self.label(x["scene_id"]), x["reason"]) for x in state["skipped"]]
            raise RuntimeError("Reelwright: {} scene{} failed:\n{}".format(
                len(state["failed"]), "" if len(state["failed"]) == 1 else "s", "\n".join(lines)))
        return list(state["rendered"])

    def _drop_encoded(self, sid, encoded):
        for k in [k for k in encoded if k[0] == sid]:
            del encoded[k]

    def _fail(self, sid, e, state, encoded):
        msg = (str(e) or type(e).__name__).strip()[-600:]
        state["failed"].append({"scene_id": sid, "error": msg})
        self.progress(sid, 0, len(self.result["scenes"][sid]["plan"]["passes"]), "error", message=msg)
        self._drop_encoded(sid, encoded)

    def _skip(self, sid, reason, state, encoded):
        state["skipped"].append({"scene_id": sid, "reason": reason})
        self.progress(sid, 0, len(self.result["scenes"][sid]["plan"]["passes"]), "skipped", message=reason)
        self._drop_encoded(sid, encoded)

    def _render_all(self, targets, action, state):
        encoded = self.encode_first(targets, action, state) if self.memory.get("encode_first") else {}
        for sid in targets:
            mm.throw_exception_if_processing_interrupted()
            failed = {x["scene_id"] for x in state["failed"]}
            skipped = {x["scene_id"] for x in state["skipped"]}
            if sid in failed:  # its encoding failed
                continue
            prev = self.prev_id(sid)
            if prev in failed or prev in skipped:
                self._skip(sid, "it continues from {}, which {}".format(
                    self.label(prev), "failed" if prev in failed else "was skipped"), state, encoded)
                continue
            try:
                self.render_job(sid, action, encoded, state)
                state["rendered"].append(sid)
            except Exception as e:  # noqa: BLE001 - one scene's failure must not stop the others
                log.exception("Reelwright: %s failed", self.label(sid))
                self._fail(sid, e, state, encoded)
            finally:
                self._drop_encoded(sid, encoded)
                _free(self.memory["policy"])  # memory is freed between scenes, also after a failure

    def encode_first(self, targets, action, state):
        """Encode every pass that will be sampled before sampling starts (one text-encoder load); passes found in the
        pass cache are not encoded."""
        encoded = {}
        for sid in targets:
            sr = self.result["scenes"][sid]
            scene = self.p["scenes"][sr["index"]]
            count = len(sr["plan"]["passes"])
            try:
                try:
                    hits = self._predicted_hits(sid, action)
                except Exception as e:  # noqa: BLE001 - only an optimisation: encode every pass
                    log.warning("Reelwright: could not look up the pass cache of %s: %s", self.label(sid), e)
                    hits = [False] * count
                for n in range(count):
                    if hits[n]:
                        continue
                    if self._late_encode(sid, n):
                        continue
                    mm.throw_exception_if_processing_interrupted()
                    self.progress(sid, n + 1, count, "encode")
                    t0 = time.time()
                    encoded[(sid, n)] = self.encode(scene, sr, n)
                    self.encode_times[(sid, n)] = time.time() - t0
            except Exception as e:  # noqa: BLE001
                log.exception("Reelwright: encoding %s failed", self.label(sid))
                self._fail(sid, e, state, encoded)
        self.models.drop_clips()
        mm.unload_all_models()
        mm.soft_empty_cache()
        return encoded

    def render_job(self, sid, action, encoded, state=None):
        """One scene of the run: a take, a pass retake, or n variants.

        Once the first take is added (and starred), a failing extra take (a drift
        retake, variant 2..n) is a warning (`state["warnings"]`, a progress "done" with warning=True), not a failed
        scene: the scenes that continue from it still render. Stop (a BaseException) still ends the run."""
        if action == "variants":
            try:
                n = int(self.request.get("n") or 2)
            except (TypeError, ValueError):
                n = 2
            n = max(1, min(MAX_VARIANTS, n))
            takes = []
            for k in range(n):
                mm.throw_exception_if_processing_interrupted()
                if k == 0:
                    takes.append(self.render_scene(sid, encoded, bump=True, star=True, keep_encoded=k < n - 1))
                    continue
                try:
                    takes.append(self.render_scene(sid, encoded, bump=True, star=False, keep_encoded=k < n - 1))
                except Exception as e:  # noqa: BLE001 - the first variant is kept and starred
                    self._warn(sid, "variant {} of {} failed: {}".format(k + 1, n, _err(e)), state)
            scored = [(continuity.score(t.get("face")), t) for t in takes]
            scored = [x for x in scored if x[0] is not None]
            if self.p["global"]["continuity"]["face_check"] and scored:
                best = max(scored, key=lambda x: x[0])[1]
                if best["id"] != takes[0]["id"]:
                    self._star(sid, best["id"])
                    count = len(self.result["scenes"][sid]["plan"]["passes"])
                    self.progress(sid, count, count, "done",
                                  message="{} starred (best face match of {})".format(best["id"], n))
            return takes
        if action == "pass_retake":
            return [self.render_scene(sid, encoded, retake_pass=int(self.request.get("pass")))]
        if action == "preview":
            if sid in self.whole:  # no longer than a preview: its normal take
                return [self.render_scene(sid, encoded, bump=True)]
            return [self.render_scene(sid, encoded, bump=True, star=False, preview=True)]
        take = self.render_scene(sid, encoded, bump=action != "pending")
        try:
            return [take] + self._drift_retake(sid, take)
        except Exception as e:  # noqa: BLE001
            self._warn(sid, "{} kept; the drift retake failed: {}".format(take["id"], _err(e)), state)
            return [take]

    def _warn(self, sid, message, state):
        """An extra take of a scene failed after its first take was made. Logged with
        the traceback, listed in the run's end event (`warnings`) and sent as a final "done" progress event."""
        log.warning("Reelwright: %s: %s", self.label(sid), message, exc_info=True)
        if state is not None:
            state.setdefault("warnings", []).append({"scene_id": sid, "message": message})
        _free(self.memory["policy"])  # a failure (often out of memory) can leave memory behind
        count = len(self.result["scenes"][sid]["plan"]["passes"])
        self.progress(sid, count, count, "done", message=message, warning=True)

    def _drift_retake(self, sid, take):
        """Face check with "retake" on drift: one more take, starred only when it matches better."""
        drift = self.p["global"]["continuity"]
        first = continuity.score(take.get("face"))
        if drift.get("on_drift") != "retake" or first is None or first >= float(drift["face_threshold"]):
            return []
        log.info("Reelwright: %s drifted (%s), rendering one more take", sid, take["face"])
        again = self.render_scene(sid, {}, bump=True, star=False)
        second = continuity.score(again.get("face"))
        if second is not None and second > first:
            self._star(sid, again["id"])
            count = len(self.result["scenes"][sid]["plan"]["passes"])
            self.progress(sid, count, count, "done", message="{} starred (better face match)".format(again["id"]))
        return [again]

    # ---- pass cache --------------------------------------------------------
    def pass_dir(self, sid):
        return os.path.join(self.store.scene_dir(sid), "passes")

    def take_plan(self, sid, bump=False, retake_pass=None, upstream=None):
        """Keys, per-pass seed offsets, seeds and pass cache file keys of the take render_scene would make."""
        sr = self.result["scenes"][sid]
        passes = sr["plan"]["passes"]
        n = len(passes)
        pass_keys, key = rekey(self.result, sid, upstream)
        idx = self.store.read_index(sid)
        same = [t for t in idx["takes"] if t.get("key") == key]
        used = set()
        for t in same:
            for v in (t.get("offsets") or [t.get("variant", 0)]):
                try:
                    used.add(int(v))
                except (TypeError, ValueError):
                    pass
        if retake_pass:
            starred = next((t for t in idx["takes"] if t["id"] == idx.get("starred")), None)
            base = starred if starred and starred.get("key") == key else (same[-1] if same else starred)
            offs = [int(v) for v in ((base or {}).get("offsets") or [(base or {}).get("variant", 0)] * n)]
            offs = (offs + [offs[-1] if offs else 0] * n)[:n]
            offs[retake_pass - 1] = max(used | set(offs)) + 1
        else:
            offs = [(max(used) + 1) if (bump and used) else 0] * n
        seeds = [(x["seed"] + o * SEED_STEP) % (2 ** 63) for x, o in zip(passes, offs)]
        return {"pass_keys": pass_keys, "key": key, "offsets": offs, "seeds": seeds,
                "file_keys": cache.pass_file_keys(pass_keys, sr["builds"], seeds)}

    def _cacheable(self, sr):
        return len(sr["plan"]["passes"]) > 1 or sr["plan"]["kind"] == "short"

    def _predicted_hits(self, sid, action):
        sr = self.result["scenes"][sid]
        count = len(sr["plan"]["passes"])
        if not self._cacheable(sr):
            return [False] * count
        prev = self.prev_id(sid)
        upstream = self.store.starred_take(prev) if prev else None
        if prev and not upstream:
            return [False] * count
        retake = int(self.request.get("pass") or 0) if action == "pass_retake" else None
        tp = self.take_plan(sid, bump=action != "pending", retake_pass=retake, upstream=upstream)
        dep = cache.upstream_dependent(sr["builds"], bool(prev))
        later = prev in self.target_set
        pdir = self.pass_dir(sid)
        return [not (later and d) and os.path.isfile(os.path.join(pdir, k + ".mp4")) and
                os.path.isfile(os.path.join(pdir, k + ".json")) for k, d in zip(tp["file_keys"], dep)]

    def _load_pass(self, path, x, st):
        """A finished pass from the pass cache, as (frames, audio), or None."""
        meta_path = path[:-4] + ".json"
        if not (os.path.isfile(path) and os.path.isfile(meta_path)):
            return None
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            if int(meta.get("frames", -1)) != int(x["gen_frames"]):
                return None
        except Exception as e:  # noqa: BLE001 - a damaged cache file is rendered again
            log.warning("Reelwright: pass cache file %s is unreadable (%s); rendering the pass again", meta_path, e)
            return None
        return self._load_pass_file(path, x)

    def _load_pass_file(self, path, x):
        try:
            frames, audio = media.load_video(path, exact=True)
        except Exception as e:  # noqa: BLE001 - a damaged cache file is rendered again
            log.warning("Reelwright: pass cache file %s is unreadable (%s); rendering the pass again", path, e)
            return None
        if frames.shape[0] != int(x["gen_frames"]):
            log.warning("Reelwright: pass cache file %s has %d frames, not %d; rendering the pass again",
                        path, frames.shape[0], x["gen_frames"])
            return None
        return frames, audio

    def _legacy_pass(self, sid, n, tp):
        """A pass file a take from before v0.6.0 kept in its own folder (takes/<id>/passes/pN.mp4) that has the same
        pass key and seeds (back to the last shot cut), or None. Only for passes that do not depend on the take the
        scene continues from (older takes did not record it)."""
        sr = self.result["scenes"][sid]
        builds = sr["builds"]
        if cache.upstream_dependent(builds, bool(self.prev_id(sid)))[n]:
            return None
        first = n
        while first > 0 and any(g.get("source") == "prev_pass_tail" for g in builds[first]["guides"]):
            first -= 1
        for t in reversed(self.store.read_index(sid)["takes"]):
            if "pass_keys" in t:
                continue
            files = (t.get("files") or {}).get("passes") or []
            seeds = [int(x) for x in t.get("seeds") or []]
            if n >= len(files) or seeds[first:n + 1] != [int(x) for x in tp["seeds"][first:n + 1]]:
                continue
            passes = _take_meta(self.store, sid, t["id"]).get("passes") or []
            if n >= len(passes) or passes[n].get("key") != tp["pass_keys"][n]:
                continue
            try:
                path = self.store.output_path(files[n])
            except ValueError:
                continue
            if os.path.isfile(path):
                return path
        return None

    def _save_pass(self, path, frames, audio, meta, handoff=None):
        """Global -> Long scenes -> pass cache "lossless" writes the pass losslessly
        (media.save_video_lossless); `handoff` (the pass's last latents for the next pass's latent hand-off) is kept as
        <file key>.latent.safetensors, so a pass read back from the cache hands off the same latents."""
        lossless = self.long["pass_cache"] == "lossless"
        media.save_video_atomic(frames, audio, path, crf=media.PASS_CRF, lossless=lossless)
        if handoff is not None:
            save_handoff(path[:-4] + ".latent.safetensors", handoff)
        meta = dict(meta, codec="lossless" if lossless else "near_lossless")
        write_json(path[:-4] + ".json", meta)  # written last: a pass counts once both files exist

    def _clean_stale(self, sid):
        """Take folders a stopped or failed render left behind: not in the index and without meta.json (a folder
        with meta.json is a finished take the index lost; Files -> Repair lists it again)."""
        try:
            tdir = os.path.join(self.store.scene_dir(sid), "takes")
            names = os.listdir(tdir)
        except (OSError, ValueError):
            return
        listed = {t.get("id") for t in self.store.read_index(sid)["takes"]}
        for name in names:
            d = os.path.join(tdir, name)
            if name in listed or os.path.islink(d) or not os.path.isdir(d) or os.path.exists(os.path.join(d, "meta.json")):
                continue
            log.info("Reelwright: removing the unfinished take folder %s", d)
            shutil.rmtree(d, ignore_errors=True)

    def _prune_pass_cache(self, sid):
        """Keep the passes some take of the scene uses; drop the rest (left by stopped runs or deleted takes)."""
        pdir = self.pass_dir(sid)
        try:
            names = os.listdir(pdir)
        except OSError:
            return
        keep = set()
        for t in self.store.read_index(sid)["takes"]:
            keep.update(t.get("pass_keys") or [])
            keep.update(os.path.basename(f).split(".")[0] for f in (t.get("files") or {}).get("passes") or [])
        for name in names:
            if name.split(".")[0] in keep:
                continue
            try:
                os.remove(os.path.join(pdir, name))
            except OSError:
                pass

    # ---- long-scene continuity ----------------------------------------------------------------------------------
    def _handoff_need(self, nxt):
        """Latents the latent guide of pass `nxt` takes from the pass before (5j+2 for a 17j+5-frame overlap), 0 when
        the hand-off is off or nxt is not joined by an overlap seam."""
        if self.long["handoff"] != "latent" or not nxt or nxt.get("seam_before") != "overlap":
            return 0
        ov = int(nxt.get("overlap_frames") or 0)
        return latent_count(ov) if ov >= 5 and ov % 17 == 5 else 0

    def _drift(self, n, frames):
        """Drift entries of pass n (0-based) just generated: each footage guide guide() anchored (self.footage)
        against the frames the pass made at the same positions."""
        out = []
        modes = {h["source"]: h for h in self.handoff_notes or []}
        for source, idx, guide in self.footage or []:
            idx, k = int(idx), int(guide.shape[0])
            try:
                if tuple(guide.shape[1:3]) != tuple(frames.shape[1:3]):  # another size (an upstream scene's override):
                    # compared at this pass's size, centre-cropped as MiniMaxH3AddGuide fits it
                    guide = comfy.utils.common_upscale(guide[..., :3].movedim(-1, 1), int(frames.shape[2]),
                                                       int(frames.shape[1]), "bilinear", "center").movedim(1, -1)
                m = drift_metrics(guide, frames[idx:idx + k])
            except Exception as e:  # noqa: BLE001 - a meter must never stop a render
                log.warning("Reelwright: drift of pass %d not measured: %s", n + 1, e)
                continue
            if not m:
                continue
            entry = {"pass": n + 1, "source": source}
            entry.update(m)
            if source == "prev_pass_tail":
                h = modes.get(source) or {"mode": "pixels"}
                entry["handoff"] = h["mode"]
                if h.get("reason"):
                    entry["handoff_reason"] = h["reason"]
            out.append(entry)
        self.footage, self.handoff_notes = [], []
        return out

    def _cached_drift(self, cpath, sr, n, frames, prev_pass):
        """Drift entries of pass n read from the pass cache: the ones stored when it was rendered, else (an older
        cache file) measured now against the end of the pass before when it continues from it."""
        try:
            with open(cpath[:-4] + ".json", encoding="utf-8") as f:
                stored = json.load(f).get("drift")
            if isinstance(stored, list):
                return [dict(e, pass_cache=True) for e in stored if isinstance(e, dict)]
        except (OSError, ValueError, AttributeError):
            pass
        out = []
        for g in sr["builds"][n].get("guides") or []:
            if g.get("source") != "prev_pass_tail" or not prev_pass:
                continue
            k = guide_count(min(int(g.get("frames") or 0), int(prev_pass[0].shape[0])))
            m = drift_metrics(prev_pass[0][-int(g["frames"]):][:k], frames[:k]) if k else None
            if m:
                out.append(dict(m, **{"pass": n + 1, "source": "prev_pass_tail", "pass_cache": True}))
        return out

    def _tail_from_pass(self, x, frames, audio):
        """The last 124 frames (and sound) of the scene from its last pass in memory, when they all lie past the
        part the stitch blends with the pass before (the overlap); else None (the tail is read from the joined
        video)."""
        ko = int(x["keep_out_frames"])
        start = int(x["overlap_frames"]) if x.get("seam_before") == "overlap" else int(x["keep_in_frames"])
        if ko - max(start, int(x["keep_in_frames"])) < TAIL_FRAMES or frames.shape[0] < ko:
            return None
        a = media.slice_audio(audio, (ko - TAIL_FRAMES) / spec.FPS, ko / spec.FPS) if audio is not None else None
        return frames[ko - TAIL_FRAMES:ko].clone(), a

    # ---- one take ----------------------------------------------------------
    def _generate(self, sid, scene, sr, n, encoded, keep_encoded, prev_pass, upstream, seed, prev_latent=None):
        """Encode (unless done already), guide, sample and decode one pass: (frames, audio, video latent).
        prev_latent (the pass before's last latents, for the latent hand-off) and the sampled
        video latent [1, 24, T, h, w] as a third value (None when the latent is not an H3 AV latent)."""
        st = sr["settings"]
        n_pass = len(sr["plan"]["passes"])
        if (sid, n) in encoded:
            positive, latent = encoded[(sid, n)] if keep_encoded else encoded.pop((sid, n))
        else:
            self.progress(sid, n + 1, n_pass, "encode")
            positive, latent = self.encode(scene, sr, n, upstream, prev_pass)
        self.phase("guides")
        hires = st.get("hires")
        unguided = positive if hires and hires.get("refine_steps") else None  # the refine guides again at its size
        positive = self.guide(scene, sr, n, positive, latent, prev_pass, upstream, prev_latent)
        model = self.models.model(st)
        last_sent = [0.0]
        last_preview = [0.0]
        preview_failed = [False]

        def on_step(step, total, preview=None, _n=n, phase="sample"):
            now = time.time()
            if now - last_sent[0] > 0.4 or step == total:
                last_sent[0] = now
                self.progress(sid, _n + 1, n_pass, phase, step, total)
            if preview is not None and (now - last_preview[0] >= PREVIEW_MIN_INTERVAL or step == total):
                last_preview[0] = now
                try:
                    image = preview()
                except Exception as e:  # a preview must never stop a render
                    if not preview_failed[0]:
                        preview_failed[0] = True
                        log.warning("Reelwright: no latent preview for scene %s pass %d: %s", sid, _n + 1, e)
                    else:
                        log.debug("Reelwright preview failed: %s", e)
                    return
                send("reelwright.preview", {"slug": self.slug, "scene_id": sid, "pass": _n + 1, "passes": n_pass,
                                            "step": step, "steps": total, "image": image})

        self.phase("sample")
        samples = _sample(model, positive, latent, seed, dict(st, preview_frame=preview_frame(sr["plan"]["passes"][n])),
                          on_step)
        del positive, latent
        big = samples
        if hires:
            big = self._hires(sid, scene, sr, n, n_pass, samples, unguided, prev_pass, upstream, prev_latent, seed, hires,
                              on_step)
            unguided = None
        self.progress(sid, n + 1, n_pass, "decode")
        frames = nodes.VAEDecode().decode(self.models.vae(st["video_vae"], "vae"), big)[0]
        del big
        audio = vae_decode_audio(self.models.vae(st["audio_vae"], "audio_vae"), samples)
        lat = samples.get("samples") if isinstance(samples, dict) else None
        video_latent = lat.tensors[0] if getattr(lat, "is_nested", False) and len(lat.tensors) == 2 else None
        del samples, lat
        return frames, audio, video_latent

    # Global -> Hires for one pass: the sampled latent enlarged by the latent upscaler, and
    # with refine steps sampled again at the big size (its guides encoded at that size; a latent hand-off can't be used
    # there, so the pass before's frames are). Returns the big latent with the sampled sound.
    def _hires(self, sid, scene, sr, n, n_pass, samples, unguided, prev_pass, upstream, prev_latent, seed, hires, on_step):
        st = sr["settings"]
        self.progress(sid, n + 1, n_pass, "upscale", message="{}×{}".format(hires["width"], hires["height"]))
        big = MiniMaxH3LatentUpscaleWithModel.execute(model=self.models.upscaler(hires["model"]), samples=samples,
                                                      width=int(hires["width"]), height=int(hires["height"])).result[0]
        steps = int(hires.get("refine_steps") or 0)
        if steps <= 0 or unguided is None:
            return big
        footage, notes = self.footage, self.handoff_notes  # the drift meter measures the first sampling's guides
        self.phase("guides")
        positive = self.guide(scene, sr, n, unguided, big, prev_pass, upstream, prev_latent)
        self.footage, self.handoff_notes = footage, notes
        model = self.models.model(st)

        def refine_step(step, total, preview=None):
            on_step(step, total, preview, phase="refine")

        self.progress(sid, n + 1, n_pass, "refine", 0, steps)
        refined = _refine(model, positive, big, seed, dict(st, preview_frame=preview_frame(sr["plan"]["passes"][n])),
                          steps, float(hires.get("refine_denoise") or 0.35), refine_step)
        del positive, big
        return _with_audio_of(refined, samples)

    def render_scene(self, sid, encoded, bump=False, star=True, retake_pass=None, keep_encoded=False, preview=False):
        """Render one take of a scene and add it to the scene's takes; returns the take. preview: the scene is planned
        as its preview (planner.preview_plan) and the take is marked so (never starred).

        Passes of long and short scenes go through the pass cache: a pass with the same key and seed is read back
        instead of sampled (after Stop or a failure, after moving a short scene's keep window, for the passes a pass
        retake keeps). tail.mp4 is the last 124 frames of the scene, across passes."""
        sr = self.result["scenes"][sid]
        scene = self.p["scenes"][sr["index"]]
        plan = sr["plan"]
        st = sr["settings"]
        n_pass = len(plan["passes"])
        prev = self.prev_id(sid)
        upstream = self._upstream_take(sr["index"]) if prev else None
        tp = self.take_plan(sid, bump=bump, retake_pass=retake_pass, upstream=upstream)
        cacheable = self._cacheable(sr)
        pdir = self.pass_dir(sid)
        self._clean_stale(sid)
        take_id = self.store.new_take_id(sid)
        tdir = self.store.take_dir(sid, take_id)
        os.makedirs(tdir, exist_ok=True)
        if cacheable:
            os.makedirs(pdir, exist_ok=True)
        video_name = "{}_{:02d}_{}_{}.mp4".format(self.slug, sr["index"] + 1, slugify(scene["title"])[:40], take_id)
        video_path = os.path.join(tdir, video_name)
        t0 = time.time()
        prev_pass, first, tail = None, None, None
        pass_files, sampled, from_cache = [], 0, 0
        lossless = self.long["pass_cache"] == "lossless"
        prev_latent, drift, tail_mem = None, [], None
        pass_times, encode_seconds = [], 0.0
        self.clock = None
        for n, x in enumerate(plan["passes"]):
            mm.throw_exception_if_processing_interrupted()
            self.clock = PassClock()
            pre = self.encode_times.pop((sid, n), 0.0)
            cpath = os.path.join(pdir, tp["file_keys"][n] + ".mp4")
            nxt = plan["passes"][n + 1] if n + 1 < n_pass else None
            need = self._handoff_need(nxt)
            keep_lat = None
            hit = self._load_pass(cpath, x, st) if cacheable else None
            if hit is None and cacheable:  # a pass an older take kept in its own folder
                legacy = self._legacy_pass(sid, n, tp)
                hit = self._load_pass_file(legacy, x) if legacy else None
                if hit is not None:
                    self._save_pass(cpath, hit[0], hit[1], {
                        "key": tp["file_keys"][n], "pass_key": tp["pass_keys"][n], "scene_id": sid, "pass": n + 1,
                        "seed": tp["seeds"][n], "frames": int(x["gen_frames"]), "width": st["width"],
                        "height": st["height"], "created": int(time.time()), "from": self.store.rel_output(legacy)})
            if hit is not None:
                frames, audio = hit
                if not keep_encoded:
                    encoded.pop((sid, n), None)
                from_cache += 1
                self.progress(sid, n + 1, n_pass, "reuse", message="pass {} from the pass cache".format(n + 1))
                drift += self._cached_drift(cpath, sr, n, frames, prev_pass)
                keep_lat = load_handoff(cpath[:-4] + ".latent.safetensors") if need else None
            else:
                if (sid, n) not in encoded:
                    pre = 0.0  # encoded again inside the take (its own "encode" phase)
                frames, audio, lat_full = self._generate(sid, scene, sr, n, encoded, keep_encoded, prev_pass, upstream,
                                                         tp["seeds"][n], prev_latent)
                sampled += int(x["gen_frames"])
                pass_drift = self._drift(n, frames)
                drift += pass_drift
                if need and lat_full is not None and lat_full.ndim == 5 and lat_full.shape[2] >= need:
                    keep_lat = {"video": lat_full[:, :, lat_full.shape[2] - need:].clone(),
                                "gen_frames": int(x["gen_frames"])}
                del lat_full
                if cacheable:
                    self.progress(sid, n + 1, n_pass, "save")
                    self._save_pass(cpath, frames, audio, {
                        "key": tp["file_keys"][n], "pass_key": tp["pass_keys"][n], "scene_id": sid, "pass": n + 1,
                        "seed": tp["seeds"][n], "frames": int(x["gen_frames"]), "width": st["width"],
                        "height": st["height"], "created": int(time.time()),
                        "drift": pass_drift}, handoff=keep_lat)
            if cacheable:
                pass_files.append(cpath)
            kept, kept_audio = media.trim(frames, audio, x["keep_in_frames"], x["keep_out_frames"])
            if n == 0:
                first = kept[:1].clone()
            if n_pass == 1:
                self.progress(sid, 1, 1, "save")
                media.save_video(kept, kept_audio, video_path)
                k = kept.shape[0]
                tail = (kept[-TAIL_FRAMES:].clone(),
                        media.slice_audio(kept_audio, max(0, k - TAIL_FRAMES) / spec.FPS, k / spec.FPS)
                        if kept_audio is not None else None)
            if lossless and n_pass > 1 and nxt is None:
                tail_mem = self._tail_from_pass(x, frames, audio)
            prev_latent = keep_lat
            keep = 0 if not nxt else max(nxt["overlap_frames"], TAIL_FRAMES) \
                if self._names_continuation(sid, n + 1, ("prev_pass_tail",)) else nxt["overlap_frames"]
            prev_pass = (frames[-keep:].clone(), audio) if nxt and nxt["seam_before"] == "overlap" else None
            del frames, audio, kept, kept_audio
            _free(self.memory["policy"])
            cached = hit is not None
            pass_times.append(self.clock.stop(n, cached=cached, encoded=0.0 if cached else pre))
            encode_seconds += 0.0 if cached else pre
            self.clock = None
        t_passes = time.time()

        if n_pass > 1:
            self.progress(sid, n_pass, n_pass, "save", message="joining {} passes".format(n_pass))
            segs = assemble.pass_segments(plan, pass_files, self.p["global"]["long"]["crossfade_frames"],
                                          carry_audio=bool(self.long["carry_audio"]))
            # Stop kills ffmpeg (merge.run_ffmpeg polls cancel, which raises ComfyUI's interrupt)
            ow, oh = output_size(st)
            merge.join(segs, video_path, ow, oh, audio_fade_frames=0,
                       cancel=lambda: mm.throw_exception_if_processing_interrupted() or False)
            tail = tail_mem or media.load_video(video_path, last_frames=TAIL_FRAMES)
        media.frame_to_png(first[0], os.path.join(tdir, "first.png"))
        tail_frames, tail_audio = tail
        media.frame_to_png(tail_frames[-1], os.path.join(tdir, "last.png"))
        media.save_video(tail_frames, tail_audio, os.path.join(tdir, "tail.mp4"), crf=media.PASS_CRF,
                         lossless=lossless)
        del tail, tail_frames, tail_audio, tail_mem

        rel = lambda name: self.store.rel_output(os.path.join(tdir, name))  # noqa: E731
        take = {
            "id": take_id, "key": tp["key"], "variant": max(tp["offsets"]), "created": int(time.time()),
            "quality": st["quality"], "seconds": plan["frames"] / spec.FPS, "frames": plan["frames"],
            "overlap_frames": plan["passes"][0]["overlap_frames"], "seeds": tp["seeds"],
            "pass_times": pass_times,
            "files": {"video": rel(video_name), "first": rel("first.png"), "last": rel("last.png"),
                      "tail": rel("tail.mp4"), "passes": [self.store.rel_output(f) for f in pass_files]},
            "face": {},
            "offsets": tp["offsets"], "pass_keys": tp["file_keys"], "start_mode": plan.get("start_mode"),
            "upstream": {"scene_id": prev, "take_id": upstream["id"]} if upstream else None,
            "prompts": sr["prompts"], "generated_frames": sum(int(x["gen_frames"]) for x in plan["passes"]),
            "sampled_frames": sampled, "cached_passes": from_cache,
            "width": st["width"], "height": st["height"], "steps": st["steps"], "face_score": None,
            "drift": drift, "long": {k: self.long.get(k) for k in LONG_TAKE_KEYS},
        }
        if st.get("hires"):
            take["out_width"], take["out_height"] = output_size(st)
            take["hires"] = dict(st["hires"])
        if encode_seconds >= 0.05:
            take["encode_seconds"] = round(encode_seconds, 1)
        if preview:
            take["preview"] = True
            take["preview_of"] = round(self.full_seconds.get(sid, take["seconds"]), 4)  # the scene's whole length
        if self.p["global"]["continuity"]["face_check"] and continuity.available():
            # an optional check must not throw away a finished take
            try:
                take["face"] = continuity.check_scene(self.p, scene, self.store, video_path)
                take["face_score"] = continuity.score(take["face"])
            except Exception as e:
                log.warning("Reelwright: face check skipped for %s: %s", sid, e)
                self.progress(sid, n_pass, n_pass, "save", message="face check skipped: {}".format(str(e)[:160]))
        # the whole take: its passes, then joining them, the first/last frames, the tail clip and the face check
        take["render_seconds"] = round(time.time() - t0, 1)
        take["finish_seconds"] = round(time.time() - t_passes, 1)
        meta = dict(take, passes=[dict(x, key=k) for x, k in zip(sr["passes"], tp["pass_keys"])],
                    settings={k: v for k, v in st.items() if k != "loras"}, loras=st["loras"])
        write_json(os.path.join(tdir, "meta.json"), meta)  # through a temp file: Files -> Repair trusts meta.json
        self.store.add_take(sid, take, star=star and not preview)
        if star and not preview:
            self._mark_auto(sid, take_id)
        if cacheable:
            self._prune_pass_cache(sid)
        if preview:
            self.previews.append({"scene_id": sid, "take_id": take_id, "video": take["files"]["video"],
                                  "seconds": take["seconds"], "of_seconds": take["preview_of"]})
        self.progress(sid, n_pass, n_pass, "done", message="preview " + take_id if preview else take_id)
        return take
