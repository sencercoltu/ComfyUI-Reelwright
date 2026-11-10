"""A scene written without shots gets its shots and spoken lines (Sencer: "when creating a
single shot scene, the shot section (and dialogues) are not populated. They should be populated. currently everything
shows only in detailed_description section").

web/rw/shotfill.js takes the [Shot N] lines and <d>…</d> spoken lines of a written description apart (run under node);
the backend asks for every spoken line as a sentence of its own and, for a scene with no lines yet, keeps the lines
the LLM writes (Write prompts, the Prompt rewriter).
"""

import asyncio
import copy
import json
import os
import shutil
import subprocess

import pytest

from reelwright import llm, model, prompt
from reelwright.planner import plan_scene

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web", "rw")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")

RUNNER = r"""
import { pathToFileURL } from "node:url";
const dir = process.argv[process.argv.length - 1];
const m = await import(pathToFileURL(dir + "/model.js").href);
const f = await import(pathToFileURL(dir + "/shotfill.js").href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const req = JSON.parse(input);
const out = [];
for (const c of req.cases) {
  const p = m.normalizeProject(c.project);
  const sc = p.scenes.find(s => s.id === c.scene);
  if (c.op === "read") out.push(f.readWritten(p, sc, c.text, null));
  else if (c.op === "fillable") out.push(f.fillable(p, sc) !== null);
  else if (c.op === "camera") out.push(f.cameraOf(p, c.text));
  else if (c.op === "write") { const n = f.writeShots(p, sc); out.push({ n, scene: sc }); }
  else if (c.op === "passes") {  // the written passes of a scene of several passes
    const plan = m.planScene(p, sc, 0);
    const n = f.takePassShots(p, sc, plan, c.items);
    out.push({ n, scene: sc, items: c.items, plan: plan.passes.map(x => x.shots.map(s => [s.id, s.continuing])) });
  }
  else { const n = f.fillScene(p, sc); out.push({ n, scene: sc, words: f.fillWords(n) }); }
}
process.stdout.write(JSON.stringify(out));
"""

STORY = ("Cinematic, rain-soaked night, teal and amber palette.\n"
         "[Shot 1] A medium shot of @Mara at the harbor wall in a navy pea coat; behind her the lamps glow. The camera "
         "slowly pushes in. @Mara (S1), with a husky low voice, mutters, <d>[English] Almost home.</d> @{Old Keeper} "
         "steps out of the shadows and (S2) calls, <d>[English] You're late again.</d> She turns toward him, startled.")


def project(desc=STORY, duration=10.0, **scene):
    p = model.default_project("Fill")
    p["cast"] = [{"id": "c_mara", "name": "Mara", "kind": "character", "language": "English"},
                 {"id": "c_keep", "name": "Old Keeper", "kind": "character"},
                 {"id": "c_narr", "name": "Narrator", "kind": "character"},
                 {"id": "c_harbor", "name": "Harbor", "kind": "location"}]
    s = p["scenes"][0]
    s.update({"id": "s_1", "duration": duration, "shots": [], "dialogue": [], "cast": []})
    s.update(scene)
    s["prompt"]["sections"]["detailed_description"] = desc
    return p


