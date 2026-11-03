"""LLM client against a stub OpenAI-compatible server (added 2026-11-02 v0.3.2).

Thinking models put their reasoning in `reasoning_content` and leave `content` empty when the token
budget runs out; that used to surface as "The model returned no text. Is it a vision model?".
"""

import asyncio
import json

import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp import web  # noqa: E402

from reelwright import llm  # noqa: E402


def reply(content, reasoning=None, finish="stop"):
    msg = {"role": "assistant", "content": content}
    if reasoning is not None:
        msg["reasoning_content"] = reasoning
    return {"model": "stub", "choices": [{"message": msg, "finish_reason": finish}]}


def run_with_server(handler, coro_fn):
    async def main():
        app = web.Application()
        app.router.add_post("/v1/chat/completions", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        cfg = {"base_url": "http://127.0.0.1:{}/v1".format(port), "model": "stub", "api_key": "", "temperature": 0.4,
               "max_tokens": 2048, "thinking": "auto", "preset": "h3_ref2va", "include_guides": False}
        try:
            return await coro_fn(cfg)
        finally:
            await runner.cleanup()
    return asyncio.run(main())


IMG = [(b"\xff\xd8fake", "image/jpeg")]


def test_read_reply_variants():
    assert llm.read_reply(reply("A red coat."), 100) == ("A red coat.", "", "stop")
    assert llm.read_reply(reply("<think>hmm</think>A red coat."), 100) == ("A red coat.", "hmm", "stop")
    # no reasoning parser on the server and cut off while thinking
    assert llm.read_reply(reply("<think>still going", finish="length"), 100) == ("", "still going", "length")
    # vLLM / Ollama style field
    d = {"choices": [{"message": {"content": None, "reasoning": "x"}, "finish_reason": "length"}]}
    assert llm.read_reply(d, 100) == ("", "x", "length")


def test_describe_thinking_budget_then_retry_without_thinking():
    seen = []

    async def handler(request):
        body = await request.json()
        seen.append(body)
        if body.get("chat_template_kwargs", {}).get("enable_thinking") is False:
            return web.json_response(reply("the woman in a navy pea coat"))
        return web.json_response(reply(None, reasoning="Let me look at the coat... " * 50, finish="length"))

    out = run_with_server(handler, lambda cfg: llm.describe(cfg, IMG, "Describe her."))
    assert out["text"] == "the woman in a navy pea coat"
    assert "thinking off" in out["note"]
    assert seen[0]["max_tokens"] >= 6000 and "chat_template_kwargs" not in seen[0]
    assert seen[1]["chat_template_kwargs"] == {"enable_thinking": False} and seen[1]["max_tokens"] == 600


def test_describe_thinking_off_sends_switch_and_explains_cutoff():
    async def handler(request):
        body = await request.json()
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        return web.json_response(reply("", reasoning="", finish="length"))

    async def go(cfg):
        cfg["thinking"] = "off"
        with pytest.raises(llm.NoAnswer) as e:
            await llm.describe(cfg, IMG, "")
        return str(e.value)
    msg = run_with_server(handler, go)
    assert "cut off at 600 tokens" in msg


def test_describe_empty_answer_still_hints_vision():
    async def handler(request):
        return web.json_response(reply(""))

    async def go(cfg):
        with pytest.raises(RuntimeError) as e:
            await llm.describe(cfg, IMG, "")
        return str(e.value)
    assert "vision model" in run_with_server(handler, go)


def test_chat_explains_thinking_cutoff():
    async def handler(request):
        return web.json_response(reply(None, reasoning="thinking...", finish="length"))

    async def go(cfg):
        with pytest.raises(llm.NoAnswer) as e:
            await llm.chat(cfg, "sys", "user", max_tokens=6000)
        return e.value
    err = run_with_server(handler, go)
    assert err.reason == "thinking_cut" and "6000 tokens thinking" in str(err)


def test_connection_test_reports_thinking_model():
    async def handler(request):
        return web.json_response(reply(None, reasoning="The user wants", finish="length"))

    out = run_with_server(handler, llm.test)
    assert out["ok"] and out["thinking"] and out["reply"] == "" and "Thinking" in out["note"]
    assert json.dumps(out)


# added 2026-11-03 v0.4.1: the rewrite proposal no longer repeats what the editor writes automatically
def test_rewrite_is_tidied(harbor):
    from reelwright.model import normalize_project
    p = normalize_project(harbor)
    scene = p["scenes"][1]
    scene["prompt"]["auto"] = {"subjects": True, "retention": False, "shots": True}

    async def handler(request):
        whole = ("subject_definitions:\n<Subject 1> is Mara.\n\nsummary:\n[reference generation] <Subject 1> walks home.\n\n"
                 "retention_analysis:\n<Subject 1> (appears in [Shot 1]): fully_preserved - face.\n\n"
                 "detailed_description:\nLive-action, rain.\n[Shot 1] <Subject 1> walks.\n\noverall_soundscape:\nRain.\n\n"
                 "non_diegetic_music:\nN/A")
        return web.json_response(reply(json.dumps({"detailed_description": whole})))

    out = run_with_server(handler, lambda cfg: llm.rewrite(cfg, p, scene, "", "", {"@Mara": "<Subject 1>", "@P1": "<Picture 1>"}))
    sec = out["sections"]
    assert sec["subject_definitions"] == scene["prompt"]["sections"]["subject_definitions"]   # auto: kept as it was
    assert sec["summary"] == "[reference generation] @Mara walks home."
    assert sec["retention_analysis"] == "@Mara (appears in [Shot 1]): fully_preserved - face."
    assert sec["detailed_description"] == "Live-action, rain." and sec["overall_soundscape"] == "Rain."
