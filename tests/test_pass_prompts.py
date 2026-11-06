"""Per-pass prompt sections, dialogue length and H3's camera vocabulary (added 2026-11-05 v0.8.0, Agent P, contract P1).

- scene.prompt.passes: each pass's own six sections; a multi-pass scene never sends the scene summary (a pass gets its
  own, or one made from its shots); the other sections fall back to the scene's (shared);
- model.pass_texts maps stored pass texts to the current layout by time overlap; lints for another layout and for
  passes without a summary of their own;
- dialogue duration / model.dialogue_seconds and the lints for a line past a pass seam or the scene's end;
- the 20 official camera moves (camera_version 2 migration) and the shot fields camera_amp / camera_speed / framing.
"""

import copy

import pytest

from reelwright import model, prompt
from reelwright.model import normalize_project
from reelwright.planner import plan_project, plan_scene
from reelwright.prompt import build_pass
from reelwright.validate import lint_project

SECTIONS = ("subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape",
            "non_diegetic_music")


def _passes(p, i):
    plan = plan_scene(p, p["scenes"][i], i)
    ctx = prompt.prepare(p)
    return [build_pass(p, p["scenes"][i], i, plan, x, ctx=ctx) for x in plan["passes"]], plan


def _sections(text):
    out, key = {}, None
    for line in text.split("\n"):
        if line.endswith(":") and line[:-1] in SECTIONS:
            key = line[:-1]
            out[key] = []
        elif key is not None:
            out[key].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def _lint(p):
    plans = plan_project(p)
    ctx = prompt.prepare(p)
    builds = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x, ctx=ctx) for x in plans[s["id"]]["passes"]]
              for i, s in enumerate(p["scenes"])}
    return lint_project(p, plans, builds, lambda a: True, ctx=ctx)


def _own(p, i, texts):
    """Write {pass number: {section: text}} as scene i's pass texts, for its current layout."""
    s = p["scenes"][i]
    plan = plan_scene(p, s, i)
    s["prompt"]["passes"] = [{"start": x["start"], "end": x["end"],
                              "sections": dict(model.empty_sections(), **texts.get(x["index"], {}))}
                             for x in plan["passes"]]
    return p


# ---- multi-pass summaries -------------------------------------------------------------------------------------------

def test_the_scene_summary_never_reaches_a_pass_of_a_multi_pass_scene(harbor):
    builds, plan = _passes(harbor, 1)
    assert len(plan["passes"]) == 3
    summary = harbor["scenes"][1]["prompt"]["sections"]["summary"]  # "@Mara walks home as a storm builds, ..."
    for b in builds:
        assert "walks home" not in b["prompt"] and "storm builds" not in b["prompt"]
        assert not any("@P3" in x["tag"] or "@V1" in x["tag"] for x in b["issues"])  # its tags are not read
    assert summary.startswith("@Mara walks home")
    s1, s2, s3 = (_sections(b["prompt"])["summary"] for b in builds)
    # each pass: who is in it and its own shots (the first sentence of each shot), who speaks, its continuation
    assert s1 == "[reference generation + video continuation + audio reference] The target video shows <Subject 1> " \
                 "and unfolds over 2 shots. Mara leaves the pier. Along the seawall. It continues seamlessly from the " \
                 "final frames of <Video 1>, the end of the scene before."
    assert s2 == "[reference generation + audio reference] The target video shows <Subject 1> and unfolds over 1 " \
                 "shot. The rain starts. <Subject 1> speaks. <Audio 2> provides the voice timbre."
    assert s3.endswith("The target video shows <Subject 1> and unfolds over 1 shot. She reaches the door.")


def test_a_pass_summary_quotes_only_the_first_sentence_with_labels_and_skips_spoken_lines(harbor):
    s = harbor["scenes"][1]
    s["shots"][2]["text"] = "@Mara pulls her hood up. Rain <d>[English] lashes</d> the wall! More detail."
    builds, _ = _passes(harbor, 1)
    assert "unfolds over 1 shot. <Subject 1> pulls her hood up. <Subject 1> speaks." in builds[1]["prompt"]


