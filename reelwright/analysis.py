"""Plan, prompts, keys, status and lint for a whole project in one pass.

Used by the /reelwright/plan route (editor feedback) and by the renderer, so
both always agree on what will be generated.
"""

import inspect  # added 2026-11-03 v0.6.0: feature-detect prompt.build_pass(ctx=)
import json  # added 2026-11-03 v0.6.0: starred take's meta.json
import os
import statistics  # added 2026-11-03 v0.6.0: time estimates

from . import cache
# [OLD 2026-11-03 v0.5.1->v0.6.0] from .model import normalize_project, project_index, resolve_settings, scene_starts
from . import model, spec  # added 2026-11-03 v0.6.0: model.effective_start when Agent M's model has it
from . import prompt as prompt_mod  # added 2026-11-03 v0.6.0: prompt.prepare / build_pass(ctx=) when present
from .model import normalize_project, project_index, resolve_settings, scene_starts
from .planner import plan_project
# [OLD 2026-11-03 v0.5.1->v0.6.0] from .prompt import build_pass  (called through prompt_mod so a ctx can be passed)
from .validate import lint_project

# added 2026-11-03 v0.6.0: plan fields the editor does not need in every take of every scene (they can be large)
TAKE_FIELDS_NOT_IN_PLAN = ("prompts",)


def continues(p, i):
    """added 2026-11-03 v0.6.0: does scene i start from the scene before it (last frame or tail clip)?"""
    if i <= 0:
        return False
    fn = getattr(model, "effective_start", None)
    if fn is not None:
        return fn(p, i) != "fresh"
    return p["scenes"][i]["start"]["mode"] in ("last_frame", "tail")


def _builder(p):
    """added 2026-11-03 v0.6.0: build_pass with one shared context per analysis (prompt.prepare, when the prompt
    module has it), so the project index, starts and soundtrack are worked out once and not once per pass."""
    prepare = getattr(prompt_mod, "prepare", None)
    ctx = None
    if prepare is not None:
        try:
            ctx = prepare(p)
        except TypeError:
            ctx = None
    try:
        takes_ctx = "ctx" in inspect.signature(prompt_mod.build_pass).parameters
    except (TypeError, ValueError):
        takes_ctx = False
    if ctx is not None and takes_ctx:
        return ctx, lambda s, i, plan, x: prompt_mod.build_pass(p, s, i, plan, x, ctx=ctx)
    return None, lambda s, i, plan, x: prompt_mod.build_pass(p, s, i, plan, x)


def _lint(p, plans, builds, asset_exists, ctx):
    """added 2026-11-03 v0.6.0: lint_project with the prompt context when validate takes one."""
    if ctx is not None:
        try:
            if "ctx" in inspect.signature(lint_project).parameters:
                return lint_project(p, plans, builds, asset_exists, ctx=ctx)
        except (TypeError, ValueError):
            pass
    return lint_project(p, plans, builds, asset_exists)


def tail_guide_frames(builds):
    """added 2026-11-03 v0.6.0 review: frames of the tail clip pass 1 of a scene takes from the scene before (the
    prev_scene_tail guide render cuts from the upstream take), 0 when it has none."""
    for g in (builds[0].get("guides") or []) if builds else []:
        if g.get("source") == "prev_scene_tail":
            return int(g.get("frames") or 0)
    return 0


def short_upstream_tail(p, i, builds, take):
    """added 2026-11-03 v0.6.0 review: the problem when scene i's tail clip needs more frames than `take` (the take
    of the scene before that it continues from) has, else None. The overlap is planned from the CURRENT length of the
    scene before (model.tail_overlap_frames), but a hand-picked, locked or older take can be shorter: the guide would
    get fewer frames than the cut trims. Analysis reports it as a warning; pre-flight refuses such a scene unless the
    scene before is rendered earlier in the same run."""
    need = tail_guide_frames(builds)
    try:
        have = int((take or {}).get("frames") or 0)
    except (TypeError, ValueError):
        have = 0
    if not need or not take or have <= 0 or have >= need:  # no tail, or a take that does not say how long it is
        return None
    s, prev = p["scenes"][i], p["scenes"][i - 1]
    name, prev_name = "{:02d} {}".format(i + 1, s["title"]), "{:02d} {}".format(i, prev["title"])
    fits = spec.align_frames_down(have) if have >= 5 else 0
    shorter = "a tail overlap of at most {} frames".format(fits) if fits else "no tail overlap"
    return ("{}: it continues with a {}-frame tail clip of {}, but the take it continues from ({}) has only {} "
            "frames. Render {} again, or use {} or a last-frame start.".format(
                name, need, prev_name, take.get("id"), have, prev_name, shorter))


