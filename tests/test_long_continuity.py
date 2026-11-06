"""Long-scene continuity (added 2026-11-05 v0.8.0, Agent V): Global -> Long scenes guide_vae, carry_audio,
seam_video_ref, handoff, pass_cache; their cache keys, the drift meter, the cut-seam hint and the pass stitch. Pure:
no ComfyUI needed (the render side is in tests/test_render_flow.py)."""

import copy

import numpy as np
import pytest

from reelwright import assemble, cache, merge, model
from reelwright.analysis import analyze, apply_long, drift_level, drift_metrics, long_settings, rekey


def _keys(r):
    return {sid: (sr["key"], list(sr["pass_keys"])) for sid, sr in r["scenes"].items()}


def _overlap(harbor):
    p = copy.deepcopy(harbor)
    p["global"]["long"]["seam_mode"] = "overlap"
    return p


def _v070_keys(r):
    """The keys v0.7.0 computed: cache.pass_key without the long extras, scene_key with the crossfade only."""
    out, crossfade = {}, int(r["project"]["global"]["long"]["crossfade_frames"])
    for sid, sr in r["scenes"].items():
        up_key = sr["_prev_key"]
        keys, prev = [], None
        for b, x in zip(sr["builds"], sr["plan"]["passes"]):
            prev = cache.pass_key(sr["_fp"], b, x, r["_asset_digest"], up_key, prev, sr["upstream_take"])
            keys.append(prev)
        out[sid] = (cache.scene_key(sr["plan"], keys, crossfade), keys)
    return out


# ---- settings -----------------------------------------------------------------------------------------------------

def test_defaults_and_normalisation():
    g = model.default_global()["long"]
    assert (g["guide_vae"], g["carry_audio"], g["seam_video_ref"], g["handoff"], g["pass_cache"]) == \
        ("", True, True, "pixels", "near_lossless")
    bad = model.normalize_global({"long": {"guide_vae": 5, "carry_audio": "no", "seam_video_ref": 0,
                                           "handoff": "LATENT", "pass_cache": "raw"}})["long"]
    assert bad["guide_vae"] == "5" and bad["carry_audio"] is True and bad["seam_video_ref"] is False
    assert bad["handoff"] == "pixels" and bad["pass_cache"] == "near_lossless"
    ok = model.normalize_global({"long": {"handoff": "latent", "pass_cache": "lossless", "carry_audio": False}})["long"]
    assert (ok["handoff"], ok["pass_cache"], ok["carry_audio"]) == ("latent", "lossless", False)
    # a project dict that skipped normalisation still reads as the defaults
    assert long_settings({"global": {"long": {"max_pass_frames": 362}}})["handoff"] == "pixels"


# ---- cache keys ---------------------------------------------------------------------------------------------------

def test_defaults_keep_every_v070_key(harbor, store):
    for p in (harbor, _overlap(harbor)):
        r = analyze(p, store)
        assert _keys(r) == _v070_keys(r)
        # a project saved before v0.8.0 (no long-scene keys) gives the same keys
        old = copy.deepcopy(p)
        for k in ("guide_vae", "carry_audio", "seam_video_ref", "handoff", "pass_cache"):
            old["global"]["long"].pop(k, None)
        assert _keys(analyze(old, store)) == _keys(r)


def test_pass_cache_changes_no_key(harbor, store):
    p = _overlap(harbor)
    before = _keys(analyze(p, store))
    p["global"]["long"]["pass_cache"] = "lossless"
    assert _keys(analyze(p, store)) == before


def test_guide_vae_changes_the_passes_that_encode(harbor, store):
    p = _overlap(harbor)
    r0 = analyze(p, store)
    p["global"]["long"]["guide_vae"] = p["global"]["models"]["video_vae"]  # the same file: nothing changes
    assert _keys(analyze(p, store)) == _keys(r0)
    p["global"]["long"]["guide_vae"] = "minimax_h3_video_vae_bf16.safetensors"
    r1 = analyze(p, store)
    for sid, sr in r1["scenes"].items():
        b = sr["builds"][0]
        assert (sr["pass_keys"][0] != r0["scenes"][sid]["pass_keys"][0]) == bool(b["images"] or b["videos"] or
                                                                                 b["guides"]), sid
    assert all(a != b for a, b in zip(r1["scenes"]["s_long"]["pass_keys"], r0["scenes"]["s_long"]["pass_keys"]))
    assert r1["scenes"]["s_long"]["key"] != r0["scenes"]["s_long"]["key"]
    # a scene whose passes encode nothing keeps its key
    q = copy.deepcopy(harbor)
    q["scenes"] = [q["scenes"][0]]
    k0 = analyze(q, store)["scenes"]["s_one"]["key"]
    assert not analyze(q, store)["scenes"]["s_one"]["builds"][0]["guides"]
    q["global"]["long"]["guide_vae"] = "minimax_h3_video_vae_bf16.safetensors"
    r = analyze(q, store)["scenes"]["s_one"]
    b = r["builds"][0]
    assert (r["key"] != k0) == bool(b["images"] or b["videos"] or b["guides"])


