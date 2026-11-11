"""web/rw/model.js and reelwright/model.py must agree.

Runs model.js under node (skipped when node is missing) on the same fixtures, malformed ones included, and compares
normalisation, scene timing (starts, overlaps, visible starts, effective starts), frames_of, seeds, slugify, the pass
plans, the soundtrack segment per pass and the reference budgets.
"""

import copy
import json
import math
import os
import re
import shutil
import subprocess

import pytest

from reelwright import model, soundtrack, spec
from reelwright.planner import plan_scene

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_JS = os.path.join(ROOT, "web", "rw", "model.js")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node is not installed")

RUNNER = r"""
import { pathToFileURL } from "node:url";
const m = await import(pathToFileURL(process.argv[2]).href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const req = JSON.parse(input);
const out = { norm: [], timing: [], slugs: [], frames: [], align: [] };
for (const raw of req.raw) out.norm.push(m.normalizeProject(raw));
for (const p of req.projects) {
  const n = p.scenes.length;
  const idx = [...Array(n).keys()];
  const plans = p.scenes.map((s, i) => m.planScene(p, s, i));
  const starts = m.sceneStarts(p);
  out.timing.push({
    starts: starts.starts, total: starts.total,
    visible: Object.fromEntries(p.scenes.map(s => [s.id, m.visibleStart(p, s.id)])),
    effective: idx.map(i => m.effectiveStart(p, i)),
    tail: idx.map(i => m.tailOverlapFrames(p, i)),
    overlap: idx.map(i => m.sceneOverlapAt(p, i)),
    depth: m.continuationDepth(p),
    seed_n: p.scenes.map(s => s.seed_n),
    next_seed_n: m.nextSeedN(p),
    seeds: p.scenes.map((s, i) => m.sceneSeed(p, s, i)),
    plans,
    songs: plans.map((pl, i) => pl.passes.map(x => m.passSoundtrack(p, starts.starts[p.scenes[i].id], x))),
    has_song: p.scenes.map(s => m.sceneHasSong(p, s)),
    budgets: p.scenes.map(s => m.sceneBudget(p, s)),
    pass_budgets: plans.map((pl, i) => pl.passes.map(x => m.sceneBudget(p, p.scenes[i], x))),
    scene_at: (req.at || []).map(t => m.sceneAt(p, t).id),
    assembled: m.assembledDuration(p),
  });
}
for (const s of req.names) out.slugs.push(m.slugify(s));
for (const x of req.seconds) out.frames.push(m.framesOf(x));
for (const x of req.align) out.align.push([m.alignFramesUp(x), m.alignFramesDown(x)]);
process.stdout.write(JSON.stringify(out));
"""

GEN_ID = re.compile(r"^[a-z]_[0-9a-z]{6,9}$")  # model.new_id (8 hex) / model.js newId (9 base36)


def run_js(tmp_path, req):
    runner = tmp_path / "runner.mjs"
    runner.write_text(RUNNER)
    res = subprocess.run([NODE, str(runner), MODEL_JS], input=json.dumps(req), capture_output=True, text=True,
                         timeout=120)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def strings_in(x, out=None):
    out = set() if out is None else out
    if isinstance(x, str):
        out.add(x)
    elif isinstance(x, dict):
        for k, v in x.items():
            out.add(k)
            strings_in(v, out)
    elif isinstance(x, list):
        for v in x:
            strings_in(v, out)
    return out


def masked(p, known):
    """Random ids that normalisation created (not in the input) become <id1>, <id2> ... in a fixed walk order, and
    project_id is dropped (only the editor makes one)."""
    p = copy.deepcopy(p)
    p.pop("project_id", None)
    names = {}

    def walk(x):
        if isinstance(x, dict):
            return {k: walk(x[k]) for k in sorted(x)}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str) and x not in known and GEN_ID.match(x):
            return names.setdefault(x, "<id{}>".format(len(names) + 1))
        return x
    return walk(p)


def assert_same(py, js, where):
    """Deep equality; numbers must be equal exactly (1 == 1.0)."""
    if isinstance(py, dict) and isinstance(js, dict):
        assert set(py) == set(js), "{}: keys differ: py-only {} js-only {}".format(
            where, sorted(set(py) - set(js)), sorted(set(js) - set(py)))
        for k in py:
            assert_same(py[k], js[k], "{}.{}".format(where, k))
    elif isinstance(py, (list, tuple)) and isinstance(js, list):
        assert len(py) == len(js), "{}: length {} != {}".format(where, len(py), len(js))
        for i, (a, b) in enumerate(zip(py, js)):
            assert_same(a, b, "{}[{}]".format(where, i))
    elif isinstance(py, bool) or isinstance(js, bool):
        assert py is js or py == js and type(py) is type(js), "{}: {!r} != {!r}".format(where, py, js)
    elif isinstance(py, (int, float)) and isinstance(js, (int, float)):
        assert py == js, "{}: {!r} != {!r}".format(where, py, js)
    else:
        assert py == js, "{}: {!r} != {!r}".format(where, py, js)


# ---------------------------------------------------------------- fixtures

