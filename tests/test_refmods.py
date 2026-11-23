"""RefMods for the cast: Sencer asked "can we add RefMod support for cast characters?" and picked "instead of anchors"
and "also as voice".

A RefMod is a saved MiniMax H3 reference made with ComfyUI-MiniMaxH3Mod (models/refmods/<name>.safetensors). A cast
member's look RefMod goes instead of its anchor pictures and video anchors (outfit pictures still go) unless a scene
unticks it; a voice RefMod goes instead of the voice sample when the character speaks.
"""

import json
import os
import struct

import pytest

from reelwright import cache, model, prompt, refmods, validate
from reelwright.planner import plan_scene

IMG = {"kind": "image", "t": 1, "h": 64, "w": 64}
VID = {"kind": "video", "t": 4, "h": 32, "w": 32}
AUD = {"kind": "audio", "t": 200, "h": 0, "w": 0}


def project(look=None, voice=None, speaks=True, outfit=True):
    p = model.default_project("Mods")
    p["assets"] = [{"id": "a_b1", "kind": "image", "name": "Birten front", "file": "reelwright/m/b1.png"},
                   {"id": "a_b2", "kind": "image", "name": "Birten side", "file": "reelwright/m/b2.png"},
                   {"id": "a_dress", "kind": "image", "name": "Dress", "file": "reelwright/m/dress.png"},
                   {"id": "a_voice", "kind": "audio", "name": "voice", "file": "reelwright/m/voice.wav", "duration": 5.0},
                   {"id": "a_clip", "kind": "video", "name": "clip", "file": "reelwright/m/clip.mp4", "duration": 6.0}]
    p["cast"] = [{"id": "c_b", "kind": "character", "name": "Birten", "description": "a man in his 40s",
                  "anchors": ["a_b1", "a_b2"], "pack_sheet": False, "voice": "a_voice",
                  "outfits": [{"id": "o_dress", "name": "Dress", "assets": ["a_dress"]}] if outfit else [],
                  "video_anchors": [{"id": "va_1", "asset": "a_clip", "in": 0, "out": 4}],
                  "refmod": look or {"name": ""}, "voice_refmod": voice or {"name": ""}}]
    s = p["scenes"][0]
    s["cast"] = [{"id": "c_b", "outfit": "o_dress" if outfit else ""}]
    s["shots"] = [{"id": "h1", "t": 0, "text": "@Birten walks in the rain.", "camera": ""}]
    s["dialogue"] = [{"id": "d1", "speaker": "c_b", "t": 1.0, "text": "Hello.", "language": "English"}] if speaks else []
    return model.normalize_project(p)


def build(p, k=1):
    s = p["scenes"][0]
    plan = plan_scene(p, s, 0)
    return prompt.build_pass(p, s, 0, plan, plan["passes"][k - 1])


def section(text, name):
    return text.split(name + ":\n", 1)[1].split("\n\n", 1)[0]


def test_normalised_alike():
    p = project(look={"name": "  characters\\birten.safetensors ", "strength": 3,
                      "members": [IMG, {"kind": "bundle"}, {"kind": "video", "t": "4", "h": 32.9, "w": -2}, "x"]},
                voice={"name": "voices/birten", "strength": -1, "members": [AUD]})
    c = p["cast"][0]
    assert c["refmod"] == {"name": "characters/birten", "strength": 1.0,
                           "members": [IMG, {"kind": "", "t": 1, "h": 0, "w": 0}, {"kind": "video", "t": 4, "h": 32, "w": 0}]}
    assert c["voice_refmod"]["strength"] == 0.0 and model.voice_parts(c) == []  # strength 0: not sent
    assert model.norm_refmod(None) == {"name": "", "strength": 1.0, "members": []}
    assert model.refmod_frames(1) == 1 and model.refmod_frames(2) == 5 and model.refmod_frames(16) == 52
    assert model.refmod_tokens(IMG) == 1024 and model.refmod_tokens(VID) == 4 * 16 * 16 and model.refmod_tokens(AUD) == 400


