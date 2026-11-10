"""Render orchestration inside a real ComfyUI checkout, with the H3 model calls stubbed.

Run with COMFYUI_PATH pointing at a ComfyUI checkout whose requirements are
installed. Everything except encoding, sampling and decoding is real: planning,
guides, file writing, pass stitching, takes, caching and the merge.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import types

import pytest

COMFY = os.environ.get("COMFYUI_PATH")
pytestmark = pytest.mark.skipif(not COMFY or importlib.util.find_spec("torch") is None,
                                reason="needs COMFYUI_PATH and torch")


@pytest.fixture
def comfy(monkeypatch, roots):
    sys.path.insert(0, COMFY)
    from comfy.cli_args import args
    args.cpu = True  # must be set before comfy.model_management is imported
    import folder_paths
    import server
    folder_paths.set_output_directory(roots.output)
    folder_paths.set_input_directory(roots.input)
    folder_paths.set_user_directory(roots.user)
    events = []

    class FakeServer:
        def send_sync(self, event, data, sid=None):
            events.append((event, data))
    monkeypatch.setattr(server.PromptServer, "instance", FakeServer(), raising=False)
    from reelwright import render
    yield render, events
    sys.path.remove(COMFY)


@pytest.fixture
def stubs(comfy, monkeypatch):
    import torch
    render, events = comfy
    calls = {"encode": [], "guides": [], "sample": []}

    def fake_ref2v(**kw):
        calls["encode"].append({"prompt": kw["prompt"], "length": kw["length"],
                                "images": sorted(kw["ref_images"] or {}), "videos": sorted(kw["ref_videos"] or {}),
                                "video_audios": sorted(kw["ref_video_audios"] or {}), "audios": sorted(kw["ref_audios"] or {}),
                                "audio_secs": [round(a["waveform"].shape[-1] / a["sample_rate"], 3) for a in (kw["ref_audios"] or {}).values()],
                                "image_order": list(kw["ref_images"] or {}),
                                "image_shapes": [tuple(v.shape) for v in (kw["ref_images"] or {}).values()],
                                "image_means": [round(float(v.float().mean()), 3) for v in (kw["ref_images"] or {}).values()],
                                "video_order": list(kw["ref_videos"] or {}),
                                "video_frames": [int(v.shape[0]) for v in (kw["ref_videos"] or {}).values()],
                                "video_last_means": [round(float(v[-1].float().mean()), 3)
                                                     for v in (kw["ref_videos"] or {}).values()],
                                "video_audio_secs": {k: round(a["waveform"].shape[-1] / a["sample_rate"], 3)
                                                     for k, a in (kw["ref_video_audios"] or {}).items()},
                                "vae": kw.get("vae")})
        return types.SimpleNamespace(result=([["cond", {}]], {"samples": torch.zeros(1), "frames": kw["length"],
                                                             "size": (kw["width"], kw["height"])}))

    def fake_guide(**kw):
        n = int(kw["image"].shape[0]) if kw.get("image") is not None else 0
        calls["guides"].append({"frame_idx": kw["frame_idx"], "frames": n, "audio": kw["audio"] is not None})
        calls.setdefault("guide_fit", []).append((kw["frame_idx"], n, kw["latent"]["frames"]))
        calls.setdefault("guide_vaes", []).append(kw.get("vae"))
        return types.SimpleNamespace(result=(kw["positive"],))

    def fake_sample(model, positive, latent, seed, settings, on_step):
        calls["sample"].append(seed)
        on_step(settings["steps"], settings["steps"])
        return latent

    class FakeDecode:
        def decode(self, vae, samples):
            calls.setdefault("decode_vaes", []).append(vae)
            w, h = samples["size"]
            n = samples["frames"]
            ramp = torch.linspace(0, 1, n).view(n, 1, 1, 1)
            return (ramp.expand(n, h, w, 3).clone(),)

    def fake_audio(vae, samples):
        n = int(samples["frames"] / 24 * 32000)
        return {"waveform": torch.zeros(1, 2, n), "sample_rate": 32000}

    monkeypatch.setattr(render.MiniMaxH3ReferenceToVideo, "execute", staticmethod(fake_ref2v))
    monkeypatch.setattr(render.MiniMaxH3AddGuide, "execute", staticmethod(fake_guide))
    monkeypatch.setattr(render, "_sample", fake_sample)
    monkeypatch.setattr(render.nodes, "VAEDecode", FakeDecode)
    monkeypatch.setattr(render, "vae_decode_audio", fake_audio)
    monkeypatch.setattr(render.Models, "clip", lambda self, st: "clip")
    monkeypatch.setattr(render.Models, "vae", lambda self, name, key: "vae:" + name)
    monkeypatch.setattr(render.Models, "model", lambda self, st: "model")
    monkeypatch.setattr(render.mm, "unload_all_models", lambda: None)
    monkeypatch.setattr(render.Renderer, "missing_models", lambda self, targets: [])
    return render, calls, events


def test_missing_models_are_reported_up_front(comfy, harbor, store):
    render, _ = comfy
    with pytest.raises(RuntimeError, match="model files are missing"):
        render.Renderer(harbor, store, {}, {"action": "pending"}).run()


def _real_assets(p, roots):
    from reelwright import merge
    ff = merge.ffmpeg_bin()
    for a in p["assets"]:
        path = os.path.join(roots.input, a["file"])
        if a["kind"] == "image":
            from PIL import Image
            Image.new("RGB", (96, 128), (180, 120, 90)).save(path, format="PNG")
        elif a["kind"] == "audio":
            subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=d=4.2", "-f", "wav", path], check=True)
        else:
            subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=96x64:r=24:d=4.2",
                            "-f", "lavfi", "-i", "sine=d=4.2", "-shortest", "-pix_fmt", "yuv420p", "-f", "mp4", path], check=True)


def test_render_pending_then_cache_then_partial(stubs, harbor, store, roots):
    render, calls, events = stubs
    from reelwright import assemble, merge
    from reelwright.analysis import analyze
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)

    done = render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    assert done == ["s_one", "s_long", "s_short"]

    # encode-first: every pass was encoded before sampling began
    long_passes = len(analyze(harbor, store)["scenes"]["s_long"]["plan"]["passes"])
    assert len(calls["encode"]) == 1 + long_passes + 1
    long_enc = calls["encode"][1]
    # Mara's sheet (the keyframe picture named in the prompt goes only with the pass that holds the keyframe)
    assert long_enc["images"][0] == "ref_image_0"
    assert long_enc["videos"] == ["ref_video_0"] and long_enc["video_audios"] == ["ref_video_audio_0"]
    # Mara's voice (sent with the passes where she speaks)
    assert any(e["audios"] == ["ref_audio_0"] for e in calls["encode"][1:1 + long_passes])

    # pass 1 continues the previous scene's 39-frame tail with audio; later passes get overlap or keyframe guides
    assert calls["guides"][0] == {"frame_idx": 0, "frames": 39, "audio": True}
    assert any(g["frames"] == 1 and g["frame_idx"] > 0 for g in calls["guides"])  # 25 s letter keyframe

    for sid, secs in (("s_one", 8.0), ("s_long", 32.0), ("s_short", 2.5)):
        take = store.starred_take(sid)
        video = store.output_path(take["files"]["video"])
        assert merge.probe(video)["duration"] == pytest.approx(secs, abs=0.1), sid
        assert re.fullmatch(r"harbor_lights_\d\d_[a-z0-9_]+_" + re.escape(take["id"]) + r"\.mp4", os.path.basename(video)), video
        for k in ("first", "last", "tail"):
            assert os.path.isfile(store.output_path(take["files"][k]))
    assert os.path.isfile(store.output_path(store.starred_take("s_short")["files"]["passes"][0]))  # handles kept

    phases = {d["phase"] for e, d in events if e == "reelwright.progress"}
    assert {"encode", "sample", "decode", "save", "done"} <= phases

    # nothing to do on a second pending run
    calls["sample"].clear()
    assert render.Renderer(harbor, store, {}, {"action": "pending"}).run() == []
    assert calls["sample"] == []

    # editing scene 1 re-renders it and the scene that continues from it, not the insert
    harbor["scenes"][0]["shots"][0]["text"] = "boats rock, gulls circle"
    assert render.Renderer(harbor, store, {}, {"action": "pending"}).run() == ["s_one", "s_long"]
    assert len(store.read_index("s_one")["takes"]) == 2

    # a new take of a cached scene uses a different seed
    before = list(calls["sample"])
    render.Renderer(harbor, store, {}, {"action": "take", "scenes": ["s_short"]}).run()
    assert calls["sample"][-1] not in before

    out = assemble.merge_project(analyze(harbor, store), store)
    assert out["duration"] == pytest.approx(8 + 32 - 39 / 24 + 2.5, abs=0.05)
    assert merge.probe(store.output_path(out["files"]["video"]))["duration"] == pytest.approx(out["duration"], abs=0.1)


def test_node_execute_returns_outputs(stubs, harbor, roots):
    render, calls, events = stubs
    from reelwright.node import Reelwright
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    out = Reelwright.execute(json.dumps(harbor), json.dumps({"action": "pending"}))
    video, last, audio, plan = out.result
    assert last.shape[-1] == 3
    assert audio["waveform"].shape[1] == 2
    assert json.loads(plan)["scenes"]["s_long"]["status"] == "cached"
    assert video.get_duration() == pytest.approx(8 + 32 - 39 / 24 + 2.5, abs=0.1)
    assert Reelwright.fingerprint_inputs("a", "b") != Reelwright.fingerprint_inputs("a", "c")


# A failed auto-merge must not break the node (it used to probe its own broken cut)
def test_node_survives_a_failed_merge(stubs, harbor, roots, monkeypatch):
    render, calls, events = stubs
    from reelwright import assemble as asm
    from reelwright import merge
    from reelwright.node import Reelwright
    from reelwright.storage import ProjectStore
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    store = ProjectStore(roots, harbor["slug"])
    os.makedirs(store.cuts_dir(), exist_ok=True)
    with open(os.path.join(store.cuts_dir(), harbor["slug"] + "_cut_v9.mp4"), "wb") as f:
        f.write(b"half-written")

    def boom(*a, **k):
        raise merge.MergeError("ffmpeg failed: Cannot select channel layout")
    monkeypatch.setattr(asm, "merge_project", boom)
    out = Reelwright.execute(json.dumps(harbor), json.dumps({"action": "pending"}))
    video, last, audio, plan = out.result
    assert video.get_duration() == pytest.approx(2.5, abs=0.1)   # the last scene's take, not the broken cut
    assert audio["waveform"].shape[1] == 2


# Latent previews go to the Render tab as reelwright.preview events, not onto the node
def test_latent_preview_events(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    asked = []

    def sample_with_preview(model, positive, latent, seed, settings, on_step):
        n = settings["steps"]
        for k in range(1, n + 1):
            on_step(k, n, lambda k=k: asked.append(k) or "data:image/jpeg;base64,AAAA")
        return latent
    monkeypatch.setattr(render, "_sample", sample_with_preview)
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_one"]}).run()
    previews = [d for e, d in events if e == "reelwright.preview"]
    assert previews and all(d["scene_id"] == "s_one" and d["image"].startswith("data:image/jpeg") for d in previews)
    assert previews[-1]["step"] == previews[-1]["steps"]          # the last step is always shown
    assert len(asked) < 5                                          # decoded only when sent (at most every 0.25 s)


# Previews follow the sampler (it used to be at most one a second)
def test_latent_preview_every_step_when_steps_are_slow(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    clock = [1000.0]

    def sample_with_preview(model, positive, latent, seed, settings, on_step):
        for k in range(1, 7):
            clock[0] += render.PREVIEW_MIN_INTERVAL + 0.05  # a step a little slower than the preview gap
            on_step(k, 6, lambda: "data:image/jpeg;base64,AAAA")
        return latent
    monkeypatch.setattr(render, "_sample", sample_with_preview)
    monkeypatch.setattr(render.time, "time", lambda: clock[0])
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_one"]}).run()
    steps = [d["step"] for e, d in events if e == "reelwright.preview"]
    assert steps == [1, 2, 3, 4, 5, 6]
    assert render.PREVIEW_MIN_INTERVAL < 1.0


def test_latent_preview_failure_warns_once(stubs, harbor, store, roots, monkeypatch, caplog):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    clock = [1000.0]

    def sample_with_bad_preview(model, positive, latent, seed, settings, on_step):
        for k in range(1, 5):
            clock[0] += 1.0
            on_step(k, 4, lambda: (_ for _ in ()).throw(RuntimeError("taeh3 missing")))
        return latent
    monkeypatch.setattr(render, "_sample", sample_with_bad_preview)
    monkeypatch.setattr(render.time, "time", lambda: clock[0])
    with caplog.at_level("DEBUG", logger="reelwright"):
        render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_one"]}).run()
    warnings = [r for r in caplog.records if r.levelname == "WARNING" and "no latent preview" in r.getMessage()]
    assert len(warnings) == 1 and "taeh3 missing" in warnings[0].getMessage()
    assert not [d for e, d in events if e == "reelwright.preview"]
    assert [d for e, d in events if e == "reelwright.run" and d.get("phase") == "end" and not d.get("error")]  # the render went on


def test_preview_jpeg_handles_nested_latents(comfy):
    render, _ = comfy
    import torch
    from PIL import Image
    seen = []

    class Previewer:
        def decode_latent_to_preview_image(self, fmt, x0):
            seen.append(tuple(x0.shape))
            return ("JPEG", Image.new("RGB", (1344, 768), (200, 80, 40)), 512)
    nested = types.SimpleNamespace(is_nested=True, tensors=[torch.zeros(1, 4, 3, 8, 8), torch.zeros(1, 2, 5)])
    url = render.preview_jpeg(Previewer(), nested)
    assert seen == [(1, 4, 3, 8, 8)] and url.startswith("data:image/jpeg;base64,")
    import base64
    import io
    img = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert max(img.size) == render.PREVIEW_MAX_SIDE


# the
# preview shows the middle of what a pass makes new, not the first frame a continuation or guide fixes
def test_preview_shows_the_middle_of_the_new_part(comfy):
    render, _ = comfy
    import torch
    from PIL import Image
    seen = []

    class Previewer:
        def decode_latent_to_preview_image(self, fmt, x0):
            seen.append(float(x0[0, 0, 0, 0, 0]))
            return ("JPEG", Image.new("RGB", (64, 36)), 512)
    lat = torch.arange(10, dtype=torch.float32).view(1, 1, 10, 1, 1).expand(1, 4, 10, 2, 2).clone()
    render.preview_jpeg(Previewer(), lat)
    render.preview_jpeg(Previewer(), lat, 6)
    render.preview_jpeg(Previewer(), lat, 99)
    assert seen == [0.0, 6.0, 9.0]
    assert render.preview_frame({"seam_before": "none", "keep_in_frames": 0, "keep_out_frames": 362}) == 46  # frame 181
    assert render.preview_frame({"seam_before": "overlap", "overlap_frames": 39, "keep_in_frames": 0,
                                 "keep_out_frames": 226}) == 33  # frame 132 of 226: past the 39 repeated frames
    assert render.preview_frame({}) is None


# VideoHelperSuite's animated previews wrap latent_preview.get_previewer; Reelwright uses the
# original underneath (VHS's previewer sends its own frames under the node and returns no image)
def test_stock_previewer_skips_wrappers(comfy, monkeypatch):
    import functools

    import latent_preview
    render, _ = comfy
    seen = []

    def original(device, latent_format):
        seen.append("original")
        return "stock"

    def vhs_like(device, latent_format, *a, **k):
        seen.append("wrapper")
        return "wrapped"
    functools.update_wrapper(vhs_like, original)

    def outer(device, latent_format):
        seen.append("outer")
        return "outer"
    functools.update_wrapper(outer, vhs_like)
    monkeypatch.setattr(latent_preview, "get_previewer", outer)
    assert render.stock_previewer("cpu", None) == "stock" and seen == ["original"]


def test_preview_jpeg_explains_a_previewer_without_image(comfy):
    render, _ = comfy

    class WrappedPreviewer:  # like VHS's: sends frames itself, returns None
        def decode_latent_to_preview_image(self, fmt, x0):
            return None
    import torch
    with pytest.raises(RuntimeError, match="WrappedPreviewer.*no image"):
        render.preview_jpeg(WrappedPreviewer(), torch.zeros(1, 4, 2, 8, 8))


# The anchor sheet keeps every anchor (no 3×3 cap) and shapes cells like the pictures
def test_sheet_image_grid(comfy, tmp_path):
    from PIL import Image

    from reelwright import media
    paths = []
    for i in range(10):
        path = str(tmp_path / "a{}.png".format(i))
        Image.new("RGB", (600, 800), (i * 20, 10, 10)).save(path)
        paths.append(path)
    assert media.sheet_grid(9) == (3, 3) and media.sheet_grid(10) == (4, 3) and media.sheet_grid(1) == (1, 1)
    im = media.sheet_image(paths, cell=100)
    cw, ch = round(100 * (0.75 ** 0.5)), round(100 / (0.75 ** 0.5))
    assert im.size == (4 * cw, 3 * ch)
    assert im.getpixel((3 * cw + cw // 2, 2 * ch + ch // 2)) == (21, 23, 28)        # 10 of 12 cells used
    assert im.getpixel((cw // 2, ch // 2))[0] == 0 and im.getpixel((cw + cw // 2, ch // 2))[0] == 20
    t = media.make_sheet(paths[:2], cell=64)
    assert tuple(t.shape)[0] == 1 and t.shape[-1] == 3


# A failing face check no longer loses the finished take
def test_face_check_failure_keeps_the_take(stubs, harbor, store, roots, monkeypatch, caplog):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    harbor["global"]["continuity"]["face_check"] = True
    _real_assets(harbor, roots)
    monkeypatch.setattr(render.continuity, "available", lambda: True)

    def broken(*a, **k):
        raise ImportError("cannot import name 'median_blur' from 'albucore'")
    monkeypatch.setattr(render.continuity, "check_scene", broken)
    with caplog.at_level("WARNING", logger="reelwright"):
        render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_one"]}).run()
    idx = store.read_index("s_one")
    assert [t["id"] for t in idx["takes"]] == ["v1"] and idx["takes"][0]["face"] == {}
    assert any("face check skipped" in r.getMessage() for r in caplog.records)
    assert any(d.get("message", "").startswith("face check skipped") for e, d in events if e == "reelwright.progress")


# A song on the soundtrack is cut per pass, sent as the pass's audio reference, mixed in the cut
def test_render_with_a_soundtrack(stubs, harbor, store, roots):
    render, calls, events = stubs
    from reelwright import assemble, merge, spec
    from reelwright.analysis import analyze
    from reelwright.model import normalize_project
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    song = "reelwright/harbor_lights/song.wav"
    subprocess.run([merge.ffmpeg_bin(), "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=60", "-ac", "2",
                    os.path.join(roots.input, song)], check=True)
    harbor["assets"].append({"id": "a_song", "kind": "audio", "name": "song", "file": song, "duration": 60.0})
    harbor["soundtrack"] = [{"asset": "a_song", "start": 0.0}]
    p = normalize_project(harbor)
    done = render.Renderer(p, store, {}, {"action": "pending"}).run()
    assert done == ["s_one", "s_long", "s_short"]
    plans = analyze(p, store)["scenes"]
    lengths = [min(spec.REF_MEDIA_MAX_SECONDS, x["gen_frames"] / spec.FPS) for sid in done for x in plans[sid]["plan"]["passes"]]
    assert len(calls["encode"]) == len(lengths)
    for enc in calls["encode"]:
        assert "Audio" in enc["prompt"] and "is the song this part of the film is cut to" in enc["prompt"]
        assert len(enc["audios"]) == 1  # the song, not Mara's voice
    assert sorted(round(x, 2) for e in calls["encode"] for x in e["audio_secs"]) == sorted(round(x, 2) for x in lengths)
    wavs = os.listdir(os.path.join(store.dir, "soundtrack"))
    assert len(wavs) == len(lengths)  # one WAV per pass: each covers another part of the song
    assert all(w.endswith(".wav") and ".partial" not in w for w in wavs)
    # every scene is cached: moving the song makes them stale again
    assert all(s["status"] == "cached" for s in analyze(p, store)["scenes"].values())
    p["soundtrack"][0]["start"] = 0.5
    assert all(s["status"] == "stale" for s in analyze(p, store)["scenes"].values())
    p["soundtrack"][0]["start"] = 0.0
    out = assemble.merge_project(analyze(p, store), store)
    assert out["soundtrack"] == 1
    from reelwright.model import scene_starts
    assert out["duration"] == pytest.approx(scene_starts(p)[1], abs=0.05)


def _run_events(events, phase=None):
    return [d for e, d in events if e == "reelwright.run" and (phase is None or d.get("phase") == phase)]


def _stop_on(render, monkeypatch, calls, nth):
    """The stub sampler raises ComfyUI's Stop on its nth call."""
    import comfy.model_management as mm
    real = render._sample

    def sample(model, positive, latent, seed, settings, on_step):
        if len(calls["sample"]) + 1 == nth:
            raise mm.InterruptProcessingException()
        return real(model, positive, latent, seed, settings, on_step)
    monkeypatch.setattr(render, "_sample", sample)


