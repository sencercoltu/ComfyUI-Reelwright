import copy

import pytest  # added 2026-11-03 v0.5.0

from reelwright.analysis import analyze, plan_response
from reelwright.planner import plan_scene
from reelwright.prompt import build_pass


def _build(p, i, n=0):
    plan = plan_scene(p, p["scenes"][i], i)
    return build_pass(p, p["scenes"][i], i, plan, plan["passes"][n]), plan


def test_reference_numbering_follows_native_order(harbor):
    # v0.6.0: pass 1 (0-14.4 s) gets the cast sheet and the dolly video whose soundtrack takes <Audio 1>; Mara speaks
    # only in pass 2 (her voice comes after the video's sound there) and the 25 s letter keyframe guides pass 3
    b, _ = _build(harbor, 1)
    assert [img["assets"] for img in b["images"]] == [["a_front", "a_side"]]
    assert b["videos"][0]["audio_number"] == 1
    assert b["tag_map"]["@V1"] == "<Video 1>"
    assert "@A1" not in b["tag_map"] and not any(a.get("cast") for a in b["audios"])
    assert b["tag_map"]["@Mara"] == "<Subject 1>"
    assert "<Subject 1> walks home" in b["prompt"]
    b2, _ = _build(harbor, 1, 1)
    assert b2["tag_map"]["@A1"] == "<Audio 2>"
    b3, _ = _build(harbor, 1, 2)
    assert [img["assets"] for img in b3["images"]] == [["a_front", "a_side"], ["a_letter"]]


def test_keyframe_named_in_prompt_becomes_a_picture(harbor):
    # v0.6.0: only in the pass the keyframe guides; the other passes name it in words
    b, _ = _build(harbor, 1, 2)
    assert b["tag_map"]["@P3"] == "<Picture 2>"
    assert "holding <Picture 2>" in b["prompt"]
    assert "<Picture 2> is the keyframe of [Shot 1] at 00:03.000." in b["prompt"]
    b1, _ = _build(harbor, 1, 0)
    assert "@P3" not in b1["tag_map"] and "holding the letter" in b1["prompt"] and not b1["unknown"]
    assert [x["level"] for x in b1["issues"]] == ["info"] and "guides another pass" in b1["issues"][0]["message"]


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
    # [OLD v0.5.1] assert set(b["unknown"]) == {"@Nobody", "@P9"}
    # v0.6.0: only a name that looks like an asset code is an error; any other unknown name is a warning
    assert b["unknown"] == ["@P9"]
    levels = {x["tag"]: x["level"] for x in b["issues"]}
    assert levels["@P9"] == "error" and levels["@Nobody"] == "warn"
    assert "@Nobody looks at @P9." in b["prompt"]


def test_raw_mode_and_pass_override(harbor):
    p = copy.deepcopy(harbor)
    p["scenes"][1]["prompt"].update(mode="raw", raw="@Mara walks. @V1 camera.")
    b, _ = _build(p, 1)
    assert b["prompt"].startswith("[reference generation")
    assert "<Subject 1> walks. <Video 1> camera." in b["prompt"]
    p["scenes"][1]["prompt"]["pass_prompts"] = {"1": "[video continuation] custom @Mara"}
    b, _ = _build(p, 1)
    # [OLD v0.5.1] assert b["prompt"] == "[video continuation] custom <Subject 1>"
    # v0.6.0: written task tags are replaced by the ones the pass needs, so they are there exactly once
    assert b["prompt"] == "[reference generation + video continuation + audio reference] custom <Subject 1>"


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


# ---- added 2026-11-03 v0.6.0 --------------------------------------------------------------------------------------
from reelwright import prompt as P  # noqa: E402
from reelwright.validate import lint_project  # noqa: E402


def _passes(p, i):
    plan = plan_scene(p, p["scenes"][i], i)
    return [build_pass(p, p["scenes"][i], i, plan, x) for x in plan["passes"]], plan


def _desc(prompt):
    return _sections(prompt)["detailed_description"]


def _lint(p, exists=lambda a: True):
    from reelwright.planner import plan_project
    plans = plan_project(p)
    builds = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
              for i, s in enumerate(p["scenes"])}
    return lint_project(p, plans, builds, exists)


