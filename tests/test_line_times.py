"""Spoken lines at their time and place in the shot.

- prompt.py: every line opens with its time in the pass ("At 00:02.000, <Subject 1> (S1) says, <d>…</d>"); a sentence
  of the shot's text that opens with "At MM:SS.mmm," is a timing cue, and a line goes after the cues at or before its
  time and before the later ones (_place_lines). The shot text's cues are scene times and move to pass time like the
  shot's own start. A written [Shot N] that left a line out gets it back at its time among its own cues.
- web/rw/shotfill.js (Write prompts on a scene without shots): "At MM:SS.mmm," before a spoken line is its time, not
  part of its delivery, and an action written after a line opens with the time that line ends, so it keeps its place.
"""

import copy
import json
import os
import shutil
import subprocess

import pytest

from reelwright import prompt
from reelwright.model import normalize_project
from reelwright.planner import plan_scene

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


def _pass_prompt(p, si, k=1):
    s = p["scenes"][si]
    plan = plan_scene(p, s, si)
    return prompt.build_pass(p, s, si, plan, plan["passes"][k - 1])["prompt"]


def _desc(text):
    return text.split("detailed_description:\n", 1)[1].split("\n\noverall_soundscape:", 1)[0]


def test_place_lines():
    text = "[Shot 1] She walks in. At 00:04.000, she sits down. At 00:06.000, the rain starts."
    lines = [(2.0, "A"), (4.0, "B"), (5.5, "C"), (9.0, "D")]
    assert prompt._place_lines(text, lines) == \
        "[Shot 1] She walks in. A At 00:04.000, she sits down. B C At 00:06.000, the rain starts. D"
    assert prompt._place_lines("[Shot 2] At 00:03.000, the shot cuts to a door.", [(3.5, "X")]) == \
        "[Shot 2] At 00:03.000, the shot cuts to a door. X"  # the cut time is not a cue
    assert prompt._place_lines("[Shot 1] Rain. <d>[English] At 00:01.000, go.</d>", [(0.5, "Y")]) == \
        "[Shot 1] Rain. <d>[English] At 00:01.000, go.</d> Y"  # nor a time inside a spoken line
    assert prompt._place_lines("[Shot 1] Rain.", []) == "[Shot 1] Rain."
    assert prompt._timed_line(2.5, "An off-screen voice (S1) says, <d>[English] Hi.</d>") == \
        "At 00:02.500, an off-screen voice (S1) says, <d>[English] Hi.</d>"
    assert prompt._timed_line(0, "<Subject 1> (S1) says, <d>[English] Hi.</d>").startswith("At 00:00.000, <Subject 1>")


def test_lines_open_with_their_time_in_the_pass(harbor):
    p = copy.deepcopy(harbor)
    s = p["scenes"][0]
    s["cast"] = [{"id": "c_mara", "outfit": ""}]
    s["shots"] = [{"t": 0, "camera": "Wide", "text": "@Mara waits on the pier. At 00:04.000, she turns to the sea."},
                  {"t": 6, "camera": "", "text": "a close-up of the lamp"}]
    s["dialogue"] = [{"id": "d_a", "speaker": "c_mara", "t": 2.0, "text": "Not tonight."},
                     {"id": "d_b", "speaker": "c_mara", "t": 5.0, "text": "Maybe tomorrow.", "delivery": "whispers"},
                     {"id": "d_c", "speaker": "c_mara", "t": 6.5, "text": "Go home."}]
    p = normalize_project(p)
    d = _desc(_pass_prompt(p, 0))
    one, two = d.split("\n")[-2:]
    assert one.endswith("<Subject 1> waits on the pier. At 00:02.000, <Subject 1> (S1) says, <d>[English] Not tonight.</d> "
                        "At 00:04.000, she turns to the sea. At 00:05.000, <Subject 1> (S1) whispers, "
                        "<d>[English] Maybe tomorrow.</d>"), one
    assert two == "[Shot 2] At 00:06.000, the shot cuts to a close-up of the lamp. At 00:06.500, <Subject 1> (S1) " \
                  "says, <d>[English] Go home.</d>", two


def test_shot_cues_and_lines_move_to_pass_time(harbor):
    """In pass 2 of the 32 s scene, a cue written in scene time in the shot's text reads in pass time, like the
    shot's start and the line's time."""
    p = copy.deepcopy(harbor)
    s = p["scenes"][1]
    s["shots"][2]["text"] = "the rain starts. At 00:17.000, she pulls up her collar"
    p = normalize_project(p)
    plan = plan_scene(p, p["scenes"][1], 1)
    k = next(i for i, x in enumerate(plan["passes"], 1) if any(abs(float(d["t"]) + float(x["start"]) - 16.0) < 1e-6
                                                                for d in x["dialogue"]))
    x = plan["passes"][k - 1]
    start = float(x["start"])
    d = _desc(_pass_prompt(p, 1, k))
    said = "At {}, <Subject 1> (S1) mutters, <d>[English] Almost home.</d>".format(prompt.spec.fmt_time(16.0 - start))
    cue = "At {}, she pulls up her collar".format(prompt.spec.fmt_time(17.0 - start))
    assert said in d and cue in d and d.index(said) < d.index(cue), d


