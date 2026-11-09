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
from . import prompt as _prompt  # added 2026-11-03 v0.6.0: the editor's tag rule (prompt.tag_re), as_text, tag_token
from .scriptparts import fit_scene  # added 2026-11-03 v0.4.3
from .storage import read_json, write_json
from . import model as _model  # added 2026-11-05 v0.8.0: pass_texts / dialogue_seconds (Agent P), when present
from . import spec  # added 2026-11-05 v0.8.0: fmt_time, FPS for the per-pass requests
from .planner import plan_scene  # added 2026-11-05 v0.8.0: scene_builds (the passes a scene is made in)

TIMEOUT = aiohttp.ClientTimeout(total=180)
# [OLD 2026-11-03 v0.5.1->v0.6.0] TAG_RE = re.compile(r"@\{[^}]+\}|@[A-Za-z][\w-]*")  (preserved_warnings uses prompt.tag_re now)
DIALOGUE_RE = re.compile(r"<d>.*?</d>", re.S)
# added 2026-11-03 v0.6.0
HTML_PAGE = "the server sent a web page, not JSON — check the base URL (usually ends in /v1)"
CUT_RETRY_CAP = 32768  # a cut-off answer is asked again with twice the budget, up to this many tokens
RETRY_AFTER_MAX = 60   # a 429 asking to wait longer than this is not retried
# added 2026-11-05 v0.8.0: the import's default answer budget per part (was 16384). Since v0.8.0 every shot is 2-4
# sentences and the summary a note on the whole scene: a 3,000-character part of a shot table answers with about
# 7,000 tokens instead of 5,000, plus a thinking model's reasoning. model.py / model.js have the same default.
IMPORT_MAX_TOKENS = 24576

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
# [OLD 2026-11-09 v0.16.1->v0.17.0] H3_RULES: "- Keep shot markers like [Shot 2] and cut times like "At 00:05.000" unless asked to change them; cut times mark cuts and the first shot has none." (the times of spoken lines were not mentioned)
H3_RULES = """You write prompts for MiniMax H3 Ref2VA, a reference-to-video-with-audio model.
Rules you must follow:
- Keep every reference token exactly as written: @P1, @V2, @A1, @Name, @{Two Words}, @tail. Never invent new ones, never rename them. The editor turns them into <Subject N>, <Picture N>, <Video N> and <Audio N> labels later.
- Keep every dialogue span <d>[Language] ...</d> exactly as written, word for word.
- Keep shot markers like [Shot 2], cut times like "At 00:05.000, the shot cuts to" and the time that opens a spoken line or an action ("At 00:06.200, <Subject 1> (S1) says, ...") unless asked to change them; cut times mark cuts and the first shot has none.
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


# added 2026-11-03 v0.6.0: "localhost:8000/v1" used to fail inside aiohttp with an unreadable error
def normalize_base_url(url):
    """'localhost:8000/v1' -> 'http://localhost:8000/v1'; a pasted '.../v1/chat/completions' loses the endpoint; no
    trailing slash. Raises ValueError for another scheme."""
    base = str(url or "").strip().rstrip("/")
    if not base:
        return ""
    for tail in ("/chat/completions", "/completions", "/models"):
        if base.lower().endswith(tail):
            base = base[:-len(tail)].rstrip("/")
    scheme = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*)://", base)
    if not scheme:
        base = "http://" + base.lstrip("/")
    elif scheme.group(1).lower() not in ("http", "https"):
        raise ValueError("The LLM base URL must start with http:// or https:// (it is {})".format(base))
    return base


def resolve(project_llm, stored):
    """Project values win for URL/model; the key always comes from the user folder."""
    # [OLD 2026-11-03 v0.5.1->v0.6.0] base = (project_llm.get("base_url") or stored["base_url"] or "").rstrip("/")  (no scheme check)
    base = normalize_base_url(project_llm.get("base_url") or stored["base_url"] or "")
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
            # [OLD 2026-11-05 v0.7.0->v0.8.0] "import_max_tokens": _num(project_llm.get("import_max_tokens"), 16384, 256, 1_000_000),
            # added 2026-11-05 v0.8.0: 2-4 sentences per shot make an answer about 1.5 times as long (IMPORT_MAX_TOKENS)
            "import_max_tokens": _num(project_llm.get("import_max_tokens"), IMPORT_MAX_TOKENS, 256, 1_000_000),
            "import_thinking": "off" if project_llm.get("import_thinking") == "off" else "same",
            "import_guides": bool(project_llm.get("import_guides", False))}


def _headers(key):
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    return h


# [OLD 2026-11-03 v0.5.1->v0.6.0] a URL without http:// or a web page answer gave an unreadable error
# async def list_models(base_url, api_key):
#     async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
#         async with s.get(base_url.rstrip("/") + "/models", headers=_headers(api_key)) as r:
#             data = await r.json(content_type=None)
#             if r.status >= 400:
#                 raise RuntimeError(_err(data, r.status))
#     return sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))
# [/OLD]
async def list_models(base_url, api_key):
    base = normalize_base_url(base_url)
    if not base:
        raise ValueError("Set the LLM base URL in Global -> Prompt rewriter")
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
            async with s.get(base + "/models", headers=_headers(api_key)) as r:
                raw = await r.text()
                kind = r.headers.get("Content-Type") or ""
                status = r.status
    except aiohttp.ClientConnectorError as e:
        raise LLMError("Cannot connect to {}: {}".format(base, e.os_error or e), "connect")
    data = _json_or_page(raw, kind, status)
    if status >= 400:
        raise LLMError(_err(data, status), "http", retry=False)
    models = data.get("data", []) if isinstance(data, dict) else []
    return sorted(m.get("id", "") for m in models if isinstance(m, dict) and m.get("id"))


# added 2026-11-03 v0.6.0
def _looks_like_page(raw, content_type=""):
    head = (raw or "").lstrip()[:200].lower()
    return "text/html" in (content_type or "").lower() or head.startswith(("<!doctype", "<html", "<head", "<body"))


def _json_or_page(raw, content_type, status):
    """The JSON of an answer; a web page (wrong base URL) or other non-JSON text raises a readable LLMError."""
    if _looks_like_page(raw, content_type):
        raise LLMError("HTTP {}: {}.".format(status, HTML_PAGE) if status >= 400 else HTML_PAGE[0].upper() +
                       HTML_PAGE[1:] + ".", "html", retry=False)
    try:
        return json.loads(raw)
    except ValueError:
        text = " ".join((raw or "").split())[:200]
        raise LLMError("The server's answer is not JSON (HTTP {}){}".format(status, ": " + text if text else ""),
                       "http" if status >= 400 else "bad_json", retry=status >= 500)


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
    # [OLD 2026-11-03 v0.5.1->v0.6.0] a reply that starts inside the think block (the chat template opened <think>) kept its
    # reasoning as the answer; _split_reasoning handles that now
    # inline = re.findall(r"<think>(.*?)</think>", text, flags=re.S)
    # text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    # # an unclosed <think> means the reply was cut off while still thinking
    # if "<think>" in text:
    #     head, _, tail = text.partition("<think>")
    #     text, inline = head, inline + [tail]
    # reasoning = (reasoning + "".join(inline)).strip()
    # return text.strip(), reasoning, choice.get("finish_reason") or ""
    # [/OLD]
    text, reasoning = _split_reasoning(text if isinstance(text, str) else str(text), reasoning or "")
    return text, reasoning, choice.get("finish_reason") or ""


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
    """A request that failed on the way: reason is stall | gave_up | connect | server | http | context | cut | bad_json
    (v0.6.0: also busy (HTTP 429), html (a web page instead of JSON)). wait: seconds the server asked to wait."""

    # [OLD 2026-11-03 v0.5.1->v0.6.0] def __init__(self, message, reason, retry=True):
    def __init__(self, message, reason, retry=True, wait=None):
        super().__init__(message)
        self.reason = reason
        self.retry = retry
        self.wait = wait  # added 2026-11-03 v0.6.0


# added 2026-11-03 v0.6.0
CONTEXT_WORDS = ("context length", "context_length", "maximum context", "context window", "too many tokens",
                 "exceeds the model", "prompt is too long", "input is too long", "max_model_len", "too long for the model")


def is_context_error(message):
    low = (message or "").lower()
    return any(x in low for x in CONTEXT_WORDS)


def retry_after(value):
    """Seconds from a Retry-After header (a number or an HTTP date), or None."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
    except (TypeError, ValueError, IndexError):
        return None


def http_error(status, raw, content_type="", headers=None):
    # [OLD 2026-11-04 v0.6.0->v0.6.1] docstring: "429 is retried (after Retry-After), ..." (it left out RETRY_AFTER_MAX)
    """LLMError for an HTTP error answer: 429 is retried after Retry-After (ask() gives up at once when the server
    asks for more than RETRY_AFTER_MAX seconds, and says so), other 4xx are not, 5xx are; a context window error is
    never retried; a web page says the base URL is wrong. (docstring corrected 2026-11-04 v0.6.1)"""
    if _looks_like_page(raw, content_type):
        return LLMError("HTTP {}: {}.".format(status, HTML_PAGE), "html", retry=False)
    try:
        msg = _err(json.loads(raw), status)
    except ValueError:
        msg = (raw or "").strip()[:300] or "HTTP {}".format(status)
    if is_context_error(msg):
        return LLMError(_context_hint(msg), "context", retry=False)
    if status == 429:
        wait = retry_after((headers or {}).get("Retry-After"))
        return LLMError("The server is busy (HTTP 429: {}).".format(msg), "busy", retry=True, wait=wait)
    return LLMError(msg, "server" if status >= 500 else "http", retry=status >= 500)


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
    # [OLD 2026-11-03 v0.5.1->v0.6.0] the hint was appended to the server's words only
    # low = message.lower()
    # if any(x in low for x in ("context length", "context_length", "maximum context", "context window", "too many tokens",
    #                           "exceeds the model", "prompt is too long")):
    #     return message + " — lower Max tokens or Script part size, or set Context window (Global → Prompt rewriter → Limits)."
    # return message
    # [/OLD]
    if is_context_error(message):
        return ("The request does not fit in the model's context window ({}). Lower Max tokens or Script part size, "
                "turn off the H3 guides, or set Context window (Global → Prompt rewriter → Limits).".format(
                    message.strip().rstrip(".")))
    return message


def _split_reasoning(content, reasoning):
    """Answer text without inline <think> blocks, and all the reasoning (same rules as read_reply)."""
    # added 2026-11-03 v0.6.0: Qwen3-style templates open <think> in the prompt, so the reply has only "</think>":
    # everything before the first </think> that no <think> opened is reasoning
    close = content.find("</think>")
    if close >= 0 and "<think>" not in content[:close]:
        reasoning = (reasoning or "") + content[:close]
        content = content[close + len("</think>"):]
    inline = re.findall(r"<think>(.*?)</think>", content, flags=re.S)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
    if "<think>" in content:
        head, _, tail = content.partition("<think>")
        content, inline = head, inline + [tail]
    return content.strip(), (reasoning + "".join(inline)).strip()