def test_tag_syntax():
    tags = [m.group(0) for m in P.tag_re().finditer(
        "@Mara's coat, bob@example.com, @@literal, @Ömer, @O'Brien. @Anna. @{Old Keeper} @P3. @अनुज x_@no @a-b.c")]
    assert tags == ["@Mara's", "@Ömer", "@O'Brien", "@Anna", "@{Old Keeper}", "@P3", "@अनुज", "@a-b.c"]
    assert P.mentioned_codes("see @P3. and @V1's sound, mail x@P9.com") == {"P3", "V1", "V1'S"}
    assert P.tag_token("Mara") == "@Mara" and P.tag_token("O'Brien") == "@O'Brien"
    assert P.tag_token("Old Keeper") == "@{Old Keeper}" and P.tag_token("Dr.") == "@{Dr.}"
    assert P.name_key(" O’Brien ") == "o'brien"


def test_escapes_mail_possessives_and_unicode_names(harbor):
    p = copy.deepcopy(harbor)
    p["cast"].append({"id": "c_obrien", "name": "O’Brien", "kind": "character", "anchors": ["a_letter"]})
    p["cast"].append({"id": "c_omer", "name": "Ömer", "kind": "character", "anchors": []})
    s = p["scenes"][0]
    s["cast"] = [{"id": "c_mara"}, {"id": "c_obrien"}, {"id": "c_omer"}]
    s["prompt"]["sections"]["summary"] = ("@Mara's coat flaps; @O'Brien waves at @Ömer. Mail mara@harbor.org or "
                                          "write @@harbor. @Finn waves.")
    from reelwright.model import normalize_project
    p = normalize_project(p)
    b, _ = _build(p, 0)
    summary = _sections(b["prompt"])["summary"]
    assert "<Subject 1>'s coat flaps; <Subject 2> waves at <Subject 3>." in summary
    assert "mara@harbor.org or write @harbor." in summary
    assert "@Finn waves." in summary and b["unknown"] == []
    assert [x["level"] for x in b["issues"]] == ["warn"] and "@@" in b["issues"][0]["message"]


def test_cast_member_not_in_scene_is_written_as_the_name(harbor):
    p = copy.deepcopy(harbor)
    p["scenes"][0]["prompt"]["sections"]["summary"] = "Boats rock while @Mara watches."
    b, _ = _build(p, 0)
    assert "while Mara watches." in b["prompt"] and b["unknown"] == []
    assert b["issues"][0]["level"] == "warn" and "not in this scene's cast" in b["issues"][0]["message"]


# Fix-first #6: @soundtrack in a pass that gets no song
def test_soundtrack_tag_without_song_is_not_an_error(harbor):
    p = copy.deepcopy(harbor)
    p["scenes"][0]["prompt"]["sections"]["summary"] = "Boats rock to @soundtrack."
    b, _ = _build(p, 0)
    assert "Boats rock to the soundtrack." in b["prompt"] and b["unknown"] == []
    assert b["issues"][0]["level"] == "warn" and "no soundtrack track" in b["issues"][0]["message"]
    # a song that plays only in the second scene: the first scene's pass gets none
    p["assets"].append({"id": "a_song", "code": "A9", "kind": "audio", "name": "song", "file": p["assets"][2]["file"],
                        "duration": 20.0, "defaults": {}, "description": ""})
    p["soundtrack"] = [{"id": "t_1", "asset": "a_song", "start": 30.0, "sync": True, "mix": True}]
    from reelwright.model import normalize_project
    p = normalize_project(p)
    b, _ = _build(p, 0)
    assert "Boats rock to the soundtrack." in b["prompt"] and not b["unknown"]
    assert [x["level"] for x in b["issues"]] == ["info"] and "no part of the soundtrack" in b["issues"][0]["message"]
    issues = _lint(p)
    assert not any("soundtrack" in x["message"] and x["level"] == "error" for x in issues)
    assert any(x["level"] == "info" and "@soundtrack" in x["message"] and x.get("scene_id") == "s_one" for x in issues)