def test_a_pass_uses_its_own_summary(harbor):
    _own(harbor, 1, {2: {"summary": "[reference generation] @Mara mutters as the rain starts."}})
    builds, _ = _passes(harbor, 1)
    sec = [_sections(b["prompt"]) for b in builds]
    assert sec[1]["summary"] == "[reference generation + audio reference] <Subject 1> mutters as the rain starts."
    assert sec[0]["summary"].startswith("[reference generation + video continuation + audio reference] The target "
                                        "video shows")  # passes without one still get theirs
    assert "mutters as the rain starts" not in builds[0]["prompt"] + builds[2]["prompt"]


def test_shared_sections_fall_back_to_the_scene_and_a_pass_may_have_its_own(harbor):
    s = harbor["scenes"][1]
    s["prompt"]["sections"].update(overall_soundscape="Rain on the seawall.", non_diegetic_music="Low strings.")
    _own(harbor, 1, {3: {"overall_soundscape": "A door creaks open."}})
    sec = [_sections(b["prompt"]) for b in _passes(harbor, 1)[0]]
    assert [x["overall_soundscape"] for x in sec] == ["Rain on the seawall.", "Rain on the seawall.",
                                                      "A door creaks open."]
    assert [x["non_diegetic_music"] for x in sec] == ["Low strings."] * 3


def test_a_pass_detailed_description_of_its_own_uses_its_own_shot_numbers(harbor):
    s = harbor["scenes"][1]
    s["prompt"]["sections"]["detailed_description"] = "Live action.\n[Shot 3] A medium shot: rain lashes the wall."
    _own(harbor, 1, {2: {"detailed_description": "Night, heavy rain.\n[Shot 1] A medium shot: @Mara pulls her hood up."}})
    b1, b2, b3 = _passes(harbor, 1)[0]
    d2 = _sections(b2["prompt"])["detailed_description"]
    assert d2.startswith("Night, heavy rain.\n[Shot 1] A medium shot: <Subject 1> pulls her hood up.")
    assert "<d>[English] Almost home.</d>" in d2  # the spoken line of the shot is kept
    assert "rain lashes the wall" not in d2 and "Live action." not in d2
    assert _sections(b1["prompt"])["detailed_description"].startswith("Live action.")  # the scene's, split per pass
    assert "rain lashes the wall" not in b1["prompt"]


def test_without_a_written_scene_summary_multi_pass_scenes_keep_the_automatic_one(harbor):
    harbor["scenes"][1]["prompt"]["sections"]["summary"] = ""
    builds, _ = _passes(harbor, 1)
    assert _sections(builds[1]["prompt"])["summary"] == "[reference generation + audio reference] The target video " \
        "shows <Subject 1> and unfolds over 1 shot. <Audio 2> provides the voice timbre."  # as v0.7.0


def test_a_pass_summary_is_made_even_without_automatic_subjects(harbor):
    harbor["scenes"][1]["prompt"]["auto"]["subjects"] = False
    builds, _ = _passes(harbor, 1)
    assert "The rain starts." in _sections(builds[1]["prompt"])["summary"]


def test_single_pass_scenes_use_pass_1_or_the_scene_summary(harbor):
    s = harbor["scenes"][0]
    s["prompt"]["sections"]["summary"] = "Boats rock in the harbor at dusk."
    (b,), _ = _passes(harbor, 0)
    assert _sections(b["prompt"])["summary"] == "Boats rock in the harbor at dusk."
    _own(harbor, 0, {1: {"summary": "Only the first lamps."}})
    (b,), _ = _passes(harbor, 0)
    assert _sections(b["prompt"])["summary"] == "Only the first lamps."


def test_raw_prompts_and_hand_edited_passes_ignore_pass_texts(harbor):
    _own(harbor, 1, {1: {"summary": "PASS TEXT"}, 2: {"summary": "PASS TEXT"}})
    s = harbor["scenes"][1]
    s["prompt"]["pass_prompts"] = {"2": "summary:\nHand edited.\n\ndetailed_description:\n[Shot 1] Rain."}
    builds, _ = _passes(harbor, 1)
    assert "PASS TEXT" in builds[0]["prompt"] and "PASS TEXT" not in builds[1]["prompt"]
    s["prompt"].update(mode="raw", raw="@Mara walks.")
    assert not any("PASS TEXT" in b["prompt"] for b in _passes(harbor, 1)[0])


