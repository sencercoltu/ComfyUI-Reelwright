"""v0.12.0: pose references (Scene → References → role "pose").

Sencer: "can we add reference assets, so the real characters can use the same pose as from a given picture?" A pose
picture is cited in its character's subject line and analysed as attribute_transfer (MiniMax's Ref2VA guide: a
characteristic transferred to another subject); it is never a subject of its own, which would put the person in it in
the shot.
"""

import copy
import os

from reelwright.model import normalize_project, pose_refs, scene_media_counts
from reelwright.planner import plan_scene
from reelwright.prompt import build_pass, pose_words
from reelwright.validate import lint_project


def _builds(p, i):
    plan = plan_scene(p, p["scenes"][i], i)
    return [build_pass(p, p["scenes"][i], i, plan, x) for x in plan["passes"]], plan


def _with_pose(harbor, roots, scene=0, time=0.0, cast="c_mara", asset_kind="image"):
    p = copy.deepcopy(harbor)
    p["assets"].append({"id": "a_pose", "kind": asset_kind, "name": "superhero landing", "file": "reelwright/harbor_lights/pose.png",
                        "description": "a man in a superhero landing, one knee and one fist on the ground"})
    with open(os.path.join(roots.input, "reelwright/harbor_lights/pose.png"), "wb") as f:
        f.write(b"pose")
    s = p["scenes"][scene]
    s["cast"] = [{"id": "c_mara"}]
    s["refs"] = [r for r in s["refs"] if r["role"] != "keyframe"] + [
        {"id": "r_pose", "asset": "a_pose", "role": "pose", "cast": cast, "time": time}]
    return normalize_project(p)


def test_normalising_keeps_the_role_and_the_character():
    p = normalize_project({"scenes": [{"refs": [{"asset": "a", "role": "pose", "cast": "c_x"}, {"asset": "b", "cast": 5},
                                                {"asset": "c", "role": "dance"}]}]})
    refs = p["scenes"][0]["refs"]
    assert [(r["role"], r["cast"]) for r in refs] == [("pose", "c_x"), ("reference", "5"), ("reference", "")]


def test_a_pose_is_cited_in_its_characters_line(harbor, roots):
    p = _with_pose(harbor, roots)
    p["cast"][0]["pack_sheet"] = True
    (b,), _ = _builds(p, 0)
    prompt = b["prompt"]
    # [OLD 2026-11-09 v0.15.1->v0.16.0] assert ("<Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 1>, whose pose in [Shot 1] comes from "
    assert ("<Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 1>, a sheet of 2 views of the same "
            "person, whose pose in [Shot 1] comes from "  # added 2026-11-09 v0.16.0: the sheet is named
            "<Picture 2>.") in prompt
    assert ("<Picture 2> (pose of <Subject 1> in [Shot 1]): attribute_transfer - the body pose is transferred to "
            "<Subject 1>; the person, clothing and setting in <Picture 2> do not appear.") in prompt
    assert "<Subject 2>" not in prompt and "<Picture 2> is" not in prompt  # no subject, no standalone line
    assert [img["assets"] for img in b["images"]] == [["a_front", "a_side"], ["a_pose"]]
    assert b["subjects"][0]["poses"] == [{"ref": "r_pose", "picture": 2, "shot": 1}]
    assert scene_media_counts(p, p["scenes"][0])["pictures"] == 2


def test_a_pose_goes_to_the_pass_that_holds_its_time(harbor, roots):
    # the 32 s scene: pass 1 0-14.4 s, pass 2 14.375-…; shots at 0, 6, 14.375, 22
    p = _with_pose(harbor, roots, scene=1, time=23.0)
    builds, plan = _builds(p, 1)
    has = [any(img.get("pose") for img in b["images"]) for b in builds]
    k = next(i for i, x in enumerate(plan["passes"]) if x["start"] <= 23.0 < x["end"])
    assert has[k] and sum(has) == 1
    b = builds[k]
    sh = b["subjects"][0]["poses"][0]["shot"]
    assert "whose pose in [Shot {}] comes from <Picture".format(sh) in b["prompt"]
    counts = [scene_media_counts(p, p["scenes"][1], x)["pictures"] for x in plan["passes"]]
    q = _with_pose(harbor, roots, scene=1, time=23.0, cast="")  # the same scene, the pose without a character
    without = [scene_media_counts(q, q["scenes"][1], x)["pictures"] for x in plan["passes"]]
    assert [a - b for a, b in zip(counts, without)] == [1 if i == k else 0 for i in range(len(plan["passes"]))]
    assert [x[0]["id"] for x in pose_refs(p, p["scenes"][1])] == ["r_pose"]


def test_a_pose_at_the_end_counts_for_the_last_pass(harbor, roots):
    p = _with_pose(harbor, roots, scene=1, time=999)
    builds, plan = _builds(p, 1)
    assert any(img.get("pose") for img in builds[-1]["images"])


def test_unusable_poses_are_not_sent_and_warned(harbor, roots, store):
    for cast, word in (("", "names no character"), ("c_gone", "names no character")):
        p = _with_pose(harbor, roots, cast=cast)
        (b,), _ = _builds(p, 0)
        assert "a_pose" not in [a for img in b["images"] for a in img["assets"]]
        plans = {s["id"]: plan_scene(p, s, i) for i, s in enumerate(p["scenes"])}
        builds = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
                  for i, s in enumerate(p["scenes"])}
        msgs = [i["message"] for i in lint_project(p, plans, builds, lambda a: True)]
        assert any("is a pose reference but it " + word in m for m in msgs), msgs
    # a character who is not in the scene
    p = _with_pose(harbor, roots)
    p["cast"].append({"id": "c_tom", "name": "Tom", "kind": "character", "anchors": []})
    p = normalize_project(p)
    p["scenes"][0]["refs"][-1]["cast"] = "c_tom"
    plans = {s["id"]: plan_scene(p, s, i) for i, s in enumerate(p["scenes"])}
    builds = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
              for i, s in enumerate(p["scenes"])}
    assert any("is a pose reference but Tom is not in this scene" in i["message"]
               for i in lint_project(p, plans, builds, lambda a: True))


def test_pose_wording_for_several_shots():
    assert pose_words([{"shot": 3, "picture": 5}, {"shot": 1, "picture": 4}]) == \
        "whose pose in [Shot 1] comes from <Picture 4> and in [Shot 3] from <Picture 5>"


def test_the_llm_is_told_only_the_pose_is_used(harbor, roots):
    from reelwright.llm import scene_context
    p = _with_pose(harbor, roots, time=2.0)
    ctx = scene_context(p, p["scenes"][0])
    assert "(image, pose for @Mara: only the body pose is used, the person in it does not appear, at 2.00s)" in ctx


def test_scenes_without_poses_keep_their_builds(harbor, roots):
    (b,), _ = _builds(copy.deepcopy(harbor), 0)
    assert all("poses" not in s for s in b["subjects"]) and all("pose" not in img for img in b["images"])
