// Render tab: what to render, takes, cache keys, dependency chains, memory
// policy, the seam inspector, merge settings and autosaved versions.

// [OLD 2026-11-02 v0.3.5->v0.3.6] import { h, icon, button, toggle, segmented, select, number, section, field, dot, confirmInline, slider } from "../ui.js";
// [OLD 2026-11-03 v0.5.1->v0.6.0] import { h, icon, button, toggle, segmented, select, number, section, field, dot, confirmInline, slider, confirmDialog } from "../ui.js";  (confirmInline bars vanished on re-render)
import { h, icon, button, toggle, segmented, select, number, section, field, dot, slider, confirmDialog } from "../ui.js";
import { rw, viewURL } from "../api.js";
// [OLD 2026-11-03 v0.4.3->v0.5.0] import { continuityChains, fmtTime, sceneStarts, sceneIndex, findAsset, overlapSeconds } from "../model.js";
// [OLD 2026-11-03 v0.5.1->v0.6.0] import { continuityChains, fmtTime, sceneStarts, sceneIndex, findAsset, overlapSeconds, soundtrackLocked, playingTracks } from "../model.js";  (effective start / overlap helpers, normalize for the version diff)
import { continuityChains, fmtTime, sceneStarts, sceneIndex, findAsset, soundtrackLocked, playingTracks, effectiveStart, sceneOverlapAt, normalizeProject } from "../model.js";

const STATUS = {
  cached: ["ok", "on disk"], locked: ["ok", "locked"], stale: ["warn", "stale"], pending: ["empty", "not rendered"],
  missing: ["empty", "not rendered"], queued: ["busy", "queued"], rendering: ["busy", "rendering"], error: ["err", "failed"], unknown: ["empty", "unknown"],
};

function scopeBar(ctx) {
  const p = ctx.p;
  const s = ctx.scene;
  const { starts } = sceneStarts(p);
  const fromScene = p.scenes.find(x => p.ui.playhead >= starts[x.id] && p.ui.playhead < starts[x.id] + x.duration) || s;
  const fromIdx = sceneIndex(p, fromScene.id);
  const pend = ctx.pendingCount();
  // added 2026-11-03 v0.6.0: time estimate of the pending queue (plan.estimate), variants of the selected scene
  const est = estimateLabel(ctx.eph.plan?.estimate, pend);
  const nVar = variantsN(ctx);
  return h("div", { class: "rw-row wrap rw-scope" },
    button({ label: pend === null ? "Render pending" : `Render pending · ${pend}`, icon: "play", variant: "primary", help: "render.scope.pending", onClick: () => ctx.actions.run("pending") }),
    est && h("span", { class: "rw-dim small mono rw-estimate", help: "render.estimate", title: est.title }, est.text), // added 2026-11-03 v0.6.0
    button({ label: `Selected: ${s.title}`, help: "render.scope.selected", onClick: () => ctx.actions.run("selected", [s.id]) }),
    button({ label: `From playhead (${String(fromIdx + 1).padStart(2, "0")} →)`, help: "render.scope.from", onClick: () => ctx.actions.run("from", [fromScene.id]) }),
    // [OLD 2026-11-03 v0.5.1->v0.6.0] button({ label: "Everything", help: "render.scope.all", onClick: e => confirmInline(e.currentTarget.parentElement, "Re-render every scene, even ones already on disk?", () => ctx.actions.run("all")) }),  (the inline bar vanished on re-render)
    button({ label: "Everything", help: "render.scope.all", onClick: async () => {
      const n = ctx.p.scenes.filter(x => !x.lock).length;
      if (await confirmDialog(ctx.root, { title: "Re-render every scene?", confirmLabel: `Render ${n} scene${n === 1 ? "" : "s"}`,
        message: "Every scene that is not locked is rendered again, even the ones already on disk. The takes you have stay on disk; the new takes are starred." })) ctx.actions.run("all");
    } }),
    button({ label: "New take of selected", icon: "refresh", help: "render.scope.take", onClick: () => ctx.actions.run("take", [s.id]) }),
    // added 2026-11-03 v0.6.0: n takes of the selected scene in one run (action "variants"); A/B compare picks one
    h("span", { class: "rw-row rw-variants", help: "render.variants" },
      number({ value: nVar, min: 2, max: 8, width: "52px", key: "render-variants-n", help: "render.variants.n", onChange: v => ctx.store.setEph({ variantsN: clampVariants(v) }) }),
      button({ label: `Variants of selected`, icon: "copy", help: "render.variants", onClick: () => queueVariants(ctx, s, variantsN(ctx)) })),
    h("span", { class: "rw-flex" }),
    segmented({ value: p.global.quality, help: "render.quality", options: [
      { value: "draft", label: `Draft · ${p.global.draft.scale}× · ${p.global.draft.steps} steps`, help: "render.quality.draft" },
      { value: "final", label: "Final", help: "render.quality.final" }],
    onChange: v => ctx.actions.edit(q => { q.global.quality = v; }) }),
    button({ label: "Stop", icon: "stop", help: "render.stop", variant: "danger-ghost", onClick: () => ctx.host.interrupt() }));
}

/* [OLD 2026-11-02 v0.2.2->v0.3.0] one line for the current pass only; no scene count or overall progress
function runBanner(ctx) {
  const prog = Object.values(ctx.eph.progress).find(x => !["done", "cached", "error"].includes(x.phase));
  if (!ctx.eph.running && !prog) return null;
  const s = prog && ctx.p.scenes.find(x => x.id === prog.scene_id);
  return h("div", { class: "rw-banner info", help: "render.banner" }, icon("render", 14),
    h("b", null, "Rendering"),
    prog ? h("span", null, `${s?.title || prog.scene_id} · pass ${prog.pass}/${prog.passes} · ${prog.phase}${prog.steps ? ` · step ${prog.step}/${prog.steps}` : ""}${prog.message ? " · " + prog.message : ""}`) : h("span", null, "waiting for ComfyUI…"),
    prog?.steps ? h("span", { class: "rw-meter-bar grow" }, h("span", { class: "rw-meter-fill rw-bg-pic", style: { width: Math.round((prog.step / prog.steps) * 100) + "%" } })) : h("span", { class: "rw-flex" }));
}
*/
// added 2026-11-02 v0.3.0: "scene k of n" with a bar for the scene and one for the whole run
function runBanner(ctx) {
  const r = ctx.runProgress?.();
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const prog = r?.current || Object.values(ctx.eph.progress).find(x => !["done", "cached", "error"].includes(x.phase));  (a skipped scene counted as running)
  const prog = r?.current || Object.values(ctx.eph.progress).find(x => !isFinal(ctx, x.phase));
  if (!ctx.eph.running && !prog) return null;
  const s = prog && ctx.p.scenes.find(x => x.id === prog.scene_id);
  const pct = v => Math.round(Math.max(0, Math.min(1, v)) * 100);
  const bar = (label, v, cls, help) => h("div", { class: "rw-progress", help },
    h("span", { class: "rw-dim" }, label),
    h("span", { class: "rw-meter-bar" }, h("span", { class: ["rw-meter-fill", cls], style: { width: pct(v) + "%" } })),
    h("span", { class: "mono rw-dim" }, pct(v) + "%"));
  const scenePart = r ? r.scenePart : prog?.steps ? prog.step / prog.steps : 0;
  // [OLD 2026-11-03 v0.6.0 review] const head = r ? `Scene ${Math.max(1, r.index)} of ${r.n}` : "Rendering";
  const head = runHead(r); // added 2026-11-03 v0.6.0 review: "Take k of n" for variants
  /* [OLD 2026-11-03 v0.5.1->v0.6.0] a pass from the pass cache read "reuse"
  const detail = prog ? `${s?.title || prog.scene_id} · pass ${prog.pass}/${prog.passes} · ${prog.phase}${prog.steps ? ` · step ${prog.step}/${prog.steps}` : ""}${prog.message ? " · " + prog.message : ""}`
    : r && r.done >= r.n ? "finishing…" : "waiting for ComfyUI…";
  [/OLD] */
  const detail = runDetail(ctx, r, prog, s); // added 2026-11-03 v0.6.0: "from cache" for a pass the pass cache had
  /* [OLD 2026-11-02 v0.3.4->v0.3.5] no latent preview (ComfyUI painted it over the whole node)
  return h("div", { class: "rw-banner info", help: "render.banner" }, icon("render", 14),
    h("div", { class: "rw-run" },
      h("div", { class: "rw-row" }, h("b", null, head), h("span", { class: "rw-ellipsis" }, detail),
        r?.reused?.length ? h("span", { class: "rw-dim small" }, `· ${r.reused.length} reused`) : null),
      bar("Scene", scenePart, "rw-bg-pic", "render.progress.scene"),
      r && bar("Total", r.total, "rw-bg-aud", "render.progress.total")));
  [/OLD] */
  // added 2026-11-02 v0.3.5: a small window with the latest latent preview of the scene being sampled
  /* [OLD 2026-11-02 v0.3.7->v0.3.8] a new <img> on every re-render, straight from the event's URL (see web/rw/preview.js)
  const pv = ctx.eph.preview;
  const pvScene = pv && ctx.p.scenes.find(x => x.id === pv.scene_id);
  const preview = pv?.image && h("figure", { class: "rw-run-preview", help: "render.preview" },
    h("img", { src: pv.image, alt: "" }),
    // [OLD 2026-11-02 v0.3.6->v0.3.7] h("figcaption", { class: "mono" }, `${pvScene ? String(sceneIndex(ctx.p, pvScene.id) + 1).padStart(2, "0") : ""} · pass ${pv.pass}/${pv.passes} · ${pv.step}/${pv.steps}`));
    h("figcaption", { class: "mono" }, [pvScene && String(sceneIndex(ctx.p, pvScene.id) + 1).padStart(2, "0"), pv.passes && `pass ${pv.pass}/${pv.passes}`, pv.steps && `${pv.step}/${pv.steps}`].filter(Boolean).join(" · ")));
  [/OLD] */
  // added 2026-11-02 v0.3.8: the editor's one preview window, moved into this banner (it updates itself in place)
  const preview = ctx.previewFigure?.() || null;
  /* [OLD 2026-11-03 v0.5.1->v0.6.0] onProgress (below) updates the head, the detail and the bars in place; they need hooks
  return h("div", { class: "rw-banner info", help: "render.banner" }, icon("render", 14),
    h("div", { class: "rw-run" },
      h("div", { class: "rw-row" }, h("b", null, head), h("span", { class: "rw-ellipsis" }, detail),
        r?.reused?.length ? h("span", { class: "rw-dim small" }, `· ${r.reused.length} reused`) : null),
      bar("Scene", scenePart, "rw-bg-pic", "render.progress.scene"),
      r && bar("Total", r.total, "rw-bg-aud", "render.progress.total")),
    preview);
  [/OLD] */
  const hooked = (el, name) => { el.dataset.bar = name; return el; };
  return h("div", { class: "rw-banner info", help: "render.banner" }, icon("render", 14),
    h("div", { class: "rw-run" },
      h("div", { class: "rw-row" }, h("b", { class: "rw-run-head" }, head), h("span", { class: "rw-ellipsis rw-run-detail", title: detail }, detail),
        r?.reused?.length ? h("span", { class: "rw-dim small" }, `· ${r.reused.length} reused`) : null),
      hooked(bar("Scene", scenePart, "rw-bg-pic", "render.progress.scene"), "scene"),
      r && hooked(bar("Total", r.total, "rw-bg-aud", "render.progress.total"), "total")),
    preview);
}

// ---- v0.6.0 helpers (added 2026-11-03 v0.6.0) ------------------------------------------------------------------