# [OLD 2026-11-08 v0.12.0->v0.13.0] async def chat(cfg, system, user, max_tokens=None, timeout=None, require_text=True, info=None, progress=None):
# added 2026-11-08 v0.13.0: history (earlier turns of the Chat tab, [{role: user|assistant, content}], sent between the
# system prompt and `user`) and with_text (progress events carry the answer so far, "text", four times a second)
async def chat(cfg, system, user, max_tokens=None, timeout=None, require_text=True, info=None, progress=None, history=None,
               with_text=False):
    """Stream one chat completion. timeout: a fixed aiohttp timeout (Test connection); otherwise no data for
    cfg timeout_s seconds, or cfg max_wait_s in all, ends the request. progress(dict) gets the running counts about
    twice a second. Servers that ignore "stream" and answer with one JSON body work too."""
    # `user` may be a list of OpenAI content parts (text + image_url) for vision models (added 2026-11-02 v0.2.0)
    want = max_tokens or cfg["max_tokens"]
    history = [m for m in history or [] if isinstance(m, dict) and m.get("role") in ("user", "assistant")]  # v0.13.0
    counted = "\n".join([str(m.get("content") or "") for m in history] + [user]) if history else user  # v0.13.0
    if timeout is None:
        # [OLD 2026-11-08 v0.12.0->v0.13.0] limit, est, ctx = await budget(cfg, system, user, want)
        limit, est, ctx = await budget(cfg, system, counted, want)
    else:
        # [OLD 2026-11-08 v0.12.0->v0.13.0] limit, est, ctx = want, estimate_tokens(system) + estimate_tokens(user), None
        limit, est, ctx = want, estimate_tokens(system) + estimate_tokens(counted), None
    # [OLD 2026-11-08 v0.12.0->v0.13.0] body = {"model": cfg["model"], "temperature": cfg["temperature"], "max_tokens": limit, "stream": True,
    # [OLD 2026-11-08 v0.12.0->v0.13.0]         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    body = {"model": cfg["model"], "temperature": cfg["temperature"], "max_tokens": limit, "stream": True,
            "messages": [{"role": "system", "content": system}] +
                        [{"role": m["role"], "content": str(m.get("content") or "")} for m in history] +
                        [{"role": "user", "content": user}]}
    if cfg.get("thinking") == "off":
        # Qwen3-style chat templates (SGLang, vLLM) skip the think block with this
        body["chat_template_kwargs"] = {"enable_thinking": False}
    stall = cfg.get("timeout_s", 120)
    total = cfg.get("max_wait_s", 900)
    tmo = timeout or aiohttp.ClientTimeout(total=total, sock_connect=min(15, stall), sock_read=stall)
    t0 = time.time()
    state = {"tokens": 0, "reasoning": 0, "chars": 0, "last": 0.0}
    content, reasoning, finish, model = [], [], "", cfg["model"]
    # added 2026-11-09 v0.15.0: how much of the answer and of the reasoning the progress events have carried so far
    # (Sencer: "When waiting for response, we receive thinking, but cannot see what it thinks. Add the thinking progress
    # and received content as output so we can see what's going on")
    sent = {"text": 0, "think": 0, "text_n": 0, "think_n": 0}

    def report(phase, force=False):
        now = time.time()
        # [OLD 2026-11-08 v0.12.0->v0.13.0] if progress and (force or now - state["last"] >= 0.5):
        if progress and (force or now - state["last"] >= (0.25 if with_text else 0.5)):
            state["last"] = now
            # [OLD 2026-11-08 v0.12.0->v0.13.0] progress({"phase": phase, "tokens": state["tokens"], "reasoning": state["reasoning"], "chars": state["chars"],
            # [OLD 2026-11-08 v0.12.0->v0.13.0]           "elapsed": round(now - t0, 1), "budget": limit, "input": est, "context": ctx})
            d = {"phase": phase, "tokens": state["tokens"], "reasoning": state["reasoning"], "chars": state["chars"],
                 "elapsed": round(now - t0, 1), "budget": limit, "input": est, "context": ctx}
            if with_text:  # added 2026-11-08 v0.13.0: the answer so far (an inline <think> block shows as it comes)
                d["text"] = "".join(content)
            # added 2026-11-09 v0.15.0: what came since the last event: text_add (answer) at text_at, think_add
            # (reasoning) at think_at, character offsets in what this request received, so the editor can show the
            # reasoning and the answer as they arrive (llmjob.js jobStream) without the whole text in every event
            for k, parts in (("text", content), ("think", reasoning)):
                if len(parts) > sent[k + "_n"]:
                    add = "".join(parts[sent[k + "_n"]:])
                    d[k + "_at"], d[k + "_add"] = sent[k], add
                    # [OLD 2026-11-09 v0.17.0->v0.17.1] sent[k] += len(add)  (code points; the editor counts UTF-16 units, so after
                    # an emoji the popup cut the start of the next piece)
                    sent[k] += len(add.encode("utf-16-le")) // 2  # added 2026-11-09 v0.17.1: UTF-16 units, as JavaScript
                    sent[k + "_n"] = len(parts)
            progress(d)

    report("waiting", force=True)
    try:
        async with aiohttp.ClientSession(timeout=tmo) as s:
            async with s.post(cfg["base_url"] + "/chat/completions", headers=_headers(cfg["api_key"]), json=body) as r:
                if r.status >= 400:
                    raw = await r.text()
                    # [OLD 2026-11-03 v0.5.1->v0.6.0] 429 was not retried, a context error from a 5xx was, a web page showed as raw HTML
                    # try:
                    #     msg = _err(json.loads(raw), r.status)
                    # except ValueError:
                    #     msg = raw.strip()[:300] or "HTTP {}".format(r.status)
                    # raise LLMError(_context_hint(msg), "server" if r.status >= 500 else "http", retry=r.status >= 500)
                    # [/OLD]
                    raise http_error(r.status, raw, r.headers.get("Content-Type") or "", r.headers)
                if "text/event-stream" not in (r.headers.get("Content-Type") or ""):
                    # [OLD 2026-11-03 v0.5.1->v0.6.0] data = await r.json(content_type=None)  (a web page gave "Expecting value")
                    data = _json_or_page(await r.text(), r.headers.get("Content-Type") or "", r.status)
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
                            # [OLD 2026-11-03 v0.5.1->v0.6.0] raise LLMError(_context_hint(_err(chunk, 500)), "server")  (a context error was retried)
                            msg = _err(chunk, 500)
                            if is_context_error(msg):
                                raise LLMError(_context_hint(msg), "context", retry=False)
                            raise LLMError(msg, "server")
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


# added 2026-11-08 v0.13.0: the Chat tab (general questions to the configured LLM, not about a scene)
CHAT_SYSTEM = ("You are a helpful assistant inside Reelwright, a timeline editor in ComfyUI that makes films of any length "
               "with MiniMax H3 reference-to-video generation. Answer the user's questions directly and concisely, about "
               "anything they ask. Use Markdown for lists, tables and code.")
CHAT_MAX_CHARS = 400_000  # a whole conversation, as sent


async def chat_turn(cfg, messages, progress=None):
    """One answer of the Chat tab: messages [{role: "user"|"assistant", content}] (the last one the user's). Returns
    {reply, ms, model, tokens, reasoning (True when the model thought first)}. One attempt; the editor offers a retry."""
    info = {}
    text, ms, model = await chat(cfg, CHAT_SYSTEM, messages[-1]["content"], history=messages[:-1], info=info,
                                 progress=progress, with_text=True)
    return {"reply": text, "ms": ms, "model": model, "tokens": info.get("tokens", 0),
            "reasoning": bool(info.get("reasoning_chars"))}


async def ask(cfg, system, user, parse=None, max_tokens=None, progress=None, info=None, retry_cut=True):
    """chat() with cfg retries: a timeout, a dropped connection, a server error, an unreadable or cut-off answer are
    tried again. parse(text, info) turns the answer into the result and raises LLMError(reason "bad_json" or "cut")."""
    info = {} if info is None else info
    tries = cfg.get("retries", 2) + 1
    # [OLD 2026-11-03 v0.5.1->v0.6.0] a cut-off answer was asked again with the same budget; 429 was not retried
    # for attempt in range(1, tries + 1):
    #     info["attempt"] = attempt
    #     step = (lambda d, a=attempt: progress(dict(d, attempt=a, attempts=tries))) if progress else None
    #     try:
    #         text, ms, model = await chat(cfg, system, user, max_tokens=max_tokens, info=info, progress=step)
    #         return parse(text, info) if parse else text
    #     except (LLMError, NoAnswer) as e:
    #         again = getattr(e, "retry", True) and (retry_cut or e.reason not in ("cut", "thinking_cut"))
    #         if not again or attempt == tries:
    #             if attempt > 1:
    #                 e.args = (str(e) + " (tried {} times)".format(attempt),)
    #             raise
    #         if progress:
    #             progress({"phase": "retry", "attempt": attempt + 1, "attempts": tries, "note": str(e)})
    #         await asyncio.sleep(min(cfg.get("retry_wait", 2) * attempt, 6))  # retry_wait: tests use 0
    # [/OLD]
    want = max_tokens or cfg["max_tokens"]
    for attempt in range(1, tries + 1):
        info["attempt"] = attempt
        step = (lambda d, a=attempt: progress(dict(d, attempt=a, attempts=tries))) if progress else None
        try:
            text, ms, model = await chat(cfg, system, user, max_tokens=want, info=info, progress=step)
            return parse(text, info) if parse else text
        except (LLMError, NoAnswer) as e:
            again = getattr(e, "retry", True) and (retry_cut or e.reason not in ("cut", "thinking_cut"))
            note = ""
            # added 2026-11-03 v0.6.0: a cut-off answer is asked again with twice the budget, up to CUT_RETRY_CAP
            if again and e.reason in ("cut", "thinking_cut"):
                used = int(info.get("budget") or want)
                bigger = min(CUT_RETRY_CAP, used * 2)
                if used < want:  # the context window already capped the budget
                    again = False
                    note = " The model's context window leaves no room for a bigger answer."
                elif bigger <= used:
                    again = False
                    note = " It already had {:,} tokens.".format(used)
                else:
                    want = bigger
            # added 2026-11-03 v0.6.0: HTTP 429: wait as long as the server asks (Retry-After), else back off
            wait = min(cfg.get("retry_wait", 2) * attempt, 6)  # retry_wait: tests use 0
            if again and e.reason == "busy":
                wait = e.wait if getattr(e, "wait", None) is not None else min(cfg.get("retry_wait", 2) * 2 ** attempt, 30)
                if wait > RETRY_AFTER_MAX:
                    again = False
                    note = " It asks to wait {:.0f} s; try again later.".format(wait)
            if not again or attempt == tries:
                if attempt > 1 or note:
                    e.args = (str(e) + note + (" (tried {} times)".format(attempt) if attempt > 1 else ""),)
                raise
            if progress:
                progress({"phase": "retry", "attempt": attempt + 1, "attempts": tries, "note": str(e)})
            await asyncio.sleep(wait)


# added 2026-11-03 v0.6.0: a plain-text answer that stopped at the token limit is not used as it is
def _whole(what):
    """parse() for ask() with a text answer: refuses one cut off at the token budget (ask retries it bigger)."""
    def parse(text, info):
        if info.get("finish") == "length":
            raise LLMError("The {} was cut off at {:,} tokens before it was complete. Raise Max tokens (Global → Prompt "
                           "rewriter), or set Thinking to Off.".format(what, info.get("budget") or 0), "cut")
        return text
    return parse


# [OLD 2026-11-03 v0.6.0 review] def json_answer(text, info, what="answer"):
def json_answer(text, info, what="answer", expect=None):
    """parse() for ask(): the JSON in an answer, with a clear reason when it was cut off or is not JSON.
    added 2026-11-03 v0.6.0 review: expect (dict or list) is the type the task asks for, see parse_json."""
    try:
        # [OLD 2026-11-03 v0.6.0 review] return parse_json(text)
        return parse_json(text, expect)  # added 2026-11-03 v0.6.0 review
    except ValueError:
        if info.get("finish") == "length":
            raise LLMError("The {} was cut off at {:,} tokens before its JSON was complete. Raise the token budget "
                           "(Global → Prompt rewriter), or send less at once.".format(what, info.get("budget") or 0), "cut")
        raise LLMError("The {} was not valid JSON.".format(what), "bad_json")


# [OLD 2026-11-03 v0.5.1->v0.6.0] text after the JSON that held a "}" or a trailing comma made the whole answer unreadable
# def parse_json(text):
#     m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
#     if m:
#         text = m.group(1)
#     start = min([i for i in (text.find("{"), text.find("[")) if i >= 0] or [0])
#     end = max(text.rfind("}"), text.rfind("]"))
#     return json.loads(text[start:end + 1])
# [/OLD]
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")
_SMART_QUOTES = str.maketrans({"“": '"', "”": '"'})


# [OLD 2026-11-03 v0.6.0 review] the first value from the first { or [ won: "Here are the prompts for passes [1, 2]:"
# before the answer made the answer [1, 2]
# def parse_json(text):
#     """The JSON value in an LLM answer (added 2026-11-03 v0.6.0: tolerant). Tries, in order: a ```json fence, the first
#     complete value from the first { or [ (text after it is ignored), the same with trailing commas removed and curly
#     quotes made straight, and a Python-style literal (single quotes, True/None). Raises ValueError."""
#     text = text or ""
#     m = re.search(r"```(?:json|JSON)?\s*(.*?)```", text, re.S)
#     candidates = [m.group(1)] if m else []
#     candidates.append(text)
#     decoder = json.JSONDecoder()
#     for body in candidates:
#         starts = sorted(i for i in (body.find("{"), body.find("[")) if i >= 0)
#         for start in starts:
#             for fix in (lambda t: t, lambda t: _TRAILING_COMMA.sub(r"\1", t),
#                         lambda t: _TRAILING_COMMA.sub(r"\1", t.translate(_SMART_QUOTES))):
#                 try:
#                     return decoder.raw_decode(fix(body[start:]))[0]
#                 except ValueError:
#                     pass
#             end = max(body.rfind("}"), body.rfind("]"))
#             if end > start:
#                 try:
#                     import ast
#                     value = ast.literal_eval(body[start:end + 1])
#                     if isinstance(value, (dict, list)):
#                         return json.loads(json.dumps(value))
#                 except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
#                     pass
#     return json.loads(text)  # raises with the parser's own message
# [/OLD]
_JSON_START = re.compile(r"[{\[]")
_MAX_JSON_STARTS = 2000  # added 2026-11-03 v0.6.0 review: positions tried per text (an answer full of brackets)


def _json_values(body):
    """added 2026-11-03 v0.6.0 review: every JSON value in `body`, left to right, each one found after the end of the
    one before (so the objects inside a value are not values of their own). A value may need its trailing commas
    removed or its curly quotes made straight, or be a Python-style literal."""
    import bisect
    decoder = json.JSONDecoder()
    smart = body.translate(_SMART_QUOTES)  # same length, same places
    removed = [c.start() for c in _TRAILING_COMMA.finditer(body)]  # commas the fix takes out (same in `smart`)
    at_fixed = [r - k for k, r in enumerate(removed)]  # where the text after each one lands in the fixed text
    variants = [(body, False), (_TRAILING_COMMA.sub(r"\1", body), True), (smart, False),
                (_TRAILING_COMMA.sub(r"\1", smart), True)]
    values, pos, tries, py_tried = [], 0, 0, set()
    while tries < _MAX_JSON_STARTS:
        m = _JSON_START.search(body, pos)
        if not m:
            break
        start, tries = m.start(), tries + 1
        found = None
        for src, fixed in variants:
            i = start - bisect.bisect_left(removed, start) if fixed else start
            try:
                value, end = decoder.raw_decode(src, i)
            except ValueError:
                continue
            if fixed:  # back to a place in `body`
                end += bisect.bisect_right(at_fixed, end)
            found = (value, end)
            break
        if not found and m.group(0) not in py_tried:
            # a Python-style literal (single quotes, True/None), tried from the first { and the first [ that are not
            # JSON, up to the last } or ] of the text (as before v0.6.0 review)
            py_tried.add(m.group(0))
            last = max(body.rfind("}"), body.rfind("]"))
            if last > start:
                try:
                    import ast
                    value = ast.literal_eval(body[start:last + 1])
                    if isinstance(value, (dict, list)):
                        found = (json.loads(json.dumps(value)), last + 1)
                except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
                    pass
        if found:
            values.append(found[0])
            pos = max(start + 1, found[1])
        else:
            pos = start + 1
    return values