def _pass_keys(fp, builds, plan, asset_digest, upstream_key, upstream_take):
    """added 2026-11-03 v0.6.0"""
    keys, prev = [], None
    for b, x in zip(builds, plan["passes"]):
        prev = cache.pass_key(fp, b, x, asset_digest, upstream_key, prev, upstream_take)
        keys.append(prev)
    return keys


_meta_memo = {}


def _take_meta(store, sid, take_id):
    """added 2026-11-03 v0.6.0: a take's meta.json (memoised by mtime), {} when missing or unreadable."""
    try:
        path = os.path.join(store.take_dir(sid, take_id), "meta.json")
        st = os.stat(path)
    except (OSError, ValueError):
        return {}
    k = (path, st.st_mtime_ns, st.st_size)
    if k not in _meta_memo:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        if len(_meta_memo) > 2000:
            _meta_memo.clear()
        _meta_memo[k] = data if isinstance(data, dict) else {}
    return _meta_memo[k]


# ---- time estimates (added 2026-11-03 v0.6.0) --------------------------------------------------------------------

def _rate_samples(all_takes):
    """[(rate s/frame, quality, w, h, steps, created)] from takes that sampled at least one frame."""
    out = []
    for t in all_takes:
        try:
            secs = float(t.get("render_seconds") or 0)
        except (TypeError, ValueError):
            continue
        if secs <= 0:
            continue
        if "sampled_frames" in t:  # v0.6.0 takes: frames actually generated (passes from the pass cache excluded)
            frames = int(t.get("sampled_frames") or 0)
        else:  # older takes: every pass was generated; a short scene still generates a whole 124-frame pass
            frames = max(int(t.get("frames") or 0), spec.MIN_PASS_FRAMES)
        if frames <= 0:
            continue
        # [OLD 2026-11-04 v0.6.0->v0.6.1] int(t.get("created") or 0) raised on a "created" that is not a number
        out.append((secs / frames, t.get("quality"), t.get("width"), t.get("height"), t.get("steps"),
                    cache.created_of(t)))  # added 2026-11-04 v0.6.1
    return out


def _median_recent(rows, n=20):
    rows = sorted(rows, key=lambda r: r[-1])[-n:]
    return statistics.median(r[0] for r in rows) if rows else None


def seconds_per_frame(samples, settings):
    """Seconds one generated frame takes with these settings, from earlier takes; None without history."""
    w, h, steps, q = settings.get("width"), settings.get("height"), settings.get("steps"), settings.get("quality")
    exact = [r for r in samples if (r[1], r[2], r[3], r[4]) == (q, w, h, steps)]
    if exact:
        return _median_recent(exact)
    sized = [(r[0] / (r[2] * r[3] * r[4]),) + r[1:] for r in samples if r[2] and r[3] and r[4]]
    if sized and w and h and steps:
        return _median_recent(sized) * w * h * steps
    same_quality = [r for r in samples if r[1] == q]
    if same_quality:
        return _median_recent(same_quality)
    return None


def _cached_pass_flags(store, sid, plan, builds, keys, continuing, upstream_pending):
    """[bool] per pass: a pending render (first take seeds) finds the pass in the pass cache."""
    if not (len(plan["passes"]) > 1 or plan["kind"] == "short"):
        return [False] * len(plan["passes"])
    try:
        names = set(os.listdir(os.path.join(store.scene_dir(sid), "passes")))
    except (OSError, ValueError):
        return [False] * len(plan["passes"])
    fkeys = cache.pass_file_keys(keys, builds, [x["seed"] for x in plan["passes"]])
    dep = cache.upstream_dependent(builds, continuing)
    return [(not (upstream_pending and d)) and (k + ".mp4") in names and (k + ".json") in names
            for k, d in zip(fkeys, dep)]