def test_a_written_shot_gets_a_missing_line_at_its_time(harbor):
    p = copy.deepcopy(harbor)
    s = p["scenes"][0]
    s["cast"] = [{"id": "c_mara", "outfit": ""}]
    s["dialogue"] = [{"id": "d_a", "speaker": "c_mara", "t": 3.0, "text": "Not tonight."}]
    s["prompt"]["sections"]["detailed_description"] = (
        "[Shot 1] Boats rock. At 00:02.000, @Mara steps onto the pier. At 00:05.000, the lamps come on.")
    p = normalize_project(p)
    d = _desc(_pass_prompt(p, 0))
    assert "At 00:02.000, <Subject 1> steps onto the pier. At 00:03.000, <Subject 1> (S1) says, " \
           "<d>[English] Not tonight.</d> At 00:05.000, the lamps come on." in d, d


RUN = r"""
import { pathToFileURL } from "node:url";
const dir = process.argv[2];
const m = await import(pathToFileURL(dir + "/model.js").href);
const f = await import(pathToFileURL(dir + "/shotfill.js").href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const req = JSON.parse(input);
const p = m.normalizeProject(req.project);
const sc = p.scenes[0];
process.stdout.write(JSON.stringify(req.texts.map(t => f.readWritten(p, sc, t, null))));
"""


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_write_prompts_reads_the_lines_times_and_places(tmp_path, harbor):
    script = tmp_path / "run.mjs"
    script.write_text(RUN)
    p = copy.deepcopy(harbor)
    p["scenes"][0]["duration"] = 10.0
    texts = [
        "[Shot 1] A wide shot of the pier. At 00:03.200, @Mara (S1) mutters, <d>[English] Almost home.</d> "
        "At 00:05.000, she pockets the key. At 00:07.500, @Mara (S1) turns to the sea and says, <d>[English] Not tonight.</d> "
        "The lamps flicker.",
    ]
    out = json.loads(subprocess.run([NODE, str(script), os.path.join(ROOT, "web", "rw")], input=json.dumps(
        {"project": p, "texts": texts}), capture_output=True, text=True, check=True).stdout)
    (one,) = out
    assert [(round(d["t"] * 24), d["delivery"], d["text"]) for d in one["lines"]] == [  # on frames
        (77, "mutters", "Almost home."), (180, "says", "Not tonight.")]
    # the action kept from a line's sentence keeps its time; the one after the last line opens with that line's end
    text = one["shots"][0]["text"]
    assert text.startswith("The pier. At 00:05.000, she pockets the key. At 00:07.500, @Mara turns to the sea. At 00:0"), text
    assert text.endswith(", the lamps flicker."), text


def test_a_cue_that_opens_a_shot(harbor):
    """Review 3: a shot text that opens with "At MM:SS.mmm," (as Write prompts writes a shot that opens with a spoken
    line) follows the shot's opening as sentences of their own; its cue places the lines (it was not seen, and a later
    shot read "the shot cuts to at 00:06.000, she leaves.")."""
    p = copy.deepcopy(harbor)
    s = p["scenes"][0]
    s["cast"] = [{"id": "c_mara", "outfit": ""}]
    s["shots"] = [{"t": 0, "camera": "", "text": "At 00:02.000, @Mara turns to the sea."},
                  {"t": 6, "camera": "", "text": "At 00:06.500, she leaves."}]
    s["dialogue"] = [{"id": "d_a", "speaker": "c_mara", "t": 0.5, "text": "Not tonight."},
                     {"id": "d_b", "speaker": "c_mara", "t": 7.0, "text": "Goodbye."}]
    p = normalize_project(p)
    one, two = _desc(_pass_prompt(p, 0)).split("\n")[-2:]
    assert one == "[Shot 1] At 00:00.500, <Subject 1> (S1) says, <d>[English] Not tonight.</d> At 00:02.000, " \
                  "<Subject 1> turns to the sea.", one
    assert two == "[Shot 2] At 00:06.000, the shot cuts to a new angle. At 00:06.500, she leaves. At 00:07.000, " \
                  "<Subject 1> (S1) says, <d>[English] Goodbye.</d>", two