def test_run_end_event_is_sent_after_stop(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    import comfy.model_management as mm
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    _stop_on(render, monkeypatch, calls, 2)
    with pytest.raises(mm.InterruptProcessingException):
        render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    start, end = _run_events(events, "start"), _run_events(events, "end")
    assert len(start) == 1 and len(end) == 1
    assert end[0]["interrupted"] is True and end[0]["error"] and end[0]["run_id"] == start[0]["run_id"]
    assert end[0]["rendered"] == ["s_one"] and end[0]["failed"] == [] and end[0]["skipped"] == []
    assert end[0]["targets"] == ["s_one", "s_long", "s_short"]
    from reelwright import jobs
    assert not jobs.is_busy(harbor["slug"], "render")  # the render job is released


def test_precheck_failure_is_rejected_before_start(stubs, harbor, store, roots):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    os.remove(os.path.join(roots.input, "reelwright/harbor_lights/dolly.mp4"))
    with pytest.raises(RuntimeError, match="fix these first") as e:
        render.Renderer(harbor, store, {}, {"action": "all"}).run()
    assert "dolly" in str(e.value)
    assert [d["phase"] for d in _run_events(events)] == ["rejected"]
    assert "dolly" in _run_events(events)[0]["error"] and calls["sample"] == [] and calls["encode"] == []
    # a continuing scene whose upstream has no take and is not rendered in this run
    events.clear()
    _real_assets(harbor, roots)
    with pytest.raises(RuntimeError, match="no take yet"):
        render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_long"]}).run()
    assert [d["phase"] for d in _run_events(events)] == ["rejected"]
    # an unknown action is rejected too
    events.clear()
    with pytest.raises(ValueError):
        render.Renderer(harbor, store, {}, {"action": "bogus"}).run()
    assert [d["phase"] for d in _run_events(events)] == ["rejected"]


def test_failing_scene_skips_the_scenes_that_continue_from_it(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    real = render._sample
    s_one_seed = harbor["global"]["sampling"]["seed"]  # scene 1's first take samples with the base seed

    def sample(model, positive, latent, seed, settings, on_step):
        if seed == s_one_seed:
            raise RuntimeError("CUDA out of memory (test)")
        return real(model, positive, latent, seed, settings, on_step)
    monkeypatch.setattr(render, "_sample", sample)
    with pytest.raises(RuntimeError, match="1 scene failed") as e:
        render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    assert "out of memory" in str(e.value) and "skipped" in str(e.value)
    end = _run_events(events, "end")[0]
    assert end["rendered"] == ["s_short"] and end["interrupted"] is False and "error" not in end
    assert end["failed"] == [{"scene_id": "s_one", "error": "CUDA out of memory (test)"}]
    assert [x["scene_id"] for x in end["skipped"]] == ["s_long"] and "01 Harbor at dusk" in end["skipped"][0]["reason"]
    phases = {(d["scene_id"], d["phase"]) for e, d in events if e == "reelwright.progress"}
    assert ("s_one", "error") in phases and ("s_long", "skipped") in phases and ("s_short", "done") in phases
    assert store.starred_take("s_short") and not store.starred_take("s_one") and not store.starred_take("s_long")


def test_pass_cache_is_reused_after_stop(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    from reelwright.analysis import analyze
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    import comfy.model_management as mm
    _stop_on(render, monkeypatch, calls, 4)  # s_one, s_long pass 1 and 2 finish; Stop during s_long pass 3
    with pytest.raises(mm.InterruptProcessingException):
        render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    assert len(calls["sample"]) == 3
    pdir = os.path.join(store.scene_dir("s_long"), "passes")
    assert len([f for f in os.listdir(pdir) if f.endswith(".mp4")]) == 2
    assert not any(".partial." in f for f in os.listdir(pdir))
    first_seeds = list(calls["sample"])
    calls["sample"].clear()
    events.clear()
    monkeypatch.setattr(render, "_sample", _plain_sampler(calls))
    done = render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    assert done == ["s_long", "s_short"]
    assert len(calls["sample"]) == 2 and calls["sample"][0] not in first_seeds  # only pass 3 of s_long and s_short
    reuse = [d["pass"] for e, d in events if e == "reelwright.progress" and d["phase"] == "reuse"]
    assert reuse == [1, 2]
    take = store.starred_take("s_long")
    plan = analyze(harbor, store)["scenes"]["s_long"]["plan"]
    assert take["cached_passes"] == 2 and take["sampled_frames"] == plan["passes"][2]["gen_frames"]
    assert len(take["pass_keys"]) == 3 and all(os.path.isfile(os.path.join(pdir, k + ".mp4")) for k in take["pass_keys"])
    from reelwright import merge
    assert merge.probe(store.output_path(take["files"]["video"]))["duration"] == pytest.approx(32.0, abs=0.1)


def _plain_sampler(calls):
    def fake_sample(model, positive, latent, seed, settings, on_step):
        calls["sample"].append(seed)
        on_step(settings["steps"], settings["steps"])
        return latent
    return fake_sample


def test_tail_is_the_last_124_frames_across_passes(stubs, harbor, store, roots):
    render, calls, events = stubs
    from reelwright import media, merge
    from reelwright.analysis import analyze
    harbor["global"]["output"].update(width=64, height=32)
    harbor["global"]["long"].update(max_pass_frames=158, seam_mode="cuts")
    _real_assets(harbor, roots)
    harbor["scenes"] = [harbor["scenes"][0]]
    harbor["scenes"][0].update(duration=10.0, shots=[{"id": "h_a", "t": 0, "camera": "Wide", "text": "a"},
                                                     {"id": "h_b", "t": 6.5, "camera": "Close", "text": "b"}])
    plan = analyze(harbor, store)["scenes"]["s_one"]["plan"]
    assert [x["keep_out_frames"] - x["keep_in_frames"] for x in plan["passes"]] == [156, 84]  # last pass < 124
    render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    take = store.starred_take("s_one")
    frames, audio = media.load_video(store.output_path(take["files"]["tail"]))
    assert frames.shape[0] == render.TAIL_FRAMES == 124
    assert audio is not None and audio["waveform"].shape[-1] / audio["sample_rate"] == pytest.approx(124 / 24, abs=0.05)
    # the stub decoder ramps 0 -> 1 through each pass: the tail starts late in pass 1 and ends late in pass 2
    lum = frames.mean(dim=(1, 2, 3))
    assert lum[0] > 0.6 and lum[39] > 0.9 and lum[40] < 0.1 and lum[-1] > 0.6
    last = media.load_image(store.output_path(take["files"]["last"]))
    assert float(last.mean()) == pytest.approx(float(lum[-1]), abs=0.05)
    assert merge.probe(store.output_path(take["files"]["video"]))["duration"] == pytest.approx(10.0, abs=0.1)


def test_new_take_upstream_marks_the_continuing_scene_stale(stubs, harbor, store, roots):
    render, calls, events = stubs
    from reelwright.analysis import analyze
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    assert store.starred_take("s_long")["upstream"] == {"scene_id": "s_one", "take_id": "v1"}
    assert analyze(harbor, store)["scenes"]["s_long"]["status"] == "cached"
    render.Renderer(harbor, store, {}, {"action": "take", "scenes": ["s_one"]}).run()
    r = analyze(harbor, store)["scenes"]
    assert r["s_long"]["status"] == "stale" and r["s_long"]["upstream_take"] == "v2" and r["s_long"]["upstream_changed"]
    calls["sample"].clear()
    assert render.Renderer(harbor, store, {}, {"action": "pending"}).run() == ["s_long"]
    assert store.starred_take("s_long")["upstream"]["take_id"] == "v2"
    assert analyze(harbor, store)["scenes"]["s_long"]["status"] == "cached"


def test_pass_retake(stubs, harbor, store, roots):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    harbor["global"]["long"]["seam_mode"] = "overlap"
    _real_assets(harbor, roots)
    render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    v1 = store.starred_take("s_long")
    n = len(v1["seeds"])
    assert n >= 3
    calls["sample"].clear()
    calls["guides"].clear()
    events.clear()
    render.Renderer(harbor, store, {}, {"action": "pass_retake", "scene_id": "s_long", "pass": 2}).run()
    v2 = store.starred_take("s_long")
    assert v2["id"] != v1["id"] and v2["seeds"][0] == v1["seeds"][0] and v2["seeds"][1] != v1["seeds"][1]
    assert v2["seeds"][2:] == v1["seeds"][2:]
    assert calls["sample"] == v2["seeds"][1:]            # pass 1 from the pass cache; later passes re-guided
    assert v2["pass_keys"][0] == v1["pass_keys"][0] and v2["pass_keys"][2] != v1["pass_keys"][2]
    assert [d["pass"] for e, d in events if e == "reelwright.progress" and d["phase"] == "reuse"] == [1]
    # a pass that does not exist is refused before anything runs
    with pytest.raises(ValueError, match="no pass 9"):
        render.Renderer(harbor, store, {}, {"action": "pass_retake", "scene_id": "s_long", "pass": 9}).run()


def test_variants_star_the_best_face_match(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    render.Renderer(harbor, store, {}, {"action": "variants", "scene_ids": ["s_short", "s_one"], "n": 3}).run()
    for sid in ("s_one", "s_short"):
        idx = store.read_index(sid)
        assert [t["id"] for t in idx["takes"]] == ["v1", "v2", "v3"] and idx["starred"] == "v1"
        assert len({t["seeds"][0] for t in idx["takes"]}) == 3
    # with face check on, the best match is starred
    harbor["global"]["continuity"]["face_check"] = True
    monkeypatch.setattr(render.continuity, "available", lambda: True)
    scores = iter([0.41, 0.77, 0.52])
    monkeypatch.setattr(render.continuity, "check_scene", lambda *a, **k: {"c_mara": next(scores)})
    render.Renderer(harbor, store, {}, {"action": "variants", "scene_ids": ["s_short"], "n": 3}).run()
    idx = store.read_index("s_short")
    assert [t["id"] for t in idx["takes"]][-3:] == ["v4", "v5", "v6"] and idx["starred"] == "v5"
    assert idx["takes"][-2]["face_score"] == 0.77


def test_drift_retake_is_starred_only_when_better(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    harbor["global"]["continuity"].update(face_check=True, on_drift="retake", face_threshold=0.8)
    _real_assets(harbor, roots)
    monkeypatch.setattr(render.continuity, "available", lambda: True)
    scores = iter([0.6, 0.4, 0.5, 0.7])
    monkeypatch.setattr(render.continuity, "check_scene", lambda *a, **k: {"c_mara": next(scores)})
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_short"]}).run()
    idx = store.read_index("s_short")
    assert [t["id"] for t in idx["takes"]] == ["v1", "v2"] and idx["starred"] == "v1"  # the retake scored worse
    render.Renderer(harbor, store, {}, {"action": "take", "scenes": ["s_short"]}).run()
    idx = store.read_index("s_short")
    assert [t["id"] for t in idx["takes"]] == ["v1", "v2", "v3", "v4"] and idx["starred"] == "v4"


def test_manual_star_survives_the_next_run(stubs, harbor, store, roots):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_short"]}).run()
    harbor["scenes"][2]["shots"] = [{"id": "h_x", "t": 0, "camera": "Close", "text": "a hand on the door"}]
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_short"]}).run()
    assert store.read_index("s_short")["starred"] == "v2"
    store.star("s_short", "v1")  # the user prefers the first one
    events.clear()
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_one"]}).run()
    assert store.read_index("s_short")["starred"] == "v1"
    assert _run_events(events, "start")[0]["reused"] == []
    # undoing the edit: the run stars the take that matches (the star was set by a render)
    harbor["scenes"][2]["shots"] = []
    store.star("s_short", "v2")
    idx = store.read_index("s_short")
    idx["auto_star"] = "v2"
    store.write_index("s_short", idx)
    events.clear()
    render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    assert store.read_index("s_short")["starred"] == "v1" and "s_short" in _run_events(events, "start")[0]["reused"]


def test_short_scene_keep_window_move_retrims_without_sampling(stubs, harbor, store, roots):
    render, calls, events = stubs
    from reelwright import merge
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_short"]}).run()
    calls["sample"].clear()
    harbor["scenes"][2]["trim"]["in"] = 0.5
    assert render.Renderer(harbor, store, {}, {"action": "pending"}).run() == ["s_one", "s_long", "s_short"]
    assert len([s for s in calls["sample"]]) == 1 + 3      # s_one and the three passes of s_long; s_short re-trimmed
    take = store.starred_take("s_short")
    assert take["id"] == "v2" and take["sampled_frames"] == 0 and take["cached_passes"] == 1
    assert merge.probe(store.output_path(take["files"]["video"]))["duration"] == pytest.approx(2.5, abs=0.1)


def test_video_guides_fit_their_pass(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    from reelwright import analysis
    real_lint = analysis.lint_project

    def lint_as_warnings(*a, **k):  # whatever level the lint gives a long clip, the render must place it inside
        return [dict(x, level="warning") if "clip" in x["message"] else x for x in real_lint(*a, **k)]
    monkeypatch.setattr(analysis, "lint_project", lint_as_warnings)
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    harbor["scenes"][2]["refs"] = [{"id": "r_end", "asset": "a_dolly", "role": "last_frame"}]
    harbor["scenes"][0]["refs"] = [{"id": "r_k", "asset": "a_dolly", "role": "keyframe", "time": 7.9}]
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_one", "s_short"]}).run()
    fits = calls["guide_fit"]
    assert len(fits) == 2 and all(0 <= idx and idx + n <= length for idx, n, length in fits)
    short = next(f for f in fits if f[2] == 124)
    plan_last = 29 + 60 - 1  # keep window 29..89 of the 124-frame pass
    assert short[0] + short[1] - 1 == plan_last and (short[1] - 5) % 17 == 0   # ends on the scene's last frame
    keyf = next(f for f in fits if f[2] == 192)
    assert keyf[0] == 190 and keyf[1] == 1                    # 2 frames left: one frame


def test_fit_clip(comfy):
    render, _ = comfy
    assert render.fit_clip(0, 100, 124) == (0, 0, 90)
    assert render.fit_clip(120, 100, 124) == (120, 0, 1)
    assert render.fit_clip(100, 100, 124) == (100, 0, 22)
    assert render.fit_clip(88, 100, 124, "last_frame") == (16, 27, 73)
    assert render.fit_clip(2, 100, 124, "last_frame") == (2, 99, 1)
    assert render.fit_clip(-1, 3, 124) == (123, 0, 1)
    with pytest.raises(ValueError):
        render.fit_clip(124, 100, 124)


def test_reference_media_are_cut_before_decoding(comfy, tmp_path):
    from reelwright import media, merge
    ff = merge.ffmpeg_bin()
    path = str(tmp_path / "long.mp4")
    subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=64x32:r=30:d=40", "-f", "lavfi",
                    "-i", "sine=d=40", "-shortest", "-pix_fmt", "yuv420p", path], check=True)
    frames, audio = media.load_video(path, max_seconds=15, max_frames=360)
    assert frames.shape[0] == 360 and audio["waveform"].shape[-1] / audio["sample_rate"] == pytest.approx(15, abs=0.05)
    tail, taudio = media.load_video(path, last_frames=124)
    assert tail.shape[0] == 124 and taudio["waveform"].shape[-1] / taudio["sample_rate"] == pytest.approx(124 / 24, abs=0.05)
    assert media.frame_positions(10, 24, 4) == [0, 1, 2, 3]
    assert media.frame_positions(100, 30, 5) == [0, 1, 2, 3, 5]       # floor(i * 30 / 24)
    assert media.frame_positions(3, 24, 5) == [0, 1, 2, 2, 2]
    wav = str(tmp_path / "voice.wav")
    subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=d=20", wav], check=True)
    a = media.load_audio(wav, max_seconds=15)
    assert a["waveform"].shape[-1] / a["sample_rate"] == pytest.approx(15, abs=0.01)


def test_vision_clip_and_frames(comfy, tmp_path):
    """Describe a video anchor (v0.19.5): its From-To part as a small silent H.264 clip, and frames spread over it."""
    import io

    from PIL import Image, ImageStat

    from reelwright import media, merge
    ff = merge.ffmpeg_bin()
    path = str(tmp_path / "anchor.mp4")
    subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "nullsrc=s=1280x720:r=24:d=10,geq=lum='T*20':cb=128:cr=128",
                    "-f", "lavfi", "-i", "sine=d=10", "-shortest", "-pix_fmt", "yuv420p", path], check=True)
    assert media.clip_range(path, 2.0, 5.5) == (2.0, 5.5)
    assert media.clip_range(path, 3.0, None)[1] == pytest.approx(10.0, abs=0.05)
    assert media.clip_range(path, 4.0, 1.0)[1] == pytest.approx(10.0, abs=0.05)  # a To before the From: to the end
    data, mime = media.vision_clip(path, 2.0, 5.5)
    assert mime == "video/mp4" and len(data) < 500_000
    out = str(tmp_path / "sent.mp4")
    with open(out, "wb") as f:
        f.write(data)
    info = merge.probe(out)
    assert info["duration"] == pytest.approx(3.5, abs=0.15) and not info["has_audio"]
    assert (info["width"], info["height"]) == (640, 360)
    frames = media.vision_frames(path, 2.0, 5.5, 4)
    lum = [ImageStat.Stat(Image.open(io.BytesIO(d)).convert("L")).mean[0] for d, m in frames]
    assert len(frames) == 4 and all(m == "image/jpeg" for _, m in frames)
    # luma 20 per second: at 2.4, 3.3, 4.2 and 5.1 s (about 38, 58, 79, 99 in RGB), never the whole video's 1.25 s
    assert lum == sorted(lum) and 30 < lum[0] < 46 and 90 < lum[-1] < 108


def test_reference_clips_start_at_their_from(comfy, tmp_path):
    """media.load_video / load_audio read a reference's clip from its From."""
    from reelwright import media, merge
    ff = merge.ffmpeg_bin()
    path = str(tmp_path / "ramp.mp4")
    subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "nullsrc=s=32x16:r=24:d=10,geq=lum='T*20':cb=128:cr=128",
                    "-f", "lavfi", "-i", "aevalsrc='t/10':d=10:s=16000", "-shortest", "-pix_fmt", "yuv420p", path], check=True)
    whole, _ = media.load_video(path, max_seconds=10)
    frames, audio = media.load_video(path, max_seconds=3.0, max_frames=360, start=4.0)
    assert frames.shape[0] == 72
    assert abs(float(frames[0].float().mean()) - float(whole[96].float().mean())) < 0.03
    assert abs(float(frames[-1].float().mean()) - float(whole[96 + 71].float().mean())) < 0.03
    assert audio["waveform"].shape[-1] / audio["sample_rate"] == pytest.approx(3.0, abs=0.05)
    assert float(audio["waveform"][..., :50].mean()) == pytest.approx(0.4, abs=0.03)
    wav = str(tmp_path / "ramp.wav")
    subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "aevalsrc='t/10':d=10:s=16000", wav], check=True)
    a = media.load_audio(wav, max_seconds=2.0, start=5.0)
    assert a["waveform"].shape[-1] / a["sample_rate"] == pytest.approx(2.0, abs=0.01)
    assert float(a["waveform"][..., :50].mean()) == pytest.approx(0.5, abs=0.01)


