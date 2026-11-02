"""OpenAI-compatible chat client and the prompt templates for rewrite, split and
script import. Every call is started by a button in the editor; nothing here
runs during a queue run.
"""

import json
import os
import re
import time

import aiohttp

from .storage import read_json, write_json

TIMEOUT = aiohttp.ClientTimeout(total=180)
TAG_RE = re.compile(r"@\{[^}]+\}|@[A-Za-z][\w-]*")
DIALOGUE_RE = re.compile(r"<d>.*?</d>", re.S)

# [OLD 2026-11-02 v0.1.0->v0.2.0] rules used "[Shot1]"; MiniMax's guide writes "[Shot 1]" and the guides
# themselves are now sent along (see GUIDES below)
# H3_RULES = """You write prompts for MiniMax H3 ref2va, a reference-to-video-with-audio model.
# Rules you must follow:
# - Keep every reference token exactly as written: @P1, @V2, @A1, @Name, @{Two Words}, @tail. Never invent new ones, never rename them.
# - Keep every dialogue span <d>[Language] ...</d> exactly as written, word for word.
# - Keep shot markers like [Shot1] and timestamps like "At 00:05.000" unless asked to change them; timestamps mark cuts.
# - One main action per shot, physically achievable in the time given. State camera framing and movement or say the camera is static.
# - Concrete visual and sound detail; no camera brand names, no meta commentary."""
# [/OLD]
H3_RULES = """You write prompts for MiniMax H3 Ref2VA, a reference-to-video-with-audio model.
Rules you must follow:
- Keep every reference token exactly as written: @P1, @V2, @A1, @Name, @{Two Words}, @tail. Never invent new ones, never rename them. The editor turns them into <Subject N>, <Picture N>, <Video N> and <Audio N> labels later.
- Keep every dialogue span <d>[Language] ...</d> exactly as written, word for word.
- Keep shot markers like [Shot 2] and cut times like "At 00:05.000" unless asked to change them; cut times mark cuts and the first shot has none.
- Write in English. Describe each shot by composition, subject appearance and position, environment and lighting, action, camera movement and sound.
- One main action per shot, physically achievable in the time given. Concrete visual and sound detail; no plot summaries, no meta commentary."""

# added 2026-11-02 v0.2.0: MiniMax's official prompt guides. They are published under the MiniMax H3
# Community License, so Reelwright downloads them on request instead of shipping copies.
GUIDES = {
    "ref-en.txt": "https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/skills/h3-prompt-writing/references/ref-en.txt",
    "base-en.txt": "https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/skills/h3-prompt-writing/references/base-en.txt",
}
GUIDE_FALLBACK = """Ref2VA output format (summary used until the official guides are downloaded):
Six sections in this order, each label on its own line followed by its text: subject_definitions:, summary:,
retention_analysis:, detailed_description:, overall_soundscape:, non_diegetic_music:.
subject_definitions: one line per tracked item, e.g. "<Subject 1> is the young woman in <Picture 1>, with long dark hair."
Standalone <Picture N> lines only for frame anchors ("<Picture 2> is the first frame of [Shot 1], ...").
summary: starts with the task types in brackets joined by " + ", e.g. "[reference generation + audio reference]".
retention_analysis: one line per label, e.g. "<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - ...";
visual markers fully_preserved, partially_preserved, attribute_transfer, weak_reference; audio markers fully_copy,
partially_copy, reference, weak_reference. No speaker IDs here.
detailed_description: one or two style sentences, then "[Shot 1] ..." and "[Shot N] At MM:SS.mmm, the shot cuts to ...".
Speakers get (S1), (S2) in the order they first speak; dialogue is <d>[Language] exact words.</d>.
Generation tasks usually run 350-500 English words here.
overall_soundscape: ambience and physical sounds, no dialogue. non_diegetic_music: score only the audience hears, or N/A."""

PRESETS = {
    "h3_ref2va": "Write in the six-section structure (subject definitions, summary, retention, detailed shot description, soundscape, music). Be precise and complete.",
    "h3_compact": "Be concise: short, dense sentences, no repetition, keep only what changes the picture or sound.",
    "h3_cinematic": "Write like a cinematographer: lens feel, light, blocking, texture and sound design, while keeping the structure.",
}


def settings_path(user_root):
    return os.path.join(user_root, "reelwright", "llm.json")


def load_settings(user_root):
    s = read_json(settings_path(user_root), {}) or {}
    return {"base_url": s.get("base_url", ""), "model": s.get("model", ""), "api_key": s.get("api_key", "")}


def save_settings(user_root, update):
    s = load_settings(user_root)
    for k in ("base_url", "model", "api_key"):
        if k in update and update[k] is not None:
            s[k] = str(update[k]).strip()
    write_json(settings_path(user_root), s)
    return s