def harbor_like():
    p = model.default_project("Harbor Lights")
    p["assets"] = [
        {"id": "a_front", "kind": "image", "name": "Mara front", "file": "x/front.png"},
        {"id": "a_side", "kind": "image", "name": "Mara side", "file": "x/side.png"},
        {"id": "a_coat", "kind": "image", "name": "coat", "file": "x/coat.png"},
        {"id": "a_voice", "kind": "audio", "name": "voice", "file": "x/voice.wav", "duration": 4.2},
        {"id": "a_voice2", "kind": "audio", "name": "voice 2", "file": "x/voice2.wav", "duration": 3.0},
        {"id": "a_letter", "kind": "image", "name": "letter", "file": "x/letter.png"},
        {"id": "a_dolly", "kind": "video", "name": "dolly", "file": "x/dolly.mp4", "duration": 4.2},
        {"id": "a_amb", "kind": "audio", "name": "rain", "file": "x/rain.wav", "duration": 6.0},
        {"id": "a_song", "kind": "audio", "name": "song", "file": "x/song.wav", "duration": 40.0},
        {"id": "a_nofile", "kind": "audio", "name": "lost", "file": "", "duration": 30.0},
        {"id": "a_belly", "kind": "image", "name": "belly", "file": "x/belly.png"},
        {"id": "a_pose", "kind": "image", "name": "pose", "file": "x/pose.png"},
    ]
    p["cast"] = [
        {"id": "c_mara", "name": "Mara", "speaker": "S1", "anchors": ["a_front", "a_side"], "voice": "a_voice",
         "pack_sheet": "auto", "outfits": [{"id": "o_coat", "name": "coat", "assets": ["a_coat", "a_coat"]}],
         "default_outfit": "o_coat"},
        {"id": "c_tom", "name": "Tom O'Brien", "speaker": "S2", "anchors": ["a_letter"], "voice": "a_voice2"},
        {"id": "c_belly", "name": "Beer belly", "kind": "prop", "part_of": "c_mara", "anchors": ["a_belly", "a_front"]},
        {"id": "c_badge", "name": "Badge", "kind": "prop", "part_of": "c_badge", "anchors": ["a_letter"]},
    ]
    p["scenes"] = [
        {"id": "s_one", "title": "Harbor", "duration": 8.0, "seed_n": 0,
         "cast": [{"id": "c_belly"}, {"id": "c_mara"}, {"id": "c_badge"}], "refs": [{"id": "r_amb", "asset": "a_amb", "role": "reference"}],
         "dialogue": [{"id": "d_neg", "speaker": "c_mara", "t": -0.5, "text": "early"},
                      {"id": "d_end", "speaker": "c_mara", "t": 8.0 - 0.4 / 24, "text": "last half frame"}],
         "shots": [{"t": -1}, {"t": 2.0}]},
        {"id": "s_long", "title": "Walk", "duration": 32.0, "seed_n": 1,
         "start": {"mode": "tail", "overlap_frames": 39},
         "cast": [{"id": "c_mara"}],
         "refs": [{"id": "r_letter", "asset": "a_letter", "role": "keyframe", "time": 25.0},
                  {"id": "r_dolly", "asset": "a_dolly", "role": "reference", "soundtrack": True},
                  {"id": "r_kf_end", "asset": "a_letter", "role": "keyframe", "time": 32.0 - 0.3 / 24},
                  {"id": "r_first", "asset": "a_front", "role": "first_frame"},
                  {"id": "r_last", "asset": "a_side", "role": "last_frame"},
                  {"id": "r_amb2", "asset": "a_amb", "role": "reference"},
                  {"id": "r_amb3", "asset": "a_amb", "role": "reference"},
                  {"id": "r_pose", "asset": "a_pose", "role": "pose", "cast": "c_mara", "time": 20.0},
                  {"id": "r_pose_end", "asset": "a_pose", "role": "pose", "cast": "c_tom", "time": 99.0},
                  {"id": "r_pose_x", "asset": "a_belly", "role": "pose", "cast": "c_nobody", "time": 1.0},
                  {"id": "r_pose_snd", "asset": "a_amb", "role": "pose", "cast": "c_mara", "time": 1.0},
                  {"id": "r_dolly_b", "asset": "a_dolly", "role": "reference", "in": 1.0, "out": 3.5, "soundtrack": True},
                  {"id": "r_dolly_c", "asset": "a_dolly", "role": "reference", "in": "2"},
                  {"id": "r_amb_clip", "asset": "a_amb", "role": "reference", "in": 2.0, "out": 4.0},
                  {"id": "r_amb_clip2", "asset": "a_amb", "role": "reference", "in": 2.0, "out": 4.0},
                  {"id": "r_voice_clip", "asset": "a_voice", "role": "reference", "in": 0.5},
                  {"id": "r_amb_long", "asset": "a_amb", "role": "reference", "in": 5.0, "out": 99.0},
                  {"id": "r_amb_late", "asset": "a_amb", "role": "reference", "in": 9.0}],
         "shots": [{"t": 0}, {"t": 6}, {"t": 14.375}, {"t": 22}],
         "dialogue": [{"id": "d_1", "speaker": "c_mara", "t": 3.0, "text": "a"},
                      {"id": "d_2", "speaker": "c_tom", "t": 28.0, "text": "b"}]},
        {"id": "s_short", "title": "Hand", "duration": 2.5, "start": {"mode": "fresh"},
         "trim": {"keep": "custom", "in": 1.208}, "seed_n": 2,
         "cast": [{"id": "c_belly"}]},
        {"id": "s_mid", "title": "Middle", "duration": 3.1, "trim": {"keep": "middle"}, "start": {"mode": "fresh"},
         "seed_n": 7},
        {"id": "s_end", "title": "End keep", "duration": 1.0, "trim": {"keep": "end"}, "start": {"mode": "last_frame"},
         "seed_n": 3},
    ]
    p["soundtrack"] = [
        {"id": "t_song", "asset": "a_song", "start": 30.03125, "in": 0.0625, "sync": True, "mix": True},
        {"id": "t_loop", "asset": "a_amb", "start": -2.5, "loop": True, "sync": False},
        {"id": "t_nofile", "asset": "a_nofile", "start": 0, "sync": True},
    ]
    return p


def chain(reanchor=2, durations=(8.0, 6.0, 6.0, 6.0, 6.0), modes=("fresh", "tail", "tail", "tail", "tail"),
          overlaps=(39, 39, 90, 39, 39)):
    p = model.default_project("Chain")
    p["global"]["continuity"]["reanchor_after"] = reanchor
    p["scenes"] = [{"id": "s_{}".format(i), "duration": d, "start": {"mode": m, "overlap_frames": o}}
                   for i, (d, m, o) in enumerate(zip(durations, modes, overlaps))]
    return p