def test_reference_clips_reach_the_encoder(stubs, harbor, store, roots):
    """The same video twice, as two clips (one with its sound), and an audio clip."""
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    s = harbor["scenes"][1]
    s["refs"][1].update({"in": 0.5, "out": None})
    s["refs"].append({"id": "r_dolly2", "asset": "a_dolly", "role": "reference", "in": 1.0, "out": 3.0, "soundtrack": True,
                      "time": 0.0, "retention": "", "keep": [], "cast": ""})
    harbor["assets"].append({"id": "a_amb", "kind": "audio", "code": "A9", "name": "rain",
                             "file": "reelwright/harbor_lights/rain.wav", "duration": 4.2})
    s["refs"].append({"id": "r_amb", "asset": "a_amb", "role": "reference", "in": 1.0, "out": 2.5, "time": 0.0,
                      "retention": "", "keep": [], "cast": "", "soundtrack": False})
    _real_assets(harbor, roots)
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_one", "s_long"]}).run()
    enc = next(e for e in calls["encode"] if len(e["video_frames"]) >= 2)
    # 1.0-3.0 s = 48 frames; 0.5 s to the end of the 4.2 s file = 3.7 s, as many frames as the file has left (88-89)
    assert 48 in enc["video_frames"] and any(x in enc["video_frames"] for x in (88, 89)), enc["video_frames"]
    assert 2.0 in [round(x, 1) for x in enc["video_audio_secs"].values()]
    assert 1.5 in [round(x, 2) for x in enc["audio_secs"]]


