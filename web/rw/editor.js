// Editor root: tab bar, active tab, footer, toasts, issues drawer, keyboard and
// websocket wiring. `host` adapts ComfyUI (or the test harness) to the editor.

import { rw, setHost } from "./api.js";
import { createStore } from "./store.js";
import { installTooltips } from "./tooltip.js";
import { h, icon, button } from "./ui.js";
import { VERSION } from "./version.js";
import {
  normalizeProject, defaultScene, newId, sceneIndex, sceneStarts, assembledDuration, fmtTime,
  sceneBudget, budgetIssues, FPS,
} from "./model.js";
import * as timeline from "./tabs/timeline.js";
import * as sceneTab from "./tabs/scene.js";
import * as assetsTab from "./tabs/assets.js";
import * as castTab from "./tabs/cast.js";
import * as renderTab from "./tabs/render.js";
import * as globalTab from "./tabs/global.js";

const TABS = {
  timeline: { label: "Timeline", icon: "timeline", mod: timeline },
  scene: { label: "Scene", icon: "scene", mod: sceneTab },
  assets: { label: "Assets", icon: "assets", mod: assetsTab },
  cast: { label: "Cast", icon: "cast", mod: castTab },
  render: { label: "Render", icon: "render", mod: renderTab },
  global: { label: "Global", icon: "global", mod: globalTab },
};

const PENDING = new Set(["stale", "pending", "missing", "queued"]);

