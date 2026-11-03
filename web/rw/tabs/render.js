// Render tab: what to render, takes, cache keys, dependency chains, memory
// policy, the seam inspector, merge settings and autosaved versions.

// [OLD 2026-11-02 v0.3.5->v0.3.6] import { h, icon, button, toggle, segmented, select, number, section, field, dot, confirmInline, slider } from "../ui.js";
import { h, icon, button, toggle, segmented, select, number, section, field, dot, confirmInline, slider, confirmDialog } from "../ui.js";
import { rw, viewURL } from "../api.js";
// [OLD 2026-11-03 v0.4.3->v0.5.0] import { continuityChains, fmtTime, sceneStarts, sceneIndex, findAsset, overlapSeconds } from "../model.js";
import { continuityChains, fmtTime, sceneStarts, sceneIndex, findAsset, overlapSeconds, soundtrackLocked, playingTracks } from "../model.js";

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
  return h("div", { class: "rw-row wrap rw-scope" },
    button({ label: pend === null ? "Render pending" : `Render pending · ${pend}`, icon: "play", variant: "primary", help: "render.scope.pending", onClick: () => ctx.actions.run("pending") }),
    button({ label: `Selected: ${s.title}`, help: "render.scope.selected", onClick: () => ctx.actions.run("selected", [s.id]) }),
    button({ label: `From playhead (${String(fromIdx + 1).padStart(2, "0")} →)`, help: "render.scope.from", onClick: () => ctx.actions.run("from", [fromScene.id]) }),
    button({ label: "Everything", help: "render.scope.all", onClick: e => confirmInline(e.currentTarget.parentElement, "Re-render every scene, even ones already on disk?", () => ctx.actions.run("all")) }),
    button({ label: "New take of selected", icon: "refresh", help: "render.scope.take", onClick: () => ctx.actions.run("take", [s.id]) }),
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
  const prog = r?.current || Object.values(ctx.eph.progress).find(x => !["done", "cached", "error"].includes(x.phase));
  if (!ctx.eph.running && !prog) return null;
  const s = prog && ctx.p.scenes.find(x => x.id === prog.scene_id);
  const pct = v => Math.round(Math.max(0, Math.min(1, v)) * 100);
  const bar = (label, v, cls, help) => h("div", { class: "rw-progress", help },
    h("span", { class: "rw-dim" }, label),
    h("span", { class: "rw-meter-bar" }, h("span", { class: ["rw-meter-fill", cls], style: { width: pct(v) + "%" } })),
    h("span", { class: "mono rw-dim" }, pct(v) + "%"));
  const scenePart = r ? r.scenePart : prog?.steps ? prog.step / prog.steps : 0;
  const head = r ? `Scene ${Math.max(1, r.index)} of ${r.n}` : "Rendering";
  const detail = prog ? `${s?.title || prog.scene_id} · pass ${prog.pass}/${prog.passes} · ${prog.phase}${prog.steps ? ` · step ${prog.step}/${prog.steps}` : ""}${prog.message ? " · " + prog.message : ""}`
    : r && r.done >= r.n ? "finishing…" : "waiting for ComfyUI…";
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
  return h("div", { class: "rw-banner info", help: "render.banner" }, icon("render", 14),
    h("div", { class: "rw-run" },
      h("div", { class: "rw-row" }, h("b", null, head), h("span", { class: "rw-ellipsis" }, detail),
        r?.reused?.length ? h("span", { class: "rw-dim small" }, `· ${r.reused.length} reused`) : null),
      bar("Scene", scenePart, "rw-bg-pic", "render.progress.scene"),
      r && bar("Total", r.total, "rw-bg-aud", "render.progress.total")),
    preview);
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
      button({ label: merging ? `Merging… ${res.percent ? Math.round(res.percent) + "%" : ""}` : `Merge ${nReady}/${p.scenes.length}`, icon: "merge", small: true, variant: "accent-ghost",
        help: "app.merge", disabled: merging || nReady === 0 || (p.global.merge.missing === "block" && nReady < p.scenes.length), onClick: () => ctx.actions.merge() }),
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
    const v = item?.url ? h("video", { class: "rw-ab-video", src: item.url, controls: true, muted: side === "b", preload: "metadata", playsinline: true }) : h("div", { class: "rw-ab-video empty" }, "Pick a take with the " + side.toUpperCase() + " button");
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
        i > 0 && h("span", { class: s.start.mode === "tail" ? "rw-c-vid" : "rw-c-pic" }, s.start.mode === "tail" ? "⇢" : "→"),
        h("button", { type: "button", class: ["rw-chain-chip mono", "st-" + status(s.id), s.lock && "locked"], help: "render.chains.chip", onClick: () => ctx.actions.select(s.id) }, String(sceneIndex(p, s.id) + 1).padStart(2, "0")),
      ])))),
      h("div", { class: "rw-dim small" }, "→ last frame   ⇢ tail clip   Lock a scene (Scene tab) to keep its take when an earlier scene changes."),
    ],
  });
}

