"""added 2026-11-09 v0.16.0: anchor sheets named in the subject line, a warning when their pictures reach H3 too small,
and video anchors of cast members.

Sencer: "if one character has multiple anchor pictures, and a sheet of say 9x9 is created, how does H3 assign the single
sheet as a single subject?" -> "do both please. also, why didn't we add video anchors? if possible, lets add them as
well." Video anchors: a "with sound" switch per anchor (off by default) and a From / To per anchor.
"""

import copy
import json
import os
import shutil
import subprocess

import pytest

from reelwright import model, spec
from reelwright.model import normalize_project, pick_video_anchors, scene_media_counts, scene_people, tile_pixels
from reelwright.planner import plan_scene
from reelwright.prompt import build_pass
from reelwright.validate import lint_project

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web", "rw")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")


def _clip_window(v):
    """render.clip_window when ComfyUI is importable (the venv run), else the same rule."""
    try:
        from reelwright import render
    except ImportError:
        start = max(0.0, float(v.get("in") or 0.0))
        secs = spec.REF_MEDIA_MAX_SECONDS if v.get("seconds") is None else min(float(v["seconds"]), spec.REF_MEDIA_MAX_SECONDS)
        return start, max(1.0 / spec.FPS, secs)
    return render.clip_window(v)


def _build(p, i, n=0):
    plan = plan_scene(p, p["scenes"][i], i)
    return build_pass(p, p["scenes"][i], i, plan, plan["passes"][n])


def _lint(p):
    plans = {s["id"]: plan_scene(p, s, i) for i, s in enumerate(p["scenes"])}
    builds = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
              for i, s in enumerate(p["scenes"])}
    return lint_project(p, plans, builds, lambda a: True)


def _clips(harbor, *durations):
    p = copy.deepcopy(harbor)
    p["scenes"][0]["cast"] = [{"id": "c_mara"}]  # Mara in the first scene (one pass, fresh)
    for k, d in enumerate(durations):
        p["assets"].append({"id": "a_clip{}".format(k), "kind": "video", "name": "Mara clip {}".format(k),
                            "file": "reelwright/harbor_lights/clip{}.mp4".format(k), "duration": d,
                            "category": "motion"})
    return p


# ---- the sheet in the subject line -----------------------------------------------------------------------------

def test_a_packed_sheet_is_named_in_the_subject_line(harbor):
    p = copy.deepcopy(harbor)  # Mara: two anchors, packed (the default)
    p["scenes"][0]["cast"] = [{"id": "c_mara"}]
    p = normalize_project(p)
    prompt = _build(p, 0)["prompt"]
    assert "<Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 1>, a sheet of 2 views of the same " \
           "person." in prompt
    p["cast"][0]["pack_sheet"] = False
    assert "shown in <Picture 1> and <Picture 2>." in _build(normalize_project(p), 0)["prompt"]
    # a location and a prop say "place" and "object"
    q = copy.deepcopy(p)
    q["cast"][0]["pack_sheet"] = True
    q["cast"][0]["kind"] = "location"
    assert "a sheet of 2 views of the same place." in _build(normalize_project(q), 0)["prompt"]
    q["cast"][0]["kind"] = "prop"
    assert "a sheet of 2 views of the same object." in _build(normalize_project(q), 0)["prompt"]


# ---- pictures of a sheet too small for identity ------------------------------------------------------------------

def test_tile_pixels():
    sq = [{"width": 1024, "height": 1024}]
    assert tile_pixels([], 1344, 768) == 0
    assert tile_pixels(sq * 4, 1344, 768) == 508          # 2x2 at the output's pixel area
    assert tile_pixels(sq * 9, 1344, 768) == 339          # 3x3
    assert tile_pixels(sq * 81, 1344, 768) == 113         # 9x9
    assert tile_pixels(sq * 81, 1344, 768, "max") == 228  # 9x9, 2048 px short edge
    assert tile_pixels(sq * 4, 1344, 768, "max") == 768   # never scaled up
    assert model.sheet_grid(9) == (3, 3) and model.sheet_grid(10) == (4, 3) and model.sheet_grid(1) == (1, 1)


