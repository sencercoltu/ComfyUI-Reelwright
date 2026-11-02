"""Folders, path containment, take indexes and autosave versions."""

import json
import os
import re
import time

SLUG_RE = re.compile(r"^[a-z0-9_][a-z0-9_-]{0,63}$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
VERSION_RE = re.compile(r"^project_\d{8}_\d{6}\.json$")
MAX_VERSIONS = 50
VERSION_INTERVAL = 120  # seconds between automatic version snapshots


class Roots:
    def __init__(self, output, input, user):
        self.output = os.path.realpath(output)
        self.input = os.path.realpath(input)
        self.user = os.path.realpath(user)


def safe_join(root, *parts):
    root = os.path.realpath(root)
    path = os.path.realpath(os.path.join(root, *[str(x) for x in parts]))
    if path != root and os.path.commonpath([root, path]) != root:
        raise ValueError("path is outside {}".format(root))
    return path


def check_slug(slug):
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise ValueError("invalid project slug: {!r}".format(slug))
    return slug


def check_id(value):
    if not isinstance(value, str) or not ID_RE.match(value):
        raise ValueError("invalid id: {!r}".format(value))
    return value


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


class ProjectStore:
    def __init__(self, roots, slug):
        self.roots = roots
        self.slug = check_slug(slug)
        self.dir = safe_join(roots.output, "reelwright", self.slug)
        self.input_dir = safe_join(roots.input, "reelwright", self.slug)

    # paths
    def scene_dir(self, scene_id):
        return safe_join(self.dir, "scenes", check_id(scene_id))

    def take_dir(self, scene_id, take_id):
        return safe_join(self.scene_dir(scene_id), "takes", check_id(take_id))

    def cuts_dir(self):
        return safe_join(self.dir, "cuts")

    def cast_dir(self, cast_id):
        return safe_join(self.dir, "cast", check_id(cast_id))

    def rel_output(self, path):
        return os.path.relpath(path, self.roots.output).replace(os.sep, "/")

    def output_path(self, rel):
        return safe_join(self.roots.output, rel)

    def input_path(self, rel):
        return safe_join(self.roots.input, rel)

    # takes
    def read_index(self, scene_id):
        idx = read_json(os.path.join(self.scene_dir(scene_id), "index.json"), None)
        if not isinstance(idx, dict):
            idx = {"starred": None, "takes": []}
        idx.setdefault("starred", None)
        idx.setdefault("takes", [])
        return idx

    def write_index(self, scene_id, idx):
        write_json(os.path.join(self.scene_dir(scene_id), "index.json"), idx)

    def new_take_id(self, scene_id):
        idx = self.read_index(scene_id)
        n = 1 + max([int(t["id"][1:]) for t in idx["takes"] if re.match(r"^v\d+$", t["id"])] or [0])
        return "v{}".format(n)

    def add_take(self, scene_id, take, star=True):
        idx = self.read_index(scene_id)
        idx["takes"] = [t for t in idx["takes"] if t["id"] != take["id"]] + [take]
        if star:
            idx["starred"] = take["id"]
        self.write_index(scene_id, idx)
        return idx

    def star(self, scene_id, take_id):
        idx = self.read_index(scene_id)
        if not any(t["id"] == take_id for t in idx["takes"]):
            raise ValueError("unknown take {}".format(take_id))
        idx["starred"] = take_id
        self.write_index(scene_id, idx)

    def delete_take(self, scene_id, take_id):
        idx = self.read_index(scene_id)
        idx["takes"] = [t for t in idx["takes"] if t["id"] != take_id]
        if idx["starred"] == take_id:
            idx["starred"] = idx["takes"][-1]["id"] if idx["takes"] else None
        self.write_index(scene_id, idx)
        d = self.take_dir(scene_id, take_id)
        if os.path.isdir(d):
            for root, dirs, files in os.walk(d, topdown=False):
                for f in files:
                    os.remove(os.path.join(root, f))
                for x in dirs:
                    os.rmdir(os.path.join(root, x))
            os.rmdir(d)

    def starred_take(self, scene_id):
        idx = self.read_index(scene_id)
        return next((t for t in idx["takes"] if t["id"] == idx["starred"]), None)

    # project file and versions
    def autosave(self, project, force_version=False):
        os.makedirs(self.dir, exist_ok=True)
        path = os.path.join(self.dir, "project.json")
        previous = read_json(path)
        write_json(path, project)
        vdir = os.path.join(self.dir, "versions")
        versions = self.list_versions()
        newest = versions[0]["created"] if versions else 0
        changed = previous != project
        name = None
        if force_version or (changed and time.time() - newest >= VERSION_INTERVAL):
            name = time.strftime("project_%Y%m%d_%H%M%S.json")
            write_json(os.path.join(vdir, name), project)
            for v in self.list_versions()[MAX_VERSIONS:]:
                os.remove(os.path.join(vdir, v["name"]))
        return name

    def list_versions(self):
        vdir = os.path.join(self.dir, "versions")
        if not os.path.isdir(vdir):
            return []
        out = []
        for name in os.listdir(vdir):
            if VERSION_RE.match(name):
                st = os.stat(os.path.join(vdir, name))
                out.append({"name": name, "created": int(st.st_mtime), "size": st.st_size})
        return sorted(out, key=lambda v: v["name"], reverse=True)

    # added 2026-11-02 v0.3.6: delete autosaved versions (project.json, the latest autosave, is never touched)
    def delete_versions(self, names):
        names = list(names or [])
        bad = [n for n in names if not VERSION_RE.match(n or "")]
        if bad:
            raise ValueError("invalid version name: " + bad[0])
        removed = 0
        for name in names:
            path = safe_join(self.dir, "versions", name)
            if os.path.isfile(path):
                os.remove(path)
                removed += 1
        return removed

    def read_version(self, name):
        if not VERSION_RE.match(name or ""):
            raise ValueError("invalid version name")
        return read_json(safe_join(self.dir, "versions", name))

    def next_cut_path(self, ext=".mp4"):
        d = self.cuts_dir()
        os.makedirs(d, exist_ok=True)
        n = 1
        while os.path.exists(os.path.join(d, "{}_cut_v{}{}".format(self.slug, n, ext))):
            n += 1
        return os.path.join(d, "{}_cut_v{}".format(self.slug, n))