def test_pass_sections_say_where_each_section_comes_from(harbor):
    s = harbor["scenes"][1]
    s["prompt"]["sections"]["overall_soundscape"] = "Rain."
    _own(harbor, 1, {2: {"summary": "own", "non_diegetic_music": "drums"}})
    plan = plan_scene(harbor, s, 1)
    one = model.pass_sections(harbor, s, plan, 1)
    two = model.pass_sections(harbor, s, plan, 2)
    assert one["source"] == {"subject_definitions": "scene", "summary": "auto", "retention_analysis": "scene",
                             "detailed_description": "split", "overall_soundscape": "scene",
                             "non_diegetic_music": "scene"}
    assert one["used"]["summary"] == "" and one["used"]["overall_soundscape"] == "Rain."
    assert two["source"]["summary"] == "pass" and two["used"]["summary"] == "own"
    assert two["source"]["non_diegetic_music"] == "pass" and two["own"]["non_diegetic_music"] == "drums"
    single = model.pass_sections(harbor, harbor["scenes"][0], plan_scene(harbor, harbor["scenes"][0], 0), 1)
    assert single["source"]["summary"] == "auto" and single["source"]["detailed_description"] == "scene"


def test_seam_video_ref_off_sends_no_video_1_at_pass_seams_but_keeps_the_tail_clip():
    p = model.default_project("Seams")
    p["global"]["long"]["seam_mode"] = "overlap"
    p["scenes"] = [{"id": "s_a", "duration": 6.0},
                   {"id": "s_b", "duration": 30.0, "start": {"mode": "tail", "overlap_frames": 39},
                    "shots": [{"t": 0, "camera": "Wide", "text": "the walk"}]}]
    on = normalize_project(p)
    p["global"]["long"]["seam_video_ref"] = False
    off = normalize_project(p)
    b_on, plan = _passes(on, 1)
    b_off, _ = _passes(off, 1)
    assert [x["seam_before"] for x in plan["passes"]][1:] == ["overlap", "overlap"]
    assert b_on[0]["prompt"] == b_off[0]["prompt"] and b_off[0]["continuation"]["source"] == "prev_scene_tail"
    for on_, off_ in zip(b_on[1:], b_off[1:]):
        assert on_["continuation"]["label"] == "<Video 1>" and off_["continuation"] is None
        assert "[Shot 1] The shot continues seamlessly from the previous moment." in off_["prompt"]
        assert "<Video 1>" not in off_["prompt"] and off_["guides"][0]["source"] == "prev_pass_tail"


# ---- layout mapping -------------------------------------------------------------------------------------------------

def _scene_with_texts(duration=32.0, entries=()):
    p = model.default_project("Layout")
    p["global"]["long"]["seam_mode"] = "overlap"
    p["scenes"][0].update(duration=duration, prompt={"passes": list(entries)})
    return normalize_project(p)


def test_texts_written_for_the_current_layout_are_used_as_they_are():
    p = _scene_with_texts()
    s = p["scenes"][0]
    plan = plan_scene(p, s, 0)
    s["prompt"]["passes"] = [{"start": x["start"] + 0.5 / 24, "end": x["end"],
                              "sections": dict(model.empty_sections(), summary="p{}".format(x["index"]))}
                             for x in plan["passes"]]
    pt = model.pass_texts(p, s, plan)
    assert pt["same"] and pt["stored"] and pt["moved"] == [] and pt["unused"] == []
    assert [t["summary"] for t in pt["texts"]] == ["p1", "p2", "p3"] and pt["entry"] == [1, 2, 3]
    s["prompt"]["passes"] = s["prompt"]["passes"][:1]  # only pass 1 written so far
    pt = model.pass_texts(p, s, plan)
    assert pt["same"] and [t["summary"] for t in pt["texts"]] == ["p1", "", ""] and pt["entry"] == [1, None, None]