def test_a_sheet_whose_pictures_are_too_small_is_a_warning(harbor, roots):
    p = copy.deepcopy(harbor)
    for k in range(16):  # a 4x4 sheet: about 254 px per picture at 1344x768
        p["assets"].append({"id": "a_m{}".format(k), "kind": "image", "name": "m", "width": 1024, "height": 1024,
                            "file": "reelwright/harbor_lights/front.png"})
    p["cast"][0]["anchors"] = ["a_m{}".format(k) for k in range(16)]
    p = normalize_project(p)
    msgs = [x["message"] for x in _lint(p) if x["level"] == "warn"]
    small = [m for m in msgs if "too small for a reliable identity" in m]
    assert small and "Mara's 16 pictures go to H3 as one 4x4 sheet, so each reaches it at about 254 px" in small[0]
    assert "Reference images to max" in small[0]
    p["global"]["output"]["ref_image_size"] = "max"  # 2048 / 4 = 512 px
    assert not [x for x in _lint(p) if "too small" in x["message"]]
    p["global"]["output"]["ref_image_size"] = "match"
    p["cast"][0]["pack_sheet"] = "auto"  # 16 separate pictures do not fit 9, so auto packs too
    assert [x for x in _lint(p) if "too small" in x["message"]]
    p["cast"][0]["anchors"] = p["cast"][0]["anchors"][:4]
    assert not [x for x in _lint(p) if "too small" in x["message"]]


# ---- video anchors -------------------------------------------------------------------------------------------------

def test_video_anchors_are_normalised(harbor):
    p = copy.deepcopy(harbor)
    p["cast"][0]["video_anchors"] = [{"asset": "a_dolly", "in": 1.01, "out": "x", "soundtrack": 1}, "junk",
                                     {"id": "va_x", "asset": 5, "in": -2, "out": 3.333}, {"id": "va_x"}]
    p = normalize_project(p)
    va = p["cast"][0]["video_anchors"]
    assert len(va) == 3 and va[0]["id"].startswith("va") and va[1]["id"] == "va_x" and va[2]["id"] == "va_x_2"
    assert (va[0]["asset"], va[0]["in"], va[0]["out"], va[0]["soundtrack"]) == ("a_dolly", 1.0, None, True)
    assert (va[1]["asset"], va[1]["in"], va[1]["out"], va[1]["soundtrack"]) == ("5", 0.0, 80 / 24, False)
    assert normalize_project(copy.deepcopy(harbor))["cast"][0]["video_anchors"] == []


def test_a_video_anchor_joins_its_characters_subject(harbor):
    p = _clips(harbor, 6.0)
    p["cast"][0]["video_anchors"] = [{"id": "va_1", "asset": "a_clip0"}]
    p = normalize_project(p)
    b = _build(p, 0)
    prompt = b["prompt"]
    assert ("<Subject 1> is Mara, woman, early 30s, auburn hair, shown in <Picture 1>, a sheet of 2 views of the same "
            "person, and in <Video 1>.") in prompt
    assert "<Video 1> is" not in prompt and "<Video 1> (" not in prompt  # no line of its own: it is the subject's
    assert "<Audio" not in prompt.split("detailed_description:")[0] or "voice-timbre" in prompt
    v = b["videos"][0]
    assert (v["asset"], v["cast"], v["anchor"], v["in"], v["seconds"], v["soundtrack"]) == \
        ("a_clip0", "c_mara", "va_1", 0.0, 6.0, False)
    assert _clip_window(v) == (0.0, 6.0)
    assert "reference generation" in prompt
    # a scene without the character sends nothing of it
    assert _build(p, 2)["videos"] == []


def test_a_video_anchor_with_sound_is_its_characters_voice(harbor):
    p = _clips(harbor, 6.0)
    p["cast"][0]["video_anchors"] = [{"id": "va_1", "asset": "a_clip0", "in": 1.0, "out": 4.0, "soundtrack": True}]
    p = normalize_project(p)
    b = _build(p, 0)
    v = b["videos"][0]
    assert (v["in"], v["out"], v["seconds"], v["soundtrack"]) == (1.0, 4.0, 3.0, True)
    assert _clip_window(v) == (1.0, 3.0)
    assert "<Audio 1> is the synchronized audio track of <Video 1>, the voice of <Subject 1>." in b["prompt"]
    assert ("<Audio 1>: reference - the voice timbre and delivery of <Subject 1> follow the sound of <Video 1> without "
            "copying the original signal.") in b["prompt"]