def malformed():
    return [
        "",
        "not json",
        "[1, 2]",
        "{\"scenes\": {}}",
        {"scenes": [None]},
        {"scenes": [], "global": "x"},
        {"scenes": [1, "two", None, {"refs": {}, "prompt": "text", "start": "tail", "duration": "abc"}],
         "soundtrack": 5, "cast": [{"name": 5, "part_of": 7}, None, "c_x", {"kind": "prop", "part_of": None}],
         "assets": {}, "markers": "m", "ui": 3},
        {"scenes": [{"id": "s_a", "duration": "12.5"}, {"id": "s_a", "duration": -3}, {"id": "s_a", "duration": 1e9},
                    {"id": "s a!", "duration": None}, {"id": 7, "duration": True}, {"id": "", "duration": [1]}]},
        {"name": None, "slug": "My Film", "scenes": [{"title": 12.5, "color": [], "notes": {}, "lock": "yes",
                                                     "start": {"mode": "warp", "overlap_frames": "39.9"}}]},
        {"name": "Ömer's Café — 2", "slug": "untitled-ab12", "scenes": [{}]},
        {"name": "x" * 90, "scenes": [{}]},
        {"name": "Москва", "slug": "", "scenes": [{}]},
        {"name": "a", "slug": "a\n", "scenes": [{}]},
        {"scenes": [{
            "shots": [{"t": 5, "id": "h_1"}, {"t": "2", "id": "h_1"}, {"t": "abc"}, None, {"t": -1, "camera": 3}],
            "dialogue": [{"t": 4, "speaker": 5}, {"t": 1, "id": "d"}, {"t": 1, "id": "d"}, "x"],
            "refs": [{"id": "r", "asset": 3, "role": "x", "time": "1.5", "keep": ["a", 1, None, {}],
                      "soundtrack": 1}, {"id": "r"}, 7, {"role": "pose", "cast": 5, "time": "x"},
                     {"in": "1.02", "out": "3.51"}, {"in": -2, "out": -1}, {"in": 1.0208333, "out": 0},
                     {"in": "x", "out": True}, {"in": None, "out": "4"}],
            "cast": ["c_1", {"id": 2, "outfit": None}, 3, None],
            "prompt": {"mode": "weird", "auto": "x", "sections": {"summary": 5, "extra": "keep"},
                       "pass_prompts": {"1": "a", "2": 3, "3": None, "4": ["x"]}},
            "overrides": {"seed": "", "steps": "abc", "width": "1024", "height": 768.9, "sampler": 5,
                          "quality": None, "loras": {"mode": "x", "items": [None, {"name": "l", "strength": "0.5"}],
                                                     "strengths": {"l_1": "0.3", "l_2": "x"}}},
            "transition": {"mode": "zoom", "frames": "12", "audio_fade_frames": "x"},
            "trim": {"keep": "x", "in": -2}}]},
        {"scenes": [{}], "overrides": [], "global": {"defaults": {"start_mode": "x", "duration": "abc",
                                                                   "overlap_frames": -4, "language": 5},
                                                      "sampling": {"seed": "77", "seed_mode": 3, "sigma_shift": "x"},
                                                      "continuity": {"reanchor_after": "2.7"},
                                                      "loras": [None, {"name": "g", "enabled": 0}],
                                                      "merge": {"score": {"asset": "a_s", "volume_db": "x",
                                                                          "duck": None}},
                                                      "long": "x", "llm": None}},
        {"scenes": [{}], "assets": [{"kind": "video", "code": "P1"}, {"kind": "image", "code": "p1"},
                                    {"kind": "image"}, {"kind": "weird", "code": 5, "duration": "3.5"},
                                    {"kind": "audio", "defaults": "x"}, None],
         "cast": [{"id": "c", "pack_sheet": 1, "outfits": [None, {"assets": [1, "a"]}], "lora": "x",
                   "anchors": "a", "kind": "robot"}]},
        {"scenes": [{"seed_n": 3}, {}, {"seed_n": 3}, {"seed_n": "1"}, {"seed_n": -1}, {"seed_n": 2.5},
                    {"seed_n": 1e10}, {"seed_n": 1.0}, {"seed_n": True}]},
        {"scenes": [{}, {}], "soundtrack": [{"asset": "a", "mute": "false", "sync": 0, "start": "x", "in": -5,
                                             "marker": "loud", "id": 4},
                                            {"id": "t_score", "asset": "b"}, None],
         "global": {"merge": {"score": {"asset": "a_old", "volume_db": -6, "duck": False}}}},
        {"scenes": [{}], "camera_presets": [None, {"name": 3}], "markers": [{"t": "2"}, None, {"text": None}]},
        {"scenes": [{}], "camera_presets": "x", "ui": {"selected": "nope", "zoom": "abc", "snap": 0}},
        {"scenes": [{"id": "s_a", "merge": 5, "transition": {"mode": "dip", "frames": "7.9"}},
                    {"id": "s_b", "merge": {"transition": "WIPE", "direction": 3, "frames": "24.7", "color": "#ABCDEF",
                                            "audio_frames": -3, "fade_in": {"frames": -5, "color": "red"},
                                            "fade_out": 12, "audio_fade_in": "1e9", "audio_fade_out": None,
                                            "volume_db": "-80", "mute": 1, "color_match": "scene", "color_ref": 7,
                                            "brightness": 5, "contrast": -1, "saturation": "2.5", "extra": "kept"}},
                    {"id": "s_c", "merge": {"transition": "zoom", "direction": "up", "color": "#12345", "fade_in": [],
                                            "color_match": "previous", "mute": "yes", "volume_db": True,
                                            "frames": 1e300, "brightness": -0.0, "contrast": "0.5"}},
                    {"id": "s_d", "merge": None, "transition": "x"},
                    {"id": "s_e", "merge": [], "transition": {"mode": "crossfade", "frames": -4,
                                                             "audio_fade_frames": 2.9}}],
         "global": {"merge": {"hard_cut": "zoom", "transition_frames": "abc", "audio_fade_frames": 4.5,
                              "color_match": 1, "color_ref_scene": "s_gone"}}},
        {"scenes": [{"id": "s_a"}, {"id": "s_b", "transition": {"mode": "", "frames": 30}}, {"id": "s_c"}],
         "global": {"merge": {"hard_cut": "dip", "color_match": True, "color_ref_scene": "s_b"}}},
        {"scenes": [{"id": "s_a"}, {"id": "s_b"}], "global": {"merge": {"color_match": "yes", "hard_cut": 5}}},
        {"scenes": [{"duration": 40.0}, {"duration": 30.0, "start": {"mode": "tail"}}],
         "global": {"long": {"guide_vae": 5, "carry_audio": "no", "seam_video_ref": 0, "handoff": "LATENT",
                             "pass_cache": None, "seam_mode": "overlap"}}},
        {"scenes": [{"duration": 40.0}], "global": {"long": {"guide_vae": "h3_full.safetensors", "carry_audio": False,
                                                             "seam_video_ref": False, "handoff": "latent",
                                                             "pass_cache": "lossless"}}},
        {"scenes": [{}], "global": {"long": {"handoff": ["pixels"], "pass_cache": {"x": 1}, "carry_audio": 1.5,
                                             "seam_video_ref": None, "guide_vae": None}}},
        {"scenes": [{}], "asset_groups": [{"id": "g_set", "name": "Harbor set", "description": "night"},
                                          {"id": "g_set", "name": 5}, None, "x", {"name": None, "description": []},
                                          {"id": 7, "extra": "kept"}],
         "assets": [{"kind": "image", "group": "g_set", "tags": [" wet  docks ", "wet docks", "\tnight\n", 3, 2.5,
                                                                   None, {}, "", "   ", "é" * 70, "ü" * 59 + " x"]},
                    {"kind": "video", "group": "g_set_2", "tags": "x"}, {"kind": "audio", "group": "g_gone"},
                    {"kind": "image", "group": 7, "tags": [True, False]}, {"kind": "image", "group": None}]},
        {"scenes": [{}], "asset_groups": "x", "assets": [{"kind": "image", "group": "g_a", "tags": None}]},
        # LoRA trigger words (v0.21.0): one line, single spaces, at most 120 characters, on every kind of LoRA
        {"scenes": [{"overrides": {"loras": {"mode": "add", "items": [{"name": "s.safetensors", "trigger": " in   sks\tstyle "},
                                                                      {"name": "t.safetensors", "trigger": None}]}}}],
         "cast": [{"kind": "character", "name": "Birten", "lora": {"name": "b.safetensors", "trigger": "ohwx\nman"}},
                  {"kind": "character", "name": "Ada", "lora": {"name": "a.safetensors", "trigger": 7}},
                  {"kind": "character", "name": "Tom", "lora": {"name": "", "trigger": ["x"]}}],
         "global": {"loras": [{"name": "g.safetensors", "trigger": "x" * 130}, {"name": "h.safetensors"}],
                    "draft": {"lora": "turbo.safetensors", "lora_trigger": "  fast  "}}},
        # crops (v0.20.0): crop_of {asset, box [x, y, w, h]} kept when whole, clamped to 0..1; dropped otherwise
        {"scenes": [{}], "assets": [{"kind": "image", "crop_of": {"asset": "a_src", "box": [0.1, "0.2", 0.5, 1.4]}},
                                    {"kind": "image", "crop_of": {"asset": "a_src", "box": [0.1, 0.2, -0.5, True]}},
                                    {"kind": "image", "crop_of": {"asset": "", "box": [0, 0, 1, 1]}},
                                    {"kind": "image", "crop_of": {"asset": "a_src", "box": [0, 0, 1]}},
                                    {"kind": "image", "crop_of": "a_src"}, {"kind": "image", "crop_of": None}]},
        {"scenes": [{}], "cast": [{"kind": "character", "name": "Nar", "voice_desc": "  a deep voice  "},
                                  {"kind": "character", "name": "Tom", "voice_desc": 5}, {"kind": "prop", "name": "Box", "voice_desc": None},
                                  {"kind": "character", "name": "Ada", "voice_desc": ["x"]}],
         "global": {"continuity": {"describe_voices": False}, "merge": {"subtitle_timing": "planned"}}},
        {"scenes": [{}], "global": {"continuity": {"describe_voices": "no"}, "merge": {"subtitle_timing": "loud"}}},
        {"scenes": [{}], "global": {"continuity": {"describe_voices": None}, "merge": {"subtitle_timing": None}}},
    ]


