"""The anchors a scene uses for each cast member, and a frame of a video anchor as a picture.

Sencer: "In scene tab, let me toggle select which anchors to use for the cast character. default all are selected, but I
should be able to deselect video, or specific picture. ... Also let me select a specific frame of a video for character
identity (optional), that will be revealed as picture anchor (select frame -> set as picture anchor -> then it is added
to "Add anchors" in Anchors card, where i can select it if I want. when frame is unset later, remove from Anchor list
and Anchors.)"

scene.cast[].skip lists the anchors the scene leaves out (picture asset ids and video anchor ids); empty = every anchor.
cast.video_anchors[].frame / frame_asset: the frame's time in the file and the image asset made from it.
"""

import copy
import json
import os
import shutil
import subprocess

import pytest

from reelwright.model import cast_pictures, normalize_project, pick_video_anchors, scene_media_counts, scene_people
from reelwright.planner import plan_scene
from reelwright.prompt import build_pass
from reelwright.validate import lint_project

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web", "rw")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")


def _build(p, i, n=0):
    plan = plan_scene(p, p["scenes"][i], i)
    return build_pass(p, p["scenes"][i], i, plan, plan["passes"][n])


def _lint(p):
    plans = {s["id"]: plan_scene(p, s, i) for i, s in enumerate(p["scenes"])}
    builds = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
              for i, s in enumerate(p["scenes"])}
    return lint_project(p, plans, builds, lambda a: True)


def _mara(harbor, skip=None, clips=()):
    """Mara (anchors a_front, a_side) in the first scene, with video anchors on clips of the given lengths."""
    p = copy.deepcopy(harbor)
    p["scenes"][0]["cast"] = [{"id": "c_mara", "skip": list(skip or [])}]
    vas = []
    for k, d in enumerate(clips):
        p["assets"].append({"id": "a_clip{}".format(k), "kind": "video", "name": "Mara clip {}".format(k),
                            "file": "reelwright/harbor_lights/clip{}.mp4".format(k), "duration": d, "category": "motion"})
        vas.append({"id": "va_{}".format(k), "asset": "a_clip{}".format(k)})
    p["cast"][0]["video_anchors"] = vas
    return normalize_project(p)


def test_skip_and_frame_are_normalised(harbor):
    p = copy.deepcopy(harbor)
    p["scenes"][0]["cast"] = [{"id": "c_mara", "skip": ["a_side", "a_side", 7, None, "va_1"]}, "c_mara", {"id": "x", "skip": "a"}]
    p["cast"][0]["video_anchors"] = [{"id": "va_1", "asset": "a_dolly", "frame": 1.01, "frame_asset": "a_f"},
                                     {"id": "va_2", "asset": "a_dolly", "frame": -1}, {"id": "va_3", "asset": "a_dolly", "frame": "x"}]
    p = normalize_project(p)
    e = p["scenes"][0]["cast"]
    assert e[0]["skip"] == ["a_side", "7", "va_1"] and e[1] == {"id": "c_mara", "outfit": "", "skip": []} and e[2]["skip"] == []
    va = p["cast"][0]["video_anchors"]
    assert (va[0]["frame"], va[0]["frame_asset"]) == (1.0, "a_f")
    assert (va[1]["frame"], va[1]["frame_asset"]) == (None, "") and va[2]["frame"] is None
    assert normalize_project(copy.deepcopy(p)) == p


def test_an_unticked_picture_is_not_sent(harbor):
    p = _mara(harbor)
    assert "a sheet of 2 views of the same person" in _build(p, 0)["prompt"]  # both, packed
    p = _mara(harbor, skip=["a_side"])
    c, e = p["cast"][0], p["scenes"][0]["cast"][0]
    assert cast_pictures(c, e, {a["id"]: a for a in p["assets"]})[1] == ["a_front"]
    b = _build(p, 0)
    assert [img["assets"] for img in b["images"]] == [["a_front"]]  # one picture: no sheet
    assert "<Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 1>." in b["prompt"]
    assert scene_media_counts(p, p["scenes"][0])["pictures"] == 1
    # another scene with Mara keeps both
    q = copy.deepcopy(p)
    q["scenes"][2]["cast"] = [{"id": "c_mara"}]
    q = normalize_project(q)
    assert [img["assets"] for img in _build(q, 2)["images"]][0] == ["a_front", "a_side"]


