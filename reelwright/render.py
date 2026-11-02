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
import time

import comfy.model_management as mm
import comfy.sample
import comfy.samplers
import comfy.utils
import folder_paths
import latent_preview
import nodes
from comfy_extras.nodes_audio import vae_decode_audio
from comfy_extras.nodes_custom_sampler import Guider_Basic, Noise_RandomNoise
from comfy_extras.nodes_minimax_h3 import MiniMaxH3AddGuide, MiniMaxH3ReferenceToVideo, MiniMaxH3SigmaShift
from server import PromptServer

from . import assemble, continuity, media, merge, spec
from .analysis import analyze
from .model import project_index, slugify  # slugify: added 2026-11-02 v0.2.0 for take file names

log = logging.getLogger("reelwright")


def send(event, data):
    PromptServer.instance.send_sync(event, data)


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


def preview_jpeg(previewer, x0):
    if getattr(x0, "is_nested", False):  # H3 latents carry video and audio; the first is the video
        x0 = x0.tensors[0]
    _, img, _ = previewer.decode_latent_to_preview_image("JPEG", x0)
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
    previewer = latent_preview.get_previewer(guider.model_patcher.load_device, guider.model_patcher.model.latent_format)
    pbar = comfy.utils.ProgressBar(steps)  # ComfyUI's queue progress, without an image

    def callback(step, x0, x, total_steps):
        pbar.update_absolute(step + 1, total_steps, None)
        # the image is only decoded when on_step asks for it (it throttles to about one per second)
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

    # ---- selection -------------------------------------------------------
    def targets(self):
        req = self.request
        action = req.get("action", "pending")
        chosen = set(req.get("scenes") or [])
        order = [s["id"] for s in self.p["scenes"]]
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
            if cur and scene["start"]["mode"] in ("last_frame", "tail") and \
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
                needs = scene["start"]["mode"] in ("last_frame", "tail") and prev in targets and prev not in done
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
            frames, audio = media.load_video(self._asset_path(v["asset"]), max_seconds=spec.REF_MEDIA_MAX_SECONDS)
            videos["ref_video_{}".format(k)] = frames
            if v["soundtrack"] and audio is not None:
                video_audios["ref_video_audio_{}".format(k)] = audio
        audios = {"ref_audio_{}".format(k): media.load_audio(self._asset_path(a["asset"])) for k, a in enumerate(b["audios"])}
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

    def guide(self, scene, sr, n, positive, latent, prev_pass):
        st = sr["settings"]
        vae = self.models.vae(st["video_vae"], "vae")
        avae = self.models.vae(st["audio_vae"], "audio_vae")
        for g in sr["builds"][n]["guides"]:
            image, audio = None, None
            if g["source"] == "prev_scene_last":
                take = self._upstream_take(sr["index"])
                image = media.load_image(self.store.output_path(take["files"]["last"]))
            elif g["source"] == "prev_scene_tail":
                take = self._upstream_take(sr["index"])
                image, audio = media.load_video(self.store.output_path(take["files"]["tail"]),
                                                last_seconds=g["frames"] / spec.FPS)
                image = image[-g["frames"]:]
            elif g["source"] == "prev_pass_tail":
                frames, aud = prev_pass
                image = frames[-g["frames"]:]
                if aud is not None:
                    dur = aud["waveform"].shape[-1] / aud["sample_rate"]
                    audio = media.slice_audio(aud, dur - g["frames"] / spec.FPS, dur)
            elif g["type"] == "image":
                image = media.load_image(self._asset_path(g["asset"]))
            else:
                image, _ = media.load_video(self._asset_path(g["asset"]), max_seconds=spec.REF_MEDIA_MAX_SECONDS)
            positive = MiniMaxH3AddGuide.execute(
                positive=positive, latent=latent, frame_idx=g["frame_idx"], vae=vae,
                audio_vae=avae if (g.get("audio") and audio is not None) else None,
                image=image, audio=audio if g.get("audio") else None).result[0]
        return positive

    # ---- run ---------------------------------------------------------------
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

    def progress(self, sid, n, passes, phase, step=0, steps=0, message=""):
        send("reelwright.progress", {"slug": self.slug, "scene_id": sid, "pass": n, "passes": passes,
                                     "step": step, "steps": steps, "phase": phase, "message": message})

    def run(self):
        targets, action = self.targets()
        blocked = [sid for sid in targets if self.result["scenes"][sid]["status"] == "error"]
        if blocked:
            msgs = [x["message"] for sid in blocked for x in self.result["scenes"][sid]["issues"] if x["level"] == "error"]
            raise RuntimeError("Reelwright: fix these first:\n" + "\n".join(msgs))
        missing = self.missing_models(targets)
        if missing:
            raise RuntimeError("Reelwright: these model files are missing:\n" + "\n".join(missing))
        reused = []
        for s in self.p["scenes"]:
            sr = self.result["scenes"][s["id"]]
            if sr["status"] == "cached" and sr["match"] and sr["match"] != sr["starred"]:
                self.store.star(s["id"], sr["match"])
                reused.append(s["id"])
        targets = self.order(targets)
        send("reelwright.run", {"slug": self.slug, "phase": "start", "targets": targets, "reused": reused})
        rendered = []
        try:
            encoded = {}
            if self.memory.get("encode_first"):
                for sid in targets:
                    sr = self.result["scenes"][sid]
                    scene = self.p["scenes"][sr["index"]]
                    for n in range(len(sr["plan"]["passes"])):
                        mm.throw_exception_if_processing_interrupted()
                        self.progress(sid, n + 1, len(sr["plan"]["passes"]), "encode")
                        encoded[(sid, n)] = self.encode(scene, sr, n)
                self.models.drop_clips()
                mm.unload_all_models()
                mm.soft_empty_cache()
            for sid in targets:
                self.render_scene(sid, encoded, variant_bump=action != "pending")
                rendered.append(sid)
        except Exception as e:
            send("reelwright.run", {"slug": self.slug, "phase": "end", "targets": targets, "reused": reused,
                                    "error": str(e)})
            raise
        send("reelwright.run", {"slug": self.slug, "phase": "end", "targets": targets, "reused": reused})
        return rendered

    def render_scene(self, sid, encoded, variant_bump, retake=False):
        sr = self.result["scenes"][sid]
        scene = self.p["scenes"][sr["index"]]
        plan = sr["plan"]
        st = sr["settings"]
        n_pass = len(plan["passes"])
        index = self.store.read_index(sid)
        same = [t for t in index["takes"] if t.get("key") == sr["key"]]
        variant = (max(t.get("variant", 0) for t in same) + 1) if (same and variant_bump) else 0
        take_id = self.store.new_take_id(sid)
        tdir = self.store.take_dir(sid, take_id)
        os.makedirs(os.path.join(tdir, "passes"), exist_ok=True)
        # added 2026-11-02 v0.2.0: readable file names, e.g. harbor_lights_02_the_long_walk_home_v3.mp4
        video_name = "{}_{:02d}_{}_{}.mp4".format(self.slug, sr["index"] + 1, slugify(scene["title"])[:40], take_id)
        vae = self.models.vae(st["video_vae"], "vae")
        avae = self.models.vae(st["audio_vae"], "audio_vae")
        t0 = time.time()
        prev_pass = None
        pass_files, firsts, last_out = [], None, None
        seeds = []
        for n, x in enumerate(plan["passes"]):
            mm.throw_exception_if_processing_interrupted()
            if (sid, n) in encoded:
                positive, latent = encoded.pop((sid, n))
            else:
                self.progress(sid, n + 1, n_pass, "encode")
                positive, latent = self.encode(scene, sr, n)
            positive = self.guide(scene, sr, n, positive, latent, prev_pass)
            model = self.models.model(st)
            seed = (x["seed"] + variant * 1000003) % (2 ** 63)
            seeds.append(seed)
            last_sent = [0.0]
            last_preview = [0.0]  # added 2026-11-02 v0.3.5

            # [OLD 2026-11-02 v0.3.4->v0.3.5] def on_step(step, total, _n=n):
            def on_step(step, total, preview=None, _n=n):
                now = time.time()
                if now - last_sent[0] > 0.4 or step == total:
                    last_sent[0] = now
                    self.progress(sid, _n + 1, n_pass, "sample", step, total)
                # added 2026-11-02 v0.3.5: about one latent preview per second, shown in the Render tab
                if preview is not None and (now - last_preview[0] > 1.0 or step == total):
                    last_preview[0] = now
                    try:
                        image = preview()
                    except Exception as e:  # a preview must never stop a render
                        log.debug("Reelwright preview failed: %s", e)
                        return
                    send("reelwright.preview", {"slug": self.slug, "scene_id": sid, "pass": _n + 1, "passes": n_pass,
                                                "step": step, "steps": total, "image": image})

            samples = _sample(model, positive, latent, seed, st, on_step)
            del positive, latent
            self.progress(sid, n + 1, n_pass, "decode")
            frames = nodes.VAEDecode().decode(vae, samples)[0]
            audio = vae_decode_audio(avae, samples)
            del samples
            self.progress(sid, n + 1, n_pass, "save")
            if n_pass > 1 or plan["kind"] == "short":
                path = os.path.join(tdir, "passes", "p{}.mp4".format(n + 1))
                media.save_video(frames, audio, path)
                pass_files.append(path)
            kept, kept_audio = media.trim(frames, audio, x["keep_in_frames"], x["keep_out_frames"])
            if n == 0:
                firsts = kept[:1].clone()
            last_out = (kept[-max(60, x["overlap_frames"]):].clone(),
                        media.slice_audio(kept_audio, max(0.0, kept.shape[0] / spec.FPS - 2.5), kept.shape[0] / spec.FPS)
                        if kept_audio is not None else None)
            if n_pass == 1:
                # [OLD 2026-11-02 v0.1.0->v0.2.0] media.save_video(kept, kept_audio, os.path.join(tdir, "video.mp4"))
                media.save_video(kept, kept_audio, os.path.join(tdir, video_name))
            if n + 1 < n_pass and plan["passes"][n + 1]["seam_before"] == "overlap":
                prev_pass = (frames[-plan["passes"][n + 1]["overlap_frames"]:].clone(), audio)
            else:
                prev_pass = None
            del frames, audio, kept, kept_audio
            _free(self.memory["policy"])

        if n_pass > 1:
            segs = assemble.pass_segments(plan, pass_files, self.p["global"]["long"]["crossfade_frames"])
            # [OLD 2026-11-02 v0.1.0->v0.2.0] merge.join(segs, os.path.join(tdir, "video.mp4"), st["width"], st["height"], audio_fade_frames=0)
            merge.join(segs, os.path.join(tdir, video_name), st["width"], st["height"], audio_fade_frames=0)
        media.frame_to_png(firsts[0], os.path.join(tdir, "first.png"))
        tail_frames, tail_audio = last_out
        media.frame_to_png(tail_frames[-1], os.path.join(tdir, "last.png"))
        media.save_video(tail_frames, tail_audio, os.path.join(tdir, "tail.mp4"))

        rel = lambda name: self.store.rel_output(os.path.join(tdir, name))
        take = {
            "id": take_id, "key": sr["key"], "variant": variant, "created": int(time.time()),
            "quality": st["quality"], "seconds": plan["frames"] / spec.FPS, "frames": plan["frames"],
            "overlap_frames": plan["passes"][0]["overlap_frames"], "seeds": seeds,
            "render_seconds": round(time.time() - t0, 1),
            # [OLD 2026-11-02 v0.1.0->v0.2.0] "files": {"video": rel("video.mp4"), "first": rel("first.png"), ...
            "files": {"video": rel(video_name), "first": rel("first.png"), "last": rel("last.png"), "tail": rel("tail.mp4"),
                      "passes": [self.store.rel_output(f) for f in pass_files]},
            "face": {},
        }
        if self.p["global"]["continuity"]["face_check"] and continuity.available():
            take["face"] = continuity.check_scene(self.p, scene, self.store, os.path.join(tdir, video_name))  # [OLD 2026-11-02] was "video.mp4"
        meta = dict(take, prompts=sr["prompts"], passes=sr["passes"],
                    settings={k: v for k, v in st.items() if k != "loras"}, loras=st["loras"])
        with open(os.path.join(tdir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1)
        self.store.add_take(sid, take, star=True)
        self.progress(sid, n_pass, n_pass, "done", message=take_id)
        drift = self.p["global"]["continuity"]
        if not retake and take["face"] and drift["on_drift"] == "retake" and \
                min(take["face"].values()) < float(drift["face_threshold"]):
            log.info("Reelwright: %s drifted (%s), rendering one more take", sid, take["face"])
            self.render_scene(sid, {}, variant_bump=True, retake=True)
