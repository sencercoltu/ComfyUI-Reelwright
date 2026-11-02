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


# ---- added 2026-11-02 v0.3.0 ----
def test_scene_quality_override():
    from reelwright.model import default_project, resolve_settings, effective_loras
    p = default_project("Q")
    p["global"]["quality"] = "final"
    p["global"]["draft"].update(lora="turbo.safetensors", scale=0.5, steps=4)
    s = p["scenes"][0]
    final = resolve_settings(p, s, 0)
    s["overrides"]["quality"] = "draft"
    draft = resolve_settings(p, s, 0)
    assert final["quality"] == "final" and draft["quality"] == "draft"
    assert draft["steps"] == 4 and draft["width"] < final["width"]
    assert ("turbo.safetensors", 1.0) in effective_loras(p, s)
    p["global"]["quality"] = "draft"
    s["overrides"]["quality"] = "final"
    assert resolve_settings(p, s, 0)["quality"] == "final"
    assert all(n != "turbo.safetensors" for n, _ in effective_loras(p, s))


def test_profiles_store(tmp_path):
    from reelwright import profiles
    from reelwright.model import default_global
    root = str(tmp_path)
    assert profiles.load(root) == {"profiles": [], "default": ""}
    g = default_global()
    a = profiles.save(root, "Draft box", g, make_default=True)
    pid = a["profile"]["id"]
    assert a["default"] == pid and a["profiles"][0]["name"] == "Draft box"
    g2 = dict(g, quality="draft")
    b = profiles.save(root, "Draft box v2", g2, pid=pid)
    assert len(b["profiles"]) == 1 and b["profiles"][0]["global"]["quality"] == "draft" and b["default"] == pid
    profiles.save(root, "Other", g)
    assert len(profiles.load(root)["profiles"]) == 2
    assert profiles.set_default(root, "")["default"] == ""
    assert [x["name"] for x in profiles.delete(root, pid)["profiles"]] == ["Other"]
    import pytest
    with pytest.raises(ValueError):
        profiles.save(root, "  ", g)
    with pytest.raises(ValueError):
        profiles.delete(root, "nope")


# added 2026-11-02 v0.3.6: autosaved versions can be deleted; project.json stays
def test_delete_versions(store, harbor):
    import os
    import pytest
    from reelwright.storage import read_json
    vdir = os.path.join(store.dir, "versions")
    os.makedirs(vdir, exist_ok=True)
    store.autosave(harbor)
    names = ["project_20261102_08{:02d}00.json".format(m) for m in range(3)]
    for n in names:
        with open(os.path.join(vdir, n), "w") as f:
            f.write("{}")
    have = [v["name"] for v in store.list_versions()]
    assert set(names) <= set(have)
    assert store.delete_versions([names[0]]) == 1
    assert names[0] not in [v["name"] for v in store.list_versions()]
    with pytest.raises(ValueError):
        store.delete_versions(["../project.json"])
    assert store.delete_versions([v["name"] for v in store.list_versions()]) == len(have) - 1
    assert store.list_versions() == [] and read_json(os.path.join(store.dir, "project.json"))["slug"] == harbor["slug"]
