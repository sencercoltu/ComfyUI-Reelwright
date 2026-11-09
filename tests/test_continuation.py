"""The continuation as a named reference (added 2026-11-05 v0.7.0, Global -> Continuity -> name_continuation).

A last-frame start sends the last frame of the scene before as <Picture 1>, a tail start its tail clip as <Video 1>
(with its sound when an audio slot is free), a pass after an overlap seam the end of the pass before as <Video 1>.
With the switch off everything is exactly as in v0.6.1: tests/data/v061_continuation.json holds what v0.6.1 (GitHub
2b5d7ff) built for its projects, written by scratchpad gen_v061_expect.py from the v0.6.1 code.
"""

import copy
import json
import re  # added 2026-11-12 v0.14.0
import os

import pytest

from reelwright import model, prompt, validate
from reelwright.analysis import analyze
from reelwright.model import normalize_project
from reelwright.planner import plan_scene
from reelwright.prompt import build_pass, tidy_rewrite
from reelwright.storage import ProjectStore

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "v061_continuation.json")
BUILD_KEYS = ("prompt", "tags", "tag_map", "unknown", "issues", "images", "videos", "audios", "guides", "subjects")


def _v061_tags(b):
    """added 2026-11-12 v0.14.0: a build without the tag map's @V1.2 style entries (a scene's further references of an
    asset), which v0.6.1 did not write; the cache key does not read the tag map."""
    b = dict(b)
    b["tag_map"] = {k: v for k, v in b["tag_map"].items() if not re.fullmatch(r"@[PVA]\d+\.\d+", k)}
    return b


@pytest.fixture(scope="module")
def v061():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def _project(raw, on=True):
    p = copy.deepcopy(raw)
    p["global"]["continuity"]["name_continuation"] = on
    return normalize_project(p)


def _pass_summaries(p):
    """v0.8.0: a multi-pass scene no longer sends the scene summary to every pass (it is a whole-scene note). Writing it
    as each pass's own summary (scene.prompt.passes) gives the prompts of v0.7.0 and before."""
    for i, s in enumerate(p["scenes"]):
        plan = plan_scene(p, s, i)
        if len(plan["passes"]) > 1 and s["prompt"]["sections"]["summary"].strip():
            s["prompt"]["passes"] = [{"start": x["start"], "end": x["end"],
                                      "sections": dict(model.empty_sections(), summary=s["prompt"]["sections"]["summary"])}
                                     for x in plan["passes"]]
    return p