def guides_dir(user_root):
    return os.path.join(user_root, "reelwright", "guides")


def guide_status(user_root):
    out = {}
    for name in GUIDES:
        path = os.path.join(guides_dir(user_root), name)
        if os.path.isfile(path):
            st = os.stat(path)
            out[name] = {"bytes": st.st_size, "fetched": int(st.st_mtime)}
    return out


def load_guides(user_root):
    texts = {}
    for name in GUIDES:
        path = os.path.join(guides_dir(user_root), name)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                texts[name] = f.read()
    return texts


async def fetch_guides(user_root):
    os.makedirs(guides_dir(user_root), exist_ok=True)
    # trust_env: honour HTTP(S)_PROXY / NO_PROXY like a browser would, since this is a public download
    async with aiohttp.ClientSession(timeout=TIMEOUT, trust_env=True) as s:
        for name, url in GUIDES.items():
            async with s.get(url) as r:
                if r.status >= 400:
                    raise RuntimeError("Could not download {} (HTTP {})".format(name, r.status))
                text = await r.text()
            tmp = os.path.join(guides_dir(user_root), name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, os.path.join(guides_dir(user_root), name))
    return guide_status(user_root)


def system_prompt(cfg, extra=""):
    """H3 rules, then MiniMax's guides (or the built-in summary), then the preset style."""
    parts = [H3_RULES]
    if cfg.get("include_guides", True):
        g = cfg.get("guides") or {}
        if g.get("ref-en.txt"):
            parts.append("Official MiniMax H3 full-reference (Ref2VA) prompt guide. Follow its section names, labels "
                         "and formats exactly:\n\n" + g["ref-en.txt"])
            if g.get("base-en.txt"):
                parts.append("Official MiniMax H3 video prompt guide, for shots, camera wording, speakers, dialogue and "
                             "sound sections:\n\n" + g["base-en.txt"])
        else:
            parts.append(GUIDE_FALLBACK)
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


def resolve(project_llm, stored):
    """Project values win for URL/model; the key always comes from the user folder."""
    base = (project_llm.get("base_url") or stored["base_url"] or "").rstrip("/")
    if not base:
        raise ValueError("Set the LLM base URL in Global -> Prompt rewriter")
    # [OLD 2026-11-02 v0.1.0->v0.2.0] guides were not part of the config
    # return {"base_url": base, "model": project_llm.get("model") or stored["model"], "api_key": stored["api_key"],
    #         "temperature": float(project_llm.get("temperature", 0.4)), "max_tokens": int(project_llm.get("max_tokens", 2048)),
    #         "preset": project_llm.get("preset", "h3_ref2va")}
    # [/OLD]
    return {"base_url": base, "model": project_llm.get("model") or stored["model"], "api_key": stored["api_key"],
            "temperature": float(project_llm.get("temperature", 0.4)), "max_tokens": int(project_llm.get("max_tokens", 2048)),
            "preset": project_llm.get("preset", "h3_ref2va"), "include_guides": bool(project_llm.get("include_guides", True)),
            "guides": stored.get("guides") or {}}


def _headers(key):
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    return h


async def list_models(base_url, api_key):
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        async with s.get(base_url.rstrip("/") + "/models", headers=_headers(api_key)) as r:
            data = await r.json(content_type=None)
            if r.status >= 400:
                raise RuntimeError(_err(data, r.status))
    return sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))


def _err(data, status):
    if isinstance(data, dict):
        e = data.get("error")
        if isinstance(e, dict):
            return e.get("message") or str(e)
        if e:
            return str(e)
    return "HTTP {}".format(status)


async def chat(cfg, system, user, max_tokens=None):
    # `user` may be a list of OpenAI content parts (text + image_url) for vision models (added 2026-11-02 v0.2.0)
    body = {"model": cfg["model"], "temperature": cfg["temperature"],
            "max_tokens": max_tokens or cfg["max_tokens"],
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    t0 = time.time()
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        async with s.post(cfg["base_url"] + "/chat/completions", headers=_headers(cfg["api_key"]), json=body) as r:
            data = await r.json(content_type=None)
            if r.status >= 400:
                raise RuntimeError(_err(data, r.status))
    text = data["choices"][0]["message"].get("content") or ""
    # reasoning models may wrap their answer after a think block
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    return text, int((time.time() - t0) * 1000), data.get("model", cfg["model"])


def parse_json(text):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0] or [0])
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start:end + 1])


