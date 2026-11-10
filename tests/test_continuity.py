"""Face checks with a broken albumentations install."""

import sys
import textwrap

import pytest

from reelwright import continuity


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


@pytest.fixture
def fake_insightface(tmp_path, monkeypatch):
    """insightface 0.7.x layout: app/__init__ imports mask_renderer, which imports albumentations, whose albucore is
    the wrong version."""
    write(tmp_path / "insightface/__init__.py", "from . import app\n")
    write(tmp_path / "insightface/app/__init__.py", "from .face_analysis import *\nfrom .mask_renderer import *\n")
    write(tmp_path / "insightface/app/face_analysis.py", "__all__ = ['FaceAnalysis']\nclass FaceAnalysis:\n    pass\n")
    write(tmp_path / "insightface/app/mask_renderer.py", """
        import albumentations as A
        from albumentations.core.transforms_interface import ImageOnlyTransform
        __all__ = ['MaskAugmentation']
        class MaskAugmentation(ImageOnlyTransform):
            pass
    """)
    write(tmp_path / "albumentations/__init__.py", "from albucore import median_blur\n")
    write(tmp_path / "albucore/__init__.py", "reduce_sum = None\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    for k in list(sys.modules):
        if k.split(".")[0] in ("insightface", "albumentations", "albucore"):
            monkeypatch.delitem(sys.modules, k)
    yield
    for k in list(sys.modules):
        if k.split(".")[0] in ("insightface", "albumentations", "albucore"):
            sys.modules.pop(k, None)


def test_face_analysis_loads_despite_broken_albumentations(fake_insightface):
    with pytest.raises(ImportError, match="median_blur"):
        import albumentations  # noqa: F401  (really broken)
    cls = continuity._face_analysis_class()
    assert cls.__name__ == "FaceAnalysis" and cls.__module__ == "insightface.app.face_analysis"
    assert "albumentations" not in sys.modules                       # the stand-in is gone again
    with pytest.raises(ImportError, match="median_blur"):
        import albumentations  # noqa: F401,F811  (still the real, broken one for everyone else)


def test_other_import_errors_still_raise(tmp_path, monkeypatch):
    write(tmp_path / "insightface/__init__.py", "import missing_thing_xyz\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    for k in list(sys.modules):
        if k.split(".")[0] == "insightface":
            monkeypatch.delitem(sys.modules, k)
    with pytest.raises(ImportError, match="missing_thing_xyz"):
        continuity._face_analysis_class()
    sys.modules.pop("insightface", None)


def test_a_character_missing_from_a_frame_is_not_drift():
    import numpy as np
    a = np.array([[1.0, 0.0, 0.0]])
    b = np.array([[0.0, 1.0, 0.0]])
    anchors = {"c_a": a, "c_b": b}
    only_b = np.array([[0.1, 0.95, 0.0]])
    assert continuity.assign_faces(only_b, anchors) == {"c_b": 0.95}  # A is not in this frame: no value for A
    both = np.array([[0.9, 0.1, 0.0], [0.05, 0.8, 0.0], [0.3, 0.3, 0.0]])
    assert continuity.assign_faces(both, anchors) == {"c_a": 0.9, "c_b": 0.8}
    one = {"c_a": a}
    assert continuity.assign_faces(np.array([[0.2, 0.0, 0.0], [0.7, 0.0, 0.0]]), one) == {"c_a": 0.7}


def test_face_score_is_the_lowest():
    assert continuity.score({"c_a": 0.9, "c_b": 0.62}) == 0.62
    assert continuity.score({}) is None and continuity.score(None) is None


def test_failed_model_setup_is_retried(monkeypatch):
    attempts = []

    class Broken:
        def __init__(self, **kw):
            attempts.append(1)

        def prepare(self, **kw):
            raise RuntimeError("buffalo_l download failed")
    monkeypatch.setattr(continuity, "_app", None)
    monkeypatch.setattr(continuity, "_error", None)
    monkeypatch.setattr(continuity, "_face_analysis_class", lambda: Broken)
    with pytest.raises(RuntimeError):
        continuity._analyzer()
    assert continuity._app is None and "download failed" in continuity.error()
    continuity.retry()
    assert continuity.error() is None
    with pytest.raises(RuntimeError):
        continuity._analyzer()
    assert len(attempts) == 2