def test_video_anchors_fit_h3s_budget(harbor):
    p = _clips(harbor, 10.0, 10.0, 3.0, 20.0)
    p["cast"][0]["video_anchors"] = [{"id": "va_a", "asset": "a_clip0"}, {"id": "va_b", "asset": "a_clip1"},
                                     {"id": "va_c", "asset": "a_clip2"}]
    p = normalize_project(p)
    b = _build(p, 0)
    sent = [(v["anchor"], v["seconds"]) for v in b["videos"]]
    assert sent == [("va_a", 10.0), ("va_b", 5.0)]  # 15 s of video in all: the second is shortened, the third left out
    msgs = [x["message"] for x in b["issues"]]
    assert "Mara's video anchor V3 is sent as its first 5.00 s: H3 takes 15 s of video in all" in msgs  # V1: the dolly
    assert "Mara's video anchor V4 is not sent: H3 takes 15 s of video in all and less than 2 s are left" in msgs
    counts = scene_media_counts(p, p["scenes"][0])
    assert (counts["videos"], counts["video_seconds"], counts["files"]) == (2, 15.0, 1 + 2 + counts["audio"])
    lint = [x["message"] for x in _lint(p)]
    assert not [m for m in lint if "reference videos (up to 3)" in m or "video refs total" in m]
    assert any("is sent as its first 5.00 s" in m for m in lint)
    # three videos at most: a scene that sends two of its own leaves room for one anchor
    q = copy.deepcopy(p)
    q["cast"][0]["video_anchors"] = [{"id": "va_c", "asset": "a_clip2"}, {"id": "va_d", "asset": "a_clip2", "in": 1}]
    q["assets"].append({"id": "a_cam", "kind": "video", "name": "cam", "file": "reelwright/harbor_lights/dolly.mp4",
                        "duration": 2.5, "category": "camera"})
    q["scenes"][0]["refs"] = [{"id": "r_d", "asset": "a_dolly", "role": "reference"},
                              {"id": "r_c", "asset": "a_cam", "role": "reference"}]
    q = normalize_project(q)
    b = _build(q, 0)
    assert [v.get("anchor") for v in b["videos"]] == [None, None, "va_c"]
    assert "Mara's video anchor V4 is not sent: H3 takes 3 videos and the pass sends that many already" in \
        [x["message"] for x in b["issues"]]
    assert scene_media_counts(q, q["scenes"][0])["videos"] == 3


def test_a_video_anchor_goes_without_its_sound_when_no_audio_slot_is_free(harbor):
    p = _clips(harbor, 6.0)
    p["cast"][0]["video_anchors"] = [{"id": "va_1", "asset": "a_clip0", "soundtrack": True}]
    for k in range(3):
        p["assets"].append({"id": "a_snd{}".format(k), "kind": "audio", "name": "s", "duration": 3.0,
                            "file": "reelwright/harbor_lights/voice.wav"})
    p["scenes"][0]["refs"] = [{"id": "r_s{}".format(k), "asset": "a_snd{}".format(k), "role": "reference"}
                              for k in range(3)]
    p = normalize_project(p)
    b = _build(p, 0)
    v = [x for x in b["videos"] if x.get("anchor")][0]
    assert v["soundtrack"] is False
    assert "Mara's video anchor V2 is sent without its sound: the 3 audio slots (or 15 s of audio) are taken" in \
        [x["message"] for x in b["issues"]]