def test_a_longer_scene_moves_the_last_pass_and_its_text_follows():
    p = _scene_with_texts()
    s = p["scenes"][0]
    plan = plan_scene(p, s, 0)
    s["prompt"]["passes"] = model.relayout_pass_texts(p, s, plan)
    for k, e in enumerate(s["prompt"]["passes"], 1):
        e["sections"]["summary"] = "p{}".format(k)
    s["duration"] = 34.0
    plan2 = plan_scene(p, s, 0)
    pt = model.pass_texts(p, s, plan2)
    assert not pt["same"] and [t["summary"] for t in pt["texts"]] == ["p1", "p2", "p3"]
    # the planner balances the last two passes, so passes 2 and 3 both move; pass 1 stays
    assert [(x["start"], x["end"]) for x in plan2["passes"]][0] == (plan["passes"][0]["start"], plan["passes"][0]["end"])
    assert pt["moved"] == [2, 3] and pt["unused"] == [] and pt["entry"] == [1, 2, 3]
    issues = [x for x in _lint(p) if "another pass layout" in x["message"]]
    assert len(issues) == 1 and issues[0]["level"] == "info"
    assert "pass 3 (00:" in issues[0]["message"] and "Use the new layout" in issues[0]["message"]
    s["prompt"]["passes"] = model.relayout_pass_texts(p, s, plan2)  # "Use the new layout"
    assert model.pass_texts(p, s, plan2)["same"]
    assert not [x for x in _lint(p) if "another pass layout" in x["message"]]


def test_another_layout_maps_by_the_largest_overlap_each_text_once():
    p = _scene_with_texts(entries=[
        {"start": 0, "end": 16, "sections": {"summary": "first half"}},
        {"start": 15.5, "end": 32, "sections": {"summary": "second half"}},
        {"start": 31, "end": 32, "sections": {"non_diegetic_music": "drums"}},
        None, {"start": 0, "end": 32, "sections": {}}])
    s = p["scenes"][0]
    assert s["prompt"]["passes"][3] == {"start": 0.0, "end": 0.0, "sections": model.empty_sections()}  # junk: empty
    plan = plan_scene(p, s, 0)
    assert len(plan["passes"]) == 3
    pt = model.pass_texts(p, s, plan)
    # pass 1 (0-15.08) overlaps "first half" most; pass 3 (~21-32) "second half"; pass 2 (~13.5-23) gets nothing left
    # but "drums" does not reach it (it overlaps pass 3 only, which is taken)
    assert [t["summary"] for t in pt["texts"]] == ["first half", "", "second half"]
    assert pt["entry"] == [1, None, 2] and pt["moved"] == [1, 3] and pt["unused"] == [3]
    msg = next(x["message"] for x in _lint(p) if "another pass layout" in x["message"])
    assert "the text written for 00:31.000–00:32.000 is not used" in msg
    new = model.relayout_pass_texts(p, s, plan)
    assert [e["sections"]["summary"] for e in new] == ["first half", "", "second half"]
    assert [(e["start"], e["end"]) for e in new] == [(x["start"], x["end"]) for x in plan["passes"]]


def test_a_one_pass_scene_keeps_its_text_and_takes_the_best_of_an_old_layout():
    p = _scene_with_texts(duration=8.0, entries=[{"start": 0, "end": 6.5, "sections": {"summary": "it"}}])
    s = p["scenes"][0]
    pt = model.pass_texts(p, s, plan_scene(p, s, 0))
    assert pt["same"] and pt["texts"][0]["summary"] == "it"  # one pass: its range does not matter
    s["prompt"]["passes"] = [{"start": 0, "end": 15, "sections": {"summary": "a"}},
                             {"start": 14, "end": 30, "sections": {"summary": "b"}}]
    pt = model.pass_texts(p, s, plan_scene(p, s, 0))
    assert not pt["same"] and pt["texts"][0]["summary"] == "a" and pt["unused"] == [2] and pt["moved"] == [1]


# ---- passes without a summary of their own --------------------------------------------------------------------------

def test_lint_lists_the_passes_without_a_summary_of_their_own(harbor):
    def summary_issues():
        return [x for x in _lint(harbor) if "no summary of" in x["message"]]
    (x,) = summary_issues()
    assert x["level"] == "warn" and x["scene_id"] == "s_long"
    assert x["message"] == "02 The long walk home: passes 1, 2 and 3 have no summary of their own; they get one made " \
                           "from their shots (the scene summary is a note for you and the LLM and is not sent)"
    _own(harbor, 1, {1: {"summary": "a"}, 3: {"summary": "c"}})
    (x,) = summary_issues()
    assert "pass 2 has no summary of its own; it gets one made from its shots" in x["message"]
    harbor["scenes"][1]["prompt"]["pass_prompts"] = {"2": "summary:\nHand edited."}
    assert summary_issues() == []


