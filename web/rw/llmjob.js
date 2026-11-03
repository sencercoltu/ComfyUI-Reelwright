// Progress of a running LLM request (added 2026-11-03 v0.4.2). The backend sends reelwright.llm events tagged with
// the job id the editor chose; editor.js keeps the latest one per job in eph.llmJobs.

export function newJob(prefix = "llm") {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
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