def test_pick_video_anchors_rules(harbor):
    p = _clips(harbor, 6.0, 30.0)
    p["cast"][0]["video_anchors"] = [{"id": "va_long", "asset": "a_clip1"}, {"id": "va_none", "asset": "a_clip0", "in": 7},
                                     {"id": "va_gone", "asset": "a_nope"}, {"id": "va_img", "asset": "a_front"}]
    p = normalize_project(p)
    recs = scene_people(p, p["scenes"][0])[0]
    assets = {a["id"]: a for a in p["assets"]}
    n = {"videos": 0, "video_seconds": 0.0, "audio": 0, "audio_seconds": 0.0, "files": 0}
    picked, left = pick_video_anchors(recs, assets, n)
    assert [(x["anchor"], x["seconds"], x["cut"]) for x in picked] == [("va_long", 15.0, False)]  # first 15 s
    assert [(x["anchor"], x["why"]) for x in left] == [("va_none", "clip")]  # deleted / not a video: not candidates
    assert n == {"videos": 1, "video_seconds": 15.0, "audio": 0, "audio_seconds": 0.0, "files": 1}
    lint = [x["message"] for x in _lint(p)]
    assert "Mara: a video anchor points to a deleted asset, so it is not sent" in lint
    assert "Mara: a video anchor is not a video, so it is not sent" in lint
    assert any(m.startswith("Mara: video anchor V2 starts at 00:07.000 but ends there or before") for m in lint)
    assert any(m.startswith("Mara: video anchor V3 is a 30.0 s clip, so only its first 15 s are sent") for m in lint)
    assert not [m for m in lint if "video refs total" in m]


# ---- the editor gives the same numbers (model.js) ------------------------------------------------------------------

RUNNER = r"""
import { pathToFileURL } from "node:url";
const dir = process.argv[process.argv.length - 1];
const m = await import(pathToFileURL(dir + "/model.js").href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const req = JSON.parse(input);
const p = m.normalizeProject(req.project);
const sheet = n => Array.from({ length: n }, () => ({ width: 1024, height: 1024 }));
process.stdout.write(JSON.stringify({
  anchors: p.cast.map(c => c.video_anchors),
  budgets: p.scenes.map(s => m.sceneBudget(p, s)),
  tiles: [[4, "match"], [9, "match"], [81, "match"], [81, "max"], [16, "match"]].map(([n, r]) => m.tilePixels(sheet(n), 1344, 768, r)),
  scene_tiles: p.scenes.map(s => p.cast.map(c => m.sceneTilePixels(p, s, c))),
}));
"""


@needs_node
def test_the_editor_counts_and_sizes_the_same(harbor):
    p = _clips(harbor, 10.0, 10.0, 3.0, 20.0)
    p["cast"][0]["video_anchors"] = [{"id": "va_a", "asset": "a_clip0"}, {"id": "va_b", "asset": "a_clip1", "soundtrack": True},
                                     {"id": "va_c", "asset": "a_clip2", "in": 0.5, "out": 2.75}]
    p = normalize_project(p)
    r = subprocess.run([NODE, "--input-type=module", "-e", RUNNER, WEB], input=json.dumps({"project": p}),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["anchors"] == [c["video_anchors"] for c in p["cast"]]
    names = {"video_seconds": "videoSeconds", "audio_seconds": "audioSeconds"}
    want = [{names.get(k, k): v for k, v in scene_media_counts(p, s).items()} for s in p["scenes"]]
    assert out["budgets"] == want
    sq = [{"width": 1024, "height": 1024}]
    assert out["tiles"] == [tile_pixels(sq * n, 1344, 768, r) for n, r in ((4, "match"), (9, "match"), (81, "match"),
                                                                           (81, "max"), (16, "match"))]
    assert out["scene_tiles"][0][0] > 0  # Mara's sheet in the first scene


def test_a_video_anchor_under_2_s_is_not_sent(harbor):
    """added 2026-11-09 v0.17.1 (third review 4): a clip under 2 s is left out ("short"), as the Cast tab says; it was
    sent unless it had been cut to the seconds left."""
    p = _clips(harbor, 1.5)
    p["cast"][0]["video_anchors"] = [{"id": "va_s", "asset": "a_clip0"}]
    p = normalize_project(p)
    recs = scene_people(p, p["scenes"][0])[0]
    n = {"videos": 0, "video_seconds": 0.0, "audio": 0, "audio_seconds": 0.0, "files": 0}
    picked, left = pick_video_anchors(recs, {a["id"]: a for a in p["assets"]}, n)
    assert picked == [] and [(x["anchor"], x["why"]) for x in left] == [("va_s", "short")]
    b = _build(p, 0)
    assert not any(v.get("anchor") for v in b["videos"])
    assert any("is not sent: its clip is under 2 s" in i["message"] for i in b["issues"])
    assert any(m.startswith("Mara: video anchor V2 is a 1.50 s clip, so it is not sent") for m in (x["message"] for x in _lint(p)))