def timing_fixtures():
    tiny = chain(durations=(8.0, 0.1, 6.0, 0.15, 6.0), modes=("fresh", "tail", "tail", "last_frame", "tail"))
    over = chain(durations=(1.0, 6.0, 2.0, 9.0, 12.0), modes=("tail", "tail", "tail", "fresh", "tail"),
                 overlaps=(39, 90, 120, 200, 300))
    mixed = chain(reanchor=1, durations=(5.0, 7.0, 7.0, 7.0, 7.0, 7.0),
                  modes=("fresh", "last_frame", "tail", "fresh", "tail", "tail"), overlaps=(39, 39, 73, 39, 22, 5))
    long_cuts = chain(durations=(32.0, 45.0, 20.0), modes=("fresh", "tail", "fresh"))
    long_cuts["scenes"][0]["shots"] = [{"t": 0}, {"t": 6}, {"t": 14.375}, {"t": 22}]
    long_cuts["scenes"][2]["shots"] = [{"t": 0}, {"t": 15.5}]
    long_cuts["global"]["long"].update(seam_mode="cuts", max_pass_frames=243, overlap_frames=56)
    overlap_only = copy.deepcopy(long_cuts)
    overlap_only["global"]["long"]["seam_mode"] = "overlap"
    fixed = chain()
    fixed["global"]["sampling"].update(seed_mode="fixed", seed=5)
    over_seed = chain()
    over_seed["scenes"][2]["overrides"] = {"seed": 99}
    random_mode = chain()
    random_mode["global"]["sampling"]["seed_mode"] = "random"
    loop_song = harbor_like()
    loop_song["soundtrack"] = [{"id": "t_l", "asset": "a_amb", "start": 1.0 / 3, "in": 0.1, "loop": True,
                                "sync": True, "marker": "reference"},
                               {"id": "t_s", "asset": "a_song", "start": 50.0, "out": 3.0, "in": 1.0, "sync": True}]
    many = harbor_like()
    many["assets"] += [{"id": "a_p{}".format(k), "kind": "image", "file": "x/{}.png".format(k)} for k in range(9)]
    many["scenes"][0]["refs"] += [{"id": "r_p{}".format(k), "asset": "a_p{}".format(k)} for k in range(9)]
    many["cast"][1]["pack_sheet"] = False
    many["cast"][1]["anchors"] = ["a_p1", "a_p2"]
    v061 = chain(durations=(4.0, 4.0, 4.0, 4.0), modes=("fresh", "fresh", "last_frame", "fresh"))
    v061["global"]["merge"].update(hard_cut="crossfade", transition_frames=12, audio_fade_frames=6, color_match=True,
                                   color_ref_scene="s_1")
    v061["scenes"][1]["transition"] = {"mode": "dip", "frames": 18, "audio_fade_frames": 0}
    merged = chain()
    for k, s in enumerate(merged["scenes"]):
        s["merge"] = dict(model.default_merge(), transition=model.MERGE_TRANSITIONS[k % 10], direction="up",
                          frames=10 + k, color="#ff8800", fade_in={"frames": k, "color": "#00ff00"},
                          fade_out={"frames": 2 * k, "color": "#0000ff"}, audio_fade_in=k, audio_fade_out=k + 1,
                          volume_db=-3.5, mute=k == 2, color_match=model.COLOR_MATCH_MODES[k % 3],
                          color_ref="s_0", brightness=0.1, contrast=1.2, saturation=0.8)
    return [harbor_like(), chain(), chain(reanchor=0), tiny, over, mixed, long_cuts, overlap_only, fixed, over_seed,
            random_mode, loop_song, many, v061, merged] + continuation_fixtures() + v080_fixtures()


