"""v0.11.0: a prop that is part of a character (Cast -> Prop -> Part of), and outfit pictures.

Sencer: "I add me as a character and a big beer belly as a prop: there are two people in the shot." Every cast member
was a <Subject N> of its own, and H3 puts each subject in the shot as a separate thing. A part's pictures and
description now go into its character's subject.
"""

import copy
import os

from reelwright.model import normalize_project, part_owner, project_index, scene_media_counts, scene_people
from reelwright.planner import plan_scene
from reelwright.prompt import build_pass, outfit_words
from reelwright.validate import lint_project


def _build(p, i, n=0):
    plan = plan_scene(p, p["scenes"][i], i)
    return build_pass(p, p["scenes"][i], i, plan, plan["passes"][n])


def _with_belly(harbor, roots, **belly):
    p = copy.deepcopy(harbor)
    p["assets"].append({"id": "a_belly", "kind": "image", "name": "belly", "file": "reelwright/harbor_lights/belly.png"})
    with open(os.path.join(roots.input, "reelwright/harbor_lights/belly.png"), "wb") as f:
        f.write(b"belly")
    p["cast"].append(dict({"id": "c_belly", "name": "Beer belly", "kind": "prop", "part_of": "c_mara",
                           "description": "a big round beer belly", "anchors": ["a_belly"]}, **belly))
    p["cast"][0]["pack_sheet"] = False  # Mara's two anchors as separate pictures
    p["scenes"][0]["cast"] = [{"id": "c_belly"}, {"id": "c_mara"}]  # the part first: order does not matter
    p["scenes"][0]["shots"][0]["text"] = "@Mara pats @{Beer belly} and laughs"
    return normalize_project(p)


def test_part_owner_rules(harbor):
    cast = {c["id"]: c for c in harbor["cast"]}
    prop = {"id": "c_x", "kind": "prop", "part_of": "c_mara"}
    assert part_owner(prop, cast) == "c_mara"
    assert part_owner(dict(prop, kind="character"), cast) == ""  # only props are parts
    assert part_owner(dict(prop, part_of="c_gone"), cast) == ""
    assert part_owner(dict(prop, part_of=""), cast) == ""
    loc = {"id": "c_loc", "kind": "location"}
    assert part_owner(dict(prop, part_of="c_loc"), dict(cast, c_loc=loc)) == ""  # a part of a character only
    assert part_owner(dict(prop, id="c_mara"), cast) == ""  # never of itself
    # normalising keeps the field as text
    p = normalize_project({"scenes": [], "cast": [{"name": "a", "part_of": 5}, {"name": "b"}]})
    assert [c["part_of"] for c in p["cast"]] == ["5", ""]  # text, as every text field; no character has that id


def test_a_part_joins_its_characters_subject(harbor, roots):
    p = _with_belly(harbor, roots)
    b = _build(p, 0)
    prompt = b["prompt"]
    # one subject: Mara, with the belly's picture as hers
    assert "<Subject 2>" not in prompt
    assert ("<Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 1> and <Picture 2>, with Beer belly "
            "(a big round beer belly) shown in <Picture 3>.") in prompt
    assert "its Beer belly: fully_preserved - shape, colour, and details are retained." in prompt
    assert "<Subject 1> pats <Subject 1>'s Beer belly and laughs" in prompt
    assert b["tag_map"]["@Mara"] == "<Subject 1>" and "@Beer belly" not in b["tag_map"]  # the LLM's label -> tag map
    people, left = scene_people(p, p["scenes"][0])
    assert [x["cast"]["id"] for x in people] == ["c_mara"] and not left
    assert people[0]["ids"] == ["a_front", "a_side", "a_belly"] and people[0]["own"] == ["a_front", "a_side"]
    assert scene_media_counts(p, p["scenes"][0])["pictures"] == 3


def test_a_part_in_a_packed_sheet_is_named_without_a_picture(harbor, roots):
    p = _with_belly(harbor, roots)
    p["cast"][0]["pack_sheet"] = True
    prompt = _build(p, 0)["prompt"]
    assert ("<Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 1>, a sheet of 3 views of the same "
            "person, with Beer belly (a big round beer belly).") in prompt
    assert "<Picture 2>" not in prompt
    assert scene_media_counts(p, p["scenes"][0])["pictures"] == 1


def test_a_part_without_its_character_is_left_out_and_warned(harbor, roots, store):
    p = _with_belly(harbor, roots)
    p["scenes"][0]["cast"] = [{"id": "c_belly"}]
    p["scenes"][0]["shots"][0]["text"] = "a quiet harbour"
    prompt = _build(p, 0)["prompt"]
    assert "Beer belly" not in prompt and "<Subject" not in prompt
    people, left = scene_people(p, p["scenes"][0])
    assert people == [] and [(a["id"], b["id"]) for a, b in left] == [("c_belly", "c_mara")]
    plans = {s["id"]: plan_scene(p, s, i) for i, s in enumerate(p["scenes"])}
    builds = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
              for i, s in enumerate(p["scenes"])}
    issues = lint_project(p, plans, builds, lambda a: True)
    assert any(i["level"] == "warn" and "Beer belly is part of Mara, who is not in this scene" in i["message"]
               for i in issues)
    # Mara speaking in the scene (not in its cast list) brings the part back
    p["scenes"][0]["dialogue"] = [{"id": "d_x", "speaker": "c_mara", "t": 1.0, "text": "Hm."}]
    assert scene_people(normalize_project(p), p["scenes"][0])[0][0]["cast"]["id"] == "c_mara"