def parse_json(text, expect=None):
    """The JSON value in an LLM answer (added 2026-11-03 v0.6.0: tolerant). Looks in a ```json fence first, then in
    the whole text; a value may need trailing commas removed or curly quotes made straight, or be a Python-style
    literal (single quotes, True/None). Raises ValueError.
    added 2026-11-03 v0.6.0 review: every JSON value in the text is read, not only the first. A value of the type
    the task expects (`expect`: dict or list) wins over the others, and a value with more JSON (of that type) after
    it is skipped, so "Here are the prompts for passes [1, 2]:" before the answer is not the answer. Without a value
    of the expected type, the last value is used."""
    text = text or ""
    m = re.search(r"```(?:json|JSON)?\s*(.*?)```", text, re.S)
    candidates = [m.group(1)] if m else []
    candidates.append(text)
    fallback = []
    for body in candidates:
        values = _json_values(body)
        typed = [v for v in values if expect is None or isinstance(v, expect)]
        if typed:
            return typed[-1]
        if values and not fallback:
            fallback = [values[-1]]
    if fallback:
        return fallback[0]
    return json.loads(text)  # raises with the parser's own message


def preserved_warnings(before, after):
    """Tokens and dialogue lines that the model changed or dropped."""
    warnings = []
    # [OLD 2026-11-03 v0.5.1->v0.6.0] missing = sorted(set(TAG_RE.findall(before)) - set(TAG_RE.findall(after)))
    # [OLD 2026-11-03 v0.5.1->v0.6.0] added = sorted(set(TAG_RE.findall(after)) - set(TAG_RE.findall(before)))
    tags = lambda t: {m.group(0) for m in _prompt.tag_re().finditer(t or "")}  # same rule as the editor (v0.6.0)
    missing = sorted(tags(before) - tags(after))
    added = sorted(tags(after) - tags(before))
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
    tokens = _model.ref_tokens(p, scene) if hasattr(_model, "ref_tokens") else {}  # added 2026-11-08 v0.14.0
    refs = []
    for r in scene["refs"]:
        a = idx_assets.get(r["asset"])
        if a:
            # [OLD 2026-11-02 v0.3.3->v0.3.4] the LLM saw the asset's name but not its description
            # refs.append("@{} {} ({}, {}{})".format(a["code"], a["name"] or a["file"], a["kind"], r["role"],
            #                                      ", at {:.2f}s".format(r["time"]) if r["role"] == "keyframe" else ""))
            desc = (a.get("description") or "").strip()
            # [OLD 2026-11-08 v0.11.0->v0.12.0] refs.append("@{} {} ({}, {}{}){}".format(a["code"], a["name"] or a["file"], a["kind"], r["role"],
            # [OLD 2026-11-08 v0.11.0->v0.12.0]                                        ", at {:.2f}s".format(r["time"]) if r["role"] == "keyframe" else "",
            # [OLD 2026-11-08 v0.11.0->v0.12.0]                                        " - " + desc if desc else ""))
            # added 2026-11-08 v0.12.0: a pose reference says whose pose it is, and that only the pose is used
            role = r["role"]
            if role == "pose":
                who = cast.get(r.get("cast") or "")
                role = "pose for {}: only the body pose is used, the person in it does not appear".format(
                    _prompt.tag_token(who["name"]) if who else "nobody yet")
            # [OLD 2026-11-08 v0.13.1->v0.14.0] refs.append("@{} {} ({}, {}{}){}".format(a["code"], a["name"] or a["file"], a["kind"], role,
            # [OLD 2026-11-08 v0.13.1->v0.14.0]                                        ", at {:.2f}s".format(r["time"]) if r["role"] in ("keyframe", "pose") else "",
            # [OLD 2026-11-08 v0.13.1->v0.14.0]                                        " - " + desc if desc else ""))
            # added 2026-11-08 v0.14.0: a video or audio reference names its clip (@V1.2 for the second one of V1) and
            # whether a video's own sound goes with it
            tok = tokens.get(r["id"], "@" + a["code"])
            clip = ""
            if a["kind"] in ("video", "audio") and r["role"] == "reference" and hasattr(_model, "ref_clip"):
                c = _model.ref_clip(r, a)
                if _model.ref_trimmed(r):
                    clip = ", the part from {} to {} of the file".format(
                        spec.fmt_time(c["start"]), spec.fmt_time(c["end"]) if c["end"] is not None else "its end")
                if a["kind"] == "video":
                    clip += ", with its own sound" if r.get("soundtrack") else ", picture only"
            refs.append("{} {} ({}, {}{}{}){}".format(tok, a["name"] or a["file"], a["kind"], role,
                                                    ", at {:.2f}s".format(r["time"]) if r["role"] in ("keyframe", "pose") else "",
                                                    clip, " - " + desc if desc else ""))
    people = []
    for e in scene["cast"]:
        c = cast.get(e["id"])
        if c:
            # [OLD 2026-11-02 v0.3.3->v0.3.4] people.append("@{} - {} ({}){}".format(c["name"] if " " not in c["name"] else "{" + c["name"] + "}",
            #                                       c["description"], c["kind"], ", speaker " + c["speaker"] if c["speaker"] else ""))
            # [OLD 2026-11-03 v0.5.1->v0.6.0] people.append("@{} - {} ({}){}".format(c["name"] if " " not in c["name"] else "{" + c["name"] + "}",
            #                                       cast_description(c, idx_assets)[0], c["kind"], ", speaker " + c["speaker"] if c["speaker"] else ""))
            # [OLD 2026-11-08 v0.10.3->v0.11.0] people.append("{} - {} ({}){}".format(_prompt.tag_token(c["name"]), cast_description(c, idx_assets)[0],
            # [OLD 2026-11-08 v0.10.3->v0.11.0]                                     c["kind"], ", speaker " + c["speaker"] if c["speaker"] else ""))
            # added 2026-11-08 v0.11.0: a prop that is part of a character is said to be so (not a separate thing)
            owner = cast.get(_model.part_owner(c, cast)) if hasattr(_model, "part_owner") else None
            kind = "part of {}'s body or look, not a separate person or object".format(
                _prompt.tag_token(owner["name"])) if owner else c["kind"]
            people.append("{} - {} ({}){}".format(_prompt.tag_token(c["name"]), cast_description(c, idx_assets)[0],
                                                kind, ", speaker " + c["speaker"] if c["speaker"] else ""))
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
        # [OLD 2026-11-03 v0.5.1->v0.6.0] text = await ask(cfg, system_prompt(cfg, preset), user, progress=progress)  (a cut-off answer was accepted)
        text = await ask(cfg, system_prompt(cfg, preset), user, parse=_whole("rewrite"), progress=progress)
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
    # added 2026-11-09 v0.14.2: a scene made in one pass with no shots is written as its [Shot 1] line with its spoken
    # lines, which the editor puts on the timeline (fills_timeline, web/rw/shotfill.js)
    i = next((n for n, x in enumerate(p["scenes"]) if x["id"] == scene["id"]), None)
    fill = bool(auto.get("shots")) and i is not None and fills_timeline(scene, plan_scene(p, scene, i))
    # [OLD 2026-11-09 v0.14.1->v0.14.2] added = [x for x, on in (("the <Subject N>/<Picture N>/<Audio N> definition lines", auto.get("subjects")),
    # [OLD 2026-11-09 v0.14.1->v0.14.2]                          ("the retention lines for every reference", auto.get("retention")),
    # [OLD 2026-11-09 v0.14.1->v0.14.2]                          ("the [Shot N] lines with their cut times and the dialogue", auto.get("shots"))) if on]
    added = [x for x, on in (("the <Subject N>/<Picture N>/<Audio N> definition lines", auto.get("subjects")),
                             ("the retention lines for every reference", auto.get("retention")),
                             ("the [Shot N] lines with their cut times and the dialogue", auto.get("shots") and not fill))
             if on]
    desc_rule = ("In detailed_description write the one or two style sentences that open the description and any extra "
                 "direction.")
    if fill:
        desc_rule = ("This scene has no shots on the timeline yet: in detailed_description write the one or two style "
                     "sentences, then the scene as one [Shot 1] line (composition, subject appearance and position, "
                     "environment and lighting, action, camera movement and sound){}. {}").format(
            ", with every spoken line of the scene, word for word" if scene.get("dialogue") else
            # [OLD 2026-11-09 v0.14.4->v0.15.0] "; when the summary or the instruction has someone speak, write those lines in it",
            "; when the summary, the brief or the instruction has someone speak, write those lines in it",
            # [OLD 2026-11-09 v0.14.2->v0.14.3] FILL_LINES_RULE)  (the camera move was not asked for in the guide's words)
            FILL_LINES_RULE + " " + FILL_CAMERA_RULE)  # FILL_CAMERA_RULE: added 2026-11-09 v0.14.3
    # [OLD 2026-11-09 v0.14.1->v0.14.2] the description rule was always the style sentences
    # user = ("{}\n\nCurrent sections (JSON, written with @ tokens):\n{}\n\n{}Instruction: {}\n\n"
    #         "Return JSON with exactly these keys: subject_definitions, summary, retention_analysis, "
    #         "detailed_description, overall_soundscape, non_diegetic_music. Leave a key empty if it should stay empty. "
    #         "Do not repeat what the editor adds automatically: {}. In detailed_description write the one or two "
    #         "style sentences that open the description and any extra direction. Write overall_soundscape and "
    #         "non_diegetic_music as the guide describes.").format(
    #     ctx, before,
    #     ("What H3 currently receives for the first pass (labels already resolved):\n{}\n\n".format(built) if built else ""),
    #     instruction or "Improve clarity and visual precision, following the guide.", "; ".join(added) or "nothing")
    # [/OLD]
    # [OLD 2026-11-09 v0.14.4->v0.15.0] no brief
    # user = ("{}\n\nCurrent sections (JSON, written with @ tokens):\n{}\n\n{}Instruction: {}\n\n"
    #         "Return JSON with exactly these keys: subject_definitions, summary, retention_analysis, "
    #         "detailed_description, overall_soundscape, non_diegetic_music. Leave a key empty if it should stay empty. "
    #         "Do not repeat what the editor adds automatically: {}. {} Write overall_soundscape and "
    #         "non_diegetic_music as the guide describes.").format(
    #     ctx, before,
    #     ("What H3 currently receives for the first pass (labels already resolved):\n{}\n\n".format(built) if built else ""),
    #     instruction or "Improve clarity and visual precision, following the guide.", "; ".join(added) or "nothing",
    #     desc_rule)
    # [/OLD]
    user = ("{}\n\nCurrent sections (JSON, written with @ tokens):\n{}\n\n{}{}Instruction: {}\n\n"
            "Return JSON with exactly these keys: subject_definitions, summary, retention_analysis, "
            "detailed_description, overall_soundscape, non_diegetic_music. Leave a key empty if it should stay empty. "
            "Do not repeat what the editor adds automatically: {}. {} Write overall_soundscape and "
            "non_diegetic_music as the guide describes.").format(
        ctx, before,
        ("What H3 currently receives for the first pass (labels already resolved):\n{}\n\n".format(built) if built else ""),
        # added 2026-11-09 v0.15.0: the author's brief (brief_text)
        (BRIEF_HEAD + brief_text(scene) + "\n\n" if brief_text(scene) else ""),
        instruction or "Improve clarity and visual precision, following the guide.", "; ".join(added) or "nothing",
        desc_rule)
    # [OLD 2026-11-03 v0.4.1->v0.4.2] an unreadable or cut-off answer raised a bare JSON error
    # text, _, _ = await chat(cfg, system_prompt(cfg, preset), user)
    # data = parse_json(text)
    # [/OLD]
    # [OLD 2026-11-03 v0.6.0 review] data = await ask(cfg, system_prompt(cfg, preset), user, parse=lambda t, i: json_answer(t, i, "rewrite"),
    # [OLD 2026-11-03 v0.6.0 review]                  progress=progress)
    # added 2026-11-03 v0.6.0 review: the rewrite is an object
    data = await ask(cfg, system_prompt(cfg, preset), user, parse=lambda t, i: json_answer(t, i, "rewrite", dict),
                     progress=progress)
    # [OLD 2026-11-03 v0.4.0->v0.4.1] the reply was used as it came: repeated automatic parts, "<Subject 1>" instead of @Name, labels inside values
    # out = {k: str(data.get(k, sections.get(k, "")) or "") for k in sections}
    # [OLD 2026-11-09 v0.14.1->v0.14.2] out = dict(sections, **tidy_rewrite(data if isinstance(data, dict) else {}, sections, auto, tag_map))  # added 2026-11-03 v0.4.1
    out = dict(sections, **tidy_rewrite(data if isinstance(data, dict) else {}, sections, auto, tag_map,
                                        new_shots=fill))  # new_shots: added 2026-11-09 v0.14.2
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
    # [OLD 2026-11-03 v0.6.0 review] data = await ask(cfg, system_prompt(cfg, PRESETS.get(cfg["preset"], "")), user,
    # [OLD 2026-11-03 v0.6.0 review]                  parse=lambda t, i: json_answer(t, i, "split"), progress=progress)
    # added 2026-11-03 v0.6.0 review: Split asks for an object ("passes [1, 2]" in a preface is not the answer)
    data = await ask(cfg, system_prompt(cfg, PRESETS.get(cfg["preset"], "")), user,
                     parse=lambda t, i: json_answer(t, i, "split", dict), progress=progress)
    # [OLD 2026-11-03 v0.5.1->v0.6.0] values went through str() (an object became a Python repr); "pass 2" or "02" keys were dropped
    # if not isinstance(data, dict):
    #     raise LLMError("The split answer was not a JSON object.", "bad_json")
    # return {str(k): str(v) for k, v in data.items() if str(k).isdigit()}
    # [/OLD]
    out = split_prompts(data, len(passes))
    if not out:
        raise LLMError("The split answer had no prompt for any of the {} passes.".format(len(passes)), "bad_json")
    return out