def v080_fixtures():
    """scene.prompt.passes in every state (the current layout, a pass that moved,
    another layout, junk entries), dialogue lines with and without a duration (CJK, junk values, lines across a seam
    and past the end), shots with camera_amp / camera_speed / framing (and junk), and Global -> Long scenes ->
    seam_video_ref off (continuation_fixtures again)."""
    from reelwright.planner import plan_scene as plan_of
    p = harbor_like()
    p["global"]["long"]["seam_mode"] = "overlap"
    s = p["scenes"][1]  # s_long, 32 s
    s["shots"] = [{"id": "h_a", "t": 0, "camera": "the camera pushes in", "camera_amp": "small", "camera_speed": "slow",
                   "framing": "close-up", "text": "@Mara leaves the pier."},
                  {"id": "h_b", "t": 6, "camera": "Tracking", "camera_amp": "LARGE", "camera_speed": 3,
                   "framing": "wide shot", "text": "along the seawall"},
                  {"id": "h_c", "t": 14.375, "camera": "", "camera_amp": "large", "framing": "dutch angle"},
                  {"id": "h_d", "t": 22, "camera_speed": "fast", "framing": None}]
    s["dialogue"] = [{"id": "d_1", "speaker": "c_mara", "t": 13.5, "text": "Is anyone still out there tonight, Tom?"},
                     {"id": "d_2", "speaker": "c_tom", "t": 20.0, "text": "你好，世界！ 今日は。", "duration": "2.5"},
                     {"id": "d_3", "speaker": "c_tom", "t": 25.0, "text": "— ... !", "duration": 0},
                     {"id": "d_4", "speaker": "c_mara", "t": 30.5, "text": "one two three four five", "duration": -1},
                     {"id": "d_5", "speaker": "c_mara", "t": 3.0, "text": "a b", "duration": "x"},
                     {"id": "d_6", "speaker": "c_mara", "t": 40.0, "text": "after the end", "duration": 1e9}]
    plan = plan_of(model.normalize_project(p), model.normalize_project(p)["scenes"][1], 1)
    cur = [{"start": x["start"], "end": x["end"],
            "sections": {"summary": "pass {} summary".format(x["index"]), "overall_soundscape": " " if x["index"] == 2
                         else "rain {}".format(x["index"])}} for x in plan["passes"]]
    s["prompt"] = {"sections": {"summary": "The whole walk home.", "overall_soundscape": "wind"}, "passes": cur}
    moved = copy.deepcopy(p)
    moved["scenes"][1]["duration"] = 35.0  # the last pass ends later, so its text is "moved"
    other = copy.deepcopy(p)
    other["scenes"][1]["prompt"]["passes"] = [
        {"start": 0, "end": 16.0, "sections": {"summary": "first half", "detailed_description": "[Shot 1] Rain."}},
        {"start": "15.5", "end": "32", "sections": {"summary": "second half"}},
        {"start": 31, "end": 32, "sections": {"non_diegetic_music": "drums"}},
        None, 5, {"start": 2, "end": 3, "sections": "x"}, {"sections": {"summary": 7, "extra": "kept"}, "extra": 1}]
    one = copy.deepcopy(p)  # a one-pass scene with texts from another layout
    one["scenes"][0]["prompt"] = {"passes": [{"start": 0, "end": 4, "sections": {"summary": "a"}},
                                             {"start": 4, "end": 8, "sections": {"summary": "b"}}]}
    one["scenes"][1]["prompt"] = {"passes": [{"start": 0, "end": 1, "sections": {"summary": "only"}}]}
    one["scenes"][1]["duration"] = 6.0
    seam_off = [copy.deepcopy(x) for x in continuation_fixtures()[:1]]
    for x in seam_off:
        x["global"]["long"]["seam_video_ref"] = False
    return [p, moved, other, one] + seam_off


def continuation_fixtures():
    """The continuation reference in the budget (model.pass_continuation / sceneBudget):
    a picture that packs the anchors, one that does not fit, a clip next to three videos, a clip without an audio
    slot for its sound, a clip from a 1 s scene, overlap seams, and the same projects with the switch off."""
    p = harbor_like()
    p["assets"] += [{"id": "a_p{}".format(k), "kind": "image", "file": "x/{}.png".format(k)} for k in range(9)]
    p["assets"] += [{"id": "a_v{}".format(k), "kind": "video", "file": "x/v{}.mp4".format(k), "duration": 3.0 + k}
                    for k in range(3)]
    mara = [{"id": "c_mara"}]
    p["scenes"] = [
        {"id": "s_a", "duration": 6.0, "seed_n": 0},
        {"id": "s_pack", "duration": 5.0, "seed_n": 1, "start": {"mode": "last_frame"}, "cast": mara,
         "refs": [{"id": "r_a{}".format(k), "asset": "a_p{}".format(k), "role": "reference"} for k in range(7)]},
        {"id": "s_full", "duration": 5.0, "seed_n": 2, "start": {"mode": "last_frame"}, "cast": mara,
         "refs": [{"id": "r_b{}".format(k), "asset": "a_p{}".format(k), "role": "reference"} for k in range(9)]},
        {"id": "s_vid3", "duration": 6.0, "seed_n": 3, "start": {"mode": "tail", "overlap_frames": 39},
         "refs": [{"id": "r_c{}".format(k), "asset": "a_v{}".format(k), "role": "reference"} for k in range(3)]},
        {"id": "s_mute", "duration": 6.0, "seed_n": 4, "start": {"mode": "tail", "overlap_frames": 39},
         "refs": [{"id": "r_d0", "asset": "a_v0", "role": "reference", "soundtrack": True},
                  {"id": "r_d1", "asset": "a_amb", "role": "reference"},
                  {"id": "r_d2", "asset": "a_voice2", "role": "reference"}]},
        {"id": "s_snd", "duration": 6.0, "seed_n": 5, "start": {"mode": "tail", "overlap_frames": 39},
         "refs": [{"id": "r_e0", "asset": "a_v1", "role": "reference", "soundtrack": True}]},
        {"id": "s_one", "duration": 1.0, "seed_n": 6},
        {"id": "s_after1", "duration": 6.0, "seed_n": 7, "start": {"mode": "tail", "overlap_frames": 39}},
        {"id": "s_long", "duration": 32.0, "seed_n": 8, "start": {"mode": "tail", "overlap_frames": 39}, "cast": mara,
         "dialogue": [{"id": "d_l", "speaker": "c_mara", "t": 20.0, "text": "x"}]},
    ]
    p["soundtrack"] = []
    p["global"]["continuity"]["reanchor_after"] = 20
    p["global"]["long"]["seam_mode"] = "overlap"
    off = copy.deepcopy(p)
    off["global"]["continuity"]["name_continuation"] = False
    reanchored = copy.deepcopy(p)
    reanchored["global"]["continuity"]["reanchor_after"] = 0
    return [p, off, reanchored]


NAMES = ["Harbor Lights — v2", "", "Ömer", "Москва", "日本語", "a" * 100, "  _x_  ", "2024", "Café-au-lait", "x\ty",
         "İstanbul", "ﬁlm", None, 5, 5.5, "a---b", "_", "Ñandú 2", "a_" * 40, "Ö" * 70, "ab cd", "x　y"]
SECONDS = [0, 0.5 / 24, 1.5 / 24, 2.5 / 24, 3.5 / 24, 1 / 48, 10.0208333, -0.5 / 24, -1.5 / 24, 7.0, 12.345, 600,
           0.1, 2.5, 8.0 - 0.5 / 24]