// true for progress phases after which a scene no longer renders (ctx.isFinal; done/cached/error/skipped)
function isFinal(ctx, phase) {
  return ctx.isFinal ? ctx.isFinal(phase) : ["done", "cached", "error", "skipped"].includes(phase);
}
const PHASE_TEXT = { reuse: "from cache" };
// "pass 2/3 · sample · step 9/20" for a progress event; a pass read from the pass cache says "from cache"
function progressText(prog) {
  const phase = PHASE_TEXT[prog.phase] || prog.phase;
  const step = prog.steps && prog.phase !== "reuse" ? ` · step ${prog.step}/${prog.steps}` : "";
  const msg = prog.message && prog.phase !== "reuse" ? " · " + prog.message : "";
  return `pass ${prog.pass}/${prog.passes} · ${phase}${step}${msg}`;
}
// added 2026-11-03 v0.6.0 review: the banner's head: "Scene k of n", or "Take k of n" for a variants run (n takes of a
// scene, ctx.runProgress counts takes)
function runHead(r) {
  if (!r) return "Rendering";
  return `${r.unit === "take" ? "Take" : "Scene"} ${Math.max(1, r.index)} of ${r.n}`;
}
function runDetail(ctx, r, prog, s) {
  return prog ? `${s?.title || prog.scene_id} · ${progressText(prog)}` : r && r.done >= r.n ? "finishing…" : "waiting for ComfyUI…";
}
// the busy text of a row in the takes table
function rowBusyText(prog) {
  return `${PHASE_TEXT[prog.phase] || prog.phase} ${prog.pass}/${prog.passes}${prog.steps && prog.phase !== "reuse" ? " · " + prog.step + "/" + prog.steps : ""}`;
}

// Progress events while the Render tab is open: the banner and the scene's row change in place (no re-render, so the
// A/B videos, open menus and scroll positions stay). The editor still re-renders when a scene starts or ends or its
// phase or pass changes.
export function onProgress(ctx, d) {
  const tab = ctx.root.querySelector(".rw-render-tab");
  if (!tab) return;
  const r = ctx.runProgress?.();
  const prog = r?.current || Object.values(ctx.eph.progress).find(x => !isFinal(ctx, x.phase));
  const run = tab.querySelector(".rw-run");
  if ((ctx.eph.running || prog) && !run) { ctx.store.notify(); return; } // the banner appears with the next render
  if (run) {
    const s = prog && ctx.p.scenes.find(x => x.id === prog.scene_id);
    const set = (sel, t) => { const el = run.querySelector(sel); if (el && el.textContent !== t) { el.textContent = t; if (el.title !== undefined) el.title = t; } };
    // [OLD 2026-11-03 v0.6.0 review] set(".rw-run-head", r ? `Scene ${Math.max(1, r.index)} of ${r.n}` : "Rendering");
    set(".rw-run-head", runHead(r)); // added 2026-11-03 v0.6.0 review
    set(".rw-run-detail", runDetail(ctx, r, prog, s));
    const pct = v => Math.round(Math.max(0, Math.min(1, v)) * 100);
    const bar = (name, v) => {
      const el = run.querySelector(`[data-bar="${name}"]`);
      if (!el) return;
      el.querySelector(".rw-meter-fill").style.width = pct(v) + "%";
      el.querySelector(".mono").textContent = pct(v) + "%";
    };
    bar("scene", r ? r.scenePart : prog?.steps ? prog.step / prog.steps : 0);
    if (r) bar("total", r.total);
  }
  const cell = d?.scene_id && tab.querySelector(`[data-run-status="${CSS.escape(d.scene_id)}"] .rw-status-text`);
  if (cell && !isFinal(ctx, d.phase)) cell.textContent = rowBusyText(d);
}

// "≈ 14 min" for the pending queue; null without a plan or with nothing pending
function fmtDuration(sec) {
  if (!(sec >= 0)) return "";
  if (sec < 60) return `${Math.max(1, Math.round(sec))} s`;
  const m = Math.round(sec / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}
function estimateLabel(est, pend) {
  if (!est || !pend) return null;
  const n = est.scenes ?? pend, unknown = est.unknown || 0;
  if (est.seconds == null) return { text: "no time estimate yet", title: "No earlier renders with these settings to learn from." };
  const extra = unknown ? ` + ${unknown} scene${unknown === 1 ? "" : "s"} without history` : "";
  return { text: `≈ ${fmtDuration(est.seconds)}${extra}`, title: `About ${fmtDuration(est.seconds)} for ${n - unknown} of ${n} pending scene${n === 1 ? "" : "s"}, learned from earlier renders.` };
}

const clampVariants = v => Math.max(2, Math.min(8, Math.round(Number(v) || 3)));
const variantsN = ctx => clampVariants(ctx.eph.variantsN ?? 3);
async function queueVariants(ctx, s, n) {
  const ok = await ctx.actions.run("variants", [], { scene_ids: [s.id], n });
  // the takes list of the scene opens, so the new takes can go into the A/B compare when they are done
  if (ok) ctx.store.setEph({ openTakes: { ...(ctx.eph.openTakes || {}), [s.id]: true } });
}

// The scenes that continue from scene `id` (its chain after it, up to a fresh start or a locked scene): they start
// from its pixels, so they render again with it.
function dependents(p, id) {
  const i = sceneIndex(p, id);
  const out = [];
  for (let k = i + 1; k < p.scenes.length; k++) {
    if (effectiveStart(p, k) === "fresh" || p.scenes[k].lock) break;
    out.push(p.scenes[k].id);
  }
  return out;
}
const num2 = (p, id) => String(sceneIndex(p, id) + 1).padStart(2, "0");

// Line diff (longest common subsequence) of two texts: [{op: "=" | "-" | "+", text}]
export function lineDiff(a, b) {
  const lines = t => (t == null || t === "" ? [] : String(t).split("\n")); // an empty text has no lines
  const x = lines(a), y = lines(b);
  const n = x.length, m = y.length;
  if (n * m > 250000) return [...x.map(t => ({ op: "-", text: t })), ...y.map(t => ({ op: "+", text: t }))]; // too big to align
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) { out.push({ op: "=", text: x[i] }); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) out.push({ op: "-", text: x[i++] });
    else out.push({ op: "+", text: y[j++] });
  }
  while (i < n) out.push({ op: "-", text: x[i++] });
  while (j < m) out.push({ op: "+", text: y[j++] });
  return out;
}

// The prompt of the starred take (plan.starred_prompts) against the prompt a render would send now (plan.prompts),
// pass by pass; unchanged lines are folded to one line of context around each change.
function promptDiffView(plan) {
  const was = plan.starred_prompts || [], now = plan.prompts || [];
  const passes = Math.max(was.length, now.length);
  const blocks = [];
  let changed = 0;
  for (let k = 0; k < passes; k++) {
    if ((was[k] ?? null) === (now[k] ?? null)) continue;
    changed++;
    const head = passes > 1 ? `Pass ${k + 1}` : "Prompt";
    if (was[k] == null || now[k] == null) {
      blocks.push(h("div", { class: "rw-diff-pass" }, h("b", null, head), h("div", { class: "rw-dim small" }, was[k] == null ? "a new pass: the starred take had fewer passes" : "this pass is gone: the scene has fewer passes now")));
      continue;
    }
    const d = lineDiff(was[k], now[k]);
    const keep = d.map((x, i) => x.op !== "=" || d.slice(Math.max(0, i - 1), i + 2).some(y => y.op !== "="));
    const lines = [];
    d.forEach((x, i) => {
      if (keep[i]) lines.push(h("div", { class: ["rw-diff-line", x.op === "-" ? "del" : x.op === "+" ? "add" : "ctx"] }, h("span", { class: "rw-diff-op" }, x.op === "=" ? " " : x.op), x.text || " "));
      else if (keep[i - 1] !== false) lines.push(h("div", { class: "rw-diff-line gap" }, "⋯"));
    });
    blocks.push(h("div", { class: "rw-diff-pass" }, h("b", null, head), h("div", { class: "rw-diff mono" }, lines)));
  }
  return h("div", { class: "rw-diff-box", help: "render.diff" },
    h("div", { class: "rw-dim small" }, changed
      ? "What a render would send now, against the prompt of the starred take: − was sent then, + is sent now."
      : "The prompt text is the same as the starred take's. Something else changed: a setting, a reference file, a seed or the take it continues from."),
    blocks);
}

// Last run: scenes that failed or were skipped, or why the run never started (eph.lastRun from the "end" event)
function lastRunNote(ctx) {
  const lr = ctx.eph.lastRun;
  if (!lr || ctx.eph.running || ctx.eph.lastRunHidden === lr.at) return null;
  const failed = lr.failed || [], skipped = lr.skipped || [];
  // [OLD 2026-11-03 v0.6.0 review] if (!lr.rejected && !failed.length && !skipped.length) return null;
  // added 2026-11-03 v0.6.0 review: warnings (an extra take failed: a drift retake, variant 2..n; the scene kept its take)
  const warnings = lr.warnings || [];
  if (!lr.rejected && !failed.length && !skipped.length && !warnings.length) return null;
  const p = ctx.p;
  const title = id => p.scenes.find(s => s.id === id)?.title || id;
  const known = id => p.scenes.some(s => s.id === id);
  const line = (id, kind, text) => h("div", { class: "rw-lastrun-line" },
    known(id) ? h("button", { type: "button", class: "link mono", help: "render.table.scene", onClick: () => ctx.actions.select(id) }, num2(p, id)) : h("span", { class: "mono" }, "—"),
    h("b", null, title(id)), h("span", { class: kind === "failed" ? "rw-c-err" : "rw-c-warn" }, kind),
    h("span", { class: "rw-ellipsis rw-dim", title: text || "" }, text || ""));
  const again = [...failed, ...skipped].map(x => x.scene_id).filter(known);
  const ordered = p.scenes.map(s => s.id).filter(id => again.includes(id));
  // [OLD 2026-11-03 v0.6.0 review] const head = lr.rejected ? "Render not started" : [lr.interrupted ? "Render stopped" : "Last render", failed.length && `${failed.length} failed`, skipped.length && `${skipped.length} skipped`].filter(Boolean).join(" · ");
  const head = lr.rejected ? "Render not started" : [lr.interrupted ? "Render stopped" : "Last render", failed.length && `${failed.length} failed`, skipped.length && `${skipped.length} skipped`,
    warnings.length && `${warnings.length} warning${warnings.length === 1 ? "" : "s"}`].filter(Boolean).join(" · "); // added 2026-11-03 v0.6.0 review: warnings
  return h("div", { class: ["rw-banner", lr.rejected || failed.length ? "err" : "warn"], help: "render.lastRun" }, icon("warn", 14),
    h("div", { class: "rw-lastrun" },
      h("b", null, head),
      lr.rejected && h("div", { class: "rw-lastrun-msg" }, lr.error || "The project has errors (Issues)."),
      failed.map(x => line(x.scene_id, "failed", x.error)),
      skipped.map(x => line(x.scene_id, "skipped", x.reason)),
      warnings.map(x => line(x.scene_id, "warning", x.message))), // added 2026-11-03 v0.6.0 review
    ordered.length ? button({ label: `Render ${ordered.length === 1 ? "it" : "them"} again`, icon: "refresh", small: true, help: "render.lastRun.retry", onClick: () => ctx.actions.run("selected", ordered) }) : null,
    button({ icon: "close", small: true, variant: "ghost", help: "common.close", onClick: () => ctx.store.setEph({ lastRunHidden: lr.at }) }));
}

