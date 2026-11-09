"""Spoken lines at their time and place in the shot (added 2026-11-12 v0.17.0; Sencer: "The dialogues are not added to
shots at the given time index. the dialogue should have it's proper place and time index in the shot").

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
