import copy

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
    assert out["timeline"]["total"] == 42.5