# added 2026-11-03 v0.6.0
_PASS_KEY = re.compile(r"^\s*(?:pass(?:es)?|part|p)?[\s_#:.-]*0*(\d+)\s*$", re.I)


def split_prompts(data, n_passes=0):
    """{"1": text, ...} from a Split answer: keys "2", "02", "pass 2", "Pass_2", "P2" all mean pass 2; a list counts
    from pass 1; {"passes": …} is unwrapped; values that are objects or lists become text (six sections in their
    labelled layout); passes past n_passes (when known) and empty prompts are left out."""
    if isinstance(data, dict) and len(data) == 1:
        (key, inner), = data.items()
        if isinstance(inner, (dict, list)) and str(key).strip().lower() in ("passes", "pass_prompts", "prompts", "split"):
            data = inner
    if isinstance(data, list):
        numbered = {}
        for i, v in enumerate(data):
            k = next((v[x] for x in ("pass", "index", "n") if isinstance(v, dict) and x in v), i + 1)
            numbered.setdefault(str(k), v)
        data = numbered
    if not isinstance(data, dict):
        raise LLMError("The split answer was not a JSON object.", "bad_json")
    out = {}
    for key, value in data.items():
        m = _PASS_KEY.match(str(key))
        if not m:
            continue
        n = int(m.group(1))
        if n < 1 or (n_passes and n > n_passes):
            continue
        if isinstance(value, dict) and not any(k in value for k in _prompt.REF2VA_SECTIONS):
            # {"index": 2, "prompt": "..."}-style objects
            value = next((value[k] for k in ("prompt", "text", "content") if k in value), value)
        text = _prompt.as_text(value).strip()
        if text:
            out.setdefault(str(n), text)
    return out


# ---- Write prompts: each pass's own six sections, one request per pass (added 2026-11-05 v0.8.0) ------------------
# Split (above) rewrites the whole prompt of every pass in one answer, as text that replaces the pass's prompt
# (scene.prompt.pass_prompts, edited by hand afterwards). write_passes asks for one pass at a time and returns the
# six sections, which the editor stores as scene.prompt.passes[k] = {start, end, sections}; prompt.build_pass sends a
# pass's own sections and falls back to the scene's shared ones. A pass prompt from Split still wins over them.

PASS_WORDS = (350, 500)        # detailed_description of a generation task (ref-en.txt 5.2)
PASS_WORDS_WARN = (300, 650)   # an answer outside this range gets a warning
PASS_MIN_TOKENS = 4096         # one pass answers with about 1,000-1,500 tokens
PASS_MIN_TOKENS_THINKING = 8192  # ... and a thinking model reasons before it

# [OLD 2026-11-09 v0.16.1->v0.17.0] PASS_RULES said: "Every spoken line of the pass appears exactly once, word for
# word, in the shot where it is spoken, after its speaker and speaker ID, for example: @Mara (S1) mutters, <d>[English]
# Almost home.</d>" (no time, no place in the action) and the Voices example had no time either
PASS_RULES = """How these requests work: H3 makes at most about 15 seconds per generation, so a longer scene is made \
in passes, one after another, and every pass gets its own prompt. Each request asks for the prompt of ONE pass:
- Write only what happens in this pass, from its first frame to its last, with its own shots and spoken lines. The \
pass before it is already written: continue the story from where it ends, without repeating it. The next pass is \
shown only so that this one leads into it; do not describe it.
- summary: one short paragraph about this pass only (its subjects, its shot flow and the roles of its references), \
not about the whole scene. Do not write the task-type prefix; the editor adds it.
- detailed_description: one or two English sentences on the visual style, then one [Shot N] line per shot of this \
pass, numbered from [Shot 1] inside the pass. [Shot 1] has no time; every later shot begins "At MM:SS.mmm, the shot \
cuts to" with its start time inside the pass, as listed. Describe each shot by composition, subject appearance and \
position in the frame, environment and lighting, action, camera movement (type, amplitude, speed) and sound. Write \
350-500 English words in detailed_description; when the pass is dense with dialogue, fit every spoken line first.
- Every spoken line of the pass appears exactly once, word for word, in the shot where it is spoken, at the place in \
the shot's action where it is spoken, as a sentence that opens with its time in the pass as listed, then its speaker \
and speaker ID, for example: At 00:03.200, @Mara (S1) mutters, <d>[English] Almost home.</d> An action that follows \
a spoken line in the same shot opens with its time too ("At 00:04.600, she pockets the key."). Speaker IDs (S1), (S2) \
follow the order in which voices are first heard in this pass. Write no other spoken words: never a line of the pass \
before or after, and never a line twice.
- When the request lists Voices, describe each speaker's voice at their first spoken line in this pass with those \
words, for example: At 00:03.200, @Mara (S1), with a husky low voice, mutters, <d>[English] Almost home.</d> The same \
voice in every pass keeps H3 from changing it.
- A pass that starts at an overlap seam continues the same shot: its [Shot 1] carries on seamlessly from the final \
frames of the pass before (@tail), without restarting the action or introducing the setting again.
- overall_soundscape: the ambience and physical sounds of this pass, no dialogue. non_diegetic_music: the score only \
the audience hears in this pass (carry on the scene's music), or N/A.
- Write references as the @ tokens listed (@Mara, @P1, @tail). Never write <Subject N>, <Picture N>, <Video N> or \
<Audio N> yourself: every pass numbers them differently, and the editor puts them in.
- Answer with one JSON object with exactly the keys subject_definitions, summary, retention_analysis, \
detailed_description, overall_soundscape, non_diegetic_music; every value is text."""

_CONTINUES_FROM = {
    "prev_scene_last": "the last frame of the scene before; [Shot 1] begins from it",
    "prev_scene_tail": "the end of the scene before; [Shot 1] continues seamlessly from its final frames",
    "prev_pass_tail": "the end of pass {prev}; [Shot 1] continues seamlessly from its final frames",
}
_LABEL_ORDER = {"Subject": 0, "Picture": 1, "Video": 2, "Audio": 3}
_LABEL = re.compile(r"<(Subject|Picture|Video|Audio) (\d+)>")
_SHOT_LOOSE = re.compile(r"\[\s*shot\s*(\d+)\s*\]", re.I)
_CUT_TIME = re.compile(r"^At\s+(\d{1,2}):(\d{2}(?:\.\d{1,3})?)(\s*,\s*)", re.I)
_EMPTY = ("n/a", "na", "none", "-")


def scene_builds(p, scene):
    """(plan, builds) of one scene of a normalised project: planner.plan_scene and prompt.build_pass, the same calls
    analysis.analyze makes, without hashing files or reading takes."""
    i = next(n for n, s in enumerate(p["scenes"]) if s["id"] == scene["id"])
    plan = plan_scene(p, scene, i)
    ctx = _prompt.prepare(p)
    return plan, [_prompt.build_pass(p, scene, i, plan, x, ctx=ctx) for x in plan["passes"]]


def pass_budget(cfg):
    """Answer budget of one pass: Max tokens, at least PASS_MIN_TOKENS (PASS_MIN_TOKENS_THINKING unless thinking is
    off). A cut-off answer is asked again with twice the budget (ask)."""
    floor = PASS_MIN_TOKENS if cfg.get("thinking") == "off" else PASS_MIN_TOKENS_THINKING
    return max(int(cfg.get("max_tokens") or 0), floor)


def _sections_of(value):
    """{section: text} of a dict, or of text with the six labels ("summary:\\n..."); {} when it has none."""
    if isinstance(value, dict):
        return {k: value[k] for k in _prompt.REF2VA_SECTIONS if k in value}
    if not isinstance(value, str):
        return {}
    found = list(_prompt.SECTION_LABEL.finditer(value))
    out = {}
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(value)
        out.setdefault(m.group(1), value[m.end():end].strip())
    return out


def stored_pass_texts(p, scene, plan):
    """[sections dict or {}] per current pass: the texts scene.prompt.passes holds for it. model.pass_texts (largest
    time overlap) when the model has it, else the stored entry with the same number whose range is the pass's."""
    fn = getattr(_model, "pass_texts", None)
    if fn is not None:
        try:
            texts = fn(p, scene, plan)
            texts = texts.get("texts") if isinstance(texts, dict) else texts
            if isinstance(texts, list):
                return [(t.get("sections") if isinstance(t.get("sections"), dict) else t) if isinstance(t, dict) else {}
                        for t in texts] + [{}] * (len(plan["passes"]) - len(texts))
        except (TypeError, KeyError, ValueError, AttributeError):
            pass
    stored = (scene.get("prompt") or {}).get("passes")
    stored = stored if isinstance(stored, list) else []
    out = []
    for k, x in enumerate(plan["passes"]):
        s = stored[k] if k < len(stored) and isinstance(stored[k], dict) else {}
        try:
            same = abs(float(s.get("start")) - float(x["start"])) <= 1.0 / spec.FPS and \
                abs(float(s.get("end")) - float(x["end"])) <= 1.0 / spec.FPS
        except (TypeError, ValueError):
            same = False
        out.append(s.get("sections") if same and isinstance(s.get("sections"), dict) else {})
    return out


def _clean_line(text):
    """A spoken line as the editor sends it: one line, ending with punctuation (prompt._dialogue_sentence)."""
    line = " ".join(str(text or "").split())
    if line and line[-1] not in ".!?…\"'":
        line += "."
    return line


def _speaker(p, d):
    c = next((c for c in p["cast"] if c["id"] == d.get("speaker")), None)
    return _prompt.tag_token(c["name"]) if c and str(c.get("name") or "").strip() else "an off-screen voice"


def _shot_camera(sh):
    """Camera words of a shot: framing, camera text, amplitude and speed (the v0.8.0 shot fields, when present)."""
    words = " · ".join(str(sh[k]).strip() for k in ("framing", "camera") if isinstance(sh.get(k), str) and sh[k].strip())
    how = ", ".join(x for x in ((sh.get("camera_amp") or "") and "{} amplitude".format(sh["camera_amp"]),
                                (sh.get("camera_speed") or "") and "{} speed".format(sh["camera_speed"])) if x)
    return (words + " ({})".format(how) if words else how) if how else words


def _last_shot(desc):
    """The last [Shot N] line of a detailed description, '' without one."""
    _, chunks = _prompt._chunks(desc or "", _prompt.SHOT_START)
    return chunks[-1][1] if chunks else ""


def _pass_lines(p, scene, x, prev_n):
    """(shot lines, dialogue lines) of a pass, with pass and scene times."""
    by_id = {s["id"]: s for s in scene["shots"]}
    shots, start, end = x["shots"], float(x["start"]), float(x["keep_out"])
    out = []
    for n, sh in enumerate(shots, 1):
        t0 = float(sh["t"])
        t1 = float(shots[n]["t"]) if n < len(shots) else max(end, t0)
        full = dict(by_id.get(sh.get("id"), {}), **sh)
        cam, text = _shot_camera(full), " ".join(str(full.get("text") or "").split())
        note = " - it continues the shot that is running at the end of pass {}".format(prev_n) \
            if sh.get("continuing") and prev_n else ""
        out.append("[Shot {}] {} to {} in the pass (scene {} to {}, {:.2f} s){}: {}".format(
            n, spec.fmt_time(t0), spec.fmt_time(t1), spec.fmt_time(start + t0), spec.fmt_time(start + t1), t1 - t0,
            note, " | ".join(v for v in (cam, text) if v) or "(no text)"))
    ids = _prompt.speaker_ids(x)
    seconds = getattr(_model, "dialogue_seconds", None)
    lines = []
    for d in x["dialogue"]:
        t = float(d["t"])
        n = _prompt._shot_index(shots, t) if shots else 1
        dur = ""
        if seconds is not None:
            try:
                dur = ", about {:.1f} s".format(float(seconds(d)))
            except (TypeError, ValueError, KeyError):
                dur = ""
        lines.append("{} in the pass (scene {}), in [Shot {}]{}: {} ({}) {}, <d>[{}] {}</d>".format(
            spec.fmt_time(t), spec.fmt_time(start + t), n, dur, _speaker(p, d), ids.get(d.get("speaker") or "", "S?"),
            (d.get("delivery") or "").strip() or "says", d.get("language") or "English", _clean_line(d.get("text"))))
    return out, lines


