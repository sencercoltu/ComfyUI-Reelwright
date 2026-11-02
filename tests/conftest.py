import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from reelwright.model import default_project, normalize_project  # noqa: E402
from reelwright.storage import ProjectStore, Roots  # noqa: E402


@pytest.fixture
def roots(tmp_path):
    for d in ("output", "input", "user"):
        (tmp_path / d).mkdir()
    return Roots(str(tmp_path / "output"), str(tmp_path / "input"), str(tmp_path / "user"))


@pytest.fixture
def harbor(roots):
    """A small project: an 8 s scene, a 32 s continuing scene with four shots, a 2.5 s insert."""
    p = default_project("Harbor Lights")
    p["scenes"][0].update({"id": "s_one", "title": "Harbor at dusk", "duration": 8.0,
                           "shots": [{"t": 0, "camera": "Wide", "text": "boats rock in the harbor"}]})
    p["assets"] = [
        {"id": "a_front", "kind": "image", "name": "Mara front", "file": "reelwright/harbor_lights/front.png"},
        {"id": "a_side", "kind": "image", "name": "Mara side", "file": "reelwright/harbor_lights/side.png"},
        {"id": "a_voice", "kind": "audio", "name": "voice", "file": "reelwright/harbor_lights/voice.wav", "duration": 4.2},
        {"id": "a_letter", "kind": "image", "name": "letter", "file": "reelwright/harbor_lights/letter.png"},
        {"id": "a_dolly", "kind": "video", "name": "dolly", "file": "reelwright/harbor_lights/dolly.mp4", "duration": 4.2},
    ]
    p["cast"] = [{"id": "c_mara", "name": "Mara", "speaker": "S1", "description": "woman, early 30s, auburn hair",
                  "anchors": ["a_front", "a_side"], "voice": "a_voice"}]
    p["scenes"].append({
        "id": "s_long", "title": "The long walk home", "duration": 32.0,
        "start": {"mode": "tail", "overlap_frames": 39},
        "cast": [{"id": "c_mara"}],
        "refs": [{"id": "r_letter", "asset": "a_letter", "role": "keyframe", "time": 25.0},
                 {"id": "r_dolly", "asset": "a_dolly", "role": "reference", "soundtrack": True}],
        "shots": [{"t": 0, "camera": "Wide", "text": "Mara leaves the pier"},
                  {"t": 6, "camera": "Tracking", "text": "along the seawall"},
                  {"t": 14.375, "camera": "Medium", "text": "the rain starts"},
                  {"t": 22, "camera": "Wide", "text": "she reaches the door"}],
        "dialogue": [{"id": "d_1", "speaker": "c_mara", "t": 16.0, "text": "Almost home.", "delivery": "mutters"}],
        "prompt": {"sections": {"summary": "@Mara walks home as a storm builds, holding @P3, camera like @V1."}},
    })
    p["scenes"].append({"id": "s_short", "title": "Hand on the door", "duration": 2.5,
                        "start": {"mode": "fresh"}, "trim": {"keep": "custom", "in": 1.208}})
    p = normalize_project(p)
    d = os.path.join(roots.input, "reelwright", "harbor_lights")
    os.makedirs(d)
    for a in p["assets"]:
        with open(os.path.join(roots.input, a["file"]), "wb") as f:
            f.write(a["id"].encode())
    return p


@pytest.fixture
def store(roots, harbor):
    return ProjectStore(roots, harbor["slug"])
