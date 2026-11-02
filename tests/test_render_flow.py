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