def test_look_refmod_instead_of_anchors():
    plain = build(project())
    assert [i["assets"] for i in plain["images"]] == [["a_b1"], ["a_b2"], ["a_dress"]]
    assert any(v.get("anchor") for v in plain["videos"])  # the video anchor goes without a RefMod

    b = build(project(look={"name": "characters/birten", "strength": 0.8, "members": [IMG, VID]}))
    assert [i.get("refmod", {}).get("member") if i.get("refmod") else i["assets"] for i in b["images"]] == [0, ["a_dress"]]
    assert b["images"][0]["refmod"] == {"name": "characters/birten", "member": 0, "kind": "image", "t": 1, "h": 64,
                                        "w": 64, "strength": 0.8}
    assert [v["refmod"]["member"] for v in b["videos"]] == [1]  # no video anchor, the RefMod's video
    assert section(b["prompt"], "subject_definitions").splitlines()[0] == \
        "<Subject 1> is Birten, a man in his 40s, shown in <Picture 1> and in <Video 1>, wearing Dress as shown in " \
        "<Picture 2>."
    assert "[reference generation" in b["prompt"]
    # the budget counts what the build sends
    s = b and project(look={"name": "characters/birten", "strength": 0.8, "members": [IMG, VID]})
    n = model.scene_media_counts(s, s["scenes"][0])
    assert (n["pictures"], n["videos"], n["files"]) == (2, 1, 4) and n["video_seconds"] == pytest.approx(13 / 24)


def test_a_scene_can_untick_the_refmod():
    p = project(look={"name": "characters/birten", "members": [IMG]})
    p["scenes"][0]["cast"][0]["skip"] = [model.REFMOD_SKIP, "a_b2"]
    b = build(p)
    assert [i["assets"] for i in b["images"]] == [["a_b1"], ["a_dress"]] and not any(i.get("refmod") for i in b["images"])
    assert model.scene_media_counts(p, p["scenes"][0])["pictures"] == 2


def test_voice_refmod_instead_of_the_voice_sample():
    voice = {"name": "voices/birten", "strength": 1, "members": [AUD]}
    b = build(project(voice=voice))
    assert [a.get("refmod", {}).get("name") for a in b["audios"]] == ["voices/birten"] and b["audios"][0]["number"] == 1
    assert "<Audio 1> is the voice-timbre reference for <Subject 1> (S1)." in b["prompt"]
    assert "audio reference" in b["tags"]
    p = project(voice=voice)
    n = model.scene_media_counts(p, p["scenes"][0])
    assert (n["audio"], n["audio_seconds"]) == (1, 5.0)
    # only when the character speaks in the pass, like the voice sample
    assert build(project(voice=voice, speaks=False))["audios"] == []
    # a bundle used for both: its pictures for the look, its audio for the voice
    both = {"name": "characters/birten", "members": [IMG, AUD]}
    b = build(project(look=both, voice=both))
    assert [i["refmod"]["member"] for i in b["images"] if i.get("refmod")] == [0]
    assert [a["refmod"]["member"] for a in b["audios"]] == [1]


def test_lint_and_keys():
    p = project(look={"name": "characters/birten", "members": [IMG]})
    p["cast"][0]["anchors"] = []
    s = p["scenes"][0]
    plans = {s["id"]: plan_scene(p, s, 0)}
    builds = {s["id"]: [build(p)]}
    msgs = [x["message"] for x in validate.lint_project(p, plans, builds, lambda a: True)]
    assert not any("identity is not locked" in m for m in msgs)  # its RefMod carries the look
    b = builds[s["id"]][0]
    x = plans[s["id"]]["passes"][0]
    key = lambda b, d: cache.pass_key({}, b, x, lambda a: a, None, None, refmod_digest=d)  # noqa: E731
    assert key(b, lambda n: "one") != key(b, lambda n: "two")
    b2 = json.loads(json.dumps(b))
    b2["images"][0]["refmod"]["strength"] = 0.5
    assert key(b, lambda n: "one") != key(b2, lambda n: "one")
    # a pass without RefMods keeps its key
    plain = build(project())
    assert key(plain, None) == key(plain, lambda n: 1 / 0)


# ---- the files ----------------------------------------------------------------------------------------------------------
def write_refmod(path, meta, tensors, sidecar=False):
    """A safetensors file as ComfyUI-MiniMaxH3Mod writes it (zeros for data)."""
    head, offset = {}, 0
    for k, shape in tensors.items():
        n = 2
        for d in shape:
            n *= d
        head[k] = {"dtype": "F16", "shape": shape, "data_offsets": [offset, offset + n]}
        offset += n
    if not sidecar:
        head["__metadata__"] = {"refmod_meta": json.dumps(meta)}
    raw = json.dumps(head).encode()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(raw)) + raw + b"\0" * offset)
    if sidecar:
        with open(path[:-len(".safetensors")] + ".json", "w") as f:
            json.dump(meta, f)


