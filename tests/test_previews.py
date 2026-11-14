"""Previews. Sencer: "Add an option to render only minimum frames that MMH3 supports (first seconds. so we can see if
scene is set up correctly before waiting for a long render)." (v0.23.0), then "make the length configurable. 39 frames
works when I try. 5 seconds is too long, thats why i asked for a preview" (v0.23.1).

A preview renders the start of a scene, Global → Preview length frames (17k+5, 5 to 362, 39 unless set), as a take
marked "preview": never starred, merged or continued from, and it does not make the scene count as rendered.
"""

import os

from reelwright import assemble, cache, model
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


def test_a_preview_is_pass_one_cut_to_the_preview_length():
    p = long_scene()
    s = p["scenes"][0]
    full = plan_scene(p, s, 0)
    v = preview_plan(full, 124)
    assert len(full["passes"]) == 2 and v["kind"] == "single" and v["frames"] == 124 and v["preview"]
    (x,) = v["passes"]
    assert (x["gen_frames"], x["keep_in_frames"], x["keep_out_frames"], x["end"]) == (124, 0, 124, 124 / 24)
    assert x["seed"] == full["passes"][0]["seed"]  # pass 1's seed
    assert [sh["id"] for sh in x["shots"]] == ["h1", "h2", "h3"]  # 5.12 s is frame 123 (the last); 5.16 s is 124
    assert [d["id"] for d in x["dialogue"]] == ["d1"]
    assert [k["ref"] for k in x["keyframes"]] == ["r_kf"]  # the one at 15 s is past the preview
    assert len(full["passes"][0]["shots"]) == 4 and full["frames"] == 480  # the full plan is untouched
    # 39 frames (1.63 s): the first shot, the line at 1 s; the keyframe at 2 s is past it
    v = preview_plan(full, 39)
    (x,) = v["passes"]
    assert (v["frames"], v["generated_frames"], x["gen_frames"], x["keep_out_frames"]) == (39, 39, 39, 39)
    assert [sh["id"] for sh in x["shots"]] == ["h1"] and [d["id"] for d in x["dialogue"]] == ["d1"] and not x["keyframes"]
    # a scene of one pass: its last-frame guide is left out (it would pin the preview's end)
    s["duration"] = 10.0
    one = plan_scene(p, s, 0)
    assert one["passes"][0]["last_frame"] and preview_plan(one, 39)["passes"][0]["last_frame"] == []
    # one the preview covers: rendered whole (its plan as it is)
    s["duration"] = 1.5
    assert preview_plan(plan_scene(p, s, 0), 39) == plan_scene(p, s, 0)
    assert model.PREVIEW_FRAMES == 39 == model.preview_frames(p)


def test_a_preview_after_a_tail_clip_and_of_a_trimmed_short_scene():
    p = model.default_project("Previews")
    p["scenes"][0].update(duration=8.0)
    p["scenes"].append(model.default_scene(p, duration=12.0, start={"mode": "tail", "overlap_frames": 39},
                                           shots=[{"id": "t1", "t": 0, "text": "a"}, {"id": "t2", "t": 2.5, "text": "b"},
                                                  {"id": "t3", "t": 4.0, "text": "c"}]))
    p["scenes"].append(model.default_scene(p, duration=3.0, start={"mode": "fresh"}, trim={"keep": "end", "in": 0.0},
                                           dialogue=[{"id": "e1", "speaker": "", "t": 0.5, "text": "x"},
                                                     {"id": "e2", "speaker": "", "t": 2.5, "text": "y"}]))
    p = model.normalize_project(p)
    tail = plan_scene(p, p["scenes"][1], 1)
    assert tail["start_mode"] == "tail" and tail["passes"][0]["overlap_frames"] == 39
    v = preview_plan(tail, 39)
    (x,) = v["passes"]
    # the 39 tail frames repeat scene 1, so 39 new ones follow: 78 frames, made (and kept) as 90 (17k+5)
    assert (x["gen_frames"], x["keep_in_frames"], x["keep_out_frames"], v["frames"]) == (90, 0, 90, 90)
    assert [sh["id"] for sh in x["shots"]] == ["t1", "t2"] and x["overlap_frames"] == 39
    # a 3 s scene keeps the end of a 124-frame pass (frames 52 to 124): its preview starts there too
    short = plan_scene(p, p["scenes"][2], 2)
    assert short["kind"] == "short" and short["passes"][0]["keep_in_frames"] == 52
    v = preview_plan(short, 22)
    (x,) = v["passes"]
    assert v["kind"] == "short" and (x["gen_frames"], x["keep_in_frames"], x["keep_out_frames"], v["frames"]) == (90, 52, 90, 38)
    assert [d["id"] for d in x["dialogue"]] == ["e1"]  # 0.5 s is frame 64 of what H3 makes; 2.5 s is past it
    assert preview_plan(short, 39)["frames"] == 55 and preview_plan(short, 56) == short  # 56 from frame 52 need all 124


def test_preview_length_setting():
    g = model.normalize_global({})
    assert g["preview"] == {"frames": 39}
    for raw, want in (("40", 56), (999, 362), (2, 5), (None, 39), ("abc", 39), (124, 124), (39.4, 39)):
        assert model.normalize_global({"preview": {"frames": raw}})["preview"]["frames"] == want, raw
    assert model.normalize_global({"preview": 5})["preview"] == {"frames": 39}


def test_analysis_of_a_preview(harbor, store):
    # the long walk (32 s, 3 passes, a 39-frame tail start) names @P3, a keyframe at 25 s: past the preview, in words
    res = analyze(harbor, store, previews=["s_long"])["scenes"]["s_long"]
    assert res["plan"]["frames"] == 90 and res["plan"]["preview"] and len(res["prompts"]) == 1 and res["status"] != "error"
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