def test_cue_points_and_rebase():
    """Review 6: a cue after "…" or a colon is a cue (as shotfill.js CUES); a cut is not."""
    pts = prompt._cue_points("[Shot 1] Wait… At 00:01.000, go. A close-up: At 00:02.000, run. "
                             "[Shot 2] At 00:03.000, the shot cuts to a door. [Shot 3] At 00:04.000, rain.")
    assert [t for _, t in pts] == [1.0, 2.0, 4.0]
    assert prompt._rebase_shot("A close-up: At 00:17.000, she turns.", 10.0, 32) == "A close-up: At 00:07.000, she turns."
    assert prompt._rebase_shot("Wait… At 00:17.000, she turns.", 10.0, 32) == "Wait… At 00:07.000, she turns."


RUN2 = r"""
import { pathToFileURL } from "node:url";
const dir = process.argv[2];
const m = await import(pathToFileURL(dir + "/model.js").href);
const f = await import(pathToFileURL(dir + "/shotfill.js").href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const req = JSON.parse(input);
const p = m.normalizeProject(req.project);
const out = [];
for (const c of req.cases) {
  const i = p.scenes.findIndex(s => s.id === c.scene);
  const sc = p.scenes[i];
  const plan = m.planScene(p, sc, i);
  if (c.op === "plan") out.push(plan.passes.map(x => ({ start: x.start, keep_in: x.keep_in, shots: x.shots.map(s => ({ id: s.id, t: s.t, continuing: s.continuing })) })));
  else if (c.op === "read") out.push(f.readWritten(p, sc, c.text, c.pass ? plan.passes[c.pass - 1] : null));
  else if (c.op === "passes") { const n = f.takePassShots(p, sc, plan, c.items); out.push({ n, shots: sc.shots }); }
}
process.stdout.write(JSON.stringify(out));
"""