def test_soundscape_lint_counts_the_passes_own_soundscapes(harbor):
    _own(harbor, 1, {1: {"overall_soundscape": "Gulls."}, 2: {"overall_soundscape": "Rain."}})
    (x,) = [x for x in _lint(harbor) if "overall_soundscape is empty" in x["message"] and x.get("scene_id") == "s_long"]
    assert x["message"].startswith("02 The long walk home pass 3: overall_soundscape is empty")


# ---- dialogue length ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("line, seconds", [
    ({"text": "Is anyone still out there?"}, 2.0),            # 5 words / 2.5
    ({"text": ""}, 1.0),                                       # at least 1 s
    ({"text": "— ... !!"}, 1.0),                               # no letters or digits: no words
    ({"text": "你好世界你好世界你好世界你好世界你好世界"}, 2.0),  # 20 CJK characters = 5 words
    ({"text": "Hello 世界 again"}, 1.0),                        # 2 words + 2 / 4
    ({"text": " ".join(["word"] * 10)}, 4.0),
    ({"text": "x", "duration": 3.25}, 3.25),
    ({"text": " ".join(["word"] * 10), "duration": 0}, 4.0),     # 0 / junk: estimated
    ({"text": " ".join(["word"] * 10), "duration": "abc"}, 4.0),
    ({"text": "x", "duration": 1e9}, 600.0),
])
def test_dialogue_seconds(line, seconds):
    assert model.dialogue_seconds(line) == pytest.approx(seconds)


def test_dialogue_duration_is_normalised():
    p = model.default_project()
    p["scenes"][0]["dialogue"] = [{"id": "d_{}".format(k), "t": k, "duration": v}
                                  for k, v in enumerate(["2.5", 0, -1, "x", None, True, 1e9, 4])]
    got = [d["duration"] for d in normalize_project(p)["scenes"][0]["dialogue"]]
    assert got == [2.5, None, None, None, None, None, 600.0, 4.0]


def test_lines_past_a_seam_or_the_scene_end_are_warned(harbor):
    s = harbor["scenes"][1]  # cut seams at 14.375 and 22 s, the scene ends at 32 s
    s["dialogue"] += [
        {"id": "d_seam", "speaker": "c_mara", "t": 13.5, "text": "Is anyone still out there?", "language": "English"},
        {"id": "d_short", "speaker": "c_mara", "t": 20.5, "text": "We should go back home now.",
         "language": "English", "duration": 1.2},
        {"id": "d_end", "speaker": "c_mara", "t": 31.0, "text": "Wait for me, please, wait.", "language": "English",
         "duration": 2.0}]
    p = normalize_project(harbor)
    plan = plan_scene(p, p["scenes"][1], 1)
    spans = {x["id"]: x for x in model.dialogue_spans(p["scenes"][1], plan)}
    assert spans["d_seam"]["pass"] == 1 and spans["d_seam"]["seam"] == 14.375 and spans["d_seam"]["estimated"]
    assert spans["d_short"]["seam"] is None and not spans["d_short"]["past_end"]
    assert spans["d_end"]["past_end"] and spans["d_end"]["seam"] is None and not spans["d_end"]["estimated"]
    issues = [x["message"] for x in _lint(p) if "runs to" in x["message"]]
    assert issues == [
        "02 The long walk home: the dialogue line at 13.50 s runs to about 15.50 s, past the pass seam at 14.38 s where "
        "pass 2 takes over, so it is cut off; let it end before the seam or start after it (its length is estimated "
        "from its words; give it a duration if it is shorter)",
        "02 The long walk home: the dialogue line at 31.00 s runs to 33.00 s, past the scene's end at 32.00 s"]


# ---- camera ---------------------------------------------------------------------------------------------------------

PHRASE = {"extreme wide": "An extreme wide shot", "wide": "A wide shot", "medium wide": "A medium-wide shot",
          "medium": "A medium shot", "medium close-up": "A medium close-up", "close-up": "A close-up",
          "extreme close-up": "An extreme close-up", "over-the-shoulder": "An over-the-shoulder shot",
          "two-shot": "A two-shot", "insert": "An insert shot", "low angle": "A low-angle shot",
          "high angle": "A high-angle shot", "overhead": "An overhead shot", "dutch angle": "A Dutch-angle shot"}


