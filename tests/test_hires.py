"""Global -> Hires, the H3 latent upscaler and an optional refine at the big size.

Sencer: "implement it, but the whole project should be upscaled to same resolution. maybe only override the other
parameters in scenes?" Chosen: the upscaler with an optional refine (steps, denoise; 0 steps = off), a scale factor of
Global -> Output, and drafts upscaled only when Global -> Draft says so.
"""

import copy
import json
import os
import shutil
import subprocess

import pytest

from reelwright import cache
from reelwright.model import (
    hires_size,
    normalize_global,
    normalize_project,
    project_output_size,
    resolve_settings,
    scene_hires,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web", "rw")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node is not installed")


def _on(p, **kw):
    p = copy.deepcopy(p)
    p["global"]["models"]["latent_upscaler"] = "h3_up.safetensors"
    p["global"]["hires"] = dict({"enabled": True, "scale": 2.0, "refine_steps": 0, "refine_denoise": 0.35}, **kw)
    return normalize_project(p)


def test_defaults_and_normalising():
    g = normalize_global({})
    assert g["hires"] == {"enabled": False, "scale": 2.0, "refine_steps": 0, "refine_denoise": 0.35}
    assert g["draft"]["hires"] is False
    g = normalize_global({"hires": {"enabled": 1, "scale": 9, "refine_steps": -3.7, "refine_denoise": 4}})
    assert g["hires"] == {"enabled": True, "scale": 4.0, "refine_steps": 0, "refine_denoise": 1.0}
    g = normalize_global({"hires": {"scale": 0.5, "refine_steps": 250.9, "refine_denoise": 0}})
    assert (g["hires"]["scale"], g["hires"]["refine_steps"], g["hires"]["refine_denoise"]) == (1.0, 100, 0.01)


def test_scene_overrides_are_normalised(harbor):
    p = copy.deepcopy(harbor)
    p["scenes"][0]["overrides"] = {"hires": "off", "refine_steps": "6.8", "refine_denoise": 3}
    p["scenes"][1]["overrides"] = {"hires": "on", "refine_steps": "", "refine_denoise": "x"}
    p = normalize_project(p)
    assert p["scenes"][0]["overrides"] == {"hires": "off", "refine_steps": 6, "refine_denoise": 1.0}
    assert p["scenes"][1]["overrides"] == {}


def test_the_project_size(harbor):
    p = normalize_project(copy.deepcopy(harbor))
    assert project_output_size(p) == (1344, 768)                       # off: Global -> Output
    assert project_output_size(_on(harbor)) == (2688, 1536)
    assert project_output_size(_on(harbor, scale=1.5)) == (2016, 1152)
    assert project_output_size(_on(harbor, scale=1.25)) == (1696, 960)  # 1680 is 52.5 cells: half up
    assert project_output_size(_on(harbor, scale=1.0)) == (1344, 768)
    assert hires_size(dict(_on(harbor)["global"], hires={"enabled": False, "scale": 2.0})) == (1344, 768)


def test_every_scene_ends_at_the_project_size(harbor):
    p = _on(harbor, refine_steps=6, refine_denoise=0.4)
    p["scenes"][1]["overrides"] = {"refine_steps": 0}
    p["scenes"][2]["overrides"] = {"width": 1024, "height": 768}       # its own (4:3) size: fitted, not stretched
    st = [resolve_settings(p, s, i) for i, s in enumerate(p["scenes"])]
    assert st[0]["hires"] == {"model": "h3_up.safetensors", "width": 2688, "height": 1536, "refine_steps": 6,
                              "refine_denoise": 0.4}
    assert st[1]["hires"] == {"model": "h3_up.safetensors", "width": 2688, "height": 1536}
    assert st[2]["hires"]["height"] == 1536 and st[2]["hires"]["width"] == 2048 and (st[2]["width"], st[2]["height"]) == (1024, 768)
    # the sampling size stays Global -> Output
    assert (st[0]["width"], st[0]["height"]) == (1344, 768)
    # a scene that turns it off, and drafts unless Global -> Draft says so (never refined)
    p["scenes"][0]["overrides"] = {"hires": "off"}
    assert "hires" not in resolve_settings(p, p["scenes"][0], 0)
    p["scenes"][0]["overrides"] = {"quality": "draft"}
    assert "hires" not in resolve_settings(p, p["scenes"][0], 0)
    p["global"]["draft"]["hires"] = True
    d = resolve_settings(p, p["scenes"][0], 0)
    assert (d["width"], d["height"]) == (672, 384) and d["hires"] == {"model": "h3_up.safetensors", "width": 2688,
                                                                       "height": 1536}


