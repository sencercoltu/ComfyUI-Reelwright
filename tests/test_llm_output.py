"""added 2026-11-09 v0.15.0: the editor keeps what an LLM request receives, for the output popup (Sencer: "When
waiting for response, we receive thinking, but cannot see what it thinks. Add the thinking progress and received
content as output so we can see what's going on. It should only be shown by a toggle button inside a popup.")

web/rw/llmjob.js feedStream joins the progress events' think_add / text_add (llm.chat) per job and per request (pass,
part, try); splitThink shows an inline <think> block as reasoning. Run under node.
"""

import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web", "rw")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node is not installed")

RUNNER = r"""
import { pathToFileURL } from "node:url";
const dir = process.argv[process.argv.length - 1];
const m = await import(pathToFileURL(dir + "/llmjob.js").href);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const req = JSON.parse(input);
for (const d of req.events) m.feedStream(d);
const st = m.streamOf(req.job);
process.stdout.write(JSON.stringify({
  segs: st.segs.map(s => ({ label: s.label, think: s.think, text: s.text, notes: s.notes, shown: m.splitThink(s) })),
  split: req.split.map(x => m.splitThink(x)),
}));
"""


def run(events, job="j", split=()):
    r = subprocess.run([NODE, "--input-type=module", "-e", RUNNER, WEB],
                       input=json.dumps({"events": events, "job": job, "split": list(split)}),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_stream_joins_the_deltas_per_request():
    ev = [
        {"job": "j", "phase": "waiting", "pass": 1, "passes": 2, "attempt": 1},
        {"job": "j", "phase": "thinking", "pass": 1, "passes": 2, "attempt": 1, "think_at": 0, "think_add": "Let me "},
        {"job": "j", "phase": "thinking", "pass": 1, "passes": 2, "attempt": 1, "think_at": 7, "think_add": "think."},
        {"job": "j", "phase": "writing", "pass": 1, "passes": 2, "attempt": 1, "text_at": 0, "text_add": "{\"summary\""},
        {"job": "j", "phase": "retry", "attempt": 2, "attempts": 3, "note": "cut off"},
        {"job": "j", "phase": "writing", "pass": 1, "passes": 2, "attempt": 2, "attempts": 3, "text_at": 0, "text_add": "ok"},
        {"job": "j", "phase": "writing", "pass": 2, "passes": 2, "attempt": 1, "text_at": 0, "text_add": "a"},
        {"job": "j", "phase": "writing", "pass": 2, "passes": 2, "attempt": 1, "text_at": 5, "text_add": "b"},  # 1..5 lost
        {"job": "other", "phase": "writing", "text_at": 0, "text_add": "not this job"},
    ]
    out = run(ev)["segs"]
    assert [s["label"] for s in out] == ["Pass 1 of 2", "Pass 1 of 2 · try 2 of 3", "Pass 2 of 2"]
    assert out[0]["think"] == "Let me think." and out[0]["text"] == "{\"summary\"" and out[0]["notes"] == ["retry 2 of 3: cut off"]
    assert out[1]["text"] == "ok"
    assert out[2]["text"].startswith("a\n[") and out[2]["text"].endswith("]\nb")  # a gap is marked


def test_inline_think_blocks_show_as_reasoning():
    got = run([{"job": "j", "phase": "done"}], split=[
        {"think": "", "text": "<think>hmm</think>\n{\"a\": 1}"},
        {"think": "", "text": "  <think>still thinking"},
        {"think": "r1 ", "text": "r2</think>answer"},
        {"think": "", "text": "plain"},
    ])["split"]
    assert got == [{"think": "hmm", "text": "{\"a\": 1}"}, {"think": "still thinking", "text": ""},
                   {"think": "r1 r2", "text": "answer"}, {"think": "", "text": "plain"}]