def test_carry_audio_off_changes_overlap_passes_and_the_stitch(harbor, store):
    p = _overlap(harbor)
    r0 = analyze(p, store)
    p["global"]["long"]["carry_audio"] = False
    r1 = analyze(p, store)
    long0, long1 = r0["scenes"]["s_long"], r1["scenes"]["s_long"]
    seams = [x["seam_before"] for x in long1["plan"]["passes"]]
    assert seams[0] == "none" and set(seams[1:]) == {"overlap"}
    assert long1["pass_keys"][0] == long0["pass_keys"][0]  # pass 1 continues the scene before: its sound is kept
    assert all(a != b for a, b in zip(long1["pass_keys"][1:], long0["pass_keys"][1:]))
    assert long1["key"] != long0["key"]
    for sid in ("s_one", "s_short"):
        assert r1["scenes"][sid]["key"] == r0["scenes"][sid]["key"]
    # the guides: the pass before's end is picture only; the tail of the scene before keeps its sound
    for n, b in enumerate(long1["builds"]):
        for g in b["guides"]:
            if g["source"] == "prev_pass_tail":
                assert g["audio"] is False
            elif g["source"] == "prev_scene_tail":
                assert g["audio"] is True
    # a long scene joined at shot cuts only: nothing to change
    q = copy.deepcopy(harbor)
    k = analyze(q, store)["scenes"]["s_long"]["key"]
    q["global"]["long"]["carry_audio"] = False
    assert analyze(q, store)["scenes"]["s_long"]["key"] == k


def test_apply_long_leaves_builds_alone_at_the_default():
    builds = {"s": [{"guides": [{"source": "prev_pass_tail", "audio": True}]}]}
    p = {"global": {"long": {"carry_audio": True}}}
    assert apply_long(p, copy.deepcopy(builds)) == builds
    p["global"]["long"]["carry_audio"] = False
    assert apply_long(p, copy.deepcopy(builds))["s"][0]["guides"][0]["audio"] is False


def test_handoff_latent_changes_overlap_passes_only(harbor, store):
    p = _overlap(harbor)
    r0 = analyze(p, store)
    p["global"]["long"]["handoff"] = "latent"
    r1 = analyze(p, store)
    sr0, sr1 = r0["scenes"]["s_long"], r1["scenes"]["s_long"]
    for n, b in enumerate(sr1["builds"]):
        chained = any(g["source"] == "prev_pass_tail" for g in b["guides"])
        assert (sr1["pass_keys"][n] != sr0["pass_keys"][n]) == chained
    assert r1["scenes"]["s_one"]["key"] == r0["scenes"]["s_one"]["key"]


def test_seam_video_ref_off_drops_the_clip_after_overlap_seams(harbor, store):
    p = _overlap(harbor)
    r0 = analyze(p, store)
    assert all(b["videos"] and b["videos"][0].get("continuation") for b in r0["scenes"]["s_long"]["builds"][1:])
    p["global"]["long"]["seam_video_ref"] = False
    r1 = analyze(p, store)
    sr0, sr1 = r0["scenes"]["s_long"], r1["scenes"]["s_long"]
    assert sr1["builds"][0]["videos"][0].get("continuation")  # pass 1: the tail clip of the scene before stays
    for b in sr1["builds"][1:]:
        assert not any(v.get("continuation") for v in b["videos"])
        assert any(g["source"] == "prev_pass_tail" and g["frames"] == 39 for g in b["guides"])  # still anchored
    assert sr1["pass_keys"][0] == sr0["pass_keys"][0]
    assert all(a != b for a, b in zip(sr1["pass_keys"][1:], sr0["pass_keys"][1:]))
    # the reference budget agrees (model.pass_continuation)
    x2 = sr1["plan"]["passes"][1]
    assert model.pass_continuation(r1["project"], 1, x2) == ""
    assert model.pass_continuation(r0["project"], 1, x2) == "video"
    # with the continuation not named at all, the switch changes nothing
    q = _overlap(harbor)
    q["global"]["continuity"]["name_continuation"] = False
    k = _keys(analyze(q, store))
    q["global"]["long"]["seam_video_ref"] = False
    assert _keys(analyze(q, store)) == k