def test_off_keeps_every_cache_key(harbor):
    """Hires off (the default) must leave the settings, and so every pass key, exactly as v0.18.0 made them."""
    p = normalize_project(copy.deepcopy(harbor))
    q = copy.deepcopy(p)
    q["global"]["hires"]["refine_steps"] = 9  # settings of a Hires that is off change nothing
    q["global"]["draft"]["hires"] = True
    for i, s in enumerate(p["scenes"]):
        a, b = resolve_settings(p, s, i), resolve_settings(q, q["scenes"][i], i)
        assert "hires" not in a and a == b
        assert cache.settings_fingerprint(a, {}) == cache.settings_fingerprint(b, {})
    on = _on(harbor)
    assert cache.settings_fingerprint(resolve_settings(on, on["scenes"][0], 0), {}) != \
        cache.settings_fingerprint(resolve_settings(p, p["scenes"][0], 0), {})
    # refine settings count only while the refine runs
    a = _on(harbor, refine_steps=0, refine_denoise=0.2)
    b = _on(harbor, refine_steps=0, refine_denoise=0.9)
    assert resolve_settings(a, a["scenes"][0], 0) == resolve_settings(b, b["scenes"][0], 0)


def test_lint_without_an_upscaler(harbor, roots):
    from reelwright.planner import plan_scene
    from reelwright.prompt import build_pass
    from reelwright.validate import lint_project
    p = _on(harbor)
    p["global"]["models"]["latent_upscaler"] = ""
    plans = {s["id"]: plan_scene(p, s, i) for i, s in enumerate(p["scenes"])}
    builds = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
              for i, s in enumerate(p["scenes"])}
    msgs = [x["message"] for x in lint_project(p, plans, builds, lambda a: True) if x["level"] == "error"]
    assert any("no latent upscaler is chosen" in m for m in msgs)


RUNNER = r"""
import { pathToFileURL } from "node:url";
const dir = process.argv[process.argv.length - 1];
const m = await import(pathToFileURL(dir + "/model.js").href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const req = JSON.parse(input);
const out = req.projects.map(raw => {
  const p = m.normalizeProject(raw);
  return { global: p.global, overrides: p.scenes.map(s => s.overrides), size: m.projectOutputSize(p),
           hires: p.scenes.map(s => m.sceneHires(p, s)), sample: p.scenes.map(s => m.sceneSampleSize(p, s)) };
});
process.stdout.write(JSON.stringify(out));
"""


@needs_node
def test_the_editor_agrees(harbor):
    cases = []
    for kw in ({"scale": 2.0}, {"scale": 1.25, "refine_steps": 4, "refine_denoise": 0.25}, {"scale": 1.75}):
        p = _on(harbor, **kw)
        p["scenes"][1]["overrides"] = {"quality": "draft", "refine_steps": 3}
        p["scenes"][2]["overrides"] = {"width": 1024, "height": 768, "refine_denoise": 0.6}
        cases.append(p)
    q = _on(harbor)
    q["global"]["draft"].update(hires=True, scale=0.55)
    q["scenes"][0]["overrides"] = {"quality": "draft"}
    q["scenes"][1]["overrides"] = {"hires": "off"}
    cases.append(normalize_project(q))
    cases.append(normalize_project(copy.deepcopy(harbor)))
    r = subprocess.run([NODE, "--input-type=module", "-e", RUNNER, WEB], input=json.dumps({"projects": cases}),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    for p, o in zip(cases, out):
        assert o["global"]["hires"] == p["global"]["hires"] and o["global"]["draft"] == p["global"]["draft"]
        assert o["overrides"] == [s["overrides"] for s in p["scenes"]]
        assert tuple(o["size"]) == project_output_size(p)
        for i, s in enumerate(p["scenes"]):
            st = resolve_settings(p, s, i)
            assert o["hires"][i] == st.get("hires"), (i, o["hires"][i], st.get("hires"))
            assert tuple(o["sample"][i]) == (st["width"], st["height"])
            assert o["hires"][i] == scene_hires(p, s, st["width"], st["height"], st["quality"])


def test_estimates_tell_hires_renders_apart():
    """A Hires take samples at the same size as a plain one but takes longer."""
    from reelwright.analysis import _rate_samples, seconds_per_frame
    up = {"model": "h3_up.safetensors", "width": 2688, "height": 1536}
    base = {"sampled_frames": 100, "width": 1344, "height": 768, "steps": 20, "quality": "final"}
    rows = _rate_samples([dict(base, render_seconds=100, created=1),
                          dict(base, render_seconds=300, created=2, hires=dict(up)),
                          dict(base, render_seconds=500, created=3, hires=dict(up, refine_steps=6, refine_denoise=0.4))])
    plain = {"width": 1344, "height": 768, "steps": 20, "quality": "final"}
    assert seconds_per_frame(rows, plain) == pytest.approx(1.0)
    assert seconds_per_frame(rows, dict(plain, hires=up)) == pytest.approx(3.0)
    assert seconds_per_frame(rows, dict(plain, hires=dict(up, refine_steps=6, refine_denoise=0.4))) == pytest.approx(5.0)
    # no take with this Hires yet: estimated from the others rather than unknown
    assert seconds_per_frame(rows, dict(plain, hires=dict(up, width=2016, height=1152))) is not None
    assert seconds_per_frame(rows[1:], plain) is not None
