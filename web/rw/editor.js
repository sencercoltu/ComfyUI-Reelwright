// Editor root: tab bar, active tab, footer, toasts, issues drawer, keyboard and
// websocket wiring. `host` adapts ComfyUI (or the test harness) to the editor.

import { rw, setHost } from "./api.js";
import { createStore } from "./store.js";
import { installTooltips } from "./tooltip.js";
/* [OLD 2026-11-02 v0.1.0->v0.2.0] comboState is needed for the render guard
import { h, icon, button } from "./ui.js";
[/OLD] */
/* [OLD 2026-11-02 v0.2.1->v0.2.2] contextMenu added
import { h, icon, button, comboState } from "./ui.js";
[/OLD] */
/* [OLD 2026-11-02 v0.2.2->v0.3.0] confirmDialog added
import { h, icon, button, comboState, contextMenu } from "./ui.js";
[/OLD] */
import { h, icon, button, comboState, contextMenu, confirmDialog } from "./ui.js";
import { VERSION } from "./version.js";
import {
  normalizeProject, defaultScene, newId, sceneIndex, sceneStarts, assembledDuration, fmtTime,
  sceneBudget, budgetIssues, FPS,
  normalizeGlobal, assetUsage, assetCastUse, findAsset, // added 2026-11-02 v0.3.0
} from "./model.js";
import * as timeline from "./tabs/timeline.js";
import * as sceneTab from "./tabs/scene.js";
import * as assetsTab from "./tabs/assets.js";
import * as castTab from "./tabs/cast.js";
import * as renderTab from "./tabs/render.js";
import * as globalTab from "./tabs/global.js";
import * as filesTab from "./tabs/files.js"; // added 2026-11-03 v0.4.0
// [OLD 2026-11-02 v0.3.8->v0.3.9] import { createPreviewView } from "./preview.js"; // added 2026-11-02 v0.3.8
import { createPreviewView, imageBlob } from "./preview.js"; // added 2026-11-02 v0.3.8; imageBlob added v0.3.9

const TABS = {
  timeline: { label: "Timeline", icon: "timeline", mod: timeline },
  scene: { label: "Scene", icon: "scene", mod: sceneTab },
  assets: { label: "Assets", icon: "assets", mod: assetsTab },
  cast: { label: "Cast", icon: "cast", mod: castTab },
  render: { label: "Render", icon: "render", mod: renderTab },
  files: { label: "Files", icon: "disk", mod: filesTab }, // added 2026-11-03 v0.4.0: disk use and deleting
  global: { label: "Global", icon: "global", mod: globalTab },
};

const PENDING = new Set(["stale", "pending", "missing", "queued"]);

// added 2026-11-02 v0.2.2: ComfyUI handles some events before they reach the editor. With "Nodes 2.0"
// (Vue nodes) on, a right-click inside the node opened the node's own menu (Delete removes the whole node)
// and the mouse wheel zoomed the canvas instead of scrolling lists. Window capture listeners run before
// anything ComfyUI attaches to the page, so events that start inside an editor stop there and are routed
// to the editor's own handlers (`menu` and `wheel` props in ui.js).
function installEventGuards() {
  if (window.__rwEventGuards) return;
  window.__rwEventGuards = true;
  const rootOf = e => (e.target instanceof Element ? e.target.closest(".rw-root") : null);
  const find = (e, root, key) => {
    for (let el = e.target; el && el !== root.parentNode; el = el.parentNode) if (el[key]) return el;
    return null;
  };
  window.addEventListener("contextmenu", e => {
    const root = rootOf(e);
    if (!root) return;
    e.stopPropagation();
    const el = find(e, root, "__rwMenu");
    const items = el ? el.__rwMenu(e) : null;
    if (items && items.length) { e.preventDefault(); contextMenu(root, e.clientX, e.clientY, items); return; }
    // text fields keep the browser's menu (copy, paste, spelling); elsewhere there is nothing to offer
    if (!e.target.closest("input, textarea, [contenteditable]")) e.preventDefault();
  }, true);
  window.addEventListener("wheel", e => {
    const root = rootOf(e);
    if (!root) return;
    e.stopPropagation(); // the default scroll still happens
    /* [OLD 2026-11-02 v0.2.2->v0.3.0] Ctrl + wheel did nothing over the node
    const el = find(e, root, "__rwWheel");
    if (el) el.__rwWheel(e);
    if ((e.ctrlKey || e.metaKey) && !e.defaultPrevented) e.preventDefault(); // no browser page zoom over the editor
    [/OLD] */
    if (e.ctrlKey || e.metaKey) {
      // Ctrl/Cmd + wheel zooms ComfyUI's canvas, except over a text field or an open list
      e.preventDefault(); // never the browser's page zoom
      if (!e.target.closest("input, textarea, select, [contenteditable], .rw-combo-list")) root.__rwHost?.forwardWheel?.(e);
      return;
    }
    const el = find(e, root, "__rwWheel");
    if (el) el.__rwWheel(e);
  }, { capture: true, passive: false });
}