def _run2(tmp_path, p, cases):
    script = tmp_path / "run2.mjs"
    script.write_text(RUN2)
    r = subprocess.run([NODE, str(script), os.path.join(ROOT, "web", "rw")], input=json.dumps({"project": p, "cases": cases}),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_write_prompts_times_review_fixes(tmp_path, harbor):
    """Review 2: a short scene's written times are pass time + the pass's start (keep_in was counted twice). Review 8:
    a written time before the line before it is not taken. Review 3: a shot that opens with a spoken line opens with
    its speaker, not with a time."""
    p = copy.deepcopy(harbor)
    p["scenes"][0]["duration"] = 10.0
    p["scenes"][2]["trim"] = {"keep": "end"}  # the 2.5 s insert keeps the end of what H3 makes
    p = normalize_project(p)
    (plan,) = _run2(tmp_path, p, [{"op": "plan", "scene": "s_short"}])
    start = plan[0]["start"]
    assert start < -1  # H3 makes more than 2.5 s; the cut keeps its end
    short, order, opens = _run2(tmp_path, p, [
        {"op": "read", "scene": "s_short", "pass": 1, "text": "[Shot 1] @Mara at the door. At {}, @Mara (S1) says, "
         "<d>[English] Home.</d>".format(prompt.spec.fmt_time(1.0 - start))},
        {"op": "read", "scene": "s_one", "text": "[Shot 1] @Mara waits. At 00:04.000, @Mara (S1) says, <d>[English] One."
         "</d> At 00:02.000, @Mara (S1) says, <d>[English] Two.</d>"},
        {"op": "read", "scene": "s_one", "text": "[Shot 1] @Mara waits.\n[Shot 2] At 00:05.000, the shot cuts to @Mara "
         "(S1), who whispers, <d>[English] Now.</d> She leaves."}])
    assert round(short["lines"][0]["t"] * 24) == 24, short["lines"]  # 1.0 s into the scene
    assert [round(d["t"] * 24) for d in order["lines"]][0] == 96 and order["lines"][1]["t"] > order["lines"][0]["t"]
    assert opens["shots"][1]["text"].startswith("@Mara. At 00:0"), opens["shots"][1]
    assert opens["shots"][1]["text"].endswith(", she leaves."), opens["shots"][1]


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_write_prompts_on_a_scene_of_several_passes_keeps_scene_times(tmp_path, harbor):
    """Review 1: takePassShots stored the written "At MM:SS," cues in pass time; they are scene times in the shots."""
    p = copy.deepcopy(harbor)
    p["scenes"][1]["prompt"]["auto"] = {"subjects": True, "retention": True, "shots": True}
    p = normalize_project(p)
    (plan,) = _run2(tmp_path, p, [{"op": "plan", "scene": "s_long"}])
    k = next(i for i, x in enumerate(plan) if i > 0 and any(not s["continuing"] for s in x["shots"]))
    x = plan[k]
    lines = []
    for j, s in enumerate(x["shots"], 1):
        if s["continuing"]:
            lines.append("[Shot {}] The walk continues.".format(j))
        else:
            lines.append("[Shot {}] At {}, the shot cuts to the seawall. @Mara walks. At {}, she stops.".format(
                j, prompt.spec.fmt_time(s["t"]), prompt.spec.fmt_time(s["t"] + 1.0)))
    items = [{"index": k + 1, "sections": {"detailed_description": "Rain.\n" + "\n".join(lines)}}]
    (res,) = _run2(tmp_path, p, [{"op": "passes", "scene": "s_long", "items": items}])
    assert res["n"]
    first = next(s for s in x["shots"] if not s["continuing"])
    shot = next(s for s in res["shots"] if s["id"] == first["id"])
    assert "At {}, she stops.".format(prompt.spec.fmt_time(first["t"] + x["start"] + 1.0)) in shot["text"], (shot, x["start"])


def test_a_timed_line_that_opens_a_shot_is_not_its_cut():
    """Review 11: "At 00:01.500, @Mara (S1) says, <d>…</d>" opening a shot is that line's time; the cut lead regexes
    took it for the cut (the first shot dropped it, a later one got no cut marker)."""
    line = "At 00:06.200, @Mara (S1) says, <d>[English] Hi.</d> She leaves."
    assert prompt._lead_kind(line) == "line"
    assert prompt._lead_kind("At 00:06.000, the camera cuts to a door.") == "cut"
    assert prompt._lead_kind("At 00:06.000, a close-up of the door. <d>[English] x</d>") == "time"
    assert prompt._lead_kind("Rain.") == ""
    assert prompt._drop_cut_lead(line) == line
    assert prompt._drop_cut_lead("At 00:06.000, the shot cuts to a door.") == "A door."
    scene = {"duration": 10.0}
    plan = {"passes": [{"index": 1, "start": 0.0, "shots": [{"number": 1, "t": 0.0}, {"number": 2, "t": 6.0}]}]}
    got = prompt.written_shots(scene, plan, plan["passes"][0], "[Shot 1] At 00:01.500, @Mara (S1) says, <d>[English] One."
                               "</d>\n[Shot 2] " + line)
    assert got["text"] == "[Shot 1] At 00:01.500, @Mara (S1) says, <d>[English] One.</d>\n[Shot 2] At 00:06.000, the shot " \
                          "cuts to a new angle. " + line, got


def test_tidy_pass_keeps_a_timed_line_that_opens_a_shot(harbor):
    from reelwright import llm
    from tests.test_llm import long_scene
    p, scene = long_scene(harbor)
    plan, builds = llm.scene_builds(p, scene)
    x, b = plan["passes"][1], builds[1]
    t2 = prompt.spec.fmt_time(float(x["shots"][1]["t"]))
    desc = "[Shot 1] Rain.\n[Shot 2] At 00:05.900, @Mara (S1) mutters, <d>[English] Almost home.</d>"
    out, _ = llm.tidy_pass({"detailed_description": desc}, x, b, {"subjects": True, "retention": True, "shots": True}, 2)
    assert out["detailed_description"].endswith("[Shot 2] At {}, the shot cuts to a new angle. At 00:05.900, @Mara (S1) "
                                                "mutters, <d>[English] Almost home.</d>".format(t2)), out


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_write_prompts_second_pass_fixes(tmp_path, harbor):
    """Review 11: a shot's leading line time stays the line's (shot 1 too); a later shot opening with a timed line starts
    there. Review 12: a line without a time stays inside its shot."""
    p = copy.deepcopy(harbor)
    p["scenes"][0]["duration"] = 10.0
    p = normalize_project(p)
    one, spill = _run2(tmp_path, p, [
        {"op": "read", "scene": "s_one", "text": "[Shot 1] At 00:01.500, @Mara (S1) says, <d>[English] One.</d> She sits."
         "\n[Shot 2] At 00:05.000, @Mara (S1) says, <d>[English] Two.</d>"},
        {"op": "read", "scene": "s_one", "text": "[Shot 1] At 00:01.000, @Mara (S1) says, <d>[English] A long line of many "
         "many words that goes on and on.</d> @Mara (S1) adds, <d>[English] More words follow here again and again "
         "for a while.</d>\n[Shot 2] At 00:03.000, the shot cuts to the door."}])
    assert [round(d["t"] * 24) for d in one["lines"]] == [36, 120] and [s["t"] for s in one["shots"]] == [0, 5], one
    assert spill["shots"][1]["t"] == 3 and spill["lines"][1]["t"] < 3, spill