# Fix-first #13: pass overrides, "Edit this pass by hand", raw prompts starting with [Shot 1]
def test_task_tags_once_in_overrides_and_raw(harbor):
    p = copy.deepcopy(harbor)
    s = p["scenes"][1]
    builds, plan = _passes(p, 1)
    tags = "[reference generation + video continuation + audio reference]"
    s["prompt"]["pass_prompts"] = {"1": builds[0]["prompt"]}  # Edit this pass by hand: a copy of the built prompt
    b = build_pass(p, s, 1, plan, plan["passes"][0])
    assert b["prompt"] == builds[0]["prompt"]
    assert b["prompt"].count(tags) == 1 and b["prompt"].startswith("subject_definitions:\n")
    assert "summary:\n" + tags + " <Subject 1> walks home" in b["prompt"]
    # a pass prompt from Split with other (stale) tags, in any case, and an N/A summary
    s["prompt"]["pass_prompts"] = {"1": "subject_definitions:\n@Mara is Mara.\n\nsummary:\n[Reference Generation] "
                                         "@Mara walks.\n\ndetailed_description:\n[Shot 1] Rain.",
                                   "2": "subject_definitions:\nN/A\n\nsummary:\nN/A\n\ndetailed_description:\nRain."}
    b = build_pass(p, s, 1, plan, plan["passes"][0])
    assert "summary:\n" + tags + " <Subject 1> walks.\n" in b["prompt"] and b["prompt"].count("[") == 2
    b2 = build_pass(p, s, 1, plan, plan["passes"][1])
    assert "summary:\n[reference generation + audio reference]\n\ndetailed_description:" in b2["prompt"]
    # a raw prompt that starts with [Shot 1] still gets its tags
    s["prompt"].update(mode="raw", raw="[Shot 1] @Mara walks.", pass_prompts={})
    b = build_pass(p, s, 1, plan, plan["passes"][0])
    assert b["prompt"] == tags + " [Shot 1] <Subject 1> walks."


def test_written_shot_lines_go_to_the_pass_that_holds_the_shot(harbor):
    p = copy.deepcopy(harbor)
    s = p["scenes"][1]
    s["prompt"]["sections"]["detailed_description"] = (
        "Live action, rain light.\n[Shot 3] At 00:14.375, the shot cuts to a medium shot: rain hammers the seawall. "
        "At 00:16.000, @Mara mutters, <d>[English] Almost home.</d>\n[Shot 4] She opens the door.\n"
        "[Shot 5] An insert of the key.")
    builds, plan = _passes(p, 1)   # passes: shots 1-2 | shot 3 (from 14.375 s) | shot 4 (from 22 s)
    d1, d2, d3 = (_desc(b["prompt"]).split("\n") for b in builds)
    assert d1 == ["Live action, rain light.", "[Shot 1] A wide shot: Mara leaves the pier.",
                  "[Shot 2] At 00:06.000, the shot cuts to a tracking shot: along the seawall."]
    # shot 3 is pass 2's first shot: no cut time, and the line's time is pass time; the spoken line is not repeated
    assert d2 == ["Live action, rain light.", "[Shot 1] A medium shot: rain hammers the seawall. At 00:01.625, "
                  "<Subject 1> mutters, <d>[English] Almost home.</d>"]
    assert d3 == ["Live action, rain light.", "[Shot 1] She opens the door.", "[Shot 2] An insert of the key."]
    assert builds[2]["issues"][0]["level"] == "info" and "[Shot 5]" in builds[2]["issues"][0]["message"]
    # the same without automatic shots
    s["prompt"]["auto"]["shots"] = False
    builds, _ = _passes(p, 1)
    assert _desc(builds[0]["prompt"]) == "Live action, rain light."
    assert _desc(builds[2]["prompt"]) == "Live action, rain light.\n[Shot 1] She opens the door.\n[Shot 2] An insert of the key."


