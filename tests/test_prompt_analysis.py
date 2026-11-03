import copy

import pytest  # added 2026-11-03 v0.5.0

from reelwright.analysis import analyze, plan_response
from reelwright.planner import plan_scene
from reelwright.prompt import build_pass


def _build(p, i, n=0):
    plan = plan_scene(p, p["scenes"][i], i)
    return build_pass(p, p["scenes"][i], i, plan, plan["passes"][n]), plan


def test_reference_numbering_follows_native_order(harbor):
    b, _ = _build(harbor, 1)
    # cast sheet first, then the keyframe named in the prompt, then the dolly video whose
    # soundtrack takes <Audio 1>, then Mara's voice
    assert [img["assets"] for img in b["images"]] == [["a_front", "a_side"], ["a_letter"]]
    assert b["videos"][0]["audio_number"] == 1
    assert b["tag_map"]["@V1"] == "<Video 1>"
    assert b["tag_map"]["@A1"] == "<Audio 2>"
    assert b["tag_map"]["@Mara"] == "<Subject 1>"
    assert "<Subject 1> walks home" in b["prompt"]


def test_keyframe_named_in_prompt_becomes_a_picture(harbor):
    b, _ = _build(harbor, 1)
    assert b["tag_map"]["@P3"] == "<Picture 2>"
    assert "holding <Picture 2>" in b["prompt"]


def test_task_tags_and_guides(harbor):
    b, plan = _build(harbor, 1)
    assert b["tags"][0] == "reference generation"
    assert "video continuation" in b["tags"]
    assert b["guides"][0] == {"type": "clip", "source": "prev_scene_tail", "frames": 39, "frame_idx": 0, "audio": True}
    later = [build_pass(harbor, harbor["scenes"][1], 1, plan, x) for x in plan["passes"][1:]]
    assert any(g["source"] == "asset" for b2 in later for g in b2["guides"])  # the 25 s letter keyframe


def test_dialogue_line_format(harbor):
    plan = plan_scene(harbor, harbor["scenes"][1], 1)
    texts = [build_pass(harbor, harbor["scenes"][1], 1, plan, x)["prompt"] for x in plan["passes"]]
    joined = "\n".join(texts)
    assert joined.count("<d>[English] Almost home.</d>") == 1
    assert "(S1) mutters" in joined


def test_unknown_tags_are_reported(harbor):
    p = copy.deepcopy(harbor)
    p["scenes"][1]["prompt"]["sections"]["summary"] += " @Nobody looks at @P9."
    b, _ = _build(p, 1)
    assert set(b["unknown"]) == {"@Nobody", "@P9"}


def test_raw_mode_and_pass_override(harbor):
    p = copy.deepcopy(harbor)
    p["scenes"][1]["prompt"].update(mode="raw", raw="@Mara walks. @V1 camera.")
    b, _ = _build(p, 1)
    assert b["prompt"].startswith("[reference generation")
    assert "<Subject 1> walks. <Video 1> camera." in b["prompt"]
    p["scenes"][1]["prompt"]["pass_prompts"] = {"1": "[video continuation] custom @Mara"}
    b, _ = _build(p, 1)
    assert b["prompt"] == "[video continuation] custom <Subject 1>"


def test_reanchor_rule_drops_the_tail_clip(harbor):
    p = copy.deepcopy(harbor)
    p["global"]["continuity"]["reanchor_after"] = 0
    b, _ = _build(p, 1)
    assert b["guides"][0]["source"] == "prev_scene_last"


def test_analysis_statuses_and_keys(harbor, store):
    r = analyze(harbor, store)
    assert {s["status"] for s in r["scenes"].values()} == {"missing"}
    k1 = r["scenes"]["s_long"]["key"]
    # an upstream change makes the continuing scene stale-by-key too
    p = copy.deepcopy(harbor)
    p["scenes"][0]["shots"][0]["text"] = "boats rock, gulls circle"
    r2 = analyze(p, store)
    assert r2["scenes"]["s_one"]["key"] != r["scenes"]["s_one"]["key"]
    assert r2["scenes"]["s_long"]["key"] != k1
    assert r2["scenes"]["s_short"]["key"] == r["scenes"]["s_short"]["key"]


def test_cached_status_and_lock(harbor, store):
    r = analyze(harbor, store)
    store.add_take("s_one", {"id": "v1", "key": r["scenes"]["s_one"]["key"], "files": {}})
    r = analyze(harbor, store)
    assert r["scenes"]["s_one"]["status"] == "cached"
    p = copy.deepcopy(harbor)
    p["scenes"][0]["duration"] = 9.0
    assert analyze(p, store)["scenes"]["s_one"]["status"] == "stale"
    p["scenes"][0]["lock"] = True
    r = analyze(p, store)
    assert r["scenes"]["s_one"]["status"] == "locked"
    # downstream depends on the locked take, so the edit does not make it stale
    assert r["scenes"]["s_long"]["key"] == analyze(harbor, store)["scenes"]["s_long"]["key"]