def _pass_refs(p, scene, b, k):
    """Lines that list what this pass sends: @ token -> label, @tail's meaning, the scene's tokens it does not send."""
    by_label = {}
    for key, label in (b.get("tag_map") or {}).items():
        if key.startswith("@"):
            by_label.setdefault(label, []).append(_prompt.tag_token(key[1:]))

    def order(label):
        m = _LABEL.fullmatch(label)
        return (_LABEL_ORDER.get(m.group(1), 9), int(m.group(2))) if m else (9, 0)
    cont = b.get("continuation") or {}
    sounds = {}  # <Video k> -> <Audio n> of its own sound
    for n, v in enumerate(b.get("videos") or [], 1):
        if isinstance(v, dict) and v.get("soundtrack") and v.get("audio_number"):
            sounds["<Video {}>".format(n)] = "<Audio {}>".format(v["audio_number"])
    out = []
    for label in sorted(by_label, key=order):
        tokens = list(dict.fromkeys(by_label[label]))
        line = "{} -> {}".format(", ".join(tokens), label)
        if cont and label == cont.get("label") and "@tail" in tokens:
            line += ": " + _CONTINUES_FROM.get(cont.get("source"), "the footage this pass continues from").format(
                prev=k - 1)
        if label in sounds:
            line += " (its own sound is sent as {}; write it as \"the sound of {}\")".format(sounds[label], tokens[0])
        out.append(line)
    sent = {_prompt.name_key(t[1:].strip("{}")) for ts in by_label.values() for t in ts}
    idx = {a["id"]: a for a in p["assets"]}
    cast = {c["id"]: c for c in p["cast"]}
    other = []
    for r in scene["refs"]:
        a = idx.get(r.get("asset"))
        if a and _prompt.name_key(a["code"]) not in sent:
            other.append("@" + a["code"])
    for e in scene["cast"]:
        c = cast.get(e.get("id"))
        if c and str(c.get("name") or "").strip() and _prompt.name_key(c["name"]) not in sent:
            other.append(_prompt.tag_token(c["name"]))
    return out, list(dict.fromkeys(other))


_GUIDE_PHRASE = {"first frame": "the shot begins from {}", "keyframe": "the shot's keyframe corresponds to {}",
                 "last frame": "the shot ends on {}"}  # ref-en.txt 5.3


def pass_guides(p, scene, x):
    """[(token, what, line)] for the first-frame, keyframe and last-frame references that guide pass x: they are sent
    to H3 as pictures (or clips) only when the pass's text names them (prompt.build_pass), so the request asks for it."""
    refs = {r["id"]: r for r in scene["refs"]}
    idx = {a["id"]: a for a in p["assets"]}
    out = []
    for key, what in (("first_frame", "first frame"), ("keyframes", "keyframe"), ("last_frame", "last frame")):
        for g in x.get(key) or []:
            r = refs.get(g.get("ref")) if isinstance(g, dict) else None
            a = idx.get(r.get("asset")) if r else None
            if not a:
                continue
            t = int(g.get("frame_idx") or 0) / spec.FPS
            n = _prompt._shot_index(x["shots"], t) if x["shots"] else 1
            token = "@" + a["code"]
            out.append((token, what, "{} is the {} at {} in the pass (scene {}), in [Shot {}]: name it in that shot, for "
                        "example \"{}\"".format(token, what, spec.fmt_time(t), spec.fmt_time(float(x["start"]) + t), n,
                                                _GUIDE_PHRASE[what].format(token))))
    return out


def _scene_tokens(p, scene, tag_map=None):
    """name_key of every @ name the scene can use: its references, its cast and their pictures and voices, @tail,
    @soundtrack, @song, and what the pass's tag_map holds."""
    idx = {a["id"]: a for a in p["assets"]}
    cast = {c["id"]: c for c in p["cast"]}
    keys = {"tail", "soundtrack", "song"}
    for r in scene["refs"]:
        if r.get("asset") in idx:
            keys.add(_prompt.name_key(idx[r["asset"]]["code"]))
    if hasattr(_model, "ref_tokens"):  # added 2026-11-08 v0.14.0: @V1.2 ...
        keys |= {_prompt.name_key(tok[1:]) for tok in _model.ref_tokens(p, scene).values()}
    for e in scene["cast"]:
        c = cast.get(e.get("id"))
        if not c:
            continue
        keys.add(_prompt.name_key(c.get("name")))
        assets = list(c.get("anchors") or []) + [c.get("voice")] + \
            [a for o in (c.get("outfits") or []) if isinstance(o, dict) for a in (o.get("assets") or [])]
        keys |= {_prompt.name_key(idx[a]["code"]) for a in assets if a in idx}
    keys |= {_prompt.name_key(k[1:]) for k in (tag_map or {}) if k.startswith("@")}
    return keys


# added 2026-11-06 v0.10.0
def pass_voices(p, x):
    """One line per cast member who speaks in pass x and has a voice description: "@Mara: with a husky low voice"
    (prompt.voice_phrase; nothing when Global -> Continuity -> describe_voices is off)."""
    cast = {c["id"]: c for c in p["cast"]}
    out, seen = [], set()
    for d in x.get("dialogue") or []:
        c = cast.get(d.get("speaker"))
        if not c or c["id"] in seen:
            continue
        seen.add(c["id"])
        v = _prompt.voice_phrase(p, c)
        if v:
            out.append("{}: {}".format(_speaker(p, d), v))
    return out


# added 2026-11-09 v0.14.2 (Sencer: "when creating a single shot scene, the shot section (and dialogues) are not
# populated"): a scene made in one pass with no shots on the timeline is written as [Shot N] lines with its spoken
# lines, and the editor puts them on the timeline (web/rw/shotfill.js). The request asks for every spoken line as a
# sentence of its own, so the editor can take it out of the shot's text, and, when the scene has no lines yet, lets
# the LLM write the lines the note calls for (tidy_pass keeps them: free_lines).
# [OLD 2026-11-09 v0.16.1->v0.17.0] FILL_LINES_RULE = ("Write every spoken line as a sentence of its own: the speaker's @name, the speaker ID and how they "
#                    "speak, then the line, for example: @Mara (S1) mutters, <d>[English] Almost home.</d> Describe the "
#                    "action in sentences of their own. The editor puts the shot and its spoken lines on the timeline.")
# added 2026-11-09 v0.17.0: each line (and each action after one) opens with its time, so the editor puts it on the
# timeline at that time and keeps its place in the shot (web/rw/shotfill.js)
FILL_LINES_RULE = ("Write every spoken line as a sentence of its own, where it is spoken in the shot's action, opening "
                   "with the time it is spoken in the pass: the time, the speaker's @name, the speaker ID and how they "
                   "speak, then the line, for example: At 00:03.200, @Mara (S1) mutters, <d>[English] Almost home.</d> "
                   "Describe the action in sentences of their own; an action that follows a spoken line in the same "
                   "shot opens with its time too (\"At 00:04.600, she pockets the key.\"). The editor puts the shot and "
                   "its spoken lines on the timeline at those times.")


def fills_timeline(scene, plan):
    """Is the scene written into the timeline (a structured prompt, one pass, no shots)?"""
    return (scene.get("prompt") or {}).get("mode") != "raw" and len(plan["passes"]) == 1 and not scene.get("shots")


# added 2026-11-09 v0.14.3 (Sencer: "camera movements are not reflected to shots when using Write prompts"): the
# editor also takes each written shot's framing and camera move into the shot's fields (web/rw/shotfill.js cameraOf),
# for a scene made in one pass with automatic shot lines, so the request asks for them in the words of H3's guide
FILL_CAMERA_RULE = ("Start each [Shot N] line with its framing, for example \"[Shot 1] A medium shot: ...\" (extreme "
                    "wide, wide, medium wide, medium, medium close-up, close-up, extreme close-up, over-the-shoulder, "
                    "two-shot, insert, low angle, high angle, overhead or Dutch angle), and write its camera movement "
                    "as a sentence of its own in the guide's words, with amplitude and speed when they matter, for "
                    "example \"The camera pushes in with small amplitude at slow speed.\" (the camera zooms in or out, "
                    "pushes in, pulls out, pans left or right, trucks left or right, tilts up or down, pedestals up or "
                    "down, arcs around the subject, tracks the moving subject, holds a static shot, shakes slightly or "
                    "strongly, takes the subject's point of view, rolls clockwise or counterclockwise). The editor puts "
                    "the framing and the camera move in the shot's fields.")


# [OLD 2026-11-09 v0.14.3->v0.14.4] only a scene made in one pass
# def writes_shots(scene, plan):
#     """Does the editor take the written shots into the scene's shots (fills_timeline, or a scene made in one pass
#     whose shot lines are automatic)?"""
#     pr = scene.get("prompt") or {}
#     return fills_timeline(scene, plan) or (pr.get("mode") != "raw" and len(plan["passes"]) == 1 and
#                                           bool((pr.get("auto") or {}).get("shots")))
# [/OLD]
def writes_shots(scene, plan):
    """Does the editor take the written shots into the scene's shots (fills_timeline, or a scene whose shot lines are
    automatic; added 2026-11-09 v0.14.4: in a scene of several passes too, web/rw/shotfill.js takePassShots)?"""
    pr = scene.get("prompt") or {}
    return fills_timeline(scene, plan) or (pr.get("mode") != "raw" and bool((pr.get("auto") or {}).get("shots")))


# added 2026-11-09 v0.15.0: scene.prompt.brief, the author's own words for Write prompts (the Prompt card's Brief).
# Nothing the LLM writes goes there, so it stays the same from one Write prompts to the next, unlike the summary.
BRIEF_HEAD = ("Author's brief for this scene (the author's own words; follow it, and where it and the whole-scene note "
              "disagree, the brief wins):\n")


def brief_text(scene):
    """added 2026-11-09 v0.15.0: the scene's Write prompts brief, stripped ("" when it has none)."""
    pr = scene.get("prompt") if isinstance(scene.get("prompt"), dict) else {}
    return str(pr.get("brief") or "").strip()