// "Continues from a different take": the take this scene would continue from is not the one its starred take used
function upstreamNote(ctx, s, plan) {
  const p = ctx.p;
  const i = sceneIndex(p, s.id);
  const prev = i > 0 ? p.scenes[i - 1] : null;
  const after = dependents(p, s.id);
  const ids = [s.id, ...after];
  const up = plan.upstream_take ? `its take ${plan.upstream_take}` : "a new take";
  return h("div", { class: "rw-trow-note warn", help: "render.table.upstream" }, icon("warn", 12),
    h("span", { class: "grow" }, `Continues from a different take: ${prev ? `${num2(p, prev.id)} ${prev.title}` : "the scene before"} now gives ${up}, but the starred take of this scene started from another one.`),
    button({ label: after.length ? `Re-render it and ${after.length} after it` : "Re-render it", icon: "refresh", small: true, variant: "warn-ghost", help: "render.table.upstream.rerender",
      onClick: () => ctx.actions.run("selected", ids) }));
}

// one button per pass of a long scene: a new seed for that pass only (earlier passes come from the pass cache)
function passRetakeRow(ctx, s, plan, starred) {
  const passes = plan?.passes || [];
  if (passes.length < 2) return null;
  return h("div", { class: "rw-row wrap rw-pass-retake", help: "render.passRetake" },
    h("span", { class: "rw-dim small" }, starred ? "Retake one pass:" : "Pass retake needs a starred take."),
    passes.map((ps, k) => button({ label: `Pass ${k + 1}`, small: true, help: "render.passRetake.pass", disabled: !starred,
      ariaLabel: `Retake pass ${k + 1} (${fmtTime(ps.start ?? 0, false)}–${fmtTime(ps.end ?? 0, false)})`,
      onClick: () => ctx.actions.run("pass_retake", [], { scene_id: s.id, pass: k + 1 }) })),
    h("span", { class: "rw-dim small" }, "A new seed for that pass; earlier passes are kept, later ones follow it."));
}

// A/B videos stay the same elements across re-renders, so a playing take keeps playing (as in the Files tab)
const abMedia = new WeakMap(); // ctx -> {a: {url, el}, b: {url, el}}
function abVideo(ctx, side, url) {
  let m = abMedia.get(ctx);
  if (!m) abMedia.set(ctx, m = {});
  if (m[side]?.url === url) return m[side].el;
  const el = h("video", { class: "rw-ab-video", src: url, controls: true, muted: side === "b", preload: "metadata", playsinline: true });
  m[side] = { url, el };
  return el;
}

// added 2026-11-05 v0.8.0: drift of a take (contract P2, render.py): take.drift = [{pass, source, frames, anchor_diff,
// color_shift, rgb_shift: [r, g, b], sharpness, level: "ok"|"warn"|"bad", handoff?, handoff_reason?, pass_cache?}]
// for each pass that continues from footage. The server sets `level` (analysis.drift_level); a take without it gets
// one from the same starting limits (analysis.DRIFT_LIMITS): anchor_diff and color_shift on a 0–255 scale, sharpness
// generated / guide (1 = the same).
const DRIFT_LIMITS = { anchor: [8, 16], color: [4, 10], sharpLow: [0.8, 0.6], sharpHigh: [1.25, 1.6] }; // [warn from, bad from]
const DRIFT_CLASS = { ok: "ok", warn: "warn", bad: "error", error: "error" };
function driftNumber(v) {
  if (Array.isArray(v)) return v.length ? Math.hypot(...v.map(x => Number(x) || 0)) : null;
  const n = Number(v);
  return v === null || v === undefined || !Number.isFinite(n) ? null : n;
}
function driftLevel(d) {
  if (DRIFT_CLASS[d?.level]) return DRIFT_CLASS[d.level];
  const a = driftNumber(d?.anchor_diff), c = driftNumber(d?.color_shift), s = driftNumber(d?.sharpness);
  if (a === null && c === null && s === null) return "";
  let lv = 0;
  const up = (v, [warn, bad]) => { if (v !== null) lv = Math.max(lv, v >= bad ? 2 : v >= warn ? 1 : 0); };
  up(a, DRIFT_LIMITS.anchor);
  up(c, DRIFT_LIMITS.color);
  if (s !== null) lv = Math.max(lv, s < DRIFT_LIMITS.sharpLow[1] || s > DRIFT_LIMITS.sharpHigh[1] ? 2 : s < DRIFT_LIMITS.sharpLow[0] || s > DRIFT_LIMITS.sharpHigh[0] ? 1 : 0);
  return ["ok", "warn", "error"][lv];
}
function driftOf(tk) {
  return Array.isArray(tk?.drift) ? tk.drift.filter(d => d && typeof d === "object") : [];
}
function driftWorst(tk) {
  const order = { "": 0, ok: 1, warn: 2, error: 3 };
  return driftOf(tk).map(driftLevel).reduce((a, b) => (order[b] > order[a] ? b : a), "");
}
function driftView(tk) {
  const list = driftOf(tk);
  if (!list.length) return null;
  const f = (v, n) => (v === null ? "–" : v.toFixed(n));
  const from = { prev_pass_tail: "the pass before", prev_scene_tail: "the tail of the scene before", prev_scene_last: "the last frame of the scene before" };
  return h("span", { class: "rw-drift mono", help: "render.take.drift" }, list.map(d => {
    const a = driftNumber(d.anchor_diff), c = driftNumber(d.color_shift), s = driftNumber(d.sharpness);
    const rgb = Array.isArray(d.rgb_shift) ? ` (r ${d.rgb_shift.map(x => (x > 0 ? "+" : "") + Number(x).toFixed(1)).join(" g ").replace(/ g ([^ ]+)$/, " b $1")})` : "";
    const title = `Pass ${d.pass ?? "?"}${from[d.source] ? ", continuing " + from[d.source] : ""}: anchor ${f(a, 1)} · colour ${f(c, 1)}${rgb} · sharpness ${f(s, 2)}`
      + (d.handoff ? ` · ${d.handoff} hand-off${d.handoff_reason ? " (" + d.handoff_reason + ")" : ""}` : "") + (d.pass_cache ? " · from the pass cache" : "");
    return h("span", { class: "rw-drift-pass", title },
      h("span", { class: ["rw-led", driftLevel(d)] }), h("b", null, `P${d.pass ?? "?"}`), `${f(a, 1)} · ${f(c, 1)} · ${f(s, 2)}`);
  }));
}
// added 2026-11-05 v0.8.0: the long-scene settings a take was made with (take.long), where they differ from the defaults
function longView(tk) {
  const L = tk?.long;
  if (!L || typeof L !== "object") return null;
  const tags = [];
  if (L.guide_vae) tags.push("guide " + String(L.guide_vae).replace(/\.safetensors$/, "").replace(/^minimax_h3_video_vae_/, ""));
  if (L.carry_audio === false) tags.push("picture-only seams");
  if (L.seam_video_ref === false) tags.push("no <Video 1>");
  if (L.handoff === "latent") tags.push("latent hand-off");
  if (L.pass_cache === "lossless") tags.push("lossless cache");
  return tags.length ? h("span", { class: "rw-dim small mono rw-take-long", help: "render.take.long", title: tags.join(" · ") }, tags.join(" · ")) : null;
}

// options of the next merge (not saved in the project): {draft, range: [from_id, to_id] | null, stems}
function mergeOpts(ctx) {
  const o = ctx.eph.mergeOpts || {};
  const ids = ctx.p.scenes.map(s => s.id);
  let range = Array.isArray(o.range) && o.range.length === 2 ? o.range.map(id => ids.includes(id) ? id : null) : null;
  if (range) {
    if (!range[0]) range[0] = ids[0];
    if (!range[1]) range[1] = ids[ids.length - 1];
    if (ids.indexOf(range[0]) > ids.indexOf(range[1])) range = [range[1], range[0]];
  }
  return { draft: !!o.draft, range, stems: !!o.stems };
}
function runMerge(ctx) {
  const o = mergeOpts(ctx);
  return ctx.actions.merge({ draft: o.draft, range: o.range, stems: o.stems });
}

// EBU R128 report of a stems merge: integrated loudness, loudness range and true peak of the mix and each stem
function loudnessReport(ctx, L) {
  if (!L || typeof L !== "object") return null;
  const v = (x, unit, digits = 1) => (typeof x === "number" && Number.isFinite(x) ? `${x.toFixed(digits)} ${unit}` : "silent");
  const trackName = key => {
    const id = key.slice(6);
    const t = ctx.p.soundtrack.find(x => x.id === id);
    const a = t && findAsset(ctx.p, t.asset);
    return a ? `Track ${a.code} · ${a.name || a.file}` : `Track ${id}`;
  };
  const rows = [["Mix", L.mix || L], ["Scenes", L.scenes], ...Object.keys(L).filter(k => k.startsWith("track_")).map(k => [trackName(k), L[k]])].filter(([, x]) => x && typeof x === "object");
  const hot = x => typeof x?.true_peak === "number" && x.true_peak > -1;
  return h("div", { class: "rw-loudness", help: "render.merge.report" },
    h("div", { class: "rw-subhead" }, "Loudness · EBU R128", typeof L.target === "number" ? h("span", { class: "rw-dim small" }, ` · target ${L.target} LUFS`) : null),
    h("div", { class: "rw-loud-grid" },
      ["", "Integrated", "Range", "True peak"].map(t => h("span", { class: "th rw-dim small" }, t)),
      rows.map(([name, x]) => [
        h("span", { class: "rw-ellipsis small" }, name),
        h("span", { class: "mono small" }, v(x.integrated, "LUFS")),
        h("span", { class: "mono small" }, v(x.lra, "LU")),
        h("span", { class: ["mono small", hot(x) && "rw-c-warn"], title: hot(x) ? "Above −1 dBTP: it may clip after conversion to MP3/AAC." : null }, v(x.true_peak, "dBTP")),
      ])));
}

// ---- version diff before a restore ----
const SECTION_NAMES = { subject_definitions: "subject definitions", summary: "summary", retention_analysis: "retention analysis", detailed_description: "detailed description", overall_soundscape: "soundscape", non_diegetic_music: "music" };
const clip = (t, n = 70) => { t = String(t ?? "").replace(/\s+/g, " ").trim(); return t.length > n ? t.slice(0, n - 1) + "…" : t; };
// JSON with sorted keys, so the same values written in another key order compare equal
const stable = x => JSON.stringify(x ?? null, (k, v) => (v && typeof v === "object" && !Array.isArray(v) ? Object.fromEntries(Object.keys(v).sort().map(key => [key, v[key]])) : v));
const same = (a, b) => stable(a) === stable(b);

