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
    # v0.6.0: accents transliterated, no ASCII letters -> untitled, at most 64 characters (storage.SLUG_RE)
    assert slugify("Ömer's Café") == "omers_cafe"
    assert slugify("Москва") == slugify("日本") == slugify("2024") == "untitled"
    long = slugify("word " * 40)
    assert len(long) <= 64 and not long.endswith("_")
    from reelwright.storage import SLUG_RE
    assert SLUG_RE.match(long)


def test_assign_codes_is_stable():
    assets = [{"kind": "image", "code": "P2"}, {"kind": "image"}, {"kind": "audio"}]
    assign_codes(assets)
    assert [a["code"] for a in assets] == ["P2", "P1", "A1"]


def test_seed_modes():
    p = default_project()
    s = p["scenes"][0]
    p["global"]["sampling"].update(seed=10, seed_mode="increment")
    # v0.6.0: "+1 per scene" adds the scene's seed_n (fixed at creation), not its position
    assert s["seed_n"] == 0 and scene_seed(p, s, 3) == 10
    s["seed_n"] = 3
    assert scene_seed(p, s, 0) == 13
    del s["seed_n"]  # a scene that was never normalised falls back to its index
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


# ---- added 2026-11-03 v0.6.0 ----
import json  # noqa: E402

from reelwright import model, soundtrack  # noqa: E402
from reelwright.planner import plan_project, plan_scene  # noqa: E402


def test_normalize_survives_malformed_json():
    bad = [{"scenes": [None]}, {"scenes": [], "global": "x"}, {"scenes": [{"refs": {}}]},
           {"scenes": [{"prompt": "text"}]}, {"scenes": [{}], "soundtrack": 5},
           {"scenes": [{"cast": ["c_1"]}], "cast": [{"id": "c_1", "name": 5}]},
           {"scenes": [{}, {"start": "tail"}]}, {"scenes": [{"duration": "abc"}, {"duration": "nan"}]},
           {"scenes": [{"shots": [{"t": "x"}, None], "dialogue": "d", "overrides": {"seed": ""}}]}]
    for raw in bad:
        p = normalize_project(json.dumps(raw))
        assert p["scenes"] and all(isinstance(s["duration"], (int, float)) for s in p["scenes"])
        plan_project(p)  # what analyze does next
        model.scene_starts(p)
        for s in p["scenes"]:
            model.scene_seed(p, s, 0)
            model.scene_media_counts(p, s)
    p = normalize_project({"scenes": [{"prompt": "a raw prompt"}, {"start": "tail"}], "cast": [{"name": 5}]})
    assert p["scenes"][0]["prompt"]["mode"] == "raw" and p["scenes"][0]["prompt"]["raw"] == "a raw prompt"
    assert p["scenes"][1]["start"]["mode"] == "tail" and p["cast"][0]["name"] == "5"
    assert normalize_project('{"scenes": [{"duration": NaN}]}')["scenes"][0]["duration"] == 8.0  # JSON.parse refuses NaN
    durations = [s["duration"] for s in normalize_project({"scenes": [{"duration": -1}, {"duration": 1e9},
                                                                      {"duration": "12.5"}]})["scenes"]]
    assert durations == [1 / 24, 600.0, 12.5]


def test_normalize_sorts_and_repairs_ids_and_codes():
    p = normalize_project({"scenes": [
        {"id": "s_a", "shots": [{"id": "h", "t": 5}, {"id": "h", "t": 1}],
         "dialogue": [{"id": "d", "t": 3}, {"id": "d", "t": 2}], "refs": [{"id": "r"}, {"id": "r"}]},
        {"id": "s_a"}, {"id": "s a/b"}],
        "assets": [{"kind": "image", "code": "P1"}, {"kind": "video", "code": "p1"}, {"kind": "image"}]})
    assert [s["id"] for s in p["scenes"]] == ["s_a", "s_a_2", "s_a_b"]
    s = p["scenes"][0]
    assert [x["t"] for x in s["shots"]] == [1, 5] and [x["id"] for x in s["shots"]] == ["h_2", "h"]
    assert [x["t"] for x in s["dialogue"]] == [2, 3] and sorted(x["id"] for x in s["dialogue"]) == ["d", "d_2"]
    assert [r["id"] for r in s["refs"]] == ["r", "r_2"]
    assert [a["code"] for a in p["assets"]] == ["P1", "V1", "P2"]


def test_slug_kept_when_valid_and_project_id_kept_or_empty():
    p = normalize_project({"name": "Mine", "slug": "untitled-x7k2", "scenes": [{}]})
    assert p["slug"] == "untitled-x7k2" and p["project_id"] == ""
    p = normalize_project({"name": "My Film", "slug": "My Film!", "project_id": "p_abc", "scenes": [{}]})
    assert p["slug"] == "my_film" and p["project_id"] == "p_abc"
    assert normalize_project({"name": "x" * 100, "scenes": [{}]})["slug"] == "x" * 64


def test_seed_n_assigned_once_and_stable():
    p = normalize_project({"scenes": [{"id": "s_a"}, {"id": "s_b"}, {"id": "s_c"}]})
    assert [s["seed_n"] for s in p["scenes"]] == [0, 1, 2]  # what their seeds were before v0.6.0
    p["global"]["sampling"].update(seed=100, seed_mode="increment")
    before = {s["id"]: model.scene_seed(p, s, i) for i, s in enumerate(p["scenes"])}
    new = model.default_scene(p, id="s_new")
    assert new["seed_n"] == model.next_seed_n(p) == 3
    p["scenes"].insert(0, new)
    p = normalize_project(p)
    after = {s["id"]: model.scene_seed(p, s, i) for i, s in enumerate(p["scenes"])}
    assert all(after[k] == v for k, v in before.items()) and after["s_new"] == 103
    rep = normalize_project({"scenes": [{"seed_n": 3}, {}, {"seed_n": 3}, {"seed_n": "1"}, {"seed_n": -1}]})
    assert [s["seed_n"] for s in rep["scenes"]] == [3, 1, 4, 5, 6]
    assert default_project()["scenes"][0]["seed_n"] == 0


