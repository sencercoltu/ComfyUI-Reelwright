"""OpenAI-compatible chat client and the prompt templates for rewrite, split and
script import. Every call is started by a button in the editor; nothing here
runs during a queue run.
"""

import json
import os
import re
import time

import asyncio  # added 2026-11-02 v0.3.0
import aiohttp

from .model import cast_description  # added 2026-11-02 v0.3.4
from .prompt import tidy_rewrite  # added 2026-11-03 v0.4.1
from .scriptparts import fit_scene  # added 2026-11-03 v0.4.3
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
    # [OLD 2026-11-02 v0.3.1->v0.3.2] no thinking switch
    # return {"base_url": base, "model": project_llm.get("model") or stored["model"], "api_key": stored["api_key"],
    #         "temperature": float(project_llm.get("temperature", 0.4)), "max_tokens": int(project_llm.get("max_tokens", 2048)),
    #         "preset": project_llm.get("preset", "h3_ref2va"), "include_guides": bool(project_llm.get("include_guides", True)),
    #         "guides": stored.get("guides") or {}}
    # [/OLD]
    # [OLD 2026-11-03 v0.4.1->v0.4.2] no limits
    # return {"base_url": base, "model": project_llm.get("model") or stored["model"], "api_key": stored["api_key"],
    #         "temperature": float(project_llm.get("temperature", 0.4)), "max_tokens": int(project_llm.get("max_tokens", 2048)),
    #         "preset": project_llm.get("preset", "h3_ref2va"), "include_guides": bool(project_llm.get("include_guides", True)),
    #         "guides": stored.get("guides") or {},
    #         "thinking": "off" if project_llm.get("thinking") == "off" else "auto"}  # added 2026-11-02 v0.3.2
    # [/OLD]
    cfg = {"base_url": base, "model": project_llm.get("model") or stored["model"], "api_key": stored["api_key"],
           "temperature": float(project_llm.get("temperature", 0.4)), "max_tokens": int(project_llm.get("max_tokens", 2048)),
           "preset": project_llm.get("preset", "h3_ref2va"), "include_guides": bool(project_llm.get("include_guides", True)),
           "guides": stored.get("guides") or {},
           "thinking": "off" if project_llm.get("thinking") == "off" else "auto"}  # added 2026-11-02 v0.3.2
    cfg.update(limits(project_llm))  # added 2026-11-03 v0.4.2
    return cfg