// What restoring version `raw` changes in project `cur`: lines of plain text (now → this version)
export function versionDiff(cur, raw) {
  let old;
  try { old = normalizeProject(structuredClone(raw)); } catch { old = raw; }
  if (!old || !Array.isArray(old.scenes)) return ["This version could not be read."];
  const lines = [];
  if (cur.name !== old.name) lines.push(`Name: “${cur.name}” → “${old.name}”`);
  if (cur.slug !== old.slug) lines.push(`Folder: ${cur.slug} → ${old.slug} (renders are found in that folder)`);
  const curIds = new Set(cur.scenes.map(s => s.id)), oldIds = new Set(old.scenes.map(s => s.id));
  const back = old.scenes.filter(s => !curIds.has(s.id)), gone = cur.scenes.filter(s => !oldIds.has(s.id));
  const names = list => list.slice(0, 4).map(s => `“${s.title}”`).join(", ") + (list.length > 4 ? ` and ${list.length - 4} more` : "");
  if (back.length) lines.push(`Brings back ${back.length} scene${back.length === 1 ? "" : "s"}: ${names(back)}`);
  if (gone.length) lines.push(`Removes ${gone.length} scene${gone.length === 1 ? "" : "s"} added since: ${names(gone)}`);
  const changed = [];
  for (const s of cur.scenes) {
    const o = old.scenes.find(x => x.id === s.id);
    if (!o) continue;
    const bits = [];
    if (s.title !== o.title) bits.push(`title “${clip(s.title, 30)}” → “${clip(o.title, 30)}”`);
    if (Math.abs(s.duration - o.duration) > 1e-6) bits.push(`length ${s.duration.toFixed(2)} s → ${o.duration.toFixed(2)} s`);
    if (s.start?.mode !== o.start?.mode) bits.push(`start ${String(s.start?.mode).replace("_", " ")} → ${String(o.start?.mode).replace("_", " ")}`);
    const secs = Object.keys(SECTION_NAMES).filter(k => (s.prompt?.sections?.[k] || "") !== (o.prompt?.sections?.[k] || ""));
    if (secs.length) {
      const k = secs[0];
      bits.push(`prompt ${secs.map(x => SECTION_NAMES[x]).join(", ")} (${SECTION_NAMES[k]}: “${clip(s.prompt.sections[k], 40) || "empty"}” → “${clip(o.prompt.sections[k], 40) || "empty"}”)`);
    }
    if ((s.prompt?.raw || "") !== (o.prompt?.raw || "") || s.prompt?.mode !== o.prompt?.mode) bits.push("raw prompt");
    if (!same(s.prompt?.pass_prompts, o.prompt?.pass_prompts)) bits.push("pass prompts");
    if (!same(s.shots, o.shots)) bits.push(s.shots.length === o.shots.length ? "shots" : `shots ${s.shots.length} → ${o.shots.length}`);
    if (!same(s.dialogue, o.dialogue)) bits.push(s.dialogue.length === o.dialogue.length ? "dialogue" : `dialogue lines ${s.dialogue.length} → ${o.dialogue.length}`);
    if (!same(s.refs, o.refs)) bits.push("references");
    if (!same(s.cast, o.cast)) bits.push("cast");
    if (!same(s.overrides, o.overrides)) bits.push("overrides");
    if (!!s.lock !== !!o.lock) bits.push(o.lock ? "locked" : "unlocked");
    // [OLD 2026-11-05 v0.6.1->v0.7.0] if (!same(s.trim, o.trim) || !same(s.transition, o.transition)) bits.push("trim or cut");
    if (!same(s.trim, o.trim)) bits.push("trim"); // added 2026-11-05 v0.7.0: the cut is scene.merge (scene.transition is no longer read)
    if (!same(s.merge, o.merge)) bits.push("in the cut"); // added 2026-11-05 v0.7.0: join, fades, sound, colour
    if (bits.length) changed.push(`“${clip(s.title, 34)}”: ${bits.join("; ")}`);
  }
  if (changed.length) {
    lines.push(`Changes ${changed.length} scene${changed.length === 1 ? "" : "s"}:`);
    for (const c of changed.slice(0, 6)) lines.push("  • " + c);
    if (changed.length > 6) lines.push(`  • … and ${changed.length - 6} more`);
  }
  const common = cur.scenes.map(s => s.id).filter(id => oldIds.has(id));
  const oldOrder = old.scenes.map(s => s.id).filter(id => curIds.has(id));
  if (!same(common, oldOrder)) lines.push("Scene order differs.");
  const g = cur.global || {}, og = old.global || {};
  const gbits = [];
  if (g.quality !== og.quality) gbits.push(`quality ${g.quality} → ${og.quality}`);
  if (g.output?.width !== og.output?.width || g.output?.height !== og.output?.height) gbits.push(`size ${g.output?.width}×${g.output?.height} → ${og.output?.width}×${og.output?.height}`);
  if (g.sampling?.steps !== og.sampling?.steps) gbits.push(`steps ${g.sampling?.steps} → ${og.sampling?.steps}`);
  if (g.sampling?.seed !== og.sampling?.seed || g.sampling?.seed_mode !== og.sampling?.seed_mode) gbits.push("seed");
  const groups = { models: "models", loras: "LoRAs", draft: "draft", defaults: "new-scene defaults", long: "long scenes", memory: "memory", continuity: "continuity", llm: "LLM", merge: "merge" };
  for (const [k, label] of Object.entries(groups)) if (!same(g[k], og[k])) gbits.push(label);
  const sampOther = { ...(g.sampling || {}), steps: 0, seed: 0, seed_mode: "" }, oSampOther = { ...(og.sampling || {}), steps: 0, seed: 0, seed_mode: "" };
  if (!same(sampOther, oSampOther)) gbits.push("sampler");
  if (gbits.length) lines.push(`Global: ${gbits.join(", ")}`);
  const count = (key, word) => {
    const a = cur[key] || [], b = old[key] || [];
    if (same(a, b)) return;
    lines.push(a.length === b.length ? `${word}: changed` : `${word}: ${a.length} → ${b.length}`);
  };
  count("assets", "Assets"); count("cast", "Cast"); count("soundtrack", "Soundtrack tracks"); count("markers", "Markers");
  const t0 = sceneStarts(cur).total, t1 = sceneStarts(old).total;
  if (Math.abs(t0 - t1) > 1e-6) lines.push(`Film length ${fmtTime(t0)} → ${fmtTime(t1)}`);
  return lines.length ? lines : ["This version is the same as the project now."];
}

async function restoreVersion(ctx, x, day, time) {
  let r;
  try { r = await rw.version(ctx.p.slug, x.name); }
  catch (err) { ctx.actions.toast("Could not read the version: " + err.message, "error"); return; }
  const lines = versionDiff(ctx.p, r.project);
  const msg = h("div", { class: "rw-vdiff" },
    h("div", { class: "rw-dim" }, "Compared with the project now (now → this version):"),
    lines.map(t => h("div", { class: t.startsWith("  ") ? "rw-vdiff-sub" : "rw-vdiff-line" }, t.trim())),
    h("div", { class: "rw-dim" }, "Restoring replaces the project with this version. Ctrl+Z brings back what you have now."));
  if (!(await confirmDialog(ctx.root, { title: `Restore the version from ${day} ${time}?`, confirmLabel: "Restore", danger: false, message: msg, help: "render.versions.diff" }))) return;
  ctx.store.replaceProject(r.project, { label: `Restore version ${time}` });
  ctx.actions.toast("Version restored. Ctrl+Z undoes this.", "ok");
}

// added 2026-11-02 v0.2.0: the take a merge would use for a scene (starred, or newest when Merge uses latest)
function mergeTake(ctx, sceneId) {
  const t = ctx.takesFor(sceneId);
  if (ctx.p.global.merge.use === "latest") return [...t.takes].sort((a, b) => (b.created || 0) - (a.created || 0))[0] || null;
  return ctx.starredTake(sceneId);
}
const baseName = rel => (rel || "").split("/").pop();