def test_asset_bytes_are_part_of_the_key(harbor, store, roots):
    import os
    k = analyze(harbor, store)["scenes"]["s_long"]["key"]
    with open(os.path.join(roots.input, "reelwright/harbor_lights/front.png"), "wb") as f:
        f.write(b"changed!")
    assert analyze(harbor, store)["scenes"]["s_long"]["key"] != k


def test_lint(harbor, store):
    p = copy.deepcopy(harbor)
    p["scenes"][1]["dialogue"].append({"speaker": "", "t": 40, "text": "", "language": ""})
    p["scenes"][1]["refs"].append({"asset": "a_gone", "role": "reference"})
    msgs = [x["message"] for x in analyze(p, store)["issues"]]
    assert any("after the scene ends" in m for m in msgs)
    assert any("no speaker" in m for m in msgs)
    assert any("no language tag" in m for m in msgs)
    assert any("deleted asset" in m for m in msgs)
    assert any("split into" in m for m in msgs)


def test_plan_response_shape(harbor, store):
    out = plan_response(analyze(harbor, store))
    s = out["scenes"]["s_long"]
    assert set(s) >= {"status", "key", "passes", "prompts", "issues", "takes"}
    assert {"index", "start", "end", "gen_frames", "keep_in", "keep_out", "seam_before", "overlap_frames", "seed"} <= set(s["passes"][0])
    # [OLD 2026-11-03 v0.4.3->v0.5.0] assert out["timeline"]["total"] == 42.5
    # added 2026-11-03 v0.5.0: the timeline is the cut, so the tail scene's 39 repeated frames overlap the scene before
    assert out["timeline"]["total"] == pytest.approx(42.5 - 39 / 24)


# added 2026-11-02 v0.2.0: output follows MiniMax's official Ref2VA guide (ref-en.txt)
def test_ref2va_sections_follow_the_guide(harbor):
    b, _ = _build(harbor, 1)
    heads = [line for line in b["prompt"].split("\n") if line.endswith(":") and " " not in line]
    assert heads == ["subject_definitions:", "summary:", "retention_analysis:", "detailed_description:",
                     "overall_soundscape:", "non_diegetic_music:"]
    for old in ("Subjects:", "Retention:", "Shots:", "Single continuous take", "[Shot1]"):
        assert old not in b["prompt"]
    assert "<Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 1>." in b["prompt"]
    assert "<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - identity and appearance are retained." in b["prompt"]
    assert "[Shot 1] A wide shot: Mara leaves the pier." in b["prompt"]
    assert "[Shot 2] At 00:06.000, the shot cuts to a tracking shot: along the seawall." in b["prompt"]
    assert "summary:\n[reference generation + video continuation + audio reference] <Subject 1> walks home" in b["prompt"]
    assert b["prompt"].endswith("overall_soundscape:\nN/A\n\nnon_diegetic_music:\nN/A")


def test_speaker_ids_follow_speaking_order_per_pass(harbor):
    p = copy.deepcopy(harbor)
    p["cast"].append({"id": "c_finn", "name": "Finn", "speaker": "S7", "kind": "character", "anchors": [],
                      "outfits": [], "description": "", "voice": "", "lora": {"name": "", "strength": 1}})
    s = p["scenes"][0]
    s["cast"] = [{"id": "c_mara", "outfit": ""}, {"id": "c_finn", "outfit": ""}]
    s["dialogue"] = [{"id": "d_a", "speaker": "c_finn", "t": 1.0, "text": "Late again", "language": "English", "delivery": "calls out"},
                     {"id": "d_b", "speaker": "c_mara", "t": 3.0, "text": "Sorry!", "language": "English", "delivery": ""}]
    b, _ = _build(p, 0)
    assert "<Subject 2> (S1) calls out, <d>[English] Late again.</d>" in b["prompt"]
    assert "<Subject 1> (S2) says, <d>[English] Sorry!</d>" in b["prompt"]
    assert "<Audio 1> is the voice-timbre reference for <Subject 1> (S2)." in b["prompt"]
    assert "(S" not in b["prompt"].split("retention_analysis:")[1].split("detailed_description:")[0]


