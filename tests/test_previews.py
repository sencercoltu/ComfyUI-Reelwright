"""Previews (v0.23.0). Sencer: "Add an option to render only minimum frames that MMH3 supports (first seconds. so we
can see if scene is set up correctly before waiting for a long render)."

A preview renders the first 124 frames of a scene (the shortest pass H3 is trained on) as a take marked "preview":
never starred, merged or continued from, and it does not make the scene count as rendered.
"""

import os

from reelwright import assemble, cache, model, spec
from reelwright.analysis import analyze
from reelwright.planner import plan_scene, preview_plan


def long_scene():
    p = model.default_project("Previews")
    p["assets"] = [{"id": "a_kf", "kind": "image", "name": "kf", "file": "x/kf.png"},
                   {"id": "a_end", "kind": "image", "name": "end", "file": "x/end.png"}]
    s = p["scenes"][0]
    s.update(duration=20.0, trim={"keep": "middle", "in": 0.0})
    s["shots"] = [{"id": "h1", "t": 0, "text": "a"}, {"id": "h2", "t": 3.0, "text": "b"}, {"id": "h3", "t": 5.12, "text": "c"}, {"id": "h3b", "t": 5.16, "text": "c2"},
                  {"id": "h4", "t": 12.0, "text": "d"}]
    s["dialogue"] = [{"id": "d1", "speaker": "", "t": 1.0, "text": "early"}, {"id": "d2", "speaker": "", "t": 9.0, "text": "late"}]
    s["refs"] = [{"id": "r_kf", "asset": "a_kf", "role": "keyframe", "time": 2.0},
                 {"id": "r_kf2", "asset": "a_kf", "role": "keyframe", "time": 15.0},
                 {"id": "r_end", "asset": "a_end", "role": "last_frame"}]
    s["prompt"] = {"pass_prompts": {"1": "pass one", "2": "pass two"}}
    return model.normalize_project(p)


def test_a_preview_is_pass_one_at_the_shortest_length():
    p = long_scene()
    s = p["scenes"][0]
    full = plan_scene(p, s, 0)
    v = preview_plan(full)
    assert len(full["passes"]) == 2 and v["kind"] == "single" and v["frames"] == 124 and v["preview"]
    (x,) = v["passes"]
    assert (x["gen_frames"], x["keep_in_frames"], x["keep_out_frames"], x["end"]) == (124, 0, 124, 124 / 24)
    assert x["seed"] == full["passes"][0]["seed"]  # pass 1's seed
    assert [sh["id"] for sh in x["shots"]] == ["h1", "h2", "h3"]  # 5.12 s is frame 123 (the last); 5.16 s is 124
    assert [d["id"] for d in x["dialogue"]] == ["d1"]
    assert [k["ref"] for k in x["keyframes"]] == ["r_kf"]  # the one at 15 s is past the preview
    assert len(full["passes"][0]["shots"]) == 4 and full["frames"] == 480  # the full plan is untouched
    # a scene of one pass: its last-frame guide is left out (it would pin the preview's end)
    s["duration"] = 10.0
    one = plan_scene(p, s, 0)
    assert one["passes"][0]["last_frame"] and preview_plan(one)["passes"][0]["last_frame"] == []
    # no longer than a preview: rendered whole
    s["duration"] = 4.0
    assert model.previews_whole(s) and preview_plan(plan_scene(p, s, 0)) == plan_scene(p, s, 0)
    assert model.PREVIEW_FRAMES == spec.MIN_PASS_FRAMES


def test_analysis_of_a_preview(harbor, store):
    # the long walk (32 s, 3 passes, a tail start) names @P3, a keyframe at 25 s: past the preview, so in words
    res = analyze(harbor, store, previews=["s_long"])["scenes"]["s_long"]
    assert res["plan"]["frames"] == 124 and len(res["prompts"]) == 1 and res["status"] != "error"
    assert not [x for x in res["issues"] if x["level"] == "error"]
    assert "@P3" not in res["prompts"][0] and "<Picture" in res["prompts"][0]
    full = analyze(harbor, store)["scenes"]["s_long"]
    assert len(full["plan"]["passes"]) > 1 and full["key"] != res["key"]


def test_previews_do_not_count_as_takes():
    full = {"id": "v1", "key": "k", "created": 1}
    pre = {"id": "v2", "key": "k2", "created": 2, "preview": True}
    idx = {"starred": None, "takes": [pre]}
    assert cache.resolve({}, idx, "k", False)["status"] == "missing"
    idx = {"starred": "v1", "takes": [full, pre], "auto_star": "v1"}
    r = cache.resolve({}, idx, "k", False)
    assert r["status"] == "cached" and r["match"]["id"] == "v1"
    assert cache.status_of({}, {"starred": None, "takes": [pre]}, "k2", False)[0] == "missing"
    assert not cache.manual_star({"starred": "v1", "takes": [full, pre]})  # an old index: the newest real take
    assert assemble.pick_take({"starred": "v1", "takes": [full, pre]}, "latest")["id"] == "v1"
    assert assemble.pick_take({"starred": None, "takes": [pre]}, "starred") is None


def test_store_never_stars_a_preview(store, harbor):
    sid = harbor["scenes"][0]["id"]
    for tid, extra in (("v1", {}), ("v2", {"preview": True})):
        d = store.take_dir(sid, tid)
        os.makedirs(d, exist_ok=True)
        rel = store.rel_output(os.path.join(d, "x.mp4"))
        with open(store.output_path(rel), "wb") as f:
            f.write(b"x")
        store.add_take(sid, dict({"id": tid, "created": int(tid[1:]), "files": {"video": rel}}, **extra), star=not extra)
    try:
        store.star(sid, "v2")
        raise AssertionError("a preview was starred")
    except ValueError as e:
        assert "preview" in str(e)
    store.delete_take(sid, "v1")
    assert store.read_index(sid)["starred"] is None  # the preview does not take the star
    import json
    for tid in ("v1", "v2"):
        if os.path.isdir(store.take_dir(sid, tid)):
            take = next((t for t in store.read_index(sid)["takes"] if t["id"] == tid), {"id": tid, "created": 1})
            with open(os.path.join(store.take_dir(sid, tid), "meta.json"), "w") as f:
                json.dump(dict(take, files={"video": store.rel_output(os.path.join(store.take_dir(sid, tid), "x.mp4"))}), f)
    assert store.index_from_takes(sid)["starred"] is None
