"""v0.20.0: the crop window's backend (detect.py, /reelwright/crop and /reelwright/detect).

Sencer: "say there are two people in a single image, i want to use the person on the left as an anchor ... should we
add crop ability to anchors?" / "instead of just faces, should we add "objects", to find dog, face, person, tea cup or
whatever?" Faces come from insightface, things by name from Grounding DINO through transformers; here a tiny random
Grounding DINO built on the spot stands in for the real one (whose 700 MB of weights are downloaded on request).
"""

import importlib.util
import os
import time

import pytest

from tests.test_routes import COMFY, api, get, post  # noqa: F401 - the api fixture

pytestmark = pytest.mark.skipif(not COMFY or importlib.util.find_spec("transformers") is None,
                                reason="needs COMFYUI_PATH, torch and transformers")


def _picture(path, size=(400, 300), exif_rotate=False):
    from PIL import Image
    im = Image.new("RGB", size, (20, 20, 20))
    im.paste((250, 0, 0), (0, 0, size[0] // 2, size[1]))  # left half red
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if exif_rotate:  # stored on its side, shown upright (EXIF orientation 6: rotate 90° clockwise to show)
        ex = Image.Exif()
        ex[0x0112] = 6
        im.rotate(90, expand=True).save(path, exif=ex)
    else:
        im.save(path)
    return path


def tiny_dino(folder):
    """A Grounding DINO with random weights and a 13-word vocabulary: the real code path, nonsense boxes."""
    from transformers import (
        BertConfig,
        BertTokenizer,
        BertTokenizerFast,
        GroundingDinoConfig,
        GroundingDinoForObjectDetection,
        GroundingDinoImageProcessor,
        GroundingDinoProcessor,
        SwinConfig,
    )
    os.makedirs(folder, exist_ok=True)
    words = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", ".", "a", "dog", "person", "tea", "cup", "face", "cat"]
    with open(os.path.join(folder, "vocab.txt"), "w") as f:
        f.write("\n".join(words) + "\n")
    BertTokenizer(os.path.join(folder, "vocab.txt"), do_lower_case=True).save_pretrained(folder)
    tok = BertTokenizerFast.from_pretrained(folder)
    backbone = SwinConfig(embed_dim=16, depths=[1, 1, 1, 1], num_heads=[1, 1, 1, 1], window_size=7,
                          out_features=["stage2", "stage3", "stage4"])
    text = BertConfig(vocab_size=len(words), hidden_size=32, num_hidden_layers=1, num_attention_heads=2,
                      intermediate_size=64, max_position_embeddings=64)
    cfg = GroundingDinoConfig(backbone_config=backbone, text_config=text, d_model=32, encoder_layers=1,
                              decoder_layers=2, encoder_attention_heads=2, decoder_attention_heads=2,
                              encoder_ffn_dim=64, decoder_ffn_dim=64, num_queries=20, num_feature_levels=3,
                              encoder_n_points=2, decoder_n_points=2, max_text_len=32, use_timm_backbone=False)
    GroundingDinoProcessor(image_processor=GroundingDinoImageProcessor(size={"shortest_edge": 224, "longest_edge": 320}),
                           tokenizer=tok).save_pretrained(folder)
    GroundingDinoForObjectDetection(cfg).save_pretrained(folder)
    return folder


@pytest.fixture
def detect(api, roots, monkeypatch):  # noqa: F811 - api is test_routes' fixture
    run, _routes, _ = api
    from reelwright import detect as d
    monkeypatch.setattr(d, "_model", None)
    monkeypatch.setattr(d, "_download", {"state": "idle", "error": "", "started": 0.0})
    monkeypatch.setattr(d, "models_dir", lambda: os.path.join(roots.user, "models", "grounding-dino-tiny"))
    return run, d


def test_words_boxes_and_labels(detect):
    _, d = detect
    assert d._prompt(["Dog", " tea  cup ", "person.", ""]) == "dog. tea cup. person."
    assert d._label("a dog", ["dog", "tea cup"]) == "dog"
    assert d._label("tea cup [SEP]", ["dog", "tea cup"]) == "tea cup"
    assert d._label("the lamp", ["dog"]) == "lamp"  # no query matches: its own words
    assert d._label("[SEP]", ["dog"]) == "thing" and d._label("dog [SEP]", ["cat"]) == "dog"
    # a face widened to head and shoulders, inside the picture
    assert d.head_and_shoulders(100, 100, 200, 200, 1000, 1000) == [0.03, 0.03, 0.24, 0.28]
    assert d.head_and_shoulders(0, 0, 50, 50, 100, 100) == [0.0, 0.0, 0.85, 1.0]
    found = [{"box": [0.1, 0.1, 0.3, 0.3], "label": "dog", "score": 0.6},
             {"box": [0.11, 0.1, 0.3, 0.3], "label": "dog", "score": 0.9},
             {"box": [0.11, 0.1, 0.3, 0.3], "label": "cat", "score": 0.5}]
    assert [(f["label"], f["score"]) for f in d._dedupe(found)] == [("dog", 0.9), ("cat", 0.5)]


def test_crop_cuts_the_picture_as_shown(detect, tmp_path):
    from PIL import Image
    _, d = detect
    src = _picture(str(tmp_path / "rot.jpg"), size=(400, 300), exif_rotate=True)
    w, h = d.crop(src, [0.0, 0.0, 0.5, 1.0], str(tmp_path / "out" / "left.png"))
    assert (w, h) == (200, 300)
    with Image.open(tmp_path / "out" / "left.png") as im:
        assert im.getpixel((100, 150))[0] > 200  # the red half, as it is shown
    with pytest.raises(ValueError, match="too small"):
        d.crop(src, [0.5, 0.5, 0.01, 0.01], str(tmp_path / "out" / "dot.png"))


def test_find_objects_with_a_tiny_grounding_dino(detect, tmp_path):
    _, d = detect
    folder = tiny_dino(str(tmp_path / "dino"))
    assert d.detector_ready(folder)
    src = _picture(str(tmp_path / "group.png"), size=(320, 240))
    found = d.find_objects(src, ["dog", "tea cup"], folder=folder, box_threshold=0.0, text_threshold=0.0)
    assert found and len(found) <= d.MAX_BOXES
    for f in found:
        x, y, w, h = f["box"]
        assert 0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 - x + 1e-6 and 0 < h <= 1 - y + 1e-6
        assert isinstance(f["label"], str) and f["label"] and 0 <= f["score"] <= 1
    assert d._model is not None and next(d._model[1].parameters()).device.type == "cpu"  # moved off the GPU after use
    with pytest.raises(ValueError, match="Name what to find"):
        d.find_objects(src, [" ", ""], folder=folder)
    with pytest.raises(ValueError, match="not downloaded"):
        d.find_objects(src, ["dog"], folder=str(tmp_path / "nothing"))


def test_download_status(detect, monkeypatch):
    _, d = detect
    import huggingface_hub
    calls = []

    def fake_snapshot(repo, local_dir, allow_patterns):
        calls.append((repo, allow_patterns))
        os.makedirs(local_dir, exist_ok=True)
        for name in ("config.json", "model.safetensors"):
            with open(os.path.join(local_dir, name), "w") as f:
                f.write("{}")
    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot)
    assert d.status()["objects"]["ready"] is False
    d.download()
    for _ in range(50):
        if d._download["state"] != "downloading":
            break
        time.sleep(0.05)
    s = d.status()
    assert s["objects"]["ready"] and s["objects"]["state"] == "done"
    assert calls == [("IDEA-Research/grounding-dino-tiny", ["*.json", "*.safetensors", "*.txt"])]
    d._download.update(state="error", error="ProxyError: 403 Forbidden")  # an earlier try failed, the files came later
    assert d.status()["objects"]["state"] == "done" and d.status()["objects"]["error"] == ""


def test_crop_and_detect_routes(detect, roots, monkeypatch):
    run, d = detect
    from reelwright import continuity
    _picture(os.path.join(roots.input, "reelwright", "harbor_lights", "group.png"), size=(400, 300))
    os.makedirs(os.path.join(roots.input, "reelwright", "harbor_lights"), exist_ok=True)
    with open(os.path.join(roots.input, "reelwright", "harbor_lights", "clip.mp4"), "wb") as f:
        f.write(b"not really")
    monkeypatch.setattr(continuity, "available", lambda: True)
    monkeypatch.setattr(continuity, "find_faces", lambda bgr: [((40.0, 40.0, 100.0, 120.0), 0.97)])
    rel = "reelwright/harbor_lights/group.png"

    async def go(c):
        out = {}
        out["crop"] = await post(c, "/reelwright/crop", {"slug": "harbor_lights", "file": rel, "box": [0, 0, 0.5, 1], "name": "Mara left"})
        out["again"] = await post(c, "/reelwright/crop", {"slug": "harbor_lights", "file": rel, "box": [0, 0, 0.5, 1], "name": "Mara left"})
        out["bad_box"] = await post(c, "/reelwright/crop", {"slug": "harbor_lights", "file": rel, "box": [0.5, 0, 0.8, 1]})
        out["video"] = await post(c, "/reelwright/crop", {"slug": "harbor_lights", "file": "reelwright/harbor_lights/clip.mp4", "box": [0, 0, 1, 1]})
        out["escape"] = await post(c, "/reelwright/crop", {"slug": "harbor_lights", "file": "../secret.png", "box": [0, 0, 1, 1]})
        out["faces"] = await post(c, "/reelwright/detect", {"slug": "harbor_lights", "file": rel, "mode": "faces"})
        out["objects"] = await post(c, "/reelwright/detect", {"slug": "harbor_lights", "file": rel, "mode": "objects", "queries": ["dog"]})
        out["status"] = await get(c, "/reelwright/detect/status")
        return out
    out = run(go)
    status, body = out["crop"]
    assert status == 200 and body["asset"]["file"].startswith("reelwright/harbor_lights/crops/mara_left_")
    assert (body["asset"]["width"], body["asset"]["height"]) == (200, 300) and body["small"] is True
    assert os.path.isfile(os.path.join(roots.input, body["asset"]["file"]))
    assert out["again"][1]["asset"]["file"] == body["asset"]["file"]  # the same box, the same file
    for k in ("bad_box", "video", "escape"):
        assert out[k][0] == 400 and out[k][1]["error"], k
    status, body = out["faces"]
    assert status == 200 and body["engine"] == "insightface"
    assert body["boxes"] == [{"box": [0.0, 0.0, 0.355, 0.6933], "label": "face", "score": 0.97}]
    assert out["objects"][0] == 400 and "not downloaded" in out["objects"][1]["error"]
    assert out["status"][1]["faces"]["ready"] is True and out["status"][1]["objects"]["ready"] is False
