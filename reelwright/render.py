"""Render pending scenes with the native MiniMax H3 nodes. Runs inside ComfyUI.

Per pass: MiniMaxH3ReferenceToVideo builds conditioning and the AV latent,
MiniMaxH3AddGuide anchors continuation clips and keyframes, a Basic guider
samples it (H3 is CFG-distilled), and the video/audio VAEs decode it. Every
scene is written to disk before the next one starts.
"""

import base64  # added 2026-11-02 v0.3.5: latent previews go to the Render tab
import gc
import io  # added 2026-11-02 v0.3.5
import json
import logging
import os
import shutil  # added 2026-11-03 v0.6.0: stale take folders
import time
import uuid  # added 2026-11-03 v0.6.0: run ids

import comfy.model_management as mm
import comfy.sample
import comfy.samplers
import comfy.utils
import folder_paths
import latent_preview
import nodes
# [OLD 2026-11-03 v0.5.1->v0.6.0] imported at load time: without the H3 nodes the whole extension failed to load
# from comfy_extras.nodes_audio import vae_decode_audio
from comfy_extras.nodes_custom_sampler import Guider_Basic, Noise_RandomNoise
# from comfy_extras.nodes_minimax_h3 import MiniMaxH3AddGuide, MiniMaxH3ReferenceToVideo, MiniMaxH3SigmaShift
# [/OLD]
from server import PromptServer

# added 2026-11-03 v0.6.0: an older ComfyUI without the MiniMax H3 nodes still loads the extension (the editor, Files,
# merges work, Global -> About says what is missing); a render is refused before it starts
try:
    from comfy_extras.nodes_audio import vae_decode_audio
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3AddGuide, MiniMaxH3ReferenceToVideo, MiniMaxH3SigmaShift
    H3_ERROR = None
except ImportError as _e:  # noqa: N816
    vae_decode_audio = MiniMaxH3AddGuide = MiniMaxH3ReferenceToVideo = MiniMaxH3SigmaShift = None
    H3_ERROR = "{}: {}".format(type(_e).__name__, _e)

# [OLD 2026-11-03 v0.4.3->v0.5.0] from . import assemble, continuity, media, merge, spec
# [OLD 2026-11-03 v0.5.1->v0.6.0] from . import assemble, cache, continuity, media, merge, spec  # cache: added 2026-11-03 v0.5.0 for the soundtrack WAVs
from . import assemble, cache, continuity, jobs, media, merge, spec  # jobs: added 2026-11-03 v0.6.0
# [OLD 2026-11-03 v0.5.1->v0.6.0] from .analysis import analyze
# [OLD 2026-11-03 v0.6.0 review] from .analysis import _take_meta, analyze, continues, rekey
from .analysis import _take_meta, analyze, continues, rekey, short_upstream_tail  # added 2026-11-03 v0.6.0 review
from .model import project_index, slugify  # slugify: added 2026-11-02 v0.2.0 for take file names
from .storage import check_slug, write_json  # added 2026-11-03 v0.6.0

log = logging.getLogger("reelwright")

# added 2026-11-03 v0.6.0
TAIL_FRAMES = spec.MIN_PASS_FRAMES  # tail.mp4: the last 124 frames of the scene (covers any tail overlap)
SEED_STEP = 1000003                 # seed offset between takes (unchanged from v0.5.1)
REF_MAX_FRAMES = int(spec.REF_MEDIA_MAX_SECONDS * spec.FPS)  # at most 15 s of a reference video is decoded
MAX_VARIANTS = 8


def h3_available():
    """added 2026-11-03 v0.6.0: True when this ComfyUI has the MiniMax H3 nodes."""
    return MiniMaxH3ReferenceToVideo is not None


def h3_error():
    """added 2026-11-03 v0.6.0: why the H3 nodes could not be imported, or None."""
    return H3_ERROR


def is_interrupt(e):
    """added 2026-11-03 v0.6.0: ComfyUI's Stop (InterruptProcessingException derives from BaseException)."""
    cls = getattr(mm, "InterruptProcessingException", None)
    return (cls is not None and isinstance(e, cls)) or isinstance(e, KeyboardInterrupt)


