"""Saved Global settings ("profiles"), shared by every Reelwright node on this ComfyUI.

Stored in ComfyUI's user folder next to llm.json, so API keys never go into a profile (they are not part of Global
anyway).
"""

import json
import os
import time

from . import soundtrack
from .model import new_id
from .storage import read_json, write_json

MAX_BYTES = 256 * 1024
MAX_PROFILES = 100


def profiles_path(user_root):
    return os.path.join(user_root, "reelwright", "profiles.json")


def migrate_global(glob):
    """A profile saved before v0.5 still has the old merge score (one looping music bed).
    The score belongs to a project's soundtrack now, so applying such a profile brought it back silently: it is
    dropped here the way soundtrack.migrate_score moves it out of a project (the scenes' sound stays on top).
    Returns True when the profile changed."""
    if not isinstance(glob, dict):
        return False
    merge = glob.get("merge")
    if not isinstance(merge, dict) or not isinstance(merge.get("score"), dict) or not merge["score"].get("asset"):
        return False
    return soundtrack.migrate_score({"global": glob, "soundtrack": []})


def load(user_root):
    data = read_json(profiles_path(user_root), None) or {}
    if not isinstance(data, dict):
        data = {}
    profiles = [x for x in data.get("profiles") or [] if isinstance(x, dict) and x.get("id") and isinstance(x.get("global"), dict)]
    for x in profiles:
        migrate_global(x["global"])
    default = data.get("default") or ""
    if default not in {x["id"] for x in profiles}:
        default = ""
    return {"profiles": profiles, "default": default}


def _write(user_root, data):
    write_json(profiles_path(user_root), data)
    return data


def save(user_root, name, glob, pid=None, make_default=None):
    """Create a profile, or replace the settings (and name) of an existing one."""
    name = str(name or "").strip()[:80]
    if not name:
        raise ValueError("Give the profile a name")
    if not isinstance(glob, dict):
        raise ValueError("A profile needs the Global settings")
    if len(json.dumps(glob)) > MAX_BYTES:
        raise ValueError("These settings are too large for a profile")
    migrate_global(glob)
    data = load(user_root)
    now = int(time.time())
    hit = next((x for x in data["profiles"] if x["id"] == pid), None) if pid else None
    if pid and hit is None:
        raise ValueError("unknown profile (it may have been deleted in another tab); use Save as new")
    if hit is None:
        if len(data["profiles"]) >= MAX_PROFILES:
            raise ValueError("Too many profiles; delete one first")
        hit = {"id": new_id("g"), "created": now}
        data["profiles"].append(hit)
    hit["name"], hit["updated"], hit["global"] = name, now, glob
    if make_default is True:
        data["default"] = hit["id"]
    elif make_default is False and data["default"] == hit["id"]:
        data["default"] = ""
    _write(user_root, data)
    return {"profile": hit, **load(user_root)}


def delete(user_root, pid):
    data = load(user_root)
    before = len(data["profiles"])
    data["profiles"] = [x for x in data["profiles"] if x["id"] != pid]
    if len(data["profiles"]) == before:
        raise ValueError("unknown profile")
    if data["default"] == pid:
        data["default"] = ""
    _write(user_root, data)
    return load(user_root)


def set_default(user_root, pid):
    data = load(user_root)
    if pid and pid not in {x["id"] for x in data["profiles"]}:
        raise ValueError("unknown profile")
    data["default"] = pid or ""
    _write(user_root, data)
    return load(user_root)