def run(cases):
    r = subprocess.run([NODE, "--input-type=module", "-e", RUNNER, WEB], input=json.dumps({"cases": cases}),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@needs_node
def test_shots_and_lines_are_read_from_the_description():
    texts = [
        STORY,
        "[Shot 1] A wide shot: the pier at dusk. @Mara walks toward the camera.\n"
        "[Shot 2] At 00:04.500, the shot cuts to a close-up of @Mara as she whispers, <d>[English] He promised.</d>\n"
        "[Shot 3] At 00:07.000, the shot cuts to @{Old Keeper} (S2), who replies, <d>[Turkish] Gel içeri.</d>",
        "Soft morning light. [Shot 1] An aerial view of the harbor. The Narrator (S1) says in an off-screen voiceover: "
        "<d>[English] It began with a letter.</d> while their lips remain completely closed. Boats bob gently.",
        "[Shot1] As the rain starts, @Mara (S1) mutters, <d>[English] Almost home.</d>, her voice breaking. The camera "
        "holds still.",
        "@Mara folds the letter and (S1) whispers, <d>[English] Not tonight.</d> Then (S1) adds, <d>[English] Maybe "
        "tomorrow.</d>",
        "Warm light, film grain.",
    ]
    one, three, vo, tail, nolabel, style = run([{"op": "read", "project": project(), "scene": "s_1", "text": t}
                                                for t in texts])
    assert one["pre"] == "Cinematic, rain-soaked night, teal and amber palette."
    assert one["shots"] == [{"t": 0, "text": "@Mara at the harbor wall in a navy pea coat; behind her the lamps glow. "
                             "At 00:01.500, @{Old Keeper} steps out of the shadows. At 00:03.000, she turns toward him, "
                             "startled.", "camera": "the camera pushes in", "camera_amp": "", "camera_speed": "slow",
                             "framing": "medium"}]
    assert [round(d["t"] * 24) for d in one["lines"]] == [12, 43] and "at" not in one["lines"][0]  # frames
    assert [(d["speaker"], d["language"], d["delivery"], d["text"]) for d in one["lines"]] == [
        ("c_mara", "English", "mutters", "Almost home."), ("c_keep", "English", "calls", "You're late again.")]
    assert 0 < one["lines"][0]["t"] < one["lines"][1]["t"] < 10

    assert [(s["t"], s["framing"], s["text"]) for s in three["shots"]] == [
        (0, "wide", "The pier at dusk. @Mara walks toward the camera."), (4.5, "close-up", "@Mara."),
        (7, "", "@{Old Keeper}.")]
    assert [(d["speaker"], d["language"], d["delivery"]) for d in three["lines"]] == [
        ("c_mara", "English", "whispers"), ("c_keep", "Turkish", "replies")]
    assert 4.5 <= three["lines"][0]["t"] < 7 <= three["lines"][1]["t"] < 10

    assert vo["pre"] == "Soft morning light." and vo["shots"][0]["text"] == \
        "An aerial view of the harbor. At 00:02.500, Boats bob gently."
    assert (vo["lines"][0]["speaker"], vo["lines"][0]["delivery"]) == ("c_narr", "voiceover")

    assert tail["shots"][0]["text"] == "" and tail["shots"][0]["camera"] == "the camera holds a static shot"
    assert tail["lines"][0]["delivery"] == "mutters as the rain starts, her voice breaking"

    # no [Shot N]: the whole text is one shot; (S1) alone is the speaker named with it before
    assert nolabel["pre"] == "" and nolabel["shots"][0]["text"] == "@Mara folds the letter."
    assert [(d["speaker"], d["delivery"], d["text"]) for d in nolabel["lines"]] == [
        ("c_mara", "whispers", "Not tonight."), ("c_mara", "adds", "Maybe tomorrow.")]
    assert style is None  # style sentences only: nothing to put on the timeline


@needs_node
def test_fill_scene_puts_them_in_the_scene():
    p = project()
    with_lines = project(dialogue=[{"id": "d_1", "speaker": "c_mara", "t": 2.0, "text": "Almost home."}])
    auto_off = project()
    auto_off["scenes"][0]["prompt"]["auto"] = {"subjects": True, "retention": True, "shots": False}
    shots = project(shots=[{"id": "h_1", "t": 0, "text": "rain"}])
    raw = project()
    raw["scenes"][0]["prompt"]["mode"] = "raw"
    long = project(duration=40.0)
    place = project(desc="[Shot 1] A wide shot of @Harbor at night. The lamps flicker.")
    filled, kept_lines, off, has_shots, is_raw, multi, at_place = run(
        [{"op": "fill", "project": x, "scene": "s_1"} for x in (p, with_lines, auto_off, shots, raw, long, place)])
    sc = filled["scene"]
    assert filled["n"] == {"shots": 1, "lines": 2} and filled["words"] == "1 shot and 2 spoken lines"
    assert sc["prompt"]["sections"]["detailed_description"] == "Cinematic, rain-soaked night, teal and amber palette."
    assert len(sc["shots"]) == 1 and sc["shots"][0]["id"].startswith("h_") and sc["shots"][0]["t"] == 0
    assert [(d["speaker"], d["delivery"], d["language"]) for d in sc["dialogue"]] == [
        ("c_mara", "mutters", "English"), ("c_keep", "calls", "English")]
    assert [c["id"] for c in sc["cast"]] == ["c_mara", "c_keep"]  # the speakers join the scene
    # a scene that has lines keeps them; with automatic shots off the description stays as written
    assert kept_lines["n"] == {"shots": 1, "lines": 0} and [d["id"] for d in kept_lines["scene"]["dialogue"]] == ["d_1"]
    assert off["n"]["shots"] == 1 and off["scene"]["prompt"]["sections"]["detailed_description"] == STORY
    # a cast member named with @ in a shot joins the scene too
    assert at_place["n"] == {"shots": 1, "lines": 0} and [c["id"] for c in at_place["scene"]["cast"]] == ["c_harbor"]
    # nothing for a scene with shots, a raw prompt or a scene made in several passes
    assert has_shots["n"] is None and is_raw["n"] is None and multi["n"] is None


@needs_node
def test_filled_scene_builds_the_same_lines():
    """After the fill the editor writes the shot and its lines back: every spoken line once, with its speaker."""
    out = run([{"op": "fill", "project": project(), "scene": "s_1"}])[0]
    p = project()
    p["scenes"][0] = out["scene"]
    p = model.normalize_project(p)
    s = p["scenes"][0]
    plan = plan_scene(p, s, 0)
    b = prompt.build_pass(p, s, 0, plan, plan["passes"][0])
    text = b["prompt"]
    assert text.count("Almost home.") == 1 and text.count("You're late again.") == 1
    assert "(S1)" in text and "(S2)" in text and "mutters, <d>[English] Almost home.</d>" in text
    assert "[Shot 1] A medium shot: The camera pushes in at slow speed. <Subject 1> at the harbor wall" in text
    assert text.count("pushes in") == 1 and "Cinematic, rain-soaked night" in text


# ---- framing and camera move -------------------------------------------------------------------------------------

@needs_node
def test_framing_and_camera_move_are_read_from_a_shot():
    texts = [
        "A medium shot of @Mara at the harbor wall. The camera slowly pushes in. @Mara looks up.",
        "A wide shot: the pier at dusk. The camera pushes in with small amplitude at slow speed.",
        "Close-up of @Mara. The camera holds still.",
        "Low angle, the lighthouse against the sky. The camera quickly tilts up.",
        "@Mara walks along the seawall. The camera tracks her as she walks past the boats.",
        "Wide on the pier. Slow push-in.",
        "Rain falls on the harbor. Gulls cry.",
        "A medium shot of @Mara. The camera holds a static shot with small amplitude at slow speed.",
    ]
    got = run([{"op": "camera", "project": project(), "scene": "s_1", "text": t} for t in texts])
    as_fields = [(g["framing"], g["camera"], g["camera_amp"], g["camera_speed"], g["text"]) for g in got]
    assert as_fields == [
        ("medium", "the camera pushes in", "", "slow", "@Mara at the harbor wall. @Mara looks up."),
        ("wide", "the camera pushes in", "small", "slow", "The pier at dusk."),
        ("close-up", "the camera holds a static shot", "", "", "@Mara."),
        ("low angle", "the camera tilts up", "", "fast", "The lighthouse against the sky."),
        ("", "the camera tracks the moving subject", "", "",
         "@Mara walks along the seawall. The camera tracks her as she walks past the boats."),
        ("", "the camera pushes in", "", "slow", "Wide on the pier."),  # "Wide on" is not a framing
        ("", "", "", "", "Rain falls on the harbor. Gulls cry."),
        ("medium", "the camera holds a static shot", "", "", "@Mara."),  # a static shot has no amplitude or speed
    ]


@needs_node
def test_write_prompts_puts_the_camera_in_the_shots():
    story = ("Night.\n[Shot 1] A medium shot of @Mara at the wall. The camera slowly pushes in. @Mara (S1) mutters, "
             "<d>[English] Almost home.</d>\n[Shot 2] At 00:05.000, the shot cuts to a close-up of @Mara. The camera "
             "holds a static shot.")
    new = project(desc=story)
    shots = project(desc=story, shots=[{"id": "h_1", "t": 0, "camera": "Wide", "text": "the wall"},
                                       {"id": "h_2", "t": 6.0, "camera": "", "text": "her face"}],
                    dialogue=[{"id": "d_1", "speaker": "c_mara", "t": 1.0, "text": "Almost home."}])
    one_shot = project(desc=story, shots=[{"id": "h_1", "t": 0, "camera": "Wide", "text": "the wall"}])
    filled, updated, other = run([{"op": "write", "project": x, "scene": "s_1"} for x in (new, shots, one_shot)])
    f = [(s["t"], s["framing"], s["camera"], s["camera_speed"], s["text"]) for s in filled["scene"]["shots"]]
    assert f == [(0, "medium", "the camera pushes in", "slow", "@Mara at the wall."),
                 (5, "close-up", "the camera holds a static shot", "", "@Mara.")]
    assert filled["n"]["shots"] == 2 and filled["n"]["lines"] == 1
    # shots on the timeline take the written text, framing and move; their times and the lines stay
    u = [(s["id"], s["t"], s["framing"], s["camera"], s["text"]) for s in updated["scene"]["shots"]]
    assert u == [("h_1", 0, "medium", "the camera pushes in", "@Mara at the wall."),
                 ("h_2", 6, "close-up", "the camera holds a static shot", "@Mara.")]
    assert updated["n"] == {"shots": 2, "lines": 0, "updated": True, "added": 0, "kept": 0}
    assert [d["id"] for d in updated["scene"]["dialogue"]] == ["d_1"]
    assert updated["scene"]["prompt"]["sections"]["detailed_description"] == "Night."
    assert other["n"]["added"] == 1 and [s["camera"] for s in other["scene"]["shots"]] == [
        "the camera pushes in", "the camera holds a static shot"]


# ---- written shots replace the shots ------------------------------------------------------------------------------

@needs_node
def test_written_shots_replace_the_shots_whatever_their_count():
    two = ("Night.\n[Shot 1] A medium shot of @Mara at the wall. The camera slowly pushes in.\n[Shot 2] At 00:05.000, the "
           "shot cuts to a close-up of @Mara. The camera holds a static shot.")
    one_shot = project(desc=two, shots=[{"id": "h_1", "t": 0, "camera": "Wide", "text": "the wall"}])
    three = project(desc=two, shots=[{"id": "h_1", "t": 0, "text": "a"}, {"id": "h_2", "t": 4.0, "text": "b"},
                                     {"id": "h_3", "t": 8.0, "text": "c"}])
    late = project(desc=two.replace("00:05.000", "00:09.900"), shots=[{"id": "h_1", "t": 0, "text": "a"}])
    more, fewer, spread = run([{"op": "write", "project": x, "scene": "s_1"} for x in (one_shot, three, late)])
    # more lines than shots: the first takes line 1, line 2 joins the timeline at its written start
    m = [(x["id"][:2], x["t"], x["framing"], x["camera"], x["text"]) for x in more["scene"]["shots"]]
    assert m == [("h_", 0, "medium", "the camera pushes in", "@Mara at the wall."),
                 ("h_", 5, "close-up", "the camera holds a static shot", "@Mara.")]
    assert more["scene"]["shots"][0]["id"] == "h_1" and more["n"]["added"] == 1 and more["n"]["shots"] == 2
    assert more["scene"]["prompt"]["sections"]["detailed_description"] == "Night."
    # fewer lines than shots: the shots it wrote are replaced, the rest keep their text and time
    f = [(x["id"], x["t"], x["text"]) for x in fewer["scene"]["shots"]]
    assert f == [("h_1", 0, "@Mara at the wall."), ("h_2", 4, "@Mara."), ("h_3", 8, "c")]
    assert fewer["n"]["kept"] == 1 and fewer["scene"]["prompt"]["sections"]["detailed_description"] == "Night."
    # a written start the scene has no room for is spread over the time left
    assert [x["t"] for x in spread["scene"]["shots"]] == [0, 5]


@needs_node
def test_shots_of_a_scene_of_several_passes_take_what_each_pass_writes():
    shots = [{"id": "h_1", "t": 0, "text": "a"}, {"id": "h_2", "t": 6.0, "text": "b"}, {"id": "h_3", "t": 13.0, "text": "c"}]
    cut = project(desc="", duration=24.0, shots=shots)
    items = [{"index": 1, "sections": {"detailed_description": "Dusk.\n[Shot 1] A wide shot of the pier. The camera "
                                                                  "pans left.\n[Shot 2] At 00:06.000, the shot cuts to a "
                                                                  "close-up of @Mara."}},
             {"index": 2, "sections": {"detailed_description": "[Shot 1] A medium shot of the door. The camera holds "
                                                                  "still.\n[Shot 2] At 00:05.000, the shot cuts to rain."}}]
    one = project(desc="", duration=24.0, shots=[{"id": "h_1", "t": 0, "text": "a"}])
    cont = [{"index": 1, "sections": {"detailed_description": "[Shot 1] A wide shot of @Mara walking. The camera "
                                                                 "tracks the moving subject."}},
            {"index": 2, "sections": {"detailed_description": "[Shot 1] The shot continues seamlessly: @Mara reaches "
                                                                 "the door."}}]
    a, b = run([{"op": "passes", "project": cut, "scene": "s_1", "items": items},
                {"op": "passes", "project": one, "scene": "s_1", "items": cont}])
    assert a["plan"] == [[["h_1", False], ["h_2", False]], [["h_3", False]]]
    got = [(x["id"], x["framing"], x["camera"], x["text"]) for x in a["scene"]["shots"]]
    assert got == [("h_1", "wide", "the camera pans left", "The pier."), ("h_2", "close-up", "", "@Mara."),
                   ("h_3", "", "", "c")]  # pass 2 wrote 2 lines for its 1 shot: left as written
    assert a["items"][0]["sections"]["detailed_description"] == "Dusk."
    assert a["items"][1]["sections"]["detailed_description"].startswith("[Shot 1] A medium shot of the door.")
    # a shot that runs on into the next pass: its start goes into the shot, its continuation stays that pass's line
    assert b["plan"] == [[["h_1", False]], [["h_1", True]]]
    assert b["scene"]["shots"][0]["text"] == "@Mara walking." and b["scene"]["shots"][0]["camera"] == "the camera tracks the moving subject"
    assert b["items"][0]["sections"]["detailed_description"] == ""
    assert b["items"][1]["sections"]["detailed_description"].startswith("[Shot 1] The shot continues seamlessly")


# ---- the backend: Write prompts and the rewriter ----------------------------------------------------------------

def test_write_prompts_asks_for_the_shot_and_lines_of_a_scene_without_shots():
    p = model.normalize_project(project(desc="", summary="x"))
    s = p["scenes"][0]
    s["prompt"]["sections"]["summary"] = "Mara tells the keeper she is home."
    plan, builds = llm.scene_builds(p, s)
    assert llm.fills_timeline(s, plan)
    body = llm.pass_request(p, s, plan, builds, 1)
    assert "none on the timeline yet: write it as one shot; the editor puts it on the timeline" in body
    assert "when the whole-scene note or the instruction has someone speak, write those lines" in body
    assert llm.FILL_LINES_RULE in body
    assert llm.FILL_CAMERA_RULE in body
    s2 = copy.deepcopy(s)
    s2["shots"] = [{"id": "h_1", "t": 0.0, "camera": "", "text": "rain"}]
    p["scenes"][0] = s2
    plan2, builds2 = llm.scene_builds(p, s2)
    assert not llm.fills_timeline(s2, plan2) and llm.writes_shots(s2, plan2)
    body2 = llm.pass_request(p, s2, plan2, builds2, 1)
    assert llm.FILL_CAMERA_RULE in body2 and "none on the timeline yet: write it as one shot" not in body2
    # shots but no spoken lines: the LLM may write the lines the note asks for, the editor takes them (free_lines)
    assert llm.free_lines(s2, plan2) and "has someone speak, write those lines" in body2
    s2["dialogue"] = [{"id": "d_1", "speaker": "c_mara", "t": 1.0, "language": "English", "text": "Home."}]
    assert not llm.free_lines(s2, plan2) and "has someone speak" not in llm.pass_request(p, s2, plan2, builds2, 1)
    s2["dialogue"] = []
    s2["prompt"]["auto"]["shots"] = False
    assert not llm.writes_shots(s2, plan2) and llm.FILL_CAMERA_RULE not in llm.pass_request(p, s2, plan2, builds2, 1)
    s3 = copy.deepcopy(s)
    s3["duration"] = 40.0
    p["scenes"][0] = s3
    plan3, builds3 = llm.scene_builds(p, s3)
    assert len(plan3["passes"]) > 1 and llm.writes_shots(s3, plan3)
    body3 = llm.pass_request(p, s3, plan3, builds3, 1)
    assert llm.FILL_CAMERA_RULE in body3 and "write the lines spoken in this pass's part of the scene" in body3


def test_lines_written_for_a_scene_without_lines_are_kept():
    x = {"shots": [], "dialogue": []}
    secs = {"detailed_description": "[Shot 1] Rain. @Mara (S1) mutters, <d>[English] Almost home.</d> She smiles. "
                                    "@Mara (S1) says, <d>[English] Almost home.</d>"}
    kept, warns = llm.tidy_pass(secs, x, {}, {"shots": True}, 1, known={"mara"}, free_lines=True)
    assert kept["detailed_description"].count("Almost home.") == 1  # only the second copy goes
    assert any("second copy" in w for w in warns)
    dropped, warns = llm.tidy_pass(secs, x, {}, {"shots": True}, 1, known={"mara"})
    assert "Almost home." not in dropped["detailed_description"]  # as before: not one of the pass's lines


def test_write_passes_keeps_the_lines_of_a_scene_without_shots(monkeypatch):
    p = model.normalize_project(project(desc=""))
    s = p["scenes"][0]
    seen = {}

    async def fake_ask(cfg, system, user, parse=None, **kw):
        seen["user"] = user
        return parse(json.dumps({"summary": "Mara is home.", "detailed_description":
                                 "Rain.\n[Shot 1] A wide shot of @Mara. @Mara (S1) mutters, <d>[English] Almost home.</d>"}),
                     {})
    monkeypatch.setattr(llm, "ask", fake_ask)
    cfg = llm.resolve({"base_url": "http://127.0.0.1:9/v1"}, {"base_url": "", "model": "", "api_key": ""})
    out = asyncio.run(llm.write_passes(cfg, p, s))
    assert "<d>[English] Almost home.</d>" in out["passes"][0]["sections"]["detailed_description"]
    assert llm.FILL_LINES_RULE in seen["user"]


def test_rewrite_keeps_the_shot_lines_of_a_scene_without_shots(monkeypatch):
    p = model.normalize_project(project(desc="Warm light."))
    s = p["scenes"][0]
    seen = {}

    async def fake_ask(cfg, system, user, parse=None, **kw):
        seen["user"] = user
        return parse(json.dumps({"detailed_description": "Warm light.\n[Shot 1] A wide shot of @Mara. @Mara (S1) "
                                                         "mutters, <d>[English] Almost home.</d>"}), {})
    monkeypatch.setattr(llm, "ask", fake_ask)
    cfg = llm.resolve({"base_url": "http://127.0.0.1:9/v1"}, {"base_url": "", "model": "", "api_key": ""})
    out = asyncio.run(llm.rewrite(cfg, p, s, ""))
    assert out["sections"]["detailed_description"].endswith("<d>[English] Almost home.</d>")
    assert "This scene has no shots on the timeline yet" in seen["user"] and llm.FILL_LINES_RULE in seen["user"]
    assert "the [Shot N] lines with their cut times" not in seen["user"]
    # a scene with shots: the rewriter's new [Shot N] lines are not taken, as before
    s["shots"] = [{"id": "h_1", "t": 0.0, "camera": "", "text": "rain", "framing": "", "camera_amp": "",
                   "camera_speed": ""}]
    out = asyncio.run(llm.rewrite(cfg, p, s, ""))
    assert out["sections"]["detailed_description"] == "Warm light."
    assert "the [Shot N] lines with their cut times" in seen["user"]


def test_tidy_rewrite_new_shots():
    before = {k: "" for k in prompt.REF2VA_SECTIONS}
    prop = {"detailed_description": "Style.\n[Shot 1] A wide shot. @Mara (S1) says, <d>[English] Hi.</d>"}
    assert prompt.tidy_rewrite(prop, before, {"shots": True})["detailed_description"] == "Style."
    assert prompt.tidy_rewrite(prop, before, {"shots": True}, new_shots=True)["detailed_description"] == \
        prop["detailed_description"]


# ---- the Write prompts brief ---------------------------------------------------------------------------------------

def test_brief_is_kept_and_sent_to_the_llm(monkeypatch):
    p = model.normalize_project(project(desc="", summary="x"))
    s = p["scenes"][0]
    assert s["prompt"]["brief"] == "" and model.default_prompt()["brief"] == ""
    s["prompt"]["brief"] = 42  # a number becomes text, junk becomes empty (as every text field)
    assert model.normalize_project(copy.deepcopy(p))["scenes"][0]["prompt"]["brief"] == "42"
    s["prompt"]["brief"] = {"x": 1}
    assert model.normalize_project(copy.deepcopy(p))["scenes"][0]["prompt"]["brief"] == ""
    s["prompt"]["brief"] = "  Mara comes home and says she missed the sea.  "
    plan, builds = llm.scene_builds(p, s)
    body = llm.pass_request(p, s, plan, builds, 1)
    assert llm.BRIEF_HEAD + "Mara comes home and says she missed the sea." in body
    assert "when the whole-scene note, the author's brief or the instruction has someone speak" in body
    s["prompt"]["brief"] = ""
    assert llm.BRIEF_HEAD not in llm.pass_request(p, s, plan, builds, 1)
    # the rewriter gets it too
    s["prompt"]["brief"] = "Keep it quiet."
    seen = {}

    async def fake_ask(cfg, system, user, parse=None, **kw):
        seen["user"] = user
        return parse(json.dumps({"summary": "s"}), {})
    monkeypatch.setattr(llm, "ask", fake_ask)
    cfg = llm.resolve({"base_url": "http://127.0.0.1:9/v1"}, {"base_url": "", "model": "", "api_key": ""})
    asyncio.run(llm.rewrite(cfg, p, s, ""))
    assert llm.BRIEF_HEAD + "Keep it quiet." in seen["user"]


BRIEF_RUNNER = r"""
import { pathToFileURL } from "node:url";
const dir = process.argv[process.argv.length - 1];
const m = await import(pathToFileURL(dir + "/model.js").href);
const ps = await import(pathToFileURL(dir + "/passes.js").href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const req = JSON.parse(input);
const out = [];
for (const c of req.cases) {
  const p = m.normalizeProject(c.project);
  const sc = p.scenes[0];
  const rep = {};
  const n = ps.applyWritten(sc, p, { passes: [{ index: 1, sections: c.sections }] }, rep);
  out.push({ n, brief: sc.prompt.brief, summary: sc.prompt.sections.summary, kept: !!rep.brief });
}
process.stdout.write(JSON.stringify(out));
"""


@needs_node
def test_write_prompts_keeps_the_written_summary_as_the_brief(tmp_path):
    # passes.js imports api.js, which needs a browser; the runner stubs it with a module of the same name
    web = tmp_path / "rw"
    shutil.copytree(WEB, web)
    (web / "api.js").write_text("export const rw = {};\n")
    (web / "llmjob.js").write_text("export const newJob = () => 'j';\n")

    def run(cases):
        r = subprocess.run([NODE, "--input-type=module", "-e", BRIEF_RUNNER, str(web)], input=json.dumps({"cases": cases}),
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)

    def proj(summary, brief=""):
        p = project(desc="Warm light.")
        p["scenes"][0]["prompt"]["sections"]["summary"] = summary
        p["scenes"][0]["prompt"]["brief"] = brief
        return p
    new = {"summary": "Mara reaches the harbor at night.", "detailed_description": "Warm light."}
    a, b, c, d = run([{"project": proj("[reference generation] She comes home."), "sections": new},
                      {"project": proj("She comes home.", "My own brief."), "sections": new},
                      {"project": proj(""), "sections": new},
                      {"project": proj("She comes home."), "sections": {"summary": "", "detailed_description": "x"}}])
    assert a == {"n": 1, "brief": "She comes home.", "summary": "Mara reaches the harbor at night.", "kept": True}
    assert b["brief"] == "My own brief." and not b["kept"]  # a brief is never overwritten
    assert c["brief"] == "" and not c["kept"]
    assert d["brief"] == "" and d["summary"] == "She comes home." and not d["kept"]  # the summary did not change


# Sencer: "No dialogues are created for this LLM return, but there are clearly dialogues in the result. I have 2
# passes, but it doesn't work on single pass either." A scene with a shot and no spoken lines, the note asking for an
# oath recited and repeated: the lines the LLM writes go on the timeline (one pass: writeShots; several:
# takePassShots), with their speakers and times, and H3 gets each line once.
OATH_1 = ("Live-action, daylight.\n[Shot 1] A medium-wide shot frames @Nesrin before the school. Behind her, the "
          "@{Crowd of students} stands in loose ranks. The camera arcs around @Nesrin with small amplitude at slow "
          "speed. She draws a breath and, in a very strong voice, yells the first line of the oath, <d>[Turkish] "
          "Türk'üm, doğruyum, çalışkanım.</d> At 00:04.200, the @{Crowd of students} answer as one, repeating the line "
          "in the same resolute tone, <d>[Turkish] Türk'üm, doğruyum, çalışkanım.</d> @Nesrin continues without losing "
          "volume, <d>[Turkish] Ülküm yükselmek, ileri gitmektir.</d> The crowd takes it up at 00:13.800, "
          "<d>[Turkish] Ülküm yükselmek, ileri gitmektir.</d>")
# pass 2 (scene 13.458 to 26.000) in its own time, as the backend stores it (scene_times_to_pass); it repeats the
# last line of pass 1 at the start of its overlap
OATH_2 = ("The target video continues seamlessly from the final frames of @tail.\n[Shot 1] The shot resumes from the "
          "middle of the ongoing arc. @Nesrin holds her line open. At 00:00.300, the @{Crowd of students} (S2) "
          "takes it up, "
          "<d>[Turkish] Ülküm yükselmek, ileri gitmektir.</d> At 00:05.742, @Nesrin (S1) continues, her voice "
          "climbing in volume, <d>[Turkish] Varlığım Türk varlığına armağan olsun.</d> At 00:08.142, the "
          "@{Crowd of students} (S2) answer together, <d>[Turkish] Varlığım Türk varlığına armağan olsun.</d>")


def oath_project(duration):
    p = model.default_project("Oath")
    p["cast"] = [{"id": "c_nes", "name": "Nesrin", "kind": "character", "language": "Turkish"},
                 {"id": "c_crowd", "name": "Crowd of students", "kind": "character"}]
    s = p["scenes"][0]
    s.update({"id": "s_1", "duration": duration, "dialogue": [], "cast": [{"id": "c_nes", "outfit": ""}],
              "shots": [{"id": "h_1", "t": 0.0, "camera": "", "text": "Nesrin recites the oath, the crowd repeats it."}]})
    return p


@needs_node
def test_lines_written_for_a_scene_with_shots_go_on_the_timeline():
    one = oath_project(15.0)
    one["scenes"][0]["prompt"]["sections"]["detailed_description"] = OATH_1
    two = oath_project(26.0)
    pl = plan_scene(model.normalize_project(copy.deepcopy(two)), two["scenes"][0], 0)
    assert [round(x["start"], 3) for x in pl["passes"]] == [0.0, 13.458]
    items = [{"index": 1, "sections": {"detailed_description": OATH_1}},
             {"index": 2, "sections": {"detailed_description": OATH_2}}]
    a, b = run([{"op": "write", "project": one, "scene": "s_1"},
                {"op": "passes", "project": two, "scene": "s_1", "items": items}])
    said = [(d["speaker"], round(d["t"], 3), d["delivery"], d["text"][:12]) for d in a["scene"]["dialogue"]]
    assert a["n"]["lines"] == 4 and said == [
        ("c_nes", 0.5, "yells", "Türk'üm, doğ"),  # "She …": the character named before the sentence
        ("c_crowd", 4.208, "answer as one, repeating the line in the same resolute tone", "Türk'üm, doğ"),
        ("c_nes", 5.708, "continues without losing volume", "Ülküm yüksel"),  # after the line before
        ("c_crowd", 13.792, "takes it up", "Ülküm yüksel")]  # "the crowd … at 00:13.800"
    assert {c["id"] for c in a["scene"]["cast"]} == {"c_nes", "c_crowd"}
    assert "<d>" not in a["scene"]["shots"][0]["text"] and "yells the first line of the oath" in a["scene"]["shots"][0]["text"]
    # two passes: pass 2's lines at pass time + 13.458; its repeat of pass 1's last line (same speaker, close) once
    said = [(d["speaker"], round(d["t"], 3), d["text"][:12]) for d in b["scene"]["dialogue"]]
    assert b["n"]["lines"] == 6 and said == [
        ("c_nes", 0.5, "Türk'üm, doğ"), ("c_crowd", 4.208, "Türk'üm, doğ"), ("c_nes", 5.708, "Ülküm yüksel"),
        ("c_crowd", 13.792, "Ülküm yüksel"), ("c_nes", 19.208, "Varlığım Tür"), ("c_crowd", 21.583, "Varlığım Tür")]
    assert b["scene"]["dialogue"][4]["delivery"] == "continues, her voice climbing in volume"
    # what H3 gets: each line once in its pass; pass 2's own text keeps the line it wrote in its overlap (the part
    # that repeats the end of pass 1), and adds none of the timeline's
    p = model.normalize_project({**two, "scenes": [b["scene"]]})
    p["scenes"][0]["prompt"]["passes"] = [{"start": 0.0, "end": 15.083, "sections": {}},
                                         {"start": 13.458, "end": 26.0, "sections": b["items"][1]["sections"]}]
    s = p["scenes"][0]
    plan = plan_scene(p, s, 0)
    texts = [prompt.build_pass(p, s, 0, plan, x)["prompt"] for x in plan["passes"]]
    assert [t.count("<d>") for t in texts] == [4, 3]
    assert texts[1].count("Varlığım Türk varlığına armağan olsun.") == 2  # Nesrin's line and the crowd's repeat


def test_later_passes_written_in_scene_time_get_their_own_times():
    text = ("[Shot 1] She waits. At 00:15.083, @Nesrin (S1) says, <d>[Turkish] Saat 00:20.000.</d> The crowd takes it "
            "up at 00:17.400, <d>[Turkish] x</d> At 00:23.400, she bows.")
    out, moved = llm.scene_times_to_pass(text, 13.458, 26.0)
    assert out == ("[Shot 1] She waits. At 00:01.625, @Nesrin (S1) says, <d>[Turkish] Saat 00:20.000.</d> The crowd "
                   "takes it up at 00:03.942, <d>[Turkish] x</d> At 00:09.942, she bows.")  # spoken words untouched
    assert moved == ["00:15.083 -> 00:01.625", "00:17.400 -> 00:03.942", "00:23.400 -> 00:09.942"]
    assert llm.scene_times_to_pass("At 00:01.625, she says, <d>x</d>", 13.458, 26.0) == ("At 00:01.625, she says, <d>x</d>", [])
    assert llm.scene_times_to_pass("At 00:30.000, she bows.", 13.458, 26.0)[1] == []  # past the pass: not scene time
    assert llm.scene_times_to_pass("At 00:12.000, she bows.", 0.0, 15.0)[1] == []  # pass 1: scene time is pass time


def test_later_passes_are_told_the_lines_written_before():
    p = model.normalize_project(oath_project(26.0))
    s = p["scenes"][0]
    plan, builds = llm.scene_builds(p, s)
    assert llm.free_lines(s, plan)
    body = llm.pass_request(p, s, plan, builds, 2, written={1: {"summary": "The oath begins.",
                                                                "detailed_description": OATH_1}})
    assert ("The spoken lines written so far, in order (already spoken; go on from the last one and never write them "
            "again):\npass 1: She draws a breath and, in a very strong voice, yells the first line of the oath, "
            "<d>[Turkish] Türk'üm, doğruyum, çalışkanım.</d>\npass 1: the @{Crowd of students} answer as one") in body
    assert "pass 1: The crowd takes it up at 00:13.800, <d>[Turkish] Ülküm yükselmek, ileri gitmektir.</d>" in body
    s["dialogue"] = [{"id": "d_1", "speaker": "c_nes", "t": 1.0, "language": "Turkish", "text": "Türk'üm."}]
    assert "written so far" not in llm.pass_request(p, s, plan, builds, 2, written={1: {"detailed_description": OATH_1}})


def test_a_line_repeated_by_someone_else_is_kept():
    # call and response: the crowd's repeat is a line of its own; Nesrin saying it again is a second copy
    x = {"shots": [], "dialogue": []}
    desc = ("[Shot 1] She yells, <d>[Turkish] Türk'üm, doğruyum.</d> At 00:04.200, the @{Crowd of students} answer as "
            "one, <d>[Turkish] Türk'üm, doğruyum.</d> @Nesrin (S1) nods, <d>[Turkish] Ülküm yükselmek.</d> The "
            "@{Crowd of students} (S2) repeat it, <d>[Turkish] Ülküm yükselmek.</d> @Nesrin (S1) says again, "
            "<d>[Turkish] Ülküm yükselmek.</d>")
    kept, warns = llm.tidy_pass({"detailed_description": desc}, x, {}, {"shots": True}, 1,
                                known={"nesrin", "crowd of students"}, free_lines=True)
    d = kept["detailed_description"]
    assert d.count("Türk'üm, doğruyum.") == 2 and d.count("Ülküm yükselmek.") == 2 and "says again" not in d
    assert [w for w in warns if "second copy" in w] == ['removed a second copy of: "Ülküm yükselmek."']