def _camera_project():
    p = model.default_project("Camera")
    p["scenes"][0].update(duration=10.0, shots=[
        {"id": "h_1", "t": 0, "camera": "the camera pushes in", "text": "@{Mara} walks to the pier"},
        {"id": "h_2", "t": 5, "camera": "the camera pans left", "text": "the rain starts"}])
    p["cast"] = [{"id": "c_mara", "name": "Mara"}]
    p["scenes"][0]["cast"] = [{"id": "c_mara"}]
    return normalize_project(p)


def _shot_lines(p):
    (b,), _ = _passes(p, 0)
    return _sections(b["prompt"])["detailed_description"].split("\n")


@pytest.mark.parametrize("framing", model.FRAMINGS)
def test_every_framing_amplitude_and_speed(framing):
    p = _camera_project()
    for amp in model.CAMERA_AMPS:
        for speed in model.CAMERA_SPEEDS:
            for sh in p["scenes"][0]["shots"]:
                sh.update(framing=framing, camera_amp=amp, camera_speed=speed)
            how = (" with {} amplitude".format(amp) if amp else "") + (" at {} speed".format(speed) if speed else "")
            push, pan = "The camera pushes in" + how + ".", "The camera pans left" + how + "."
            if framing:
                want = ["[Shot 1] {}: {} <Subject 1> walks to the pier.".format(PHRASE[framing], push),
                        "[Shot 2] At 00:05.000, the shot cuts to {}: {} The rain starts.".format(
                            PHRASE[framing][0].lower() + PHRASE[framing][1:], pan)]
            else:  # without a framing: as before, plus amplitude and speed
                want = ["[Shot 1] {} <Subject 1> walks to the pier.".format(push),
                        "[Shot 2] At 00:05.000, the shot cuts to the rain starts. {}".format(pan)]
            assert _shot_lines(p) == want, (framing, amp, speed)


def test_shots_without_the_new_fields_read_as_before_and_hand_written_text_works():
    p = _camera_project()
    shots = p["scenes"][0]["shots"]
    shots[0]["camera"], shots[1]["camera"] = "Wide", "Close-up · slow push-in"
    assert _shot_lines(p) == ["[Shot 1] A wide shot: <Subject 1> walks to the pier.",
                              "[Shot 2] At 00:05.000, the shot cuts to the rain starts. Close-up · slow push-in."]
    shots[1]["camera_speed"] = "fast"
    assert _shot_lines(p)[1] == "[Shot 2] At 00:05.000, the shot cuts to the rain starts. Close-up · slow push-in at " \
                                "fast speed."
    shots[0].update(camera="", camera_amp="large")  # amplitude without a camera move: nothing to scale
    assert _shot_lines(p)[0] == "[Shot 1] <Subject 1> walks to the pier."
    shots[0].update(camera="", camera_amp="", framing="insert", text="")
    assert _shot_lines(p)[0] == "[Shot 1] An insert shot."


def test_framed_shot_continues_across_a_pass_seam():
    assert prompt._framed_shot(1, {"continuing": True, "framing": "wide"}, "", "the walk") == \
        [prompt.CONTINUES, "A wide shot: The walk."]
    assert prompt._framed_shot(1, {"framing": ""}, "the camera pushes in", "x") is None


def test_camera_sentence():
    assert model.camera_sentence("the camera pushes in", "small", "slow") == \
        "The camera pushes in with small amplitude at slow speed."
    assert model.camera_sentence("The camera whips left!", "large", "") == "The camera whips left with large amplitude."
    assert model.camera_sentence("the camera holds a static shot.") == "The camera holds a static shot."
    assert model.camera_sentence("  ", "small", "fast") == "" and model.camera_sentence("...", "small") == ""
    assert model.framing_phrase("close-up") == "a close-up" and model.framing_phrase("Close-up") == ""


# ---- presets and the camera_version migration -----------------------------------------------------------------------

OFFICIAL = ["Zoom In", "Zoom Out", "Push In", "Pull Out", "Pan Left", "Pan Right", "Truck Left", "Truck Right",
            "Tilt Up", "Tilt Down", "Pedestal Up", "Pedestal Down", "Arc Shot", "Tracking Shot", "Static Shot",
            "Shake Slightly", "Shake Strongly", "POV", "Roll Clockwise", "Roll Counterclockwise"]