@pytest.fixture
def mods_dir(tmp_path, monkeypatch):
    d = tmp_path / "refmods"
    write_refmod(str(d / "characters" / "birten.safetensors"), {"name": "birten", "kind": "image", "latent_t": 1},
                 {"latent": [1, 24, 1, 64, 64]})
    write_refmod(str(d / "hero.safetensors"),
                 {"kind": "bundle", "name": "hero", "members": [{"kind": "video"}, {"kind": "audio"}]},
                 {"ref_0": [1, 24, 4, 32, 32], "ref_1": [1, 32, 2, 200]})
    write_refmod(str(d / "old.safetensors"), {"kind": "audio", "description": "old voice"}, {"latent": [1, 32, 2, 80]},
                 sidecar=True)
    write_refmod(str(d / "bad.safetensors"), {"kind": "image"}, {"latent": [1, 24, 3, 64, 64]})  # 3 frames: no image
    write_refmod(str(d / "lora.safetensors"), None, {"w": [4]})  # no RefMod metadata
    write_refmod(str(d / "graph_presets" / "x.safetensors"), {"kind": "image"}, {"latent": [1, 24, 1, 8, 8]})
    monkeypatch.setattr(refmods, "roots", lambda: [str(d)])
    return d


def test_listing_and_reading(mods_dir):
    got = {x["name"]: x for x in refmods.list_refmods()}
    assert sorted(got) == ["bad", "characters/birten", "hero", "old"]
    assert got["characters/birten"]["members"] == [IMG] and got["hero"]["kind"] == "bundle"
    assert got["hero"]["members"] == [VID, AUD]
    assert got["old"]["members"] == [{"kind": "audio", "t": 80, "h": 0, "w": 0}] and got["old"]["description"] == "old voice"
    assert got["bad"]["members"] == [{"kind": "", "t": 1, "h": 0, "w": 0}]
    assert refmods.summary("characters\\birten.safetensors") == [IMG]
    assert refmods.summary("missing") is None
    for bad in ("../x", "a/../../x", "a//b", "graph_presets/x", "C:/x"):
        with pytest.raises(ValueError):
            refmods.find(bad)
    assert refmods.digest("hero") == cache.file_digest(str(mods_dir / "hero.safetensors"))
    assert refmods.digest("nope") == "missing:nope"


def test_plan_errors_for_missing_or_changed_files(mods_dir):
    p = project(look={"name": "characters/birten", "members": [IMG]}, voice={"name": "hero", "members": [VID, AUD]})
    builds = {p["scenes"][0]["id"]: [build(p)]}
    assert refmods.issues(p, builds) == []
    p["cast"][0]["refmod"]["members"] = [dict(IMG, h=32)]
    p["cast"][0]["voice_refmod"]["name"] = "gone"
    builds = {p["scenes"][0]["id"]: [build(p)]}
    msgs = sorted(x["message"] for x in refmods.issues(p, builds))
    assert msgs == ["01 Scene 1: Birten's RefMod characters/birten has changed since it was picked: press Update under "
                    "Cast -> Birten -> RefMod",
                    "01 Scene 1: Birten's voice RefMod gone is not in models/refmods (Cast -> Birten)"]


# ---- render: the RefMods among the node's references --------------------------------------------------------------------
class FakeVAE:
    def decode(self, z):
        import torch
        frames = model.refmod_frames(z.shape[2])
        return torch.zeros(1, frames, z.shape[3] * 16, z.shape[4] * 16, 3)


