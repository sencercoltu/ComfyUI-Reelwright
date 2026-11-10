"""Voices that stay the same from pass to pass: a character's voice description (cast
voice_desc) at their first line in every pass, the switch for it, the Issues warning for a character heard in several
passes with nothing that fixes the voice, Script import's voice, and Write prompts' Voices list."""

import copy

from reelwright import llm, prompt, validate
from reelwright.model import normalize_project
from reelwright.planner import plan_scene


def narrated(harbor):
    """The harbor with a narrator (no pictures, no voice file) speaking twice in pass 2 and once in pass 3 of the
    32 s scene, and Mara's voice file taken away."""
    p = copy.deepcopy(harbor)
    p["cast"].append({"id": "c_nar", "name": "Narrator", "kind": "character", "speaker": "S2"})
    p["cast"][0]["voice"] = ""
    s = p["scenes"][1]
    s["dialogue"] += [{"id": "d_n1", "speaker": "c_nar", "t": 15.0, "text": "The storm came early.", "delivery": "voiceover"},
                      {"id": "d_n2", "speaker": "c_nar", "t": 19.0, "text": "She did not look back."},
                      {"id": "d_n3", "speaker": "c_nar", "t": 26.0, "text": "Home was near."}]
    return normalize_project(p)


def pass_prompt(p, k):
    s = p["scenes"][1]
    plan = plan_scene(p, s, 1)
    return prompt.build_pass(p, s, 1, plan, plan["passes"][k - 1])["prompt"]


def test_voice_description_at_a_speakers_first_line_in_each_pass(harbor):
    p = narrated(harbor)
    before = [pass_prompt(p, k) for k in (2, 3)]
    assert "with a" not in before[0]  # no description yet: the lines as before
    nar = next(c for c in p["cast"] if c["id"] == "c_nar")
    nar["voice_desc"] = "Deep, warm male voice, slow and measured."
    p["cast"][0]["voice_desc"] = "a husky low voice"
    two, three = pass_prompt(p, 2), pass_prompt(p, 3)
    assert two.count("with a deep, warm male voice, slow and measured") == 1  # the first line only
    assert ("(S1), with a deep, warm male voice, slow and measured, says in an off-screen voiceover: "
            "<d>[English] The storm came early.</d> while their lips remain completely closed.") in two
    assert "with a husky low voice, mutters, <d>[English] Almost home.</d>" in two
    assert "<d>[English] She did not look back.</d>" in two and "with a deep" not in two.split("She did not")[0][-120:]
    assert "with a deep, warm male voice, slow and measured, says, <d>[English] Home was near.</d>" in three  # pass 3 again
    # the switch off: as before the description
    p["global"]["continuity"]["describe_voices"] = False
    assert [pass_prompt(p, k) for k in (2, 3)] == before


def test_issues_warn_about_a_voice_nothing_fixes(harbor):
    p = narrated(harbor)

    def warnings(q):
        plans = {s["id"]: plan_scene(q, s, i) for i, s in enumerate(q["scenes"])}
        return [i["message"] for i in validate._voice_issues(q, plans, {a["id"]: a for a in q["assets"]})]
    w = warnings(p)
    assert any(m.startswith("Narrator speaks in 2 passes with no voice reference and no voice description") for m in w)
    assert not any(m.startswith("Mara") for m in w)  # one pass only
    nar = next(c for c in p["cast"] if c["id"] == "c_nar")
    nar["voice_desc"] = "a deep male voice"
    assert warnings(p) == []
    p["global"]["continuity"]["describe_voices"] = False
    assert any("(and Describe voices is off)" in m for m in warnings(p))
    nar["voice"] = "a_voice"  # a voice reference fixes it whatever the switch
    assert warnings(p) == []


def test_script_import_keeps_a_voice_and_write_prompts_lists_voices(harbor):
    scenes, cast, _ = llm.coerce_script({"cast": [
        {"name": "Narrator", "kind": "character", "voice": "a calm, low female voice"},
        {"name": "Pier", "kind": "location", "voice": "ignored"},
        {"name": "Tom", "voice_desc": ["gravelly", "slow"]}]})
    assert [c["voice_desc"] for c in cast] == ["a calm, low female voice", "", "gravelly\nslow"]
    p = narrated(harbor)
    next(c for c in p["cast"] if c["id"] == "c_nar")["voice_desc"] = "a calm, low female voice"
    plan = plan_scene(p, p["scenes"][1], 1)
    assert llm.pass_voices(p, plan["passes"][1]) == ["@Narrator: with a calm, low female voice"]
    p["global"]["continuity"]["describe_voices"] = False
    assert llm.pass_voices(p, plan["passes"][1]) == []
    assert "When the request lists Voices, describe each speaker's voice" in llm.PASS_RULES