def fit_clip(frame_idx, clip_frames, gen_frames, role="keyframe"):
    """added 2026-11-03 v0.6.0: where a video guide goes in a pass, as (frame_idx, first source frame, frame count).
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


def send(event, data):
    PromptServer.instance.send_sync(event, data)


def _err(e):
    """added 2026-11-03 v0.6.0 review: an exception as a short message (as Renderer._fail shows it)."""
    return (str(e) or type(e).__name__).strip()[-600:]


class Models:
    """Loads each model once per run and applies LoRA stacks."""

    def __init__(self, wired):
        self.wired = wired
        self.unets, self.clips, self.vaes, self.patched, self.lora_loaders = {}, {}, {}, {}, {}

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


# added 2026-11-02 v0.3.5: one sampling step's latent as a small JPEG data URL for the Render tab
PREVIEW_MAX_SIDE = 480
# added 2026-11-02 v0.3.8: the shortest gap between two previews. It used to be one second; H3 steps usually take
# longer than this, so in practice every sampler step now shows up in the Render tab.
PREVIEW_MIN_INTERVAL = 0.25


# added 2026-11-02 v0.3.9: ComfyUI's own previewer, not an extension's wrapper of it.
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


def preview_jpeg(previewer, x0):
    if getattr(x0, "is_nested", False):  # H3 latents carry video and audio; the first is the video
        x0 = x0.tensors[0]
    # [OLD 2026-11-02 v0.3.8->v0.3.9] a previewer that returned None failed here with "cannot unpack non-iterable NoneType"
    # _, img, _ = previewer.decode_latent_to_preview_image("JPEG", x0)
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


def _sample(model, positive, latent, seed, settings, on_step):
    guider = Guider_Basic(model)
    guider.set_conds(positive)
    latent_image = comfy.sample.fix_empty_latent_channels(guider.model_patcher, latent["samples"])
    noise = Noise_RandomNoise(seed).generate_noise({"samples": latent_image})
    sigmas = comfy.samplers.calculate_sigmas(model.get_model_object("model_sampling"),
                                             settings["scheduler"], settings["steps"]).cpu()
    sampler = comfy.samplers.sampler_object(settings["sampler"])
    # [OLD 2026-11-02 v0.3.4->v0.3.5] ComfyUI's preview callback sent each step's image with the progress bar, and the
    # frontend painted it over the whole node; the preview now goes to the editor's Render tab instead
    # preview = latent_preview.prepare_callback(guider.model_patcher, sigmas.shape[-1] - 1)
    #
    # def callback(step, x0, x, total_steps):
    #     preview(step, x0, x, total_steps)
    #     on_step(step + 1, total_steps)
    # [/OLD]
    steps = sigmas.shape[-1] - 1
    # the user's preview method (--preview-method / the frontend setting) still decides how, or whether, to preview
    # [OLD 2026-11-02 v0.3.8->v0.3.9] an extension's wrapper (VideoHelperSuite) could take over the preview
    # previewer = latent_preview.get_previewer(guider.model_patcher.load_device, guider.model_patcher.model.latent_format)
    previewer = stock_previewer(guider.model_patcher.load_device, guider.model_patcher.model.latent_format)
    pbar = comfy.utils.ProgressBar(steps)  # ComfyUI's queue progress, without an image

    def callback(step, x0, x, total_steps):
        pbar.update_absolute(step + 1, total_steps, None)
        # [OLD 2026-11-02 v0.3.7->v0.3.8] # the image is only decoded when on_step asks for it (it throttles to about one per second)
        # the image is only decoded when on_step asks for it (at most one per PREVIEW_MIN_INTERVAL)
        on_step(step + 1, total_steps, (lambda: preview_jpeg(previewer, x0)) if previewer else None)

    samples = guider.sample(noise, latent_image, sampler, sigmas, callback=callback,
                            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED, seed=seed)
    out = latent.copy()
    out["samples"] = samples.to(mm.intermediate_device())
    return out


def _free(policy):
    gc.collect()
    if policy == "unload_all":
        mm.unload_all_models()
    if policy in ("free_cache", "unload_all"):
        mm.soft_empty_cache()


class Renderer:
    def __init__(self, project, store, wired, run_request):
        self.store = store
        self.wired = wired
        self.wired_flags = {"diffusion": wired.get("model") is not None, "text_encoder": wired.get("clip") is not None,
                            "video_vae": wired.get("vae") is not None, "audio_vae": wired.get("audio_vae") is not None}
        self.result = analyze(project, store, self.wired_flags)
        self.p = self.result["project"]
        self.idx = project_index(self.p)
        self.request = run_request
        self.models = Models(wired)
        self.slug = self.p["slug"]
        self.memory = self.p["global"]["memory"]
        self.run_id = None  # added 2026-11-03 v0.6.0
        self.target_set = set()  # added 2026-11-03 v0.6.0: scenes this run renders

    # ---- helpers (added 2026-11-03 v0.6.0) ------------------------------------
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
        # added 2026-11-03 v0.6.0: a new seed for one pass of a scene; n takes of some scenes
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
            elif action in ("selected", "take"):
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
            scene = self.p["scenes"][self.result["scenes"][sid]["index"]]
            # [OLD 2026-11-03 v0.5.1->v0.6.0] if cur and scene["start"]["mode"] in ("last_frame", "tail") and \
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
                scene = self.p["scenes"][first]
                prev = self.p["scenes"][first - 1]["id"] if first > 0 else None
                # [OLD 2026-11-03 v0.5.1->v0.6.0] needs = scene["start"]["mode"] in ("last_frame", "tail") and prev in targets and prev not in done
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
        """added 2026-11-03 v0.5.0: the part of the soundtrack a pass covers, as a WAV made once and kept under
        output/reelwright/<project>/soundtrack/."""
        pieces = []
        for x in song["pieces"]:
            path = self._asset_path(x["asset"])
            pieces.append({"path": path, "src_in": x["src_in"], "src_out": x["src_out"], "at": x["at"]})
        return merge.render_segment(pieces, song["length"], os.path.join(self.store.dir, "soundtrack"),
                                    cache.file_digest)

    def encode(self, scene, sr, n):
        b = sr["builds"][n]
        x = sr["plan"]["passes"][n]
        st = sr["settings"]
        images = {}
        for k, img in enumerate(b["images"]):
            paths = [self._asset_path(a) for a in img["assets"]]
            images["ref_image_{}".format(k)] = media.make_sheet(paths) if len(paths) > 1 else media.load_image(paths[0])
        videos, video_audios = {}, {}
        for k, v in enumerate(b["videos"]):
            # [OLD 2026-11-03 v0.5.1->v0.6.0] frames, audio = media.load_video(self._asset_path(v["asset"]), max_seconds=spec.REF_MEDIA_MAX_SECONDS)
            frames, audio = media.load_video(self._asset_path(v["asset"]), max_seconds=spec.REF_MEDIA_MAX_SECONDS,
                                             max_frames=REF_MAX_FRAMES)  # only the first 15 s is decoded
            videos["ref_video_{}".format(k)] = frames
            if v["soundtrack"] and audio is not None:
                video_audios["ref_video_audio_{}".format(k)] = audio
        # [OLD 2026-11-03 v0.4.3->v0.5.0] audios = {"ref_audio_{}".format(k): media.load_audio(self._asset_path(a["asset"])) for k, a in enumerate(b["audios"])}
        # added 2026-11-03 v0.5.0: the soundtrack segment is cut to a WAV of its own first
        # [OLD 2026-11-03 v0.5.1->v0.6.0] audio references were sent whole
        # audios = {"ref_audio_{}".format(k): media.load_audio(self._song_path(a["song"]) if a.get("song")
        #                                                      else self._asset_path(a["asset"]))
        #           for k, a in enumerate(b["audios"])}
        # [/OLD]
        audios = {"ref_audio_{}".format(k): media.load_audio(self._song_path(a["song"]) if a.get("song")
                                                             else self._asset_path(a["asset"]),
                                                             max_seconds=spec.REF_MEDIA_MAX_SECONDS)
                  for k, a in enumerate(b["audios"])}
        out = MiniMaxH3ReferenceToVideo.execute(
            clip=self.models.clip(st), prompt=b["prompt"], width=st["width"], height=st["height"],
            length=x["gen_frames"], ref_image_size=st["ref_image_size"],
            vae=self.models.vae(st["video_vae"], "vae"), audio_vae=self.models.vae(st["audio_vae"], "audio_vae"),
            ref_images=images or None, ref_videos=videos or None,
            ref_video_audios=video_audios or None, ref_audios=audios or None)
        positive, latent = out.result
        return positive, latent

    def _upstream_take(self, scene_index):
        prev = self.p["scenes"][scene_index - 1]
        take = self.store.starred_take(prev["id"])
        if not take:
            raise RuntimeError("{:02d} {} continues from {:02d} {}, which has no take yet".format(
                scene_index + 1, self.p["scenes"][scene_index]["title"], scene_index, prev["title"]))
        return take

    def _planned_upstream(self, sid, prev):
        """added 2026-11-03 v0.6.0 review: the take of `prev` that `sid` will continue from when `prev` is not
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
        """added 2026-11-03 v0.6.0: the last `frames` frames (and sound) of the take a scene continues from. tail.mp4
        holds 124 frames since v0.6.0; an older one held 60, so a longer overlap is cut from the take's video."""
        image, audio = None, None
        for which in ("tail", "video"):
            rel = (take.get("files") or {}).get(which)
            if not rel:
                continue
            path = self.store.output_path(rel)
            if not os.path.isfile(path):
                continue
            image, audio = media.load_video(path, last_frames=frames)
            if image.shape[0] >= frames:
                break
        if image is None:
            raise RuntimeError("take {} has no tail clip or video to continue from".format(take.get("id")))
        # added 2026-11-03 v0.6.0 review: a take shorter than the planned overlap used to give the guide fewer frames
        # (AddGuide keeps the first 17k+5 of them) while the cut still trims the planned overlap: the seam was off
        if image.shape[0] < frames:
            raise RuntimeError("take {} has only {} frames, but the scene that continues from it needs a {}-frame tail "
                               "clip. Render that take's scene again, or use a shorter tail overlap or a last-frame "
                               "start.".format(take.get("id"), image.shape[0], frames))
        return image[-frames:], audio

    def _guide_role(self, sr, n, g):
        """added 2026-11-03 v0.6.0: first_frame | last_frame | keyframe for an asset guide (the prompt module may say
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
        """added 2026-11-03 v0.6.0: frames a video guide can have (24 fps, at most 15 s), from its length on disk."""
        dur = float(merge.probe(path)["duration"] or 0)
        return min(REF_MAX_FRAMES, max(1, int(round(dur * spec.FPS))))

    # [OLD 2026-11-03 v0.5.1->v0.6.0] a video guide could fall off the end of the pass (AddGuide raised mid-run), and
    # a 73/90-frame tail overlap got only the 60 frames an older tail.mp4 held
    # def guide(self, scene, sr, n, positive, latent, prev_pass):
    #     st = sr["settings"]
    #     vae = self.models.vae(st["video_vae"], "vae")
    #     avae = self.models.vae(st["audio_vae"], "audio_vae")
    #     for g in sr["builds"][n]["guides"]:
    #         image, audio = None, None
    #         if g["source"] == "prev_scene_last":
    #             take = self._upstream_take(sr["index"])
    #             image = media.load_image(self.store.output_path(take["files"]["last"]))
    #         elif g["source"] == "prev_scene_tail":
    #             take = self._upstream_take(sr["index"])
    #             image, audio = media.load_video(self.store.output_path(take["files"]["tail"]),
    #                                             last_seconds=g["frames"] / spec.FPS)
    #             image = image[-g["frames"]:]
    #         elif g["source"] == "prev_pass_tail":
    #             frames, aud = prev_pass
    #             image = frames[-g["frames"]:]
    #             if aud is not None:
    #                 dur = aud["waveform"].shape[-1] / aud["sample_rate"]
    #                 audio = media.slice_audio(aud, dur - g["frames"] / spec.FPS, dur)
    #         elif g["type"] == "image":
    #             image = media.load_image(self._asset_path(g["asset"]))
    #         else:
    #             image, _ = media.load_video(self._asset_path(g["asset"]), max_seconds=spec.REF_MEDIA_MAX_SECONDS)
    #         positive = MiniMaxH3AddGuide.execute(
    #             positive=positive, latent=latent, frame_idx=g["frame_idx"], vae=vae,
    #             audio_vae=avae if (g.get("audio") and audio is not None) else None,
    #             image=image, audio=audio if g.get("audio") else None).result[0]
    #     return positive
    # [/OLD]
    def guide(self, scene, sr, n, positive, latent, prev_pass, upstream=None):
        st = sr["settings"]
        vae = self.models.vae(st["video_vae"], "vae")
        avae = self.models.vae(st["audio_vae"], "audio_vae")
        x = sr["plan"]["passes"][n]
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
        return sorted(missing)

    # ---- pre-flight (added 2026-11-03 v0.6.0) -------------------------------
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
        try:
            check_slug(self.slug)
            if getattr(self.store, "slug", self.slug) != self.slug:
                problems.append("The project folder {!r} does not match the project ({!r}).".format(self.store.slug, self.slug))
        except ValueError as e:
            problems.append("The project's folder name is not valid: {}".format(e))
        # the v0.5.1 "fix these first" check
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
                    if not checked[aid] and not (a and any(a["code"] in m and "missing" in m for m in problems)):
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
                # [OLD 2026-11-03 v0.6.0 review] the starred take before reuse(), which can re-star another one
                # take = self.store.starred_take(prev)
                take = self._planned_upstream(sid, prev)  # added 2026-11-03 v0.6.0 review: the take the render uses
                files = (take or {}).get("files") or {}
                have = lambda k: bool(files.get(k)) and os.path.isfile(self.store.output_path(files[k]))  # noqa: E731
                if not take:
                    problems.append("{} continues from {}, which has no take yet. Render {} first, or both together."
                                    .format(self.label(sid), self.label(prev), self.label(prev)))
                elif not have("last") or not (have("tail") or have("video")):
                    problems.append("{} continues from {}, whose starred take {} is missing its files. Render {} again."
                                    .format(self.label(sid), self.label(prev), take.get("id"), self.label(prev)))
                # added 2026-11-03 v0.6.0 review: a tail clip longer than the take it is cut from (analysis warns)
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

    # ---- stars (added 2026-11-03 v0.6.0) ------------------------------------
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
    # [OLD 2026-11-03 v0.6.0 review] def progress(self, sid, n, passes, phase, step=0, steps=0, message=""):
    def progress(self, sid, n, passes, phase, step=0, steps=0, message="", warning=False):
        # [OLD 2026-11-03 v0.5.1->v0.6.0] send("reelwright.progress", {"slug": self.slug, "scene_id": sid, "pass": n, "passes": passes,
        #                                      "step": step, "steps": steps, "phase": phase, "message": message})
        # [OLD 2026-11-03 v0.6.0 review] send("reelwright.progress", {"slug": self.slug, "run_id": self.run_id, "scene_id": sid, "pass": n,
        #                                      "passes": passes, "step": step, "steps": steps, "phase": phase, "message": message})
        data = {"slug": self.slug, "run_id": self.run_id, "scene_id": sid, "pass": n,
                "passes": passes, "step": step, "steps": steps, "phase": phase, "message": message}
        if warning:  # added 2026-11-03 v0.6.0 review: an extra take failed; the message says which (see _warn)
            data["warning"] = True
        send("reelwright.progress", data)

    # [OLD 2026-11-03 v0.5.1->v0.6.0] Stop (a BaseException) and the checks before the start event left the editor
    # "rendering"; one failing scene ended the whole run; a run re-starred a take the user had picked
    # def run(self):
    #     targets, action = self.targets()
    #     blocked = [sid for sid in targets if self.result["scenes"][sid]["status"] == "error"]
    #     if blocked:
    #         msgs = [x["message"] for sid in blocked for x in self.result["scenes"][sid]["issues"] if x["level"] == "error"]
    #         raise RuntimeError("Reelwright: fix these first:\n" + "\n".join(msgs))
    #     missing = self.missing_models(targets)
    #     if missing:
    #         raise RuntimeError("Reelwright: these model files are missing:\n" + "\n".join(missing))
    #     reused = []
    #     for s in self.p["scenes"]:
    #         sr = self.result["scenes"][s["id"]]
    #         if sr["status"] == "cached" and sr["match"] and sr["match"] != sr["starred"]:
    #             self.store.star(s["id"], sr["match"])
    #             reused.append(s["id"])
    #     targets = self.order(targets)
    #     send("reelwright.run", {"slug": self.slug, "phase": "start", "targets": targets, "reused": reused})
    #     rendered = []
    #     try:
    #         encoded = {}
    #         if self.memory.get("encode_first"):
    #             for sid in targets:
    #                 sr = self.result["scenes"][sid]
    #                 scene = self.p["scenes"][sr["index"]]
    #                 for n in range(len(sr["plan"]["passes"])):
    #                     mm.throw_exception_if_processing_interrupted()
    #                     self.progress(sid, n + 1, len(sr["plan"]["passes"]), "encode")
    #                     encoded[(sid, n)] = self.encode(scene, sr, n)
    #             self.models.drop_clips()
    #             mm.unload_all_models()
    #             mm.soft_empty_cache()
    #         for sid in targets:
    #             self.render_scene(sid, encoded, variant_bump=action != "pending")
    #             rendered.append(sid)
    #     except Exception as e:
    #         send("reelwright.run", {"slug": self.slug, "phase": "end", "targets": targets, "reused": reused,
    #                                 "error": str(e)})
    #         raise
    #     send("reelwright.run", {"slug": self.slug, "phase": "end", "targets": targets, "reused": reused})
    #     return rendered
    # [/OLD]
    def run(self):
        """added 2026-11-03 v0.6.0: render the requested scenes; returns the ids of the scenes that got a take.

        Events: `rejected` when a check before any GPU work fails (then raises); otherwise `start`, and `end` always
        (also after Stop or an error, sent from a finally). A failing scene does not stop the others: the scenes
        that continue from it are skipped, and the run raises at the end.
        added 2026-11-03 v0.6.0 review: `end` also lists `warnings` [{scene_id, message}]: extra takes (a drift
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
        reused = self.reuse()
        send("reelwright.run", {"slug": self.slug, "run_id": self.run_id, "phase": "start", "targets": targets,
                                "reused": reused})
        # [OLD 2026-11-03 v0.6.0 review] no warnings field
        # state = {"slug": self.slug, "run_id": self.run_id, "phase": "end", "targets": targets, "reused": reused,
        #          "rendered": [], "failed": [], "skipped": [], "interrupted": False}
        # [/OLD]
        # added 2026-11-03 v0.6.0 review: warnings: [{scene_id, message}], extra takes (drift retake, variant 2..n)
        # that failed after the scene's first take was made
        state = {"slug": self.slug, "run_id": self.run_id, "phase": "end", "targets": targets, "reused": reused,
                 "rendered": [], "failed": [], "skipped": [], "warnings": [], "interrupted": False}
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
                # [OLD 2026-11-03 v0.6.0 review] self.render_job(sid, action, encoded)
                self.render_job(sid, action, encoded, state)  # added 2026-11-03 v0.6.0 review: for warnings
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
                    mm.throw_exception_if_processing_interrupted()
                    self.progress(sid, n + 1, count, "encode")
                    encoded[(sid, n)] = self.encode(scene, sr, n)
            except Exception as e:  # noqa: BLE001
                log.exception("Reelwright: encoding %s failed", self.label(sid))
                self._fail(sid, e, state, encoded)
        self.models.drop_clips()
        mm.unload_all_models()
        mm.soft_empty_cache()
        return encoded

    # [OLD 2026-11-03 v0.6.0 review] a failed drift retake or variant after the first take failed the whole scene
    # def render_job(self, sid, action, encoded):
    def render_job(self, sid, action, encoded, state=None):
        """One scene of the run: a take, a pass retake, or n variants.

        added 2026-11-03 v0.6.0 review: once the first take is added (and starred), a failing extra take (a drift
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
                # [OLD 2026-11-03 v0.6.0 review] takes.append(self.render_scene(sid, encoded, bump=True, star=k == 0, keep_encoded=k < n - 1))
                # added 2026-11-03 v0.6.0 review: only the first variant can fail the scene
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
        take = self.render_scene(sid, encoded, bump=action != "pending")
        # [OLD 2026-11-03 v0.6.0 review] return [take] + self._drift_retake(sid, take)
        # added 2026-11-03 v0.6.0 review: a failed drift retake keeps the take just made (and starred)
        try:
            return [take] + self._drift_retake(sid, take)
        except Exception as e:  # noqa: BLE001
            self._warn(sid, "{} kept; the drift retake failed: {}".format(take["id"], _err(e)), state)
            return [take]

    def _warn(self, sid, message, state):
        """added 2026-11-03 v0.6.0 review: an extra take of a scene failed after its first take was made. Logged with
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

    # ---- pass cache (added 2026-11-03 v0.6.0) ------------------------------
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
            frames, audio = media.load_video(path)
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
            if "pass_keys" in t:  # v0.6.0 takes use the pass cache
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

    def _save_pass(self, path, frames, audio, meta):
        media.save_video_atomic(frames, audio, path, crf=media.PASS_CRF)
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

    # ---- one take ----------------------------------------------------------
    def _generate(self, sid, scene, sr, n, encoded, keep_encoded, prev_pass, upstream, seed):
        """Encode (unless done already), guide, sample and decode one pass: (frames, audio)."""
        st = sr["settings"]
        n_pass = len(sr["plan"]["passes"])
        if (sid, n) in encoded:
            positive, latent = encoded[(sid, n)] if keep_encoded else encoded.pop((sid, n))
        else:
            self.progress(sid, n + 1, n_pass, "encode")
            positive, latent = self.encode(scene, sr, n)
        positive = self.guide(scene, sr, n, positive, latent, prev_pass, upstream)
        model = self.models.model(st)
        last_sent = [0.0]
        last_preview = [0.0]  # added 2026-11-02 v0.3.5
        preview_failed = [False]  # added 2026-11-02 v0.3.8: warn once per pass when a preview can't be made

        def on_step(step, total, preview=None, _n=n):
            now = time.time()
            if now - last_sent[0] > 0.4 or step == total:
                last_sent[0] = now
                self.progress(sid, _n + 1, n_pass, "sample", step, total)
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

        samples = _sample(model, positive, latent, seed, st, on_step)
        del positive, latent
        self.progress(sid, n + 1, n_pass, "decode")
        frames = nodes.VAEDecode().decode(self.models.vae(st["video_vae"], "vae"), samples)[0]
        audio = vae_decode_audio(self.models.vae(st["audio_vae"], "audio_vae"), samples)
        del samples
        return frames, audio

    # [OLD 2026-11-03 v0.5.1->v0.6.0] finished passes were thrown away on Stop or failure, the tail kept
    # max(60, overlap) frames of the last pass only, a drift retake was starred even when it scored worse,
    # and the take did not record what it continued from
    # def render_scene(self, sid, encoded, variant_bump, retake=False):
    #     sr = self.result["scenes"][sid]
    #     scene = self.p["scenes"][sr["index"]]
    #     plan = sr["plan"]
    #     st = sr["settings"]
    #     n_pass = len(plan["passes"])
    #     index = self.store.read_index(sid)
    #     same = [t for t in index["takes"] if t.get("key") == sr["key"]]
    #     variant = (max(t.get("variant", 0) for t in same) + 1) if (same and variant_bump) else 0
    #     take_id = self.store.new_take_id(sid)
    #     tdir = self.store.take_dir(sid, take_id)
    #     os.makedirs(os.path.join(tdir, "passes"), exist_ok=True)
    #     # added 2026-11-02 v0.2.0: readable file names, e.g. harbor_lights_02_the_long_walk_home_v3.mp4
    #     video_name = "{}_{:02d}_{}_{}.mp4".format(self.slug, sr["index"] + 1, slugify(scene["title"])[:40], take_id)
    #     vae = self.models.vae(st["video_vae"], "vae")
    #     avae = self.models.vae(st["audio_vae"], "audio_vae")
    #     t0 = time.time()
    #     prev_pass = None
    #     pass_files, firsts, last_out = [], None, None
    #     seeds = []
    #     for n, x in enumerate(plan["passes"]):
    #         mm.throw_exception_if_processing_interrupted()
    #         if (sid, n) in encoded:
    #             positive, latent = encoded.pop((sid, n))
    #         else:
    #             self.progress(sid, n + 1, n_pass, "encode")
    #             positive, latent = self.encode(scene, sr, n)
    #         positive = self.guide(scene, sr, n, positive, latent, prev_pass)
    #         model = self.models.model(st)
    #         seed = (x["seed"] + variant * 1000003) % (2 ** 63)
    #         seeds.append(seed)
    #         last_sent = [0.0]
    #         last_preview = [0.0]  # added 2026-11-02 v0.3.5
    #         preview_failed = [False]  # added 2026-11-02 v0.3.8: warn once per pass when a preview can't be made
    #
    #         # [OLD 2026-11-02 v0.3.4->v0.3.5] def on_step(step, total, _n=n):
    #         def on_step(step, total, preview=None, _n=n):
    #             now = time.time()
    #             if now - last_sent[0] > 0.4 or step == total:
    #                 last_sent[0] = now
    #                 self.progress(sid, _n + 1, n_pass, "sample", step, total)
    #             # added 2026-11-02 v0.3.5: about one latent preview per second, shown in the Render tab
    #             # [OLD 2026-11-02 v0.3.7->v0.3.8] once a second was too slow to follow; now every step (see PREVIEW_MIN_INTERVAL)
    #             # if preview is not None and (now - last_preview[0] > 1.0 or step == total):
    #             if preview is not None and (now - last_preview[0] >= PREVIEW_MIN_INTERVAL or step == total):
    #                 last_preview[0] = now
    #                 try:
    #                     image = preview()
    #                 except Exception as e:  # a preview must never stop a render
    #                     # [OLD 2026-11-02 v0.3.7->v0.3.8] failures were hidden at debug level
    #                     # log.debug("Reelwright preview failed: %s", e)
    #                     # added 2026-11-02 v0.3.8: the first failure of a pass shows in the ComfyUI console
    #                     if not preview_failed[0]:
    #                         preview_failed[0] = True
    #                         log.warning("Reelwright: no latent preview for scene %s pass %d: %s", sid, _n + 1, e)
    #                     else:
    #                         log.debug("Reelwright preview failed: %s", e)
    #                     return
    #                 send("reelwright.preview", {"slug": self.slug, "scene_id": sid, "pass": _n + 1, "passes": n_pass,
    #                                             "step": step, "steps": total, "image": image})
    #
    #         samples = _sample(model, positive, latent, seed, st, on_step)
    #         del positive, latent
    #         self.progress(sid, n + 1, n_pass, "decode")
    #         frames = nodes.VAEDecode().decode(vae, samples)[0]
    #         audio = vae_decode_audio(avae, samples)
    #         del samples
    #         self.progress(sid, n + 1, n_pass, "save")
    #         if n_pass > 1 or plan["kind"] == "short":
    #             path = os.path.join(tdir, "passes", "p{}.mp4".format(n + 1))
    #             media.save_video(frames, audio, path)
    #             pass_files.append(path)
    #         kept, kept_audio = media.trim(frames, audio, x["keep_in_frames"], x["keep_out_frames"])
    #         if n == 0:
    #             firsts = kept[:1].clone()
    #         last_out = (kept[-max(60, x["overlap_frames"]):].clone(),
    #                     media.slice_audio(kept_audio, max(0.0, kept.shape[0] / spec.FPS - 2.5), kept.shape[0] / spec.FPS)
    #                     if kept_audio is not None else None)
    #         if n_pass == 1:
    #             # [OLD 2026-11-02 v0.1.0->v0.2.0] media.save_video(kept, kept_audio, os.path.join(tdir, "video.mp4"))
    #             media.save_video(kept, kept_audio, os.path.join(tdir, video_name))
    #         if n + 1 < n_pass and plan["passes"][n + 1]["seam_before"] == "overlap":
    #             prev_pass = (frames[-plan["passes"][n + 1]["overlap_frames"]:].clone(), audio)
    #         else:
    #             prev_pass = None
    #         del frames, audio, kept, kept_audio
    #         _free(self.memory["policy"])
    #
    #     if n_pass > 1:
    #         segs = assemble.pass_segments(plan, pass_files, self.p["global"]["long"]["crossfade_frames"])
    #         # [OLD 2026-11-02 v0.1.0->v0.2.0] merge.join(segs, os.path.join(tdir, "video.mp4"), st["width"], st["height"], audio_fade_frames=0)
    #         merge.join(segs, os.path.join(tdir, video_name), st["width"], st["height"], audio_fade_frames=0)
    #     media.frame_to_png(firsts[0], os.path.join(tdir, "first.png"))
    #     tail_frames, tail_audio = last_out
    #     media.frame_to_png(tail_frames[-1], os.path.join(tdir, "last.png"))
    #     media.save_video(tail_frames, tail_audio, os.path.join(tdir, "tail.mp4"))
    #
    #     rel = lambda name: self.store.rel_output(os.path.join(tdir, name))
    #     take = {
    #         "id": take_id, "key": sr["key"], "variant": variant, "created": int(time.time()),
    #         "quality": st["quality"], "seconds": plan["frames"] / spec.FPS, "frames": plan["frames"],
    #         "overlap_frames": plan["passes"][0]["overlap_frames"], "seeds": seeds,
    #         "render_seconds": round(time.time() - t0, 1),
    #         # [OLD 2026-11-02 v0.1.0->v0.2.0] "files": {"video": rel("video.mp4"), "first": rel("first.png"), ...
    #         "files": {"video": rel(video_name), "first": rel("first.png"), "last": rel("last.png"), "tail": rel("tail.mp4"),
    #                   "passes": [self.store.rel_output(f) for f in pass_files]},
    #         "face": {},
    #     }
    #     if self.p["global"]["continuity"]["face_check"] and continuity.available():
    #         # [OLD 2026-11-03 v0.4.0->v0.4.1] take["face"] = continuity.check_scene(self.p, scene, self.store, os.path.join(tdir, video_name))  # [OLD 2026-11-02] was "video.mp4"
    #         # added 2026-11-03 v0.4.1: an optional check must not throw away a finished take (an insightface import
    #         # error used to stop the run here, before the take was listed)
    #         try:
    #             take["face"] = continuity.check_scene(self.p, scene, self.store, os.path.join(tdir, video_name))
    #         except Exception as e:
    #             log.warning("Reelwright: face check skipped for %s: %s", sid, e)
    #             self.progress(sid, n_pass, n_pass, "save", message="face check skipped: {}".format(str(e)[:160]))
    #     meta = dict(take, prompts=sr["prompts"], passes=sr["passes"],
    #                 settings={k: v for k, v in st.items() if k != "loras"}, loras=st["loras"])
    #     with open(os.path.join(tdir, "meta.json"), "w", encoding="utf-8") as f:
    #         json.dump(meta, f, indent=1)
    #     self.store.add_take(sid, take, star=True)
    #     self.progress(sid, n_pass, n_pass, "done", message=take_id)
    #     drift = self.p["global"]["continuity"]
    #     if not retake and take["face"] and drift["on_drift"] == "retake" and \
    #             min(take["face"].values()) < float(drift["face_threshold"]):
    #         log.info("Reelwright: %s drifted (%s), rendering one more take", sid, take["face"])
    #         self.render_scene(sid, {}, variant_bump=True, retake=True)
    # [/OLD]
    def render_scene(self, sid, encoded, bump=False, star=True, retake_pass=None, keep_encoded=False):
        """added 2026-11-03 v0.6.0: render one take of a scene and add it to the scene's takes; returns the take.

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
        for n, x in enumerate(plan["passes"]):
            mm.throw_exception_if_processing_interrupted()
            cpath = os.path.join(pdir, tp["file_keys"][n] + ".mp4")
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
            else:
                frames, audio = self._generate(sid, scene, sr, n, encoded, keep_encoded, prev_pass, upstream,
                                               tp["seeds"][n])
                sampled += int(x["gen_frames"])
                if cacheable:
                    self.progress(sid, n + 1, n_pass, "save")
                    self._save_pass(cpath, frames, audio, {
                        "key": tp["file_keys"][n], "pass_key": tp["pass_keys"][n], "scene_id": sid, "pass": n + 1,
                        "seed": tp["seeds"][n], "frames": int(x["gen_frames"]), "width": st["width"],
                        "height": st["height"], "created": int(time.time())})
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
            nxt = plan["passes"][n + 1] if n + 1 < n_pass else None
            prev_pass = (frames[-nxt["overlap_frames"]:].clone(), audio) \
                if nxt and nxt["seam_before"] == "overlap" else None
            del frames, audio, kept, kept_audio
            _free(self.memory["policy"])

        if n_pass > 1:
            self.progress(sid, n_pass, n_pass, "save", message="joining {} passes".format(n_pass))
            segs = assemble.pass_segments(plan, pass_files, self.p["global"]["long"]["crossfade_frames"])
            # Stop kills ffmpeg (merge.run_ffmpeg polls cancel, which raises ComfyUI's interrupt)
            merge.join(segs, video_path, st["width"], st["height"], audio_fade_frames=0,
                       cancel=lambda: mm.throw_exception_if_processing_interrupted() or False)
            tail = media.load_video(video_path, last_frames=TAIL_FRAMES)  # across the seams, as the cut shows it
        media.frame_to_png(first[0], os.path.join(tdir, "first.png"))
        tail_frames, tail_audio = tail
        media.frame_to_png(tail_frames[-1], os.path.join(tdir, "last.png"))
        media.save_video(tail_frames, tail_audio, os.path.join(tdir, "tail.mp4"), crf=media.PASS_CRF)
        del tail, tail_frames, tail_audio

        rel = lambda name: self.store.rel_output(os.path.join(tdir, name))  # noqa: E731
        take = {
            "id": take_id, "key": tp["key"], "variant": max(tp["offsets"]), "created": int(time.time()),
            "quality": st["quality"], "seconds": plan["frames"] / spec.FPS, "frames": plan["frames"],
            "overlap_frames": plan["passes"][0]["overlap_frames"], "seeds": tp["seeds"],
            "render_seconds": round(time.time() - t0, 1),
            "files": {"video": rel(video_name), "first": rel("first.png"), "last": rel("last.png"),
                      "tail": rel("tail.mp4"), "passes": [self.store.rel_output(f) for f in pass_files]},
            "face": {},
            # added 2026-11-03 v0.6.0
            "offsets": tp["offsets"], "pass_keys": tp["file_keys"], "start_mode": plan.get("start_mode"),
            "upstream": {"scene_id": prev, "take_id": upstream["id"]} if upstream else None,
            "prompts": sr["prompts"], "generated_frames": sum(int(x["gen_frames"]) for x in plan["passes"]),
            "sampled_frames": sampled, "cached_passes": from_cache,
            "width": st["width"], "height": st["height"], "steps": st["steps"], "face_score": None,
        }
        if self.p["global"]["continuity"]["face_check"] and continuity.available():
            # an optional check must not throw away a finished take
            try:
                take["face"] = continuity.check_scene(self.p, scene, self.store, video_path)
                take["face_score"] = continuity.score(take["face"])
            except Exception as e:
                log.warning("Reelwright: face check skipped for %s: %s", sid, e)
                self.progress(sid, n_pass, n_pass, "save", message="face check skipped: {}".format(str(e)[:160]))
        meta = dict(take, passes=[dict(x, key=k) for x, k in zip(sr["passes"], tp["pass_keys"])],
                    settings={k: v for k, v in st.items() if k != "loras"}, loras=st["loras"])
        write_json(os.path.join(tdir, "meta.json"), meta)  # through a temp file: Files -> Repair trusts meta.json
        self.store.add_take(sid, take, star=star)
        if star:
            self._mark_auto(sid, take_id)
        if cacheable:
            self._prune_pass_cache(sid)
        self.progress(sid, n_pass, n_pass, "done", message=take_id)
        return take