def test_reference_pictures_become_subjects(harbor):
    p = copy.deepcopy(harbor)
    p["assets"].append({"id": "a_pier", "code": "P9", "kind": "image", "name": "pier", "file": p["assets"][0]["file"],
                        "category": "location", "description": "the wooden pier at dusk", "defaults": {}})
    p["scenes"][0]["refs"] = [{"id": "r_pier", "asset": "a_pier", "role": "reference", "keep": ["planks", "lamps"]}]
    p["scenes"][0]["shots"][0]["text"] = "boats rock beside @P9"
    b, _ = _build(p, 0)
    assert b["tag_map"]["@P9"] == "<Subject 1>"
    assert "<Subject 1> is the wooden pier at dusk, shown in <Picture 1>." in b["prompt"]
    assert "<Subject 1> (appears in [Shot 1]): fully_preserved - planks and lamps are retained." in b["prompt"]
    assert "boats rock beside <Subject 1>" in b["prompt"]


# added 2026-11-02 v0.3.4: an asset's description reaches every scene, including through a character's anchors
def test_asset_description_reaches_every_scene_and_character(harbor):
    from reelwright.model import cast_description, project_index
    p = copy.deepcopy(harbor)
    mara = p["cast"][0]
    mara["description"] = ""
    p["assets"][1]["description"] = "side view of the woman, auburn bob"  # a_side, second anchor
    assets = project_index(p)["assets"]
    assert cast_description(mara, assets) == ("side view of the woman, auburn bob", "a_side")
    p["assets"][0]["description"] = "a woman in her thirties with short auburn hair."  # a_front, first anchor wins
    assert cast_description(mara, project_index(p)["assets"]) == ("a woman in her thirties with short auburn hair", "a_front")
    p["scenes"][1]["cast"] = [{"id": "c_mara", "outfit": ""}]
    b, _ = _build(p, 1)
    assert "<Subject 1> is Mara, a woman in her thirties with short auburn hair, shown in <Picture 1>." in b["prompt"]
    # an edit to the asset changes the prompt; the character's own description still wins
    p["assets"][0]["description"] = "a woman with a grey wool coat"
    b, _ = _build(p, 1)
    assert "<Subject 1> is Mara, a woman with a grey wool coat, shown in" in b["prompt"]
    mara["description"] = "Mara, harbour clerk"
    b, _ = _build(p, 1)
    assert "<Subject 1> is Mara, Mara, harbour clerk, shown in" in b["prompt"]


def test_llm_context_uses_live_descriptions(harbor):
    import pytest
    pytest.importorskip("aiohttp")
    from reelwright.llm import scene_context
    p = copy.deepcopy(harbor)
    p["cast"][0]["description"] = ""
    p["assets"][0]["description"] = "a woman with a grey wool coat"
    p["scenes"][0]["refs"] = [{"id": "r_l", "asset": "a_letter", "role": "reference", "time": 0, "retention": "", "keep": [], "soundtrack": False}]
    p["scenes"][0]["cast"] = [{"id": "c_mara", "outfit": ""}]
    p["assets"][3]["description"] = "a folded letter with a red wax seal"
    ctx = scene_context(p, p["scenes"][0])
    assert "a folded letter with a red wax seal" in ctx and "a woman with a grey wool coat" in ctx


# ---- added 2026-11-03 v0.4.1: written sections no longer repeat the automatic ones -------------------------------

def _sections(prompt):
    out, key = {}, None
    for line in prompt.split("\n"):
        if line.rstrip(":") in ("subject_definitions", "summary", "retention_analysis", "detailed_description",
                                "overall_soundscape", "non_diegetic_music") and line.endswith(":"):
            key = line[:-1]
            out[key] = []
        elif key and line.strip():
            out[key].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def test_written_subject_line_replaces_the_automatic_one(harbor):
    s = harbor["scenes"][1]
    s["prompt"]["auto"] = {"subjects": True, "retention": True, "shots": True}
    s["prompt"]["sections"]["subject_definitions"] = "@Mara is a tall woman in a navy coat."
    s["prompt"]["sections"]["retention_analysis"] = "@Mara (appears in [Shot 1]): fully_preserved - her face is retained."
    s["prompt"]["sections"]["summary"] = "[reference generation + audio reference + keyframe completion] Mara walks home."
    b, _ = _build(harbor, 1)
    sec = _sections(b["prompt"])
    subj = [x for x in sec["subject_definitions"].split("\n") if x.startswith("<Subject 1>")]
    assert subj == ["<Subject 1> is a tall woman in a navy coat, shown in <Picture 1>."]  # the picture link is added back
    assert sec["retention_analysis"].count("<Subject 1> (") == 1 and "her face is retained" in sec["retention_analysis"]
    assert sec["summary"].count("[") == 1 and sec["summary"].endswith("Mara walks home.")


