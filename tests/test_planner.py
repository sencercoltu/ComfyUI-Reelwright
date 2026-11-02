from reelwright import spec
from reelwright.model import default_project, normalize_project
from reelwright.planner import plan_scene


def _plan(duration, shots=(), mode="fresh", index=1, **long_cfg):
    p = default_project()
    p["global"]["long"].update(long_cfg)
    p["scenes"].append({"id": "s_x", "duration": duration, "start": {"mode": mode, "overlap_frames": 39},
                        "shots": [{"t": t} for t in shots]})
    p = normalize_project(p)
    return plan_scene(p, p["scenes"][index], index)


def covered(plan):
    """Frames of the scene each pass contributes once overlaps are removed."""
    total = 0
    for x in plan["passes"]:
        total += (x["keep_out_frames"] - x["keep_in_frames"]) - (x["overlap_frames"] if x["seam_before"] == "overlap" else 0)
    return total


def test_single_pass_snaps_up_and_trims():
    plan = _plan(8.0)
    assert plan["kind"] == "single"
    (x,) = plan["passes"]
    assert x["gen_frames"] == 192 and x["keep_out_frames"] == 192
    plan = _plan(7.0)
    assert plan["passes"][0]["gen_frames"] == 175 and plan["passes"][0]["keep_out_frames"] == 168


def test_short_scene_keeps_a_window():
    p = default_project()
    p["scenes"][0].update(duration=2.5, trim={"keep": "middle", "in": 0})
    plan = plan_scene(normalize_project(p), normalize_project(p)["scenes"][0], 0)
    (x,) = plan["passes"]
    assert plan["kind"] == "short"
    assert x["gen_frames"] == spec.MIN_PASS_FRAMES
    assert x["keep_out_frames"] - x["keep_in_frames"] == 60
    assert x["keep_in_frames"] == (124 - 60) // 2


def test_long_scene_prefers_cuts_and_covers_every_frame():
    plan = _plan(32.0, shots=(0, 6, 14.375, 22))
    seams = [x["seam_before"] for x in plan["passes"]]
    assert seams[0] == "none" and "cut" in seams
    for x in plan["passes"]:
        assert spec.MIN_PASS_FRAMES <= x["gen_frames"] <= spec.MAX_PASS_FRAMES
        assert x["gen_frames"] % 17 == 5
        assert x["keep_out_frames"] <= x["gen_frames"]
    assert covered(plan) == 768


def test_long_scene_without_cuts_uses_guided_overlaps():
    plan = _plan(45.0)
    assert plan["kind"] == "long"
    assert all(x["seam_before"] == "overlap" for x in plan["passes"][1:])
    assert all(x["overlap_frames"] == 39 for x in plan["passes"][1:])
    assert covered(plan) == 1080


def test_cut_only_mode_and_overlap_only_mode():
    cuts = _plan(32.0, shots=(0, 6, 14.375, 22), seam_mode="cuts")
    assert [x["seam_before"] for x in cuts["passes"]].count("cut") >= 1
    ov = _plan(32.0, shots=(0, 6, 14.375, 22), seam_mode="overlap")
    assert all(x["seam_before"] == "overlap" for x in ov["passes"][1:])
    assert covered(cuts) == covered(ov) == 768


def test_tail_start_overlap_is_part_of_the_scene():
    plan = _plan(10.0, mode="tail")
    assert plan["passes"][0]["overlap_frames"] == 39


def test_content_is_rebased_per_pass(harbor):
    p = harbor
    plan = plan_scene(p, p["scenes"][1], 1)
    shot_times = []
    for x in plan["passes"]:
        for sh in x["shots"]:
            assert 0 <= sh["t"] <= x["gen_frames"] / spec.FPS
            shot_times.append(round(x["start"] + sh["t"], 3))
    assert 22.0 in shot_times
    lines = [(x["index"], d["t"]) for x in plan["passes"] for d in x["dialogue"]]
    assert len(lines) == 1  # the 16 s line appears once
    keyframes = [k for x in plan["passes"] for k in x["keyframes"]]
    assert len(keyframes) == 1


def test_short_scene_shifts_content_into_the_window(harbor):
    p = harbor
    p["scenes"][2]["shots"] = [{"id": "h", "t": 0.5, "camera": "Macro", "text": "hand grips the handle"}]
    plan = plan_scene(p, p["scenes"][2], 2)
    x = plan["passes"][0]
    assert abs(x["keep_in"] - 1.208) < 0.01
    assert abs(x["shots"][0]["t"] - (x["keep_in"] + 0.5)) < 0.05