def preserved_warnings(before, after):
    """Tokens and dialogue lines that the model changed or dropped."""
    warnings = []
    missing = sorted(set(TAG_RE.findall(before)) - set(TAG_RE.findall(after)))
    added = sorted(set(TAG_RE.findall(after)) - set(TAG_RE.findall(before)))
    if missing:
        warnings.append("Dropped references: " + ", ".join(missing))
    if added:
        warnings.append("New references the scene does not have: " + ", ".join(added))
    lost = [d for d in DIALOGUE_RE.findall(before) if d not in after]
    if lost:
        warnings.append("Dialogue changed or removed: " + " | ".join(lost))
    return warnings


def scene_context(p, scene):
    idx_assets = {a["id"]: a for a in p["assets"]}
    cast = {c["id"]: c for c in p["cast"]}
    refs = []
    for r in scene["refs"]:
        a = idx_assets.get(r["asset"])
        if a:
            refs.append("@{} {} ({}, {}{})".format(a["code"], a["name"] or a["file"], a["kind"], r["role"],
                                                 ", at {:.2f}s".format(r["time"]) if r["role"] == "keyframe" else ""))
    people = []
    for e in scene["cast"]:
        c = cast.get(e["id"])
        if c:
            people.append("@{} - {} ({}){}".format(c["name"] if " " not in c["name"] else "{" + c["name"] + "}",
                                                  c["description"], c["kind"], ", speaker " + c["speaker"] if c["speaker"] else ""))
    shots = ["{:.2f}s {} | {}".format(float(s["t"]), s["camera"], s["text"]) for s in scene["shots"]]
    lines = ["{:.2f}s {}: <d>[{}] {}</d>".format(float(d["t"]), cast.get(d["speaker"], {}).get("name", "?"),
                                               d["language"], d["text"]) for d in scene["dialogue"]]
    return ("Scene: {title}, {dur:.2f} s.\nReferences:\n{refs}\nCast:\n{cast}\nShots:\n{shots}\nDialogue:\n{lines}".format(
        title=scene["title"], dur=float(scene["duration"]), refs="\n".join(refs) or "(none)",
        cast="\n".join(people) or "(none)", shots="\n".join(shots) or "(none)", lines="\n".join(lines) or "(none)"))


async def rewrite(cfg, p, scene, instruction, built=""):  # built: added 2026-11-02 v0.2.0
    pr = scene["prompt"]
    ctx = scene_context(p, scene)
    preset = PRESETS.get(cfg["preset"], PRESETS["h3_ref2va"])
    if pr["mode"] == "raw":
        before = pr["raw"]
        user = ("{}\n\nCurrent prompt:\n{}\n\nInstruction: {}\n\nReturn only the rewritten prompt text.").format(
            ctx, before, instruction or "Improve clarity and visual precision.")
        # [OLD 2026-11-02 v0.1.0->v0.2.0] text, _, _ = await chat(cfg, H3_RULES + "\n" + preset, user)
        text, _, _ = await chat(cfg, system_prompt(cfg, preset), user)
        text = re.sub(r"^```\w*\n|```$", "", text.strip()).strip()
        return {"raw": text, "warnings": preserved_warnings(before, text)}
    sections = pr["sections"]
    before = json.dumps(sections, ensure_ascii=False)
    # [OLD 2026-11-02 v0.1.0->v0.2.0] the model did not see what the editor adds around its sections
    # user = ("{}\n\nCurrent sections (JSON):\n{}\n\nInstruction: {}\n\n"
    #         "Return JSON with exactly these keys: subject_definitions, summary, retention_analysis, "
    #         "detailed_description, overall_soundscape, non_diegetic_music. Leave a key empty if it should stay empty. "
    #         "Shots and dialogue are added automatically from the timeline, so detailed_description only holds extra direction.").format(
    #     ctx, before, instruction or "Improve clarity and visual precision.")
    # text, _, _ = await chat(cfg, H3_RULES + "\n" + preset, user)
    # [/OLD]
    auto = pr["auto"]
    added = [x for x, on in (("the <Subject N>/<Picture N>/<Audio N> definition lines", auto.get("subjects")),
                             ("the retention lines for every reference", auto.get("retention")),
                             ("the [Shot N] lines with their cut times and the dialogue", auto.get("shots"))) if on]
    user = ("{}\n\nCurrent sections (JSON, written with @ tokens):\n{}\n\n{}Instruction: {}\n\n"
            "Return JSON with exactly these keys: subject_definitions, summary, retention_analysis, "
            "detailed_description, overall_soundscape, non_diegetic_music. Leave a key empty if it should stay empty. "
            "Do not repeat what the editor adds automatically: {}. In detailed_description write the one or two "
            "style sentences that open the description and any extra direction. Write overall_soundscape and "
            "non_diegetic_music as the guide describes.").format(
        ctx, before,
        ("What H3 currently receives for the first pass (labels already resolved):\n{}\n\n".format(built) if built else ""),
        instruction or "Improve clarity and visual precision, following the guide.", "; ".join(added) or "nothing")
    text, _, _ = await chat(cfg, system_prompt(cfg, preset), user)
    data = parse_json(text)
    out = {k: str(data.get(k, sections.get(k, "")) or "") for k in sections}
    return {"sections": out, "warnings": preserved_warnings(before, json.dumps(out, ensure_ascii=False))}


