"""Render orchestration inside a real ComfyUI checkout, with the H3 model calls stubbed.

Run with COMFYUI_PATH pointing at a ComfyUI checkout whose requirements are
installed. Everything except encoding, sampling and decoding is real: planning,
guides, file writing, pass stitching, takes, caching and the merge.
"""

import importlib.util
import json
import os
import re  # added 2026-11-02 v0.2.0
import subprocess
import sys
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
                                "video_audios": sorted(kw["ref_video_audios"] or {}), "audios": sorted(kw["ref_audios"] or {})})
        return types.SimpleNamespace(result=([["cond", {}]], {"samples": torch.zeros(1), "frames": kw["length"],
                                                             "size": (kw["width"], kw["height"])}))

    def fake_guide(**kw):
        calls["guides"].append({"frame_idx": kw["frame_idx"], "frames": int(kw["image"].shape[0]),
                                "audio": kw["audio"] is not None})
        return types.SimpleNamespace(result=(kw["positive"],))

    def fake_sample(model, positive, latent, seed, settings, on_step):
        calls["sample"].append(seed)
        on_step(settings["steps"], settings["steps"])
        return latent

    class FakeDecode:
        def decode(self, vae, samples):
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
    assert long_enc["images"] == ["ref_image_0", "ref_image_1"]   # Mara's sheet + the named keyframe
    assert long_enc["videos"] == ["ref_video_0"] and long_enc["video_audios"] == ["ref_video_audio_0"]
    assert long_enc["audios"] == ["ref_audio_0"]                  # Mara's voice

    # pass 1 continues the previous scene's 39-frame tail with audio; later passes get overlap or keyframe guides
    assert calls["guides"][0] == {"frame_idx": 0, "frames": 39, "audio": True}
    assert any(g["frames"] == 1 and g["frame_idx"] > 0 for g in calls["guides"])  # 25 s letter keyframe

    for sid, secs in (("s_one", 8.0), ("s_long", 32.0), ("s_short", 2.5)):
        take = store.starred_take(sid)
        video = store.output_path(take["files"]["video"])
        assert merge.probe(video)["duration"] == pytest.approx(secs, abs=0.1), sid
        # added 2026-11-02 v0.2.0: takes are named <slug>_<NN>_<title>_<take>.mp4
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


# added 2026-11-02 v0.2.1: a failed auto-merge must not break the node (it used to probe its own broken cut)
def test_node_survives_a_failed_merge(stubs, harbor, roots, monkeypatch):
    render, calls, events = stubs
    from reelwright import assemble as asm, merge
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


# added 2026-11-02 v0.3.5: latent previews go to the Render tab as reelwright.preview events, not onto the node
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
    # [OLD 2026-11-02 v0.3.7->v0.3.8] assert len(asked) < 5                                          # decoded only when sent (about once a second)
    assert len(asked) < 5                                          # decoded only when sent (at most every 0.25 s)


# added 2026-11-02 v0.3.8: previews follow the sampler (it used to be at most one a second)
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
    import base64, io
    img = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert max(img.size) == render.PREVIEW_MAX_SIDE


# added 2026-11-02 v0.3.9: VideoHelperSuite's animated previews wrap latent_preview.get_previewer; Reelwright uses the
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


# added 2026-11-03 v0.4.1: the anchor sheet keeps every anchor (no 3×3 cap) and shapes cells like the pictures
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


# added 2026-11-03 v0.4.1: a failing face check no longer loses the finished take
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
