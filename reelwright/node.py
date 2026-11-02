"""The Reelwright node."""

import glob
import hashlib
import json
import logging
import os
from fractions import Fraction

import folder_paths
import torch
from comfy_api.latest import ComfyExtension, InputImpl, Types, io

from . import assemble, media, merge
from .analysis import analyze, plan_response
from .model import normalize_project
from .render import Renderer
from .storage import ProjectStore, Roots, write_json

log = logging.getLogger("reelwright")


def _roots():
    return Roots(folder_paths.get_output_directory(), folder_paths.get_input_directory(),
                 folder_paths.get_user_directory())


def _placeholder_video():
    comp = Types.VideoComponents(images=torch.zeros(1, 64, 64, 3), frame_rate=Fraction(24), audio=None)
    return InputImpl.VideoFromComponents(comp)


class Reelwright(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="Reelwright",
            display_name="Reelwright",
            category="video/Reelwright",
            description=("Timeline editor for MiniMax H3 ref2va. Scenes of any length are planned into valid H3 passes, "
                         "rendered one at a time to files on disk, cached by content, and merged into one film."),
            is_output_node=True,
            inputs=[
                io.String.Input("project", multiline=True, default="",
                                tooltip="The project as JSON. Edited through the timeline editor inside the node."),
                io.String.Input("run_request", default='{"action": "pending"}',
                                tooltip="Set by the editor's render buttons: which scenes this queue run renders."),
                io.Model.Input("model", optional=True,
                               tooltip="Optional H3 ref2va diffusion model. Wired in, it replaces the Global tab's model for every scene."),
                io.Clip.Input("clip", optional=True,
                              tooltip="Optional Qwen3-VL text encoder (CLIP type minimax). Replaces the Global tab's text encoder."),
                io.Vae.Input("vae", optional=True, tooltip="Optional H3 video VAE. Replaces the Global and per-scene video VAE."),
                io.Vae.Input("audio_vae", optional=True, tooltip="Optional H3 audio VAE. Replaces the Global and per-scene audio VAE."),
            ],
            outputs=[
                io.Video.Output(display_name="video", tooltip="The merged film, or the last finished scene when nothing is merged yet."),
                io.Image.Output(display_name="last_frame", tooltip="Last frame of the last finished scene."),
                io.Audio.Output(display_name="audio", tooltip="Soundtrack of the video output."),
                io.String.Output(display_name="scene_plan", tooltip="JSON: passes, prompts, status and cache keys per scene."),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, project, run_request, **kwargs):
        return hashlib.sha256((project + "\n" + run_request).encode()).hexdigest()

    @classmethod
    def execute(cls, project, run_request, model=None, clip=None, vae=None, audio_vae=None) -> io.NodeOutput:
        p = normalize_project(project)
        store = ProjectStore(_roots(), p["slug"])
        store.autosave(p)
        wired = {"model": model, "clip": clip, "vae": vae, "audio_vae": audio_vae}
        write_json(os.path.join(store.dir, "wired.json"),
                   {"diffusion": model is not None, "text_encoder": clip is not None,
                    "video_vae": vae is not None, "audio_vae": audio_vae is not None})
        try:
            request = json.loads(run_request or "{}")
        except json.JSONDecodeError:
            request = {"action": "pending"}

        rendered = Renderer(p, store, wired, request).run()

        wired_flags = {"diffusion": model is not None, "text_encoder": clip is not None,
                       "video_vae": vae is not None, "audio_vae": audio_vae is not None}
        result = analyze(p, store, wired_flags)
        video_path = None
        if rendered and p["global"]["merge"]["auto_after_render"]:
            try:
                video_path = store.output_path(assemble.merge_project(result, store)["files"]["video"])
            except merge.MergeError as e:
                log.warning("Reelwright: merge skipped: %s", e)
        if not video_path:
            cuts = sorted(glob.glob(os.path.join(store.cuts_dir(), "*_cut_v*.mp4")), key=os.path.getmtime)
            video_path = cuts[-1] if cuts else None

        last_take = None
        for s in reversed(p["scenes"]):
            last_take = store.starred_take(s["id"])
            if last_take:
                break
        if not video_path and last_take:
            video_path = store.output_path(last_take["files"]["video"])

        video = InputImpl.VideoFromFile(video_path) if video_path else _placeholder_video()
        last = media.load_image(store.output_path(last_take["files"]["last"])) if last_take else torch.zeros(1, 64, 64, 3)
        audio = {"waveform": torch.zeros(1, 2, 1), "sample_rate": 48000}
        if video_path and merge.probe(video_path)["has_audio"]:
            audio = media.load_audio(video_path)
        plan = plan_response(result)
        for s in plan["scenes"].values():
            s.pop("takes", None)
        return io.NodeOutput(video, last, audio, json.dumps(plan, ensure_ascii=False))


class ReelwrightExtension(ComfyExtension):
    async def get_node_list(self):
        return [Reelwright]