def analyze(project, store, wired=None):
    p = normalize_project(project)
    wired = wired or {}
    idx = project_index(p)  # built once per analysis
    plans = plan_project(p)
    # [OLD 2026-11-03 v0.5.1->v0.6.0] builds = {s["id"]: [build_pass(p, s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
    #           for i, s in enumerate(p["scenes"])}
    ctx, build = _builder(p)  # added 2026-11-03 v0.6.0: one prompt context for every scene and pass
    builds = {s["id"]: [build(s, i, plans[s["id"]], x) for x in plans[s["id"]]["passes"]]
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

    # [OLD 2026-11-03 v0.5.1->v0.6.0] issues = lint_project(p, plans, builds, asset_exists)
    issues = _lint(p, plans, builds, asset_exists, ctx)  # added 2026-11-03 v0.6.0: the same prompt context
    errors_by_scene = {}
    for x in issues:
        if x["level"] == "error" and x.get("scene_id"):
            errors_by_scene[x["scene_id"]] = True
    global_errors = [x for x in issues if x["level"] == "error" and not x.get("scene_id")]

    # [OLD 2026-11-03 v0.5.1->v0.6.0] the key used the upstream scene's key only, not the take it continues from (#11),
    # and a run re-starred the matching take even over a star picked by hand
    # scenes = {}
    # upstream = None
    # for i, s in enumerate(p["scenes"]):
    #     sid = s["id"]
    #     settings = resolve_settings(p, s, i)
    #     fp = cache.settings_fingerprint(settings, wired)
    #     plan = plans[sid]
    #     keys, prev = [], None
    #     for b, x in zip(builds[sid], plan["passes"]):
    #         prev = cache.pass_key(fp, b, x, asset_digest, upstream, prev)
    #         keys.append(prev)
    #     key = cache.scene_key(plan, keys)
    #     index = store.read_index(sid)
    #     status, match = cache.status_of(s, index, key, sid in errors_by_scene)
    #     scenes[sid] = {
    #         "index": i,
    #         "plan": plan,
    #         "passes": [dict({k: v for k, v in x.items() if k not in ("shots", "dialogue", "keyframes", "first_frame", "last_frame")},
    #                         key=keys[n]) for n, x in enumerate(plan["passes"])],
    #         "builds": builds[sid],
    #         "prompts": [b["prompt"] for b in builds[sid]],
    #         "pass_keys": keys,
    #         "key": key,
    #         "status": status,
    #         "match": match["id"] if match else None,
    #         "starred": index.get("starred"),
    #         "takes": index.get("takes", []),
    #         "settings": settings,
    #         "issues": [x for x in issues if x.get("scene_id") == sid],
    #     }
    #     upstream = cache.used_key(s, index, key)
    # [/OLD]
    # added 2026-11-03 v0.6.0: a continuing scene's key holds the take it continues from (the take the scene before
    # provides: its starred take when cached or locked or picked by hand, nothing when it is going to be rendered).
    # The v0.5.1 key is computed beside it, so takes rendered before v0.6.0 stay cached.
    # added 2026-11-03 v0.6.0 review: a scene with lint errors provides its starred take (cache.resolve): no run
    # renders or re-stars it, so that is the take the next scene is rendered from.
    crossfade = int(p["global"]["long"]["crossfade_frames"])
    scenes, all_takes = {}, []
    prev_key, prev_provided, prev_pending, legacy_up = None, None, False, None
    for i, s in enumerate(p["scenes"]):
        sid = s["id"]
        settings = resolve_settings(p, s, i)
        fp = cache.settings_fingerprint(settings, wired)
        plan = plans[sid]
        cont = continues(p, i)
        up_take = prev_provided if cont else None
        # added 2026-11-03 v0.6.0 review: a tail clip longer than the take it is cut from (warning; pre-flight refuses)
        short_tail = short_upstream_tail(p, i, builds[sid], up_take) if up_take else None
        if short_tail:
            issues.append({"level": "warn", "message": short_tail, "scene_id": sid, "code": "short_upstream_tail"})
        up_key = up_take["key"] if up_take and up_take.get("key") else prev_key
        keys = _pass_keys(fp, builds[sid], plan, asset_digest, up_key, up_take["id"] if up_take else None)
        key = cache.scene_key(plan, keys, crossfade)
        legacy_keys = _pass_keys(fp, builds[sid], plan, asset_digest, legacy_up, None)
        legacy_key = cache.scene_key(plan, legacy_keys)
        index = store.read_index(sid)
        res = cache.resolve(s, index, key, sid in errors_by_scene, legacy_key=legacy_key, upstream=up_take)
        status, match, starred = res["status"], res["match"], res["starred"]
        all_takes += index.get("takes", [])

        upstream_changed = False
        if cont and starred:
            if "upstream" in starred:
                used = starred.get("upstream") or {}
                upstream_changed = used.get("take_id") != (up_take["id"] if up_take else None)
            else:  # before v0.6.0 the take did not say; a newer upstream take means it changed
                # [OLD 2026-11-04 v0.6.0->v0.6.1] a "created" that is not a number raised ValueError (500 on /plan)
                # upstream_changed = up_take is None or int(up_take.get("created") or 0) > int(starred.get("created") or 0)
                upstream_changed = up_take is None or cache.created_of(up_take) > cache.created_of(starred)  # added 2026-11-04 v0.6.1
        starred_prompts = None
        if starred:
            starred_prompts = starred.get("prompts")
            if starred_prompts is None:
                starred_prompts = _take_meta(store, sid, starred["id"]).get("prompts")
            if not isinstance(starred_prompts, list):
                starred_prompts = None

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
            # added 2026-11-03 v0.6.0
            "continues": cont,
            "manual_star": res["manual"],
            "upstream_take": up_take["id"] if up_take else None,
            "upstream_changed": upstream_changed,
            "starred_prompts": starred_prompts,
            "cached_passes": _cached_pass_flags(store, sid, plan, builds[sid], keys, cont, cont and prev_pending)
            if status in ("stale", "missing") else [],
            "_fp": fp,
            "_prev_key": prev_key,
        }
        prev_key, prev_provided = key, res["provided"]
        prev_pending = res["provided"] is None
        legacy_up = cache.used_key(s, index, legacy_key)

    # added 2026-11-03 v0.6.0: time estimates from earlier takes' render_seconds
    samples = _rate_samples(all_takes)
    pending = {"seconds": 0.0, "scenes": 0, "unknown": 0}
    for sid, sr in scenes.items():
        rate = seconds_per_frame(samples, sr["settings"])
        gen = sum(x["gen_frames"] for x in sr["plan"]["passes"])
        sr["estimate_seconds"] = round(rate * gen, 1) if rate is not None else None
        if sr["status"] in ("stale", "missing"):
            pending["scenes"] += 1
            todo = sum(x["gen_frames"] for x, hit in zip(sr["plan"]["passes"], sr["cached_passes"] or
                                                          [False] * len(sr["plan"]["passes"])) if not hit)
            if rate is None:
                pending["unknown"] += 1
            else:
                pending["seconds"] += rate * todo
    # seconds: the scenes with history (`unknown` counts the others); None when no pending scene has any
    if pending["scenes"] and pending["unknown"] == pending["scenes"]:
        pending["seconds"] = None
    else:
        pending["seconds"] = round(pending["seconds"], 1)

    starts, total = scene_starts(p)
    # [OLD 2026-11-03 v0.5.1->v0.6.0] return {"project": p, "scenes": scenes, "issues": issues, "global_errors": global_errors,
    #         "timeline": {"starts": starts, "total": total}}
    return {"project": p, "scenes": scenes, "issues": issues, "global_errors": global_errors,
            "timeline": {"starts": starts, "total": total},
            "estimate": pending,  # added 2026-11-03 v0.6.0
            "_asset_digest": asset_digest}  # added 2026-11-03 v0.6.0: for rekey()