export function mountEditor(container, host) {
  setHost(host);
  const store = createStore(normalizeProject(host.getProject()), { persist: json => host.setProject(json) });
  const root = h("div", { class: "rw-root", tabindex: "0" });
  const tabbar = h("div", { class: "rw-tabbar" });
  const body = h("div", { class: "rw-body" });
  const footer = h("div", { class: "rw-footer" });
  const toasts = h("div", { class: "rw-toasts" });
  const drawer = h("div", { class: "rw-drawer" });
  root.append(tabbar, body, footer, drawer, toasts);
  container.replaceChildren(root);
  const tips = installTooltips(root);

  const ctx = {
    store, host, root, tips, eph: store.eph,
    get p() { return store.project; },
    get scene() { return store.project.scenes.find(s => s.id === store.project.ui.selected) || store.project.scenes[0]; },
    planFor: id => store.eph.plan?.scenes?.[id] || null,
    statusOf: id => {
      if (store.eph.progress[id] && !["done", "cached", "error"].includes(store.eph.progress[id].phase)) return "rendering";
      return store.eph.plan?.scenes?.[id]?.status || "unknown";
    },
    takesFor: id => store.eph.takes?.scenes?.[id] || { starred: null, takes: [] },
    starredTake(id) {
      const t = this.takesFor(id);
      return t.takes.find(x => x.id === t.starred) || null;
    },
    actions: null,
  };

  const actions = ctx.actions = {
    setTab(tab) {
      store.update(p => { p.ui.tab = tab; }, { history: false, plan: false, autosave: false });
    },
    select(id, tab) {
      store.update(p => { p.ui.selected = id; if (tab) p.ui.tab = tab; }, { history: false, plan: false, autosave: false });
    },
    edit(fn, opts) {
      store.update(fn, opts);
    },
    editScene(id, fn, opts) {
      store.update(p => { const s = p.scenes.find(x => x.id === id); if (s) fn(s, p); }, opts);
    },
    addScene(afterId) {
      store.update(p => {
        const i = afterId ? sceneIndex(p, afterId) : p.scenes.length - 1;
        const s = defaultScene(p, { title: "Scene " + (p.scenes.length + 1) });
        p.scenes.splice(i + 1, 0, s);
        p.ui.selected = s.id;
      });
    },
    duplicateScene(id) {
      store.update(p => {
        const i = sceneIndex(p, id);
        if (i < 0) return;
        const copy = structuredClone(p.scenes[i]);
        copy.id = newId("s");
        copy.title = copy.title + " (copy)";
        for (const list of [copy.refs, copy.shots, copy.dialogue]) for (const x of list) x.id = newId(x.id.split("_")[0]);
        p.scenes.splice(i + 1, 0, copy);
        p.ui.selected = copy.id;
      });
    },
    deleteScene(id) {
      if (store.project.scenes.length <= 1) { actions.toast("A project needs at least one scene.", "warn"); return; }
      store.update(p => {
        const i = sceneIndex(p, id);
        if (i < 0) return;
        p.scenes.splice(i, 1);
        if (p.scenes[0]) p.scenes[0].start.mode = "fresh";
        p.ui.selected = p.scenes[Math.min(i, p.scenes.length - 1)].id;
      });
    },
    moveScene(id, dir) {
      store.update(p => {
        const i = sceneIndex(p, id), j = i + dir;
        if (i < 0 || j < 0 || j >= p.scenes.length) return;
        [p.scenes[i], p.scenes[j]] = [p.scenes[j], p.scenes[i]];
        p.scenes[0].start.mode = "fresh";
      });
    },
    splitScene(id, at) {
      const s = store.project.scenes.find(x => x.id === id);
      const minT = 1 / FPS;
      if (!s || at < minT || at > s.duration - minT) { actions.toast("Put the playhead inside the scene to split it.", "warn"); return; }
      store.update(p => {
        const i = sceneIndex(p, id);
        const a = p.scenes[i];
        const b = structuredClone(a);
        b.id = newId("s");
        b.title = a.title + " (2)";
        b.duration = Math.round((a.duration - at) * FPS) / FPS;
        a.duration = Math.round(at * FPS) / FPS;
        b.start = { mode: "last_frame", overlap_frames: a.start.overlap_frames };
        const keepA = x => x.t < at, keepB = x => x.t >= at;
        b.shots = a.shots.filter(keepB).map(x => ({ ...x, id: newId("h"), t: x.t - at }));
        b.dialogue = a.dialogue.filter(keepB).map(x => ({ ...x, id: newId("d"), t: x.t - at }));
        a.shots = a.shots.filter(keepA);
        a.dialogue = a.dialogue.filter(keepA);
        b.refs = a.refs.filter(r => r.role !== "keyframe" || r.time >= at).map(r => ({ ...r, id: newId("r"), time: r.role === "keyframe" ? r.time - at : r.time }));
        a.refs = a.refs.filter(r => r.role !== "keyframe" || r.time < at);
        p.scenes.splice(i + 1, 0, b);
        p.ui.selected = b.id;
      });
    },
    async run(action, scenes = []) {
      const request = { action, scenes, token: Date.now() };
      host.setProject(JSON.stringify(store.project));
      try {
        await host.queue(request);
        store.setEph({ running: true });
        actions.toast(action === "take" ? "Queued a new take." : "Render queued.", "ok");
      } catch (err) {
        actions.toast("Could not queue: " + err.message, "error");
      }
    },
    async merge() {
      store.setEph({ merge: { phase: "start" } });
      try {
        const res = await rw.merge(store.project);
        store.setEph({ merge: { phase: "end", files: res.files, duration: res.duration } });
        actions.toast("Merged " + fmtTime(res.duration || 0) + " → " + (res.files?.video || ""), "ok");
      } catch (err) {
        store.setEph({ merge: { phase: "error", error: err.message } });
        actions.toast("Merge failed: " + err.message, "error");
      }
    },
    async refreshTakes() {
      try { store.setEph({ takes: await rw.takes(store.project.slug) }); } catch { /* backend offline: keep last */ }
    },
    async refreshModels() {
      try { store.setEph({ models: await rw.models() }); } catch { store.setEph({ models: null }); }
    },
    async refreshInfo() {
      try { store.setEph({ info: await rw.info() }); } catch { store.setEph({ info: null }); }
    },
    toast(message, kind = "info") {
      const t = { id: Math.random(), message, kind };
      store.setEph({ toasts: [...store.eph.toasts, t] });
      setTimeout(() => store.setEph({ toasts: store.eph.toasts.filter(x => x !== t) }), kind === "error" ? 7000 : 3500);
    },
    toggleIssues(open) {
      store.setEph({ issuesOpen: open ?? !store.eph.issuesOpen });
    },
    gotoIssue(issue) {
      if (issue.scene_id) actions.select(issue.scene_id, "scene");
      actions.toggleIssues(false);
    },
  };

  function allIssues() {
    const p = store.project;
    const list = [...(store.eph.plan?.issues || [])];
    for (const s of p.scenes) {
      for (const msg of budgetIssues(sceneBudget(p, s))) list.push({ level: "warn", scene_id: s.id, message: `${s.title}: ${msg}` });
      for (const i of store.eph.plan?.scenes?.[s.id]?.issues || []) list.push({ scene_id: s.id, ...i });
    }
    const seen = new Set();
    return list.filter(i => { const k = i.level + i.scene_id + i.message; if (seen.has(k)) return false; seen.add(k); return true; });
  }
  ctx.allIssues = allIssues;

  function pendingCount() {
    const plan = store.eph.plan?.scenes;
    if (!plan) return null;
    return store.project.scenes.filter(s => PENDING.has(plan[s.id]?.status)).length;
  }
  ctx.pendingCount = pendingCount;

  function renderTabbar() {
    const p = store.project;
    const active = p.ui.tab;
    const idx = Math.max(0, sceneIndex(p, ctx.scene?.id)) + 1;
    const pend = pendingCount();
    const issues = allIssues();
    const errors = issues.filter(i => i.level === "error").length;
    const counts = {
      scene: String(idx).padStart(2, "0"), assets: p.assets.length, cast: p.cast.length,
      render: pend === null ? "" : pend,
    };
    tabbar.replaceChildren(
      h("div", { class: "rw-brand", help: "app.brand" }, icon("clapper", 15), h("b", null, "Reelwright"), h("span", { class: "mono rw-dim" }, "v" + VERSION)),
      ...Object.entries(TABS).map(([id, t]) => h("button", {
        type: "button", class: ["rw-tab", id === active && "on"], help: "tab." + id,
        onClick: () => actions.setTab(id),
      }, icon(t.icon, 15), t.label, counts[id] !== undefined && counts[id] !== "" && h("span", { class: ["rw-tab-count mono", id === "render" && pend ? "warn" : id === "scene" && "accent"] }, counts[id]))),
      h("span", { class: "rw-flex" }),
      h("span", { class: ["rw-backend", store.eph.backend], help: "app.backend" }, h("span", { class: "rw-led" }), store.eph.backend === "online" ? "backend" : store.eph.backend),
      button({ icon: "undo", help: "app.undo", onClick: () => store.undo(), disabled: !store.canUndo(), variant: "ghost" }),
      button({ icon: "redo", help: "app.redo", onClick: () => store.redo(), disabled: !store.canRedo(), variant: "ghost" }),
      h("span", { class: "rw-sep" }),
      button({
        label: issues.length ? `${issues.length} issue${issues.length > 1 ? "s" : ""}` : "Valid", icon: issues.length ? "warn" : "check",
        help: "app.issues", variant: errors ? "danger-ghost" : issues.length ? "warn-ghost" : "ok-ghost", onClick: () => actions.toggleIssues(),
      }),
      button({ label: "Merge scenes", icon: "merge", help: "app.merge", onClick: () => actions.merge() }),
      button({
        label: pend ? `Render pending · ${pend}` : "Render pending", icon: "play", help: "app.renderPending", variant: "primary",
        onClick: () => actions.run("pending"),
      }),
    );
  }

  function renderFooter() {
    const p = store.project;
    const g = p.global;
    const { total } = sceneStarts(p);
    const issues = allIssues();
    const plan = store.eph.plan?.scenes || {};
    const st = { cached: 0, stale: 0, pending: 0 };
    for (const s of p.scenes) {
      const v = plan[s.id]?.status;
      if (v === "cached" || v === "locked") st.cached++;
      else if (v === "stale") st.stale++;
      else if (v) st.pending++;
    }
    const running = Object.values(store.eph.progress).find(x => !["done", "cached", "error"].includes(x.phase));
    footer.replaceChildren(
      h("span", { class: "rw-foot-item", help: "footer.issues" },
        h("span", { class: ["rw-led", issues.some(i => i.level === "error") ? "error" : issues.length ? "warn" : "ok"] }),
        issues.length ? issues[0].message : "All scenes within H3 limits"),
      h("span", { class: "rw-foot-sep" }),
      h("span", { class: "rw-foot-item mono", help: "footer.output" }, `${g.output.width}×${g.output.height} · 24 fps · 32 kHz stereo · ${g.quality}`),
      h("span", { class: "rw-foot-sep" }),
      h("span", { class: "rw-foot-item", help: "footer.status" }, store.eph.plan
        ? `On disk ${st.cached} · Stale ${st.stale} · Pending ${st.pending}` : "Render status unavailable"),
      running ? h("span", { class: "rw-foot-item rw-c-pic", help: "footer.running" },
        `Rendering ${p.scenes.find(s => s.id === running.scene_id)?.title || ""} · pass ${running.pass}/${running.passes} · ${running.phase} ${running.step ? running.step + "/" + running.steps : ""}`) : "",
      h("span", { class: "rw-flex" }),
      h("span", { class: "rw-foot-item mono", help: "footer.length" }, `${p.scenes.length} scenes · ${fmtTime(total)} · cut ${fmtTime(assembledDuration(p))}`),
      h("span", { class: "rw-foot-sep" }),
      h("span", { class: ["rw-foot-item", "save-" + store.eph.saveState], help: "footer.save" }, store.eph.saveState === "saved" ? "Saved" : store.eph.saveState === "pending" ? "Saving…" : "Autosave offline"),
    );
  }

  function renderDrawer() {
    drawer.classList.toggle("on", !!store.eph.issuesOpen);
    if (!store.eph.issuesOpen) { drawer.replaceChildren(); return; }
    const issues = allIssues();
    drawer.replaceChildren(
      h("div", { class: "rw-drawer-head" }, h("b", null, "Issues"), h("span", { class: "rw-dim" }, `${issues.length}`),
        h("button", { type: "button", class: "rw-q", dataset: { more: "app.issues" }, help: "app.issues", "aria-label": "Help" }, "?"),
        h("span", { class: "rw-flex" }),
        button({ icon: "close", help: "common.close", variant: "ghost", onClick: () => actions.toggleIssues(false) })),
      issues.length ? h("div", { class: "rw-issue-list", dataset: { scroll: "issues" } }, issues.map(i => h("button", {
        type: "button", class: ["rw-issue", i.level], help: "app.issueItem", onClick: () => actions.gotoIssue(i),
      }, icon(i.level === "info" ? "info" : "warn", 13), h("span", null, i.message)))) : h("div", { class: "rw-empty" }, "No issues. Every scene fits H3's limits."));
  }

  function renderToasts() {
    toasts.replaceChildren(...store.eph.toasts.map(t => h("div", { class: ["rw-toast", t.kind] }, t.message)));
  }

  let frame = 0;
  function render() {
    frame = 0;
    const scroll = {};
    root.querySelectorAll("[data-scroll]").forEach(el => { scroll[el.dataset.scroll] = [el.scrollLeft, el.scrollTop]; });
    const focused = root.querySelector(":focus");
    const focusKey = focused?.dataset?.key;
    const sel = focused && typeof focused.selectionStart === "number" ? [focused.selectionStart, focused.selectionEnd] : null;

    renderTabbar();
    const tab = TABS[store.project.ui.tab] || TABS.timeline;
    body.replaceChildren(tab.mod.render(ctx));
    renderFooter();
    renderDrawer();
    renderToasts();

    root.querySelectorAll("[data-scroll]").forEach(el => {
      const s = scroll[el.dataset.scroll];
      if (s) { el.scrollLeft = s[0]; el.scrollTop = s[1]; }
    });
    if (focusKey) {
      const el = root.querySelector(`[data-key="${CSS.escape(focusKey)}"]`);
      if (el) {
        el.focus({ preventScroll: true });
        if (sel && typeof el.setSelectionRange === "function") { try { el.setSelectionRange(sel[0], sel[1]); } catch { /* not a text field */ } }
      }
    } else if (focused === root || !root.contains(document.activeElement)) {
      /* keep focus where it was */
    }
    tab.mod.afterRender?.(ctx);
  }
  ctx.render = render;
  store.subscribe(() => { if (!frame) frame = requestAnimationFrame(render); });

  root.addEventListener("pointerdown", e => {
    if (!e.target.closest("input, textarea, select, [contenteditable]")) root.focus({ preventScroll: true });
  }, true);
  root.addEventListener("keydown", e => {
    e.stopPropagation();
    const typing = e.target.matches?.("input, textarea, select, [contenteditable]");
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); store.saveNow(); actions.toast("Saved.", "ok"); return; }
    if (typing) return;
    if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); if (e.shiftKey) store.redo(); else store.undo(); return; }
    if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); store.redo(); return; }
    if (e.key === "?") { e.preventDefault(); tips.openPopover("tab." + store.project.ui.tab, root.querySelector(".rw-tab.on") || root); return; }
    const tab = TABS[store.project.ui.tab];
    if (tab.mod.onKey?.(ctx, e)) { e.preventDefault(); return; }
    if (timeline.sceneKeys(ctx, e)) e.preventDefault();
  });
  for (const ev of ["keyup", "keypress", "wheel", "copy", "paste", "cut"]) root.addEventListener(ev, e => e.stopPropagation());

  const lastProgressRender = { at: 0 };
  host.on("reelwright.progress", d => {
    if (d.slug !== store.project.slug) return;
    store.eph.progress[d.scene_id] = d;
    if (["done", "cached", "error"].includes(d.phase)) {
      actions.refreshTakes();
      store.refreshPlan();
    }
    const now = Date.now();
    if (now - lastProgressRender.at > 250 || d.phase !== "sample") { lastProgressRender.at = now; store.notify(); }
  });
  host.on("reelwright.run", d => {
    if (d.slug !== store.project.slug) return;
    if (d.phase === "start") store.setEph({ running: true });
    else {
      store.setEph({ running: false });
      actions.refreshTakes();
      store.refreshPlan();
      if (d.error) actions.toast("Render stopped: " + d.error, "error");
      else actions.toast(`Render finished · ${d.targets?.length || 0} generated · ${d.reused?.length || 0} reused`, "ok");
    }
  });
  host.on("reelwright.merge", d => {
    if (d.slug !== store.project.slug) return;
    store.setEph({ merge: d });
  });

  render();
  store.refreshPlan();
  actions.refreshTakes();
  actions.refreshModels();
  actions.refreshInfo();

  return {
    root,
    load(json) { store.load(json); },
    get project() { return store.project; },
    destroy() { timeline.stopPlayback(ctx); root.remove(); },
  };
}