def test_rekey_matches_analysis_with_every_switch(harbor, store):
    p = _overlap(harbor)
    p["global"]["long"].update(guide_vae="full.safetensors", carry_audio=False, handoff="latent",
                               seam_video_ref=False, pass_cache="lossless")
    r = analyze(p, store)
    store.add_take("s_one", {"id": "v1", "key": r["scenes"]["s_one"]["key"], "files": {}, "created": 1000,
                             "upstream": None})
    r2 = analyze(p, store)
    keys, key = rekey(r, "s_long", store.starred_take("s_one"))
    assert key == r2["scenes"]["s_long"]["key"] and keys == r2["scenes"]["s_long"]["pass_keys"]


# ---- drift meter --------------------------------------------------------------------------------------------------

def test_drift_metrics():
    rng = np.random.default_rng(3)
    guide = rng.random((39, 32, 48, 3), dtype=np.float32)
    same = drift_metrics(guide, guide.copy())
    assert same["anchor_diff"] == 0 and same["color_shift"] == 0 and same["sharpness"] == 1.0
    assert same["frames"] == 3 and same["level"] == "ok" and same["rgb_shift"] == [0.0, 0.0, 0.0]
    warm = np.clip(guide + np.array([0.04, 0.0, -0.04], dtype=np.float32), 0, 1)
    m = drift_metrics(guide, warm)
    assert m["rgb_shift"][0] > 8 and m["rgb_shift"][2] < -8 and m["color_shift"] > 10 and m["level"] == "bad"
    soft = (guide + np.roll(guide, 1, axis=1) + np.roll(guide, 1, axis=2) + np.roll(guide, (1, 1), axis=(1, 2))) / 4
    m = drift_metrics(guide, soft)
    assert m["sharpness"] < 0.5 and m["level"] == "bad"
    assert drift_metrics(guide[:1], guide[:1])["frames"] == 1           # a last-frame start: one frame
    assert drift_metrics(np.zeros((5, 8, 8, 3)), np.zeros((5, 8, 8, 3)))["sharpness"] is None  # flat guide
    assert drift_metrics(guide[:0], guide[:0]) is None


def test_drift_levels():
    assert drift_level({"anchor_diff": 3, "color_shift": 1, "sharpness": 0.95}) == "ok"
    assert drift_level({"anchor_diff": 9, "color_shift": 1, "sharpness": 0.95}) == "warn"
    assert drift_level({"anchor_diff": 3, "color_shift": 1, "sharpness": 0.7}) == "warn"
    assert drift_level({"anchor_diff": 3, "color_shift": 12, "sharpness": 1.0}) == "bad"
    assert drift_level({"anchor_diff": 3, "color_shift": 1, "sharpness": None}) == "ok"


# ---- cut-seam hint (validate) --------------------------------------------------------------------------------------

def test_long_scene_without_shot_cuts_gets_a_cut_seam_hint(harbor, store):
    p = copy.deepcopy(harbor)
    p["scenes"][1]["shots"] = [p["scenes"][1]["shots"][0]]  # one shot at 0 s: no cuts
    r = analyze(p, store)
    hints = [x["message"] for x in r["issues"] if x.get("scene_id") == "s_long" and "overlap seam" in x["message"]]
    assert len(hints) == 1 and "Add shot cuts up to 2 s before a seam" in hints[0]
    seams = [x for x in r["scenes"]["s_long"]["plan"]["passes"] if x["seam_before"] == "overlap"]
    assert "{:.2f} s".format(seams[0]["start"] + seams[0]["overlap_frames"] / 24) in hints[0]
    assert next(x for x in r["issues"] if x["message"] == hints[0])["level"] == "info"
    p["global"]["long"]["seam_mode"] = "overlap"
    hint = [x["message"] for x in analyze(p, store)["issues"] if "overlap seam" in x["message"]][0]
    assert "Seams to Auto or Cuts" in hint
    # with shot cuts (the fixture's four shots) there is no hint, even with overlap seams
    q = _overlap(harbor)
    assert not [x for x in analyze(q, store)["issues"] if "overlap seam" in x["message"]]