def test_audio_references_are_trimmed_to_15_seconds(stubs, harbor, store, roots):
    render, calls, events = stubs
    from reelwright import merge
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    subprocess.run([merge.ffmpeg_bin(), "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=d=20", "-f", "wav",
                    os.path.join(roots.input, "reelwright/harbor_lights/voice.wav")], check=True)
    render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    secs = [x for e in calls["encode"] for x in e["audio_secs"]]
    assert secs and max(secs) <= 15.0 + 1e-6


def test_unfinished_take_folders_are_removed(stubs, harbor, store, roots):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    stale = store.take_dir("s_short", "v7")
    os.makedirs(os.path.join(stale, "passes"))
    open(os.path.join(stale, "passes", "p1.mp4"), "wb").close()
    kept = store.take_dir("s_short", "v8")
    os.makedirs(kept)
    with open(os.path.join(kept, "meta.json"), "w") as f:
        f.write("{}")
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_short"]}).run()
    assert not os.path.exists(stale) and os.path.isdir(kept)
    take = store.starred_take("s_short")
    assert not os.path.exists(os.path.join(store.take_dir("s_short", take["id"]), "passes"))


def test_take_meta_records_upstream_prompts_and_keys(stubs, harbor, store, roots):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    take = store.starred_take("s_long")
    with open(os.path.join(store.take_dir("s_long", take["id"]), "meta.json")) as f:
        meta = json.load(f)
    for t in (take, meta):
        assert t["upstream"] == {"scene_id": "s_one", "take_id": "v1"}
        assert len(t["prompts"]) == len(t["pass_keys"]) == 3 and t["render_seconds"] >= 0
        assert "face_score" in t and t["sampled_frames"] > 0
    assert store.starred_take("s_one")["upstream"] is None
    idx = store.read_index("s_one")
    assert idx["auto_star"] == "v1"


def test_takes_record_their_render_times(stubs, harbor, store, roots, monkeypatch):
    """Render tab: each take keeps its time per pass (split by phase), the encode-first time it used and the time
    after its passes; a pass read from the pass cache is marked."""
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    ref2v = render.MiniMaxH3ReferenceToVideo.execute

    def slow_ref2v(**kw):
        time.sleep(0.1)
        return ref2v(**kw)

    def slow_sample(model, positive, latent, seed, settings, on_step):
        calls["sample"].append(seed)
        time.sleep(0.15)
        on_step(settings["steps"], settings["steps"])
        return latent

    monkeypatch.setattr(render.MiniMaxH3ReferenceToVideo, "execute", staticmethod(slow_ref2v))
    monkeypatch.setattr(render, "_sample", slow_sample)
    render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    take = store.starred_take("s_long")
    with open(os.path.join(store.take_dir("s_long", take["id"]), "meta.json")) as f:
        meta = json.load(f)
    for t in (take, meta):
        times = t["pass_times"]
        assert [x["pass"] for x in times] == [1, 2, 3] and not any(x["cached"] for x in times)
        for x in times:
            assert x["phases"]["encode"] >= 0.1 and x["phases"]["sample"] >= 0.15
            assert set(x["phases"]) <= {"encode", "guides", "sample", "upscale", "refine", "decode", "save"}
            assert x["seconds"] >= sum(x["phases"].values()) - 0.2
        whole = t["render_seconds"] + t.get("encode_seconds", 0)
        assert whole == pytest.approx(sum(x["seconds"] for x in times) + t["finish_seconds"], abs=0.3)
    assert take["render_seconds"] >= 0.45
    # a pass retake reads pass 1 from the pass cache: no phases, marked as cached
    render.Renderer(harbor, store, {}, {"action": "pass_retake", "scene_id": "s_long", "pass": 2}).run()
    times = store.starred_take("s_long")["pass_times"]
    assert times[0]["cached"] and "phases" not in times[0]
    assert not times[1]["cached"] and times[1]["phases"]["sample"] >= 0.15


def test_node_output_is_a_full_cut_never_a_draft(stubs, harbor, roots, monkeypatch):
    render, calls, events = stubs
    import shutil

    from reelwright import assemble as asm
    from reelwright.node import Reelwright, full_cuts
    from reelwright.storage import ProjectStore
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    out = Reelwright.execute(json.dumps(harbor), json.dumps({"action": "pending"}))
    full = out.result[0].get_duration()
    store = ProjectStore(roots, harbor["slug"])
    cut = full_cuts(store)[0]
    shot = store.output_path(store.starred_take("s_short")["files"]["video"])
    for name in ("harbor_lights_cut_v90_draft.mp4", "harbor_lights_cut_v91_range.mp4", "harbor_lights_cut_v92.partial.mp4"):
        shutil.copy(shot, os.path.join(store.cuts_dir(), name))
    assert full_cuts(store) == [cut]
    out = Reelwright.execute(json.dumps(harbor), json.dumps({"action": "pending", "token": 2}))  # nothing to render
    assert out.result[0].get_duration() == pytest.approx(full, abs=0.05)

    def boom(*a, **k):
        raise ValueError("not a MergeError")
    monkeypatch.setattr(asm, "merge_project", boom)
    out = Reelwright.execute(json.dumps(harbor), json.dumps({"action": "take", "scenes": ["s_short"]}))
    assert out.result[0].get_duration() == pytest.approx(2.5, abs=0.1)  # the new take: the merge failed


def test_extension_loads_without_h3_nodes(roots):
    """render.py must import without comfy_extras.nodes_minimax_h3; a render is then refused up front."""
    code = r'''
import importlib.abc, json, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name == "comfy_extras.nodes_minimax_h3":
            raise ImportError("no H3 here")
sys.meta_path.insert(0, Block())
from comfy.cli_args import args
args.cpu = True
import folder_paths
folder_paths.set_output_directory(sys.argv[1]); folder_paths.set_input_directory(sys.argv[2])
import server
class S:
    def send_sync(self, e, d, sid=None):
        print("EVENT", json.dumps([e, d]))
server.PromptServer.instance = S()
from reelwright import render
from reelwright.model import default_project
from reelwright.storage import ProjectStore, Roots
print("H3", render.h3_available())
p = default_project("No H3")
store = ProjectStore(Roots(sys.argv[1], sys.argv[2], sys.argv[1]), p["slug"])
try:
    render.Renderer(p, store, {}, {"action": "pending"}).run()
except RuntimeError as e:
    print("REFUSED", "MiniMax H3" in str(e))
'''
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-c", code, roots.output, roots.input], capture_output=True, text=True,
                       cwd=root, env=dict(os.environ, PYTHONPATH=os.pathsep.join([COMFY, root])), timeout=300)
    assert "H3 False" in r.stdout, r.stderr[-2000:]
    assert "REFUSED True" in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]
    assert '"phase": "rejected"' in r.stdout


def test_pass_files_of_older_takes_are_reused(stubs, harbor, store, roots):
    """A take from before v0.6.0 kept its passes in takes/<id>/passes/pN.mp4; a keep-window move uses them."""
    render, calls, events = stubs
    import shutil
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_short"]}).run()
    # turn the take into one made by v0.5.1
    idx = store.read_index("s_short")
    t = idx["takes"][0]
    tdir = store.take_dir("s_short", t["id"])
    os.makedirs(os.path.join(tdir, "passes"))
    shutil.move(store.output_path(t["files"]["passes"][0]), os.path.join(tdir, "passes", "p1.mp4"))
    shutil.rmtree(os.path.join(store.scene_dir("s_short"), "passes"))
    t["files"]["passes"] = [store.rel_output(os.path.join(tdir, "passes", "p1.mp4"))]
    for k in ("pass_keys", "upstream", "offsets"):
        t.pop(k)
    store.write_index("s_short", idx)
    calls["sample"].clear()
    harbor["scenes"][2]["trim"]["in"] = 0.25
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_short"]}).run()
    assert calls["sample"] == []
    take = store.starred_take("s_short")
    assert take["cached_passes"] == 1 and os.path.isfile(store.output_path(take["files"]["passes"][0]))


def test_node_refuses_a_folder_of_another_project(stubs, harbor, roots):
    render, calls, events = stubs
    from reelwright.node import Reelwright
    from reelwright.storage import ProjectStore, write_json
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    store = ProjectStore(roots, harbor["slug"])
    os.makedirs(store.dir, exist_ok=True)
    write_json(os.path.join(store.dir, "project.json"), dict(harbor, project_id="p_other", name="Other film"))
    harbor["project_id"] = "p_mine"
    with pytest.raises(RuntimeError, match="holds another project"):
        Reelwright.execute(json.dumps(harbor), json.dumps({"action": "pending"}))
    assert [d["phase"] for d in _run_events(events)] == ["rejected"] and calls["sample"] == []


