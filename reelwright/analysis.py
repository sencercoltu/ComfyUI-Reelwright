"""Plan, prompts, keys, status and lint for a whole project in one pass.

Used by the /reelwright/plan route (editor feedback) and by the renderer, so
both always agree on what will be generated.
"""

import os

from . import cache
from .model import normalize_project, project_index, resolve_settings, scene_starts
from .planner import plan_project
from .prompt import build_pass
from .validate import lint_project


def analyze(project, store, wired=None):
    p = normalize_project(project)
    wired = wired or {}
    idx = project_index(p)
    plans = plan_project(p)
    builds = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
              for i, s in enumerate(p["scenes"])}

    def asset_path(a):
        return store.input_path(a["file"]) if a.get("file") else ""

    def asset_exists(a):
        try:
            return os.path.isfile(asset_path(a))
        except ValueError:
            return False

    def asset_digest(aid):
        a = idx["assets"].get(aid)
        if not a:
            return "missing"
        try:
            return cache.file_digest(asset_path(a))
        except ValueError:
            return "invalid"

    issues = lint_project(p, plans, builds, asset_exists)
    errors_by_scene = {}
    for x in issues:
        if x["level"] == "error" and x.get("scene_id"):
            errors_by_scene[x["scene_id"]] = True
    global_errors = [x for x in issues if x["level"] == "error" and not x.get("scene_id")]

    scenes = {}
    upstream = None
    for i, s in enumerate(p["scenes"]):
        sid = s["id"]
        settings = resolve_settings(p, s, i)
        fp = cache.settings_fingerprint(settings, wired)
        plan = plans[sid]
        keys, prev = [], None
        for b, x in zip(builds[sid], plan["passes"]):
            prev = cache.pass_key(fp, b, x, asset_digest, upstream, prev)
            keys.append(prev)
        key = cache.scene_key(plan, keys)
        index = store.read_index(sid)
        status, match = cache.status_of(s, index, key, sid in errors_by_scene)
        scenes[sid] = {
            "index": i,
            "plan": plan,
            "passes": [dict({k: v for k, v in x.items() if k not in ("shots", "dialogue", "keyframes", "first_frame", "last_frame")},
                            key=keys[n]) for n, x in enumerate(plan["passes"])],
            "builds": builds[sid],
            "prompts": [b["prompt"] for b in builds[sid]],
            "pass_keys": keys,
            "key": key,
            "status": status,
            "match": match["id"] if match else None,
            "starred": index.get("starred"),
            "takes": index.get("takes", []),
            "settings": settings,
            "issues": [x for x in issues if x.get("scene_id") == sid],
        }
        upstream = cache.used_key(s, index, key)
    starts, total = scene_starts(p)
    return {"project": p, "scenes": scenes, "issues": issues, "global_errors": global_errors,
            "timeline": {"starts": starts, "total": total}}


def plan_response(result):
    """JSON shape the editor reads from /reelwright/plan."""
    out = {}
    for sid, s in result["scenes"].items():
        out[sid] = {"status": s["status"], "key": s["key"], "starred": s["starred"], "match": s["match"],
                    "kind": s["plan"]["kind"], "passes": s["passes"], "prompts": s["prompts"],
                    "tags": [b["tags"] for b in s["builds"]],
                    "tag_maps": [b["tag_map"] for b in s["builds"]],
                    "issues": s["issues"],
                    "takes": s["takes"],
                    "settings": {k: v for k, v in s["settings"].items() if k != "loras"},
                    "loras": [{"name": n, "strength": v} for n, v in s["settings"]["loras"]]}
    return {"scenes": out, "issues": result["issues"], "timeline": result["timeline"]}
