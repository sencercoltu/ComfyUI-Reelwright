"""LoRA trigger words (v0.21.0). Sencer: "for all LORA's, add trigger word support".

Every LoRA (Global stack, scene LoRAs, a cast member's identity LoRA, the draft LoRA) has an optional trigger word.
While the LoRA is in use, a pass's prompt that lacks the word gets it: an identity LoRA's after its character's name in
the subject line, in passes where the character is a subject; any other at the start of the summary, after the task
tags (ai-toolkit puts a missing trigger at the start of the caption when it trains).
"""

import copy

from reelwright import model, prompt
from reelwright.planner import plan_scene


def project(cast_lora=None, global_loras=(), scene_loras=None, desc="a man in his 40s", anchors=True, **scene):
    p = model.default_project("Triggers")
    p["assets"] = [{"id": "a_b", "kind": "image", "name": "Birten", "file": "reelwright/t/b.png", "width": 768, "height": 1024}]
    p["cast"] = [{"id": "c_b", "kind": "character", "name": "Birten", "description": desc,
                  "anchors": ["a_b"] if anchors else [], "lora": cast_lora or {"name": ""}},
                 {"id": "c_x", "kind": "character", "name": "Xavi", "anchors": [], "lora": {"name": ""}}]
    p["global"]["loras"] = [dict(x) for x in global_loras]
    s = p["scenes"][0]
    s["cast"] = [{"id": "c_b", "outfit": ""}]
    s["shots"] = [{"id": "h1", "t": 0, "text": "@Birten walks in the rain.", "camera": ""}]
    if scene_loras is not None:
        s["overrides"]["loras"] = scene_loras
    s.update(scene)
    return model.normalize_project(p)


def built(p, k=1):
    s = p["scenes"][0]
    plan = plan_scene(p, s, 0)
    return prompt.build_pass(p, s, 0, plan, plan["passes"][k - 1])["prompt"]


def section(text, name):
    return text.split(name + ":\n", 1)[1].split("\n\n", 1)[0]


def test_which_triggers_a_scene_has():
    film = {"id": "l1", "name": "film.safetensors", "strength": 0.5, "trigger": "sks film look"}
    off = {"id": "l2", "name": "off.safetensors", "strength": 0.5, "enabled": False, "trigger": "never"}
    blank = {"id": "l3", "name": "", "strength": 0.5, "trigger": "no file"}
    p = project(cast_lora={"name": "birten.safetensors", "strength": 0.6, "trigger": "ohwx man"}, global_loras=[film, off, blank])
    s = p["scenes"][0]
    assert model.lora_triggers(p, s) == [{"trigger": "sks film look", "cast": None}, {"trigger": "ohwx man", "cast": "c_b"}]
    assert model.effective_loras(p, s) == [("film.safetensors", 0.5), ("birten.safetensors", 0.6)]  # unchanged shape
    # a scene item with the same file retunes the strength and, with one, the trigger; without one the Global's stays
    s["overrides"]["loras"] = {"mode": "add", "items": [{"id": "i1", "name": "film.safetensors", "strength": 0.9}], "strengths": {}}
    assert model.lora_triggers(p, s)[0]["trigger"] == "sks film look" and model.effective_loras(p, s)[0] == ("film.safetensors", 0.9)
    s["overrides"]["loras"]["items"][0]["trigger"] = "sks grain"
    assert model.lora_triggers(p, s)[0]["trigger"] == "sks grain"
    # Replace Global drops the stack's; the draft LoRA's only in a draft; a cast member not in the scene adds nothing
    s["overrides"]["loras"] = {"mode": "replace", "items": [], "strengths": {}}
    assert model.lora_triggers(p, s) == [{"trigger": "ohwx man", "cast": "c_b"}]
    p["global"]["draft"].update(lora="turbo.safetensors", lora_trigger="fast")
    assert [t["trigger"] for t in model.lora_triggers(p, s)] == ["ohwx man"]
    s["overrides"]["quality"] = "draft"
    assert [t["trigger"] for t in model.lora_triggers(p, s)] == ["ohwx man", "fast"]
    s["cast"] = []
    assert [t["trigger"] for t in model.lora_triggers(p, s)] == ["fast"]
    # one word once, whatever its case
    s["overrides"]["loras"] = {"mode": "add", "items": [{"id": "i1", "name": "x.safetensors", "strength": 1, "trigger": "FAST"}], "strengths": {}}
    assert [t["trigger"] for t in model.lora_triggers(p, s)] == ["sks film look", "FAST"]


def test_identity_trigger_follows_the_name_and_others_open_the_summary():
    film = {"id": "l1", "name": "film.safetensors", "strength": 0.5, "trigger": "sks film look"}
    p = project(cast_lora={"name": "birten.safetensors", "strength": 0.6, "trigger": "ohwx man"}, global_loras=[film])
    text = built(p)
    assert section(text, "subject_definitions") == "<Subject 1> is Birten (ohwx man), a man in his 40s, shown in <Picture 1>."
    assert section(text, "summary").startswith("[reference generation] sks film look, The target video shows <Subject 1>")
    assert text.count("ohwx man") == 1 and text.count("sks film look") == 1
    # without triggers the prompt is what it was (no cache key moves)
    plain = project(cast_lora={"name": "birten.safetensors", "strength": 0.6}, global_loras=[dict(film, trigger="")])
    assert built(plain) == text.replace(" (ohwx man)", "").replace("sks film look, ", "")