def test_auto_merge_events_carry_a_job(stubs, harbor, roots):
    render, calls, events = stubs
    from reelwright.node import Reelwright
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    Reelwright.execute(json.dumps(harbor), json.dumps({"action": "pending"}))
    merges = [d for e, d in events if e == "reelwright.merge"]
    assert merges[0]["phase"] == "start" and merges[-1]["phase"] == "end" and merges[-1]["files"]["video"]
    assert len({d["job"] for d in merges}) == 1 and merges[0]["job"].startswith("merge-")


def test_error_upstream_does_not_keep_the_next_scene_stale(stubs, harbor, store, roots):
    """An upstream scene with a lint error and an undone edit (an older take matches, a newer one is starred): the
    continuing scene is keyed against the starred take, the one the render uses, so one run makes it cached."""
    render, calls, events = stubs
    from reelwright.analysis import analyze
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    one = harbor["scenes"][0]
    render.Renderer(harbor, store, {}, {"action": "pending"}).run()            # s_one v1, s_long v1
    one["shots"][0]["text"] = "edited"
    render.Renderer(harbor, store, {}, {"action": "pending"}).run()            # s_one v2 (starred), s_long v2
    one["shots"][0]["text"] = "boats rock in the harbor"                       # undo: s_one v1 matches again
    one["dialogue"] = [{"id": "d_x", "speaker": "", "t": 30.0, "text": "too late"}]  # lint error
    harbor["scenes"][1]["shots"][0]["text"] = "Mara leaves the pier, slowly"    # s_long needs a new take
    r = analyze(harbor, store)["scenes"]
    assert r["s_one"]["status"] == "error" and r["s_one"]["match"] == "v1" and r["s_one"]["starred"] == "v2"
    assert r["s_long"]["status"] == "stale" and r["s_long"]["upstream_take"] == "v2"
    runs = [render.Renderer(harbor, store, {}, {"action": "pending"}).run() for _ in range(3)]
    assert runs == [["s_long"], [], []]
    assert store.starred_take("s_long")["upstream"]["take_id"] == "v2"
    assert analyze(harbor, store)["scenes"]["s_long"]["status"] == "cached"


def test_shortened_error_upstream_does_not_rerender_the_next_scene(stubs, harbor, store, roots):
    """The scene before is shortened so one of its lines falls past its end (a lint error and a new key). It is not
    rendered, and the scene that continues from its starred take stays cached."""
    render, calls, events = stubs
    from reelwright.analysis import analyze
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    harbor["scenes"][0]["dialogue"] = [{"id": "d_a", "speaker": "", "t": 6.0, "text": "the gulls"}]
    render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    harbor["scenes"][0]["duration"] = 5.0
    r = analyze(harbor, store)["scenes"]
    assert r["s_one"]["status"] == "error" and r["s_long"]["status"] == "cached"
    calls["sample"].clear()
    runs = [render.Renderer(harbor, store, {}, {"action": "pending"}).run() for _ in range(2)]
    assert runs == [[], []] and calls["sample"] == []


def test_error_upstream_reuse_keeps_the_next_scenes_star(stubs, harbor, store, roots):
    """reuse() must not star a take of the continuing scene that was rendered from another upstream take than the
    starred one of an error scene (which no run re-stars)."""
    render, calls, events = stubs
    from reelwright.analysis import analyze
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    one = harbor["scenes"][0]
    render.Renderer(harbor, store, {}, {"action": "pending"}).run()            # s_long v1 from s_one v1
    one["shots"][0]["text"] = "edited"
    render.Renderer(harbor, store, {}, {"action": "pending"}).run()            # s_long v2 from s_one v2
    one["shots"][0]["text"] = "boats rock in the harbor"                       # undo: s_one v1 matches again
    one["dialogue"] = [{"id": "d_x", "speaker": "", "t": 30.0, "text": "too late"}]  # lint error
    r = analyze(harbor, store)["scenes"]
    assert r["s_one"]["status"] == "error" and r["s_one"]["starred"] == "v2"
    assert r["s_long"]["status"] == "cached" and r["s_long"]["match"] == "v2" and r["s_long"]["upstream_take"] == "v2"
    events.clear()
    render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_short"]}).run()
    assert _run_events(events, "start")[0]["reused"] == []
    assert store.read_index("s_one")["starred"] == "v2" and store.read_index("s_long")["starred"] == "v2"
    assert store.starred_take("s_long")["upstream"]["take_id"] == "v2"


def _short_upstream(render, harbor, store, roots):
    """s_e continues s_short with a 73-frame tail; s_short's hand-picked take v1 is 2.5 s (60 frames) long."""
    from reelwright.model import normalize_project
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    harbor["scenes"].append({"id": "s_e", "title": "E", "duration": 6.0, "start": {"mode": "tail", "overlap_frames": 73}})
    p = normalize_project(harbor)
    render.Renderer(p, store, {}, {"action": "selected", "scenes": ["s_short"]}).run()   # v1: 60 frames
    p["scenes"][2]["duration"] = 6.0
    render.Renderer(p, store, {}, {"action": "selected", "scenes": ["s_short"]}).run()   # v2: 144 frames
    store.star("s_short", "v1")                                                          # the user prefers v1
    return p


def test_tail_longer_than_the_upstream_take_is_refused(stubs, harbor, store, roots):
    """The tail overlap is planned from the current length of the scene before, but cut from the take it continues
    from: a shorter take is a warning in the plan and refused in pre-flight (it used to send fewer guide frames than
    the cut trims, about 13 frames off at the seam)."""
    render, calls, events = stubs
    from reelwright.analysis import analyze
    p = _short_upstream(render, harbor, store, roots)
    r = analyze(p, store)
    s_e = r["scenes"]["s_e"]
    assert s_e["plan"]["passes"][0]["overlap_frames"] == 73 and s_e["upstream_take"] == "v1"
    assert s_e["status"] == "missing"  # a warning, not a lint error
    warn = [x for x in s_e["issues"] if x.get("code") == "short_upstream_tail"]
    assert len(warn) == 1 and warn[0]["level"] == "warn" and "only 60 frames" in warn[0]["message"]
    assert "at most 56 frames" in warn[0]["message"] and warn[0] in r["issues"]
    events.clear()
    calls["guides"].clear()
    with pytest.raises(RuntimeError, match="only 60 frames") as e:
        render.Renderer(p, store, {}, {"action": "selected", "scenes": ["s_e"]}).run()
    assert "Render 03 Hand on the door again" in str(e.value)
    assert [d["phase"] for d in _run_events(events)] == ["rejected"] and calls["guides"] == []
    with pytest.raises(RuntimeError, match="only 60 frames"):  # "Render pending" picks s_e (missing) and refuses
        render.Renderer(p, store, {}, {"action": "pending"}).run()
    # the render itself never sends a shorter guide
    rr = render.Renderer(p, store, {}, {"action": "selected", "scenes": ["s_e"]})
    with pytest.raises(RuntimeError, match="has only 60 frames"):
        rr._upstream_tail(store.starred_take("s_short"), 73)
    # rendering the scene before in the same run gives a take of the current length: no refusal, a full guide
    render.Renderer(p, store, {}, {"action": "selected", "scenes": ["s_short", "s_e"]}).run()
    assert calls["guides"][0]["frames"] == 73 and store.starred_take("s_e")["upstream"]["take_id"] == "v3"
    assert not [x for x in analyze(p, store)["scenes"]["s_e"]["issues"] if x.get("code") == "short_upstream_tail"]


def test_preflight_checks_the_take_reuse_will_star(stubs, harbor, store, roots):
    """Pre-flight runs before reuse(): it checks the take the scene before provides (the one reuse() stars), not the
    starred take reuse() is about to replace."""
    render, calls, events = stubs
    from reelwright.analysis import analyze
    p = _short_upstream(render, harbor, store, roots)
    idx = store.read_index("s_short")
    idx["auto_star"] = "v1"  # v1 starred by a render (an undone edit), so reuse() goes back to v2 (current length)
    store.write_index("s_short", idx)
    r = analyze(p, store)["scenes"]
    assert r["s_short"]["match"] == "v2" and r["s_e"]["upstream_take"] == "v2"
    assert not [x for x in r["s_e"]["issues"] if x.get("code") == "short_upstream_tail"]
    calls["guides"].clear()
    assert render.Renderer(p, store, {}, {"action": "selected", "scenes": ["s_e"]}).run() == ["s_e"]
    assert store.read_index("s_short")["starred"] == "v2" and calls["guides"][0]["frames"] == 73


def _face_drift(render, harbor, monkeypatch):
    harbor["global"]["continuity"].update(face_check=True, on_drift="retake", face_threshold=0.8)
    monkeypatch.setattr(render.continuity, "available", lambda: True)
    monkeypatch.setattr(render.continuity, "check_scene", lambda *a, **k: {"c_mara": 0.5})  # drifted -> retake


def test_failed_drift_retake_keeps_the_scene(stubs, harbor, store, roots, monkeypatch):
    """A drift retake that fails after the first take was made and starred is a warning: the scene counts as
    rendered and the scenes that continue from it render."""
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    _face_drift(render, harbor, monkeypatch)
    real = render._sample
    n = {"s_one": 0}

    def sample(model, positive, latent, seed, settings, on_step):
        if latent["frames"] == 192:          # s_one's single pass
            n["s_one"] += 1
            if n["s_one"] == 2:              # the drift retake
                raise RuntimeError("CUDA out of memory (retake)")
        return real(model, positive, latent, seed, settings, on_step)
    monkeypatch.setattr(render, "_sample", sample)
    done = render.Renderer(harbor, store, {}, {"action": "pending"}).run()   # does not raise
    assert done[:2] == ["s_one", "s_long"]
    end = _run_events(events, "end")[0]
    assert end["failed"] == [] and end["skipped"] == [] and end["rendered"] == done
    assert len(end["warnings"]) == 1 and end["warnings"][0]["scene_id"] == "s_one"
    assert "drift retake failed" in end["warnings"][0]["message"] and "out of memory" in end["warnings"][0]["message"]
    assert store.read_index("s_one")["starred"] == "v1" and [t["id"] for t in store.read_index("s_one")["takes"]] == ["v1"]
    assert store.starred_take("s_long")["upstream"]["take_id"] == "v1"
    warned = [d for e, d in events if e == "reelwright.progress" and d.get("warning")]
    assert len(warned) == 1 and warned[0]["scene_id"] == "s_one" and warned[0]["phase"] == "done"


