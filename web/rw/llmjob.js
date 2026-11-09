import { h } from "./ui.js"; // added 2026-11-06 v0.10.2: jobText
import { button, icon, rootScale } from "./ui.js"; // added 2026-11-09 v0.15.0: the output popup

// Progress of a running LLM request (added 2026-11-03 v0.4.2). The backend sends reelwright.llm events tagged with
// the job id the editor chose; editor.js keeps the latest one per job in eph.llmJobs.

/* [OLD 2026-11-06 v0.10.1->v0.10.2] job ids were not remembered, so editor.js could not tell its own jobs from another
   browser tab's (every reelwright.llm event rebuilt every editor's tab)
export function newJob(prefix = "llm") {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}
[/OLD] */
// added 2026-11-06 v0.10.2: the job ids made on this page; editor.js ignores reelwright.llm events of other jobs
// (another browser tab or client)
export const ownJobs = new Set();
export function newJob(prefix = "llm") {
  const id = `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  ownJobs.add(id);
  if (ownJobs.size > 500) ownJobs.delete(ownJobs.values().next().value);
  return id;
}

const n = v => Math.round(v || 0).toLocaleString("en-US");

// One line: "writing · ≈3,120 tokens of 16,384 · 48 s", "thinking · ≈1,240 tokens · 34 s", "retry 2 of 3 · …"
export function jobLine(d) {
  if (!d) return "sending…";
  if (d.phase === "retry") return `retry ${d.attempt} of ${d.attempts} · ${d.note || ""}`;
  const t = d.elapsed !== undefined ? ` · ${Math.round(d.elapsed)} s` : "";
  const tries = d.attempts > 1 && d.attempt > 1 ? ` · try ${d.attempt} of ${d.attempts}` : "";
  if (d.phase === "waiting") return `waiting for the server · prompt ≈${n(d.input)} tokens${d.context ? ` of ${n(d.context)} context` : ""}${t}${tries}`;
  if (d.phase === "thinking") return `thinking · ≈${n(d.reasoning)} tokens${d.budget ? ` of ${n(d.budget)}` : ""}${t}${tries}`;
  const used = (d.tokens || 0) + (d.reasoning || 0);
  return `${d.phase === "done" ? "done" : "writing"} · ≈${n(used)} tokens${d.budget ? ` of ${n(d.budget)}` : ""}${t}${tries}`;
}

// added 2026-11-06 v0.10.2: an element showing a job's progress. editor.js rewrites its text in place on every
// reelwright.llm event of that job (fmt(d), jobLine by default), so a running request no longer rebuilds the tab
// twice a second (the tab's tooltips restarted and its text fields flickered).
export function jobText(job, d, { tag = "span", fmt = jobLine, ...props } = {}) {
  const el = h(tag, { ...props, dataset: { llmJob: job } }, fmt(d));
  el.__rwJobText = fmt;
  return el;
}

// ---- added 2026-11-09 v0.15.0: what an LLM request receives, as it arrives (Sencer: "The Write prompt LLM response
// sometimes never ends, after a while times out. When waiting for response, we receive thinking, but cannot see what
// it thinks. Add the thinking progress and received content as output so we can see what's going on. It should only
// be shown by a toggle button inside a popup.")
// The backend's progress events carry what came since the last one: think_add at think_at (the reasoning) and
// text_add at text_at (the answer), character offsets in what that request received (llm.py chat). editor.js hands
// every event of this page's jobs to feedStream, which keeps them per job and per request (a pass, a part, a try);
// outputPopup shows one job's in a panel over the editor that follows the run (a batch moves on to the next scene's
// job). The streams stay after the job ends, so the popup still shows what a request that failed or timed out got.
const STREAMS = new Map(); // job id -> { segs: [{ key, label, think, text, thinkN, textN, notes }], last }
const MAX_JOBS = 40;
const MAX_CHARS = 500000; // kept per text; older text gives way ("[…]")
const GAP = "\n[… part of the stream was not received …]\n";

const segKey = d => `${d.item ?? ""}|${d.pass ?? ""}|${d.part ?? ""}|${d.attempt ?? 1}`;
function segLabel(d) {
  const what = d.pass ? `Pass ${d.pass}${d.passes ? ` of ${d.passes}` : ""}` : d.part ? `Part ${d.part}${d.parts ? ` of ${d.parts}` : ""}` : "Request";
  return what + (d.attempt > 1 ? ` · try ${d.attempt}${d.attempts ? ` of ${d.attempts}` : ""}` : "");
}

function put(seg, k, at, add) {
  if (typeof add !== "string" || !add) return;
  const n = seg[k + "N"];
  const pos = Number.isFinite(at) ? at : n;
  const endAt = pos + add.length;
  if (pos > n) seg[k] += GAP;
  else if (pos < n) add = add.slice(n - pos); // sent again: only what is new
  seg[k] += add;
  seg[k + "N"] = Math.max(n, endAt);
  if (seg[k].length > MAX_CHARS) seg[k] = "[…]" + seg[k].slice(-MAX_CHARS);
}

export function feedStream(d) {
  if (!d?.job) return null;
  let st = STREAMS.get(d.job);
  if (!st) {
    st = { segs: [], last: null };
    STREAMS.set(d.job, st);
    if (STREAMS.size > MAX_JOBS) STREAMS.delete(STREAMS.keys().next().value);
  }
  st.last = d;
  if (d.phase === "retry") {
    const seg = st.segs[st.segs.length - 1];
    if (seg) seg.notes.push(`retry ${d.attempt} of ${d.attempts}${d.note ? `: ${d.note}` : ""}`);
    return st;
  }
  const key = segKey(d);
  let seg = st.segs.find(x => x.key === key);
  if (!seg) {
    seg = { key, label: segLabel(d), think: "", text: "", thinkN: 0, textN: 0, notes: [] };
    st.segs.push(seg);
  }
  put(seg, "think", d.think_at, d.think_add);
  put(seg, "text", d.text_at, d.text_add);
  seg.phase = d.phase;
  return st;
}

export const streamOf = job => STREAMS.get(job) || null;

// a model without a reasoning parser on the server writes its reasoning into the answer, in <think>…</think> (or
// with only the closing tag): shown as reasoning, as llm.py _split_reasoning reads it
export function splitThink(seg) {
  let think = seg.think, text = seg.text;
  const lead = text.match(/^\s*<think>/);
  if (lead) {
    const rest = text.slice(lead[0].length);
    const end = rest.indexOf("</think>");
    return end < 0 ? { think: think + rest, text: "" } : { think: think + rest.slice(0, end), text: rest.slice(end + 8).replace(/^\s+/, "") };
  }
  const close = text.indexOf("</think>");
  if (close >= 0 && !text.slice(0, close).includes("<think>")) {
    think += text.slice(0, close);
    text = text.slice(close + 8).replace(/^\s+/, "");
  }
  return { think, text };
}

const chars = n => `${Math.round(n).toLocaleString("en-US")} character${n === 1 ? "" : "s"}`;

function drawOutput(el) {
  const st = streamOf(el.__rwJob);
  const body = el.querySelector(".rw-llm-out-body");
  const status = el.querySelector(".rw-llm-out-status");
  status.textContent = st?.last ? (st.last.pass ? `pass ${st.last.pass}${st.last.passes ? " of " + st.last.passes : ""} · ` : "") + jobLine(st.last) : "sending…";
  const end = body.scrollHeight - body.scrollTop - body.clientHeight < 32; // at the bottom: stay there
  const segs = st?.segs || [];
  if (!segs.length) {
    if (!body.querySelector(".rw-llm-out-empty")) body.replaceChildren(h("div", { class: "rw-llm-out-empty rw-dim small" }, "Nothing received yet. A thinking model's reasoning and the answer show here as they arrive."));
    return;
  }
  if (body.__rwJob !== el.__rwJob || body.children.length !== segs.length || body.querySelector(".rw-llm-out-empty")) {
    body.__rwJob = el.__rwJob;
    body.replaceChildren(...segs.map(seg => {
      const think = h("pre", { class: "rw-llm-think-text" });
      const sum = h("summary", { class: "small" });
      const text = h("pre", { class: "rw-llm-ans-text" });
      const ansHead = h("div", { class: "rw-llm-ans-head small" });
      const notes = h("div", { class: "rw-llm-notes small rw-c-warn" });
      const box = h("div", { class: "rw-llm-seg" },
        h("div", { class: "rw-llm-seg-head" }, h("b", { class: "small" }, seg.label)),
        h("details", { class: "rw-llm-think", open: true }, sum, think), ansHead, text, notes);
      box.__rwParts = { think, sum, text, ansHead, notes };
      return box;
    }));
  }
  segs.forEach((seg, i) => {
    const p = body.children[i].__rwParts;
    const v = splitThink(seg);
    if (p.think.textContent !== v.think) p.think.textContent = v.think;
    p.sum.textContent = v.think ? `Thinking · ${chars(v.think.length)}` : "Thinking · none received";
    if (p.text.textContent !== v.text) p.text.textContent = v.text;
    p.ansHead.textContent = v.text ? `Answer · ${chars(v.text.length)}` : seg.phase === "done" ? "Answer · none" : "Answer · nothing yet";
    p.notes.textContent = seg.notes.join(" · ");
  });
  if (end) body.scrollTop = body.scrollHeight;
}

// The popup goes just below the button that opened it (`anchor`), at the editor's right edge, or above it when there is
// no room below in the window: a node taller than the window (Nodes 2.0) has its bottom out of sight.
function placeOutput(root, el, anchor) {
  const a = anchor?.getBoundingClientRect?.();
  if (!a || !a.height) return;
  const r = root.getBoundingClientRect(), sc = rootScale(root) || 1;
  const rootH = root.offsetHeight || r.height / sc;
  const below = Math.min(window.innerHeight, r.bottom) - a.bottom - 12, above = a.top - Math.max(0, r.top) - 12;
  const room = (below >= 220 || below >= above ? below : above) / sc;
  const height = Math.max(160, Math.min(460, room, rootH - 16));
  let top = below >= 220 || below >= above ? (a.bottom - r.top) / sc + 6 : (a.top - r.top) / sc - 6 - height;
  top = Math.max(8, Math.min(top, rootH - height - 8));
  Object.assign(el.style, { top: `${Math.round(top)}px`, bottom: "auto", height: `${Math.round(height)}px` });
}

// The popup over the editor (`root`, the .rw-root): one per editor. follow() gives the job to show while it runs
// (a batch moves to the next scene's job), else `job` stays shown. onClose runs when its × closes it. anchor: the
// element it opens next to (placeOutput).
export function outputPopup(root, { job, follow, title = "LLM output", onClose, anchor } = {}) {
  if (!root) return null;
  let el = root.querySelector(":scope > .rw-llm-out");
  if (!el) {
    const close = () => { const f = el.__rwOnClose; el.remove(); f?.(); };
    el = h("div", { class: "rw-llm-out", role: "dialog", "aria-label": title, help: "llm.output",
      onPointerdown: e => { e.rwOwned = true; }, onWheel: e => e.stopPropagation(), onKeydown: e => { if (e.key === "Escape") { e.stopPropagation(); close(); } } },
      h("div", { class: "rw-llm-out-head" }, icon("eye", 13), h("b", { class: "small rw-llm-out-title" }, title),
        h("span", { class: "rw-llm-out-status rw-dim small mono grow" }),
        button({ icon: "copy", small: true, variant: "ghost", help: "llm.output.copy", ariaLabel: "Copy the output", onClick: () => {
          const st = streamOf(el.__rwJob);
          const all = (st?.segs || []).map(seg => { const v = splitThink(seg); return `## ${seg.label}\n\n### Thinking\n${v.think}\n\n### Answer\n${v.text}`; }).join("\n\n");
          navigator.clipboard?.writeText(all).catch(() => {});
        } }),
        button({ icon: "close", small: true, variant: "ghost", help: "common.close", ariaLabel: "Close the output", onClick: close })),
      h("div", { class: "rw-llm-out-body", dataset: { scroll: "llm-out" } }));
    el.__rwFeed = d => {
      const want = el.__rwFollow?.();
      if (want && want !== el.__rwJob) el.__rwJob = want;
      if (d?.job !== el.__rwJob || el.__rwFrame) return;
      el.__rwFrame = requestAnimationFrame(() => { el.__rwFrame = 0; if (el.isConnected) drawOutput(el); });
    };
    root.append(el);
    placeOutput(root, el, anchor);
  }
  el.__rwJob = (follow && follow()) || job || el.__rwJob;
  el.__rwFollow = follow;
  el.__rwOnClose = onClose;
  el.querySelector(".rw-llm-out-title").textContent = title;
  drawOutput(el);
  return el;
}

export const outputShown = root => !!root?.querySelector(":scope > .rw-llm-out");

export function closeOutput(root) {
  const el = root?.querySelector(":scope > .rw-llm-out");
  if (!el) return;
  const f = el.__rwOnClose;
  el.remove();
  f?.();
}

// The toggle button for a row that shows an LLM job: opens the popup on `job` (following follow()), or closes it.
// ctx.eph.llmOut says it is open, so the buttons draw as "Hide output".
export function outputButton(ctx, { job, follow, title, key, label = true }) {
  const open = !!ctx.eph.llmOut && outputShown(ctx.root);
  return button({ label: label ? (open ? "Hide output" : "Output") : undefined, icon: "eye", small: true, variant: open ? "accent-ghost" : "ghost", key,
    help: "llm.output", ariaLabel: open ? "Hide the LLM output" : "Show the LLM output", disabled: !job && !follow?.(),
    onClick: e => {
      if (open) { closeOutput(ctx.root); return; }
      outputPopup(ctx.root, { job, follow, title, anchor: e?.currentTarget, onClose: () => ctx.store.setEph({ llmOut: false }) });
      ctx.store.setEph({ llmOut: true });
    } });
}