def _files(p, roots):
    for a in p["assets"]:
        path = os.path.join(roots.input, a["file"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(a["id"].encode())


def _analyze(p, roots):
    _files(p, roots)
    return analyze(p, ProjectStore(roots, p["slug"]))


def _scene(p, sid):
    return next((i, s) for i, s in enumerate(p["scenes"]) if s["id"] == sid)


def _builds(p, sid):
    i, s = _scene(p, sid)
    plan = plan_scene(p, s, i)
    ctx = prompt.prepare(p)
    return [build_pass(p, s, i, plan, x, ctx=ctx) for x in plan["passes"]], plan


def _sections(text):
    out, key = {}, None
    for line in text.split("\n"):
        if line.endswith(":") and line[:-1] in prompt.REF2VA_SECTIONS:
            key = line[:-1]
            out[key] = []
        elif key:
            out[key].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


# ---- switch off: exactly v0.6.1 ----------------------------------------------------------------------------------

# added 2026-11-12 v0.16.0: a packed anchor sheet is named in its subject line ("shown in <Picture 1>, a sheet of 2 views
# of the same person"); without those words a build is v0.6.1's. A scene that sends a sheet gets new keys (re-renders).
SHEET_WORDS = re.compile(r", a sheet of \d+ views of the same (?:person|place|object|subject)")


def _no_sheet_words(b):
    return dict(b, prompt=SHEET_WORDS.sub("", b["prompt"])) if isinstance(b.get("prompt"), str) else b


# added 2026-11-12 v0.17.0: every spoken line opens with its time ("At 00:02.400, <Subject 1> (S1) says, …"); without
# the time a build is v0.6.1's. A scene with spoken lines gets new keys (re-renders).
LINE_TIME = re.compile(r"At \d{2}:\d{2}\.\d{3}, (<Subject \d+>|an off-screen voice|[A-Z][^,(<]{0,40}?) (\(S\d+(?:,S\d+)*\))")


def _no_line_times(b):
    if not isinstance(b.get("prompt"), str):
        return b
    return dict(b, prompt=LINE_TIME.sub(lambda m: m.group(1)[0].upper() + m.group(1)[1:] + " " + m.group(2), b["prompt"]))


def _sends_sheet(builds):
    return any(len(x["assets"]) > 1 for b in builds for x in b["images"])


def test_off_gives_the_v061_builds_and_cache_keys(v061, roots):
    assert model.default_global()["continuity"]["name_continuation"] is True
    for raw, expect in zip(v061["projects"], v061["expect"]):
        # [OLD v0.7.0] r = _analyze(_project(raw, on=False), roots)
        # v0.8.0: with the scene summary written as each pass's own summary (a multi-pass scene no longer sends the
        # scene summary), every build and key is v0.6.1's
        # [OLD 2026-11-12 v0.15.1->v0.16.0] r = _analyze(_pass_summaries(_project(raw, on=False)), roots)
        q = _pass_summaries(_project(raw, on=False))  # added 2026-11-12 v0.16.0: the scene order, for chained keys
        r = _analyze(q, roots)
        assert set(r["scenes"]) == set(expect)
        moved = set()  # added 2026-11-12 v0.16.0: scenes with new keys (a sheet, or continuing from such a scene)
        # [OLD 2026-11-12 v0.15.1->v0.16.0] for sid, want in expect.items():
        for i, sid in enumerate(x["id"] for x in q["scenes"]):
            want = expect[sid]
            sr = r["scenes"][sid]
            got = [{k: b[k] for k in BUILD_KEYS} for b in sr["builds"]]
            # [OLD 2026-11-12 v0.13.1->v0.14.0] assert json.loads(json.dumps(got)) == want["builds"], sid
            # added 2026-11-12 v0.14.0: the tag map also names a scene's further references of an asset (@V1.2); the
            # cache key does not read the tag map, so everything else is still v0.6.1's
            for g in got:
                g["tag_map"] = {k: v for k, v in g["tag_map"].items() if not re.fullmatch(r"@[PVA]\d+\.\d+", k)}
            # [OLD 2026-11-12 v0.15.1->v0.16.0] assert json.loads(json.dumps(got)) == want["builds"], sid
            got = [_no_sheet_words(g) for g in got]  # added 2026-11-12 v0.16.0
            timed = any(LINE_TIME.search(g["prompt"] or "") for g in got)  # added 2026-11-12 v0.17.0
            got = [_no_line_times(g) for g in got]  # added 2026-11-12 v0.17.0
            assert json.loads(json.dumps(got)) == want["builds"], sid
            assert all(b["continuation"] is None for b in sr["builds"]), sid
            # [OLD 2026-11-12 v0.15.1->v0.16.0] assert sr["pass_keys"] == want["pass_keys"], sid
            # [OLD 2026-11-12 v0.15.1->v0.16.0] assert sr["key"] == want["key"], sid
            # added 2026-11-12 v0.16.0: the sheet words change its prompt, so its keys, and the keys of the scenes that
            # continue from it
            # [OLD 2026-11-12 v0.16.1->v0.17.0] if _sends_sheet(sr["builds"]) or (i > 0 and model.effective_start(q, i) != "fresh" and
            if _sends_sheet(sr["builds"]) or timed or (i > 0 and model.effective_start(q, i) != "fresh" and  # v0.17.0: timed lines
                                              q["scenes"][i - 1]["id"] in moved):
                moved.add(sid)
                assert sr["key"] != want["key"], sid
                continue
            assert sr["pass_keys"] == want["pass_keys"], sid
            assert sr["key"] == want["key"], sid
            assert sr["status"] == want["status"], sid


def test_v080_changes_only_the_summary_of_multi_pass_scenes_with_a_written_summary(v061, roots):
    """added 2026-11-05 v0.8.0: what re-renders after the update (switch off, so only P1 counts): a multi-pass scene
    whose scene summary was written sends each pass a summary made from its own shots instead, and a guide picture
    named only in that summary is no longer sent as a reference (s_long pass 3: the letter keyframe @P3, still
    anchored); every other section, reference and every other scene (single-pass, or multi-pass with an empty
    summary) keep v0.6.1's build and key."""
    changed, chained = [], set()
    for raw, expect in zip(v061["projects"], v061["expect"]):
        p = _project(raw, on=False)
        r = _analyze(p, roots)
        for i, s in enumerate(p["scenes"]):
            sr, want = r["scenes"][s["id"]], expect[s["id"]]
            multi = len(sr["builds"]) > 1
            written = s["prompt"]["mode"] != "raw" and s["prompt"]["sections"]["summary"].strip()
            for n, (b, was) in enumerate(zip(sr["builds"], want["builds"])):
                if s["id"] == "s_long" and n == 2:  # the keyframe named only in the scene summary
                    assert [x["assets"] for x in b["images"]] == [x["assets"] for x in was["images"]][:-1] and \
                        was["images"][-1]["assets"] == ["a_letter"] and b["guides"] == was["guides"]
                    continue
                # [OLD 2026-11-12 v0.15.1->v0.16.0] now, old = _sections(b["prompt"]), _sections(was["prompt"])
                # [OLD 2026-11-12 v0.16.1->v0.17.0] now, old = _sections(_no_sheet_words(b)["prompt"]), _sections(was["prompt"])  # added 2026-11-12 v0.16.0
                now, old = _sections(_no_line_times(_no_sheet_words(b))["prompt"]), _sections(was["prompt"])  # v0.17.0: line times
                assert {k: v for k, v in now.items() if k != "summary"} == \
                    {k: v for k, v in old.items() if k != "summary"}, s["id"]
                # [OLD 2026-11-12 v0.13.1->v0.14.0] assert {k: b[k] for k in BUILD_KEYS if k not in ("prompt", "issues", "unknown")} == \
                # [OLD 2026-11-12 v0.13.1->v0.14.0]     {k: was[k] for k in BUILD_KEYS if k not in ("prompt", "issues", "unknown")}, s["id"]
                assert {k: _v061_tags(b)[k] for k in BUILD_KEYS if k not in ("prompt", "issues", "unknown")} == \
                    {k: was[k] for k in BUILD_KEYS if k not in ("prompt", "issues", "unknown")}, s["id"]  # added 2026-11-12 v0.14.0
            if multi and written:
                changed.append(s["id"])
                assert all(_sections(b["prompt"])["summary"] != _sections(w["prompt"])["summary"]
                           for b, w in zip(sr["builds"], want["builds"])), s["id"]
                assert sr["key"] != want["key"]
            elif i > 0 and model.effective_start(p, i) != "fresh" and p["scenes"][i - 1]["id"] in chained:
                chained.add(s["id"])  # continues from a scene that renders again: same prompts, new key
                # [OLD 2026-11-12 v0.15.1->v0.16.0] assert [b["prompt"] for b in sr["builds"]] == [w["prompt"] for w in want["builds"]], s["id"]
                # [OLD 2026-11-12 v0.16.1->v0.17.0] assert [_no_sheet_words(b)["prompt"] for b in sr["builds"]] == [w["prompt"] for w in want["builds"]], s["id"]
                assert [_no_line_times(_no_sheet_words(b))["prompt"] for b in sr["builds"]] == [w["prompt"] for w in want["builds"]], s["id"]  # v0.17.0
                assert sr["key"] != want["key"], s["id"]
                continue
            elif _sends_sheet(sr["builds"]):  # added 2026-11-12 v0.16.0: its sheet is named now (new prompt, new key)
                chained.add(s["id"])
                assert sr["key"] != want["key"], s["id"]
                continue
            elif any(LINE_TIME.search(b["prompt"] or "") for b in sr["builds"]):  # added 2026-11-12 v0.17.0: timed lines
                chained.add(s["id"])
                assert sr["key"] != want["key"], s["id"]
                continue
            else:
                assert sr["pass_keys"] == want["pass_keys"] and sr["key"] == want["key"], s["id"]
            if multi and written:
                chained.add(s["id"])
    assert changed == ["s_long"] and "s_short" in chained


def test_on_changes_only_the_passes_that_continue(v061, roots):
    """Fresh scenes keep their keys (no re-render); continuing scenes and passes after overlap seams get new ones."""
    for raw, expect in zip(v061["projects"], v061["expect"]):
        p = _project(raw, on=True)
        r = _analyze(p, roots)
        for i, s in enumerate(p["scenes"]):
            sr, want = r["scenes"][s["id"]], expect[s["id"]]
            named = [b["continuation"] is not None for b in sr["builds"]]
            timed = [bool(LINE_TIME.search(b["prompt"] or "")) for b in sr["builds"]]  # added 2026-11-12 v0.17.0
            for n, (b, was) in enumerate(zip(sr["builds"], want["builds"])):
                same_so_far = not any(named[:n + 1]) and (i == 0 or not sr["continues"])
                if same_so_far:
                    # [OLD 2026-11-12 v0.16.1->v0.17.0] assert b["prompt"] == was["prompt"] and sr["pass_keys"][n] == want["pass_keys"][n], (s["id"], n)
                    # added 2026-11-12 v0.17.0: the same prompt but for the lines' times; a pass with lines has a new key
                    assert _no_line_times(b)["prompt"] == was["prompt"] and (timed[n] or sr["pass_keys"][n] == want["pass_keys"][n]), (s["id"], n)
                if named[n]:
                    assert b["prompt"] != was["prompt"] and sr["pass_keys"][n] != want["pass_keys"][n], (s["id"], n)
            # [OLD 2026-11-12 v0.16.1->v0.17.0] if not sr["continues"] and not any(named):
            if not sr["continues"] and not any(named) and not any(timed):  # v0.17.0
                assert sr["key"] == want["key"], s["id"]
            if any(named):
                assert sr["key"] != want["key"], s["id"]
    # the fixture has both kinds
    p = _project(v061["projects"][0])
    assert _builds(p, "s_one")[0][0]["continuation"] is None
    assert [b["continuation"] is not None for b in _builds(p, "s_seams")[0]] == [False, True, True]


# ---- last-frame start: <Picture 1> ---------------------------------------------------------------------------------

def test_last_frame_start_names_the_frame_as_picture_1(v061):
    p = _project(v061["projects"][0])
    (b,), _ = _builds(p, "s_lf")
    assert b["continuation"] == {"kind": "picture", "source": "prev_scene_last", "frames": 1, "label": "<Picture 1>",
                                 "audio_number": None}
    assert b["images"][0] == {"assets": [], "cast": None, "ref": None, "source": "prev_scene_last", "continuation": True}
    assert [img["assets"] for img in b["images"][1:]] == [["a_front"], ["a_side"]]  # "auto": no sheet needed
    assert b["subjects"][0]["pictures"] == [2, 3] and b["tag_map"]["@P1"] == "<Picture 2>"
    assert b["tag_map"]["@tail"] == "<Picture 1>"
    assert b["guides"] == [{"type": "image", "source": "prev_scene_last", "frame_idx": 0}]  # still anchored
    assert b["tags"] == ["reference generation", "keyframe completion", "audio reference"]
    sec = _sections(b["prompt"])
    assert sec["subject_definitions"].split("\n")[:2] == [
        "<Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 2> and <Picture 3>.",
        "<Picture 1> is the first frame of [Shot 1], the last frame of the scene before."]
    assert "<Picture 1> ([Shot 1] first frame): fully_preserved - the target video starts on this frame and continues " \
           "from it." in sec["retention_analysis"].split("\n")
    # @tail in the written summary is <Picture 1>; the written style line stays first, [Shot 1] cites the frame
    assert "<Subject 1> finds the boat she waited for, continuing from <Picture 1>." in sec["summary"]
    desc = sec["detailed_description"].split("\n")
    assert desc[0] == "Soft dusk light."
    assert desc[1].startswith("[Shot 1] The shot begins from <Picture 1>. A medium shot: <Subject 1> turns to the sea.")
    assert desc[2].startswith("[Shot 2] At 00:03.500, the shot cuts to a close-up of <Subject 1>'s eyes.")


def test_tail_start_names_the_tail_clip_as_video_1_with_its_sound(v061):
    p = _pass_summaries(_project(v061["projects"][0]))  # v0.8.0: the summary as each pass's own
    builds, plan = _builds(p, "s_long")
    b = builds[0]
    assert b["continuation"] == {"kind": "video", "source": "prev_scene_tail", "frames": 124, "label": "<Video 1>",
                                 "audio_number": 1}
    assert [(v["asset"], v["soundtrack"], v.get("audio_number")) for v in b["videos"]] == \
        [(None, True, 1), ("a_dolly", True, 2)]
    assert b["tag_map"]["@V1"] == "<Video 2>" and b["tag_map"]["@tail"] == "<Video 1>"
    assert b["guides"][0] == {"type": "clip", "source": "prev_scene_tail", "frames": 39, "frame_idx": 0, "audio": True}
    assert b["tags"] == ["reference generation", "video continuation", "audio reference"]
    sec = _sections(b["prompt"])
    defs = sec["subject_definitions"].split("\n")
    assert "<Video 1> is the end of the scene before; the target video continues from its final frames." in defs
    assert "<Audio 1> is the synchronized audio track of <Video 1>." in defs
    assert "<Audio 2> is the synchronized audio track of <Video 2>." in defs
    ret = sec["retention_analysis"].split("\n")
    assert "<Video 1> (continuation source): fully_preserved - its final frames are kept as they are, and the " \
           "subjects, setting, lighting and motion carry on from them." in ret
    assert "<Audio 1>: reference - the target video's sound carries on from <Audio 1> without copying the original " \
           "signal." in ret
    assert "camera like <Video 2>" in sec["summary"]
    assert sec["detailed_description"].startswith("[Shot 1] The shot continues seamlessly from the final frames of "
                                                  "<Video 1>. A wide shot: Mara leaves the pier.")


def test_overlap_seams_name_the_end_of_the_pass_before(v061):
    p = _pass_summaries(_project(v061["projects"][0]))  # v0.8.0: the summary as each pass's own
    builds, plan = _builds(p, "s_long")
    assert [x["seam_before"] for x in plan["passes"]] == ["none", "overlap", "overlap"]
    for b in builds[1:]:
        assert b["continuation"]["source"] == "prev_pass_tail" and b["continuation"]["frames"] == 124
        assert b["videos"][0]["continuation"] and b["guides"][0]["source"] == "prev_pass_tail"
        sec = _sections(b["prompt"])
        assert "<Video 1> is the end of the previous part of this scene; the target video continues from its final " \
               "frames." in sec["subject_definitions"]
        assert sec["detailed_description"].startswith(
            "[Shot 1] The shot continues seamlessly from the final frames of <Video 1>.")
        assert "previous moment" not in sec["detailed_description"]
    # pass 3 holds the 25 s letter keyframe named in the summary: <Picture 3> after Mara's two pictures
    assert builds[2]["tag_map"]["@P3"] == "<Picture 3>" and "holding <Picture 3>" in builds[2]["prompt"]


# ---- written prompts -----------------------------------------------------------------------------------------------

def test_raw_prompt_gets_the_definition_and_tail_reads_as_the_label(v061):
    p = _project(v061["projects"][0])
    (b,), _ = _builds(p, "s_raw")
    assert b["prompt"] == "[reference generation + keyframe completion] <Picture 1> is the first frame of the target " \
                          "video, the last frame of the scene before.\n<Subject 1> steps inside from <Picture 1>; the " \
                          "pier <Subject 2> behind her."


def test_pass_prompt_with_task_tags(v061):
    p = _project(v061["projects"][0])
    (b,), _ = _builds(p, "s_over")
    assert b["prompt"] == "[reference generation + video continuation + audio reference] <Video 1> is the end of the " \
                          "scene before; the target video continues from its final frames. <Audio 1> is the " \
                          "synchronized audio track of <Video 1>.\n<Subject 1> meets <Subject 2> in the hallway."


def test_six_section_pass_prompt_gets_its_lines_once(v061):
    p = _project(v061["projects"][0])
    i, s = _scene(p, "s_lf")
    (built,), plan = _builds(p, "s_lf")
    # "Edit this pass by hand": a copy of the v0.7.0 build is sent as it is
    s["prompt"]["pass_prompts"] = {"1": built["prompt"]}
    b = build_pass(p, s, i, plan, plan["passes"][0])
    assert b["prompt"] == built["prompt"] and b["continuation"]["kind"] == "picture"
    # a Split answer with @tags only: the lines are added to its sections
    s["prompt"]["pass_prompts"] = {"1": "subject_definitions:\n@Mara is Mara.\n\nsummary:\n@Mara turns.\n\n"
                                        "retention_analysis:\nN/A\n\ndetailed_description:\nDusk.\n[Shot 1] @Mara turns."}
    sec = _sections(build_pass(p, s, i, plan, plan["passes"][0])["prompt"])
    assert sec["subject_definitions"] == "<Picture 1> is the first frame of [Shot 1], the last frame of the scene " \
                                         "before.\n<Subject 1> is Mara."
    assert sec["retention_analysis"] == "<Picture 1> ([Shot 1] first frame): fully_preserved - the target video " \
                                        "starts on this frame and continues from it."
    assert sec["detailed_description"] == "Dusk.\n[Shot 1] The shot begins from <Picture 1>. <Subject 1> turns."
    # without a subject_definitions section, one is added in front for it
    s["prompt"]["pass_prompts"] = {"1": "summary:\n@Mara turns.\n\ndetailed_description:\n[Shot 1] @Mara turns."}
    text = build_pass(p, s, i, plan, plan["passes"][0])["prompt"]
    assert text == "subject_definitions:\n<Picture 1> is the first frame of [Shot 1], the last frame of the scene " \
                   "before.\n\nsummary:\n[reference generation + keyframe completion + audio reference] <Subject 1> " \
                   "turns.\n\ndetailed_description:\n[Shot 1] The shot begins from <Picture 1>. <Subject 1> turns."


def test_text_with_fixed_numbers_keeps_the_v061_build(v061):
    """A pass prompt written with <Picture N> numbers (before v0.7.0) would point at other pictures once the frame is
    <Picture 1>, so that pass is built as before and an info issue says why."""
    on, off = _project(v061["projects"][0]), _project(v061["projects"][0], on=False)
    for p in (on, off):
        _scene(p, "s_lf")[1]["prompt"]["pass_prompts"] = {"1": "<Picture 1> is Mara. @Mara turns to the sea."}
    (b,), _ = _builds(on, "s_lf")
    (b_off,), _ = _builds(off, "s_lf")
    assert b["continuation"] is None
    assert {k: b[k] for k in BUILD_KEYS if k != "issues"} == {k: b_off[k] for k in BUILD_KEYS if k != "issues"}
    assert [x["level"] for x in b["issues"]] == ["info"] and "fixed reference numbers" in b["issues"][0]["message"]
    # a <Video N> does not move when the picture is named
    _scene(on, "s_lf")[1]["prompt"]["pass_prompts"] = {"1": "<Video 1> sets the pace. @Mara turns to the sea."}
    (b,), _ = _builds(on, "s_lf")
    assert b["continuation"]["kind"] == "picture"


def test_hand_written_sections_get_the_definition(v061):
    p = _project(v061["projects"][0])
    (b,), _ = _builds(p, "s_auto_off")
    sec = _sections(b["prompt"])
    assert sec["subject_definitions"] == "<Picture 1> is the first frame of [Shot 1], the last frame of the scene " \
                                         "before.\n<Subject 1> is Mara in her grey coat, shown in <Picture 2> and <Picture 3>."
    assert sec["retention_analysis"] == "<Picture 1> ([Shot 1] first frame): fully_preserved - the target video " \
                                        "starts on this frame and continues from it."
    assert sec["detailed_description"] == "Night. <Subject 1> closes the door.\n[Shot 1] The shot begins from " \
                                          "<Picture 1>."


def test_rewriter_turns_the_label_back_into_tail(v061):
    p = _project(v061["projects"][0])
    (b,), _ = _builds(p, "s_lf")
    before = {k: "" for k in prompt.REF2VA_SECTIONS}
    out = tidy_rewrite({"summary": "<Subject 1> starts on <Picture 1> and looks at <Picture 2>."}, before,
                       {"subjects": True, "retention": True, "shots": True}, b["tag_map"])
    assert out["summary"] == "@Mara starts on @tail and looks at @P1."
    # and @tail reads as it did before with the switch off
    off = _project(v061["projects"][0], on=False)
    _scene(off, "s_lf")[1]["prompt"]["sections"]["summary"] = out["summary"]
    (b_off,), _ = _builds(off, "s_lf")
    assert "<Subject 1> starts on the end of the previous shot and looks at <Picture 1>." in b_off["prompt"]


# ---- budget ----------------------------------------------------------------------------------------------------------

def test_continuation_picture_packs_the_anchors_first(v061, roots):
    p = _project(v061["projects"][0])
    (b,), _ = _builds(p, "s_many")   # Mara's 2 anchors + 7 pictures = 9; the frame makes 10, so Mara is one sheet
    assert b["continuation"]["kind"] == "picture" and len(b["images"]) == 9
    assert b["images"][1]["assets"] == ["a_front", "a_side"]
    i, s = _scene(p, "s_many")
    counts = model.scene_media_counts(p, s)
    assert (counts["pictures"], counts["continuation"]) == (9, "picture")
    assert counts["files"] == 9 + counts["audio"]  # + the song's part
    r = _analyze(p, roots)
    assert not [x for x in r["scenes"]["s_many"]["issues"] if "pictures" in x["message"]]


def test_continuation_that_does_not_fit_is_only_anchored(v061, roots):
    on, off = _project(v061["projects"][0]), _project(v061["projects"][0], on=False)
    for sid, what in (("s_full", "the last frame of the scene before is only anchored, not named <Picture 1>: with it "
                                 "this pass would send 11 pictures, 0 videos and 12 files"),
                      ("s_vid3", "the tail clip of the scene before is only anchored, not named <Video 1>: with it this "
                                 "pass would send 0 pictures, 4 videos and 5 files")):
        (b,), _ = _builds(on, sid)
        (b_off,), _ = _builds(off, sid)
        assert b["continuation"] is None, sid
        assert {k: b[k] for k in BUILD_KEYS if k != "issues"} == {k: b_off[k] for k in BUILD_KEYS if k != "issues"}
        assert [x["level"] for x in b["issues"]] == ["warn"] and b["issues"][0]["message"].startswith(what), sid
        i, s = _scene(on, sid)
        assert model.scene_media_counts(on, s) == dict(model.scene_media_counts(off, s), continuation="")
    r = _analyze(on, roots)
    assert any("not named <Picture 1>" in x["message"] and x["level"] == "warn" for x in r["scenes"]["s_full"]["issues"])


def test_tail_clip_without_a_free_audio_slot_goes_without_its_sound(v061):
    p = _project(v061["projects"][0])
    i, s = _scene(p, "s_vid3")
    s["refs"] = [{"id": "r_v1", "asset": "a_dolly", "role": "reference", "soundtrack": True},
                 {"id": "r_rain", "asset": "a_rain", "role": "reference"},
                 {"id": "r_tv", "asset": "a_tvoice", "role": "reference"}]
    p["soundtrack"] = []
    p = normalize_project(p)
    (b,), _ = _builds(p, "s_vid3")
    c = b["continuation"]
    assert c["kind"] == "video" and c["audio_number"] is None and not b["videos"][0]["soundtrack"]
    assert [x.get("audio_number") for x in b["videos"]] == [None, 1]
    assert "synchronized audio track of <Video 1>" not in b["prompt"]
    assert [x["level"] for x in b["issues"]] == ["info"] and "without its sound" in b["issues"][0]["message"]
    counts = model.scene_media_counts(p, _scene(p, "s_vid3")[1])
    assert (counts["videos"], counts["audio"], counts["continuation"]) == (2, 3, "video")


def test_lint_counts_what_the_build_sends(v061, roots):
    for raw in v061["projects"]:
        p = _project(raw)
        ctx = prompt.prepare(p)
        for i, s in enumerate(p["scenes"]):
            plan = plan_scene(p, s, i)
            for x in plan["passes"]:
                b = build_pass(p, s, i, plan, x, ctx=ctx)
                c = validate._media_counts(p, s, x, b, ctx)
                guided = any(img["ref"] and not img["cast"] for img in b["images"]) or any(v.get("guide")
                                                                                          for v in b["videos"])
                if not guided:
                    assert (c["pictures"], c["videos"]) == (len(b["images"]), len(b["videos"])), (s["id"], x["index"])
                assert c["files"] == c["pictures"] + c["videos"] + len(b["audios"]), (s["id"], x["index"])
                kind = (b["continuation"] or {}).get("kind", "")
                assert c["continuation"].startswith(kind) and (kind or not c["continuation"]), (s["id"], x["index"])


def test_short_tail_clip_is_linted_by_its_length(roots):
    p = model.default_project("Short")
    p["scenes"] = [{"id": "s_a", "duration": 1.0}, {"id": "s_b", "duration": 6.0,
                                                     "start": {"mode": "tail", "overlap_frames": 22}}]
    p = normalize_project(p)
    (b,), _ = _builds(p, "s_b")
    assert b["continuation"]["frames"] == 24 and b["guides"][0]["frames"] == 22
    msgs = [x["message"] for x in _analyze(p, roots)["scenes"]["s_b"]["issues"]]
    assert any("the tail clip of the scene before is 1.0 s (H3 video refs are 2-15 s)" in m for m in msgs)


def test_reanchored_tail_and_cut_seams_follow_the_effective_start(v061):
    p = _project(v061["projects"][1])   # re-anchor after 1: the third tail of a chain continues from the last frame
    starts = [model.effective_start(p, i) for i in range(len(p["scenes"]))]
    for i, s in enumerate(p["scenes"]):
        builds, plan = _builds(p, s["id"])
        first = builds[0]["continuation"]
        assert (first or {}).get("kind", "") == {"fresh": "", "last_frame": "picture", "tail": "video"}[starts[i]]
        for b, x in zip(builds[1:], plan["passes"][1:]):
            assert (b["continuation"] is not None) == (x["seam_before"] == "overlap"), (s["id"], x["index"])