function memoryCard(ctx) {
  const m = ctx.p.global.memory;
  const set = fn => ctx.actions.edit(q => fn(q.global.memory));
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
  const opts = p.scenes.slice(1).map((s, i) => ({ value: String(i), label: `${String(i + 1).padStart(2, "0")} → ${String(i + 2).padStart(2, "0")} · ${s.start.mode.replace("_", " ")}` }));
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
          h("figure", null, img(tb, "first", "First frame of " + b.title), h("figcaption", null, `${b.title} · first frame${b.start.mode === "tail" ? ` (after ${overlapSeconds(b).toFixed(2)} s overlap)` : ""}`)))
        : h("div", { class: "rw-seam onion" }, img(ta, "last", "Last frame"), h("div", { class: "rw-seam-top", style: { opacity: mix } }, img(tb, "first", "First frame"))),
      mode === "onion" && field("Mix", slider({ value: mix, min: 0, max: 1, step: 0.01, help: "render.seam.mix", format: v => Math.round(v * 100) + "%", onInput: v => { ctx.eph.seamMix = v; const top = ctx.root.querySelector(".rw-seam-top"); if (top) top.style.opacity = v; }, onChange: v => ctx.store.setEph({ seamMix: v }) }), { help: "render.seam.mix" }),
    ],
  });
}

