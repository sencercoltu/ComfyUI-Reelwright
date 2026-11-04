"""The Reelwright node."""

import glob
import hashlib
import json
import logging
import os
import re  # added 2026-11-03 v0.6.0: full cut names
import uuid  # added 2026-11-03 v0.6.0: merge job ids
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


def _send(event, data):
    """Websocket event to the editor; never fails the node (added 2026-11-02 v0.2.1)."""
    try:
        from server import PromptServer
        PromptServer.instance.send_sync(event, data)
    except Exception:  # noqa: BLE001 - no server in tests
        pass


def _roots():
    return Roots(folder_paths.get_output_directory(), folder_paths.get_input_directory(),
                 folder_paths.get_user_directory())


def _placeholder_video():
    comp = Types.VideoComponents(images=torch.zeros(1, 64, 64, 3), frame_rate=Fraction(24), audio=None)
    return InputImpl.VideoFromComponents(comp)


# added 2026-11-03 v0.6.0: <slug>_cut_vN.mp4 only; drafts (cut_vN_draft.mp4), ranges and half-written
# (.partial.) files are not the film
FULL_CUT = re.compile(r".+_cut_v(\d+)\.mp4")


def full_cuts(store):
    """added 2026-11-03 v0.6.0: the project's full cuts, newest (highest number) first."""
    out = []
    for c in glob.glob(os.path.join(store.cuts_dir(), "*_cut_v*.mp4")):
        m = FULL_CUT.fullmatch(os.path.basename(c))
        if m:
            try:
                out.append((int(m.group(1)), os.path.getmtime(c), c))
            except OSError:
                continue
    return [c for _, _, c in sorted(out, reverse=True)]


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
        # [OLD 2026-11-03 v0.5.1->v0.6.0] a failure here (project folder, autosave, analysis) reached the editor only as
        # ComfyUI's error, and the render status stayed on "queued"
        # p = normalize_project(project)
        # store = ProjectStore(_roots(), p["slug"])
        # store.autosave(p)
        # wired = {"model": model, "clip": clip, "vae": vae, "audio_vae": audio_vae}
        # write_json(os.path.join(store.dir, "wired.json"),
        #            {"diffusion": model is not None, "text_encoder": clip is not None,
        #             "video_vae": vae is not None, "audio_vae": audio_vae is not None})
        # try:
        #     request = json.loads(run_request or "{}")
        # except json.JSONDecodeError:
        #     request = {"action": "pending"}
        #
        # rendered = Renderer(p, store, wired, request).run()
        # [/OLD]
        slug = ""
        try:
            p = normalize_project(project)
            slug = p.get("slug") or ""
            store = ProjectStore(_roots(), p["slug"])
            # [OLD 2026-11-03 v0.5.1->v0.6.0] store.autosave(p)  (overwrote another project living in the same folder)
            try:
                store.autosave(p, owner_check=True)
            except TypeError:  # a storage module without the owner check
                store.autosave(p)
            except ValueError as e:
                if getattr(e, "other", None) is None:
                    raise
                raise RuntimeError(
                    "Reelwright: the folder {!r} holds another project ({}). In the editor choose \"Use a separate "
                    "project\" or \"Take over this folder\", then render again.".format(
                        p["slug"], e.other.get("name") or e.other.get("id"))) from e
            wired = {"model": model, "clip": clip, "vae": vae, "audio_vae": audio_vae}
            write_json(os.path.join(store.dir, "wired.json"),
                       {"diffusion": model is not None, "text_encoder": clip is not None,
                        "video_vae": vae is not None, "audio_vae": audio_vae is not None})
            try:
                request = json.loads(run_request or "{}")
            except json.JSONDecodeError:
                request = {"action": "pending"}
            if not isinstance(request, dict):
                request = {"action": "pending"}
            renderer = Renderer(p, store, wired, request)
        except Exception as e:
            _send("reelwright.run", {"slug": slug, "phase": "rejected", "error": str(e)})  # added 2026-11-03 v0.6.0
            raise

        rendered = renderer.run()  # sends its own run events (rejected / start / end)

        wired_flags = {"diffusion": model is not None, "text_encoder": clip is not None,
                       "video_vae": vae is not None, "audio_vae": audio_vae is not None}
        result = analyze(p, store, wired_flags)
        # [OLD 2026-11-02 v0.2.0->v0.2.1] after a failed merge this fell back to the newest cut file, which could be the
        # half-written cut of that same failed merge, and probing it raised out of the node
        # video_path = None
        # if rendered and p["global"]["merge"]["auto_after_render"]:
        #     try:
        #         video_path = store.output_path(assemble.merge_project(result, store)["files"]["video"])
        #     except merge.MergeError as e:
        #         log.warning("Reelwright: merge skipped: %s", e)
        # if not video_path:
        #     cuts = sorted(glob.glob(os.path.join(store.cuts_dir(), "*_cut_v*.mp4")), key=os.path.getmtime)
        #     video_path = cuts[-1] if cuts else None
        #
        # last_take = None
        # for s in reversed(p["scenes"]):
        #     last_take = store.starred_take(s["id"])
        #     if last_take:
        #         break
        # if not video_path and last_take:
        #     video_path = store.output_path(last_take["files"]["video"])
        #
        # video = InputImpl.VideoFromFile(video_path) if video_path else _placeholder_video()
        # last = media.load_image(store.output_path(last_take["files"]["last"])) if last_take else torch.zeros(1, 64, 64, 3)
        # audio = {"waveform": torch.zeros(1, 2, 1), "sample_rate": 48000}
        # if video_path and merge.probe(video_path)["has_audio"]:
        #     audio = media.load_audio(video_path)
        # [/OLD]
        merged, merge_failed = None, False
        if rendered and p["global"]["merge"]["auto_after_render"]:
            # [OLD 2026-11-03 v0.5.1->v0.6.0] no job id or progress events; only a MergeError was caught
            # try:
            #     out = assemble.merge_project(result, store)
            #     merged = store.output_path(out["files"]["video"])
            #     _send("reelwright.merge", {"slug": p["slug"], "phase": "end", "files": out["files"],
            #                                "duration": out.get("duration")})
            # except merge.MergeError as e:
            #     merge_failed = True
            #     log.warning("Reelwright: merge skipped: %s", e)
            #     # added 2026-11-02 v0.2.1: tell the editor, which used to show nothing for a failed auto-merge
            #     _send("reelwright.merge", {"slug": p["slug"], "phase": "error", "error": str(e)[-600:]})
            # [/OLD]
            # added 2026-11-03 v0.6.0: the merge after a render has a job id (POST /reelwright/merge/cancel stops it,
            # and so does ComfyUI's Stop); its events carry the id like the editor's own merges
            job = "merge-" + (renderer.run_id or uuid.uuid4().hex[:12])
            ev = {"slug": p["slug"], "job": job}
            _send("reelwright.merge", dict(ev, phase="start"))
            try:
                out = assemble.merge_project(
                    result, store, progress=lambda x: _send("reelwright.merge", dict(ev, phase="progress",
                                                                                     percent=round(x * 100, 1))),
                    options={"interruptible": True}, job_id=job)
                merged = store.output_path(out["files"]["video"])
                _send("reelwright.merge", dict(ev, phase="end", files=out["files"], duration=out.get("duration")))
            except merge.MergeCancelled:
                merge_failed = True
                _send("reelwright.merge", dict(ev, phase="end", cancelled=True))
            except Exception as e:  # noqa: BLE001 - the scenes are rendered; a merge problem must not fail the node
                merge_failed = True
                log.warning("Reelwright: merge skipped: %s", e)
                _send("reelwright.merge", dict(ev, phase="error", error=str(e)[-600:]))
            except BaseException:  # Stop during the merge: ComfyUI's interrupt goes on up
                _send("reelwright.merge", dict(ev, phase="end", cancelled=True))
                raise

        last_take = None
        for s in reversed(p["scenes"]):
            last_take = store.starred_take(s["id"])
            if last_take:
                break
        take_video = store.output_path(last_take["files"]["video"]) if last_take else None
        # [OLD 2026-11-03 v0.5.1->v0.6.0] any file named like a cut, newest by time (a draft or range merge would win)
        # cuts = sorted((c for c in glob.glob(os.path.join(store.cuts_dir(), "*_cut_v*.mp4")) if ".partial." not in c),
        #               key=os.path.getmtime, reverse=True)
        cuts = full_cuts(store)
        # an older cut does not show what was just rendered, so after a failed merge the last take comes first
        candidates = [merged] + ([take_video] + cuts if merge_failed else cuts + [take_video])
        video_path, info = None, None
        for c in candidates:
            if c and os.path.isfile(c):
                try:
                    info = merge.probe(c)
                except (merge.MergeError, ValueError, OSError) as e:
                    log.warning("Reelwright: skipping unreadable video %s: %s", c, e)
                    continue
                video_path = c
                break

        video = InputImpl.VideoFromFile(video_path) if video_path else _placeholder_video()
        last = media.load_image(store.output_path(last_take["files"]["last"])) if last_take else torch.zeros(1, 64, 64, 3)
        audio = {"waveform": torch.zeros(1, 2, 1), "sample_rate": 48000}
        if video_path and info["has_audio"]:
            audio = media.load_audio(video_path)
        plan = plan_response(result)
        for s in plan["scenes"].values():
            s.pop("takes", None)
        return io.NodeOutput(video, last, audio, json.dumps(plan, ensure_ascii=False))


class ReelwrightExtension(ComfyExtension):
    async def get_node_list(self):
        return [Reelwright]
