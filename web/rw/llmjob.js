import { h } from "./ui.js"; // added 2026-11-06 v0.10.2: jobText

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