def _chain(durations, modes, overlaps=None, reanchor=2):
    p = default_project()
    p["global"]["continuity"]["reanchor_after"] = reanchor
    overlaps = overlaps or [39] * len(durations)
    p["scenes"] = [{"id": "s_{}".format(i), "duration": d, "start": {"mode": m, "overlap_frames": o}}
                   for i, (d, m, o) in enumerate(zip(durations, modes, overlaps))]
    return normalize_project(p)


def test_effective_start_reanchor_and_caps():
    p = _chain([8, 6, 6, 6, 6], ["fresh", "tail", "tail", "tail", "tail"], reanchor=2)
    assert [model.effective_start(p, i) for i in range(5)] == ["fresh", "tail", "tail", "last_frame", "last_frame"]
    assert [model.tail_overlap_frames(p, i) for i in range(5)] == [0, 39, 39, 0, 0]
    assert model.scene_overlap_at(p, 3) == 1 / 24
    # capped by the scene before (1 s = 24 frames -> 22) and by its own length; under 5 frames -> last frame
    p = _chain([1, 6, 0.1, 6], ["fresh", "tail", "tail", "tail"], [90, 90, 39, 39])
    assert [model.tail_overlap_frames(p, i) for i in range(4)] == [0, 22, 0, 0]
    assert [model.effective_start(p, i) for i in range(4)] == ["fresh", "tail", "last_frame", "last_frame"]
    p = _chain([20, 20], ["fresh", "tail"], [39, 300])  # never more than the 124-frame tail clip render keeps
    assert model.tail_overlap_frames(p, 1) == 124


def test_scene_starts_and_visible_start():
    p = _chain([8, 10, 5], ["fresh", "tail", "last_frame"])
    starts, total = model.scene_starts(p)
    assert starts == {"s_0": 0.0, "s_1": 8 - 39 / 24, "s_2": 8 - 39 / 24 + 10 - 1 / 24}
    assert model.visible_start(p, "s_1") == 8.0 and model.visible_start(p, "s_2") == starts["s_1"] + 10
    assert total == starts["s_2"] + 5 and model.visible_start(p, "nope") is None


def test_media_counts_voice_video_sound_and_song():
    p = default_project()
    # v0.7.0: without the continuation clips of the overlap seams (tests/test_continuation.py counts those)
    p["global"]["continuity"]["name_continuation"] = False
    p["assets"] = [{"id": "a_pic", "kind": "image", "file": "x.png"},
                   {"id": "a_v", "kind": "audio", "file": "v.wav", "duration": 4.0},
                   {"id": "a_vid", "kind": "video", "file": "c.mp4", "duration": 5.0},
                   {"id": "a_song", "kind": "audio", "file": "s.wav", "duration": 30.0}]
    p["cast"] = [{"id": "c_a", "name": "A", "anchors": ["a_pic"], "voice": "a_v"}]
    p["scenes"] = [{"id": "s_l", "duration": 32.0, "cast": [{"id": "c_a"}],
                    "refs": [{"asset": "a_vid", "role": "reference", "soundtrack": True}],
                    "dialogue": [{"speaker": "c_a", "t": 25.0, "text": "hi"}]}]
    p = normalize_project(p)
    s = p["scenes"][0]
    passes = plan_scene(p, s, 0)["passes"]
    counts = [model.scene_media_counts(p, s, x) for x in passes]
    assert len(passes) == 3
    # the video's own sound takes an audio slot in every pass; the voice only where A speaks
    assert [c["audio"] for c in counts] == [1, 1, 2]
    assert all(c["files"] == c["pictures"] + c["videos"] + c["audio"] - 1 for c in counts)
    assert model.scene_media_counts(p, s)["audio"] == 2
    # a song in the last pass only: it replaces the voice there; a track without a file never plays
    p["soundtrack"] = [{"asset": "a_song", "start": 25.0, "sync": True}]
    p = normalize_project(p)
    s = p["scenes"][0]
    songs = [soundtrack.pass_soundtrack(p, 0.0, x) is not None for x in passes]
    counts = [model.scene_media_counts(p, s, x) for x in passes]
    assert [c["song"] for c in counts] == songs == [False, False, True]
    assert counts[2]["audio"] == 2 and counts[2]["audio_seconds"] == 5.0 + passes[2]["gen_frames"] / 24
    p["assets"][3]["file"] = ""
    assert not any(model.scene_media_counts(p, s, x)["song"] for x in passes)


# ---- added 2026-11-04 v0.6.1 (review of v0.6.0) ----
def test_profile_update_of_a_deleted_profile_is_refused(tmp_path):
    """Review 13: save() with an id that is not saved (deleted in another tab) added a second profile of that name;
    delete() and set_default() refuse such an id, and so does save() now. "Save as new" sends no id."""
    import pytest
    from reelwright import profiles
    root = str(tmp_path)
    a = profiles.save(root, "Box", {"steps": 8})["profile"]
    with pytest.raises(ValueError, match="unknown profile"):
        profiles.save(root, "Box", {"steps": 12}, pid="g_gone")
    assert [(x["id"], x["global"]) for x in profiles.load(root)["profiles"]] == [(a["id"], {"steps": 8})]
    assert len(profiles.save(root, "Box 2", {"steps": 4}, pid=None)["profiles"]) == 2
    assert len(profiles.save(root, "Box 3", {"steps": 4}, pid="")["profiles"]) == 3