def test_a_part_named_in_a_scene_it_is_not_in(harbor, roots):
    p = _with_belly(harbor, roots)
    p["scenes"][0]["cast"] = [{"id": "c_mara"}]
    b = _build(p, 0)
    assert "<Subject 1>'s Beer belly" in b["prompt"] and "<Picture 3>" not in b["prompt"]
    assert any(i["level"] == "info" and "not in this scene's cast" in i["message"] for i in b["issues"])
    p["scenes"][0]["cast"] = []
    b = _build(p, 0)
    assert any(i["level"] == "warn" and "is part of Mara, who is not in this scene's cast" in i["message"] for i in b["issues"])


def test_a_character_and_a_free_prop_stay_two_subjects(harbor, roots):
    p = _with_belly(harbor, roots, part_of="")
    prompt = _build(p, 0)["prompt"]
    assert "<Subject 1> is Beer belly, a big round beer belly, shown in <Picture 1>." in prompt
    assert "<Subject 2> is Mara" in prompt


def test_outfit_pictures_and_wording(harbor, roots):
    p = _with_belly(harbor, roots, part_of="")
    p["cast"].pop()  # no belly prop: the belly is a look of Mara's
    p["scenes"][0]["cast"] = [{"id": "c_mara", "outfit": "o_belly"}]
    p["scenes"][0]["shots"][0]["text"] = "@Mara laughs"
    p["cast"][0]["outfits"] = [{"id": "o_belly", "name": "with a big beer belly", "retention": "partially_preserved",
                                "keep": ["face", "hair"], "assets": ["a_belly"]}]
    p = normalize_project(p)
    prompt = _build(p, 0)["prompt"]
    # the outfit's picture is named as the outfit's, not as one more picture of Mara
    assert ("<Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 1> and <Picture 2>, "
            "with a big beer belly as shown in <Picture 3>.") in prompt
    assert ("<Subject 1> (appears in [Shot 1]): partially_preserved - face and hair are partly retained, "
            "with a big beer belly as shown in <Picture 3>.") in prompt
    assert outfit_words("grey suit") == "wearing grey suit"
    assert outfit_words("in a wheelchair") == "in a wheelchair"
    assert outfit_words("Wearing a  red scarf") == "Wearing a red scarf"
    assert outfit_words("Indigo dress") == "wearing Indigo dress"


def test_llm_context_says_a_part_is_no_separate_subject(harbor, roots):
    from reelwright.llm import scene_context
    p = _with_belly(harbor, roots)
    ctx = scene_context(p, p["scenes"][0])
    assert "@{Beer belly} - a big round beer belly (part of @Mara's body or look, not a separate person or object)" in ctx
    assert project_index(p)["cast"]["c_belly"]["part_of"] == "c_mara"


def test_an_outfit_picture_is_named_in_the_prompt(harbor, roots):
    """v0.19.3 (Sencer: "when selecting the Dress outfit, seems the outfit's picture is not referenced anywhere, but
    only the name "Dress""): the outfit's picture was one more "shown in" picture of the character."""
    p = _with_belly(harbor, roots, part_of="")
    p["cast"].pop()
    p["assets"][-1].update(id="a_dress", name="dress")
    p["scenes"][0]["cast"] = [{"id": "c_mara", "outfit": "o_dress"}]
    p["scenes"][0]["shots"][0]["text"] = "@Mara laughs"
    p["cast"][0]["outfits"] = [{"id": "o_plain", "name": "Default", "assets": []},
                               {"id": "o_dress", "name": "Dress", "assets": ["a_dress"]}]
    p["cast"][0]["default_outfit"] = "o_plain"
    p = normalize_project(p)
    prompt = _build(p, 0)["prompt"]
    assert ("<Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 1> and <Picture 2>, "
            "wearing Dress as shown in <Picture 3>.") in prompt
    assert ("<Subject 1> (appears in [Shot 1]): fully_preserved - identity and appearance are retained, wearing Dress "
            "as shown in <Picture 3>.") in prompt
    # the default outfit, unnamed, with a picture
    p["scenes"][0]["cast"] = [{"id": "c_mara", "outfit": ""}]
    p["cast"][0]["outfits"][0]["assets"] = ["a_dress"]
    assert "shown in <Picture 1> and <Picture 2>, wearing the outfit shown in <Picture 3>." in _build(p, 0)["prompt"]
    # an outfit picture that is also an anchor is an anchor; an anchor left out in this scene is the outfit's then
    p["cast"][0]["outfits"][0]["assets"] = [p["cast"][0]["anchors"][1]]
    assert "shown in <Picture 1> and <Picture 2>." in _build(p, 0)["prompt"]
    p["scenes"][0]["cast"][0]["skip"] = [p["cast"][0]["anchors"][1]]
    p = normalize_project(p)
    assert "shown in <Picture 1>, wearing the outfit shown in <Picture 2>." in _build(p, 0)["prompt"]
    # one sheet: the outfit is its last view
    p["scenes"][0]["cast"] = [{"id": "c_mara", "outfit": "o_dress"}]
    p["cast"][0]["pack_sheet"] = True
    p = normalize_project(p)
    prompt = _build(p, 0)["prompt"]
    assert ("shown in <Picture 1>, a sheet of 3 views of the same person, wearing Dress as shown in the last view of "
            "the sheet.") in prompt
    # a scene without outfit pictures builds exactly as before
    p["cast"][0]["outfits"][1]["assets"] = []
    p["cast"][0]["pack_sheet"] = False
    p = normalize_project(p)
    prompt = _build(p, 0)["prompt"]
    assert "shown in <Picture 1> and <Picture 2>, wearing Dress." in prompt
    assert "fully_preserved - identity and appearance are retained." in prompt