def pass_request(p, scene, plan, builds, k, written=None, stored=None, instruction=""):
    """The user message that asks for pass k (1-based) of a scene: the scene and cast (scene_context), the whole-scene
    note, this pass's range, shots and spoken lines in pass and scene time, the references it sends, the pass before
    (its summary and last shot: just written, written earlier, or as the editor builds it now) and the pass after
    (an outline), what H3 receives for the pass now, the instruction and the rules that depend on the scene."""
    written, stored = written or {}, stored or [{}] * len(plan["passes"])
    n = len(plan["passes"])
    x, b = plan["passes"][k - 1], builds[k - 1]
    pr = scene["prompt"]
    auto = pr.get("auto") or {}
    parts = ["The whole scene, for context (you write only pass {}):\n{}".format(k, scene_context(p, scene))]
    note = _prompt._strip_task_tags(str((pr.get("sections") or {}).get("summary") or "")).strip()
    parts.append("Whole-scene note (what the whole scene is about; not a prompt of its own):\n" + (note or "(none)"))
    if brief_text(scene):  # added 2026-11-09 v0.15.0: the author's Write prompts brief, kept between runs
        parts.append(BRIEF_HEAD + brief_text(scene))

    start, end, gen = float(x["start"]), float(x["end"]), int(x["gen_frames"])
    head = ("Write the prompt of pass {} of {}. It covers scene time {} to {} ({:.2f} s); H3 generates {} frames "
            "({:.2f} s) for it.".format(k, n, spec.fmt_time(max(0.0, start)), spec.fmt_time(end), end - max(0.0, start),
                                        gen, gen / spec.FPS) if n > 1 else
            "This scene is made in one pass; write its prompt. H3 generates {} frames ({:.2f} s) for it.".format(
                gen, gen / spec.FPS))
    if plan.get("kind") == "short":
        head += (" The scene is shorter than one pass: the cut keeps {} to {} of what H3 makes, and the times below are "
                 "times in what H3 makes.".format(spec.fmt_time(float(x["keep_in"])), spec.fmt_time(float(x["keep_out"]))))
    cont = b.get("continuation") or {}
    if x.get("seam_before") == "overlap":
        head += (" It starts at an overlap seam, in the middle of a shot: its first {:.2f} s repeat the end of pass {}, "
                 "and its [Shot 1] continues that shot seamlessly.".format(int(x.get("overlap_frames") or 0) / spec.FPS,
                                                                             k - 1))
    elif x.get("seam_before") == "cut":
        head += " It starts at a shot cut, with a new shot."
    elif cont.get("source") == "prev_scene_last" or (k == 1 and plan.get("start_mode") == "last_frame"):
        head += " It begins from the last frame of the scene before (@tail)."
    elif cont.get("source") == "prev_scene_tail" or (k == 1 and plan.get("start_mode") == "tail"):
        head += " It continues seamlessly from the end of the scene before (@tail)."
    shot_lines, spoken = _pass_lines(p, scene, x, k - 1 if k > 1 else 0)
    # [OLD 2026-11-09 v0.14.1->v0.14.2] a scene without shots or lines got no lines: the rules forbid other spoken words
    # parts.append(head + "\nIts shots:\n" + ("\n".join(shot_lines) or "(no shots on the timeline: write it as one shot)") +
    #              "\nIts spoken lines:\n" + ("\n".join(spoken) or "(none)"))
    # added 2026-11-09 v0.14.2: a scene written into the timeline (fills_timeline)
    fill = fills_timeline(scene, plan)
    free = fill and not scene.get("dialogue")
    parts.append(head + "\nIts shots:\n" + ("\n".join(shot_lines) or (
        "(none on the timeline yet: write it as one shot; the editor puts it on the timeline)" if fill else
        "(no shots on the timeline: write it as one shot)")) +
        "\nIts spoken lines:\n" + ("\n".join(spoken) or (
            # [OLD 2026-11-09 v0.14.4->v0.15.0] "(none on the timeline yet: when the whole-scene note or the instruction has someone speak, write those "
            # [OLD 2026-11-09 v0.14.4->v0.15.0] "lines, word for word as the note gives them, and only those; the editor puts them on the timeline)"
            # added 2026-11-09 v0.15.0: or the author's brief, when the scene has one
            "(none on the timeline yet: when the whole-scene note{} or the instruction has someone speak, write those "
            "lines, word for word as the note gives them, and only those; the editor puts them on the timeline)".format(
                ", the author's brief" if brief_text(scene) else "")
            if free else "(none)")))
    # added 2026-11-06 v0.10.0: how each speaker of this pass sounds (cast voice_desc), to describe at their first line
    voices = pass_voices(p, x)
    if voices:
        parts.append("Voices (describe each at the speaker's first line in this pass, in these words, so the voice "
                     "stays the same in every pass):\n" + "\n".join(voices))

    sent, not_sent = _pass_refs(p, scene, b, k)
    guides = pass_guides(p, scene, x)
    refs = "References this pass sends to H3 (write the @ token; the editor turns it into the label):\n" + \
        ("\n".join(sent) or "(none)")
    if guides:
        refs += "\nFrame guides of this pass (sent as pictures when the text names them):\n" + \
            "\n".join(g[2] for g in guides)
    not_sent = [t for t in not_sent if t not in {g[0] for g in guides}]
    if not_sent:
        refs += "\nNot sent with this pass (the editor writes them as words): " + ", ".join(not_sent)
    if b.get("tags"):
        refs += "\nTask types of this pass (the editor writes them before the summary): [{}]".format(
            " + ".join(b["tags"]))
    parts.append(refs)

    if k > 1:
        px = plan["passes"][k - 2]
        mine = written.get(k - 1) or {}
        theirs = stored[k - 2] if k - 2 < len(stored) and isinstance(stored[k - 2], dict) else {}
        secs, how = (mine, "was just written") if mine else (theirs, "was written earlier") if any(
            str(v or "").strip() for v in theirs.values()) else ({}, "has no text of its own yet")
        summary = _prompt._strip_task_tags(str(secs.get("summary") or "")).strip()
        last = _last_shot(str(secs.get("detailed_description") or ""))
        if not last:  # as H3 receives it now (labels resolved), else the timeline's last shot
            last = _last_shot(str(_sections_of(builds[k - 2].get("prompt") or "").get("detailed_description") or ""))
        if not last and px["shots"]:
            sh = px["shots"][-1]
            last = " | ".join(v for v in (sh.get("camera"), sh.get("text")) if v)
        block = ["The pass before (pass {}, scene {} to {}) {}. Continue the story from where it ends; do not repeat "
                 "it.".format(k - 1, spec.fmt_time(max(0.0, float(px["start"]))), spec.fmt_time(float(px["end"])), how)]
        if summary:
            block.append("Its summary: " + summary)
        block.append("Its last shot: " + (last or "(none)"))
        if px["dialogue"]:
            d = px["dialogue"][-1]
            # [OLD 2026-11-06 v0.9.0->v0.10.0] block.append("Its last spoken line: {} <d>[{}] {}</d>".format(_speaker(p, d), d.get("language") or "English",
            # [OLD 2026-11-06 v0.9.0->v0.10.0]                                                              _clean_line(d.get("text"))))
            # added 2026-11-06 v0.10.0: written as plain words, marked as already spoken (answers copied it, and H3
            # said it again)
            block.append('Its last spoken line (already spoken in pass {}; never write it again): {}: "{}"'.format(
                k - 1, _speaker(p, d), _clean_line(d.get("text"))))
        parts.append("\n".join(block))
    if k < n:
        nx = plan["passes"][k]
        nstart = float(nx["start"])
        block = ["The pass after (pass {}, scene {} to {}), only so this pass leads into it; do not describe it:".format(
            k + 1, spec.fmt_time(nstart), spec.fmt_time(float(nx["end"])))]
        theirs = stored[k] if k < len(stored) and isinstance(stored[k], dict) else {}
        if str(theirs.get("summary") or "").strip():
            block.append("Its summary: " + _prompt._strip_task_tags(str(theirs["summary"])).strip())
        for sh in nx["shots"]:
            block.append("Shot at scene {}: {}".format(spec.fmt_time(nstart + float(sh["t"])), " | ".join(
                v for v in (sh.get("camera"), sh.get("text")) if v) or "(no text)"))
        for d in nx["dialogue"]:
            block.append("Line at scene {}: {} <d>[{}] {}</d>".format(spec.fmt_time(nstart + float(d["t"])),
                                                                      _speaker(p, d), d.get("language") or "English",
                                                                      _clean_line(d.get("text"))))
        parts.append("\n".join(block))
    if b.get("prompt"):
        parts.append("What H3 receives for this pass now (labels already resolved; the sections without text of this "
                     "pass's own are the scene's shared ones):\n" + b["prompt"])

    m = max(1, len(x["shots"]))
    rules = ["Write detailed_description with {} [Shot N] line{} (about {} words per shot, {}-{} words in all).".format(
        m, "s" if m > 1 else "", int(round(sum(PASS_WORDS) / 2.0 / m)), *PASS_WORDS)]
    if auto.get("shots"):
        rules.append("Your [Shot N] lines replace the editor's automatic shot lines, so describe every shot in full.")
    # [OLD 2026-11-09 v0.14.2->v0.14.3] if fill:  # added 2026-11-09 v0.14.2
    # [OLD 2026-11-09 v0.14.2->v0.14.3]     rules.append(FILL_LINES_RULE)
    if fill or writes_shots(scene, plan):  # v0.14.2: spoken lines; v0.14.3: framing and camera move too
        rules += [FILL_LINES_RULE, FILL_CAMERA_RULE]
    rules.append("Leave subject_definitions empty: the editor writes a definition line for every reference this pass "
                 "sends." if auto.get("subjects") else
                 "subject_definitions: one line per reference this pass sends, for example \"@Mara is the woman in ...\".")
    rules.append("Leave retention_analysis empty: the editor writes it." if auto.get("retention") else
                 "retention_analysis: one line per reference with its retention marker, as the guide shows (no speaker "
                 "IDs).")
    parts.append("\n".join(rules))
    parts.append("Instruction: " + (instruction.strip() if isinstance(instruction, str) and instruction.strip() else
                                    "Write this pass's prompt following the guide."))
    parts.append("Return JSON with exactly these keys: subject_definitions, summary, retention_analysis, "
                 "detailed_description, overall_soundscape, non_diegetic_music.")
    return "\n\n".join(parts)


def pass_sections(data, k=None, _depth=0):
    """The six sections of one pass's answer, as given (values not yet text), or None when it has none. Takes the
    sections object itself, {"sections": …}, {"passes": [...]} / [...] (the entry for pass k, or the only one),
    {"2": …} / {"pass 2": …}, {"prompt": "<labelled text>"} and labelled text ("summary:\\n…")."""
    if _depth > 4 or data is None:
        return None
    again = lambda v: pass_sections(v, k, _depth + 1)  # noqa: E731
    if isinstance(data, str):
        return _sections_of(data) or None
    if isinstance(data, list):
        items = [v for v in data if isinstance(v, (dict, str))]
        for v in items:
            if isinstance(v, dict) and k is not None and any(str(v.get(x, "")).strip() == str(k)
                                                             for x in ("index", "pass", "n")):
                return again(v)
        return again(items[0]) if len(items) == 1 else None
    if not isinstance(data, dict):
        return None
    found = _sections_of(data)
    if found:
        return found
    for key in ("sections", "passes", "pass_prompts", "prompts", "result", "answer"):
        if isinstance(data.get(key), (dict, list, str)):
            got = again(data[key])
            if got:
                return got
    numbered = {}
    for key, value in data.items():
        m = _PASS_KEY.match(str(key))
        if m and isinstance(value, (dict, str, list)):
            numbered.setdefault(int(m.group(1)), value)
    if numbered:
        pick = numbered.get(k) if k is not None else None
        if pick is None and len(numbered) == 1:
            pick = next(iter(numbered.values()))
        return again(pick) if pick is not None else None
    for key in ("prompt", "text", "content"):
        if isinstance(data.get(key), str):
            return again(data[key])
    return None


def _pass_parser(k):
    """parse() for ask(): one pass's sections, from JSON or from labelled text."""
    def parse(text, info):
        try:
            data = json_answer(text, info, "answer for pass {}".format(k), dict)
            secs = pass_sections(data, k)
        except LLMError as e:
            if e.reason != "bad_json":
                raise
            secs = None
        if not secs:
            secs = pass_sections(text or "", k)  # the six labels as plain text
            if secs and info.get("finish") == "length":
                secs = None  # a labelled answer cut off at the budget: not complete
        if not secs:
            if info.get("finish") == "length":
                raise LLMError("The answer for pass {} was cut off at {:,} tokens before it was complete. Raise Max "
                               "tokens (Global → Prompt rewriter), or set Thinking to Off.".format(
                                   k, info.get("budget") or 0), "cut")
            raise LLMError("The answer for pass {} has none of the six sections.".format(k), "bad_json")
        return secs
    return parse


def _label_tokens(build):
    """label -> @ token of one pass (the inverse of its tag_map); a video's own sound <Audio N> is its video's token
    (the continuation clip's is @tail)."""
    inverse = {}
    for key, label in (build.get("tag_map") or {}).items():
        if key.startswith("@"):
            inverse.setdefault(label, _prompt.tag_token(key[1:]))
    for k, v in enumerate(build.get("videos") or [], 1):
        if isinstance(v, dict) and v.get("soundtrack") and v.get("audio_number"):
            token = "@tail" if v.get("continuation") else inverse.get("<Video {}>".format(k))
            if token:
                inverse.setdefault("<Audio {}>".format(v["audio_number"]), token)
    return inverse


def _spoken(text):
    """Spoken words in <d>…</d> spans, without the [Language] tag, in one line each."""
    out = []
    for span in DIALOGUE_RE.findall(text or ""):
        body = re.sub(r"^\s*\[[^\]]*\]\s*", "", span[3:-4])
        out.append(" ".join(body.split()))
    return out


def _core(line):
    return " ".join(str(line or "").split()).rstrip(" .!?…\"'").lower()


# added 2026-11-06 v0.10.0: the sentence around a spoken line, to take it out of a description
_SENTENCE_STOP = re.compile(r"[.!?…](?=\s)|\n|\]\s")


def drop_foreign_lines(text, belongs):
    """(text, removed, twice): text without the spoken lines (<d>…</d>) whose words (_core) `belongs` rejects, and
    without a second copy of a line. Each is removed with its sentence: from the end of the sentence before (or the
    [Shot N] label, or a line break) to the end of the line, plus a short tail that only finishes the sentence (", her
    voice breaking." / " while their lips remain completely closed.")."""
    text = text or ""
    spans = list(DIALOGUE_RE.finditer(text))
    if not spans:
        return text, [], []
    removed, twice, seen, cuts = [], [], set(), []
    for m in spans:
        body = " ".join(re.sub(r"^\s*\[[^\]]*\]\s*", "", m.group(0)[3:-4]).split())
        c = _core(body)
        if not c:
            continue
        if not belongs(c):
            removed.append(body)
        elif c in seen:
            twice.append(body)
        else:
            seen.add(c)
            continue
        # the sentence starts after the last stop before the line (never inside an earlier line)
        before = text[:m.start()]
        floor = max([x.end() for x in spans if x.end() <= m.start()] + [0])
        start = floor
        for s in _SENTENCE_STOP.finditer(before, floor):
            start = s.end()
        end = m.end()
        # only a tail that goes on with the same sentence: a stop right after the line, or a clause that starts with a
        # comma, a dash or a lower-case word (" while their lips…"); "Rain falls." is the next sentence and stays
        tail = re.match(r"\s*[.!?]|(?:\s*[,;:\u2014\u2013-]|\s+(?=[a-z]))[^<.!?\n]{0,120}[.!?]", text[end:])
        if tail:
            end += tail.end()
        cuts.append((start, end))
    for a, b in reversed(cuts):
        left, right = text[:a].rstrip(" "), text[b:].lstrip(" ")
        text = left + (" " if left and right and not left.endswith("\n") and not right.startswith("\n") else "") + right
    return text.strip(), removed, twice


