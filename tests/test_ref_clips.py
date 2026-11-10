"""Clips of video and audio references (Sencer: "when using video or audio references, allow to
select from-to timestamps/frames of source video. we should be able to use the same video/audio asset in a single scene
multiple times, with different start/end timestamps/durations, with or without audio (for videos)").

Each reference has From / To (r["in"], r["out"]): the clip it sends. A trimmed clip carries in / out / seconds in the
build and its range in the cache key; references that are not trimmed keep their builds and keys. @V1 names the first
reference of V1 in a scene, @V1.2 the second and so on.
"""

import copy

from reelwright import cache, llm, model, prompt, spec, validate
from reelwright.planner import plan_scene


def project():
    p = model.default_project("Clips")
    p["assets"] = [
        {"id": "a_walk", "kind": "video", "code": "V1", "name": "walk", "file": "x/walk.mp4", "duration": 20.0,
         "category": "motion"},
        {"id": "a_cam", "kind": "video", "code": "V2", "name": "dolly", "file": "x/dolly.mp4", "duration": 12.0,
         "category": "camera"},
        {"id": "a_rain", "kind": "audio", "code": "A1", "name": "rain", "file": "x/rain.wav", "duration": 30.0,
         "category": "ambience"},
        {"id": "a_voice", "kind": "audio", "code": "A2", "name": "voice", "file": "x/voice.wav", "duration": 6.0},
    ]
    p["cast"] = [{"id": "c_mara", "name": "Mara", "speaker": "S1", "anchors": [], "voice": "a_voice"}]
    s = p["scenes"][0]
    s.update({"id": "s_one", "duration": 8.0, "cast": [{"id": "c_mara"}],
              "dialogue": [{"id": "d_1", "speaker": "c_mara", "t": 1.0, "text": "Hello."}],
              "shots": [{"id": "h_1", "t": 0, "text": "@V1 walks like @V1.2; the camera moves as @V2.2; rain like @A1.2."}]})
    s["refs"] = [
        {"id": "r_walk", "asset": "a_walk", "role": "reference", "in": 2.0, "out": 6.0},
        {"id": "r_walk2", "asset": "a_walk", "role": "reference", "in": 10.0, "out": 14.5, "soundtrack": True},
        {"id": "r_cam", "asset": "a_cam", "role": "reference"},
        {"id": "r_cam2", "asset": "a_cam", "role": "reference", "in": 1.0, "out": 4.0, "soundtrack": True},
        {"id": "r_rain", "asset": "a_rain", "role": "reference", "in": 3.0, "out": 7.0},
        {"id": "r_rain2", "asset": "a_rain", "role": "reference", "in": 20.0},
    ]
    return model.normalize_project(p)


def build(p, sid="s_one", k=0):
    i = next(n for n, s in enumerate(p["scenes"]) if s["id"] == sid)
    s = p["scenes"][i]
    plan = plan_scene(p, s, i)
    return prompt.build_pass(p, s, i, plan, plan["passes"][k], prompt.prepare(p))


def test_normalize_snaps_from_and_to_to_frames():
    p = model.default_project("n")
    p["scenes"][0]["refs"] = [{"id": "r1", "asset": "a", "in": "1.02", "out": "3.51"},
                              {"id": "r2", "asset": "a", "in": -2, "out": -1},
                              {"id": "r3", "asset": "a"},
                              {"id": "r4", "asset": "a", "in": "x", "out": True}]
    refs = model.normalize_project(p)["scenes"][0]["refs"]
    assert [(r["in"], r["out"]) for r in refs] == [(1.0, 3.5), (0.0, None), (0.0, None), (0.0, None)]
    assert model.snap_frame(1.0208333) == 1.0 and model.snap_frame(1.5 / 24) == 2 / 24