def test_pass_mods_line_up_with_the_node(monkeypatch):
    torch = pytest.importorskip("torch")
    b = {"images": [{"assets": ["a"]}, {"refmod": dict(IMG, name="m", member=0, strength=1.0)}, {"assets": ["b"]}],
         "videos": [{"refmod": dict(VID, name="m", member=1, strength=0.5)}, {"asset": "v", "soundtrack": True}],
         "audios": [{"asset": "x"}, {"refmod": dict(AUD, name="m", member=2, strength=1.0)}]}
    shapes = {0: [1, 24, 1, 64, 64], 1: [1, 24, 4, 32, 32], 2: [1, 32, 2, 200]}
    mods = refmods.PassMods(b, {1}, FakeVAE(), load_fn=lambda name, i, e: torch.ones(*shapes[i]))
    native = [{"type": "image", "n": "a"}, {"type": "image", "n": "b"}, {"type": "audio", "n": "v-sound"},
              {"type": "video", "n": "v"}, {"type": "audio", "n": "x"}]
    items = mods.items(native)
    assert [x.get("n") or "mod-" + x["type"] for x in items] == \
        ["a", "mod-image", "b", "mod-video", "v-sound", "v", "x", "mod-audio"]
    assert items[1]["data"].shape == (1, 1024, 1024, 3)
    assert items[3]["timestamps"] == [0.0, 0.5] and items[3]["data"].shape[0] == 2  # 13 frames at 24 fps, Qwen's 2 fps
    blocks = mods.blocks([{"kind": "image", "n": "a"}, {"kind": "image", "n": "b"}, {"kind": "video_audio", "n": "v"},
                          {"kind": "audio", "n": "x"}])
    assert [x.get("n") or "mod-" + x["kind"] for x in blocks] == ["a", "mod-image", "b", "mod-video", "v", "x", "mod-audio"]
    assert blocks[3]["latent_t"] == 4 and blocks[6]["ref_audio_t"] == 200
    assert float(blocks[1]["latent"].mean()) == 1.0  # strength 1: as saved
    with pytest.raises(RuntimeError):
        mods.items(native[:-1])
    with pytest.raises(RuntimeError):
        mods.blocks([{"kind": "image"}])


def test_weakened_mixes_toward_a_blur():
    torch = pytest.importorskip("torch")
    z = torch.zeros(1, 24, 1, 16, 16)
    z[..., 0, 0] = 64.0
    w = refmods.weakened(z, 0.25)
    assert w.shape == z.shape and 16 <= float(w[0, 0, 0, 0, 0]) < 64 and float(w[0, 0, 0, 9, 9]) > 0  # detail spread out
    assert refmods.weakened(z, 1.0) is z
    a = torch.zeros(1, 32, 2, 40)
    assert refmods.weakened(a, 0.5).shape == a.shape


