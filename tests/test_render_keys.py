"""Cache keys, take status and plan extras (added 2026-11-03 v0.6.0). Pure: no ComfyUI needed."""

import copy

import pytest

from reelwright import cache
from reelwright.analysis import analyze, plan_response, rekey, seconds_per_frame, _rate_samples


def _take(r, sid, tid, **kw):
    t = {"id": tid, "key": r["scenes"][sid]["key"], "files": {}, "created": 1000, "upstream": None}
    t.update(kw)
    return t


def test_upstream_take_is_part_of_the_key(harbor, store):
    r = analyze(harbor, store)
    store.add_take("s_one", _take(r, "s_one", "v1"))
    r = analyze(harbor, store)
    assert r["scenes"]["s_long"]["upstream_take"] == "v1"
    store.add_take("s_long", _take(r, "s_long", "v1", upstream={"scene_id": "s_one", "take_id": "v1"}))
    r = analyze(harbor, store)
    assert r["scenes"]["s_long"]["status"] == "cached" and not r["scenes"]["s_long"]["upstream_changed"]
    # a new take of scene 1 (same settings, other seed) makes the scene that continues from it stale
    store.add_take("s_one", _take(r, "s_one", "v2", variant=1, created=2000))
    r2 = analyze(harbor, store)
    assert r2["scenes"]["s_one"]["status"] == "cached"
    assert r2["scenes"]["s_long"]["status"] == "stale"
    assert r2["scenes"]["s_long"]["upstream_take"] == "v2" and r2["scenes"]["s_long"]["upstream_changed"]
    assert r2["scenes"]["s_short"]["status"] == "missing"          # fresh start: not affected
    # rekey gives the renderer the same key the next analysis computes
    keys, key = rekey(r, "s_long", store.starred_take("s_one"))
    assert key == r2["scenes"]["s_long"]["key"] and keys == r2["scenes"]["s_long"]["pass_keys"]
    # starring v1 again makes it cached again
    store.star("s_one", "v1")
    assert analyze(harbor, store)["scenes"]["s_long"]["status"] == "cached"


def test_takes_from_before_v060_stay_cached(harbor, store):
    """A take without "upstream" was keyed the v0.5.1 way; it still counts until its upstream gets a newer take."""
    r = analyze(harbor, store)
    legacy = {}
    up = None
    for s in r["project"]["scenes"]:
        sr = r["scenes"][s["id"]]
        keys = []
        prev = None
        for b, x in zip(sr["builds"], sr["plan"]["passes"]):
            prev = cache.pass_key(sr["_fp"], b, x, r["_asset_digest"], up, prev)
            keys.append(prev)
        legacy[s["id"]] = cache.scene_key(sr["plan"], keys)
        up = legacy[s["id"]]
    store.add_take("s_one", {"id": "v1", "key": legacy["s_one"], "files": {}, "created": 1000})
    store.add_take("s_long", {"id": "v1", "key": legacy["s_long"], "files": {}, "created": 1001})
    r = analyze(harbor, store)
    assert r["scenes"]["s_one"]["status"] == "cached" and r["scenes"]["s_long"]["status"] == "cached"
    assert not r["scenes"]["s_long"]["upstream_changed"]
    # scene 1 gets a newer take: the old continuing take no longer counts
    store.add_take("s_one", {"id": "v2", "key": legacy["s_one"], "files": {}, "created": 5000})
    r = analyze(harbor, store)
    assert r["scenes"]["s_long"]["status"] == "stale" and r["scenes"]["s_long"]["upstream_changed"]


def test_crossfade_is_in_the_key_of_overlap_seams_only(harbor, store):
    p = copy.deepcopy(harbor)
    k_cut = analyze(p, store)["scenes"]["s_long"]["key"]
    p["global"]["long"]["crossfade_frames"] = 6
    assert analyze(p, store)["scenes"]["s_long"]["key"] == k_cut  # this long scene is joined at shot cuts
    p["global"]["long"]["seam_mode"] = "overlap"
    k1 = analyze(p, store)["scenes"]["s_long"]["key"]
    p["global"]["long"]["crossfade_frames"] = 12
    assert analyze(p, store)["scenes"]["s_long"]["key"] != k1
    assert analyze(p, store)["scenes"]["s_one"]["key"] == analyze(harbor, store)["scenes"]["s_one"]["key"]


