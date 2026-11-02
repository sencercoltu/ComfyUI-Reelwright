"""Lint rules. Problems are reported, never fixed silently; only errors block a render."""

from . import spec
from .model import project_index
from .planner import continuation_depth


def _issue(level, message, scene_id=None):
    x = {"level": level, "message": message}
    if scene_id:
        x["scene_id"] = scene_id
    return x


def lint_project(p, plans, builds, asset_exists):
    idx = project_index(p)
    assets, cast = idx["assets"], idx["cast"]
    issues = []
    depth = continuation_depth(p)
    reanchor = int(p["global"]["continuity"]["reanchor_after"])

    for a in p["assets"]:
        if not a.get("file") or not asset_exists(a):
            issues.append(_issue("error", "{} ({}) file is missing".format(a["code"], a["name"] or a["file"])))

    score = p["global"]["merge"]["score"].get("asset")
    if score and score not in assets:
        issues.append(_issue("warn", "Merge score track asset no longer exists"))

    for i, s in enumerate(p["scenes"]):
        sid = s["id"]
        name = "{:02d} {}".format(i + 1, s["title"])
        d = float(s["duration"])
        plan = plans[sid]
        if d <= 0:
            issues.append(_issue("error", "{}: duration must be above 0".format(name), sid))
        if i == 0 and s["start"]["mode"] != "fresh":
            issues.append(_issue("info", "{}: the first scene always starts fresh".format(name), sid))
        if plan["kind"] == "long":
            issues.append(_issue("info", "{}: split into {} passes".format(name, len(plan["passes"])), sid))
        if plan["kind"] == "short":
            issues.append(_issue("info", "{}: rendered as {} frames and trimmed to {:.2f} s".format(
                name, spec.MIN_PASS_FRAMES, d), sid))
        if depth.get(sid, 0) > reanchor and s["start"]["mode"] == "tail":
            issues.append(_issue("info", "{}: {} chained continuations, so it continues from the last frame only (re-anchor rule)".format(
                name, depth[sid]), sid))

        for sh in s["shots"]:
            if float(sh["t"]) >= d:
                issues.append(_issue("error", "{}: a shot starts at {:.2f} s, after the scene ends".format(name, float(sh["t"])), sid))
        for line in s["dialogue"]:
            t = float(line["t"])
            if t >= d:
                issues.append(_issue("error", "{}: a dialogue line at {:.2f} s is after the scene ends".format(name, t), sid))
            if not line["text"].strip():
                issues.append(_issue("warn", "{}: a dialogue line is empty".format(name), sid))
            if not line.get("speaker"):
                issues.append(_issue("warn", "{}: a dialogue line has no speaker".format(name), sid))
            elif line["speaker"] not in cast:
                issues.append(_issue("error", "{}: a dialogue speaker is not in the cast".format(name), sid))
            if not line.get("language"):
                issues.append(_issue("warn", "{}: a dialogue line has no language tag".format(name), sid))
            elif line["language"] not in spec.STABLE_LANGUAGES:
                issues.append(_issue("info", "{}: {} is outside H3's 11 stable dialogue languages".format(name, line["language"]), sid))

        has_first = False
        for r in s["refs"]:
            a = assets.get(r["asset"])
            if not a:
                issues.append(_issue("error", "{}: a reference points to a deleted asset".format(name), sid))
                continue
            if r["role"] == "keyframe" and not (0 <= float(r["time"]) < d):
                issues.append(_issue("error", "{}: keyframe {} at {:.2f} s is outside the scene".format(name, a["code"], float(r["time"])), sid))
            if r["role"] in ("first_frame", "last_frame", "keyframe") and a["kind"] == "audio":
                issues.append(_issue("error", "{}: audio {} cannot be a {}".format(name, a["code"], r["role"].replace("_", " ")), sid))
            if r["role"] == "first_frame":
                has_first = True
        if has_first and i > 0 and s["start"]["mode"] != "fresh":
            issues.append(_issue("warn", "{}: a first-frame reference and a continuation both anchor frame 0".format(name), sid))

        for entry in s["cast"]:
            c = cast.get(entry["id"])
            if not c:
                issues.append(_issue("error", "{}: a cast member was deleted".format(name), sid))
            elif c["kind"] == "character" and not c["anchors"]:
                issues.append(_issue("warn", "{}: {} has no anchor pictures, so identity is not locked".format(name, c["name"]), sid))

        for b, pass_ in zip(builds[sid], plan["passes"]):
            where = name if len(plan["passes"]) == 1 else "{} pass {}".format(name, pass_["index"])
            for tag in b["unknown"]:
                issues.append(_issue("error", "{}: {} does not match an asset or cast member in this scene".format(where, tag), sid))
            n_img, n_vid, n_aud = len(b["images"]), len(b["videos"]), len(b["audios"])
            if n_img > spec.MAX_REF_IMAGES:
                issues.append(_issue("warn", "{}: {} pictures (H3 is trained on up to 9)".format(where, n_img), sid))
            if n_vid > spec.MAX_REF_VIDEOS:
                issues.append(_issue("warn", "{}: {} reference videos (up to 3)".format(where, n_vid), sid))
            if n_aud > spec.MAX_REF_AUDIOS:
                issues.append(_issue("warn", "{}: {} reference audio clips (up to 3)".format(where, n_aud), sid))
            if n_img + n_vid + n_aud > spec.MAX_REF_FILES:
                issues.append(_issue("warn", "{}: {} reference files (up to 12)".format(where, n_img + n_vid + n_aud), sid))
            for kind, items in (("video", [assets[v["asset"]] for v in b["videos"]]),
                                ("audio", [assets[x["asset"]] for x in b["audios"]])):
                total = 0.0
                for a in items:
                    dur = float(a.get("duration") or 0)
                    total += dur
                    if dur and not (spec.REF_MEDIA_MIN_SECONDS <= dur <= spec.REF_MEDIA_MAX_SECONDS):
                        issues.append(_issue("warn", "{}: {} is {:.1f} s (H3 {} refs are 2-15 s)".format(where, a["code"], dur, kind), sid))
                if total > spec.REF_MEDIA_TOTAL_SECONDS:
                    issues.append(_issue("warn", "{}: {} refs total {:.1f} s (max 15 s)".format(where, kind, total), sid))
            if s["prompt"]["mode"] == "raw":
                text = (s["prompt"]["pass_prompts"] or {}).get(str(pass_["index"])) or s["prompt"]["raw"]
                for img in b["images"]:
                    for aid in img["assets"]:
                        code = "@" + assets[aid]["code"]
                        if not img["cast"] and code.lower() not in text.lower():
                            issues.append(_issue("info", "{}: {} is attached but never named in the prompt".format(where, code), sid))
            # added 2026-11-02 v0.2.0: hints from MiniMax's Ref2VA prompt guide (ref-en.txt)
            elif not (s["prompt"]["pass_prompts"] or {}).get(str(pass_["index"]), "").strip():
                desc = b["prompt"].split("detailed_description:\n", 1)[-1].split("\n\noverall_soundscape:", 1)[0]
                words = len(desc.split())
                if words < 120:
                    issues.append(_issue("info", "{}: detailed_description has {} words; H3's guide aims for 350-500 "
                                                 "(Rewrite can expand it)".format(where, words), sid))
        if s["prompt"]["mode"] != "raw":
            if not s["prompt"]["sections"]["overall_soundscape"].strip():
                issues.append(_issue("info", "{}: overall_soundscape is empty, so H3 gets N/A, which its guide "
                                             "reserves for complete silence".format(name), sid))
            described = set()
            for b in builds[sid]:
                for subj in b["subjects"]:
                    a = assets.get(subj.get("asset") or "")
                    if a and not (a.get("description") or "").strip() and a["id"] not in described:
                        described.add(a["id"])
                        issues.append(_issue("info", "{}: {} has no description, so its subject line is generic "
                                                     "(Assets tab: Describe with LLM)".format(name, a["code"]), sid))
    return issues