def test_written_shot_lines_across_overlap_seams(harbor):
    p = copy.deepcopy(harbor)
    p["global"]["long"]["seam_mode"] = "overlap"
    s = p["scenes"][1]
    s["prompt"]["sections"]["detailed_description"] = "[Shot 2] A tracking shot along the seawall.\n[Shot 3] Rain."
    builds, plan = _passes(p, 1)
    assert [[(x["number"], x["continuing"]) for x in q["shots"]] for q in plan["passes"]][:2] == \
        [[(1, False), (2, False), (3, False)], [(2, True), (3, False), (4, False)]]
    d1, d2 = _desc(builds[0]["prompt"]).split("\n"), _desc(builds[1]["prompt"]).split("\n")
    assert d1[1:] == ["[Shot 2] At 00:06.000, the shot cuts to a tracking shot along the seawall.",
                      "[Shot 3] At 00:14.375, the shot cuts to rain."]
    assert d2[0] == "[Shot 1] The shot continues seamlessly from the previous moment. A tracking shot along the seawall."
    assert d2[1].startswith("[Shot 2] At 00:00.917, the shot cuts to rain.")


def test_rewrite_keeps_hand_written_shot_lines():
    before = {k: "" for k in P.REF2VA_SECTIONS}
    before["detailed_description"] = "Live action.\n[Shot 3] A medium shot: rain."
    answer = {"detailed_description": "Live action, cold blue light.\n[Shot 1] A wide shot.\n[Shot 3] A medium shot: "
                                      "rain hammers the seawall.", "summary": ["Mara walks home.", "Rain builds."]}
    out = P.tidy_rewrite(answer, before, {"subjects": True, "retention": True, "shots": True}, {})
    assert out["detailed_description"] == "Live action, cold blue light.\n[Shot 3] A medium shot: rain hammers the seawall."
    assert out["summary"] == "Mara walks home.\nRain builds."
    out = P.tidy_rewrite({"summary": "x"}, before, {"shots": True}, {})   # left out: kept as it was
    assert out["detailed_description"] == "Live action.\n[Shot 3] A medium shot: rain."


def test_guide_clip_named_in_text_is_a_video_of_its_pass(harbor):
    p = copy.deepcopy(harbor)
    s = p["scenes"][1]
    p["assets"].append({"id": "a_wave", "code": "V2", "kind": "video", "name": "wave", "file": p["assets"][4]["file"],
                        "duration": 2.0, "defaults": {}, "description": "a wave breaking over the wall"})
    s["refs"].append({"id": "r_wave", "asset": "a_wave", "role": "keyframe", "time": 23.0})
    s["prompt"]["sections"]["summary"] += " The wall is hit by @V2."
    builds, plan = _passes(p, 1)
    b3 = builds[2]
    assert b3["tag_map"]["@V2"] == "<Video 2>" and b3["videos"][1]["guide"] is True
    assert "video continuation" in b3["tags"]
    assert "<Video 2> is the clip placed in [Shot 1] at 00:01.000; the target video passes through its frames, " \
           "showing a wave breaking over the wall." in b3["prompt"]
    assert "<Video 2> ([Shot 1] clip at 00:01.000): fully_preserved - its frames are kept as they are." in b3["prompt"]
    assert any(g["type"] == "clip" and g["source"] == "asset" for g in b3["guides"])
    assert "hit by a wave breaking over the wall." in builds[0]["prompt"] and "@V2" not in builds[0]["tag_map"]


def test_prepare_context_gives_the_same_prompts_and_is_reused(harbor, monkeypatch):
    from reelwright.planner import plan_project
    p = copy.deepcopy(harbor)
    plans = plan_project(p)
    plain = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
             for i, s in enumerate(p["scenes"])}
    ctx = P.prepare(p)
    calls = []
    real = P.project_index
    monkeypatch.setattr(P, "project_index", lambda q: calls.append(1) or real(q))
    with_ctx = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x, ctx=ctx) for x in plans[s["id"]]["passes"]]
                for i, s in enumerate(p["scenes"])}
    assert len(calls) <= 1   # worked out once, in the shared context, not per pass
    assert {k: [b["prompt"] for b in v] for k, v in with_ctx.items()} == {k: [b["prompt"] for b in v] for k, v in plain.items()}
    assert lint_project(p, plans, with_ctx, lambda a: True, ctx=ctx) == lint_project(p, plans, plain, lambda a: True)
    other = copy.deepcopy(p)   # a context of another project state is not used
    other["cast"][0]["name"] = "Nadia"
    b = build_pass(p, p["scenes"][1], 1, plans["s_long"], plans["s_long"]["passes"][0], ctx=P.prepare(other))
    assert b["tag_map"]["@Mara"] == "<Subject 1>"


