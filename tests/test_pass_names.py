"""scene.pass_names (Sencer: "we should be able to rename passes. pass number is always in
front."). The editor shows "Pass 2 · Storm"; nothing sent to H3 or the LLM, and no cache key, reads a name."""

import copy
import json
import os
import shutil
import subprocess

import pytest

from reelwright import cache
from reelwright.model import default_scene, normalize_project, pass_names, resolve_settings
from reelwright.planner import plan_scene
from reelwright.prompt import build_pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web", "rw")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")

RAW = {"1": "  Arrival \n at\tdusk ", "2": "", "03": "x", "0": "zero", "1000": "big", "a": "letter", "4": 5, "5": None,
       "6": "é" * 70, "7": "🌊" * 61}


def test_names_are_normalised():
    out = pass_names(RAW)
    assert out == {"1": "Arrival at dusk", "4": "5", "6": "é" * 60, "7": "🌊" * 60}
    assert pass_names("junk") == {} and pass_names(None) == {}
    assert default_scene()["pass_names"] == {}


def test_a_name_changes_no_prompt_or_key(harbor):
    p = normalize_project(copy.deepcopy(harbor))
    q = copy.deepcopy(p)
    q["scenes"][1]["pass_names"] = {"1": "Storm", "2": "Harbour"}
    q = normalize_project(q)
    assert q["scenes"][1]["pass_names"] == {"1": "Storm", "2": "Harbour"}
    for proj in (p, q):
        s = proj["scenes"][1]
        plan = plan_scene(proj, s, 1)
        proj["_b"] = [build_pass(proj, s, 1, plan, x)["prompt"] for x in plan["passes"]]
    assert p["_b"] == q["_b"]
    assert cache.settings_fingerprint(resolve_settings(p, p["scenes"][1], 1), {}) == \
        cache.settings_fingerprint(resolve_settings(q, q["scenes"][1], 1), {})


RUNNER = r"""
import { pathToFileURL } from "node:url";
const dir = process.argv[process.argv.length - 1];
const m = await import(pathToFileURL(dir + "/model.js").href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const req = JSON.parse(input);
const s = { pass_names: m.passNames(req.raw) };
process.stdout.write(JSON.stringify({ names: s.pass_names, labels: [1, 2, 6].map(k => m.passLabel(s, k)),
  counted: [1, 2].map(k => m.passLabel(s, k, 3)), scene: m.defaultScene(null).pass_names }));
"""


@needs_node
def test_the_editor_agrees():
    r = subprocess.run([NODE, "--input-type=module", "-e", RUNNER, WEB], input=json.dumps({"raw": RAW}),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["names"] == pass_names(RAW)
    assert out["labels"] == ["Pass 1 · Arrival at dusk", "Pass 2", "Pass 6 · " + "é" * 60]
    assert out["counted"] == ["Pass 1 of 3 · Arrival at dusk", "Pass 2 of 3"]  # the number first, then the count
    assert out["scene"] == {}