export function mountEditor(container, host) {
  installEventGuards(); // added 2026-11-02 v0.2.2
  setHost(host);
  const store = createStore(normalizeProject(host.getProject()), { persist: json => host.setProject(json) });
  const root = h("div", { class: "rw-root", tabindex: "0" });
  root.__rwHost = host; // added 2026-11-02 v0.3.0: the wheel guard forwards Ctrl + wheel to the canvas
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

  let mergeInFlight = false; // added 2026-11-02 v0.2.1
  const actions = ctx.actions = {
    setTab(tab) {
      store.update(p => { p.ui.tab = tab; }, { history: false, plan: false, autosave: false });
      // added 2026-11-03 v0.4.0: renders, merges and other nodes change the folders; rescan (in the background) on every visit
      if (tab === "files" && store.eph.files) filesTab.refresh(ctx);
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
    /* [OLD 2026-11-02 v0.2.2->v0.3.0] no confirmation, and the last scene could not be deleted (it stayed as it was)
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
    [/OLD] */
    async deleteScene(id, { ask = true } = {}) {
      const s = store.project.scenes.find(x => x.id === id);
      if (!s) return false;
      const last = store.project.scenes.length <= 1;
      if (ask && !(await confirmDialog(root, last
        ? { title: `Reset “${s.title}”?`, confirmLabel: "Reset scene",
          message: "It is the only scene, so it is replaced by an empty one: title, length, shots, dialogue, references, cast, prompt, overrides and transition go back to the defaults. Rendered takes stay on disk. Ctrl+Z undoes this." }
        : { title: `Delete “${s.title}”?`, confirmLabel: "Delete scene",
          message: "Its shots, dialogue, references and prompt are removed from the project. Rendered takes stay on disk. Ctrl+Z undoes this." }))) return false;
      store.update(p => {
        const i = sceneIndex(p, id);
        if (i < 0) return;
        if (p.scenes.length <= 1) {
          const fresh = defaultScene(p, { title: "Scene 1" });
          fresh.start.mode = "fresh";
          p.scenes = [fresh];
          p.ui.selected = fresh.id;
          p.ui.playhead = 0;
          return;
        }
        p.scenes.splice(i, 1);
        if (p.scenes[0]) p.scenes[0].start.mode = "fresh";
        p.ui.selected = p.scenes[Math.min(i, p.scenes.length - 1)].id;
      });
      return true;
    },
    // added 2026-11-02 v0.3.0: delete an asset (with confirmation) and every reference to it
    async deleteAsset(id) {
      const p = store.project;
      const a = findAsset(p, id);
      if (!a) return false;
      const uses = assetUsage(p, id).length, castUses = assetCastUse(p, id).length;
      const what = [uses ? `${uses} scene reference${uses > 1 ? "s" : ""}` : "", castUses ? `${castUses} cast link${castUses > 1 ? "s" : ""}` : ""].filter(Boolean).join(" and ");
      if (!(await confirmDialog(root, { title: `Delete ${a.code} “${a.name || a.file}”?`, confirmLabel: "Delete asset",
        message: (what ? `It is removed from the project together with its ${what}. ` : "It is removed from the project. ") +
          "The file stays in ComfyUI's input folder. Ctrl+Z undoes this." }))) return false;
      store.update(q => {
        q.assets = q.assets.filter(x => x.id !== id);
        for (const s of q.scenes) s.refs = s.refs.filter(r => r.asset !== id);
        for (const c of q.cast) { c.anchors = c.anchors.filter(x => x !== id); if (c.voice === id) c.voice = ""; for (const o of c.outfits || []) o.assets = (o.assets || []).filter(x => x !== id); }
        if (q.global.merge.score.asset === id) q.global.merge.score.asset = "";
      });
      store.setEph({ selectedAsset: "" });
      actions.toast(`Deleted ${a.code}.`, "info");
      return true;
    },
    // added 2026-11-02 v0.3.0: Global profiles
    applyProfile(prof) {
      store.update(p => { p.global = normalizeGlobal(prof.global, p); });
      store.setEph({ fresh: false, profileSel: prof.id });
      actions.toast(`Applied profile “${prof.name}”. Ctrl+Z undoes this.`, "ok");
    },
    async loadProfiles() {
      try { const r = await rw.profiles(); store.setEph({ profiles: r }); return r; }
      catch { store.setEph({ profiles: { profiles: [], default: "", offline: true } }); return null; }
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
      mergeInFlight = true; // added 2026-11-02 v0.2.1: the HTTP reply reports errors, so the websocket toast is skipped
      try {
        const res = await rw.merge(store.project);
        store.setEph({ merge: { phase: "end", files: res.files, duration: res.duration } });
        actions.toast("Merged " + fmtTime(res.duration || 0) + " → " + (res.files?.video || ""), "ok");
      } catch (err) {
        store.setEph({ merge: { phase: "error", error: err.message } });
        actions.toast("Merge failed: " + err.message, "error");
      } finally {
        mergeInFlight = false;
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
      /* [OLD 2026-11-02 v0.1.0->v0.2.0] Merge moved into the Render tab, next to scene states and takes
      button({ label: "Merge scenes", icon: "merge", help: "app.merge", onClick: () => actions.merge() }),
      [/OLD] */
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
    // added 2026-11-02 v0.2.0: an open combobox list lives in the root; re-rendering under it would
    // orphan the list, so wait until it closes
    if (comboState.open) { comboState.onClose = () => { if (!frame) frame = requestAnimationFrame(render); }; return; }
    const scroll = {};
    root.querySelectorAll("[data-scroll]").forEach(el => { scroll[el.dataset.scroll] = [el.scrollLeft, el.scrollTop]; });
    const focused = root.querySelector(":focus");
    const focusKey = focused?.dataset?.key;
    const sel = focused && typeof focused.selectionStart === "number" ? [focused.selectionStart, focused.selectionEnd] : null;
    // added 2026-11-03 v0.4.1: a text field being typed in keeps what is typed. Most fields store their value on
    // change (Enter or leaving the field), so a re-render in between (progress, plan refresh, autosave status) rebuilt
    // the field with the stored value and the caret landed in the wrong place: "Sencer" came out as "Seernc".
    const textField = !!focused?.matches?.("input:not([type=checkbox]):not([type=radio]):not([type=range]), textarea");
    const typing = textField ? focused.value : null;
    // a field without a key is found again by its help id and position (it used to lose focus)
    const helpId = textField && !focusKey ? focused.dataset.help : null;
    const helpPos = helpId ? [...root.querySelectorAll(`${focused.tagName}[data-help="${CSS.escape(helpId)}"]`)].indexOf(focused) : -1;

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
    // [OLD 2026-11-03 v0.4.0->v0.4.1] if (focusKey) {
    // [OLD 2026-11-03 v0.4.0->v0.4.1]   const el = root.querySelector(`[data-key="${CSS.escape(focusKey)}"]`);
    if (focusKey || helpPos >= 0) {
      const el = focusKey ? root.querySelector(`[data-key="${CSS.escape(focusKey)}"]`)
        : root.querySelectorAll(`${focused.tagName}[data-help="${CSS.escape(helpId)}"]`)[helpPos];
      if (el && el !== focused) {
        /* [OLD 2026-11-02 v0.1.0->v0.2.0] re-focusing a combobox would reopen its list
        el.focus({ preventScroll: true });
        [/OLD] */
        if (typing !== null && "value" in el && el.value !== typing) el.value = typing; // added 2026-11-03 v0.4.1
        comboState.restoring = true;
        try { el.focus({ preventScroll: true }); } finally { comboState.restoring = false; }
        if (sel && typeof el.setSelectionRange === "function") { try { el.setSelectionRange(sel[0], sel[1]); } catch { /* not a text field */ } }
      }
    } else if (focused === root || !root.contains(document.activeElement)) {
      /* keep focus where it was */
    }
    tab.mod.afterRender?.(ctx);
  }
  ctx.render = render;
  store.subscribe(() => { if (!frame) frame = requestAnimationFrame(render); });

  /* [OLD 2026-11-02 v0.2.1->v0.2.2] clicking a combobox list (e.g. its scrollbar) moved focus to the root, which closed the list
  root.addEventListener("pointerdown", e => {
    if (!e.target.closest("input, textarea, select, [contenteditable]")) root.focus({ preventScroll: true });
  }, true);
  [/OLD] */
  root.addEventListener("pointerdown", e => {
    if (!e.target.closest("input, textarea, select, [contenteditable], .rw-combo-list, .rw-ctx")) root.focus({ preventScroll: true });
  }, true);
  // added 2026-11-02 v0.3.3: presses the editor handles itself (timeline pan) stop at the root, after the root's own
  // listeners (tooltips) have seen them, so ComfyUI doesn't also drag the node
  root.addEventListener("pointerdown", e => { if (e.rwOwned) e.stopPropagation(); });
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

  // added 2026-11-02 v0.3.0: progress of the whole run (scene k of n) for the Render tab and the node title
  function runProgress() {
    const run = store.eph.run;
    if (!run || !run.targets?.length) return null;
    const n = run.targets.length;
    const cur = Object.values(store.eph.progress).find(x => run.targets.includes(x.scene_id) && !["done", "cached", "error"].includes(x.phase));
    let part = 0;
    if (cur) {
      const passes = Math.max(1, cur.passes || 1);
      const within = cur.phase === "sample" && cur.steps ? cur.step / cur.steps : ["decode", "save"].includes(cur.phase) ? 1 : 0;
      part = Math.min(1, ((Math.max(1, cur.pass || 1) - 1) + within) / passes);
    }
    const done = run.done.length;
    return { n, done, index: Math.min(n, done + (cur ? 1 : 0)), current: cur || null, scenePart: part, total: Math.min(1, (done + part) / n), reused: run.reused || [] };
  }
  ctx.runProgress = runProgress;
  function updateTitle() {
    const r = runProgress();
    host.setTitle?.(r ? `rendering ${Math.max(1, r.index)}/${r.n} · ${Math.round(r.total * 100)}%` : null);
  }

  const lastProgressRender = { at: 0 };
  host.on("reelwright.progress", d => {
    if (d.slug !== store.project.slug) return;
    store.eph.progress[d.scene_id] = d;
    if (store.eph.run && ["done", "cached", "error"].includes(d.phase) && !store.eph.run.done.includes(d.scene_id)) store.eph.run.done.push(d.scene_id);
    updateTitle();
    if (["done", "cached", "error"].includes(d.phase)) {
      actions.refreshTakes();
      store.refreshPlan();
    }
    const now = Date.now();
    if (now - lastProgressRender.at > 250 || d.phase !== "sample") { lastProgressRender.at = now; store.notify(); }
  });
  // added 2026-11-02 v0.3.5: the latest latent preview, shown only in the Render tab's run banner
  /* [OLD 2026-11-02 v0.3.6->v0.3.7] only the backend's reelwright.preview events were shown
  host.on("reelwright.preview", d => {
    if (d.slug !== store.project.slug) return;
    store.eph.preview = d;
    if (store.project.ui.tab !== "render") return; // nothing else shows it, so no re-render elsewhere
    const now = Date.now();
    if (now - lastProgressRender.at > 250) { lastProgressRender.at = now; store.notify(); }
  });
  [/OLD] */
  // added 2026-11-02 v0.3.7: previews come from the backend (reelwright.preview, a data URL) or from ComfyUI's own
  // preview stream for this node (a Blob, redirected by web/reelwright.js); both end up in the Render tab
  /* [OLD 2026-11-02 v0.3.7->v0.3.8] the <img> was rebuilt from store.eph.preview on every (throttled) re-render and the previous object URL was
     revoked at once; a picture that failed to load showed as a broken-image icon
  function setPreview(p) {
    const old = store.eph.preview;
    if (old?.objectUrl && old.objectUrl !== p?.objectUrl) URL.revokeObjectURL(old.objectUrl);
    store.eph.preview = p;
    if (!p || store.project.ui.tab !== "render") return; // nothing else shows it, so no re-render elsewhere
    const now = Date.now();
    if (now - lastProgressRender.at > 250) { lastProgressRender.at = now; store.notify(); }
  }
  [/OLD] */
  // added 2026-11-02 v0.3.8: one preview window for the editor's lifetime (web/rw/preview.js). Each new image is decoded
  // off-screen and swapped in place, without re-rendering the tab, so it can follow every sampler step.
  const previewView = createPreviewView({
    captionFor: pv => {
      const i = store.project.scenes.findIndex(x => x.id === pv.scene_id);
      return [i >= 0 && String(i + 1).padStart(2, "0"), pv.passes && `pass ${pv.pass}/${pv.passes}`, pv.steps && `${pv.step}/${pv.steps}`].filter(Boolean).join(" · ");
    },
    onVisible: () => { if (store.project.ui.tab === "render") store.notify(); }, // the banner needs to make room once
  });
  ctx.previewFigure = () => previewView.element();
  function setPreview(p) {
    if (!p) previewView.clear();
    else previewView.show(p);
  }
  host.on("reelwright.preview", d => {
    if (d.slug !== store.project.slug) return;
    setPreview(d);
  });
  /* [OLD 2026-11-02 v0.3.7->v0.3.8] the object URL is now made (and released) by the preview window
  function showComfyPreview(blob) {
    const cur = Object.values(store.eph.progress).find(x => !["done", "cached", "error"].includes(x.phase)) || {};
    const url = URL.createObjectURL(blob);
    setPreview({ image: url, objectUrl: url, scene_id: cur.scene_id, pass: cur.pass, passes: cur.passes, step: cur.step, steps: cur.steps });
  }
  [/OLD] */
  /* [OLD 2026-11-02 v0.3.8->v0.3.9] the blob was shown as it came; VideoHelperSuite's animated previews put a header before the JPEG
  function showComfyPreview(blob) {
    const cur = Object.values(store.eph.progress).find(x => !["done", "cached", "error"].includes(x.phase)) || {};
    setPreview({ blob, scene_id: cur.scene_id, pass: cur.pass, passes: cur.passes, step: cur.step, steps: cur.steps });
  }
  [/OLD] */
  // added 2026-11-02 v0.3.9
  let comfySeq = 0;
  function showComfyPreview(blob) {
    // the scene of this run that is sampling (an older, unfinished progress entry can belong to another scene)
    const cur = runProgress()?.current || Object.values(store.eph.progress).find(x => !["done", "cached", "error"].includes(x.phase)) || {};
    const meta = { scene_id: cur.scene_id, pass: cur.pass, passes: cur.passes, step: cur.step, steps: cur.steps };
    const seq = ++comfySeq;
    imageBlob(blob).catch(() => blob).then(b => {
      if (seq !== comfySeq || !store.eph.running) return; // a newer one is on its way, or the run is over
      setPreview({ ...meta, blob: b });
    });
  }
  host.on("reelwright.run", d => {
    if (d.slug !== store.project.slug) return;
    // [OLD 2026-11-02 v0.2.2->v0.3.0] if (d.phase === "start") store.setEph({ running: true });
    // [OLD 2026-11-02 v0.3.4->v0.3.5] if (d.phase === "start") { store.setEph({ running: true, run: { targets: d.targets || [], reused: d.reused || [], done: [], started: Date.now() } }); updateTitle(); }
    // [OLD 2026-11-02 v0.3.6->v0.3.7] if (d.phase === "start") { store.setEph({ running: true, preview: null, run: { targets: d.targets || [], reused: d.reused || [], done: [], started: Date.now() } }); updateTitle(); }
    if (d.phase === "start") { setPreview(null); store.setEph({ running: true, run: { targets: d.targets || [], reused: d.reused || [], done: [], started: Date.now() } }); updateTitle(); }
    else {
      // [OLD 2026-11-02 v0.3.4->v0.3.5] store.setEph({ running: false, run: null });
      // [OLD 2026-11-02 v0.3.6->v0.3.7] store.setEph({ running: false, run: null, preview: null });
      setPreview(null);
      store.setEph({ running: false, run: null });
      host.setTitle?.(null);
      actions.refreshTakes();
      store.refreshPlan();
      if (d.error) actions.toast("Render stopped: " + d.error, "error");
      else actions.toast(`Render finished · ${d.targets?.length || 0} generated · ${d.reused?.length || 0} reused`, "ok");
    }
  });
  /* [OLD 2026-11-02 v0.2.0->v0.2.1] a failed merge (e.g. the automatic one after a render) was not shown
  host.on("reelwright.merge", d => {
    if (d.slug !== store.project.slug) return;
    store.setEph({ merge: d });
  });
  [/OLD] */
  host.on("reelwright.merge", d => {
    if (d.slug !== store.project.slug) return;
    if (d.error) {
      store.setEph({ merge: { ...d, phase: "error" } });
      if (!mergeInFlight) actions.toast("Merge failed: " + d.error.split("\n").filter(Boolean).slice(-1)[0], "error");
      return;
    }
    store.setEph({ merge: d });
  });

  render();
  store.refreshPlan();
  actions.refreshTakes();
  actions.refreshModels();
  actions.refreshInfo();

  return {
    root,
    // added 2026-11-02 v0.3.0: called for a node that was just added (not loaded from a workflow)
    showComfyPreview, // added 2026-11-02 v0.3.7: ComfyUI's preview stream for this node, redirected by reelwright.js
    async startNew() {
      store.setEph({ fresh: true });
      const r = await actions.loadProfiles();
      const d = r?.profiles?.find(x => x.id === r.default);
      if (d) {
        store.update(p => { p.global = normalizeGlobal(d.global, p); }, { history: false });
        store.setEph({ profileSel: d.id });
        actions.toast(`New project: using profile “${d.name}”.`, "ok");
      }
    },
    load(json) { store.load(json); },
    get project() { return store.project; },
    // [OLD 2026-11-02 v0.3.7->v0.3.8] destroy() { timeline.stopPlayback(ctx); root.remove(); },
    destroy() { timeline.stopPlayback(ctx); previewView.clear(); root.remove(); },
  };
}