def test_tail_after_a_very_short_scene_is_guided_by_the_last_frame(harbor):
    p = copy.deepcopy(harbor)
    p["scenes"][0]["duration"] = 0.1   # 2 frames: no 5-frame tail to continue from
    b, _ = _build(p, 1)
    assert b["guides"][0]["source"] == "prev_scene_last" and "video continuation" not in b["tags"]


# ---- lint (validate.py) ----

def test_lint_missing_files_are_scene_errors(harbor):
    p = copy.deepcopy(harbor)
    p["assets"].append({"id": "a_unused", "code": "P8", "kind": "image", "name": "spare", "file": "x/spare.png",
                        "defaults": {}, "description": ""})
    issues = _lint(p, exists=lambda a: a["id"] not in ("a_letter", "a_voice", "a_side", "a_unused"))
    mine = [x for x in issues if "file is missing" in x["message"]]
    assert {(x.get("scene_id"), x["level"]) for x in mine} == {("s_long", "error"), (None, "warn")}
    # the letter keyframe, Mara's voice (pass 2) and her anchor picture are all sent with s_long
    assert {x["message"] for x in mine if x.get("scene_id")} == {
        "02 The long walk home: P2 (Mara side) file is missing", "02 The long walk home: P3 (letter) file is missing",
        "02 The long walk home: A1 (voice) file is missing"}
    assert [x["message"] for x in mine if not x.get("scene_id")] == ["P8 (spare) file is missing (no scene uses it)"]


def test_lint_clip_guides_must_fit_their_pass(harbor):
    # the renderer fits a long clip (render.fit_clip), so the lint says how much is used and how to keep it all
    p = copy.deepcopy(harbor)
    p["scenes"][1]["refs"].append({"id": "r_end", "asset": "a_dolly", "role": "last_frame"})      # 240 frames of room
    p["scenes"][1]["refs"].append({"id": "r_late", "asset": "a_dolly", "role": "keyframe", "time": 31.0})
    p["scenes"][2]["refs"].append({"id": "r_end2", "asset": "a_dolly", "role": "last_frame"})     # 2.5 s scene
    clips = [x for x in _lint(p) if "-frame clip" in x["message"]]
    msgs = {x["message"]: x["level"] for x in clips}
    assert len(clips) == 2 and set(msgs.values()) == {"warn"}
    assert msgs["02 The long walk home pass 3: keyframe V1 is a 90-frame clip (3.75 s), but the 243-frame pass has room "
                "for 27 of them, so only its first 22 frames are used; move it to 28.38 s or earlier, or shorten the "
                "clip to 0.92 s"] == "warn"
    assert msgs["03 Hand on the door: last frame V1 is a 90-frame clip (3.75 s), but the 124-frame pass has room for 89 "
                "of them, so only its last 73 frames are used; shorten the clip to 3.04 s, or make the scene longer"] == "warn"
    p["scenes"][1]["refs"][-1]["time"] = 25.0   # fits: 72 + 90 <= 243
    assert not any("keyframe V1" in x["message"] for x in _lint(p))


def test_lint_dialogue_in_the_tail_overlap_and_before_the_scene(harbor):
    p = copy.deepcopy(harbor)
    s = p["scenes"][1]
    s["dialogue"].append({"id": "d_early", "speaker": "c_mara", "t": 1.0, "text": "Hm.", "language": "English"})
    s["dialogue"].append({"id": "d_neg", "speaker": "c_mara", "t": -0.5, "text": "Oh.", "language": "English"})
    s["shots"].append({"id": "h_x", "t": 0.5, "camera": "", "text": "a gull"})
    from reelwright.model import normalize_project
    msgs = [(x["level"], x["message"]) for x in _lint(normalize_project(p)) if x.get("scene_id") == "s_long"]
    assert ("warn", "02 The long walk home: a dialogue line at 1.00 s is inside the 1.62 s tail overlap, which the "
                    "cut trims away; move it to 1.62 s or later") in msgs
    assert any(lvl == "warn" and "-0.50 s starts before the scene" in m for lvl, m in msgs)
    assert any(lvl == "warn" and "a shot starts at 0.50 s, inside the 1.62 s tail overlap" in m for lvl, m in msgs)