# added 2026-11-03 v0.4.2: tweakable limits (Global -> Prompt rewriter -> Limits)
def _num(v, default, lo, hi, kind=int):
    try:
        v = kind(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def limits(project_llm):
    timeout_s = _num(project_llm.get("timeout_s"), 120, 10, 3600)
    ctx = _num(project_llm.get("context_tokens"), 0, 0, 4_000_000)
    part = _num(project_llm.get("import_part_chars"), 3000, 0, 1_000_000)
    return {"timeout_s": timeout_s,
            "max_wait_s": max(timeout_s, _num(project_llm.get("max_wait_s"), 900, 30, 7200)),
            "retries": _num(project_llm.get("retries"), 2, 0, 5),
            "context_tokens": ctx if ctx >= 1024 else 0,
            "import_part_chars": part if part >= 500 else 0,
            "import_max_tokens": _num(project_llm.get("import_max_tokens"), 16384, 256, 1_000_000),
            "import_thinking": "off" if project_llm.get("import_thinking") == "off" else "same",
            "import_guides": bool(project_llm.get("import_guides", False))}


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


# added 2026-11-02 v0.3.2: a reply with no answer text, and why
class NoAnswer(RuntimeError):
    def __init__(self, message, reason):
        super().__init__(message)
        self.reason = reason  # "thinking_cut" | "cut" | "reasoning_only" | "empty"


def read_reply(data, max_tokens):
    """(answer, reasoning, finish_reason) from an OpenAI-style reply. Thinking models put their reasoning in
    `reasoning_content` (SGLang, vLLM, DeepSeek) or `reasoning` (newer vLLM, Ollama, OpenRouter), or inline in
    <think>…</think> when the server has no reasoning parser."""
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    if isinstance(text, list):  # some servers return content parts
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
    inline = re.findall(r"<think>(.*?)</think>", text, flags=re.S)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    # an unclosed <think> means the reply was cut off while still thinking
    if "<think>" in text:
        head, _, tail = text.partition("<think>")
        text, inline = head, inline + [tail]
    reasoning = (reasoning + "".join(inline)).strip()
    return text.strip(), reasoning, choice.get("finish_reason") or ""


def no_answer(reasoning, finish, max_tokens):
    if finish == "length" and reasoning:
        return NoAnswer("The model used all {} tokens thinking and stopped before it answered. Raise Max tokens, or set "
                        "Thinking to Off (Global → Prompt rewriter).".format(max_tokens), "thinking_cut")
    if finish == "length":
        return NoAnswer("The reply was cut off at {} tokens before any text. Raise Max tokens.".format(max_tokens), "cut")
    if reasoning:
        return NoAnswer("The model returned only its reasoning, no answer. Try Thinking: Off (Global → Prompt rewriter).",
                        "reasoning_only")
    return NoAnswer("The model returned no text.", "empty")


# [OLD 2026-11-02 v0.3.1->v0.3.2] ignored the reasoning field and finish_reason, so a thinking model that ran out of tokens
# looked like an empty answer ("Is it a vision model?")
# async def chat(cfg, system, user, max_tokens=None, timeout=None):
#     # `user` may be a list of OpenAI content parts (text + image_url) for vision models (added 2026-11-02 v0.2.0)
#     body = {"model": cfg["model"], "temperature": cfg["temperature"],
#             "max_tokens": max_tokens or cfg["max_tokens"],
#             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
#     t0 = time.time()
#     async with aiohttp.ClientSession(timeout=timeout or TIMEOUT) as s:
#         async with s.post(cfg["base_url"] + "/chat/completions", headers=_headers(cfg["api_key"]), json=body) as r:
#             data = await r.json(content_type=None)
#             if r.status >= 400:
#                 raise RuntimeError(_err(data, r.status))
#     text = data["choices"][0]["message"].get("content") or ""
#     # reasoning models may wrap their answer after a think block
#     text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
#     return text, int((time.time() - t0) * 1000), data.get("model", cfg["model"])
# [/OLD]
# [OLD 2026-11-03 v0.4.1->v0.4.2] one non-streaming request with a fixed 180 s total timeout. A long answer (a 46-scene script import)
# could take longer than that; the timeout surfaced as an empty error message, and a reply cut off at the token budget
# only showed up later as unreadable JSON.
# async def chat(cfg, system, user, max_tokens=None, timeout=None, require_text=True, info=None):
#     # `user` may be a list of OpenAI content parts (text + image_url) for vision models (added 2026-11-02 v0.2.0)
#     limit = max_tokens or cfg["max_tokens"]
#     body = {"model": cfg["model"], "temperature": cfg["temperature"], "max_tokens": limit,
#             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
#     if cfg.get("thinking") == "off":
#         # Qwen3-style chat templates (SGLang, vLLM) skip the think block with this
#         body["chat_template_kwargs"] = {"enable_thinking": False}
#     t0 = time.time()
#     async with aiohttp.ClientSession(timeout=timeout or TIMEOUT) as s:
#         async with s.post(cfg["base_url"] + "/chat/completions", headers=_headers(cfg["api_key"]), json=body) as r:
#             data = await r.json(content_type=None)
#             if r.status >= 400:
#                 raise RuntimeError(_err(data, r.status))
#     text, reasoning, finish = read_reply(data if isinstance(data, dict) else {}, limit)
#     if info is not None:
#         info.update(finish=finish, reasoning_chars=len(reasoning))
#     if not text and require_text:
#         raise no_answer(reasoning, finish, limit)
#     return text, int((time.time() - t0) * 1000), data.get("model", cfg["model"])
# [/OLD]


# ---- transport (added 2026-11-03 v0.4.2) ------------------------------------------------------

class LLMError(RuntimeError):
    """A request that failed on the way: reason is stall | gave_up | connect | server | http | context | cut | bad_json."""

    def __init__(self, message, reason, retry=True):
        super().__init__(message)
        self.reason = reason
        self.retry = retry


def estimate_tokens(content):
    """Rough prompt size: about 3.5 characters per token for English and JSON, about 1000 per picture."""
    if isinstance(content, list):
        return sum(estimate_tokens(p.get("text", "")) if p.get("type") == "text" else 1000
                   for p in content if isinstance(p, dict))
    return int(len(content or "") / 3.5) + 1


_SERVER_CONTEXT = {}  # (base_url, model) -> context window the server reported, or None


async def server_context(cfg):
    """The model's context window from GET /models (vLLM and SGLang: max_model_len), cached; None if unknown."""
    key = (cfg["base_url"], cfg.get("model") or "")
    if key in _SERVER_CONTEXT:
        return _SERVER_CONTEXT[key]
    found = None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get(cfg["base_url"] + "/models", headers=_headers(cfg["api_key"])) as r:
                data = await r.json(content_type=None) if r.status < 400 else {}
        models = [m for m in (data.get("data") or []) if isinstance(m, dict)] if isinstance(data, dict) else []
        pick = next((m for m in models if m.get("id") == cfg.get("model")), models[0] if models else {})
        for k in ("max_model_len", "context_length", "max_context_length", "context_window", "n_ctx"):
            if isinstance(pick.get(k), int) and pick[k] > 0:
                found = pick[k]
                break
    except Exception:
        found = None
    _SERVER_CONTEXT[key] = found
    return found


async def context_window(cfg):
    return cfg.get("context_tokens") or await server_context(cfg)


async def budget(cfg, system, user, want):
    """(max_tokens to ask for, estimated prompt tokens, context window or None). With a known context window the
    answer is capped so prompt + answer fit; a prompt that leaves less than 512 tokens is refused before sending."""
    est = estimate_tokens(system) + estimate_tokens(user) + 16
    ctx = await context_window(cfg)
    if not ctx:
        return want, est, None
    room = ctx - est - 64
    if room < min(want, 512):
        raise LLMError("The request is about {:,} tokens, but the model's context window is {:,} tokens. Lower Script part "
                       "size, turn off the H3 guides, or raise Context window (Global → Prompt rewriter → Limits)."
                       .format(est, ctx), "context", retry=False)
    return min(want, room), est, ctx


def _context_hint(message):
    low = message.lower()
    if any(x in low for x in ("context length", "context_length", "maximum context", "context window", "too many tokens",
                              "exceeds the model", "prompt is too long")):
        return message + " — lower Max tokens or Script part size, or set Context window (Global → Prompt rewriter → Limits)."
    return message


def _split_reasoning(content, reasoning):
    """Answer text without inline <think> blocks, and all the reasoning (same rules as read_reply)."""
    inline = re.findall(r"<think>(.*?)</think>", content, flags=re.S)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
    if "<think>" in content:
        head, _, tail = content.partition("<think>")
        content, inline = head, inline + [tail]
    return content.strip(), (reasoning + "".join(inline)).strip()


async def chat(cfg, system, user, max_tokens=None, timeout=None, require_text=True, info=None, progress=None):
    """Stream one chat completion. timeout: a fixed aiohttp timeout (Test connection); otherwise no data for
    cfg timeout_s seconds, or cfg max_wait_s in all, ends the request. progress(dict) gets the running counts about
    twice a second. Servers that ignore "stream" and answer with one JSON body work too."""
    # `user` may be a list of OpenAI content parts (text + image_url) for vision models (added 2026-11-02 v0.2.0)
    want = max_tokens or cfg["max_tokens"]
    if timeout is None:
        limit, est, ctx = await budget(cfg, system, user, want)
    else:
        limit, est, ctx = want, estimate_tokens(system) + estimate_tokens(user), None
    body = {"model": cfg["model"], "temperature": cfg["temperature"], "max_tokens": limit, "stream": True,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if cfg.get("thinking") == "off":
        # Qwen3-style chat templates (SGLang, vLLM) skip the think block with this
        body["chat_template_kwargs"] = {"enable_thinking": False}
    stall = cfg.get("timeout_s", 120)
    total = cfg.get("max_wait_s", 900)
    tmo = timeout or aiohttp.ClientTimeout(total=total, sock_connect=min(15, stall), sock_read=stall)
    t0 = time.time()
    state = {"tokens": 0, "reasoning": 0, "chars": 0, "last": 0.0}
    content, reasoning, finish, model = [], [], "", cfg["model"]

    def report(phase, force=False):
        now = time.time()
        if progress and (force or now - state["last"] >= 0.5):
            state["last"] = now
            progress({"phase": phase, "tokens": state["tokens"], "reasoning": state["reasoning"], "chars": state["chars"],
                      "elapsed": round(now - t0, 1), "budget": limit, "input": est, "context": ctx})

    report("waiting", force=True)
    try:
        async with aiohttp.ClientSession(timeout=tmo) as s:
            async with s.post(cfg["base_url"] + "/chat/completions", headers=_headers(cfg["api_key"]), json=body) as r:
                if r.status >= 400:
                    raw = await r.text()
                    try:
                        msg = _err(json.loads(raw), r.status)
                    except ValueError:
                        msg = raw.strip()[:300] or "HTTP {}".format(r.status)
                    raise LLMError(_context_hint(msg), "server" if r.status >= 500 else "http", retry=r.status >= 500)
                if "text/event-stream" not in (r.headers.get("Content-Type") or ""):
                    data = await r.json(content_type=None)
                    data = data if isinstance(data, dict) else {}
                    text, why, finish = read_reply(data, limit)
                    content, reasoning = [text], [why]
                    model = data.get("model") or model
                else:
                    async for raw in r.content:
                        line = raw.decode("utf-8", "replace").strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except ValueError:
                            continue
                        if not isinstance(chunk, dict):
                            continue
                        if chunk.get("error"):
                            raise LLMError(_context_hint(_err(chunk, 500)), "server")
                        model = chunk.get("model") or model
                        for choice in chunk.get("choices") or []:
                            delta = choice.get("delta") or choice.get("message") or {}
                            piece = delta.get("content") or ""
                            if isinstance(piece, list):
                                piece = "".join(x.get("text", "") for x in piece if isinstance(x, dict))
                            why = delta.get("reasoning_content") or delta.get("reasoning") or ""
                            if piece:
                                content.append(piece)
                                state["tokens"] += 1
                                state["chars"] += len(piece)
                            if why:
                                reasoning.append(why)
                                state["reasoning"] += 1
                            finish = choice.get("finish_reason") or finish
                        report("thinking" if state["reasoning"] and not state["chars"] else "writing")
    except asyncio.TimeoutError:
        if timeout is not None:
            raise
        took = time.time() - t0
        got = state["tokens"] + state["reasoning"]
        if took >= total - 1:
            raise LLMError("Gave up after {:.0f} s with about {:,} tokens received. Raise “Give up after”, or send less "
                           "at once (Global → Prompt rewriter → Limits).".format(took, got), "gave_up")
        raise LLMError(("No answer from {} for {} s" + (" after about {:,} tokens".format(got) if got else "") +
                        ". The server may be busy or still reading a long prompt; raise “Stall timeout” "
                        "(Global → Prompt rewriter → Limits).").format(cfg["base_url"], stall), "stall")
    except aiohttp.ClientConnectorError as e:
        if timeout is not None:
            raise
        raise LLMError("Cannot connect to {}: {}".format(cfg["base_url"], e.os_error or e), "connect")
    except (aiohttp.ClientPayloadError, aiohttp.ServerDisconnectedError) as e:
        raise LLMError("The server closed the connection after about {:,} tokens ({}).".format(
            state["tokens"] + state["reasoning"], e.__class__.__name__), "server")
    text, why = _split_reasoning("".join(content), "".join(reasoning))
    ms = int((time.time() - t0) * 1000)
    if info is not None:
        info.update(finish=finish, reasoning_chars=len(why), tokens=state["tokens"], ms=ms, budget=limit, input=est,
                    context=ctx)
    report("done", force=True)
    if not text and require_text:
        raise no_answer(why, finish, limit)
    return text, ms, model


async def ask(cfg, system, user, parse=None, max_tokens=None, progress=None, info=None, retry_cut=True):
    """chat() with cfg retries: a timeout, a dropped connection, a server error, an unreadable or cut-off answer are
    tried again. parse(text, info) turns the answer into the result and raises LLMError(reason "bad_json" or "cut")."""
    info = {} if info is None else info
    tries = cfg.get("retries", 2) + 1
    for attempt in range(1, tries + 1):
        info["attempt"] = attempt
        step = (lambda d, a=attempt: progress(dict(d, attempt=a, attempts=tries))) if progress else None
        try:
            text, ms, model = await chat(cfg, system, user, max_tokens=max_tokens, info=info, progress=step)
            return parse(text, info) if parse else text
        except (LLMError, NoAnswer) as e:
            again = getattr(e, "retry", True) and (retry_cut or e.reason not in ("cut", "thinking_cut"))
            if not again or attempt == tries:
                if attempt > 1:
                    e.args = (str(e) + " (tried {} times)".format(attempt),)
                raise
            if progress:
                progress({"phase": "retry", "attempt": attempt + 1, "attempts": tries, "note": str(e)})
            await asyncio.sleep(min(cfg.get("retry_wait", 2) * attempt, 6))  # retry_wait: tests use 0


def json_answer(text, info, what="answer"):
    """parse() for ask(): the JSON in an answer, with a clear reason when it was cut off or is not JSON."""
    try:
        return parse_json(text)
    except ValueError:
        if info.get("finish") == "length":
            raise LLMError("The {} was cut off at {:,} tokens before its JSON was complete. Raise the token budget "
                           "(Global → Prompt rewriter), or send less at once.".format(what, info.get("budget") or 0), "cut")
        raise LLMError("The {} was not valid JSON.".format(what), "bad_json")


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
            # [OLD 2026-11-02 v0.3.3->v0.3.4] the LLM saw the asset's name but not its description
            # refs.append("@{} {} ({}, {}{})".format(a["code"], a["name"] or a["file"], a["kind"], r["role"],
            #                                      ", at {:.2f}s".format(r["time"]) if r["role"] == "keyframe" else ""))
            desc = (a.get("description") or "").strip()
            refs.append("@{} {} ({}, {}{}){}".format(a["code"], a["name"] or a["file"], a["kind"], r["role"],
                                                   ", at {:.2f}s".format(r["time"]) if r["role"] == "keyframe" else "",
                                                   " - " + desc if desc else ""))
    people = []
    for e in scene["cast"]:
        c = cast.get(e["id"])
        if c:
            # [OLD 2026-11-02 v0.3.3->v0.3.4] people.append("@{} - {} ({}){}".format(c["name"] if " " not in c["name"] else "{" + c["name"] + "}",
            #                                       c["description"], c["kind"], ", speaker " + c["speaker"] if c["speaker"] else ""))
            people.append("@{} - {} ({}){}".format(c["name"] if " " not in c["name"] else "{" + c["name"] + "}",
                                                  cast_description(c, idx_assets)[0], c["kind"], ", speaker " + c["speaker"] if c["speaker"] else ""))
    shots = ["{:.2f}s {} | {}".format(float(s["t"]), s["camera"], s["text"]) for s in scene["shots"]]
    lines = ["{:.2f}s {}: <d>[{}] {}</d>".format(float(d["t"]), cast.get(d["speaker"], {}).get("name", "?"),
                                               d["language"], d["text"]) for d in scene["dialogue"]]
    return ("Scene: {title}, {dur:.2f} s.\nReferences:\n{refs}\nCast:\n{cast}\nShots:\n{shots}\nDialogue:\n{lines}".format(
        title=scene["title"], dur=float(scene["duration"]), refs="\n".join(refs) or "(none)",
        cast="\n".join(people) or "(none)", shots="\n".join(shots) or "(none)", lines="\n".join(lines) or "(none)"))


# [OLD 2026-11-03 v0.4.0->v0.4.1] async def rewrite(cfg, p, scene, instruction, built=""):  # built: added 2026-11-02 v0.2.0
# [OLD 2026-11-03 v0.4.1->v0.4.2] async def rewrite(cfg, p, scene, instruction, built="", tag_map=None):  # tag_map: added 2026-11-03 v0.4.1
async def rewrite(cfg, p, scene, instruction, built="", tag_map=None, progress=None):  # progress: added 2026-11-03 v0.4.2
    pr = scene["prompt"]
    ctx = scene_context(p, scene)
    preset = PRESETS.get(cfg["preset"], PRESETS["h3_ref2va"])
    if pr["mode"] == "raw":
        before = pr["raw"]
        user = ("{}\n\nCurrent prompt:\n{}\n\nInstruction: {}\n\nReturn only the rewritten prompt text.").format(
            ctx, before, instruction or "Improve clarity and visual precision.")
        # [OLD 2026-11-02 v0.1.0->v0.2.0] text, _, _ = await chat(cfg, H3_RULES + "\n" + preset, user)
        # [OLD 2026-11-03 v0.4.1->v0.4.2] text, _, _ = await chat(cfg, system_prompt(cfg, preset), user)
        text = await ask(cfg, system_prompt(cfg, preset), user, progress=progress)  # retries and limits
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
    # [OLD 2026-11-03 v0.4.1->v0.4.2] an unreadable or cut-off answer raised a bare JSON error
    # text, _, _ = await chat(cfg, system_prompt(cfg, preset), user)
    # data = parse_json(text)
    # [/OLD]
    data = await ask(cfg, system_prompt(cfg, preset), user, parse=lambda t, i: json_answer(t, i, "rewrite"),
                     progress=progress)
    # [OLD 2026-11-03 v0.4.0->v0.4.1] the reply was used as it came: repeated automatic parts, "<Subject 1>" instead of @Name, labels inside values
    # out = {k: str(data.get(k, sections.get(k, "")) or "") for k in sections}
    out = dict(sections, **tidy_rewrite(data if isinstance(data, dict) else {}, sections, auto, tag_map))  # added 2026-11-03 v0.4.1
    return {"sections": out, "warnings": preserved_warnings(before, json.dumps(out, ensure_ascii=False))}


# [OLD 2026-11-03 v0.4.1->v0.4.2] async def split(cfg, p, scene, passes, built_prompts):
async def split(cfg, p, scene, passes, built_prompts, progress=None):
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
    # [OLD 2026-11-03 v0.4.1->v0.4.2] text, _, _ = await chat(cfg, system_prompt(cfg, PRESETS.get(cfg["preset"], "")), user)
    # data = parse_json(text)
    # [/OLD]
    data = await ask(cfg, system_prompt(cfg, PRESETS.get(cfg["preset"], "")), user,
                     parse=lambda t, i: json_answer(t, i, "split"), progress=progress)
    if not isinstance(data, dict):
        raise LLMError("The split answer was not a JSON object.", "bad_json")
    return {str(k): str(v) for k, v in data.items() if str(k).isdigit()}


# [OLD 2026-11-03 v0.4.1->v0.4.2] the whole script in one request with max(Max tokens, 6000) tokens and the H3 guides: a long script's answer
# ran past the budget or the 180 s timeout (see script_part)
# async def script_to_scenes(cfg, p, script):
#     names = ", ".join(c["name"] for c in p["cast"]) or "(none yet)"
#     user = ("Break this script into scenes for a video timeline. Existing cast: {}.\n\n"
#             "Return JSON: {{\"cast\": [{{\"name\", \"kind\": \"character|location|prop\", \"description\", \"speaker\": \"S1\", \"language\"}}], "
#             "\"scenes\": [{{\"title\", \"duration\": seconds (any length), \"summary\", \"soundscape\", \"music\", "
#             "\"cast\": [names], \"shots\": [{{\"t\": seconds from scene start, \"camera\", \"text\"}}], "
#             "\"dialogue\": [{{\"speaker\": name, \"t\": seconds, \"text\", \"language\", \"delivery\"}}]}}]}}.\n"
#             "Give each speaking character a speaker id S1, S2... Leave timings realistic for the action and lines.\n\n"
#             "Script:\n{}").format(names, script)
#     # [OLD 2026-11-02 v0.1.0->v0.2.0] text, _, _ = await chat(cfg, H3_RULES, user, max_tokens=max(cfg["max_tokens"], 6000))
#     text, _, _ = await chat(cfg, system_prompt(cfg), user, max_tokens=max(cfg["max_tokens"], 6000))
#     data = parse_json(text)
#     if not isinstance(data, dict):
#         raise ValueError("The LLM did not return a JSON object")
#     return {"scenes": list(data.get("scenes") or []), "cast": list(data.get("cast") or [])}
# [/OLD]
async def script_to_scenes(cfg, p, script, progress=None):
    """The whole script as one part (the old request shape)."""
    return await script_part(cfg, p, script, progress=progress)


def import_cfg(cfg):
    """Import's own settings: thinking can be switched off for it, and the H3 guides are left out unless asked for."""
    c = dict(cfg, include_guides=bool(cfg.get("import_guides", False)))
    if cfg.get("import_thinking") == "off":
        c["thinking"] = "off"
    return c


def _cast_line(c):
    return "{} ({})".format(c.get("name", "?"), c.get("kind") or "character")


async def script_part(cfg, p, text, part=1, parts=1, notes="", known_cast=(), progress=None, retry_cut=True):
    """Scenes and cast for one part of a script (added 2026-11-03 v0.4.2). known_cast: cast proposed by earlier
    parts, so names stay the same across parts."""
    known = [_cast_line(c) for c in p["cast"]]
    seen = {c["name"].lower() for c in p["cast"]}
    for c in known_cast or ():
        if isinstance(c, dict) and c.get("name") and c["name"].lower() not in seen:
            seen.add(c["name"].lower())
            known.append(_cast_line(c))
    lines = ["Break this script into scenes for a video timeline. Existing cast (reuse these exact names): {}.".format(
        ", ".join(known) or "(none yet)")]
    if parts > 1:
        lines.append("This is part {} of {} of a longer script. Make scenes only from the text under \"Script part\"; "
                     "the other parts are imported separately. Keep the script's order and any numbering it uses."
                     .format(part, parts))
    if notes:
        lines.append("Notes from the start of the script (they apply to every part; do not make scenes from them):\n"
                     + notes)
    # [OLD 2026-11-03 v0.4.2->v0.4.3] shots had only a start time, and nothing tied them to the scene's length: a scene made of several
    # table rows came back 30 s long with shots starting up to 61.8 s
    # lines.append(
    #     "Return JSON: {\"cast\": [{\"name\", \"kind\": \"character|location|prop\", \"description\", \"speaker\": \"S1\", "
    #     "\"language\"}], \"scenes\": [{\"title\", \"duration\": seconds (any length), \"summary\", \"soundscape\", \"music\", "
    #     "\"cast\": [names], \"shots\": [{\"t\": seconds from scene start, \"camera\", \"text\"}], "
    #     "\"dialogue\": [{\"speaker\": name, \"t\": seconds, \"text\", \"language\", \"delivery\"}]}]}.\n"
    #     "In \"cast\" list only characters, locations and props that are not in the existing cast. Give each speaking "
    #     "character a speaker id S1, S2... Leave timings realistic for the action and lines; when the script gives "
    #     "durations or times, use them.")
    # [/OLD]
    lines.append(
        "Return JSON: {\"cast\": [{\"name\", \"kind\": \"character|location|prop\", \"description\", \"speaker\": \"S1\", "
        "\"language\"}], \"scenes\": [{\"title\", \"duration\": seconds (any length), \"summary\", \"soundscape\", \"music\", "
        "\"cast\": [names], \"shots\": [{\"t\": seconds from scene start, \"duration\": seconds, \"camera\", \"text\"}], "
        "\"dialogue\": [{\"speaker\": name, \"t\": seconds, \"text\", \"language\", \"delivery\"}]}]}.\n"
        "In \"cast\" list only characters, locations and props that are not in the existing cast. Give each speaking "
        "character a speaker id S1, S2... Every shot has a duration; a shot's t is the sum of the durations of the shots "
        "before it in the same scene, and the scene's duration is the sum of all its shot durations, so no shot starts "
        "after the scene ends. Leave timings realistic for the action and lines; when the script gives durations or "
        "times, use them (a scene made of several timed rows lasts as long as those rows together).")
    lines.append(("Script part:\n" if parts > 1 else "Script:\n") + text)
    user = "\n\n".join(lines)
    icfg = import_cfg(cfg)

    def parse(answer, info):
        data = json_answer(answer, info, "answer" if parts == 1 else "answer for part {}".format(part))
        if not isinstance(data, dict):
            raise LLMError("The answer was not a JSON object.", "bad_json")
        return data

    info = {}
    data = await ask(icfg, system_prompt(icfg), user, parse=parse, max_tokens=cfg.get("import_max_tokens", 16384),
                     progress=progress, info=info, retry_cut=retry_cut)
    # [OLD 2026-11-03 v0.4.2->v0.4.3] return {"scenes": [s for s in (data.get("scenes") or []) if isinstance(s, dict)],
    scenes = [s for s in (data.get("scenes") or []) if isinstance(s, dict)]
    for s in scenes:  # added 2026-11-03 v0.4.3: no shot or line after the scene's end
        note = fit_scene(s)
        if note:
            s["fit_note"] = note
    return {"scenes": scenes,
            "cast": [c for c in (data.get("cast") or []) if isinstance(c, dict)],
            "tokens": info.get("tokens", 0), "ms": info.get("ms", 0), "attempts": info.get("attempt", 1),
            "budget": info.get("budget"), "input": info.get("input"), "context": info.get("context")}


async def test(cfg):
    # [OLD 2026-11-02 v0.2.2->v0.3.0] waited up to 180 s, so an unreachable server looked like "nothing happens"
    # text, ms, model = await chat(cfg, "Reply with the single word OK.", "ping", max_tokens=8)
    # return {"ok": True, "ms": ms, "model": model, "reply": text[:40]}
    # [/OLD]
    info = {}  # added 2026-11-02 v0.3.2: report whether the model thinks first
    try:
        # [OLD 2026-11-02 v0.3.1->v0.3.2] an empty reply from a thinking model counted as a failure only later, in Describe
        # text, ms, model = await chat(cfg, "Reply with the single word OK.", "ping", max_tokens=16,
        #                              timeout=aiohttp.ClientTimeout(total=20, connect=6))
        text, ms, model = await chat(cfg, "Reply with the single word OK.", "ping", max_tokens=16,
                                     timeout=aiohttp.ClientTimeout(total=20, connect=6), require_text=False, info=info)
    except asyncio.TimeoutError:
        raise RuntimeError("No answer from {} within 20 s".format(cfg["base_url"]))
    except aiohttp.ClientConnectorError as e:
        raise RuntimeError("Cannot connect to {}: {}".format(cfg["base_url"], e.os_error or e))
    # [OLD 2026-11-02 v0.3.1->v0.3.2] return {"ok": True, "ms": ms, "model": model, "reply": text[:40], "base_url": cfg["base_url"]}
    thinking = info.get("reasoning_chars", 0) > 0
    # [OLD 2026-11-03 v0.4.1->v0.4.2] no context window in the answer
    # return {"ok": True, "ms": ms, "model": model, "reply": text[:40], "base_url": cfg["base_url"], "thinking": thinking,
    #         "note": ("This model thinks before it answers, so Describe, Rewrite, Split and Import get a bigger token budget. "
    #                  "Set Thinking to Off for faster answers.") if thinking and cfg.get("thinking") != "off" else ""}
    # [/OLD]
    _SERVER_CONTEXT.pop((cfg["base_url"], cfg.get("model") or ""), None)  # ask again on every test
    return {"ok": True, "ms": ms, "model": model, "reply": text[:40], "base_url": cfg["base_url"], "thinking": thinking,
            "context": await server_context(cfg),
            "note": ("This model thinks before it answers, so Describe, Rewrite, Split and Import get a bigger token budget. "
                     "Set Thinking to Off for faster answers.") if thinking and cfg.get("thinking") != "off" else ""}


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
    # [OLD 2026-11-02 v0.3.1->v0.3.2] 400 tokens: a thinking model often used them all on reasoning, which read as "no text"
    # text, ms, model = await chat(cfg, DESCRIBE_SYSTEM, parts, max_tokens=400)
    note = ""
    try:
        text, ms, model = await chat(cfg, DESCRIBE_SYSTEM, parts, max_tokens=describe_budget(cfg))
    except NoAnswer as e:
        if e.reason == "empty":
            raise RuntimeError("The model returned no text. Is it a vision model?")
        if cfg.get("thinking") == "off" or e.reason == "cut":
            raise
        # still thinking when the budget ran out: ask once more with thinking switched off
        try:
            text, ms, model = await chat(dict(cfg, thinking="off"), DESCRIBE_SYSTEM, parts, max_tokens=600)
        except Exception:
            raise e
        note = "The model kept thinking past the token budget, so this answer was made with thinking off."
    text = text.strip().strip('"').strip()
    if not text:
        raise RuntimeError("The model returned no text. Is it a vision model?")
    # [OLD 2026-11-02 v0.3.1->v0.3.2] return {"text": text, "ms": ms, "model": model}
    return {"text": text, "ms": ms, "model": model, "note": note}


def describe_budget(cfg):
    """The answer is two sentences; a thinking model needs room to reason first (added 2026-11-02 v0.3.2)."""
    return 600 if cfg.get("thinking") == "off" else max(int(cfg["max_tokens"]), 6000)