def test_manual_star_is_kept(harbor, store):
    r = analyze(harbor, store)
    store.add_take("s_one", {"id": "v1", "key": "old-settings", "files": {}, "upstream": None})
    store.add_take("s_one", _take(r, "s_one", "v2"))
    idx = store.read_index("s_one")
    idx["auto_star"] = "v2"
    store.write_index("s_one", idx)
    r = analyze(harbor, store)
    assert r["scenes"]["s_one"]["status"] == "cached" and not r["scenes"]["s_one"]["manual_star"]
    store.star("s_one", "v1")  # picked by hand
    r = analyze(harbor, store)
    s = r["scenes"]["s_one"]
    assert s["manual_star"] and s["starred"] == "v1" and s["match"] == "v2" and s["status"] == "cached"
    assert r["scenes"]["s_long"]["upstream_take"] == "v1"   # the next scene continues from the hand-picked take
    # an index from before v0.6.0 (no auto_star): a star on an older take than the newest counts as manual
    assert cache.manual_star({"starred": "v1", "takes": [{"id": "v1"}, {"id": "v2"}]})
    assert not cache.manual_star({"starred": "v2", "takes": [{"id": "v1"}, {"id": "v2"}]})


def test_plan_extras(harbor, store):
    r = analyze(harbor, store)
    store.add_take("s_one", _take(r, "s_one", "v1", prompts=["pass one prompt"], render_seconds=96.0,
                                  sampled_frames=192, width=1344, height=768, steps=20, quality="final"))
    out = plan_response(analyze(harbor, store))
    s1, s2 = out["scenes"]["s_one"], out["scenes"]["s_long"]
    assert s1["starred_prompts"] == ["pass one prompt"]
    assert "prompts" not in s1["takes"][0]                     # kept out of the plan (can be large)
    assert s1["estimate_seconds"] == pytest.approx(96.0)         # 0.5 s per generated frame
    gen = sum(x["gen_frames"] for x in s2["passes"])
    assert s2["estimate_seconds"] == pytest.approx(0.5 * gen)
    assert out["estimate"]["scenes"] == 2 and out["estimate"]["seconds"] == pytest.approx(
        s2["estimate_seconds"] + out["scenes"]["s_short"]["estimate_seconds"])
    assert {"upstream_take", "upstream_changed", "manual_star", "cached_passes"} <= set(s2)
    assert s2["upstream_take"] == "v1" and s1["upstream_take"] is None


def test_estimates_without_history_and_scaling():
    assert seconds_per_frame([], {"width": 64, "height": 32, "steps": 8, "quality": "final"}) is None
    rows = _rate_samples([{"render_seconds": 100, "sampled_frames": 100, "width": 100, "height": 100, "steps": 10,
                           "quality": "final", "created": 1},
                          {"render_seconds": 50, "sampled_frames": 0, "quality": "final"}])  # all from the pass cache
    assert len(rows) == 1
    # half the pixels: half the time per frame
    assert seconds_per_frame(rows, {"width": 50, "height": 100, "steps": 10, "quality": "final"}) == pytest.approx(0.5)
    # takes from before v0.6.0 have no size: used for the same quality
    old = _rate_samples([{"render_seconds": 248, "frames": 60, "quality": "draft", "created": 1}])
    assert seconds_per_frame(old, {"width": 1, "height": 1, "steps": 1, "quality": "draft"}) == pytest.approx(2.0)


def test_pass_file_keys_follow_seeds_and_chains():
    builds = [{"guides": []}, {"guides": [{"source": "prev_pass_tail"}]}, {"guides": []}]
    a = cache.pass_file_keys(["k1", "k2", "k3"], builds, [1, 2, 3])
    b = cache.pass_file_keys(["k1", "k2", "k3"], builds, [9, 2, 3])
    assert a[0] != b[0] and a[1] != b[1] and a[2] == b[2]   # pass 2 continues pass 1; pass 3 starts at a cut
    assert all(len(k) == 32 for k in a)
    assert cache.upstream_dependent([{"guides": [{"source": "prev_scene_tail"}]}] + builds[1:], True) == [True, True, False]
    assert cache.upstream_dependent(builds, False) == [False, False, False]