def test_clip_lengths_and_tokens():
    p = project()
    s = p["scenes"][0]
    idx = model.project_index(p)
    clip = {r["id"]: model.ref_clip(r, idx["assets"][r["asset"]]) for r in s["refs"]}
    assert clip["r_walk"] == {"start": 2.0, "end": 6.0, "seconds": 4.0}
    assert clip["r_cam"]["seconds"] == 12.0 and clip["r_rain2"] == {"start": 20.0, "end": 30.0, "seconds": 10.0}
    assert model.ref_tokens(p, s) == {"r_walk": "@V1", "r_walk2": "@V1.2", "r_cam": "@V2", "r_cam2": "@V2.2",
                                      "r_rain": "@A1", "r_rain2": "@A1.2"}
    assert not model.ref_trimmed(s["refs"][2]) and model.ref_trimmed(s["refs"][5])


def test_each_reference_sends_its_own_clip_and_tag():
    b = build(project())
    vids = [(v["ref"], v.get("in"), v.get("out"), v.get("seconds"), v["soundtrack"]) for v in b["videos"]]
    assert vids == [("r_walk", 2.0, 6.0, 4.0, False), ("r_walk2", 10.0, 14.5, 4.5, True),
                    ("r_cam", None, None, None, False), ("r_cam2", 1.0, 4.0, 3.0, True)]
    auds = [(a.get("ref"), a.get("cast"), a.get("in"), a.get("seconds")) for a in b["audios"]]
    assert auds == [(None, "c_mara", None, None), ("r_rain", None, 3.0, 4.0), ("r_rain2", None, 20.0, 10.0)]
    # each motion clip is a subject of its own (Mara is <Subject 1>); @V1 is the first, @V1.2 the second
    assert b["tag_map"]["@V1"] == "<Subject 2>" and b["tag_map"]["@V1.2"] == "<Subject 3>"
    assert b["tag_map"]["@V2"] == "<Video 3>" and b["tag_map"]["@V2.2"] == "<Video 4>"
    assert b["tag_map"]["@A1"] == "<Audio 4>" and b["tag_map"]["@A1.2"] == "<Audio 5>"
    assert "[Shot 1] <Subject 2> walks like <Subject 3>; the camera moves as <Video 4>; rain like <Audio 5>." in b["prompt"]
    assert "<Audio 4> is the ambience reference." in b["prompt"] and "<Audio 5> is the ambience reference." in b["prompt"]
    assert "<Audio 1> is the synchronized audio track of <Video 2>." in b["prompt"]
    assert not b["unknown"]


def test_unknown_numbers_and_pictures_are_written_in_words():
    p = project()
    p["scenes"][0]["shots"][0]["text"] = "like @V1.7 and @A1.3"
    b = build(p)
    msgs = [x["message"] for x in b["issues"]]
    assert any("@V1.7: this scene has 2 references of V1" in m for m in msgs)
    assert "[Shot 1] Like the walk and the rain." in b["prompt"]


def test_a_repeated_audio_clip_or_the_voice_file_is_sent_once():
    p = project()
    s = p["scenes"][0]
    s["refs"].append({"id": "r_rain3", "asset": "a_rain", "role": "reference", "in": 3.0, "out": 7.0})  # = r_rain
    s["refs"].append({"id": "r_voice", "asset": "a_voice", "role": "reference"})  # = the voice sample
    s["refs"].append({"id": "r_voice_part", "asset": "a_voice", "role": "reference", "in": 1.0, "out": 3.0})
    s["shots"][0]["text"] = "@A1.3 and @A2.2"
    p = model.normalize_project(p)
    b = build(p)
    assert [a.get("ref") for a in b["audios"]] == [None, "r_rain", "r_rain2", "r_voice_part"]
    # @A1.3 repeats @A1's clip; @A2 (the whole voice file) is the voice sample; @A2.2 is a part of it, a clip of its own
    assert b["tag_map"]["@A1.3"] == b["tag_map"]["@A1"] == "<Audio 4>" and b["tag_map"]["@A2"] == "<Audio 3>"
    assert b["tag_map"]["@A2.2"] == "<Audio 6>"
    counts = model.scene_media_counts(p, p["scenes"][0])
    assert counts["audio"] == len(b["audios"]) + 2  # two video clips with their sound
    assert counts["videos"] == 4 and counts["video_seconds"] == 4.0 + 4.5 + 12.0 + 3.0
    assert counts["audio_seconds"] == 6.0 + 4.0 + 10.0 + 2.0 + 4.5 + 3.0