function takesTable(ctx) {
  const p = ctx.p;
  const open = ctx.eph.openTakes || {};
  const rows = [];
  /* [OLD 2026-11-03 v0.5.1->v0.6.0] a skipped scene counted as busy; no last-run result, estimate, kept passes, upstream warning, prompt diff or pass retake; take delete used the inline bar that vanished on re-render
  p.scenes.forEach((s, i) => {
    const st = ctx.statusOf(s.id);
    const [cls, label] = STATUS[st] || STATUS.unknown;
    const t = ctx.takesFor(s.id);
    const plan = ctx.planFor(s.id);
    const prog = ctx.eph.progress[s.id];
    const busy = prog && !["done", "cached", "error"].includes(prog.phase);
    rows.push(h("div", { class: ["rw-trow", s.id === ctx.scene.id && "on", busy && "busy"] },
      h("span", { class: "mono" }, String(i + 1).padStart(2, "0")),
      h("button", { type: "button", class: "link rw-ellipsis", help: "render.table.scene", onClick: () => ctx.actions.select(s.id) }, s.title, s.lock ? h("span", { class: "rw-dim" }, " · locked") : null),
      h("span", { class: "rw-status st-" + st, help: "status." + st }, dot(cls, "status." + st),
        busy ? `${prog.phase} ${prog.pass}/${prog.passes}${prog.steps ? " · " + prog.step + "/" + prog.steps : ""}` : label),
      h("button", { type: "button", class: "link mono", help: "render.table.takes", onClick: () => ctx.store.setEph({ openTakes: { ...open, [s.id]: !open[s.id] } }) },
        t.takes.length ? `${t.starred || "—"} ★ /${t.takes.length}` : "—", icon(open[s.id] ? "chevDown" : "chevRight", 11)),
      // added 2026-11-02 v0.2.0: rendered file of the take the merge uses
      (() => {
        const tk = mergeTake(ctx, s.id);
        const rel = tk?.files?.video;
        return rel ? h("a", { class: "rw-tfile mono rw-ellipsis", href: viewURL(rel), target: "_blank", rel: "noopener", title: "output/" + rel, help: "render.table.file" }, baseName(rel))
          : h("span", { class: "rw-dim", help: "render.table.file" }, "—");
      })(),
      h("span", { class: "mono rw-dim", help: "render.cacheKey" }, plan?.key ? plan.key.slice(0, 4) + "…" + plan.key.slice(-2) : "—"),
      h("span", { class: "rw-dim small", help: "render.table.passes" }, plan?.passes ? `${plan.passes.length} pass${plan.passes.length > 1 ? "es" : ""}` : ""),
      h("span", { class: "mono", style: { "text-align": "right" } }, s.duration.toFixed(2) + " s")));
    if (open[s.id]) {
      rows.push(h("div", { class: "rw-takes" }, t.takes.length ? t.takes.map(tk => h("div", { class: ["rw-take", tk.id === t.starred && "on"] },
        h("button", { type: "button", class: ["rw-star", tk.id === t.starred && "on"], help: "render.take.star", "aria-label": "Star this take",
          onClick: async () => { try { await rw.star(p.slug, s.id, tk.id); await ctx.actions.refreshTakes(); ctx.store.refreshPlan(); } catch (err) { ctx.actions.toast(err.message, "error"); } } },
        icon(tk.id === t.starred ? "starFill" : "star", 13)),
        tk.files?.first ? h("img", { class: "rw-take-thumb", src: viewURL(tk.files.first), alt: "" }) : h("span", { class: "rw-take-thumb" }),
        h("b", { class: "mono" }, tk.id),
        h("span", { class: "rw-tag" }, tk.quality || "final"),
        // added 2026-11-02 v0.2.0: file name of this take
        tk.files?.video && h("span", { class: "mono small rw-dim rw-ellipsis rw-take-file", title: "output/" + tk.files.video, help: "render.take.file" }, baseName(tk.files.video)),
        h("span", { class: "mono rw-dim" }, `${(tk.seconds ?? 0).toFixed(2)} s · ${tk.frames ?? "?"} f`),
        h("span", { class: "rw-dim small" }, tk.created ? new Date(tk.created * (tk.created < 1e12 ? 1000 : 1)).toLocaleString() : ""),
        tk.face && Object.keys(tk.face).length ? h("span", { class: "mono small rw-c-aud", help: "cast.appearances.score" }, "face " + Object.values(tk.face).map(v => Number(v).toFixed(2)).join(" / ")) : null,
        h("span", { class: "rw-flex" }),
        button({ label: "A", small: true, help: "render.take.compareA", variant: ctx.eph.compare?.a?.take === tk.id ? "accent-ghost" : "ghost", onClick: () => ctx.store.setEph({ compare: { ...(ctx.eph.compare || {}), a: { scene: s.id, take: tk.id, url: viewURL(tk.files?.video) } } }) }),
        button({ label: "B", small: true, help: "render.take.compareB", variant: ctx.eph.compare?.b?.take === tk.id ? "accent-ghost" : "ghost", onClick: () => ctx.store.setEph({ compare: { ...(ctx.eph.compare || {}), b: { scene: s.id, take: tk.id, url: viewURL(tk.files?.video) } } }) }),
        tk.files?.video && h("a", { class: "rw-btn rw-btn-ghost rw-btn-sm", href: viewURL(tk.files.video), target: "_blank", rel: "noopener", help: "render.take.open" }, icon("eye", 12), h("span", null, "Open")),
        button({ icon: "trash", small: true, variant: "ghost", help: "render.take.delete", onClick: e => confirmInline(e.currentTarget.closest(".rw-take"), `Delete take ${tk.id}?`, async () => {
          try { await rw.deleteTake(p.slug, s.id, tk.id); await ctx.actions.refreshTakes(); ctx.store.refreshPlan(); } catch (err) { ctx.actions.toast(err.message, "error"); }
        }) })))
        : h("div", { class: "rw-empty sm" }, "No takes yet. Render this scene to create one.")));
    }
  });
  [/OLD] */
  // added 2026-11-03 v0.6.0: busy uses isFinal (skipped is finished); the last run's failure or skip per scene; time
  // estimate and passes kept in the pass cache; "continues from a different take" with a re-render of it and its
  // dependents; the prompt diff against the starred take ("why?"); a hand-picked star; a pass retake per pass; the A/B
  // compare of the two newest takes (after variants); deleting a take asks in a dialog
  const openDiff = ctx.eph.openDiff || {};
  p.scenes.forEach((s, i) => {
    const st = ctx.statusOf(s.id);
    const [cls, label] = STATUS[st] || STATUS.unknown;
    const t = ctx.takesFor(s.id);
    const plan = ctx.planFor(s.id);
    const prog = ctx.eph.progress[s.id];
    const busy = prog && !isFinal(ctx, prog.phase);
    const result = busy ? null : ctx.sceneRunResult?.(s.id) || null;
    const pending = ["stale", "missing", "pending"].includes(st);
    const canDiff = st === "stale" && Array.isArray(plan?.starred_prompts) && Array.isArray(plan?.prompts);
    const est = pending && typeof plan?.estimate_seconds === "number" ? fmtDuration(plan.estimate_seconds) : "";
    const nPass = plan?.passes?.length || 0;
    const kept = pending && plan?.cached_passes > 0 ? plan.cached_passes : 0;
    rows.push(h("div", { class: ["rw-trow", s.id === ctx.scene.id && "on", busy && "busy"] },
      h("span", { class: "mono" }, String(i + 1).padStart(2, "0")),
      h("button", { type: "button", class: "link rw-ellipsis", help: "render.table.scene", onClick: () => ctx.actions.select(s.id) }, s.title, s.lock ? h("span", { class: "rw-dim" }, " · locked") : null),
      h("span", { class: "rw-tstatus" },
        h("span", { class: "rw-status st-" + st, help: "status." + st, dataset: { runStatus: s.id } }, dot(cls, "status." + st),
          h("span", { class: "rw-status-text" }, busy ? rowBusyText(prog) : label)),
        result && h("span", { class: ["rw-runres", result.kind], help: "render.table." + result.kind, title: result.message || null }, result.kind),
        est && h("span", { class: "rw-dim small mono", help: "render.table.estimate" }, "≈ " + est),
        canDiff && h("button", { type: "button", class: ["link", "rw-why", openDiff[s.id] && "on"], help: "render.table.diff",
          onClick: () => ctx.store.setEph({ openDiff: { ...openDiff, [s.id]: !openDiff[s.id] } }) }, "why?")),
      h("button", { type: "button", class: ["link mono", plan?.manual_star && "rw-manual"], help: plan?.manual_star ? "render.table.manualStar" : "render.table.takes", onClick: () => ctx.store.setEph({ openTakes: { ...open, [s.id]: !open[s.id] } }) },
        t.takes.length ? `${t.starred || "—"} ★ /${t.takes.length}` : "—", plan?.manual_star ? h("span", { class: "rw-manual-mark" }, icon("pointer", 10)) : null, icon(open[s.id] ? "chevDown" : "chevRight", 11)),
      (() => {
        const tk = mergeTake(ctx, s.id);
        const rel = tk?.files?.video;
        return rel ? h("a", { class: "rw-tfile mono rw-ellipsis", href: viewURL(rel), target: "_blank", rel: "noopener", title: "output/" + rel, help: "render.table.file" }, baseName(rel))
          : h("span", { class: "rw-dim", help: "render.table.file" }, "—");
      })(),
      h("span", { class: "mono rw-dim", help: "render.cacheKey" }, plan?.key ? plan.key.slice(0, 4) + "…" + plan.key.slice(-2) : "—"),
      // [OLD 2026-11-05 v0.7.0->v0.8.0] h("span", { class: "rw-dim small", help: kept ? "render.table.cachedPasses" : "render.table.passes" }, nPass ? `${nPass} pass${nPass > 1 ? "es" : ""}` : "",
      // [OLD 2026-11-05 v0.7.0->v0.8.0]   kept ? h("span", { class: "rw-c-aud" }, ` · ${kept} kept`) : null),
      // added 2026-11-05 v0.8.0: a light for the worst drift of the starred take's continuing passes
      h("span", { class: "rw-dim small", help: kept ? "render.table.cachedPasses" : "render.table.passes" }, nPass ? `${nPass} pass${nPass > 1 ? "es" : ""}` : "",
        kept ? h("span", { class: "rw-c-aud" }, ` · ${kept} kept`) : null,
        (lv => lv ? h("span", { class: ["rw-led", lv], help: "render.table.drift", style: { "margin-left": "6px", "vertical-align": "1px" } }) : null)(driftWorst(ctx.starredTake(s.id)))),
      h("span", { class: "mono", style: { "text-align": "right" } }, s.duration.toFixed(2) + " s")));
    if (plan?.upstream_changed && !busy) rows.push(upstreamNote(ctx, s, plan));
    if (canDiff && openDiff[s.id]) rows.push(promptDiffView(plan));
    if (open[s.id]) {
      const starred = t.takes.find(x => x.id === t.starred) || null;
      const newest = [...t.takes].sort((a, b) => (b.created || 0) - (a.created || 0)).slice(0, 2);
      const setAB = (a, b) => ctx.store.setEph({ compare: { a: { scene: s.id, take: a.id, url: viewURL(a.files?.video) }, b: { scene: s.id, take: b.id, url: viewURL(b.files?.video) } } });
      const removeTake = async tk => {
        if (!(await confirmDialog(ctx.root, { title: `Delete take ${tk.id} of “${s.title}”?`, confirmLabel: "Delete take",
          message: `Its video, frames and tail clip are removed from disk for good.${tk.id === t.starred ? " It is the starred take: the scene uses its next newest take, or needs rendering again." : ""}` }))) return;
        try { await rw.deleteTake(p.slug, s.id, tk.id); await ctx.actions.refreshTakes(); ctx.store.refreshPlan(); } catch (err) { ctx.actions.toast(err.message, "error"); }
      };
      rows.push(h("div", { class: "rw-takes" },
        plan?.manual_star ? h("div", { class: "rw-dim small", help: "render.table.manualStar" }, `You starred ${t.starred} by hand. Renders keep your choice; a new take of this scene is starred when it is made.`) : null,
        newest.length === 2 && h("div", { class: "rw-row" }, button({ label: `Compare ${newest[1].id} and ${newest[0].id}`, icon: "compare", small: true, help: "render.take.compareNewest", onClick: () => setAB(newest[1], newest[0]) })),
        passRetakeRow(ctx, s, plan, starred),
        t.takes.length ? t.takes.map(tk => h("div", { class: ["rw-take", tk.id === t.starred && "on"] },
        h("button", { type: "button", class: ["rw-star", tk.id === t.starred && "on"], help: "render.take.star", "aria-label": "Star this take",
          onClick: async () => { try { await rw.star(p.slug, s.id, tk.id); await ctx.actions.refreshTakes(); ctx.store.refreshPlan(); } catch (err) { ctx.actions.toast(err.message, "error"); } } },
        icon(tk.id === t.starred ? "starFill" : "star", 13)),
        tk.files?.first ? h("img", { class: "rw-take-thumb", src: viewURL(tk.files.first), alt: "" }) : h("span", { class: "rw-take-thumb" }),
        h("b", { class: "mono" }, tk.id),
        h("span", { class: "rw-tag" }, tk.quality || "final"),
        tk.files?.video && h("span", { class: "mono small rw-dim rw-ellipsis rw-take-file", title: "output/" + tk.files.video, help: "render.take.file" }, baseName(tk.files.video)),
        h("span", { class: "mono rw-dim" }, `${(tk.seconds ?? 0).toFixed(2)} s · ${tk.frames ?? "?"} f`),
        h("span", { class: "rw-dim small" }, tk.created ? new Date(tk.created * (tk.created < 1e12 ? 1000 : 1)).toLocaleString() : ""),
        tk.face && Object.keys(tk.face).length ? h("span", { class: "mono small rw-c-aud", help: "cast.appearances.score" }, "face " + Object.values(tk.face).map(v => Number(v).toFixed(2)).join(" / ")) : null,
        driftView(tk), longView(tk), // added 2026-11-05 v0.8.0: drift of the passes that continue from footage, the take's seam settings
        h("span", { class: "rw-flex" }),
        button({ label: "A", small: true, help: "render.take.compareA", variant: ctx.eph.compare?.a?.take === tk.id ? "accent-ghost" : "ghost", onClick: () => ctx.store.setEph({ compare: { ...(ctx.eph.compare || {}), a: { scene: s.id, take: tk.id, url: viewURL(tk.files?.video) } } }) }),
        button({ label: "B", small: true, help: "render.take.compareB", variant: ctx.eph.compare?.b?.take === tk.id ? "accent-ghost" : "ghost", onClick: () => ctx.store.setEph({ compare: { ...(ctx.eph.compare || {}), b: { scene: s.id, take: tk.id, url: viewURL(tk.files?.video) } } }) }),
        tk.files?.video && h("a", { class: "rw-btn rw-btn-ghost rw-btn-sm", href: viewURL(tk.files.video), target: "_blank", rel: "noopener", help: "render.take.open" }, icon("eye", 12), h("span", null, "Open")),
        button({ icon: "trash", small: true, variant: "ghost", help: "render.take.delete", onClick: () => removeTake(tk) })))
        : h("div", { class: "rw-empty sm" }, "No takes yet. Render this scene to create one.")));
    }
  });
  /* [OLD 2026-11-02 v0.1.0->v0.2.0] Merge moved here from the tab bar; table gains a File column
  return section({
    title: "Scenes and takes", help: "render.table",
    actions: [button({ label: "Refresh", icon: "refresh", small: true, help: "render.refresh", onClick: async () => { await ctx.actions.refreshTakes(); ctx.store.refreshPlan(); } })],
    children: [
      h("div", { class: "rw-trow head" }, ["#", "Scene", "Status", "Takes", "Cache key", "Passes", "Length"].map(x => h("span", null, x))),
  [/OLD] */
  const res = ctx.eph.merge;
  const merging = res?.phase === "start" || res?.phase === "progress";
  const nReady = p.scenes.filter(s => mergeTake(ctx, s.id)).length;
  return section({
    title: "Scenes and takes", help: "render.table",
    actions: [
      res?.files?.video && h("a", { class: "rw-btn rw-btn-ghost rw-btn-sm", href: viewURL(res.files.video), target: "_blank", rel: "noopener", title: "output/" + res.files.video, help: "render.lastCut" },
        icon("eye", 12), h("span", { class: "mono" }, baseName(res.files.video))),
      button({ label: "Refresh", icon: "refresh", small: true, help: "render.refresh", onClick: async () => { await ctx.actions.refreshTakes(); ctx.store.refreshPlan(); } }),
      /* [OLD 2026-11-03 v0.5.1->v0.6.0] always a full merge, and no way to stop one
      button({ label: merging ? `Merging… ${res.percent ? Math.round(res.percent) + "%" : ""}` : `Merge ${nReady}/${p.scenes.length}`, icon: "merge", small: true, variant: "accent-ghost",
        help: "app.merge", disabled: merging || nReady === 0 || (p.global.merge.missing === "block" && nReady < p.scenes.length), onClick: () => ctx.actions.merge() }),
      [/OLD] */
      // added 2026-11-03 v0.6.0: the Merge card's options (draft, range, stems) apply here too; Stop while merging
      button({ label: merging ? `Merging… ${res.percent ? Math.round(res.percent) + "%" : ""}` : `${mergeOpts(ctx).draft ? "Draft merge" : "Merge"} ${nReady}/${p.scenes.length}`, icon: "merge", small: true, variant: "accent-ghost",
        help: "app.merge", disabled: merging || nReady === 0 || (p.global.merge.missing === "block" && nReady < p.scenes.length), onClick: () => runMerge(ctx) }),
      merging && button({ label: "Stop", icon: "stop", small: true, variant: "danger-ghost", help: "render.merge.stop", onClick: () => ctx.actions.cancelMerge() }),
    ],
    children: [
      h("div", { class: "rw-trow head" }, ["#", "Scene", "Status", "Takes", "File", "Cache key", "Passes", "Length"].map(x => h("span", null, x))),
      rows,
    ],
  });
}