# ---- v0.6.0 review (added 2026-11-03) -----------------------------------------------------------------------------

def test_error_scene_provides_its_starred_take(harbor, store):
    """No run renders or re-stars a scene with lint errors, so the scene after it is keyed against its starred take
    (the one a render and a merge use), not the take that matches."""
    v1, v2 = {"id": "v1", "key": "k"}, {"id": "v2", "key": "other"}
    index = {"takes": [v1, v2], "starred": "v2", "auto_star": "v2"}
    ok = cache.resolve({}, index, "k", False)
    assert ok["status"] == "cached" and ok["match"] is v1 and ok["provided"] is v1   # reuse() stars v1
    err = cache.resolve({}, index, "k", True)
    assert err["status"] == "error" and err["match"] is v1 and err["provided"] is v2
    assert cache.resolve({}, dict(index, starred=None), "k", True)["provided"] is None
    assert cache.resolve({}, {"takes": []}, "k", True)["provided"] is None
    # through analyze: an undone edit of scene 1 (v1 matches, v2 starred by the render), then a lint error
    r = analyze(harbor, store)
    store.add_take("s_one", _take(r, "s_one", "v1"))
    store.add_take("s_one", _take(r, "s_one", "v2", key="older-edit", created=2000))
    idx = store.read_index("s_one")
    idx["auto_star"] = "v2"
    store.write_index("s_one", idx)
    assert analyze(harbor, store)["scenes"]["s_long"]["upstream_take"] == "v1"
    harbor["scenes"][0]["dialogue"] = [{"id": "d_x", "speaker": "", "t": 30.0, "text": "too late"}]  # an error
    r = analyze(harbor, store)["scenes"]
    assert r["s_one"]["status"] == "error" and r["s_one"]["match"] == "v1"
    assert r["s_long"]["upstream_take"] == "v2"


def test_short_upstream_take_is_a_warning(harbor, store):
    from reelwright.analysis import short_upstream_tail, tail_guide_frames
    harbor["scenes"].append({"id": "s_e", "title": "E", "duration": 6.0, "start": {"mode": "tail", "overlap_frames": 73}})
    harbor["scenes"][2]["duration"] = 6.0
    r = analyze(harbor, store)
    assert tail_guide_frames(r["scenes"]["s_e"]["builds"]) == 73 and tail_guide_frames(r["scenes"]["s_one"]["builds"]) == 0
    assert not [x for x in r["issues"] if x.get("code") == "short_upstream_tail"]   # s_short is rendered first
    store.add_take("s_short", _take(r, "s_short", "v1", key="when-it-was-2.5s", frames=60))
    store.add_take("s_short", _take(r, "s_short", "v2", frames=144, created=2000))
    store.star("s_short", "v1")  # by hand
    r = analyze(harbor, store)
    s_e = r["scenes"]["s_e"]
    assert s_e["upstream_take"] == "v1" and s_e["status"] == "missing"
    warn = [x for x in s_e["issues"] if x.get("code") == "short_upstream_tail"]
    assert len(warn) == 1 and warn[0]["level"] == "warn" and warn[0]["scene_id"] == "s_e"
    assert warn[0]["message"] == ("04 E: it continues with a 73-frame tail clip of 03 Hand on the door, but the take "
                                  "it continues from (v1) has only 60 frames. Render 03 Hand on the door again, or "
                                  "use a tail overlap of at most 56 frames or a last-frame start.")
    assert plan_response(r)["scenes"]["s_e"]["issues"] == s_e["issues"]
    store.star("s_short", "v2")
    assert not [x for x in analyze(harbor, store)["issues"] if x.get("code") == "short_upstream_tail"]
    # a take that does not say how long it is is not judged (render refuses a short one when it reads it)
    p, i = r["project"], s_e["index"]
    assert short_upstream_tail(p, i, s_e["builds"], {"id": "v9"}) is None
    assert short_upstream_tail(p, i, s_e["builds"], {"id": "v9", "frames": 73}) is None
    assert "no tail overlap" in short_upstream_tail(p, i, s_e["builds"], {"id": "v9", "frames": 3})