def test_lint_budget_counts_video_sound_and_levels_of_tags(harbor):
    p = copy.deepcopy(harbor)
    s = p["scenes"][0]
    for k in range(3):
        p["assets"].append({"id": "a_fx%d" % k, "code": "A%d" % (5 + k), "kind": "audio", "name": "fx", "duration": 3.0,
                            "file": p["assets"][2]["file"], "defaults": {}, "description": ""})
        s["refs"].append({"id": "r_fx%d" % k, "asset": "a_fx%d" % k, "role": "reference"})
    s["refs"].append({"id": "r_dv", "asset": "a_dolly", "role": "reference", "soundtrack": True})
    s["prompt"]["sections"]["summary"] = "Boats rock, @handle tweets, @P9 and @tail."
    s["prompt"]["pass_prompts"] = {"4": "old text"}
    from reelwright.model import normalize_project
    issues = [x for x in _lint(normalize_project(p)) if x.get("scene_id") == "s_one"]
    msgs = {x["message"]: x["level"] for x in issues}
    assert msgs["01 Harbor at dusk: 4 reference audio clips, counting a video's own sound and the soundtrack (up to 3)"] == "warn"
    assert not any("audio refs total" in m for m in msgs)   # 3 x 3 s + the video's 4.2 s
    p["assets"][-1]["duration"] = 5.0
    msgs = {x["message"]: x["level"] for x in _lint(normalize_project(p)) if x.get("scene_id") == "s_one"}
    assert msgs["01 Harbor at dusk: audio refs total 15.2 s, counting a video's own sound and the soundtrack (max 15 s)"] == "warn"
    assert msgs["01 Harbor at dusk: @P9 matches no asset of this project"] == "error"
    assert msgs["01 Harbor at dusk: @handle is not a cast member, asset or @soundtrack, so it is written as plain text "
                "(write @@ for a literal @)"] == "warn"
    assert msgs["01 Harbor at dusk: @tail: this scene starts fresh, so there is no previous shot to continue"] == "warn"
    assert msgs["01 Harbor at dusk: the prompt written for pass 4 is not used, because the scene has 1 pass now"] == "warn"


# ---- added 2026-11-03 v0.6.0 review --------------------------------------------------------------------------------

def test_scene_assets_not_sent_with_a_pass_are_words_never_errors(harbor, store):
    """Bug 2: a cast voice goes only to the passes where that character speaks, so @A1 (Mara's voice) in another
    pass was the error "is not a reference of this scene" and blocked the render."""
    from reelwright.model import normalize_project
    p = copy.deepcopy(harbor)
    p["scenes"][1]["prompt"]["sections"]["overall_soundscape"] = "Rain; @Mara hums in the voice of @A1."
    p = normalize_project(p)
    b1, _ = _build(p, 1, 0)  # Mara speaks only in pass 2
    assert "hums in the voice of Mara's voice." in b1["prompt"] and b1["unknown"] == []
    assert [x["level"] for x in b1["issues"] if "@A1" in x["message"]] == ["info"]
    b2, _ = _build(p, 1, 1)
    assert "hums in the voice of <Audio 2>." in b2["prompt"] and b2["unknown"] == []
    sr = analyze(p, store)["scenes"]["s_long"]
    assert sr["status"] != "error" and not [x for x in sr["issues"] if x["level"] == "error"]
    # a voice with a description is written as the description
    p["assets"][2]["description"] = "A low, warm alto."
    b1, _ = _build(p, 1, 0)
    assert "hums in the voice of a low, warm alto." in b1["prompt"]
    # an outfit's non-picture asset (never sent) and a soundtrack file in a pass without the song: words, info
    p["assets"].append({"id": "a_coat", "code": "V7", "kind": "video", "name": "raincoat turn", "file": p["assets"][4]["file"],
                        "duration": 4.0, "defaults": {}, "description": ""})
    p["assets"].append({"id": "a_song", "code": "A9", "kind": "audio", "name": "song", "file": p["assets"][2]["file"],
                        "duration": 20.0, "defaults": {}, "description": ""})
    p["cast"][0]["outfits"] = [{"id": "o_rain", "name": "raincoat", "assets": ["a_coat"]}]
    p["cast"][0]["default_outfit"] = "o_rain"
    p["soundtrack"] = [{"id": "t_1", "asset": "a_song", "start": 300.0, "sync": True, "mix": True}]
    p["scenes"][1]["prompt"]["sections"]["overall_soundscape"] = "@Mara turns like @V7 while @A9 swells."
    p = normalize_project(p)
    b1, _ = _build(p, 1, 0)
    assert b1["unknown"] == [] and "turns like the raincoat turn while the soundtrack swells." in b1["prompt"]
    assert sorted(x["level"] for x in b1["issues"] if "@V7" in x["message"] or "@A9" in x["message"]) == ["info", "info"]
    # an asset of nothing in the scene is still an error
    p["scenes"][1]["prompt"]["sections"]["overall_soundscape"] = "Rain on @P3 and on @V7."
    p["cast"][0]["default_outfit"] = ""
    p = normalize_project(p)
    b1, _ = _build(p, 1, 0)
    assert b1["unknown"] == ["@V7"]


