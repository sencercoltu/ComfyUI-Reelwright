// Chat tab (added 2026-11-12 v0.13.0): ask the configured LLM general questions (Sencer: "a simple chat interface where
// we can ask LLM general questions; show the tab only if the LLM is enabled"). The conversation lives in this editor
// session (eph.chat), not in the project. The answer streams in: POST /reelwright/llm/chat sends reelwright.llm
// progress events with the text so far, which editor.js writes into the pending bubble in place (llmjob.jobText).

import { h, icon, button, copyWithToast } from "../ui.js";
import { rw } from "../api.js";
import { newJob, jobText } from "../llmjob.js";

// the tab shows when an LLM base URL is set: this project's (Global → Prompt rewriter) or the one stored on the server
export function enabled(ctx) {
  return !!(String(ctx.p.global.llm?.base_url || "").trim() || String(ctx.eph.llm?.base_url || "").trim());
}

let seq = 0;
const newMsgId = () => "m" + Date.now().toString(36) + (seq++).toString(36);

function state(ctx) {
  if (!ctx.store.eph.chat) ctx.store.eph.chat = { messages: [], busy: false, job: "", draft: "", scrollDown: false };
  return ctx.store.eph.chat;
}

// ---- a small, safe Markdown reader (DOM nodes only, never innerHTML): code fences, inline code, bold, headings, lists,
// tables as preformatted text, paragraphs
export function markdown(text) {
  const out = [];
  String(text || "").split("```").forEach((part, i) => {
    if (i % 2) {
      const nl = part.indexOf("\n");
      const body = nl >= 0 && /^[\w+#.-]*$/.test(part.slice(0, nl).trim()) ? part.slice(nl + 1) : part;
      out.push(h("pre", { class: "rw-chat-code" }, h("code", null, body.replace(/\n$/, ""))));
    } else out.push(...blocks(part));
  });
  return out;
}
function blocks(text) {
  const out = [];
  let list = null, para = [], table = [];
  const flushPara = () => { if (para.length) { out.push(h("p", null, ...inline(para.join("\n")))); para = []; } };
  const flushTable = () => { if (table.length) { out.push(h("pre", { class: "rw-chat-code" }, table.join("\n"))); table = []; } };
  for (const line of text.split("\n")) {
    if (/^\s*\|/.test(line)) { flushPara(); list = null; table.push(line.trim()); continue; }
    flushTable();
    if (!line.trim()) { flushPara(); list = null; continue; }
    const hd = /^\s*#{1,6}\s+(.*)$/.exec(line);
    if (hd) { flushPara(); list = null; out.push(h("div", { class: "rw-chat-h" }, ...inline(hd[1]))); continue; }
    const li = /^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/.exec(line);
    if (li) {
      flushPara();
      const ordered = li[1] !== undefined;
      if (!list || list.ordered !== ordered) { list = { ordered, el: h(ordered ? "ol" : "ul", null) }; out.push(list.el); }
      list.el.appendChild(h("li", null, ...inline(li[2])));
      continue;
    }
    list = null;
    para.push(line);
  }
  flushPara();
  flushTable();
  return out;
}
function inline(text) {
  const out = [];
  const re = /(`[^`\n]+`|\*\*[^*\n]+\*\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(m[0][0] === "`" ? h("code", null, m[0].slice(1, -1)) : h("b", null, m[0].slice(2, -2)));
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

// the answer so far, without a reasoning block a model writes inline (<think>…</think>)
export function visibleText(text) {
  const t = String(text || "");
  if (/^\s*<think>/.test(t) && !t.includes("</think>")) return "";
  return t.replace(/^\s*<think>[\s\S]*?<\/think>\s*/, "");
}
function liveLine(d) {
  const t = visibleText(d?.text);
  if (t) return t;
  if (!d || d.phase === "waiting") return "…";
  return d.reasoning || d.phase === "thinking" ? `Thinking… ≈${Math.round(d.reasoning || d.tokens || 0).toLocaleString("en-US")} tokens` : "…";
}

// the answer being written: editor.js calls __rwJobRender on every progress event of the job, which draws the text so far
// as Markdown and keeps the conversation scrolled to the end while it was there
function liveAnswer(ctx, job, nearEnd) {
  const el = jobText(job, ctx.eph.llmJobs[job], { tag: "div", class: "rw-chat-live", help: "chat.live", fmt: liveLine });
  el.__rwJobRender = (node, d) => {
    const log = ctx.root.querySelector(".rw-chat-log");
    const stick = log && nearEnd(log);
    const t = visibleText(d?.text);
    node.replaceChildren(...(t ? markdown(t) : [h("p", null, liveLine(d))]));
    if (stick) requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
  };
  el.__rwJobRender(el, ctx.eph.llmJobs[job]);
  return el;
}

async function send(ctx, text) {
  const st = state(ctx);
  const q = String(text ?? st.draft).trim();
  if (!q || st.busy) return;
  const messages = [...st.messages.filter(m => !m.error), { id: newMsgId(), role: "user", content: q }];
  const job = newJob("chat");
  // the box empties now: the editor keeps what was typed in a focused field across the re-render that follows
  if (text === undefined) { const ta = ctx.root.querySelector("textarea[data-key='chat-input']"); if (ta) ta.value = ""; }
  ctx.store.setEph({ chat: { ...st, messages, busy: true, job, draft: text === undefined ? "" : st.draft, scrollDown: true } });
  let reply;
  try {
    const r = await rw.llmChat(ctx.store.project, messages.map(m => ({ role: m.role, content: m.content })), job);
    if (r?.cancelled) {
      const partial = visibleText(ctx.store.eph.llmJobs[job]?.text).trim();
      reply = { id: newMsgId(), role: "assistant", content: partial, stopped: true };
    } else reply = { id: newMsgId(), role: "assistant", content: String(r?.reply || ""), ms: r?.ms || 0, model: r?.model || "" };
  } catch (err) {
    reply = { id: newMsgId(), role: "assistant", content: "", error: err?.message || "failed" };
  } finally {
    delete ctx.store.eph.llmJobs[job];
  }
  const now = state(ctx);
  if (now.job !== job) return; // cleared meanwhile
  ctx.store.setEph({ chat: { ...now, messages: [...messages, reply], busy: false, job: "", scrollDown: true } });
}
function stop(ctx) {
  const st = state(ctx);
  if (st.busy && st.job) rw.llmCancel(st.job).catch(() => {});
}
function clear(ctx) {
  stop(ctx);
  ctx.store.setEph({ chat: { messages: [], busy: false, job: "", draft: state(ctx).draft, scrollDown: false } });
}
function retry(ctx, m) {
  const st = state(ctx);
  const i = st.messages.indexOf(m);
  const q = [...st.messages.slice(0, i)].reverse().find(x => x.role === "user");
  if (!q || st.busy) return;
  // the question goes again, after the turns before it
  const before = st.messages.slice(0, st.messages.lastIndexOf(q));
  ctx.store.eph.chat = { ...st, messages: before };
  send(ctx, q.content);
}

function bubble(ctx, m) {
  const mine = m.role === "user";
  const foot = mine ? null : h("div", { class: "rw-chat-foot" },
    m.error ? h("span", { class: "rw-c-err" }, icon("warn", 11), " ", m.error)
      : h("span", { class: "rw-dim" }, m.stopped ? "stopped" : [m.model, m.ms ? (m.ms / 1000).toFixed(1) + " s" : ""].filter(Boolean).join(" · ")),
    h("span", { class: "rw-flex" }),
    m.error ? button({ label: "Retry", icon: "refresh", small: true, variant: "ghost", help: "chat.retry", key: "chat-retry-" + m.id, onClick: () => retry(ctx, m) })
      : m.content ? button({ icon: "copy", small: true, variant: "ghost", help: "chat.copy", key: "chat-copy-" + m.id, onClick: e => copyWithToast(m.content, e.currentTarget || e.target, "answer") }) : null);
  return h("div", { class: ["rw-chat-msg", mine ? "me" : "ai", m.error && "err"], dataset: { msg: m.id } },
    h("div", { class: "rw-chat-bubble" }, mine ? h("p", null, m.content) : m.content ? markdown(m.content) : m.stopped ? h("p", { class: "rw-dim" }, "(nothing yet)") : null),
    foot);
}

export function render(ctx) {
  const st = state(ctx);
  const g = ctx.p.global.llm || {}, server = ctx.eph.llm || {};
  const model = g.model || server.model || "the server's model";
  const url = g.base_url || server.base_url || "";
  const scrollDown = st.scrollDown;
  st.scrollDown = false;
  const scrollToEnd = el => { const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80; return near; };
  const log = h("div", { class: "rw-chat-log", dataset: { scroll: "chat-log" }, help: "chat.log" },
    st.messages.length || st.busy ? null : h("div", { class: "rw-chat-empty" }, icon("dialogue", 22),
      h("b", null, "Ask the LLM anything"), h("span", { class: "rw-dim" }, "General questions, not about a scene: nothing from this project is sent. The conversation stays in this editor until you clear it or reload.")),
    ...st.messages.map(m => bubble(ctx, m)),
    st.busy ? h("div", { class: "rw-chat-msg ai pending" },
      h("div", { class: "rw-chat-bubble" }, liveAnswer(ctx, st.job, scrollToEnd)),
      h("div", { class: "rw-chat-foot" }, h("span", { class: "rw-dim" }, "writing…"))) : null);
  if (scrollDown) requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
  const input = h("textarea", {
    class: "rw-textarea rw-chat-input", key: "chat-input", rows: 3, help: "chat.input", value: st.draft,
    placeholder: "Ask a question… (Enter sends, Shift+Enter for a new line)",
    onInput: e => { state(ctx).draft = e.target.value; },
    onKeydown: e => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); e.stopPropagation(); send(ctx); }
    },
  });
  return h("div", { class: "rw-chat" },
    h("div", { class: "rw-chat-head" },
      h("b", null, "Chat"), h("span", { class: "rw-dim small mono rw-ellipsis", help: "chat.model", title: url }, `${model}${url ? " · " + url : ""}`),
      h("span", { class: "rw-flex" }),
      button({ label: "Clear", icon: "trash", small: true, variant: "ghost", help: "chat.clear", key: "chat-clear", disabled: !st.messages.length && !st.busy, onClick: () => clear(ctx) })),
    log,
    h("div", { class: "rw-chat-send" }, input,
      st.busy ? button({ label: "Stop", icon: "stop", variant: "danger-ghost", help: "chat.stop", key: "chat-stop", onClick: () => stop(ctx) })
        : button({ label: "Send", icon: "play", variant: "primary", help: "chat.send", key: "chat-send", onClick: () => send(ctx) })));
}