function mergeCard(ctx) {
  const p = ctx.p;
  const m = p.global.merge;
  const set = fn => ctx.actions.edit(q => fn(q.global.merge));
  const audio = p.assets.filter(a => a.kind === "audio").map(a => ({ value: a.id, label: `${a.code} · ${a.name || a.file}` }));
  const ready = p.scenes.map(s => ({ s, ok: !!ctx.starredTake(s.id) }));
  const nReady = ready.filter(r => r.ok).length;
  // [OLD 2026-11-03 v0.4.3->v0.5.0] const cutLen = ready.reduce((t, r, i) => t + (r.ok || m.missing !== "skip" ? r.s.duration - (i > 0 ? overlapSeconds(r.s) : 0) : 0), 0);
  // added 2026-11-03 v0.5.0: with a soundtrack the cut keeps the timeline's length (missing scenes become slates)
  const locked = soundtrackLocked(p);
  const mixed = playingTracks(p).filter(x => x.t.mix);
  const cutLen = locked ? sceneStarts(p).total : ready.reduce((t, r, i) => t + (r.ok || m.missing !== "skip" ? r.s.duration - (i > 0 ? overlapSeconds(r.s) : 0) : 0), 0);
  const res = ctx.eph.merge;
  // added 2026-11-02 v0.3.0: scenes whose Start card overrides the cut defaults
  const overrides = p.scenes.filter((s, i) => i > 0 && s.transition && (s.transition.mode || s.transition.frames != null || s.transition.audio_fade_frames != null)).length;
  const fileLink = (label, rel) => rel && h("a", { class: "rw-file", href: viewURL(rel), target: "_blank", rel: "noopener", help: "render.merge.file" }, icon("download", 12), label, h("span", { class: "mono rw-dim" }, rel.split("/").pop()));
  return section({
    title: "Merge scenes", help: "render.merge", cls: "rw-merge",
    actions: h("span", { class: "rw-dim small" }, "no re-render"),
    children: [
      field("Use", segmented({ small: true, value: m.use, help: "render.merge.use", options: [{ value: "starred", label: "Starred takes" }, { value: "latest", label: "Latest takes" }], onChange: v => set(x => { x.use = v; }) }), { help: "render.merge.use" }),
      field("Not ready", segmented({ small: true, value: m.missing, help: "render.merge.missing", options: [{ value: "skip", label: "Skip" }, { value: "slate", label: "Slate" }, { value: "block", label: "Block" }], onChange: v => set(x => { x.missing = v; }) }), { help: "render.merge.missing" }),
      // added 2026-11-03 v0.5.0
      locked && h("div", { class: "rw-dim small", help: "render.merge.locked" }, "A soundtrack sets the timing: scenes not rendered yet merge as slates of their length, and crossfades and dips play as a dip through black inside the scenes."),
      h("div", { class: "rw-subhead" }, "Seams"),
      /* [OLD 2026-11-02 v0.2.2->v0.3.0] labels did not say that each scene can override these
      field("Hard cuts", segmented({ small: true, value: m.hard_cut, help: "render.merge.hardCut", options: [{ value: "cut", label: "Cut" }, { value: "crossfade", label: "Crossfade" }, { value: "dip", label: "Dip to black" }], onChange: v => set(x => { x.hard_cut = v; }) }), { help: "render.merge.hardCut" }),
      field("Transition", number({ value: m.transition_frames, min: 0, max: 96, unit: "f", help: "render.merge.transition", onChange: v => set(x => { x.transition_frames = v ?? 12; }) }), { help: "render.merge.transition" }),
      field("Audio fade", number({ value: m.audio_fade_frames, min: 0, max: 48, unit: "f", help: "render.merge.audioFade", onChange: v => set(x => { x.audio_fade_frames = v ?? 6; }) }), { help: "render.merge.audioFade" }),
      */
      // added 2026-11-02 v0.3.0: these are defaults; a scene's Start card can set its own cut
      field("Hard cuts · default", segmented({ small: true, value: m.hard_cut, help: "render.merge.hardCut", options: [{ value: "cut", label: "Cut" }, { value: "crossfade", label: "Crossfade" }, { value: "dip", label: "Dip to black" }], onChange: v => set(x => { x.hard_cut = v; }) }), { help: "render.merge.hardCut" }),
      field("Transition · default", number({ value: m.transition_frames, min: 0, max: 96, unit: "f", help: "render.merge.transition", onChange: v => set(x => { x.transition_frames = v ?? 12; }) }), { help: "render.merge.transition" }),
      field("Audio fade · default", number({ value: m.audio_fade_frames, min: 0, max: 48, unit: "f", help: "render.merge.audioFade", onChange: v => set(x => { x.audio_fade_frames = v ?? 6; }) }), { help: "render.merge.audioFade" }),
      // [OLD 2026-11-03 v0.4.3->v0.5.0] overrides && h("div", { class: "rw-dim small", help: "render.merge.overrides" }, `${overrides} scene${overrides > 1 ? "s" : ""} set their own cut`),
      overrides > 0 && h("div", { class: "rw-dim small", help: "render.merge.overrides" }, `${overrides} scene${overrides > 1 ? "s" : ""} set their own cut`), // 0 was printed as "0"
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
      field("Colour match", h("span", { class: "rw-row" }, toggle({ value: m.color_match, help: "render.merge.color", onChange: v => set(x => { x.color_match = v; }) }),
        m.color_match && select({ options: p.scenes.map(s => ({ value: s.id, label: s.title })), value: m.color_ref_scene, placeholder: "first scene", help: "render.merge.colorRef", onChange: v => set(x => { x.color_ref_scene = v; }) })), { help: "render.merge.color" }),
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
      h("div", { class: "rw-ready", help: "render.merge.ready" }, ready.map(r => h("span", { class: ["rw-ready-seg", r.ok ? "ok" : "no"], style: { "flex-grow": String(r.s.duration) }, title: r.s.title }))),
      // [OLD 2026-11-03 v0.4.3->v0.5.0] button({ label: res?.phase === "start" || res?.phase === "progress" ? `Merging… ${res.percent ? Math.round(res.percent) + "%" : ""}` : `Merge ${m.missing === "skip" ? nReady : p.scenes.length} scenes · ${fmtTime(cutLen)}`,
      // added 2026-11-03 v0.5.0: with a soundtrack missing scenes merge as slates
      button({ label: res?.phase === "start" || res?.phase === "progress" ? `Merging… ${res.percent ? Math.round(res.percent) + "%" : ""}` : `Merge ${m.missing === "skip" && !locked ? nReady : p.scenes.length} scenes · ${fmtTime(cutLen)}`,
        icon: "merge", variant: "primary", help: "render.merge.run", disabled: res?.phase === "start" || res?.phase === "progress" || (m.missing === "block" && nReady < p.scenes.length) || nReady === 0,
        onClick: () => ctx.actions.merge() }),
      // [OLD 2026-11-03 v0.4.3->v0.5.0] h("div", { class: "rw-dim small", style: { "text-align": "center" } }, nReady < p.scenes.length ? `${p.scenes.length - nReady} scene${p.scenes.length - nReady > 1 ? "s" : ""} not rendered yet · ${m.missing}` : "Every scene has a take."),
      h("div", { class: "rw-dim small", style: { "text-align": "center" } }, nReady < p.scenes.length ? `${p.scenes.length - nReady} scene${p.scenes.length - nReady > 1 ? "s" : ""} not rendered yet · ${locked && m.missing !== "block" ? "slate (soundtrack)" : m.missing}` : "Every scene has a take."),
      res?.phase === "error" && h("div", { class: "rw-note err" }, icon("warn", 12), res.error),
      res?.files && h("div", { class: "rw-files" }, fileLink("Video", res.files.video), fileLink("Subtitles", res.files.srt), fileLink("OTIO", res.files.otio),
        fileLink("FCPXML", res.files.fcpxml), fileLink("Chapters", res.files.chapters), fileLink("Bundle", res.files.bundle)),
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
          button({ label: "Restore", small: true, help: "render.versions.restore", onClick: e => confirmInline(e.currentTarget.closest(".rw-list-row"), "Replace the current project with this version? (Undo works.)", async () => {
            try { const r = await rw.version(ctx.p.slug, x.name); ctx.store.replaceProject(r.project); ctx.actions.toast("Version restored.", "ok"); } catch (err) { ctx.actions.toast(err.message, "error"); }
          }) }),
          button({ icon: "trash", small: true, variant: "ghost", help: "render.versions.delete", "aria-label": "Delete this version",
            onClick: e => confirmInline(e.currentTarget.closest(".rw-list-row"), `Delete the version from ${day} ${time}? This cannot be undone.`, () => remove([x.name])) }));
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
    // [OLD 2026-11-03 v0.4.3->v0.5.0] scoreMissing && h("div", { class: "rw-banner warn" }, icon("warn", 13), "The score track points at a deleted asset."),
    scoreMissing && h("div", { class: "rw-banner warn" }, icon("warn", 13), "A soundtrack track points at a deleted audio asset (Timeline tab)."),
    h("div", { class: "rw-cols", dataset: { scroll: "render-cols" } },
      h("div", { class: "rw-col wide" }, takesTable(ctx), compareCard(ctx), chainsCard(ctx), memoryCard(ctx), seamCard(ctx)),
      h("div", { class: "rw-col mid" }, mergeCard(ctx), versionsCard(ctx))));
}