def test_untrimmed_references_keep_their_build_and_key():
    p = project()
    s = p["scenes"][0]
    for r in s["refs"]:
        r["in"], r["out"] = 0.0, None
    b = build(p)
    assert all("in" not in v and "seconds" not in v for v in b["videos"] + b["audios"])
    keyed = cache.pass_key({}, b, {"gen_frames": 124, "seed": 1}, lambda a: "d" + a, None, None)
    v0 = copy.deepcopy(b)
    v0["videos"][0].update({"in": 0.0, "out": 20.0, "seconds": 20.0})
    assert cache.pass_key({}, v0, {"gen_frames": 124, "seed": 1}, lambda a: "d" + a, None, None) != keyed


def test_the_range_is_in_the_cache_key():
    p = project()
    b = build(p)
    key = cache.pass_key({}, b, {"gen_frames": 124, "seed": 1}, lambda a: "d" + a, None, None)
    p["scenes"][0]["refs"][0]["out"] = 6.5
    b2 = build(model.normalize_project(p))
    assert cache.pass_key({}, b2, {"gen_frames": 124, "seed": 1}, lambda a: "d" + a, None, None) != key
    p["scenes"][0]["refs"][4]["in"] = 3.5  # an audio clip
    b3 = build(model.normalize_project(p))
    assert cache.pass_key({}, b3, {"gen_frames": 124, "seed": 1}, lambda a: "d" + a, None, None) != \
        cache.pass_key({}, b2, {"gen_frames": 124, "seed": 1}, lambda a: "d" + a, None, None)


def test_lint_checks_the_range():
    p = project()
    s = p["scenes"][0]
    s["refs"][0].update(out=1.0)          # ends before it starts
    s["refs"][1].update(**{"in": 21.0, "out": None})  # starts after the end
    s["refs"][4].update(out=40.0)         # ends after the end: sent up to its end
    p = model.normalize_project(p)
    plans = {s["id"]: plan_scene(p, s, i) for i, s in enumerate(p["scenes"])}
    builds = {s["id"]: [prompt.build_pass(p, s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
              for i, s in enumerate(p["scenes"])}
    msgs = [(i["level"], i["message"]) for i in validate.lint_project(p, plans, builds, lambda a: True)]
    assert any(lv == "error" and "@V1 ends at 00:01.000, before it starts" in m for lv, m in msgs)
    assert any(lv == "error" and "@V1.2 starts at 00:21.000 but V1 is only 00:20.000 long" in m for lv, m in msgs)
    assert any(lv == "info" and "@A1 ends at 00:40.000, after the end of A1" in m for lv, m in msgs)


def test_the_rewriter_is_told_about_each_clip():
    text = llm.scene_context(project(), project()["scenes"][0])
    assert "@V1.2 walk (video, reference, the part from 00:10.000 to 00:14.500 of the file, with its own sound)" in text
    assert "@V2 dolly (video, reference, picture only)" in text
    assert "@A1.2 rain (audio, reference, the part from 00:20.000 to 00:30.000 of the file)" in text


def test_editor_and_backend_tags():
    assert prompt.NTH_CLIP.fullmatch("V1.2") and prompt.NTH_CLIP.fullmatch("a12.3") and not prompt.NTH_CLIP.fullmatch("V1")
    assert {"V1"} <= prompt.mentioned_codes("like @V1.2.")
    assert spec.REF_MEDIA_MAX_SECONDS == 15.0