def test_failed_variant_is_a_warning(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    real = render._sample

    def sample(model, positive, latent, seed, settings, on_step):
        if len(calls["sample"]) == 1 and not calls.get("failed"):   # the second variant
            calls["failed"] = True
            raise RuntimeError("CUDA out of memory (variant)")
        return real(model, positive, latent, seed, settings, on_step)
    monkeypatch.setattr(render, "_sample", sample)
    assert render.Renderer(harbor, store, {}, {"action": "variants", "scene_ids": ["s_short"], "n": 3}).run() == ["s_short"]
    idx = store.read_index("s_short")
    assert len(idx["takes"]) == 2 and idx["starred"] == idx["takes"][0]["id"]
    end = _run_events(events, "end")[0]
    assert end["failed"] == [] and [w["scene_id"] for w in end["warnings"]] == ["s_short"]
    assert end["warnings"][0]["message"].startswith("variant 2 of 3 failed")


def test_stop_during_a_drift_retake_still_stops_the_run(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    import comfy.model_management as mm
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    _face_drift(render, harbor, monkeypatch)
    _stop_on(render, monkeypatch, calls, 2)          # the drift retake of s_one
    with pytest.raises(mm.InterruptProcessingException):
        render.Renderer(harbor, store, {}, {"action": "pending"}).run()
    end = _run_events(events, "end")[0]
    assert end["interrupted"] is True and end["warnings"] == [] and "s_long" not in end["rendered"]
    assert len(calls["sample"]) == 1


def test_node_output_survives_a_missing_last_frame(stubs, harbor, roots):
    """Review 2: a missing or unreadable last.png (or a take entry without files.last, as one rebuilt from meta.json
    may be) failed the node after the scenes were rendered."""
    render, calls, events = stubs
    import torch

    from reelwright.node import Reelwright
    from reelwright.storage import ProjectStore
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    Reelwright.execute(json.dumps(harbor), json.dumps({"action": "pending"}))
    store = ProjectStore(roots, harbor["slug"])
    os.remove(store.output_path(store.starred_take("s_short")["files"]["last"]))
    out = Reelwright.execute(json.dumps(harbor), json.dumps({"action": "pending", "token": 2}))
    assert torch.equal(out.result[1], torch.zeros(1, 64, 64, 3)) and out.result[0].get_duration() > 40
    idx = store.read_index("s_short")
    idx["takes"][-1]["files"].pop("last")
    idx["takes"][-1]["files"]["video"] = "../../outside.mp4"
    store.write_index("s_short", idx)
    out = Reelwright.execute(json.dumps(harbor), json.dumps({"action": "pending", "token": 3}))
    assert out.result[1].shape == (1, 64, 64, 3)


def test_preflight_names_each_missing_asset_and_survives_odd_take_paths(stubs, harbor, store, roots):
    """Review 4a / 4b: a missing asset whose code is part of another one's ("P1" in lint's line about "P10") was left
    out of pre-flight, and a take file path outside the output folder raised ValueError out of pre-flight."""
    render, calls, events = stubs
    from reelwright.model import normalize_project
    harbor["assets"][3]["code"] = "P10"                      # the letter, a keyframe of s_long
    p = normalize_project(harbor)
    assert [a["code"] for a in p["assets"] if a["id"] in ("a_front", "a_letter")] == ["P1", "P10"]
    os.remove(os.path.join(roots.input, "reelwright/harbor_lights/letter.png"))   # lint reports P10
    store.add_take("s_one", {"id": "v1", "files": {"video": "../../../etc/passwd", "last": "../../../etc/passwd"}})
    r = render.Renderer(p, store, {}, {"action": "selected", "scenes": ["s_long"]})
    os.remove(os.path.join(roots.input, "reelwright/harbor_lights/front.png"))    # gone after the analysis
    with pytest.raises(RuntimeError) as e:
        r.preflight(["s_long"])
    msg = str(e.value)
    assert "P10 (letter) file is missing" in msg
    assert "P1 (Mara front) is missing" in msg
    assert "whose starred take v1 is missing its files" in msg
    assert render._names_code("02 x: P10 (letter) file is missing", "P10")
    assert not render._names_code("02 x: P10 (letter) file is missing", "P1")


def test_video_guide_length_comes_from_its_video_stream(stubs, harbor, store, roots, tmp_path):
    """Review 4c: pre-flight sized a video guide from the file's length (an audio track longer than the picture
    counted) while the render uses the decoded frames; a file without a picture passed pre-flight and failed mid-run."""
    render, calls, events = stubs
    from reelwright import media, merge
    ff = merge.ffmpeg_bin()
    harbor["global"]["output"].update(width=64, height=32)
    _real_assets(harbor, roots)
    long_audio = str(tmp_path / "long_audio.mp4")
    subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=64x32:r=30:d=4", "-f", "lavfi",
                    "-i", "sine=d=10", "-pix_fmt", "yuv420p", long_audio], check=True)
    info = merge.probe(long_audio)
    assert info["duration"] == pytest.approx(10, abs=0.05) and info["video_frames"] == 96
    r = render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_one"]})
    frames, _ = media.load_video(long_audio, max_seconds=15, max_frames=render.REF_MAX_FRAMES)
    assert r._clip_frames(long_audio) == frames.shape[0] == 96
    webm = str(tmp_path / "clip.webm")  # no frame count or stream duration, only the Matroska DURATION tag
    subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=64x32:r=24:d=3", "-f", "lavfi",
                    "-i", "sine=d=6", "-c:v", "libvpx", "-c:a", "libopus", webm], check=True)
    assert r._clip_frames(webm) == 72
    # a "video" with no picture: refused before any GPU work
    dolly = os.path.join(roots.input, "reelwright/harbor_lights/dolly.mp4")
    subprocess.run([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=d=4", "-f", "mp4", dolly], check=True)
    harbor["scenes"][0]["refs"] = [{"id": "r_k", "asset": "a_dolly", "role": "keyframe", "time": 1.0}]
    with pytest.raises(RuntimeError, match="the video has no frames"):
        render.Renderer(harbor, store, {}, {"action": "selected", "scenes": ["s_one"]}).run()
    assert calls["sample"] == [] and calls["guides"] == []


def test_a_video_without_decodable_frames_says_so(comfy, tmp_path):
    """Review 10: zero decodable frames made load_video raise IndexError ("index 0 is out of bounds")."""
    from reelwright import media, merge
    src = str(tmp_path / "src.mp4")
    subprocess.run([merge.ffmpeg_bin(), "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=64x32:r=24:d=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", src], check=True)
    data = bytearray(open(src, "rb").read())
    i = data.find(b"mdat")
    data[i + 4:i - 4 + int.from_bytes(data[i - 4:i], "big")] = bytes(int.from_bytes(data[i - 4:i], "big") - 8)
    broken = str(tmp_path / "broken.mp4")
    with open(broken, "wb") as f:
        f.write(bytes(data))
    with pytest.raises(ValueError, match="no video frames could be decoded from broken.mp4"):
        media.load_video(broken, max_seconds=15)


# ---- the continuation as a named reference ------------------------------------------------------------------------

def _continuing_harbor(harbor, roots, on=True):
    """s_one (fresh) -> s_lf (last-frame start, Mara's sheet) -> s_long (tail start, dolly video with its sound,
    three passes joined by overlap seams)."""
    from reelwright.model import normalize_project
    harbor["global"]["output"].update(width=64, height=32)
    harbor["global"]["long"]["seam_mode"] = "overlap"
    harbor["global"]["continuity"]["name_continuation"] = on
    _real_assets(harbor, roots)
    lf = {"id": "s_lf", "title": "Pier", "duration": 6.0, "start": {"mode": "last_frame"}, "cast": [{"id": "c_mara"}],
          "shots": [{"id": "h_lf", "t": 0, "camera": "Medium", "text": "@Mara turns to the sea"}]}
    harbor["scenes"] = [harbor["scenes"][0], lf, harbor["scenes"][1]]
    return normalize_project(harbor)


def _encodes_by_pass(calls, analysis):
    """{(scene id, pass index): encode call}, matched by prompt."""
    want = {b["prompt"]: (sid, n + 1) for sid, sr in analysis["scenes"].items() for n, b in enumerate(sr["builds"])}
    return {want[e["prompt"]]: e for e in calls["encode"]}


def test_continuation_reaches_the_node(stubs, harbor, store, roots, monkeypatch):
    """The last frame of the scene before is ref_image_0, the tail clip (124 frames and its sound) ref_video_0 and,
    after an overlap seam, the last 124 frames of the pass before ref_video_0; the guides are as before."""
    render, calls, events = stubs
    from reelwright import media
    from reelwright.analysis import analyze
    p = _continuing_harbor(harbor, roots)
    first_sample = []
    real_sample = render._sample

    def sample(*a, **k):
        first_sample.append(len(calls["encode"]))
        return real_sample(*a, **k)
    monkeypatch.setattr(render, "_sample", sample)
    assert render.Renderer(p, store, {}, {"action": "pending"}).run() == ["s_one", "s_lf", "s_long"]
    r = analyze(p, store)
    assert [x["seam_before"] for x in r["scenes"]["s_long"]["plan"]["passes"]] == ["none", "overlap", "overlap"]
    assert first_sample[0] == 1  # encode-first did s_one only: the others need footage made in this run
    enc = _encodes_by_pass(calls, r)
    assert len(enc) == len(calls["encode"]) == 5
    one_last = media.load_image(store.output_path(store.starred_take("s_one")["files"]["last"]))
    lf_last = media.load_image(store.output_path(store.starred_take("s_lf")["files"]["last"]))
    e = enc[("s_lf", 1)]
    assert e["image_order"] == ["ref_image_0", "ref_image_1"] and e["video_order"] == []
    assert e["image_shapes"][0] == (1, 32, 64, 3) and e["image_means"][0] == pytest.approx(float(one_last.mean()), abs=0.01)
    assert e["prompt"].count("<Picture 1> is the first frame of [Shot 1], the last frame of the scene before.") == 1
    e = enc[("s_long", 1)]
    assert e["video_order"] == ["ref_video_0", "ref_video_1"] and e["video_frames"][0] == 124
    assert e["video_last_means"][0] == pytest.approx(float(lf_last.mean()), abs=0.02)  # it ends on that last frame
    assert e["video_audio_secs"]["ref_video_audio_0"] == pytest.approx(124 / 24, abs=0.06)
    assert e["video_audio_secs"]["ref_video_audio_1"] == pytest.approx(4.2, abs=0.06)  # the dolly's own sound
    for n in (2, 3):
        e = enc[("s_long", n)]
        assert e["video_order"][0] == "ref_video_0" and e["video_frames"][0] == 124
        assert e["video_last_means"][0] == pytest.approx(1.0, abs=0.01)  # the stub's passes end on white
        assert e["video_audio_secs"]["ref_video_audio_0"] == pytest.approx(124 / 24, abs=0.01)
        assert "<Video 1> is the end of the previous part of this scene" in e["prompt"]
    # the latent anchors are unchanged: frame 0 of s_lf, the 39-frame tail with sound, 39-frame overlaps
    assert [g for g in calls["guides"] if g["frame_idx"] == 0] == [
        {"frame_idx": 0, "frames": 1, "audio": False}, {"frame_idx": 0, "frames": 39, "audio": True},
        {"frame_idx": 0, "frames": 39, "audio": True}, {"frame_idx": 0, "frames": 39, "audio": True}]

    # the scene before is not rendered in this run: its take is there, so the pass is encoded first again
    calls["encode"].clear()
    first_sample.clear()
    p["scenes"][1]["shots"][0]["text"] = "@Mara turns to the sea and waves"
    assert render.Renderer(p, store, {}, {"action": "pending"}).run() == ["s_lf", "s_long"]
    assert first_sample[0] == 1
    e = _encodes_by_pass(calls, analyze(p, store))[("s_lf", 1)]
    assert e["image_means"][0] == pytest.approx(float(one_last.mean()), abs=0.01)


def test_continuation_switched_off_sends_what_v061_sent(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    from reelwright.analysis import analyze
    p = _continuing_harbor(harbor, roots, on=False)
    first_sample = []
    real_sample = render._sample

    def sample(*a, **k):
        first_sample.append(len(calls["encode"]))
        return real_sample(*a, **k)
    monkeypatch.setattr(render, "_sample", sample)
    assert render.Renderer(p, store, {}, {"action": "pending"}).run() == ["s_one", "s_lf", "s_long"]
    assert first_sample[0] == len(calls["encode"]) == 5  # encode-first: every pass before sampling
    enc = _encodes_by_pass(calls, analyze(p, store))
    assert enc[("s_lf", 1)]["image_order"] == ["ref_image_0"]
    assert enc[("s_long", 1)]["video_order"] == ["ref_video_0"] and enc[("s_long", 1)]["video_frames"][0] != 124
    assert enc[("s_long", 2)]["video_order"] == ["ref_video_0"]
    assert not any("<Video 1> is the end" in e["prompt"] or "the last frame of the scene before" in e["prompt"]
                   for e in calls["encode"])


# ---- long-scene continuity -----------------------------------------------------------------------------------------
# Global -> Long scenes: guide_vae, carry_audio, seam_video_ref, handoff, pass_cache, and the drift meter. Each test
# checks what reaches MiniMaxH3AddGuide and MiniMaxH3ReferenceToVideo for one setting. _continuing_harbor: s_one
# (fresh) -> s_lf (last-frame start) -> s_long (tail start, three passes joined by 39-frame overlap seams).

def _frame0_guides(calls):
    return [g for g in calls["guides"] if g["frame_idx"] == 0]


def test_defaults_send_what_v070_sent(stubs, harbor, store, roots):
    render, calls, events = stubs
    p = _continuing_harbor(harbor, roots)
    assert render.Renderer(p, store, {}, {"action": "pending"}).run() == ["s_one", "s_lf", "s_long"]
    video_vae = "vae:" + p["global"]["models"]["video_vae"]
    assert {e["vae"] for e in calls["encode"]} == {video_vae} and set(calls["guide_vaes"]) == {video_vae}
    assert _frame0_guides(calls) == [{"frame_idx": 0, "frames": 1, "audio": False}] + \
        [{"frame_idx": 0, "frames": 39, "audio": True}] * 3
    take = store.starred_take("s_long")
    assert take["long"] == {"guide_vae": "", "carry_audio": True, "seam_video_ref": True, "handoff": "pixels",
                            "pass_cache": "near_lossless"}
    from reelwright import media
    assert not any(media.is_rgb_video(store.output_path(f)) for f in take["files"]["passes"] + [take["files"]["tail"]])


def test_guide_vae_encodes_references_and_guides(stubs, harbor, store, roots):
    render, calls, events = stubs
    p = _continuing_harbor(harbor, roots)
    p["global"]["long"]["guide_vae"] = "h3_full.safetensors"
    assert render.Renderer(p, store, {}, {"action": "pending"}).run() == ["s_one", "s_lf", "s_long"]
    assert {e["vae"] for e in calls["encode"]} == {"vae:h3_full.safetensors"}
    assert set(calls["guide_vaes"]) == {"vae:h3_full.safetensors"}
    assert set(calls["decode_vaes"]) == {"vae:" + p["global"]["models"]["video_vae"]}  # the video VAE decodes
    assert store.starred_take("s_long")["long"]["guide_vae"] == "h3_full.safetensors"


def test_guide_vae_must_exist_and_be_an_h3_video_vae_with_an_encoder(comfy, harbor, store, monkeypatch):
    render, _ = comfy
    import comfy.ldm.minimax.vae as h3vae
    harbor["global"]["long"]["guide_vae"] = "nope.safetensors"
    r = render.Renderer(harbor, store, {}, {"action": "pending"})
    monkeypatch.setattr(render.folder_paths, "get_filename_list", lambda folder: [])
    assert "vae/nope.safetensors (the guide VAE)" in r.missing_models(["s_one"])
    with pytest.raises(RuntimeError, match="not a MiniMax H3 video VAE"):
        render.check_guide_vae(types.SimpleNamespace(first_stage_model=object()), "x.safetensors")
    with pytest.raises(RuntimeError, match="no encoder"):
        render.check_guide_vae(types.SimpleNamespace(
            first_stage_model=h3vae.MiniMaxH3VideoVAE(ch=32, encoder=False, decoder=False)), "dec.safetensors")
    render.check_guide_vae(types.SimpleNamespace(first_stage_model=h3vae.MiniMaxH3VideoVAE(ch=32, decoder=False)), "ok")


def test_carry_audio_off_anchors_the_picture_only_and_crossfades_the_sound(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    from reelwright import merge
    p = _continuing_harbor(harbor, roots)
    p["global"]["long"]["carry_audio"] = False
    joined = []
    real_join = render.merge.join

    def join(segs, *a, **k):
        joined.append(segs)
        return real_join(segs, *a, **k)
    monkeypatch.setattr(render.merge, "join", join)
    assert render.Renderer(p, store, {}, {"action": "pending"}).run() == ["s_one", "s_lf", "s_long"]
    # the tail of the scene before keeps its sound; the end of the pass before goes without
    assert _frame0_guides(calls) == [{"frame_idx": 0, "frames": 1, "audio": False},
                                     {"frame_idx": 0, "frames": 39, "audio": True},
                                     {"frame_idx": 0, "frames": 39, "audio": False},
                                     {"frame_idx": 0, "frames": 39, "audio": False}]
    segs = joined[-1]
    assert [s.get("audio_lead_frames") for s in segs] == [None, 39 - 12, 39 - 12]
    take = store.starred_take("s_long")
    assert merge.probe(store.output_path(take["files"]["video"]))["duration"] == pytest.approx(32.0, abs=0.1)


def test_seam_video_ref_off_anchors_pass_seams_without_video_1(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    from reelwright.analysis import analyze
    p = _continuing_harbor(harbor, roots)
    p["global"]["long"]["seam_video_ref"] = False
    first_sample = []
    real_sample = render._sample

    def sample(*a, **k):
        first_sample.append(len(calls["encode"]))
        return real_sample(*a, **k)
    monkeypatch.setattr(render, "_sample", sample)
    assert render.Renderer(p, store, {}, {"action": "pending"}).run() == ["s_one", "s_lf", "s_long"]
    enc = _encodes_by_pass(calls, analyze(p, store))
    assert enc[("s_long", 1)]["video_order"][0] == "ref_video_0" and enc[("s_long", 1)]["video_frames"][0] == 124
    for n in (2, 3):
        e = enc[("s_long", n)]
        assert 124 not in e["video_frames"] and "ref_video_audio_0" in e["video_audios"]  # the dolly only
        assert "<Video 1> is the end of the previous part" not in e["prompt"]
    # encode-first now covers the passes after the seams (nothing in them is made during the run): s_one and the
    # two later passes of s_long are encoded before sampling starts
    assert first_sample[0] == 3
    assert _frame0_guides(calls)[2:] == [{"frame_idx": 0, "frames": 39, "audio": True}] * 2  # still anchored


def _nested_latents(render, calls, monkeypatch):
    """Stubs that pass real H3-shaped AV latents (NestedTensor video [1, 24, T, h, w] + audio): the sampler writes
    latent index + 1000 * (seed % 1000) into every video latent, and records the conditioning it got."""
    import torch
    from comfy.nested_tensor import NestedTensor
    from comfy_extras.nodes_minimax_h3 import temporal_shape
    stub = render.MiniMaxH3ReferenceToVideo.execute

    def ref2v(**kw):
        positive, lat = stub(**kw).result
        _, lt, at = temporal_shape(kw["length"])
        lat = dict(lat, samples=NestedTensor((torch.zeros(1, 24, lt, kw["height"] // 16, kw["width"] // 16),
                                              torch.zeros(1, 32, 2, at))))
        return types.SimpleNamespace(result=(positive, lat))

    def sample(model, positive, latent, seed, settings, on_step):
        calls["sample"].append(seed)
        calls.setdefault("positives", []).append(positive)
        v, a = latent["samples"].tensors
        t = torch.arange(v.shape[2], dtype=torch.float32).view(1, 1, -1, 1, 1)
        on_step(settings["steps"], settings["steps"])
        return dict(latent, samples=NestedTensor((v * 0 + t + 1000.0 * (seed % 1000), a)))
    monkeypatch.setattr(render.MiniMaxH3ReferenceToVideo, "execute", staticmethod(ref2v))
    monkeypatch.setattr(render, "_sample", sample)


def _expected_slice(seed, t_prev, need=12):
    import torch
    return (torch.arange(t_prev - need, t_prev, dtype=torch.float32) + 1000.0 * (seed % 1000)).view(1, 1, -1, 1, 1)


def test_latent_handoff_guides_with_the_sampled_latents(stubs, harbor, store, roots, monkeypatch):
    """With handoff "latent", the guide after an overlap seam is the pass before's last 12 sampled latents (39 frames),
    To minimax_keyframes as MiniMaxH3AddGuide would add an encoded clip; MiniMaxH3AddGuide gets only the sound
    (no picture, so no VAE encode for that guide). A pass read back from the pass cache hands off the latents kept
    next to it; without them it falls back to the decoded frames."""
    render, calls, events = stubs
    import torch
    p = _continuing_harbor(harbor, roots)
    p["global"]["long"]["handoff"] = "latent"
    _nested_latents(render, calls, monkeypatch)
    assert render.Renderer(p, store, {}, {"action": "pending"}).run() == ["s_one", "s_lf", "s_long"]
    from reelwright.analysis import analyze
    plan = analyze(p, store)["scenes"]["s_long"]["plan"]
    t = [render.latent_count(x["gen_frames"]) for x in plan["passes"]]
    seeds = calls["sample"][2:5]  # s_one, s_lf, then the three passes of s_long
    for n in (1, 2):  # passes 2 and 3
        kfs = calls["positives"][2 + n][0][1].get("minimax_keyframes") or []
        assert len(kfs) == 1 and kfs[0]["resolved_frame_index"] == 0
        assert kfs[0]["latent"].shape == (1, 24, 12, 2, 4)
        assert torch.equal(kfs[0]["latent"], _expected_slice(seeds[n - 1], t[n - 1]).expand(1, 24, 12, 2, 4))
    # pass 1 continues the scene before: its tail clip goes through AddGuide as pixels; the seams send sound only
    assert _frame0_guides(calls) == [{"frame_idx": 0, "frames": 1, "audio": False},
                                     {"frame_idx": 0, "frames": 39, "audio": True},
                                     {"frame_idx": 0, "frames": 0, "audio": True},
                                     {"frame_idx": 0, "frames": 0, "audio": True}]
    take = store.starred_take("s_long")
    assert [(d["pass"], d.get("handoff")) for d in take["drift"]] == [(1, None), (2, "latent"), (3, "latent")]
    pdir = os.path.join(store.scene_dir("s_long"), "passes")
    kept = sorted(f for f in os.listdir(pdir) if f.endswith(".latent.safetensors"))
    assert [k.split(".")[0] for k in kept] == sorted(take["pass_keys"][:2])  # passes 1 and 2 keep theirs

    # a retake of pass 3: pass 2 comes from the pass cache and hands off the latents kept with it
    calls["positives"].clear()
    calls["guides"].clear()
    render.Renderer(p, store, {}, {"action": "pass_retake", "scene_id": "s_long", "pass": 3}).run()
    kf = calls["positives"][-1][0][1]["minimax_keyframes"][0]["latent"]
    assert torch.equal(kf, _expected_slice(seeds[1], t[1]).expand(1, 24, 12, 2, 4))
    assert _frame0_guides(calls) == [{"frame_idx": 0, "frames": 0, "audio": True}]

    # without the kept latents the pass falls back to the decoded frames (AddGuide encodes the 39 frames)
    for f in os.listdir(pdir):
        if f.endswith(".latent.safetensors"):
            os.remove(os.path.join(pdir, f))
    calls["positives"].clear()
    calls["guides"].clear()
    render.Renderer(p, store, {}, {"action": "pass_retake", "scene_id": "s_long", "pass": 3}).run()
    assert not calls["positives"][-1][0][1].get("minimax_keyframes")
    assert _frame0_guides(calls) == [{"frame_idx": 0, "frames": 39, "audio": True}]
    d3 = [d for d in store.starred_take("s_long")["drift"] if d["pass"] == 3][0]
    assert d3["handoff"] == "pixels" and "pass cache" in d3["handoff_reason"]


def test_latent_guide_refuses_what_is_not_a_valid_slice(comfy):
    import torch
    from comfy.nested_tensor import NestedTensor
    render, _ = comfy
    lat = {"samples": NestedTensor((torch.zeros(1, 24, 37, 2, 4), torch.zeros(1, 32, 2, 207)))}  # 124 frames
    prev = {"video": torch.ones(1, 24, 12, 2, 4), "gen_frames": 362}
    g = {"source": "prev_pass_tail", "frames": 39, "frame_idx": 0}
    got, why = render.latent_guide(g, lat, prev)
    assert why is None and torch.equal(got, prev["video"])
    assert render.latent_guide(dict(g, frames=38), lat, prev)[1] == "the overlap is 38 frames, not 17k+5"
    assert "pass cache" in render.latent_guide(g, lat, None)[1]
    assert "canvas" in render.latent_guide(g, lat, dict(prev, video=torch.ones(1, 24, 12, 4, 4)))[1]
    assert "fewer latents" in render.latent_guide(g, lat, dict(prev, video=torch.ones(1, 24, 7, 2, 4)))[1]
    assert "17m+5" in render.latent_guide(g, lat, dict(prev, gen_frames=360))[1]
    assert "not a MiniMax H3 AV latent" in render.latent_guide(g, {"samples": torch.zeros(1)}, prev)[1]
    assert render.latent_count(39) == 12 and render.latent_count(124) == 37 and render.latent_frames(37) == 124


def test_h3_vae_latents_of_an_aligned_overlap_are_a_slice(comfy):
    """Why the latent hand-off is valid: the H3 video VAE encodes each 17-frame chunk on its own, so encoding the last
    17j+5 frames of a 17m+5-frame clip gives exactly its last 5j+2 latents (here with a small randomly initialised
    encoder). A tail that does not start on a chunk boundary gives other latents."""
    import comfy.ldm.minimax.vae as h3vae
    import torch
    torch.manual_seed(0)
    vae = h3vae.MiniMaxH3VideoVAE(ch=32, decoder=False, tiling=False)
    for prm in vae.parameters():
        torch.nn.init.normal_(prm, std=0.05)
    vae.latents_mean.zero_()
    vae.latents_std.fill_(1.0)
    x = torch.rand(1, 3, 17 * 4 + 5, 32, 32) * 2 - 1
    with torch.no_grad():
        z = vae.encode(x)
        for k in (39, 22, 5):
            n = (k - 5) // 17 * 5 + 2
            assert torch.equal(z[:, :, -n:], vae.encode(x[:, :, -k:])), k
        assert not torch.allclose(z[:, :, -7:], vae.encode(x[:, :, -38:][:, :, :22]), atol=1e-3)


def test_lossless_pass_cache_reads_back_identical_frames(stubs, harbor, store, roots):
    render, calls, events = stubs
    import torch

    from reelwright import media
    p = _continuing_harbor(harbor, roots)
    p["global"]["long"]["pass_cache"] = "lossless"
    assert render.Renderer(p, store, {}, {"action": "pending"}).run() == ["s_one", "s_lf", "s_long"]
    take = store.starred_take("s_long")
    from reelwright.analysis import analyze
    plan = analyze(p, store)["scenes"]["s_long"]["plan"]
    for rel, x in zip(take["files"]["passes"], plan["passes"]):
        path = store.output_path(rel)
        assert media.is_rgb_video(path)
        frames, audio = media.load_video(path, exact=True)
        n = x["gen_frames"]
        written = torch.linspace(0, 1, n).view(n, 1, 1, 1).expand(n, 32, 64, 3)  # what the stub decoder made
        assert torch.equal(frames, media.to_u8(written).float() / 255)
        assert audio["waveform"].shape[-1] == pytest.approx(n / 24 * 32000, abs=2)
        with open(path[:-4] + ".json", encoding="utf-8") as f:
            assert json.load(f)["codec"] == "lossless"
    # tail.mp4 is lossless too; the last pass holds 124 frames past its seam, so it comes from memory exactly
    tail = store.output_path(take["files"]["tail"])
    assert media.is_rgb_video(tail)
    t, _ = media.load_video(tail, exact=True)
    n = plan["passes"][-1]["gen_frames"]
    ko = plan["passes"][-1]["keep_out_frames"]
    ramp = media.to_u8(torch.linspace(0, 1, n).view(n, 1, 1, 1).expand(n, 32, 64, 3)).float() / 255
    assert t.shape[0] == 124 and torch.equal(t, ramp[ko - 124:ko])
    # a retake of pass 3 reads pass 2 back exactly: the overlap guide is the same 39 frames as from memory
    render.Renderer(p, store, {}, {"action": "pass_retake", "scene_id": "s_long", "pass": 3}).run()
    assert store.starred_take("s_long")["cached_passes"] == 2


def test_lossless_writer_round_trip(comfy, tmp_path):
    import torch

    from reelwright import media
    torch.manual_seed(5)
    frames = torch.rand(29, 48, 80, 3)
    audio = {"waveform": (0.4 * torch.randn(1, 2, int(29 / 24 * 32000))).clamp(-1, 1), "sample_rate": 32000}
    path = str(tmp_path / "p.mp4")
    media.save_video_atomic(frames, audio, path, lossless=True)
    got, a = media.load_video(path, exact=True)
    assert torch.equal(got, media.to_u8(frames).float() / 255)
    n = a["waveform"].shape[-1]
    assert (a["waveform"] - audio["waveform"][..., :n]).abs().max() < 1e-6  # FLAC at 24 bits
    tail, ta = media.load_video(path, exact=True, last_frames=5)
    assert torch.equal(tail, got[-5:]) and ta["waveform"].shape[-1] == pytest.approx(5 / 24 * 32000, abs=2)
    near = str(tmp_path / "n.mp4")
    media.save_video_atomic(frames, audio, near, crf=media.PASS_CRF)
    assert not media.is_rgb_video(near) and media.is_rgb_video(path)
    approx, _ = media.load_video(near, exact=True)  # a CRF 4 file reads as before
    assert not torch.equal(approx, got)


def test_drift_is_recorded_per_continuing_pass(stubs, harbor, store, roots):
    render, calls, events = stubs
    from reelwright.analysis import analyze, plan_response
    p = _continuing_harbor(harbor, roots)
    assert render.Renderer(p, store, {}, {"action": "pending"}).run() == ["s_one", "s_lf", "s_long"]
    assert store.starred_take("s_one")["drift"] == []  # a fresh scene continues from nothing
    lf = store.starred_take("s_lf")["drift"]
    assert [(d["pass"], d["source"], d["frames"]) for d in lf] == [(1, "prev_scene_last", 1)]
    long_ = store.starred_take("s_long")["drift"]
    assert [(d["pass"], d["source"]) for d in long_] == [(1, "prev_scene_tail"), (2, "prev_pass_tail"),
                                                         (3, "prev_pass_tail")]
    for d in long_:
        assert {"anchor_diff", "color_shift", "rgb_shift", "sharpness", "level", "frames"} <= set(d)
        assert d["level"] in ("ok", "warn", "bad") and d["frames"] == 3
    # the stub decoder ramps 0 -> 1 through every pass: a pass starts dark where the pass before ended bright
    assert long_[1]["anchor_diff"] > 100 and long_[1]["handoff"] == "pixels" and long_[1]["level"] == "bad"
    # in meta.json, the index and /plan's takes
    sid_take = store.starred_take("s_long")
    with open(os.path.join(store.take_dir("s_long", sid_take["id"]), "meta.json"), encoding="utf-8") as f:
        assert json.load(f)["drift"] == long_
    takes = plan_response(analyze(p, store))["scenes"]["s_long"]["takes"]
    assert takes[-1]["drift"] == long_
    # a retake of pass 3 keeps the drift passes 1 and 2 were rendered with (from the pass cache)
    render.Renderer(p, store, {}, {"action": "pass_retake", "scene_id": "s_long", "pass": 3}).run()
    again = store.starred_take("s_long")["drift"]
    assert [d.get("pass_cache", False) for d in again] == [True, True, False]
    assert {k: v for k, v in again[1].items() if k != "pass_cache"} == long_[1]


# ---- Global -> Hires (the latent upscaler, an optional refine) -----------------------------------------------------

def test_hires_enlarges_every_pass_to_the_project_size(stubs, harbor, store, roots, monkeypatch):
    render, calls, events = stubs
    from reelwright import assemble, merge
    from reelwright.analysis import analyze
    from reelwright.model import normalize_project, resolve_settings
    harbor["global"]["output"].update(width=64, height=32)
    harbor["global"]["models"]["latent_upscaler"] = "h3_up.safetensors"
    harbor["global"]["hires"] = {"enabled": True, "scale": 2.0, "refine_steps": 3, "refine_denoise": 0.5}
    harbor["scenes"][0]["overrides"] = {"refine_steps": 0}   # s_one: upscaler only
    harbor["scenes"][2]["overrides"] = {"hires": "off"}      # s_short: made at 64x32, enlarged by the merge
    _real_assets(harbor, roots)
    ups, refines = [], []
    monkeypatch.setattr(render.Models, "upscaler", lambda self, name: "up:" + name)

    def fake_up(model, samples, width, height):
        ups.append((model, samples["size"], (width, height)))
        time.sleep(0.06)  # long enough to show in the take's pass times
        return types.SimpleNamespace(result=(dict(samples, size=(width, height)),))

    def fake_refine(model, positive, latent, seed, settings, steps, denoise, on_step):
        refines.append((latent["size"], steps, denoise))
        time.sleep(0.06)
        on_step(steps, steps)  # _hires passes its own callback (phase "refine")
        return latent
    monkeypatch.setattr(render.MiniMaxH3LatentUpscaleWithModel, "execute", staticmethod(fake_up))
    monkeypatch.setattr(render, "_refine", fake_refine)

    p = normalize_project(harbor)
    st = [resolve_settings(p, s, i) for i, s in enumerate(p["scenes"])]
    assert st[0]["hires"] == {"model": "h3_up.safetensors", "width": 128, "height": 64}
    assert st[1]["hires"] == {"model": "h3_up.safetensors", "width": 128, "height": 64, "refine_steps": 3,
                              "refine_denoise": 0.5}
    assert "hires" not in st[2]

    assert render.Renderer(harbor, store, {}, {"action": "pending"}).run() == ["s_one", "s_long", "s_short"]
    n_long = len(analyze(harbor, store)["scenes"]["s_long"]["plan"]["passes"])
    assert len(ups) == 1 + n_long and all(u == ("up:h3_up.safetensors", (64, 32), (128, 64)) for u in ups)
    assert refines == [((128, 64), 3, 0.5)] * n_long
    for sid, size in (("s_one", (128, 64)), ("s_long", (128, 64)), ("s_short", (64, 32))):
        take = store.starred_take(sid)
        info = merge.probe(store.output_path(take["files"]["video"]))
        assert (info["width"], info["height"]) == size, sid
        assert (take["width"], take["height"]) == (64, 32)  # the sampling size (the time estimates read it)
        assert (take.get("out_width"), take.get("out_height")) == (size if sid != "s_short" else (None, None))
    phases = {d["phase"] for e, d in events if e == "reelwright.progress"}
    assert {"upscale", "refine"} <= phases
    assert all({"upscale", "refine"} <= set(x["phases"]) for x in store.starred_take("s_long")["pass_times"])
    assert "refine" not in store.starred_take("s_one")["pass_times"][0]["phases"]

    out = assemble.merge_project(analyze(harbor, store), store)  # the film is the hires size
    info = merge.probe(store.output_path(out["files"]["video"]))
    assert (info["width"], info["height"]) == (128, 64)

    # turning Hires off brings back the keys of a project without it: s_short (off already) stays cached
    harbor["global"]["hires"]["enabled"] = False
    assert render.Renderer(harbor, store, {}, {"action": "pending"}).run() == ["s_one", "s_long"]


def test_hires_without_an_upscaler_is_refused(comfy, harbor, store):
    render, _ = comfy
    harbor["global"]["output"].update(width=64, height=32)
    harbor["global"]["hires"] = {"enabled": True, "scale": 2.0}
    r = render.Renderer(harbor, store, {}, {"action": "pending"})
    assert any(m.startswith("latent_upscale_models/(none selected)") for m in r.missing_models(["s_one"]))
    issues = [x["message"] for x in r.result["issues"]] if "issues" in r.result else []
    assert not issues or any("no latent upscaler is chosen" in m for m in issues)


def test_refine_sigmas_start_part_way(comfy):
    render, _ = comfy

    class MS:
        def get_model_object(self, name):
            import comfy.model_sampling as ms

            class S(ms.ModelSamplingDiscreteFlow, ms.CONST):
                pass
            return S()
    full = render.comfy.samplers.calculate_sigmas(MS().get_model_object("model_sampling"), "simple", 8)
    part = render.refine_sigmas(MS(), "simple", 4, 0.5)
    assert len(part) == 5 and float(part[-1]) == 0.0
    assert [round(float(x), 5) for x in part] == [round(float(x), 5) for x in full[-5:]]
    assert len(render.refine_sigmas(MS(), "simple", 4, 1.0)) == 5


def test_hires_with_the_real_upscale_node(comfy, roots):
    """The real LatentUpscaleModelLoader and MiniMaxH3LatentUpscaleWithModel with a tiny random H3 upscaler: the video
    latent is enlarged to the asked size, the sound latent passes through (render.Models.upscaler, render._hires)."""
    render, _ = comfy
    if render.MiniMaxH3LatentUpscaleWithModel is None:
        pytest.skip("this ComfyUI has no H3 latent upscale node")
    import comfy.nested_tensor
    import comfy.ops
    import folder_paths
    import torch
    from comfy.ldm.minimax.latent_upscaler import MiniMaxH3LatentUpscaler
    from safetensors.torch import save_file
    d = os.path.join(roots.output, "ups")
    os.makedirs(d, exist_ok=True)
    torch.manual_seed(0)
    m = MiniMaxH3LatentUpscaler(in_channels=24, channels=32, in_blocks=2, out_blocks=2, temporal_kernel=5,
                                dtype=torch.float32, operations=comfy.ops.manual_cast)
    save_file({k: torch.randn_like(v) * 0.02 for k, v in m.state_dict().items()}, os.path.join(d, "tiny_up.safetensors"))
    folder_paths.add_model_folder_path("latent_upscale_models", d)
    models = render.Models({})
    up = models.upscaler("tiny_up.safetensors")
    assert models.upscaler("tiny_up.safetensors") is up  # loaded once
    video, audio = torch.randn(1, 24, 7, 2, 4), torch.randn(1, 32, 2, 50)
    with torch.inference_mode():
        out = render.MiniMaxH3LatentUpscaleWithModel.execute(
            model=up, samples={"samples": comfy.nested_tensor.NestedTensor((video, audio))}, width=128, height=64).result[0]
    v, a = out["samples"].tensors
    assert tuple(v.shape) == (1, 24, 7, 4, 8) and torch.equal(a, audio)
    kept = render._with_audio_of({"samples": comfy.nested_tensor.NestedTensor((v, torch.zeros_like(a)))}, out)
    assert torch.equal(kept["samples"].tensors[1], audio)
    assert render.output_size({"width": 64, "height": 32, "hires": {"width": 128, "height": 64}}) == (128, 64)
    assert render.output_size({"width": 64, "height": 32}) == (64, 32)