# [OLD 2026-11-09 v0.14.1->v0.14.2] def tidy_pass(sections, x, build, auto, k=1, known=None, guides=()):
def tidy_pass(sections, x, build, auto, k=1, known=None, guides=(), free_lines=False):  # free_lines: added v0.14.2
    """(six sections as text, warnings) of one pass's answer, ready to store as scene.prompt.passes[k-1].sections:
    - a whole six-section prompt inside one key is split into its sections; a value's own label is dropped;
    - <Subject N>, <Picture N>, <Video N>, <Audio N> become the @ tokens of this pass's tag_map (the clip's own sound
      <Audio N> becomes @tail), so the text works when another pass numbers its references differently;
    - "N/A" in subject_definitions, summary, retention_analysis or detailed_description means empty (the shared text);
    - the task-type prefix leaves the summary; subject_definitions / retention_analysis are empty when the editor
      writes them (auto);
    - detailed_description: "[Shot1]" is "[Shot 1]"; when the answer has one [Shot N] per shot of the pass, the
      shots are numbered from 1 in order, [Shot 1] has no cut time and every other shot's "At MM:SS.mmm," is its
      start time in the pass (the timeline's).
    Warnings: the description's length, spoken lines missing or added, unknown @ names, labels left as written,
    a [Shot N] count that does not match the pass's shots, cut times moved, a frame guide (pass_guides) not named.
    free_lines (added 2026-11-09 v0.14.2): the scene has no spoken lines yet and the LLM may write them
    (fills_timeline), so only a second copy of a line is taken out."""
    warnings = []
    out = {key: _prompt.as_text(sections.get(key)).strip() if sections.get(key) is not None else ""
           for key in _prompt.REF2VA_SECTIONS}
    for key in _prompt.REF2VA_SECTIONS:
        found = list(_prompt.SECTION_LABEL.finditer(out[key]))
        if len(found) >= 2:  # the whole prompt in one key
            text = out[key]
            for i, m in enumerate(found):
                body = text[m.end():found[i + 1].start() if i + 1 < len(found) else len(text)].strip()
                if m.group(1) == key or not out[m.group(1)].strip():
                    out[m.group(1)] = body
        elif len(found) == 1 and found[0].start() == 0 and found[0].group(1) == key:
            out[key] = out[key][found[0].end():].strip()
    for key in ("subject_definitions", "summary", "retention_analysis", "detailed_description"):
        if out[key].strip().lower().rstrip(".") in _EMPTY:
            out[key] = ""
    inverse = _label_tokens(build)
    if inverse:
        pattern = re.compile("|".join(re.escape(v) for v in sorted(inverse, key=len, reverse=True)))
        out = {key: pattern.sub(lambda m: inverse[m.group(0)], v) for key, v in out.items()}
    left = sorted({m.group(0) for v in out.values() for m in _LABEL.finditer(v)})
    if left:
        warnings.append("{} left as written (not a reference this pass sends); fixed numbers can point at another "
                        "reference, so write @ tokens".format(", ".join(left)))
    out["summary"] = _prompt._strip_task_tags(out["summary"]).strip()
    if auto.get("subjects"):
        out["subject_definitions"] = ""
    if auto.get("retention"):
        out["retention_analysis"] = ""

    shots = x.get("shots") or []
    desc = _SHOT_LOOSE.sub(lambda m: "[Shot {}]".format(int(m.group(1))), out["detailed_description"])
    pre, chunks = _prompt._chunks(desc, _prompt.SHOT_START)
    if chunks:
        if shots and len(chunks) == len(shots):
            numbers = [int(_prompt.SHOT_NUMBER.match(label).group(1)) for label, _ in chunks]
            if numbers != list(range(1, len(chunks) + 1)):
                warnings.append("the shots were numbered {} and are numbered from [Shot 1] in the pass".format(
                    ", ".join("[Shot {}]".format(n) for n in numbers)))
            moved, lines = [], []
            for j, (label, chunk) in enumerate(chunks, 1):
                body = chunk[len(label):].strip()
                if j == 1:
                    body = _prompt._drop_cut_lead(body)
                else:
                    t = float(shots[j - 1]["t"])
                    # [OLD 2026-11-09 v0.17.1->v0.17.2] m = _CUT_TIME.match(body)  (a shot that opens with a timed spoken line
                    # had the line's time rewritten to the shot's start)
                    timed_line = _prompt._lead_kind(body) == "line"  # added 2026-11-09 v0.17.2 (third review 11)
                    m = None if timed_line else _CUT_TIME.match(body)
                    if timed_line:
                        body = "At {}, the shot cuts to a new angle. {}".format(spec.fmt_time(t), body)
                    elif m:
                        said = int(m.group(1)) * 60 + float(m.group(2))
                        if abs(said - t) > 0.0005:
                            body = "At {}{}{}".format(spec.fmt_time(t), m.group(3), body[m.end():])
                            if abs(said - t) > 0.05:
                                moved.append("[Shot {}] {} -> {}".format(j, spec.fmt_time(said), spec.fmt_time(t)))
                    else:
                        body = "At {}, the shot cuts to {}".format(spec.fmt_time(t), _prompt._cut_object(body))
                lines.append("[Shot {}] {}".format(j, body).strip())
            if moved:
                warnings.append("cut times set to the timeline's: " + ", ".join(moved))
            desc = "\n".join(([pre] if pre else []) + lines)
        elif shots:
            warnings.append("the answer has {} [Shot N] line{} for the pass's {} shot{}; they are kept as written".format(
                len(chunks), "s" if len(chunks) != 1 else "", len(shots), "s" if len(shots) != 1 else ""))
    elif desc.strip() and shots:
        warnings.append("the detailed description has no [Shot N] lines")
    out["detailed_description"] = desc.strip()

    words = len(_prompt.SHOT_NUMBER.sub("", out["detailed_description"]).split())
    if not words:
        warnings.append("no detailed description (the shared one is used)")
    elif words < PASS_WORDS_WARN[0]:
        warnings.append("the detailed description has {} words; H3's guide asks for {}-{}".format(words, *PASS_WORDS))
    elif words > PASS_WORDS_WARN[1]:
        warnings.append("the detailed description has {} words, more than the {}-{} H3's guide asks for".format(
            words, *PASS_WORDS))
    said = [_core(s) for s in _spoken(out["detailed_description"])]
    lines = [_clean_line(d.get("text")) for d in x.get("dialogue") or []]
    missing = [t for t in lines if _core(t) and not any(_core(t) in s for s in said)]
    if missing:
        warnings.append("spoken lines missing or changed: " + " | ".join('"{}"'.format(t) for t in missing))
    # [OLD 2026-11-06 v0.9.0->v0.10.0] kept in the text with a warning, so H3 said them: a line of the pass before
    # written again, or a line written twice, was heard twice
    # extra = [s for s in _spoken(out["detailed_description"])
    #          if _core(s) and not any(_core(t) in _core(s) or _core(s) in _core(t) for t in lines)]
    # if extra:
    #     warnings.append("spoken lines that are not this pass's (H3 would say them): " +
    #                     " | ".join('"{}"'.format(t) for t in extra))
    # [/OLD]
    # added 2026-11-06 v0.10.0: a spoken line that is not one of this pass's, and a second copy of one that is, are
    # taken out of the text with their sentence ("Mara (S1) says, <d>…</d>"); the warning says which
    own = [_core(t) for t in lines if _core(t)]
    # [OLD 2026-11-09 v0.14.1->v0.14.2] out["detailed_description"], extra, twice = drop_foreign_lines(
    # [OLD 2026-11-09 v0.14.1->v0.14.2]     out["detailed_description"], lambda c: any(t in c or c in t for t in own))
    out["detailed_description"], extra, twice = drop_foreign_lines(
        out["detailed_description"], lambda c: free_lines or any(t in c or c in t for t in own))
    if extra:
        warnings.append("removed spoken lines that are not this pass's (H3 would have said them): " +
                        " | ".join('"{}"'.format(t) for t in extra))
    if twice:
        warnings.append("removed a second copy of: " + " | ".join('"{}"'.format(t) for t in twice))
    known = set(known or ()) | {_prompt.name_key(key[1:]) for key in (build.get("tag_map") or {}) if key.startswith("@")}
    unknown = []
    for v in out.values():
        for m in _prompt.tag_re().finditer(v):
            name = m.group(1) or m.group(2)
            key = _prompt.name_key(name)
            pos = _prompt.POSSESSIVE.match(name or "")
            if key not in known and not (pos and _prompt.name_key(pos.group(1)) in known):
                unknown.append(m.group(0))
    if unknown:
        warnings.append("references the scene does not have: " + ", ".join(dict.fromkeys(unknown)))
    named = {_prompt.name_key(m.group(1) or m.group(2)) for v in out.values() for m in _prompt.tag_re().finditer(v)}
    for g in guides or ():
        if _prompt.name_key(g[0][1:]) not in named:
            warnings.append("the {} {} is not named, so it is only anchored, not sent as a picture".format(g[1], g[0]))
    return out, warnings