# ---- the pass stitch ----------------------------------------------------------------------------------------------

def _plan():
    return {"passes": [
        {"index": 1, "keep_in": 0.0, "keep_out": 362 / 24, "seam_before": "none", "overlap_frames": 0},
        {"index": 2, "keep_in": 0.0, "keep_out": 300 / 24, "seam_before": "overlap", "overlap_frames": 39},
        {"index": 3, "keep_in": 0.0, "keep_out": 200 / 24, "seam_before": "cut", "overlap_frames": 0}]}


def test_pass_segments_lead_the_sound_without_carry_audio():
    files = ["a.mp4", "b.mp4", "c.mp4"]
    on = assemble.pass_segments(_plan(), files, 12)
    off = assemble.pass_segments(_plan(), files, 12, carry_audio=False)
    assert on == assemble.pass_segments(_plan(), files, 12, True)
    assert "audio_lead_frames" not in on[1] and off[1]["audio_lead_frames"] == 39 - 12
    assert [dict(s, audio_lead_frames=None) for s in off] != on  # only that key differs
    assert [{k: v for k, v in s.items() if k != "audio_lead_frames"} for s in off] == on
    assert "audio_lead_frames" not in off[2]  # a shot cut
    zero = assemble.pass_segments(_plan(), files, 0, carry_audio=False)  # no crossfade: a plain cut, sound led 39
    assert zero[1]["join"] == "cut" and zero[1]["audio_lead_frames"] == 39


def _graph(segs):
    args, _, total = merge.build_command(segs, "/tmp/out.mp4", 64, 32, audio_fade_frames=0, ffmpeg="ffmpeg")
    return args[args.index("-filter_complex") + 1], args, total


def test_build_command_audio_lead():
    files = ["a.mp4", "b.mp4", "c.mp4"]
    on = assemble.pass_segments(_plan(), files, 12)
    off = assemble.pass_segments(_plan(), files, 12, carry_audio=False)
    g_on, args_on, t_on = _graph(on)
    g_off, _, t_off = _graph(off)
    # the picture is the same; the sound of pass 2 starts at its first frame and crossfades over the whole overlap
    pic = lambda g: [x for x in g.split(";") if "[v" in x.split("]")[0] or x.startswith("[v")]  # noqa: E731
    assert [x for x in g_on.split(";") if ":v]" in x or "xfade=" in x or "concat=n=2:v=1" in x] == \
        [x for x in g_off.split(";") if ":v]" in x or "xfade=" in x or "concat=n=2:v=1" in x]
    assert pic(g_on) == pic(g_off)
    assert "acrossfade=d=0.5[ac1]" in g_on and "acrossfade=d=1.625[ac1]" in g_off
    assert "[1:a]atrim=start=1.125:" in g_on and "[1:a]atrim=start=0:" in g_off
    assert t_on == t_off and merge.frame_timeline(on) == merge.frame_timeline(off)
    # a plain cut (no crossfade) whose sound has a lead: the picture cuts, the sound crossfades over the lead
    zero = assemble.pass_segments(_plan(), files, 0, carry_audio=False)
    g0, _, _ = _graph(zero)
    assert "[v0][v1]concat=n=2:v=1:a=0" in g0 and "[a0][a1]acrossfade=d=1.625[ac1]" in g0
    assert "[ac1][a2]concat=n=2:v=0:a=1[ac2]" in g0  # the shot cut after it is a plain cut
    # with nothing to lead, the command is exactly what it was
    assert _graph(assemble.pass_segments(_plan(), files, 12))[1] == args_on


def test_audio_lead_needs_a_file_and_an_in_point():
    assert merge._audio_lead({"path": "a", "in": 1.0, "audio_lead_frames": 30}, 1) == 24  # at most its in-point
    assert merge._audio_lead({"path": "a", "in": 1.0, "audio_lead_frames": 30}, 0) == 0
    assert merge._audio_lead({"path": None, "in": 1.0, "audio_lead_frames": 5}, 1) == 0
    assert merge._audio_lead({"path": "a", "in": 1.0, "audio_lead_frames": 5, "mute": True}, 1) == 0
    assert merge._audio_lead({"path": "a", "in": 1.0, "audio_lead_frames": "x"}, 1) == 0
