"""Face checks with a broken albumentations install (added 2026-11-03 v0.4.1)."""

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