def test_a_word_the_prompt_already_has_is_not_added():
    # trained with the character's name as its trigger: the subject line already says it
    p = project(cast_lora={"name": "birten.safetensors", "strength": 0.6, "trigger": "birten"})
    text = built(p)
    assert "(birten)" not in text and section(text, "summary").startswith("[reference generation] The target video")
    # in the description
    p = project(cast_lora={"name": "birten.safetensors", "strength": 0.6, "trigger": "ohwx"}, desc="ohwx, a man in his 40s")
    assert built(p).count("ohwx") == 1
    # written into the scene's own text; part of a longer word does not count
    film = {"id": "l1", "name": "film.safetensors", "strength": 0.5, "trigger": "sks"}
    p = project(global_loras=[film])
    p["scenes"][0]["prompt"]["sections"]["detailed_description"] = "Shot on SKS film stock."
    assert "sks, " not in built(p)
    p["scenes"][0]["prompt"]["sections"]["detailed_description"] = "Shot on sksfilm stock."
    assert section(built(p), "summary").startswith("[reference generation] sks, ")


def test_identity_trigger_with_its_character_as_a_subject():
    # a character without pictures is still a subject (described in words): the word follows the name
    p = project(cast_lora={"name": "birten.safetensors", "strength": 0.6, "trigger": "ohwx man"}, anchors=False)
    assert section(built(p), "subject_definitions") == "<Subject 1> is Birten (ohwx man), a man in his 40s."
    # a character the scene does not have: its identity LoRA is not loaded, so no word either
    p["scenes"][0]["cast"] = [{"id": "c_x", "outfit": ""}]
    p["cast"][1]["lora"] = {"name": "xavi.safetensors", "strength": 0.6, "trigger": "xvi"}
    text = built(p)
    assert "ohwx" not in text and "Xavi (xvi)" in text
    # own subject definitions (auto off): the word goes to the summary
    p = project(cast_lora={"name": "birten.safetensors", "strength": 0.6, "trigger": "ohwx man"})
    s = p["scenes"][0]
    s["prompt"]["auto"]["subjects"] = False
    s["prompt"]["sections"]["subject_definitions"] = "<Subject 1> is the man shown in <Picture 1>."
    text = built(p)
    assert section(text, "subject_definitions") == "<Subject 1> is the man shown in <Picture 1>."
    assert section(text, "summary").startswith("[reference generation] ohwx man")


def test_raw_prompts_and_an_empty_summary():
    film = {"id": "l1", "name": "film.safetensors", "strength": 0.5, "trigger": "sks film look"}
    p = project(cast_lora={"name": "birten.safetensors", "strength": 0.6, "trigger": "ohwx man"}, global_loras=[film])
    s = p["scenes"][0]
    s["prompt"]["mode"] = "raw"
    s["prompt"]["raw"] = "A man walks in the rain, @Birten."
    assert built(p) == "[reference generation] sks film look, ohwx man, A man walks in the rain, <Subject 1>."
    # a raw prompt in six sections: after the summary's tags
    s["prompt"]["raw"] = "subject_definitions:\n<Subject 1> is @Birten.\n\nsummary:\nHe walks.\n\ndetailed_description:\nRain."
    text = built(p)
    assert section(text, "summary") == "[reference generation] sks film look, ohwx man, He walks."
    # no references, no summary of its own, auto subjects off: the word is the summary
    q = project(global_loras=[film])
    q["cast"][0]["anchors"] = []
    q["scenes"][0]["prompt"]["auto"]["subjects"] = False
    assert section(built(q), "summary") == "sks film look."


def test_place_trigger_words_keeps_the_task_tags_first():
    assert prompt.place_trigger_words("[reference generation + audio reuse] He walks.", ["a", "b"]) == \
        "[reference generation + audio reuse] a, b, He walks."
    assert prompt.place_trigger_words("[Shot 1] He walks.", ["a"]) == "a, [Shot 1] He walks."  # not a task tag
    assert prompt.place_trigger_words("He walks.", []) == "He walks."
    assert prompt.has_word("Shot on SKS film.", "sks") and not prompt.has_word("sksfilm", "sks")


def test_normalised_everywhere():
    p = model.normalize_project(copy.deepcopy({
        "scenes": [{"overrides": {"loras": {"items": [{"name": "s.safetensors", "trigger": " in   sks\tstyle "}]}}}],
        "cast": [{"kind": "character", "name": "B", "lora": {"name": "b.safetensors", "trigger": "ohwx\nman"}}],
        "global": {"loras": [{"name": "g.safetensors", "trigger": "x" * 130}], "draft": {"lora_trigger": 5}}}))
    assert p["scenes"][0]["overrides"]["loras"]["items"][0]["trigger"] == "in sks style"
    assert p["cast"][0]["lora"]["trigger"] == "ohwx man"
    assert p["global"]["loras"][0]["trigger"] == "x" * 120 and p["global"]["draft"]["lora_trigger"] == "5"