async def write_passes(cfg, p, scene, wanted=None, instruction="", progress=None, state=None, plan=None,
                       builds=None):
    """Write the six sections of each wanted pass (1-based numbers; None = every pass) of a scene of a normalised
    project, one request per pass, in order; each request sees the passes written before it in this batch.
    progress(dict) gets ask()'s events plus pass (number), passes (the scene's count), item / items (place in this
    batch) and completed (passes done). `state` is filled as the batch goes, so a caller that stops the task still has
    the passes written so far: {scene_id, pass_count, passes: [{index, start, end, sections}], warnings, tokens, ms};
    a request that fails after a pass was written ends the batch with error, reason and failed (the pass number)
    in it, and a warning; one that fails before raises. Returns `state`."""
    t0 = time.time()
    state = {} if state is None else state
    for key, value in (("passes", []), ("warnings", []), ("tokens", 0), ("ms", 0)):
        state.setdefault(key, value)
    pr = scene.get("prompt") or {}
    if pr.get("mode") == "raw":
        raise ValueError("This scene's prompt is raw text, which every pass gets as it is; switch it to Structured to "
                         "write each pass")
    if plan is None or builds is None:
        plan, builds = scene_builds(p, scene)
    n = len(plan["passes"])
    todo = sorted({int(k) for k in wanted}) if wanted else list(range(1, n + 1))
    bad = [k for k in todo if not 1 <= k <= n]
    if bad:
        raise ValueError("pass {} is not in this scene, which is made in {} pass{}".format(
            ", ".join(str(k) for k in bad), n, "es" if n != 1 else ""))
    state.update(scene_id=scene["id"], pass_count=n)
    preset = PRESETS.get(cfg.get("preset"), PRESETS["h3_ref2va"])
    system = system_prompt(cfg, preset + "\n\n" + PASS_RULES)  # the same for every pass (a server's prefix cache)
    stored = stored_pass_texts(p, scene, plan)
    overrides = pr.get("pass_prompts") or {}
    want = pass_budget(cfg)
    written = {}
    for item, k in enumerate(todo, 1):
        x, b = plan["passes"][k - 1], builds[k - 1]
        user = pass_request(p, scene, plan, builds, k, written, stored, instruction)
        step = None
        if progress:
            extra = {"pass": k, "passes": n, "item": item, "items": len(todo), "completed": len(state["passes"])}
            step = (lambda d, e=extra: progress({**d, **e}))
        info = {}
        try:
            secs = await ask(cfg, system, user, parse=_pass_parser(k), max_tokens=want, progress=step, info=info)
        except (LLMError, NoAnswer) as e:
            state["tokens"] += int(info.get("tokens") or 0)
            state["ms"] = int((time.time() - t0) * 1000)
            if not state["passes"]:
                raise
            state.update(error=str(e), reason=e.reason, failed=k)
            state["warnings"].append("Pass {} was not written: {}".format(k, e))
            return state
        state["tokens"] += int(info.get("tokens") or 0)
        # [OLD 2026-11-09 v0.14.1->v0.14.2] sections, warns = tidy_pass(secs, x, b, pr.get("auto") or {}, k, _scene_tokens(p, scene),
        # [OLD 2026-11-09 v0.14.1->v0.14.2]                             pass_guides(p, scene, x))
        sections, warns = tidy_pass(secs, x, b, pr.get("auto") or {}, k, _scene_tokens(p, scene),
                                    pass_guides(p, scene, x),
                                    free_lines=fills_timeline(scene, plan) and not scene.get("dialogue"))  # v0.14.2
        override = overrides.get(str(k))
        if isinstance(override, str) and override.strip():
            warns.append("its prompt was edited by hand (or by Split), and that prompt is sent instead of these "
                         "sections; clear it to use them")
        written[k] = sections
        state["passes"].append({"index": k, "start": x["start"], "end": x["end"], "sections": sections})
        state["warnings"] += ["Pass {}: {}".format(k, w) for w in warns]
        state["ms"] = int((time.time() - t0) * 1000)
    return state


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
        # [OLD 2026-11-03 v0.6.0 review] if isinstance(c, dict) and c.get("name") and c["name"].lower() not in seen:
        # added 2026-11-03 v0.6.0 review: a name that is not text ({"name": 5}) is skipped, not an AttributeError
        if isinstance(c, dict) and isinstance(c.get("name"), str) and c["name"].strip() \
                and c["name"].lower() not in seen:
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
    # [OLD 2026-11-05 v0.7.0->v0.8.0] nothing said how long a shot's text or the summary should be: shots came back as
    # one short sentence, so each pass of a long scene got 1-2 sentences per shot, far below the 350-500 words of
    # detailed description H3's guide asks for
    # lines.append(
    #     "Return JSON: {\"cast\": [{\"name\", \"kind\": \"character|location|prop\", \"description\", \"speaker\": \"S1\", "
    #     "\"language\"}], \"scenes\": [{\"title\", \"duration\": seconds (any length), \"summary\", \"soundscape\", \"music\", "
    #     "\"cast\": [names], \"shots\": [{\"t\": seconds from scene start, \"duration\": seconds, \"camera\", \"text\"}], "
    #     "\"dialogue\": [{\"speaker\": name, \"t\": seconds, \"text\", \"language\", \"delivery\"}]}]}.\n"
    #     "In \"cast\" list only characters, locations and props that are not in the existing cast. Give each speaking "
    #     "character a speaker id S1, S2... Every shot has a duration; a shot's t is the sum of the durations of the shots "
    #     "before it in the same scene, and the scene's duration is the sum of all its shot durations, so no shot starts "
    #     "after the scene ends. Leave timings realistic for the action and lines; when the script gives durations or "
    #     "times, use them (a scene made of several timed rows lasts as long as those rows together).")
    # [/OLD]
    # added 2026-11-05 v0.8.0: the same JSON, with 2-4 sentences per shot and the summary as a note on the whole scene
    # (each pass's own summary and 350-500-word description are written later, by Write prompts: write_passes)
    lines.append(
        "Return JSON: {\"cast\": [{\"name\", \"kind\": \"character|location|prop\", \"description\", \"speaker\": \"S1\", "
        "\"language\"}], \"scenes\": [{\"title\", \"duration\": seconds (any length), \"summary\", \"soundscape\", \"music\", "
        "\"cast\": [names], \"shots\": [{\"t\": seconds from scene start, \"duration\": seconds, \"camera\", \"text\"}], "
        "\"dialogue\": [{\"speaker\": name, \"t\": seconds, \"text\", \"language\", \"delivery\"}]}]}.\n"
        "In \"cast\" list only characters, locations and props that are not in the existing cast. Give each speaking "
        "character a speaker id S1, S2... Every shot has a duration; a shot's t is the sum of the durations of the shots "
        "before it in the same scene, and the scene's duration is the sum of all its shot durations, so no shot starts "
        "after the scene ends. Leave timings realistic for the action and lines; when the script gives durations or "
        "times, use them (a scene made of several timed rows lasts as long as those rows together).\n"
        "Each shot's \"text\" is 2-4 English sentences that a video model can film: the composition (shot size, angle, "
        "foreground and background), each subject's appearance and position in the frame, the action, the camera "
        "movement (or that the camera holds still) and the sound heard in the shot. Use cast names as written; keep "
        "spoken words out of \"text\" (they belong in \"dialogue\"). \"camera\" is a few words, such as "
        "\"Wide · slow push-in\".\n"
        "Each scene's \"summary\" is a note on the whole scene in 2-4 sentences: setting, time of day and mood, who is "
        "in it, and what happens from its start to its end. \"soundscape\" is the scene's ambience and physical "
        "sounds; \"music\" is the score only the audience hears, or empty.")
    # added 2026-11-06 v0.10.0: every speaking character (a narrator too) gets a voice description, written into every
    # pass so H3 keeps the voice (it picked a new one in each pass, a narrator turned from male to female)
    lines.append(
        "Give every character who speaks (a narrator or an off-screen voice too) a \"voice\" in their cast entry: one "
        "short phrase on how the voice sounds, with gender, age, pitch, timbre, pace and accent where the script implies "
        "them, for example \"a deep, warm male voice, slow and measured\". Add a narrator who speaks to the cast as a "
        "character, and use that name as the speaker of their lines.")
    lines.append(("Script part:\n" if parts > 1 else "Script:\n") + text)
    user = "\n\n".join(lines)
    icfg = import_cfg(cfg)

    def parse(answer, info):
        # [OLD 2026-11-03 v0.6.0 review] data = json_answer(answer, info, "answer" if parts == 1 else "answer for part {}".format(part))
        # added 2026-11-03 v0.6.0 review: the script answer is an object (a bare list of scenes still works)
        data = json_answer(answer, info, "answer" if parts == 1 else "answer for part {}".format(part), dict)
        if isinstance(data, list):  # added 2026-11-03 v0.6.0: a bare list of scenes
            data = {"scenes": data}
        if not isinstance(data, dict):
            raise LLMError("The answer was not a JSON object.", "bad_json")
        return data

    info = {}
    # [OLD 2026-11-05 v0.7.0->v0.8.0] data = await ask(icfg, system_prompt(icfg), user, parse=parse, max_tokens=cfg.get("import_max_tokens", 16384),
    data = await ask(icfg, system_prompt(icfg), user, parse=parse, max_tokens=cfg.get("import_max_tokens", IMPORT_MAX_TOKENS),
                     progress=progress, info=info, retry_cut=retry_cut)
    # [OLD 2026-11-03 v0.4.2->v0.4.3] return {"scenes": [s for s in (data.get("scenes") or []) if isinstance(s, dict)],
    # [OLD 2026-11-03 v0.5.1->v0.6.0] wrong types reached the project (a list as a title, text as a time) and /plan failed later
    # scenes = [s for s in (data.get("scenes") or []) if isinstance(s, dict)]
    # [/OLD]
    scenes, cast, warnings = coerce_script(data)
    for s in scenes:  # added 2026-11-03 v0.4.3: no shot or line after the scene's end
        note = fit_scene(s)
        if note:
            s["fit_note"] = note
    # [OLD 2026-11-03 v0.5.1->v0.6.0] return {"scenes": scenes,
    #         "cast": [c for c in (data.get("cast") or []) if isinstance(c, dict)],
    return {"scenes": scenes, "cast": cast, "warnings": warnings,  # warnings: added 2026-11-03 v0.6.0
            "tokens": info.get("tokens", 0), "ms": info.get("ms", 0), "attempts": info.get("attempt", 1),
            "budget": info.get("budget"), "input": info.get("input"), "context": info.get("context")}


# ---- script import answer, checked (added 2026-11-03 v0.6.0) ------------------------------------------------------
CAST_KINDS = ("character", "location", "prop")


def _seconds(v):
    """Seconds from 12, 12.5, "12", "12 s", "0:12", "00:01:05.5"; None when it is not a time."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v == v and abs(v) != float("inf") else None
    if isinstance(v, str):
        t = v.strip().lower()
        m = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)", t)
        if m:
            return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)?", t)
        if m:
            return float(m.group(1))
    return None


def _items(v):
    """A list from a list, a dict of numbered items, or one item; [] for nothing."""
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, dict) and v and all(isinstance(x, dict) for x in v.values()) and \
            all(str(k).strip().isdigit() for k in v):
        return [v[k] for k in sorted(v, key=lambda k: int(str(k).strip()))]
    return [v]


# added 2026-11-05 v0.8.0: a shot answered as separate parts ({"composition", "subject", "action", "sound"}) instead
# of one "text" is joined in reading order, so none of the 2-4 sentences is lost
SHOT_PARTS_BEFORE = ("composition", "framing", "subject", "subjects", "appearance", "position")
SHOT_PARTS_AFTER = ("environment", "lighting", "camera_movement", "movement", "sound", "audio")


def _shot_text(sh, body):
    """The shot's text: `body` (its text, action or description), with the parts written under their own keys before
    and after it. Without such parts, `body` as it is (the v0.7.0 result). A part of fewer than 3 words (a bare name
    under "subject") is left out."""
    def part(key):
        v = sh.get(key)
        if not isinstance(v, (str, list)):
            return ""
        t = " ".join(_prompt.as_text(v).split())
        if len(t.split()) < 3 or t in body:
            return ""
        return t if t[-1] in ".!?…" else t + "."
    before = [t for t in (part(k) for k in SHOT_PARTS_BEFORE) if t]
    after = [t for t in (part(k) for k in SHOT_PARTS_AFTER) if t]
    if not before and not after:
        return body
    main = body.strip()
    if main and main[-1] not in ".!?…":
        main += "."
    return " ".join(x for x in before + [main] + after if x)


def coerce_script(data):
    """(scenes, cast, warnings) from a script-import answer, in exactly the shapes the editor reads: text fields are
    text (lists become lines, objects "key: value" lines), times and durations are numbers or left out, shots and
    dialogue are lists of objects; anything that cannot be used is left out with a warning, so a bad answer can
    never break /plan later."""
    warnings = []

    def warn(msg):
        if len(warnings) < 30:
            warnings.append(msg)

    def text(v, where, key):
        if v is not None and not isinstance(v, str):
            warn("{}: {} was {}, used as text".format(where, key, type(v).__name__))
        return _prompt.as_text(v).strip()

    scenes = []
    for n, s in enumerate(_items(data.get("scenes")), 1):
        if not isinstance(s, dict):
            warn("Scene {}: not an object, left out".format(n))
            continue
        where = "Scene {}".format(n)
        out = {}
        for key in ("title", "summary", "soundscape", "music"):
            if s.get(key) is not None:
                out[key] = text(s[key], where, key)
        if s.get("duration") not in (None, ""):
            d = _seconds(s["duration"])
            if d is not None and d > 0:
                out["duration"] = d
            else:
                warn("{}: duration {!r} is not a length in seconds, left out".format(where, s["duration"]))
        names = []
        for c in _items(s.get("cast")):
            name = _prompt.as_text(c.get("name") if isinstance(c, dict) else c).strip()
            if name:
                names.append(name)
        out["cast"] = names
        shots = []
        for k, sh in enumerate(_items(s.get("shots")), 1):
            if isinstance(sh, str):
                sh = {"text": sh}
            if not isinstance(sh, dict):
                warn("{}, shot {}: not an object, left out".format(where, k))
                continue
            # [OLD 2026-11-05 v0.7.0->v0.8.0] one field only: a shot written as "composition", "action", "sound"...
            # (the parts v0.8.0 asks for) kept only its action
            # o = {"camera": text(sh.get("camera"), where, "a shot's camera"),
            #      "text": text(next((sh[x] for x in ("text", "action", "description") if sh.get(x) is not None), ""),
            #                   where, "a shot's text")}
            # [/OLD]
            o = {"camera": text(sh.get("camera"), where, "a shot's camera"),
                 "text": _shot_text(sh, text(next((sh[x] for x in ("text", "action", "description")
                                                   if sh.get(x) is not None), ""), where, "a shot's text"))}
            raw_t = next((sh[x] for x in ("t", "time", "start") if sh.get(x) not in (None, "")), None)
            if raw_t is not None:
                t = _seconds(raw_t)
                if t is None:
                    warn("{}, shot {}: start {!r} is not a time, left out".format(where, k, raw_t))
                else:
                    o["t"] = t
            if sh.get("duration") not in (None, ""):
                d = _seconds(sh["duration"])
                if d is not None and d > 0:
                    o["duration"] = d
                else:
                    warn("{}, shot {}: duration {!r} is not a length, left out".format(where, k, sh["duration"]))
            shots.append(o)
        out["shots"] = shots
        lines = []
        for k, d in enumerate(_items(s.get("dialogue")), 1):
            if isinstance(d, str):
                m = re.match(r"^\s*([^:\n]{1,40}):\s*(.+)$", d, re.S)
                d = {"speaker": m.group(1), "text": m.group(2)} if m else {"text": d}
            if not isinstance(d, dict):
                warn("{}, line {}: not an object, left out".format(where, k))
                continue
            spk = d.get("speaker")
            o = {"speaker": _prompt.as_text(spk.get("name") if isinstance(spk, dict) else spk).strip(),
                 "text": text(next((d[x] for x in ("text", "line") if d.get(x) is not None), ""), where, "a line's text"),
                 "language": text(d.get("language"), where, "a line's language"),
                 "delivery": text(d.get("delivery"), where, "a line's delivery")}
            if not o["text"]:
                warn("{}, line {}: no words, left out".format(where, k))
                continue
            raw_t = next((d[x] for x in ("t", "time", "start") if d.get(x) not in (None, "")), None)
            if raw_t is not None:
                t = _seconds(raw_t)
                if t is None:
                    warn("{}, line {}: time {!r} is not a time, left out".format(where, k, raw_t))
                else:
                    o["t"] = t
            lines.append(o)
        out["dialogue"] = lines
        scenes.append(out)
    if data.get("scenes") is not None and not isinstance(data.get("scenes"), (list, dict)):
        warn("\"scenes\" was not a list")
    cast = []
    for n, c in enumerate(_items(data.get("cast")), 1):
        if isinstance(c, str):
            c = {"name": c}
        if not isinstance(c, dict):
            warn("Cast {}: not an object, left out".format(n))
            continue
        name = _prompt.as_text(c.get("name")).strip()
        if not name:
            warn("Cast {}: no name, left out".format(n))
            continue
        kind = _prompt.as_text(c.get("kind")).strip().lower() or "character"
        if kind not in CAST_KINDS:
            warn("Cast {} ({}): kind {!r} is not character, location or prop, so it is a character".format(n, name, kind))
            kind = "character"
        # [OLD 2026-11-06 v0.9.0->v0.10.0] cast.append({"name": name, "kind": kind,
        # [OLD 2026-11-06 v0.9.0->v0.10.0]              "description": text(c.get("description"), "Cast " + name, "description"),
        # [OLD 2026-11-06 v0.9.0->v0.10.0]              "speaker": _prompt.as_text(c.get("speaker")).strip(),
        # [OLD 2026-11-06 v0.9.0->v0.10.0]              "language": _prompt.as_text(c.get("language")).strip()})
        # added 2026-11-06 v0.10.0: voice (how a speaking character sounds) -> the cast member's voice_desc
        voice = next((c[x] for x in ("voice", "voice_desc", "voice_description") if c.get(x) is not None), "")
        cast.append({"name": name, "kind": kind,
                     "description": text(c.get("description"), "Cast " + name, "description"),
                     "speaker": _prompt.as_text(c.get("speaker")).strip(),
                     "language": _prompt.as_text(c.get("language")).strip(),
                     "voice_desc": text(voice, "Cast " + name, "voice") if kind == "character" else ""})
    return scenes, cast, warnings


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