function compareCard(ctx) {
  const c = ctx.eph.compare;
  if (!c?.a && !c?.b) return null;
  const vids = [];
  const pane = (side, item) => {
    const scene = item && ctx.p.scenes.find(s => s.id === item.scene);
    // [OLD 2026-11-03 v0.5.1->v0.6.0] const v = item?.url ? h("video", { class: "rw-ab-video", src: item.url, controls: true, muted: side === "b", preload: "metadata", playsinline: true }) : h("div", { class: "rw-ab-video empty" }, "Pick a take with the " + side.toUpperCase() + " button");  (a new <video> on every re-render: playback restarted on each progress event)
    const v = item?.url ? abVideo(ctx, side, item.url) : h("div", { class: "rw-ab-video empty" }, "Pick a take with the " + side.toUpperCase() + " button"); // added 2026-11-03 v0.6.0
    if (item?.url) vids.push(v);
    return h("div", { class: "rw-ab-pane" }, h("div", { class: "rw-dim small mono" }, side.toUpperCase() + (item ? ` · ${scene?.title || ""} · ${item.take}` : "")), v);
  };
  return section({
    title: "A/B compare", help: "render.compare",
    actions: [
      button({ label: "Play both", icon: "play", small: true, help: "render.compare.play", onClick: () => { for (const v of vids) { v.currentTime = 0; v.play().catch(() => {}); } } }),
      button({ icon: "close", small: true, variant: "ghost", help: "common.close", onClick: () => ctx.store.setEph({ compare: null }) }),
    ],
    children: h("div", { class: "rw-ab" }, pane("a", c.a), pane("b", c.b)),
  });
}

function chainsCard(ctx) {
  const p = ctx.p;
  const chains = continuityChains(p);
  const status = id => ctx.statusOf(id);
  return section({
    title: "What re-renders when you change something", help: "render.chains",
    children: [
      h("div", { class: "rw-dim small" }, "A scene’s cache key includes the take it continues from. Change a scene and only it and the scenes chained after it go stale."),
      h("div", { class: "rw-chains" }, chains.map(ch => h("span", { class: "rw-chain-box", help: "render.chains" }, ch.map((s, i) => [
        // [OLD 2026-11-03 v0.5.1->v0.6.0] i > 0 && h("span", { class: s.start.mode === "tail" ? "rw-c-vid" : "rw-c-pic" }, s.start.mode === "tail" ? "⇢" : "→"),  (a re-anchored tail continues from the last frame only)
        i > 0 && (tail => h("span", { class: tail ? "rw-c-vid" : "rw-c-pic" }, tail ? "⇢" : "→"))(effectiveStart(p, sceneIndex(p, s.id)) === "tail"), // added 2026-11-03 v0.6.0
        h("button", { type: "button", class: ["rw-chain-chip mono", "st-" + status(s.id), s.lock && "locked"], help: "render.chains.chip", onClick: () => ctx.actions.select(s.id) }, String(sceneIndex(p, s.id) + 1).padStart(2, "0")),
      ])))),
      h("div", { class: "rw-dim small" }, "→ last frame   ⇢ tail clip   Lock a scene (Scene tab) to keep its take when an earlier scene changes."),
    ],
  });
}

function memoryCard(ctx) {
  const m = ctx.p.global.memory;
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const set = fn => ctx.actions.edit(q => fn(q.global.memory));  (no History menu name)
  const set = fn => ctx.actions.edit(q => fn(q.global.memory), { label: "Memory setting" }); // added 2026-11-03 v0.6.0: History menu name
  return section({
    title: "Memory between scenes", help: "render.memory",
    children: [
      segmented({ value: m.policy, help: "render.memory.policy", options: [
        { value: "keep", label: "Keep models loaded", help: "render.memory.keep" },
        { value: "free_cache", label: "Free cache, keep models", help: "render.memory.free_cache" },
        { value: "unload_all", label: "Unload everything", help: "render.memory.unload_all" }],
      onChange: v => set(x => { x.policy = v; }) }),
      toggle({ value: m.encode_first, label: "Encode all prompts first, then unload the text encoder", help: "render.memory.encodeFirst", onChange: v => set(x => { x.encode_first = v; }) }),
      toggle({ value: m.group_by_lora, label: "Group independent scenes that share a LoRA stack", help: "render.memory.group", onChange: v => set(x => { x.group_by_lora = v; }) }),
      h("div", { class: "rw-dim small" }, "Each scene is written to MP4 as soon as it finishes, then its frames are dropped. Last frame, first frame and the tail clip are saved next to it."),
    ],
  });
}

function seamCard(ctx) {
  const p = ctx.p;
  if (p.scenes.length < 2) return null;
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const opts = p.scenes.slice(1).map((s, i) => ({ value: String(i), label: `${String(i + 1).padStart(2, "0")} → ${String(i + 2).padStart(2, "0")} · ${s.start.mode.replace("_", " ")}` }));  (showed the declared start, not the effective one)
  const opts = p.scenes.slice(1).map((s, i) => ({ value: String(i), label: `${String(i + 1).padStart(2, "0")} → ${String(i + 2).padStart(2, "0")} · ${effectiveStart(p, i + 1).replace("_", " ")}` })); // added 2026-11-03 v0.6.0
  const idx = Math.min(Number(ctx.eph.seam ?? 0), p.scenes.length - 2);
  const a = p.scenes[idx], b = p.scenes[idx + 1];
  const ta = ctx.starredTake(a.id), tb = ctx.starredTake(b.id);
  const mode = ctx.eph.seamMode || "side";
  const mix = ctx.eph.seamMix ?? 0.5;
  const img = (take, which, label) => take?.files?.[which] ? h("img", { src: viewURL(take.files[which]), alt: label }) : h("div", { class: "rw-seam-empty" }, label + ": not rendered");
  return section({
    title: "Seam inspector", help: "render.seam",
    actions: [
      select({ options: opts, value: String(idx), help: "render.seam.pick", onChange: v => ctx.store.setEph({ seam: Number(v) }) }),
      segmented({ small: true, value: mode, help: "render.seam.mode", options: [{ value: "side", label: "Side by side" }, { value: "onion", label: "Onion skin" }], onChange: v => ctx.store.setEph({ seamMode: v }) }),
    ],
    children: [
      mode === "side"
        ? h("div", { class: "rw-seam side" }, h("figure", null, img(ta, "last", "Last frame of " + a.title), h("figcaption", null, `${a.title} · last frame`)),
          // [OLD 2026-11-03 v0.5.1->v0.6.0] h("figure", null, img(tb, "first", "First frame of " + b.title), h("figcaption", null, `${b.title} · first frame${b.start.mode === "tail" ? ` (after ${overlapSeconds(b).toFixed(2)} s overlap)` : ""}`)))  (deprecated overlapSeconds; a re-anchored tail has no overlap)
          h("figure", null, img(tb, "first", "First frame of " + b.title), h("figcaption", null, `${b.title} · first frame${effectiveStart(p, idx + 1) === "tail" ? ` (after ${sceneOverlapAt(p, idx + 1).toFixed(2)} s overlap)` : ""}`))) // added 2026-11-03 v0.6.0
        : h("div", { class: "rw-seam onion" }, img(ta, "last", "Last frame"), h("div", { class: "rw-seam-top", style: { opacity: mix } }, img(tb, "first", "First frame"))),
      mode === "onion" && field("Mix", slider({ value: mix, min: 0, max: 1, step: 0.01, help: "render.seam.mix", format: v => Math.round(v * 100) + "%", onInput: v => { ctx.eph.seamMix = v; const top = ctx.root.querySelector(".rw-seam-top"); if (top) top.style.opacity = v; }, onChange: v => ctx.store.setEph({ seamMix: v }) }), { help: "render.seam.mix" }),
    ],
  });
}

