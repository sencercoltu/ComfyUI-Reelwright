from reelwright import spec
from reelwright.model import (assign_codes, default_project, effective_loras, normalize_project,
                              resolve_settings, scene_seed, slugify)


def test_frame_grid_matches_native_node():
    # comfy_extras.nodes_minimax_h3.align_frame_count snaps up to 17k+5
    assert [spec.align_frames_up(n) for n in (1, 5, 6, 124, 125, 192, 361, 362)] == [5, 5, 22, 124, 141, 192, 362, 362]
    assert spec.align_frames_down(200) == 192
    assert spec.clamp_pass_frames(60) == 124
    assert spec.clamp_pass_frames(400) == 362


def test_canvas_matches_native_node():
    assert spec.adapt_canvas(16, 9) == (1344, 768)
    assert spec.adapt_canvas(9, 16) == (768, 1344)
    assert spec.adapt_canvas(1, 1) == (768, 768)
    assert spec.adapt_canvas(21, 9) == (1536, 672)  # Python rounds 48.5 to even


def test_normalize_fills_and_keeps_user_values():
    p = normalize_project('{"name": "My Film!", "scenes": [{"title": "A", "duration": 3}], '
                          '"assets": [{"kind": "video"}, {"kind": "image"}, {"kind": "video", "code": "V1"}]}')
    assert p["slug"] == "my_film"
    assert p["scenes"][0]["duration"] == 3
    assert p["scenes"][0]["prompt"]["mode"] == "structured"
    assert sorted(a["code"] for a in p["assets"]) == ["P1", "V1", "V2"]
    assert normalize_project("not json")["scenes"]


def test_slugify():
    assert slugify("Harbor Lights — v2") == "harbor_lights_v2"
    assert slugify("") == "untitled"


def test_assign_codes_is_stable():
    assets = [{"kind": "image", "code": "P2"}, {"kind": "image"}, {"kind": "audio"}]
    assign_codes(assets)
    assert [a["code"] for a in assets] == ["P2", "P1", "A1"]


def test_seed_modes():
    p = default_project()
    s = p["scenes"][0]
    p["global"]["sampling"].update(seed=10, seed_mode="increment")
    assert scene_seed(p, s, 3) == 13
    p["global"]["sampling"]["seed_mode"] = "fixed"
    assert scene_seed(p, s, 3) == 10
    s["overrides"]["seed"] = 77
    assert scene_seed(p, s, 3) == 77


def test_lora_stack_add_replace_and_strength_override():
    p = default_project()
    p["global"]["loras"] = [{"id": "l_1", "name": "grain", "strength": 0.6, "enabled": True},
                            {"id": "l_2", "name": "style", "strength": 0.8, "enabled": False}]
    s = p["scenes"][0]
    s["overrides"]["loras"] = {"mode": "add", "items": [{"name": "candle", "strength": 0.7, "enabled": True}],
                               "strengths": {"l_1": 0.35}}
    assert effective_loras(p, s) == [("grain", 0.35), ("candle", 0.7)]
    s["overrides"]["loras"]["mode"] = "replace"
    assert effective_loras(p, s) == [("candle", 0.7)]


def test_draft_quality_scales_and_cuts_steps():
    p = default_project()
    p["global"]["quality"] = "draft"
    st = resolve_settings(p, p["scenes"][0], 0)
    assert (st["width"], st["height"], st["steps"]) == (672, 384, 8)


def test_scene_overrides_win():
    p = default_project()
    s = p["scenes"][0]
    s["overrides"].update(video_vae="other_vae.safetensors", steps=30)
    st = resolve_settings(p, s, 0)
    assert st["video_vae"] == "other_vae.safetensors" and st["steps"] == 30
    assert st["audio_vae"] == p["global"]["models"]["audio_vae"]