ALIGN = [0, 1, 4.5, 5, 6, 21.5, 22.5, 124, 125, 192.5, 361, 362, 1000, -3]


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    raw = [x if isinstance(x, str) else json.dumps(x) for x in malformed()]
    raw += [json.dumps(p) for p in timing_fixtures()]
    projects = [model.normalize_project(p) for p in timing_fixtures()]
    req = {"raw": raw, "projects": projects, "names": NAMES, "seconds": SECONDS, "align": ALIGN,
           "at": [-1, 0, 1 / 24, 5.9, 6.0, 6.375, 8.0, 8.01, 14.0, 16.375, 17.0, 1000]}
    js = run_js(tmp_path_factory.mktemp("parity"), req)
    return raw, projects, req, js


def test_normalize_matches(results):
    raw, _, _, js = results
    assert len(js["norm"]) == len(raw)
    for k, (r, out) in enumerate(zip(raw, js["norm"])):
        py = model.normalize_project(r)
        try:
            known = strings_in(json.loads(r))
        except ValueError:
            known = set()
        assert_same(masked(py, known), masked(out, known), "norm[{}]".format(k))
        assert isinstance(out["project_id"], str) and out["project_id"]  # the editor always has one
        again = model.normalize_project(py)  # normalising twice changes nothing
        assert_same(masked(again, known | strings_in(py)), masked(py, known | strings_in(py)), "twice[{}]".format(k))


def test_timing_plans_and_budgets_match(results):
    _, projects, req, js = results
    for k, (p, out) in enumerate(zip(projects, js["timing"])):
        where = "project[{}]".format(k)
        starts, total = model.scene_starts(p)
        assert_same(starts, out["starts"], where + ".starts")
        assert_same(total, out["total"], where + ".total")
        assert_same(model.visible_starts(p), out["visible"], where + ".visible")
        n = len(p["scenes"])
        assert_same([model.effective_start(p, i) for i in range(n)], out["effective"], where + ".effective")
        assert_same([model.tail_overlap_frames(p, i) for i in range(n)], out["tail"], where + ".tail")
        assert_same([model.scene_overlap_at(p, i) for i in range(n)], out["overlap"], where + ".overlap")
        assert_same(model.continuation_depth(p), out["depth"], where + ".depth")
        assert_same([s["seed_n"] for s in p["scenes"]], out["seed_n"], where + ".seed_n")
        assert_same(model.next_seed_n(p), out["next_seed_n"], where + ".next_seed_n")
        random = p["global"]["sampling"]["seed_mode"] == "random"
        seeds = [model.scene_seed(p, s, i) for i, s in enumerate(p["scenes"])]
        for i, s in enumerate(p["scenes"]):
            if random and s["overrides"].get("seed") is None:
                assert out["seeds"][i] is None
                out["plans"][i]["seed"] = seeds[i]
                for x in out["plans"][i]["passes"]:
                    x["seed"] = seeds[i] + x["index"] - 1
            else:
                assert_same(seeds[i], out["seeds"][i], where + ".seeds[{}]".format(i))
        plans = [plan_scene(p, s, i) for i, s in enumerate(p["scenes"])]
        assert_same(plans, out["plans"], where + ".plans")
        songs = [[soundtrack.pass_soundtrack(p, starts[p["scenes"][i]["id"]], x) for x in pl["passes"]]
                 for i, pl in enumerate(plans)]
        assert_same(songs, out["songs"], where + ".songs")
        assert_same([any(x is not None for x in row) for row in songs], out["has_song"], where + ".has_song")
        names = {"video_seconds": "videoSeconds", "audio_seconds": "audioSeconds"}

        def js_keys(b):
            return {names.get(key, key): v for key, v in b.items()}
        budgets = [js_keys(model.scene_media_counts(p, s)) for s in p["scenes"]]
        assert_same(budgets, out["budgets"], where + ".budgets")
        pass_budgets = [[js_keys(model.scene_media_counts(p, p["scenes"][i], x)) for x in pl["passes"]]
                        for i, pl in enumerate(plans)]
        assert_same(pass_budgets, out["pass_budgets"], where + ".pass_budgets")
        vis = model.visible_starts(p)
        expect_at = []
        for t in req["at"]:
            on = [s["id"] for s in p["scenes"] if vis[s["id"]] <= t]
            expect_at.append(on[-1] if on else p["scenes"][0]["id"])
        assert_same(expect_at, out["scene_at"], where + ".scene_at")
        assembled = sum(s["duration"] - model.scene_overlap_at(p, i) for i, s in enumerate(p["scenes"]))
        assert math.isclose(assembled, out["assembled"], abs_tol=1e-9)


def test_slug_frames_and_alignment_match(results):
    _, _, req, js = results
    assert_same([model.slugify(x) for x in req["names"]], js["slugs"], "slugify")
    assert all(model.SLUG_RE.fullmatch(s) for s in js["slugs"])
    assert_same([spec.frames_of(x) for x in req["seconds"]], js["frames"], "frames_of")
    assert_same([[spec.align_frames_up(x), spec.align_frames_down(x)] for x in req["align"]], js["align"], "align")


JS_CHECKS = r"""
import { pathToFileURL } from "node:url";
const m = await import(pathToFileURL(process.argv[2]).href);
const out = {};
// no endless loops on junk (a non-numeric duration used to hang the browser)
out.align = [m.alignFramesUp(NaN), m.alignFramesDown(NaN), m.alignFramesUp(Infinity), m.alignFramesDown(-Infinity),
             m.alignFramesUp("abc"), m.alignFramesUp(1e300) > 0];
const p = m.normalizeProject({ scenes: [{ id: "s_a", duration: 8 }, { id: "s_b", duration: 10, start: { mode: "tail", overlap_frames: 39 } }] });
Object.defineProperty(p, "__rwv", { value: 1, enumerable: false, writable: true });
const first = m.sceneStarts(p);
out.same_object = m.sceneStarts(p).starts === first.starts;    // memoised for one version
p.scenes[0].duration = 4;
out.stale = m.sceneStarts(p).total === first.total;             // same version: the memo answers
p.__rwv = 2;
out.fresh_total = m.sceneStarts(p).total;                        // a new version recomputes
out.enumerable = Object.keys(p).includes("__rwv");
const copy = JSON.parse(JSON.stringify(p));
out.copy_total = m.sceneStarts(copy).total;                      // no __rwv: computed fresh
out.scene_at = [m.sceneAt(p, 0).id, m.sceneAt(p, 4 - 39 / 24).id, m.sceneAt(p, 4).id, m.sceneAt(p, 99).id, m.sceneAt(p, NaN).id];
out.new_seed = m.defaultScene(p).seed_n;
out.next_seed = m.nextSeedN(p);
out.default_pid = typeof m.defaultProject().project_id;
const tracks = m.normalizeProject({ scenes: [{}], assets: [{ id: "a", kind: "audio", duration: 9 }],
  soundtrack: [{ asset: "a", sync: true }], cast: [{ name: "O'Brien" }, { name: "Old Keeper" }, { name: "Ömer" }, { name: "" }] });
out.tags = m.tagCandidates(tracks).map(x => x.tag);
out.regex = [..."@Anna. mail a@b.c @@lit @O'Brien's @Ömer".matchAll(m.tagRegex())].map(x => x[1]);
process.stdout.write(JSON.stringify(out));
"""