def test_every_picture_unticked_is_a_warning(harbor):
    p = _mara(harbor, skip=["a_front", "a_side"])
    b = _build(p, 0)
    assert not any(img.get("cast") == "c_mara" for img in b["images"])
    msgs = [x["message"] for x in _lint(p) if x["level"] == "warn"]
    assert any("every anchor picture of Mara is unticked in this scene" in m for m in msgs)
    assert not any("every anchor picture" in m for m in (x["message"] for x in _lint(_mara(harbor, skip=["a_side"]))))


def test_an_unticked_video_anchor_is_not_sent_or_counted(harbor):
    p = _mara(harbor, clips=(6.0, 6.0))
    assert [v.get("anchor") for v in _build(p, 0)["videos"]] == ["va_0", "va_1"]
    assert scene_media_counts(p, p["scenes"][0])["videos"] == 2
    p = _mara(harbor, skip=["va_0"], clips=(6.0, 6.0))
    b = _build(p, 0)
    assert [v.get("anchor") for v in b["videos"]] == ["va_1"]
    assert scene_media_counts(p, p["scenes"][0])["videos"] == 1
    recs = scene_people(p, p["scenes"][0])[0]
    n = {"videos": 0, "video_seconds": 0.0, "audio": 0, "audio_seconds": 0.0, "files": 0}
    picked, left = pick_video_anchors(recs, {a["id"]: a for a in p["assets"]}, n)
    assert [x["anchor"] for x in picked] == ["va_1"] and left == []  # unticked: not "left out" either
    # without a scene entry (a speaker missing from the cast list) every anchor goes
    assert [x["anchor"] for x in pick_video_anchors([dict(recs[0], entry={"id": "c_mara"})], {a["id"]: a for a in p["assets"]},
                                                    dict(n, videos=0, video_seconds=0.0, files=0))[0]] == ["va_0", "va_1"]


def test_a_frame_asset_is_an_anchor_only_once_added(harbor):
    p = _mara(harbor, clips=(6.0,))
    p["assets"].append({"id": "a_frame", "kind": "image", "name": "Mara clip 0 frame", "file": "reelwright/harbor_lights/f.png"})
    p["cast"][0]["video_anchors"][0].update(frame=2.0, frame_asset="a_frame")
    p = normalize_project(p)
    assert all("a_frame" not in img["assets"] for img in _build(p, 0)["images"])
    p["cast"][0]["anchors"].append("a_frame")
    assert ["a_front", "a_side", "a_frame"] in [img["assets"] for img in _build(normalize_project(p), 0)["images"]]


RUNNER = r"""
import { pathToFileURL } from "node:url";
const dir = process.argv[process.argv.length - 1];
const m = await import(pathToFileURL(dir + "/model.js").href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const req = JSON.parse(input);
const p = m.normalizeProject(req.project);
process.stdout.write(JSON.stringify({
  project: p,
  budgets: p.scenes.map(s => m.sceneBudget(p, s)),
  packs: p.scenes.map(s => p.cast.map(c => m.castPacks(p, s, c))),
  ids: p.scenes.map(s => m.scenePeople(p, s).people.map(x => x.ids)),
  used: p.scenes.map(s => p.cast.map(c => m.sceneAnchorIds(p, s, c))),
}));
"""


@needs_node
def test_the_editor_agrees(harbor):
    p = _mara(harbor, skip=["a_side", "va_0"], clips=(6.0, 6.0))
    p["scenes"][2]["cast"] = [{"id": "c_mara"}]
    p = normalize_project(p)
    r = subprocess.run([NODE, "--input-type=module", "-e", RUNNER, WEB], input=json.dumps({"project": p}),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["project"]["scenes"][0]["cast"] == p["scenes"][0]["cast"]
    assert out["project"]["cast"][0]["video_anchors"] == p["cast"][0]["video_anchors"]
    names = {"video_seconds": "videoSeconds", "audio_seconds": "audioSeconds"}
    want = [{names.get(k, k): v for k, v in scene_media_counts(p, s).items()} for s in p["scenes"]]
    assert out["budgets"] == want
    assert out["ids"][0] == [["a_front"]] and out["ids"][2][0] == ["a_front", "a_side"]
    assert out["packs"][0][0] is False and out["packs"][2][0] is True  # one picture left: nothing to pack
    assert out["used"][0][0] == ["a_front"] and out["used"][2][0] == ["a_front", "a_side"]
    assert out["ids"] == [[x["ids"] for x in scene_people(p, s)[0]] for s in p["scenes"]]