function mergeCard(ctx) {
  const p = ctx.p;
  const m = p.global.merge;
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const set = fn => ctx.actions.edit(q => fn(q.global.merge));  (no History menu name)
  const set = fn => ctx.actions.edit(q => fn(q.global.merge), { label: "Merge setting" }); // added 2026-11-03 v0.6.0: History menu name
  const audio = p.assets.filter(a => a.kind === "audio").map(a => ({ value: a.id, label: `${a.code} · ${a.name || a.file}` }));
  const ready = p.scenes.map(s => ({ s, ok: !!ctx.starredTake(s.id) }));
  const nReady = ready.filter(r => r.ok).length;
  // [OLD 2026-11-03 v0.4.3->v0.5.0] const cutLen = ready.reduce((t, r, i) => t + (r.ok || m.missing !== "skip" ? r.s.duration - (i > 0 ? overlapSeconds(r.s) : 0) : 0), 0);
  // added 2026-11-03 v0.5.0: with a soundtrack the cut keeps the timeline's length (missing scenes become slates)
  const locked = soundtrackLocked(p);
  const mixed = playingTracks(p).filter(x => x.t.mix);
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const cutLen = locked ? sceneStarts(p).total : ready.reduce((t, r, i) => t + (r.ok || m.missing !== "skip" ? r.s.duration - (i > 0 ? overlapSeconds(r.s) : 0) : 0), 0);  (whole film only; deprecated overlapSeconds)
  // added 2026-11-03 v0.6.0: options of this merge (draft, a range of scenes, audio stems); length and count of the range
  const mo = mergeOpts(ctx);
  const setMo = patch => ctx.store.setEph({ mergeOpts: { ...mo, ...patch } });
  const lo = mo.range ? sceneIndex(p, mo.range[0]) : 0, hi = mo.range ? sceneIndex(p, mo.range[1]) : p.scenes.length - 1;
  const inRange = (r, i) => i >= lo && i <= hi;
  const { starts } = sceneStarts(p);
  const cutLen = locked
    ? (mo.range ? starts[p.scenes[hi].id] + p.scenes[hi].duration - (lo > 0 ? starts[p.scenes[lo].id] + sceneOverlapAt(p, lo) : 0) : sceneStarts(p).total)
    : ready.reduce((t, r, i) => t + (inRange(r, i) && (r.ok || m.missing !== "skip") ? r.s.duration - (i > lo ? sceneOverlapAt(p, i) : 0) : 0), 0);
  const nRange = hi - lo + 1, readyRange = ready.filter(inRange).filter(r => r.ok).length;
  const sceneOpts = p.scenes.map((s, i) => ({ value: s.id, label: `${String(i + 1).padStart(2, "0")} · ${s.title}` }));
  const res = ctx.eph.merge;
  const merging = res?.phase === "start" || res?.phase === "progress";
  // added 2026-11-02 v0.3.0: scenes whose Start card overrides the cut defaults
  // [OLD 2026-11-05 v0.6.1->v0.7.0] const overrides = p.scenes.filter((s, i) => i > 0 && s.transition && (s.transition.mode || s.transition.frames != null || s.transition.audio_fade_frames != null)).length;  (no Global defaults any more)
  const fileLink = (label, rel) => rel && h("a", { class: "rw-file", href: viewURL(rel), target: "_blank", rel: "noopener", help: "render.merge.file" }, icon("download", 12), label, h("span", { class: "mono rw-dim" }, rel.split("/").pop()));
  return section({
    title: "Merge scenes", help: "render.merge", cls: "rw-merge",
    actions: h("span", { class: "rw-dim small" }, "no re-render"),
    children: [
      field("Use", segmented({ small: true, value: m.use, help: "render.merge.use", options: [{ value: "starred", label: "Starred takes" }, { value: "latest", label: "Latest takes" }], onChange: v => set(x => { x.use = v; }) }), { help: "render.merge.use" }),
      field("Not ready", segmented({ small: true, value: m.missing, help: "render.merge.missing", options: [{ value: "skip", label: "Skip" }, { value: "slate", label: "Slate" }, { value: "block", label: "Block" }], onChange: v => set(x => { x.missing = v; }) }), { help: "render.merge.missing" }),
      // added 2026-11-03 v0.5.0
      // [OLD 2026-11-05 v0.6.1->v0.7.0] locked && h("div", { class: "rw-dim small", help: "render.merge.locked" }, "A soundtrack sets the timing: scenes not rendered yet merge as slates of their length, and crossfades and dips play as a dip through black inside the scenes."),
      // added 2026-11-05 v0.7.0: transitions are per scene now and dip through the scene's own dip colour
      locked && h("div", { class: "rw-dim small", help: "render.merge.locked" }, "A soundtrack sets the timing: scenes not rendered yet merge as slates of their length, and transitions play as a dip through their colour inside the scenes."),
      h("div", { class: "rw-subhead" }, "Seams"),
      // added 2026-11-05 v0.7.0: joins, fades, sound level and colour moved to each scene (Scene tab → In the cut)
      h("div", { class: "rw-row rw-merge-perscene", help: "render.merge.perScene" },
        h("span", { class: "rw-dim small" }, "Joins, fades, sound and colour are per scene:"),
        button({ label: "In the cut", icon: "scene", small: true, variant: "link", help: "render.merge.perSceneOpen",
          onClick: () => { ctx.store.setEph({ scrollToCut: true }); ctx.actions.setTab("scene"); } })),
      /* [OLD 2026-11-02 v0.2.2->v0.3.0] labels did not say that each scene can override these
      field("Hard cuts", segmented({ small: true, value: m.hard_cut, help: "render.merge.hardCut", options: [{ value: "cut", label: "Cut" }, { value: "crossfade", label: "Crossfade" }, { value: "dip", label: "Dip to black" }], onChange: v => set(x => { x.hard_cut = v; }) }), { help: "render.merge.hardCut" }),
      field("Transition", number({ value: m.transition_frames, min: 0, max: 96, unit: "f", help: "render.merge.transition", onChange: v => set(x => { x.transition_frames = v ?? 12; }) }), { help: "render.merge.transition" }),
      field("Audio fade", number({ value: m.audio_fade_frames, min: 0, max: 48, unit: "f", help: "render.merge.audioFade", onChange: v => set(x => { x.audio_fade_frames = v ?? 6; }) }), { help: "render.merge.audioFade" }),
      */
      /* [OLD 2026-11-05 v0.6.1->v0.7.0] Global defaults of the cut into a fresh scene; moved to each scene (scene.merge)
      // added 2026-11-02 v0.3.0: these are defaults; a scene's Start card can set its own cut
      field("Hard cuts · default", segmented({ small: true, value: m.hard_cut, help: "render.merge.hardCut", options: [{ value: "cut", label: "Cut" }, { value: "crossfade", label: "Crossfade" }, { value: "dip", label: "Dip to black" }], onChange: v => set(x => { x.hard_cut = v; }) }), { help: "render.merge.hardCut" }),
      field("Transition · default", number({ value: m.transition_frames, min: 0, max: 96, unit: "f", help: "render.merge.transition", onChange: v => set(x => { x.transition_frames = v ?? 12; }) }), { help: "render.merge.transition" }),
      field("Audio fade · default", number({ value: m.audio_fade_frames, min: 0, max: 48, unit: "f", help: "render.merge.audioFade", onChange: v => set(x => { x.audio_fade_frames = v ?? 6; }) }), { help: "render.merge.audioFade" }),
      // [OLD 2026-11-03 v0.4.3->v0.5.0] overrides && h("div", { class: "rw-dim small", help: "render.merge.overrides" }, `${overrides} scene${overrides > 1 ? "s" : ""} set their own cut`),
      overrides > 0 && h("div", { class: "rw-dim small", help: "render.merge.overrides" }, `${overrides} scene${overrides > 1 ? "s" : ""} set their own cut`), // 0 was printed as "0"
      [/OLD] */
      h("div", { class: "rw-subhead" }, "Audio"),
      field("Normalize", h("span", { class: "rw-row" }, toggle({ value: m.normalize, help: "render.merge.normalize", onChange: v => set(x => { x.normalize = v; }) }),
        number({ value: m.loudness, min: -40, max: -5, step: 0.5, unit: "LUFS", help: "render.merge.loudness", onChange: v => set(x => { x.loudness = v ?? -16; }) })), { help: "render.merge.normalize" }),
      /* [OLD 2026-11-03 v0.4.3->v0.5.0] the score track is a soundtrack track on the Timeline now (an old project's score moves there on load)
      field("Score track", select({ options: audio, value: m.score.asset, placeholder: "none", help: "render.merge.score", onChange: v => set(x => { x.score.asset = v; }) }), { help: "render.merge.score" }),
      m.score.asset && field("Score level", h("span", { class: "rw-row" }, number({ value: m.score.volume_db, min: -40, max: 6, step: 0.5, unit: "dB", help: "render.merge.scoreVolume", onChange: v => set(x => { x.score.volume_db = v ?? -12; }) }),
        toggle({ value: m.score.duck, label: "duck under dialogue", help: "render.merge.duck", onChange: v => set(x => { x.score.duck = v; }) })), { help: "render.merge.scoreVolume" }),
      [/OLD] */
      // added 2026-11-03 v0.5.0: soundtrack tracks play unchanged; the scenes' own sound can be laid under them
      field("Soundtrack", h("span", { class: "rw-row" }, h("span", { class: mixed.length ? "rw-c-aud" : "rw-dim" }, mixed.length ? `${mixed.length} track${mixed.length > 1 ? "s" : ""} in the cut, unchanged` : "none in the cut"),
        button({ label: "Timeline", icon: "timeline", small: true, variant: "link", help: "render.merge.soundtrack", onClick: () => ctx.actions.setTab("timeline") })), { help: "render.merge.soundtrack" }),
      mixed.length > 0 && field("Scene sound", h("span", { class: "rw-row" }, toggle({ value: m.scene_audio.mix, label: m.scene_audio.mix ? "under the soundtrack" : "off", help: "render.merge.sceneAudio", onChange: v => set(x => { x.scene_audio.mix = v; }) }),
        m.scene_audio.mix && number({ value: m.scene_audio.volume_db, min: -40, max: 6, step: 0.5, unit: "dB", help: "render.merge.sceneLevel", onChange: v => set(x => { x.scene_audio.volume_db = v ?? -12; }) })), { help: "render.merge.sceneAudio" }),
      h("div", { class: "rw-subhead" }, "Picture"),
      /* [OLD 2026-11-05 v0.6.1->v0.7.0] one colour match for the whole film; each scene chooses its own now (scene.merge.color_match)
      field("Colour match", h("span", { class: "rw-row" }, toggle({ value: m.color_match, help: "render.merge.color", onChange: v => set(x => { x.color_match = v; }) }),
        m.color_match && select({ options: p.scenes.map(s => ({ value: s.id, label: s.title })), value: m.color_ref_scene, placeholder: "first scene", help: "render.merge.colorRef", onChange: v => set(x => { x.color_ref_scene = v; }) })), { help: "render.merge.color" }),
      [/OLD] */
      field("Codec", h("span", { class: "rw-row" }, segmented({ small: true, value: m.codec, help: "render.merge.codec", options: [{ value: "h264", label: "H.264" }, { value: "h265", label: "H.265" }], onChange: v => set(x => { x.codec = v; }) }),
        number({ value: m.crf, min: 0, max: 51, width: "56px", help: "render.merge.crf", onChange: v => set(x => { x.crf = v ?? 16; }) }), h("span", { class: "rw-dim small" }, "CRF")), { help: "render.merge.codec" }),
      h("div", { class: "rw-subhead" }, "Extras"),
      h("div", { class: "rw-toggle-grid" },
        toggle({ value: m.subtitles, label: "Subtitles .srt", help: "render.merge.subtitles", onChange: v => set(x => { x.subtitles = v; }) }),
        toggle({ value: m.chapters, label: "Chapter per scene", help: "render.merge.chapters", onChange: v => set(x => { x.chapters = v; }) }),
        toggle({ value: m.otio, label: "Timeline .otio", help: "render.merge.otio", onChange: v => set(x => { x.otio = v; }) }),
        toggle({ value: m.fcpxml, label: "Timeline .fcpxml", help: "render.merge.fcpxml", onChange: v => set(x => { x.fcpxml = v; }) }),
        toggle({ value: m.bundle, label: "Project bundle .zip", help: "render.merge.bundle", onChange: v => set(x => { x.bundle = v; }) }),
        toggle({ value: m.auto_after_render, label: "Merge after each render", help: "render.merge.auto", onChange: v => set(x => { x.auto_after_render = v; }) })),
      // added 2026-11-03 v0.6.0: options of the next merge: draft (half size, fast), a range of scenes, audio stems with a
      // loudness report. They are not saved in the project.
      h("div", { class: "rw-subhead" }, "This merge"),
      field("Size", segmented({ small: true, value: mo.draft ? "draft" : "full", help: "render.merge.draft", options: [
        { value: "full", label: "Full", help: "render.merge.draft.full" }, { value: "draft", label: "Draft · half size, fast", help: "render.merge.draft.on" }],
      onChange: v => setMo({ draft: v === "draft" }) }), { help: "render.merge.draft" }),
      field("Scenes", h("span", { class: "rw-row wrap" },
        segmented({ small: true, value: mo.range ? "range" : "all", help: "render.merge.range", options: [
          { value: "all", label: "All", help: "render.merge.range.all" }, { value: "range", label: "From … to", help: "render.merge.range.some" }],
        onChange: v => setMo({ range: v === "range" ? [ctx.scene?.id || p.scenes[0].id, p.scenes[p.scenes.length - 1].id] : null }) }),
        mo.range && select({ options: sceneOpts, value: mo.range[0], key: "merge-range-from", help: "render.merge.rangeFrom", width: "150px", onChange: v => setMo({ range: [v, mo.range[1]] }) }),
        mo.range && h("span", { class: "rw-dim small" }, "to"),
        mo.range && select({ options: sceneOpts, value: mo.range[1], key: "merge-range-to", help: "render.merge.rangeTo", width: "150px", onChange: v => setMo({ range: [mo.range[0], v] }) })), { help: "render.merge.range", wide: true }),
      field("Stems", toggle({ value: mo.stems, label: "Audio stems + loudness report", help: "render.merge.stems", onChange: v => setMo({ stems: v }) }), { help: "render.merge.stems" }),
      // [OLD 2026-11-03 v0.5.1->v0.6.0] h("div", { class: "rw-ready", help: "render.merge.ready" }, ready.map(r => h("span", { class: ["rw-ready-seg", r.ok ? "ok" : "no"], style: { "flex-grow": String(r.s.duration) }, title: r.s.title }))),  (scenes outside the range are dimmed now)
      h("div", { class: "rw-ready", help: "render.merge.ready" }, ready.map((r, i) => h("span", { class: ["rw-ready-seg", r.ok ? "ok" : "no", !inRange(r, i) && "out"], style: { "flex-grow": String(r.s.duration) }, title: r.s.title }))),
      // [OLD 2026-11-03 v0.4.3->v0.5.0] button({ label: res?.phase === "start" || res?.phase === "progress" ? `Merging… ${res.percent ? Math.round(res.percent) + "%" : ""}` : `Merge ${m.missing === "skip" ? nReady : p.scenes.length} scenes · ${fmtTime(cutLen)}`,
      // added 2026-11-03 v0.5.0: with a soundtrack missing scenes merge as slates
      /* [OLD 2026-11-03 v0.5.1->v0.6.0] no draft/range/stems, no Stop
      button({ label: res?.phase === "start" || res?.phase === "progress" ? `Merging… ${res.percent ? Math.round(res.percent) + "%" : ""}` : `Merge ${m.missing === "skip" && !locked ? nReady : p.scenes.length} scenes · ${fmtTime(cutLen)}`,
        icon: "merge", variant: "primary", help: "render.merge.run", disabled: res?.phase === "start" || res?.phase === "progress" || (m.missing === "block" && nReady < p.scenes.length) || nReady === 0,
        onClick: () => ctx.actions.merge() }),
      [/OLD] */
      button({ label: merging ? `Merging… ${res.percent ? Math.round(res.percent) + "%" : ""}`
        : `${mo.draft ? "Draft merge" : "Merge"} ${m.missing === "skip" && !locked ? readyRange : nRange} scene${(m.missing === "skip" && !locked ? readyRange : nRange) === 1 ? "" : "s"}${mo.range ? ` (${String(lo + 1).padStart(2, "0")}–${String(hi + 1).padStart(2, "0")})` : ""} · ${fmtTime(cutLen)}`,
        icon: "merge", variant: "primary", help: "render.merge.run", disabled: merging || (m.missing === "block" && readyRange < nRange) || readyRange === 0,
        onClick: () => runMerge(ctx) }),
      merging && button({ label: "Stop merging", icon: "stop", variant: "danger-ghost", help: "render.merge.stop", onClick: () => ctx.actions.cancelMerge() }),
      (res?.phase === "cancelled" || res?.cancelled) && h("div", { class: "rw-note" }, icon("info", 12), "Merge stopped. Its files were removed."),
      // [OLD 2026-11-03 v0.4.3->v0.5.0] h("div", { class: "rw-dim small", style: { "text-align": "center" } }, nReady < p.scenes.length ? `${p.scenes.length - nReady} scene${p.scenes.length - nReady > 1 ? "s" : ""} not rendered yet · ${m.missing}` : "Every scene has a take."),
      h("div", { class: "rw-dim small", style: { "text-align": "center" } }, nReady < p.scenes.length ? `${p.scenes.length - nReady} scene${p.scenes.length - nReady > 1 ? "s" : ""} not rendered yet · ${locked && m.missing !== "block" ? "slate (soundtrack)" : m.missing}` : "Every scene has a take."),
      res?.phase === "error" && h("div", { class: "rw-note err" }, icon("warn", 12), res.error),
      /* [OLD 2026-11-03 v0.5.1->v0.6.0] no stems folder or loudness report
      res?.files && h("div", { class: "rw-files" }, fileLink("Video", res.files.video), fileLink("Subtitles", res.files.srt), fileLink("OTIO", res.files.otio),
        fileLink("FCPXML", res.files.fcpxml), fileLink("Chapters", res.files.chapters), fileLink("Bundle", res.files.bundle)),
      [/OLD] */
      // added 2026-11-03 v0.6.0: what kind of cut it was, the stems folder, the loudness file and its report
      res?.files && h("div", { class: "rw-files" },
        (res.draft || res.range) && h("div", { class: "rw-dim small" }, [res.draft && "draft (half size)", res.range && `scenes ${num2(p, res.range[0])}–${num2(p, res.range[1])}`].filter(Boolean).join(" · ")),
        fileLink("Video", res.files.video), fileLink("Subtitles", res.files.srt), fileLink("OTIO", res.files.otio),
        fileLink("FCPXML", res.files.fcpxml), fileLink("Chapters", res.files.chapters), fileLink("Bundle", res.files.bundle),
        res.files.stems && h("div", { class: "rw-file", help: "render.merge.stemsFolder" }, icon("folder", 12), "Stems", h("span", { class: "mono rw-dim rw-ellipsis", title: "output/" + res.files.stems }, "output/" + res.files.stems + "/")),
        fileLink("Loudness", res.files.loudness)),
      res?.loudness && loudnessReport(ctx, res.loudness),
    ],
  });
}