def test_written_shot_lines_move_only_timeline_times(harbor):
    """Bug 5 (v0.6.0 review): every MM:SS in a written [Shot N] line moved to pass time, clock times in the action
    and inside spoken lines too ("the last ferry leaves at 11:45" -> "at 11:30.625" in pass 2)."""
    p = copy.deepcopy(harbor)
    p["scenes"][1]["prompt"]["sections"]["detailed_description"] = (
        "[Shot 3] At 00:14.375, the shot cuts to a medium shot: Mara checks the clock reading 10:30 and says "
        "<d>[English] At 11:45, the last ferry leaves.</d> At 00:16.000, @Mara mutters.\n"
        "[Shot 4] At 00:22.000, the shot cuts to a wide shot: the station clock shows 22:05. At 10:30, nothing moves.")
    builds, _ = _passes(p, 1)   # passes: shots 1-2 | shot 3 (from 14.375 s) | shot 4 (from 22 s)
    d2, d3 = _desc(builds[1]["prompt"]), _desc(builds[2]["prompt"])
    assert "clock reading 10:30 and says <d>[English] At 11:45, the last ferry leaves.</d>" in d2
    assert "At 00:01.625, <Subject 1> mutters." in d2  # a timing cue inside the scene moves to pass time
    assert d2.startswith("[Shot 1] A medium shot:")
    assert "the station clock shows 22:05. At 10:30, nothing moves." in d3  # 10:30 is past the 32 s scene
    p["scenes"][1]["prompt"]["sections"]["detailed_description"] = (
        "[Shot 2] A tracking shot.\n[Shot 3] At 00:14.375, the shot cuts to rain: <d>[English] Meet me at 10:30.</d>")
    p["global"]["long"]["seam_mode"] = "overlap"
    builds, _ = _passes(p, 1)
    d2 = _desc(builds[1]["prompt"]).split("\n")
    assert d2[1].startswith("[Shot 2] At 00:00.917, the shot cuts to rain: <d>[English] Meet me at 10:30.</d>")


# ---- added 2026-11-04 v0.6.1 (review of v0.6.0) --------------------------------------------------------------------

def test_rewrite_keeps_hand_written_subject_and_retention_lines():
    """Review 1: with automatic subject definitions / retention lines off, a rewrite answer that left the key out
    emptied the hand-written text (the docstring says they keep their text)."""
    from reelwright.prompt import REF2VA_SECTIONS, tidy_rewrite
    before = {k: "" for k in REF2VA_SECTIONS}
    before.update(subject_definitions="@Mara is the keeper, shown in @P1.", retention_analysis="@Mara: face kept.",
                  summary="old")
    out = tidy_rewrite({"summary": "new"}, before, {"subjects": False, "retention": False, "shots": False}, {})
    assert out["summary"] == "new"
    assert out["subject_definitions"] == before["subject_definitions"]
    assert out["retention_analysis"] == before["retention_analysis"]
    # a key the answer does give still replaces the text, and automatic parts still keep theirs
    out = tidy_rewrite({"subject_definitions": "@Mara, older."}, before, {"subjects": False, "retention": True}, {})
    assert out["subject_definitions"] == "@Mara, older." and out["retention_analysis"] == "@Mara: face kept."
