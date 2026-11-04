"""web/rw/model.js and reelwright/model.py must agree (added 2026-11-03 v0.6.0).

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
    ]
    p["cast"] = [
        {"id": "c_mara", "name": "Mara", "speaker": "S1", "anchors": ["a_front", "a_side"], "voice": "a_voice",
         "pack_sheet": "auto", "outfits": [{"id": "o_coat", "name": "coat", "assets": ["a_coat", "a_coat"]}],
         "default_outfit": "o_coat"},
        {"id": "c_tom", "name": "Tom O'Brien", "speaker": "S2", "anchors": ["a_letter"], "voice": "a_voice2"},
    ]
    p["scenes"] = [
        {"id": "s_one", "title": "Harbor", "duration": 8.0, "seed_n": 0,
         "cast": [{"id": "c_mara"}], "refs": [{"id": "r_amb", "asset": "a_amb", "role": "reference"}],
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
                  {"id": "r_amb3", "asset": "a_amb", "role": "reference"}],
         "shots": [{"t": 0}, {"t": 6}, {"t": 14.375}, {"t": 22}],
         "dialogue": [{"id": "d_1", "speaker": "c_mara", "t": 3.0, "text": "a"},
                      {"id": "d_2", "speaker": "c_tom", "t": 28.0, "text": "b"}]},
        {"id": "s_short", "title": "Hand", "duration": 2.5, "start": {"mode": "fresh"},
         "trim": {"keep": "custom", "in": 1.208}, "seed_n": 2},
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
         "soundtrack": 5, "cast": [{"name": 5}, None, "c_x"], "assets": {}, "markers": "m", "ui": 3},
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
                      "soundtrack": 1}, {"id": "r"}, 7],
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
    return [harbor_like(), chain(), chain(reanchor=0), tiny, over, mixed, long_cuts, overlap_only, fixed, over_seed,
            random_mode, loop_song, many]


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