def test_written_subject_line_without_auto_keeps_its_picture(harbor):
    s = harbor["scenes"][0]
    s["cast"] = [{"id": "c_mara"}]
    s["prompt"]["auto"] = {"subjects": False, "retention": False, "shots": False}
    s["prompt"]["sections"]["subject_definitions"] = "<Subject 1> is Mara, a woman with auburn hair."
    b, _ = _build(harbor, 0)
    assert _sections(b["prompt"])["subject_definitions"] == "<Subject 1> is Mara, a woman with auburn hair, shown in <Picture 1>."


def test_written_shot_replaces_the_automatic_shot_and_keeps_its_dialogue(harbor):
    s = harbor["scenes"][1]
    s["prompt"]["auto"]["shots"] = True
    s["prompt"]["sections"]["detailed_description"] = "Live-action, soft rain light.\n[Shot 1] A wide shot: @Mara walks along the pier in the drizzle."
    plan = plan_scene(harbor, s, 1)
    texts = [build_pass(harbor, s, 1, plan, x)["prompt"] for x in plan["passes"]]
    first = _sections(texts[0])["detailed_description"].split("\n")
    assert first[0] == "Live-action, soft rain light." and first[1].startswith("[Shot 1] A wide shot: <Subject 1> walks")
    assert sum(x.startswith("[Shot 1]") for x in first) == 1
    # the pass with the spoken line: written [Shot N] lines elsewhere don't drop it
    spoken = [t for t in texts if "Almost home." in t]
    assert spoken and all(t.count("<d>[English] Almost home.</d>") == 1 for t in spoken)


def test_tidy_rewrite():
    from reelwright.prompt import tidy_rewrite
    before = {"subject_definitions": "", "summary": "old", "retention_analysis": "", "detailed_description": "",
              "overall_soundscape": "", "non_diegetic_music": ""}
    whole = ("subject_definitions:\n<Subject 1> is Mara, shown in <Picture 1>.\n\nsummary:\n[reference generation] "
             "<Subject 1> walks home.\n\nretention_analysis:\n<Subject 1> (appears in [Shot 1]): fully_preserved - face.\n\n"
             "detailed_description:\nLive-action.\n[Shot 1] <Subject 1> walks.\n\noverall_soundscape:\nRain.\n\n"
             "non_diegetic_music:\nN/A")
    tag_map = {"@Mara": "<Subject 1>", "@P1": "<Picture 1>", "@Old Keeper": "<Subject 2>"}
    out = tidy_rewrite({"detailed_description": whole}, before, {"subjects": True, "retention": True, "shots": True}, tag_map)
    assert out["subject_definitions"] == "" and out["retention_analysis"] == ""   # the editor writes these
    assert out["summary"] == "[reference generation] @Mara walks home."
    assert out["detailed_description"] == "Live-action." and out["overall_soundscape"] == "Rain."
    out = tidy_rewrite({"summary": "summary: <Subject 2> waits.", "subject_definitions": "<Subject 2> is old."}, before,
                       {"subjects": False}, tag_map)
    assert out["summary"] == "@{Old Keeper} waits." and out["subject_definitions"] == "@{Old Keeper} is old."


# added 2026-11-03 v0.4.1: pack_sheet "auto" packs a character's anchors only when the pass would not fit 9 pictures
def test_auto_packing(harbor):
    s = harbor["scenes"][0]
    s["cast"] = [{"id": "c_mara"}]
    mara = harbor["cast"][0]
    extra = [{"id": "a_x%d" % i, "code": "", "kind": "image", "name": "x%d" % i, "file": "reelwright/harbor_lights/x%d.png" % i,
              "width": 800, "height": 1000, "defaults": {"role": "reference", "retention": "fully_preserved", "keep": [], "soundtrack": False}}
             for i in range(8)]
    harbor["assets"] += extra
    from reelwright.model import normalize_project
    p = normalize_project(harbor)
    p["cast"][0]["pack_sheet"] = "auto"
    p["cast"][0]["anchors"] = ["a_front", "a_side"] + [a["id"] for a in extra[:5]]   # 7 anchors
    b, _ = _build(p, 0)
    assert [len(x["assets"]) for x in b["images"]] == [1] * 7                          # fits: separate
    p["scenes"][0]["refs"] = [{"id": "r%d" % i, "asset": a["id"], "role": "reference"} for i, a in enumerate(extra[5:])]
    b, _ = _build(p, 0)
    assert [len(x["assets"]) for x in b["images"]] == [7, 1, 1, 1]                     # 10 pictures: the anchors pack
    assert "<Subject 1> is Mara" in b["prompt"] and "shown in <Picture 1>." in b["prompt"]
    p["cast"][0]["pack_sheet"] = False
    assert len(_build(p, 0)[0]["images"]) == 10
    p["cast"][0]["pack_sheet"] = "nonsense"
    assert normalize_project(p)["cast"][0]["pack_sheet"] is True