def test_with_the_real_h3_node(monkeypatch):
    """MiniMaxH3ReferenceToVideo itself, with a CLIP and VAEs that only record: the RefMods reach the tokenizer and
    the conditioning at the places the prompt numbers them."""
    comfy = os.environ.get("COMFYUI_PATH")
    torch = pytest.importorskip("torch")
    if not comfy:
        pytest.skip("needs COMFYUI_PATH")
    import sys
    sys.path.insert(0, comfy)
    from comfy.cli_args import args
    args.cpu = True
    from comfy_extras.nodes_minimax_h3 import MiniMaxH3ReferenceToVideo

    class Clip:
        def tokenize(self, text, minimax_ref_items=None):
            self.items = minimax_ref_items
            return {"text": text}

        def encode_from_tokens_scheduled(self, tokens):
            return [[torch.zeros(1, 4, 8), {"minimax_token_tags": torch.zeros(1, 4)}]]

    class VideoVAE(FakeVAE):
        def encode(self, px):
            return torch.full((1, 24, 1 + (px.shape[0] - 1) // 4, px.shape[1] // 16, px.shape[2] // 16), 2.0)

    class AudioVAE:
        audio_sample_rate = 32000

        def encode(self, w):
            return torch.full((1, 32, 2, 40), 3.0)

    b = {"images": [{"assets": ["a"]}, {"refmod": dict(IMG, name="m", member=0, strength=1.0)}],
         "videos": [{"asset": "v", "soundtrack": True}, {"refmod": dict(VID, name="m", member=1, strength=1.0)}],
         "audios": [{"refmod": dict(AUD, name="m", member=2, strength=1.0)}, {"asset": "x"}]}
    shapes = {0: [1, 24, 1, 64, 64], 1: [1, 24, 4, 32, 32], 2: [1, 32, 2, 200]}
    mods = refmods.PassMods(b, {0}, VideoVAE(), load_fn=lambda name, i, e: torch.ones(*shapes[i]))
    clip = Clip()
    audio = {"waveform": torch.zeros(1, 1, 32000), "sample_rate": 32000}
    out = MiniMaxH3ReferenceToVideo.execute(
        clip=mods.clip(clip), prompt="p", width=512, height=512, length=124, ref_image_size="match",
        vae=VideoVAE(), audio_vae=AudioVAE(), ref_images={"ref_image_0": torch.zeros(1, 512, 512, 3)},
        ref_videos={"ref_video_0": torch.zeros(22, 256, 256, 3)}, ref_video_audios={"ref_video_audio_0": audio},
        ref_audios={"ref_audio_1": audio})
    cond = mods.attach(out.result[0])
    assert [x["type"] for x in clip.items] == ["image", "image", "audio", "video", "video", "audio", "audio"]
    refs = cond[0][1]["minimax_refs"]
    assert [r["kind"] for r in refs] == ["image", "image", "video_audio", "video", "audio", "audio"]
    assert float(refs[1]["latent"].mean()) == 1.0 and float(refs[0]["latent"].mean()) == 2.0
    assert refs[4]["ref_audio_t"] == 200 and refs[5]["ref_audio_t"] == 40
    assert "minimax_token_tags" in cond[0][1]


def test_load_reads_the_member(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    st = pytest.importorskip("safetensors.torch")
    d = tmp_path / "refmods"
    d.mkdir()
    meta = {"kind": "bundle", "name": "hero", "_format_version": 5,
            "members": [{"kind": "image", "name": "face"}, {"kind": "audio", "name": "voice"}]}
    st.save_file({"ref_0": torch.full((1, 24, 1, 8, 8), 0.5, dtype=torch.float16),
                  "ref_1": torch.full((1, 32, 2, 40), 0.25)}, str(d / "hero.safetensors"),
                 metadata={"refmod_meta": json.dumps(meta)})
    st.save_file({"latent": torch.ones(1, 24, 3, 8, 8)}, str(d / "walk.safetensors"),
                 metadata={"refmod_meta": json.dumps({"kind": "video", "name": "walk"})})
    monkeypatch.setattr(refmods, "roots", lambda: [str(d)])
    face = refmods.load("hero", 0, {"kind": "image", "t": 1, "h": 8, "w": 8})
    assert face.dtype == torch.float32 and face.shape == (1, 24, 1, 8, 8) and float(face.mean()) == 0.5
    assert float(refmods.load("hero", 1).mean()) == 0.25 and refmods.load("walk", 0).shape[2] == 3
    with pytest.raises(ValueError, match="changed since it was picked"):
        refmods.load("hero", 0, {"kind": "image", "t": 1, "h": 16, "w": 16})
    with pytest.raises(ValueError):
        refmods.load("walk", 1)
    with pytest.raises(FileNotFoundError):
        refmods.load("nobody", 0)


# ---- stacked photos (v0.23.2): Sencer: "are you sure you implemented refmod correctly? i created a refmod identity, used it
# in cast, but a random character shows." His RefMod was photos that went in as one video (2 latent frames: the photos
# after the first packed into one); the pack's default stack is one latent frame per photo, now sent as pictures.
def stack_meta(n, mode="encode", shapes=None):
    return {"name": "id", "kind": "video", "mode": mode, "source": "stack", "latent_t": n,
            "source_shape": " +".join(shapes or ["1x16x8"] * n), "tags": ["{} img, 0 vid".format(n)]}


def test_a_stack_of_photos_goes_as_pictures(tmp_path, monkeypatch):
    d = tmp_path / "refmods"
    write_refmod(str(d / "stack.safetensors"), stack_meta(3), {"latent": [1, 24, 3, 16, 8]})
    write_refmod(str(d / "batch.safetensors"),  # photos given to a video slot: one video source, 2 latent frames
                 {"name": "b", "kind": "video", "mode": "encode", "source": "video", "source_shape": "2x114x64",
                  "tags": ["0 img, 1 vid"]}, {"latent": [1, 24, 2, 114, 64]})
    write_refmod(str(d / "mixed.safetensors"), stack_meta(17, shapes=["1x16x8", "16x16x8"]), {"latent": [1, 24, 17, 16, 8]})
    write_refmod(str(d / "many.safetensors"), stack_meta(12, mode="training"), {"latent": [1, 24, 12, 16, 8]})
    write_refmod(str(d / "kit.safetensors"),  # a bundle whose first member is a stack
                 {"kind": "bundle", "name": "kit", "members": [stack_meta(2), {"kind": "audio"}]},
                 {"ref_0": [1, 24, 2, 16, 8], "ref_1": [1, 32, 2, 80]})
    monkeypatch.setattr(refmods, "roots", lambda: [str(d)])
    got = {x["name"]: x for x in refmods.list_refmods()}
    pic = {"kind": "image", "t": 1, "h": 16, "w": 8}
    assert got["stack"]["members"] == [pic] * 3 and got["stack"]["packed"] == [{"kind": "video", "t": 3, "h": 16, "w": 8}]
    assert got["stack"]["notes"] == []
    assert got["kit"]["members"] == [pic, pic, {"kind": "audio", "t": 80, "h": 0, "w": 0}]
    assert got["batch"]["members"] == [{"kind": "video", "t": 2, "h": 114, "w": 64}] and "packed" not in got["batch"]
    assert got["batch"]["notes"][0].startswith("Made from 5 frames of one video input (0.21 s)")
    assert got["mixed"]["members"][0]["kind"] == "video" and "one video" in got["mixed"]["notes"][0]
    assert got["many"]["members"][0]["kind"] == "video" and got["many"]["notes"][0].startswith("A Compressed Reference")
    assert refmods.summary("stack") == [pic] * 3 and refmods.summary("stack", split=False) == got["stack"]["packed"]
    assert [p[1:] for p in refmods.layout(*refmods._read_head(str(d / "kit.safetensors")))] == \
        [("ref_0", 0), ("ref_0", 1), ("ref_1", 0)]

    # the prompt: one subject shown in both pictures
    b = build(project(look={"name": "stack", "members": [pic] * 3}, outfit=False, speaks=False))
    assert section(b["prompt"], "subject_definitions") == \
        "<Subject 1> is Birten, a man in his 40s, shown in <Picture 1>, <Picture 2>, and <Picture 3>."
    assert [i["refmod"]["member"] for i in b["images"]] == [0, 1, 2] and not b["videos"]

    # a project that picked it before: Update, said so
    p = project(look={"name": "stack", "members": got["stack"]["packed"]}, outfit=False, speaks=False)
    (issue,) = refmods.issues(p, {p["scenes"][0]["id"]: [build(p)]})
    assert issue["message"] == "01 Scene 1: Birten's RefMod stack holds stacked photos, which Reelwright now sends as " \
        "separate pictures: press Update under Cast -> Birten -> RefMod"


def test_load_slices_a_photo_out_of_a_stack(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    st = pytest.importorskip("safetensors.torch")
    d = tmp_path / "refmods"
    d.mkdir()
    z = torch.stack([torch.full((1, 24, 16, 8), float(k)) for k in range(3)], dim=2).to(torch.float16)
    st.save_file({"latent": z}, str(d / "stack.safetensors"), metadata={"refmod_meta": json.dumps(stack_meta(3))})
    monkeypatch.setattr(refmods, "roots", lambda: [str(d)])
    pic = {"kind": "image", "t": 1, "h": 16, "w": 8}
    for k in range(3):
        one = refmods.load("stack", k, pic)
        assert one.shape == (1, 24, 1, 16, 8) and one.dtype == torch.float32 and float(one.mean()) == k
    with pytest.raises(ValueError, match="changed since it was picked"):
        refmods.load("stack", 0, {"kind": "video", "t": 3, "h": 16, "w": 8})  # picked before: the one video
    # to the node: three pictures, each decoded on its own for the text encoder
    b = {"images": [{"refmod": dict(pic, name="stack", member=k, strength=1.0)} for k in range(3)], "videos": [], "audios": []}
    mods = refmods.PassMods(b, set(), FakeVAE())
    items = mods.items([])
    assert [x["type"] for x in items] == ["image"] * 3 and items[0]["data"].shape == (1, 256, 128, 3)
    blocks = mods.blocks([])
    assert [(x["kind"], x["latent_h"], x["latent_w"], float(x["latent"].mean())) for x in blocks] == \
        [("image", 16, 8, 0.0), ("image", 16, 8, 1.0), ("image", 16, 8, 2.0)]