def rekey(result, sid, upstream):
    """added 2026-11-03 v0.6.0: (pass_keys, scene_key) of a scene when it continues from `upstream` (a take dict:
    the upstream scene's starred take at render time, which can be a take made earlier in the same run). Fresh scenes
    keep their keys."""
    sr = result["scenes"][sid]
    if not sr.get("continues") or not upstream:
        return sr["pass_keys"], sr["key"]
    up_key = upstream.get("key") or sr["_prev_key"]
    keys = _pass_keys(sr["_fp"], sr["builds"], sr["plan"], result["_asset_digest"], up_key, upstream.get("id"))
    return keys, cache.scene_key(sr["plan"], keys, int(result["project"]["global"]["long"]["crossfade_frames"]))


def plan_response(result):
    """JSON shape the editor reads from /reelwright/plan."""
    out = {}
    for sid, s in result["scenes"].items():
        out[sid] = {"status": s["status"], "key": s["key"], "starred": s["starred"], "match": s["match"],
                    "kind": s["plan"]["kind"], "passes": s["passes"], "prompts": s["prompts"],
                    "tags": [b["tags"] for b in s["builds"]],
                    "tag_maps": [b["tag_map"] for b in s["builds"]],
                    "issues": s["issues"],
                    # [OLD 2026-11-03 v0.5.1->v0.6.0] "takes": s["takes"],  (takes now carry their per-pass prompts)
                    "takes": [{k: v for k, v in t.items() if k not in TAKE_FIELDS_NOT_IN_PLAN} for t in s["takes"]],
                    "settings": {k: v for k, v in s["settings"].items() if k != "loras"},
                    # [OLD 2026-11-03 v0.5.1->v0.6.0] "loras": [{"name": n, "strength": v} for n, v in s["settings"]["loras"]]}
                    "loras": [{"name": n, "strength": v} for n, v in s["settings"]["loras"]],
                    # added 2026-11-03 v0.6.0
                    "upstream_take": s.get("upstream_take"),
                    "upstream_changed": bool(s.get("upstream_changed")),
                    "manual_star": bool(s.get("manual_star")),
                    "estimate_seconds": s.get("estimate_seconds"),
                    "starred_prompts": s.get("starred_prompts"),
                    "cached_passes": sum(1 for x in s.get("cached_passes") or [] if x)}
    # [OLD 2026-11-03 v0.5.1->v0.6.0] return {"scenes": out, "issues": result["issues"], "timeline": result["timeline"]}
    return {"scenes": out, "issues": result["issues"], "timeline": result["timeline"],
            "estimate": result.get("estimate") or {"seconds": None, "scenes": 0, "unknown": 0}}