async def split(cfg, p, scene, passes, built_prompts):
    ranges = "\n".join("Pass {}: scene time {:.3f}s to {:.3f}s ({} frames, seam before: {})".format(
        x["index"], max(0.0, x["start"]), x["end"], x["gen_frames"], x["seam_before"]) for x in passes)
    user = ("{}\n\nThis scene is generated in {} passes:\n{}\n\nThe automatic per-pass prompts are:\n{}\n\n"
            "Rewrite one complete prompt per pass, in the six-section Ref2VA format of the guide. Inside each pass, "
            "cut times start at 00:00.000 and [Shot 1] has none. A pass after an "
            "'overlap' seam starts by continuing the previous pass, so open it as a continuation of the same shot. "
            "Return JSON: {{\"1\": \"...\", \"2\": \"...\"}}. Use @ tokens (not <Picture N>) for references.").format(
        scene_context(p, scene), len(passes), ranges,
        "\n\n".join("--- pass {} ---\n{}".format(i + 1, t) for i, t in enumerate(built_prompts)))
    # [OLD 2026-11-02 v0.1.0->v0.2.0] text, _, _ = await chat(cfg, H3_RULES + "\n" + PRESETS.get(cfg["preset"], ""), user)
    text, _, _ = await chat(cfg, system_prompt(cfg, PRESETS.get(cfg["preset"], "")), user)
    data = parse_json(text)
    return {str(k): str(v) for k, v in data.items() if str(k).isdigit()}


async def script_to_scenes(cfg, p, script):
    names = ", ".join(c["name"] for c in p["cast"]) or "(none yet)"
    user = ("Break this script into scenes for a video timeline. Existing cast: {}.\n\n"
            "Return JSON: {{\"cast\": [{{\"name\", \"kind\": \"character|location|prop\", \"description\", \"speaker\": \"S1\", \"language\"}}], "
            "\"scenes\": [{{\"title\", \"duration\": seconds (any length), \"summary\", \"soundscape\", \"music\", "
            "\"cast\": [names], \"shots\": [{{\"t\": seconds from scene start, \"camera\", \"text\"}}], "
            "\"dialogue\": [{{\"speaker\": name, \"t\": seconds, \"text\", \"language\", \"delivery\"}}]}}]}}.\n"
            "Give each speaking character a speaker id S1, S2... Leave timings realistic for the action and lines.\n\n"
            "Script:\n{}").format(names, script)
    # [OLD 2026-11-02 v0.1.0->v0.2.0] text, _, _ = await chat(cfg, H3_RULES, user, max_tokens=max(cfg["max_tokens"], 6000))
    text, _, _ = await chat(cfg, system_prompt(cfg), user, max_tokens=max(cfg["max_tokens"], 6000))
    data = parse_json(text)
    if not isinstance(data, dict):
        raise ValueError("The LLM did not return a JSON object")
    return {"scenes": list(data.get("scenes") or []), "cast": list(data.get("cast") or [])}


async def test(cfg):
    text, ms, model = await chat(cfg, "Reply with the single word OK.", "ping", max_tokens=8)
    return {"ok": True, "ms": ms, "model": model, "reply": text[:40]}


# ---- vision (added 2026-11-02 v0.2.0) ------------------------------------------------------

DESCRIBE_SYSTEM = """You describe reference media for MiniMax H3 video generation.
Answer with one or two English sentences that can follow "<Subject 1> is ..." in a subject definition, for
example: "the young woman with long dark hair, a blue cardigan and a thin silver necklace".
Describe only what is visible: appearance, clothing, colours, materials, layout and lighting. Do not guess names,
ages beyond what is obvious, or story. No preamble, no labels, no quotes."""


def image_part(data, mime="image/jpeg"):
    import base64
    return {"type": "image_url", "image_url": {"url": "data:{};base64,{}".format(mime, base64.b64encode(data).decode("ascii"))}}


async def describe(cfg, images, prompt):
    """images: list of (bytes, mime). Needs a vision-capable model."""
    if not images:
        raise ValueError("Nothing to describe")
    parts = [{"type": "text", "text": prompt or "Describe the main subject."}] + [image_part(d, m) for d, m in images]
    text, ms, model = await chat(cfg, DESCRIBE_SYSTEM, parts, max_tokens=400)
    text = text.strip().strip('"').strip()
    if not text:
        raise RuntimeError("The model returned no text. Is it a vision model?")
    return {"text": text, "ms": ms, "model": model}