def test_new_projects_get_the_20_official_moves():
    p = model.default_project()
    assert [k["name"] for k in p["camera_presets"]] == OFFICIAL and p["camera_version"] == 2
    assert all(k["text"].startswith("the camera ") for k in p["camera_presets"])
    assert normalize_project(p)["camera_presets"] == p["camera_presets"]


def test_older_projects_get_the_missing_official_moves_once():
    old = {"scenes": [{}], "camera_presets": [
        {"id": "k_1", "name": "Slow push-in", "text": "slow push-in toward the subject"},
        {"id": "k_2", "name": " push in ", "text": "my own push"},
        {"id": "k_3", "name": "Whip", "text": "a whip pan"}]}
    p = normalize_project(old)
    names = [k["name"] for k in p["camera_presets"]]
    assert names[:3] == ["Slow push-in", " push in ", "Whip"]  # kept, first, unchanged
    assert names[3:] == [x for x in OFFICIAL if x != "Push In"] and p["camera_version"] == 2
    assert [k["id"] for k in p["camera_presets"][:3]] == ["k_1", "k_2", "k_3"]
    assert normalize_project(p)["camera_presets"] == p["camera_presets"]  # once
    p["camera_presets"] = p["camera_presets"][:1]  # presets deleted after the migration stay deleted
    assert len(normalize_project(p)["camera_presets"]) == 1


@pytest.mark.parametrize("version, appended, kept", [
    (None, True, 2), (1, True, 2), ("x", True, 2), (True, True, 2), (2, False, 2), ("2", False, 2), (3.7, False, 3),
    (1e300, False, 1000000)])
def test_camera_version_values(version, appended, kept):
    raw = {"scenes": [{}], "camera_presets": [{"name": "Mine", "text": "x"}]}
    if version is not None:
        raw["camera_version"] = version
    p = normalize_project(raw)
    assert (len(p["camera_presets"]) == 21) is appended and p["camera_version"] == kept


def test_shot_camera_fields_are_normalised():
    p = model.default_project()
    p["scenes"][0]["shots"] = [{"t": 0, "camera_amp": "small", "camera_speed": "fast", "framing": "two-shot"},
                               {"t": 1, "camera_amp": "Small", "camera_speed": 2, "framing": "close up"}, {"t": 2}]
    shots = normalize_project(p)["scenes"][0]["shots"]
    assert [(x["camera_amp"], x["camera_speed"], x["framing"]) for x in shots] == \
        [("small", "fast", "two-shot"), ("", "", ""), ("", "", "")]
    plan = plan_scene(normalize_project(p), normalize_project(p)["scenes"][0], 0)
    assert plan["passes"][0]["shots"][0]["framing"] == "two-shot"  # the planner passes them on


def test_prompt_passes_are_normalised():
    p = model.default_project()
    p["scenes"][0]["prompt"] = {"passes": [{"start": "1.5", "end": 9, "sections": {"summary": 5, "x": "kept"}},
                                           None, "text", {"sections": []}]}
    got = normalize_project(p)["scenes"][0]["prompt"]["passes"]
    assert got[0] == {"start": 1.5, "end": 9.0, "sections": dict(model.empty_sections(), summary="5", x="kept")}
    assert got[1:] == [{"start": 0.0, "end": 0.0, "sections": model.empty_sections()}] * 3
    q = model.default_project()
    q["scenes"][0]["prompt"]["passes"] = "x"
    assert normalize_project(q)["scenes"][0]["prompt"]["passes"] == []
    assert copy.deepcopy(model.default_prompt())["passes"] == []


def test_an_official_camera_name_is_written_as_its_phrase():
    """added 2026-11-06 v0.8.0 (lead review): "Tracking Shot" in a shot's camera became "A tracking Shot:"."""
    from reelwright import model
    assert model.official_camera("Tracking Shot") == "the camera tracks the moving subject"
    assert model.official_camera(" push in. ") == "the camera pushes in"
    assert model.official_camera("a slow crane up") == "a slow crane up"
    assert model.camera_sentence("Push In", "small", "slow") == "The camera pushes in with small amplitude at slow speed."
    assert model.camera_sentence("POV") == "The camera takes the subject's point of view."