def test_js_guards_memo_and_tags(tmp_path):
    runner = tmp_path / "checks.mjs"
    runner.write_text(JS_CHECKS)
    res = subprocess.run([NODE, str(runner), MODEL_JS], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["align"] == [5, 5, 5, 5, 5, True]
    assert out["same_object"] and out["stale"] and not out["enumerable"]
    assert out["fresh_total"] == out["copy_total"] == 4 + 10 - 39 / 24
    assert out["scene_at"] == ["s_a", "s_a", "s_b", "s_b", "s_a"]
    assert out["new_seed"] == out["next_seed"] == 2
    assert out["default_pid"] == "string"
    # a track whose asset has no file never plays, so no @soundtrack; names that are tag names go without braces
    assert out["tags"] == ["@A1", "@O'Brien", "@{Old Keeper}", "@Ömer", "@tail"]
    assert out["regex"] == ["Anna", "O'Brien's", "Ömer"]


# ---- fuzz: a valid project with random parts replaced by junk, normalised by both ----
JUNK = [None, 0, 1, -1, 2.5, "x", "", "12", " 7.5 ", "abc", [], [None], {}, {"a": 1}, True, False, 1e300, -0.0,
        "tail", "fresh", "auto", "P1"]


def _paths(x, path=()):
    yield path
    if isinstance(x, dict):
        for k in x:
            yield from _paths(x[k], path + (k,))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _paths(v, path + (i,))


def test_fuzzed_projects_match(tmp_path):
    import random
    rng = random.Random(20261103)
    base = [harbor_like()] + timing_fixtures()
    raws = []
    for _ in range(150):
        p = copy.deepcopy(rng.choice(base))
        for _ in range(rng.randint(1, 8)):
            path = rng.choice([q for q in _paths(p) if q])
            target = p
            for k in path[:-1]:
                target = target[k]
            target[path[-1]] = copy.deepcopy(rng.choice(JUNK))
        raws.append(json.dumps(p))
    projects = [model.normalize_project(r) for r in raws]
    js = run_js(tmp_path, {"raw": raws, "projects": projects, "names": [], "seconds": [], "align": [], "at": []})
    names = {"video_seconds": "videoSeconds", "audio_seconds": "audioSeconds"}
    for k, (r, out, p, t) in enumerate(zip(raws, js["norm"], projects, js["timing"])):
        known = strings_in(json.loads(r))
        assert_same(masked(model.normalize_project(r), known), masked(out, known), "fuzz[{}]".format(k))
        assert_same(model.scene_starts(p)[0], t["starts"], "fuzz[{}].starts".format(k))
        plans = [plan_scene(p, s, i) for i, s in enumerate(p["scenes"])]
        for pl, jl in zip(plans, t["plans"]):
            if jl["seed"] is None or not 0 <= pl["seed"] < 2 ** 53 - 10:  # random mode / beyond JS integers
                jl["seed"] = pl["seed"]
                for x in jl["passes"]:
                    x["seed"] = pl["seed"] + x["index"] - 1
        assert_same(plans, t["plans"], "fuzz[{}].plans".format(k))
        assert_same([{names.get(a, a): b for a, b in model.scene_media_counts(p, s).items()} for s in p["scenes"]],
                    t["budgets"], "fuzz[{}].budgets".format(k))


# ---- per-pass sections, dialogue lengths, camera wording -----------------------------------
RUNNER_V080 = r"""
import { pathToFileURL } from "node:url";
const m = await import(pathToFileURL(process.argv[2]).href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const req = JSON.parse(input);
const out = { scenes: [], seconds: req.lines.map(d => m.dialogueSeconds(d)),
  camera: req.camera.map(([c, a, s]) => m.cameraSentence(c, a, s)), framing: req.framing.map(f => m.framingPhrase(f)),
  constants: [m.DEFAULT_CAMERA, m.CAMERA_AMPS, m.CAMERA_SPEEDS, m.FRAMINGS, m.FRAMING_PHRASE, m.CAMERA_VERSION] };
for (const p of req.projects) {
  out.scenes.push(p.scenes.map((s, i) => {
    const plan = m.planScene(p, s, i);
    const n = plan.passes.length;
    const ks = [...Array(n + 2).keys()];  // 0 and n + 1 are out of range
    // JS-only edit helpers, on copies
    const a = structuredClone(s), b = structuredClone(s);
    m.setPassSection(p, a, plan, n, "summary", "set by hand");
    m.writePassTexts(p, b, plan, [{ index: 1, sections: { summary: "written", music: "x", detailed_description: 5 } },
      { index: n + 1, sections: { summary: "beyond" } }, { index: "1", sections: { overall_soundscape: "sea" } }, null]);
    return { texts: m.passTexts(p, s, plan), relayout: m.relayoutPassTexts(p, s, plan),
      sections: ks.map(k => m.passSections(p, s, plan, k)), spans: m.dialogueSpans(s, plan),
      set: a.prompt.passes, write: b.prompt.passes };
  }));
}
process.stdout.write(JSON.stringify(out));
"""

LINES = [{"text": "Is anyone still out there?"}, {"text": ""}, {"text": "你好世界"}, {"text": "你好世界你好世界你好世界"},
         {"text": "日本語のテキストです。 ok"}, {"text": "한국어 문장입니다"}, {"text": "— ... !!"}, {"text": "a\u00a0b\u3000c"},
         {"text": "e\u0301te 2024 x_y"}, {"text": "𠀀𠀁 emoji 😀 word"}, {"text": 5}, {"text": None},
         {"text": "x", "duration": 2.5}, {"text": "x", "duration": "3"}, {"text": "one two", "duration": 0},
         {"text": "one two", "duration": -2}, {"text": "one two", "duration": "abc"}, {"text": "x", "duration": 1e9},
         {"text": "x", "duration": True}, None, "text", {"text": " ".join(["word"] * 40)}]
CAMERAS = ["the camera pushes in", "Wide", "the camera holds a static shot.", "The camera whips left!", "  ", "",
           None, 5, "...", "slow push-in toward the subject", "ölçek", "𠀀 camera"]


def _v080_projects():
    return [model.normalize_project(p) for p in v080_fixtures() + [harbor_like()]]


def test_v080_helpers_match(tmp_path):
    projects = _v080_projects()
    camera = [[c, a, s] for c in CAMERAS for a in model.CAMERA_AMPS + ("medium", None)
              for s in model.CAMERA_SPEEDS + ("normal",)]
    framing = list(model.FRAMINGS) + ["Close-up", "constructor", None, 3]
    req = {"projects": projects, "lines": LINES, "camera": camera, "framing": framing}
    runner = tmp_path / "v080.mjs"
    runner.write_text(RUNNER_V080)
    res = subprocess.run([NODE, str(runner), MODEL_JS], input=json.dumps(req), capture_output=True, text=True,
                         timeout=120)
    assert res.returncode == 0, res.stderr
    js = json.loads(res.stdout)
    assert_same([model.dialogue_seconds(d) for d in LINES], js["seconds"], "dialogue_seconds")
    assert_same([model.camera_sentence(c, a, s) for c, a, s in camera], js["camera"], "camera_sentence")
    assert_same([model.framing_phrase(f) for f in framing], js["framing"], "framing_phrase")
    assert_same([[list(x) for x in model.DEFAULT_CAMERA], list(model.CAMERA_AMPS), list(model.CAMERA_SPEEDS),
                 list(model.FRAMINGS), model.FRAMING_PHRASE, model.CAMERA_VERSION], js["constants"], "constants")
    for k, (p, scenes) in enumerate(zip(projects, js["scenes"])):
        for i, (s, out) in enumerate(zip(p["scenes"], scenes)):
            where = "project[{}].scene[{}]".format(k, i)
            plan = plan_scene(p, s, i)
            n = len(plan["passes"])
            assert_same(model.pass_texts(p, s, plan), out["texts"], where + ".pass_texts")
            assert_same(model.relayout_pass_texts(p, s, plan), out["relayout"], where + ".relayout")
            assert_same([model.pass_sections(p, s, plan, x) for x in range(n + 2)], out["sections"], where + ".sections")
            assert_same(model.dialogue_spans(s, plan), out["spans"], where + ".spans")
            # the JS edit helpers lay the list out first, then write
            want = model.relayout_pass_texts(p, s, plan)
            want[n - 1]["sections"]["summary"] = "set by hand"
            assert_same(want, out["set"], where + ".setPassSection")
            want = model.relayout_pass_texts(p, s, plan)
            want[0]["sections"].update(summary="written", overall_soundscape="sea")
            assert_same(want, out["write"], where + ".writePassTexts")
    # the fixtures cover every case
    texts = [model.pass_texts(p, s, plan_scene(p, s, i)) for p in projects for i, s in enumerate(p["scenes"])]
    assert any(t["same"] and t["stored"] for t in texts) and any(t["moved"] for t in texts)
    assert any(t["unused"] for t in texts) and any(t["same"] and not t["stored"] for t in texts)
    spans = [x for p in projects for i, s in enumerate(p["scenes"]) for x in model.dialogue_spans(s, plan_scene(p, s, i))]
    assert any(x["seam"] for x in spans) and any(x["past_end"] for x in spans) and any(x["pass"] is None for x in spans)


def test_v080_seam_video_ref_off_budget_matches_the_build():
    """With Global -> Long scenes -> seam_video_ref off a pass after an overlap seam sends no
    <Video 1> (only the anchor), the budget (model.scene_media_counts = model.js sceneBudget) counts it the same way,
    and the tail clip a continuing scene starts from is still sent."""
    from reelwright import prompt
    on = model.normalize_project(continuation_fixtures()[0])
    off = copy.deepcopy(on)
    off["global"]["long"]["seam_video_ref"] = False
    i, s = next((i, s) for i, s in enumerate(off["scenes"]) if s["id"] == "s_long")
    plan = plan_scene(off, s, i)
    assert [x["seam_before"] for x in plan["passes"]][1:] == ["overlap"] * (len(plan["passes"]) - 1)
    for p, later in ((on, "video"), (off, "")):
        ctx = prompt.prepare(p)
        builds = [prompt.build_pass(p, p["scenes"][i], i, plan, x, ctx=ctx) for x in plan["passes"]]
        assert builds[0]["continuation"]["source"] == "prev_scene_tail"
        for x, b in zip(plan["passes"][1:], builds[1:]):
            assert (b["continuation"] or {}).get("kind", "") == later
            assert b["guides"][0]["source"] == "prev_pass_tail"  # anchored either way
            c = model.scene_media_counts(p, p["scenes"][i], x)
            assert c["continuation"].startswith("video") if later else c["continuation"] == ""
            assert c["videos"] == len(b["videos"]) and c["files"] == len(b["images"]) + len(b["videos"]) + len(b["audios"])


def test_v0140_clip_helpers_match(tmp_path):
    """model.ref_clip / ref_trimmed / clip_key / ref_tokens = model.js refClip / refTrimmed /
    clipKey / refTokens."""
    p = model.normalize_project(harbor_like())
    p["assets"].append({"id": "a_v2", "kind": "video", "code": "V9", "name": "x", "file": "x/v.mp4", "duration": 0})
    p = model.normalize_project(p)
    s = next(x for x in p["scenes"] if x["id"] == "s_long")
    s["refs"].append({"id": "r_unknown_len", "asset": "a_v2", "role": "reference", "in": 1.0, "out": None})
    s["refs"].append({"id": "r_unknown_len2", "asset": "a_v2", "role": "reference", "in": 1.0, "out": 2.0})
    idx = model.project_index(p)
    py = {"clips": [[model.ref_clip(r, idx["assets"].get(r["asset"])), model.ref_trimmed(r),
                     list(model.clip_key(r, idx["assets"][r["asset"]])) if r["asset"] in idx["assets"] else None]
                    for r in s["refs"]],
          "tokens": model.ref_tokens(p, s), "snap": [model.snap_frame(x) for x in (0, 1.0208333, 2.5 / 24, 7.999)]}
    runner = tmp_path / "clips.mjs"
    runner.write_text(r"""
import { pathToFileURL } from "node:url";
const m = await import(pathToFileURL(process.argv[2]).href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const p = JSON.parse(input);
const s = p.scenes.find(x => x.id === "s_long");
const asset = id => p.assets.find(a => a.id === id);
process.stdout.write(JSON.stringify({
  clips: s.refs.map(r => [m.refClip(r, asset(r.asset)), m.refTrimmed(r), asset(r.asset) ? m.clipKey(r, asset(r.asset)) : null]),
  tokens: m.refTokens(p, s), snap: [0, 1.0208333, 2.5 / 24, 7.999].map(m.snapFrame) }));
""")
    res = subprocess.run([NODE, str(runner), MODEL_JS], input=json.dumps(p), capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert_same(py, json.loads(res.stdout), "clips")
    assert py["tokens"]["r_dolly"] == "@" + idx["assets"]["a_dolly"]["code"]
    assert py["tokens"]["r_dolly_b"].endswith(".2") and py["tokens"]["r_dolly_c"].endswith(".3")