/* [OLD 2026-11-02 v0.3.5->v0.3.6] versions could not be deleted, and the long file name squeezed the date onto two lines
function versionsCard(ctx) {
  const v = ctx.eph.versions;
  return section({
    title: "Autosaved versions", help: "render.versions",
    actions: button({ label: v ? "Refresh" : "Load list", icon: "refresh", small: true, help: "render.versions.load", onClick: async () => {
      try { ctx.store.setEph({ versions: (await rw.versions(ctx.p.slug)).versions || [] }); } catch (err) { ctx.actions.toast("Versions unavailable: " + err.message, "error"); }
    } }),
    children: !v ? h("div", { class: "rw-dim small" }, "Every few seconds of editing is saved to output/reelwright/" + ctx.p.slug + "/versions.")
      : v.length ? h("div", { class: "rw-versions", dataset: { scroll: "versions" } }, v.map(x => h("div", { class: "rw-list-row" },
        h("span", { class: "mono grow rw-ellipsis" }, x.name), h("span", { class: "rw-dim small" }, x.created ? new Date(x.created * (x.created < 1e12 ? 1000 : 1)).toLocaleString() : ""),
        button({ label: "Restore", small: true, help: "render.versions.restore", onClick: e => confirmInline(e.currentTarget.closest(".rw-list-row"), "Replace the current project with this version? (Undo works.)", async () => {
          try { const r = await rw.version(ctx.p.slug, x.name); ctx.store.replaceProject(r.project); ctx.actions.toast("Version restored.", "ok"); } catch (err) { ctx.actions.toast(err.message, "error"); }
        }) }))))
        : h("div", { class: "rw-empty sm" }, "No versions saved yet."),
  });
}
[/OLD] */
// added 2026-11-02 v0.3.6: one row per version (date, time, size), with Restore and Delete; Delete all in the header
function versionsCard(ctx) {
  const v = ctx.eph.versions;
  const load = async () => {
    try { ctx.store.setEph({ versions: (await rw.versions(ctx.p.slug)).versions || [] }); } catch (err) { ctx.actions.toast("Versions unavailable: " + err.message, "error"); }
  };
  const fmt = x => {
    const m = /^project_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.json$/.exec(x.name);
    const d = m ? new Date(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6]) : new Date(x.created * 1000);
    return [d.toLocaleDateString(), d.toLocaleTimeString()];
  };
  const kb = n => (n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB");
  const remove = async names => {
    try {
      const r = await rw.deleteVersions(ctx.p.slug, names);
      ctx.store.setEph({ versions: r.versions || [] });
      ctx.actions.toast(`Deleted ${r.removed} version${r.removed === 1 ? "" : "s"}.`, "ok");
    } catch (err) { ctx.actions.toast("Delete failed: " + err.message, "error"); }
  };
  const removeAll = async () => {
    if (!(await confirmDialog(ctx.root, { title: `Delete all ${v.length} autosaved versions?`, confirmLabel: "Delete all",
      message: `The version files in output/reelwright/${ctx.p.slug}/versions are removed for good. The project itself (and its latest autosave) stays.` }))) return;
    try {
      const r = await rw.deleteAllVersions(ctx.p.slug);
      ctx.store.setEph({ versions: r.versions || [] });
      ctx.actions.toast(`Deleted ${r.removed} version${r.removed === 1 ? "" : "s"}.`, "ok");
    } catch (err) { ctx.actions.toast("Delete failed: " + err.message, "error"); }
  };
  return section({
    title: "Autosaved versions", help: "render.versions",
    actions: h("span", { class: "rw-row" },
      v?.length ? button({ label: "Delete all", icon: "trash", small: true, variant: "danger-ghost", help: "render.versions.deleteAll", onClick: removeAll }) : null,
      button({ label: v ? "Refresh" : "Load list", icon: "refresh", small: true, help: "render.versions.load", onClick: load })),
    children: !v ? h("div", { class: "rw-dim small" }, "Every few seconds of editing is saved to output/reelwright/" + ctx.p.slug + "/versions.")
      : v.length ? h("div", { class: "rw-versions", dataset: { scroll: "versions" } }, v.map(x => {
        const [day, time] = fmt(x);
        return h("div", { class: "rw-list-row rw-version", title: x.name },
          h("span", { class: "mono rw-version-when" }, h("span", null, day), " ", h("b", null, time)),
          h("span", { class: "rw-dim small grow" }, x.size ? kb(x.size) : ""),
          /* [OLD 2026-11-03 v0.5.1->v0.6.0] inline bars (they vanished on any re-render) and no way to see what a restore changes
          button({ label: "Restore", small: true, help: "render.versions.restore", onClick: e => confirmInline(e.currentTarget.closest(".rw-list-row"), "Replace the current project with this version? (Undo works.)", async () => {
            try { const r = await rw.version(ctx.p.slug, x.name); ctx.store.replaceProject(r.project); ctx.actions.toast("Version restored.", "ok"); } catch (err) { ctx.actions.toast(err.message, "error"); }
          }) }),
          button({ icon: "trash", small: true, variant: "ghost", help: "render.versions.delete", "aria-label": "Delete this version",
            onClick: e => confirmInline(e.currentTarget.closest(".rw-list-row"), `Delete the version from ${day} ${time}? This cannot be undone.`, () => remove([x.name])) }));
          [/OLD] */
          // added 2026-11-03 v0.6.0: Restore shows what differs (scenes, lengths, prompt text, Global) in the dialog first
          button({ label: "Restore", small: true, help: "render.versions.restore", onClick: () => restoreVersion(ctx, x, day, time) }),
          button({ icon: "trash", small: true, variant: "ghost", help: "render.versions.delete", ariaLabel: "Delete this version",
            onClick: async () => {
              if (await confirmDialog(ctx.root, { title: `Delete the version from ${day} ${time}?`, confirmLabel: "Delete version",
                message: "The version file is removed for good. The project itself is not changed." })) remove([x.name]);
            } }));
      }))
        : h("div", { class: "rw-empty sm" }, "No versions saved yet."),
  });
}

export function render(ctx) {
  // [OLD 2026-11-03 v0.4.3->v0.5.0] const scoreMissing = ctx.p.global.merge.score.asset && !findAsset(ctx.p, ctx.p.global.merge.score.asset);
  const scoreMissing = ctx.p.soundtrack.some(t => !findAsset(ctx.p, t.asset)); // added 2026-11-03 v0.5.0
  return h("div", { class: "rw-render-tab" },
    scopeBar(ctx),
    runBanner(ctx),
    lastRunNote(ctx), // added 2026-11-03 v0.6.0: failed / skipped scenes of the last run, or why it never started
    // [OLD 2026-11-03 v0.4.3->v0.5.0] scoreMissing && h("div", { class: "rw-banner warn" }, icon("warn", 13), "The score track points at a deleted asset."),
    scoreMissing && h("div", { class: "rw-banner warn" }, icon("warn", 13), "A soundtrack track points at a deleted audio asset (Timeline tab)."),
    h("div", { class: "rw-cols", dataset: { scroll: "render-cols" } },
      h("div", { class: "rw-col wide" }, takesTable(ctx), compareCard(ctx), chainsCard(ctx), memoryCard(ctx), seamCard(ctx)),
      h("div", { class: "rw-col mid" }, mergeCard(ctx), versionsCard(ctx))));
}
