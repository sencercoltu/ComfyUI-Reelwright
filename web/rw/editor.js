// Editor root: tab bar, active tab, footer, toasts, issues drawer, keyboard and
// websocket wiring. `host` adapts ComfyUI (or the test harness) to the editor.

import { rw, setHost } from "./api.js";
// [OLD 2026-11-03 v0.5.1->v0.6.0] import { createStore } from "./store.js";
import { createStore, withProjectId } from "./store.js";
import * as M from "./model.js"; // added 2026-11-03 v0.6.0: model APIs that may not exist yet (nextSeedN, migrateScore)
import { clearAnchorFrame } from "./model.js"; // added 2026-11-10 v0.18.0: deleting a video asset clears its anchors' frame pictures
import { hiresSize } from "./model.js"; // added 2026-11-10 v0.19.0: the footer shows the Hires size
// added 2026-11-10 v0.19.0: " → 2688×1536" while Global → Hires is on
function hiresLabel(g) {
  const [w, h] = hiresSize(g);
  return w !== g.output.width || h !== g.output.height ? ` → ${w}×${h}` : "";
}
import { newJob } from "./llmjob.js"; // added 2026-11-03 v0.6.0: merge job ids
import { ownJobs, jobLine } from "./llmjob.js"; // added 2026-11-06 v0.10.2: LLM progress in place, own jobs only
import { feedStream } from "./llmjob.js"; // added 2026-11-09 v0.15.0: the reasoning and answer received, for the output popup
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
// [OLD 2026-11-03 v0.5.1->v0.6.0] import { h, icon, button, comboState, contextMenu, confirmDialog } from "./ui.js";
import { h, icon, button, comboState, contextMenu, confirmDialog, choiceDialog, focusGuard, isTextField } from "./ui.js";
import { copyMenuItems, copyButton } from "./ui.js"; // added 2026-11-06 v0.10.0: right-click Copy text, Issues → Copy all
import { foldScope } from "./ui.js"; // added 2026-11-09 v0.14.1: every card on every tab folds
import { VERSION } from "./version.js";
import {
  normalizeProject, defaultScene, newId, sceneIndex, sceneStarts, assembledDuration, fmtTime,
  sceneBudget, budgetIssues, FPS,
  normalizeGlobal, assetUsage, assetCastUse, findAsset, // added 2026-11-02 v0.3.0
  overruns, lengthenToFit, // added 2026-11-03 v0.4.3
} from "./model.js";
import * as timeline from "./tabs/timeline.js";
import * as sceneTab from "./tabs/scene.js";
import * as assetsTab from "./tabs/assets.js";
import * as castTab from "./tabs/cast.js";
import * as renderTab from "./tabs/render.js";
import * as globalTab from "./tabs/global.js";
import * as filesTab from "./tabs/files.js"; // added 2026-11-03 v0.4.0
import * as chatTab from "./tabs/chat.js"; // added 2026-11-08 v0.13.0: general questions to the LLM
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
  // added 2026-11-08 v0.13.0: shown only while an LLM base URL is set (when: chatTab.enabled)
  chat: { label: "Chat", icon: "dialogue", mod: chatTab, when: ctx => chatTab.enabled(ctx) },
};

const PENDING = new Set(["stale", "pending", "missing", "queued"]);
// added 2026-11-03 v0.6.0: progress phases after which a scene is no longer rendering ("error": it failed, "skipped":
// it depends on a scene that failed)
const FINAL = new Set(["done", "cached", "error", "skipped"]);

// added 2026-11-04 v0.6.1: a key press for the single-key shortcuts: no Ctrl, Cmd or Alt held. AltGr, which Windows
// reports as Ctrl+Alt, still counts for the symbol it types (+ - = ? on keyboard layouts that need it), never for a letter.
function plainKey(e) {
  if (e.metaKey) return false;
  if (!e.ctrlKey && !e.altKey) return true;
  return !!e.getModifierState?.("AltGraph") && e.key.length === 1 && !/\p{L}/u.test(e.key);
}

// added 2026-11-03 v0.6.0: a fresh per-scene seed number (stable seeds, model.nextSeedN); undefined with a model.js
// that has no seed numbers yet
function freshSeedN(p) {
  if (typeof M.nextSeedN === "function") return M.nextSeedN(p);
  const ns = p.scenes.map(s => s.seed_n).filter(Number.isInteger);
  return ns.length ? Math.max(...ns) + 1 : undefined;
}

// added 2026-11-03 v0.6.0: a pre-0.5 `merge.score` (from an old profile) becomes a soundtrack track, as
// normalizeProject does on load; true when a track was added
function migrateScoreIn(p) {
  const before = p.soundtrack?.length || 0;
  if (typeof M.migrateScore === "function") { M.migrateScore(p); return (p.soundtrack?.length || 0) > before; }
  const score = p.global?.merge?.score;
  if (!score?.asset) return false;
  const id = p.soundtrack.some(t => t.id === "t_score") ? newId("t") : "t_score";
  p.soundtrack.push(M.normalizeTrack({ id, asset: score.asset, volume_db: Number(score.volume_db ?? -12), sync: false, mix: true, duck: score.duck !== false, loop: true }));
  score.asset = "";
  p.global.merge.scene_audio = { mix: true, volume_db: 0 };
  return true;
}

// added 2026-11-03 v0.6.0 review: a stable project id for a copy that keeps its own folder (editor.separateProjectId):
// "p_" + a 53-bit hash (cyrb53) of the shared id and the folder, in base 36
function derivedProjectId(id, slug) {
  const str = `${id}\u0000${slug}`;
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < str.length; i++) {
    const c = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 2654435761);
    h2 = Math.imul(h2 ^ c, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return "p_" + (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
}

// added 2026-11-03 v0.6.0: copies of scenes with new ids (scene, refs, shots, dialogue) and fresh seed numbers
function cloneScenes(p, scenes) {
  const made = [];
  for (const src of scenes) {
    const copy = structuredClone(src);
    copy.id = newId("s");
    for (const list of [copy.refs, copy.shots, copy.dialogue]) for (const x of list || []) x.id = newId(String(x.id || "x").split("_")[0] || "x");
    const n = freshSeedN({ ...p, scenes: [...p.scenes, ...made] }); // copies made so far count too
    if (n !== undefined) copy.seed_n = n;
    made.push(copy);
  }
  return made;
}

// added 2026-11-08 v0.13.1: what a duplicated scene keeps that decides what H3 gets besides its sections: shot and
// dialogue lines (with "auto shots + dialogue"), pass texts from Write prompts, hand-edited pass prompts, Raw mode.
// Editing only the copy's sections left all of these as they were, so it rendered the original scene again.
export function copyKeeps(s) {
  const out = [];
  const t = x => String(x ?? "").trim();
  const pr = s?.prompt || {};
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  if (pr.mode === "raw") { if (t(pr.raw)) out.push("its Raw prompt"); return out; }
  if (pr.auto?.shots !== false) {
    const shots = (s.shots || []).filter(x => t(x.text) || t(x.camera)).length;
    const lines = (s.dialogue || []).filter(x => t(x.text)).length;
    if (shots) out.push(plural(shots, "shot", "shots"));
    if (lines) out.push(plural(lines, "spoken line", "spoken lines"));
  }
  if ((Array.isArray(pr.passes) ? pr.passes : []).some(x => x && Object.values(x.sections || {}).some(v => t(v)))) out.push("its pass texts");
  const hand = Object.values(pr.pass_prompts || {}).filter(v => t(v)).length;
  if (hand) out.push(hand === 1 ? "a hand-edited prompt" : `${hand} hand-edited pass prompts`);
  return out;
}

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
    /* [OLD 2026-11-06 v0.9.0->v0.10.0] no way to copy text the canvas would not let you select
    if (items && items.length) { e.preventDefault(); contextMenu(root, e.clientX, e.clientY, items); return; }
    // text fields keep the browser's menu (copy, paste, spelling); elsewhere there is nothing to offer
    if (!e.target.closest("input, textarea, [contenteditable]")) e.preventDefault();
    [/OLD] */
    // added 2026-11-06 v0.10.0: Copy text. An element's own menu gets it when the element carries text to copy (a
    // spoken line, a camera phrase); elsewhere it is the menu. Text fields keep the browser's menu (copy, paste, spelling).
    if (items && items.length) {
      e.preventDefault();
      const copy = copyMenuItems(e.target, root, { explicitOnly: true });
      contextMenu(root, e.clientX, e.clientY, copy.length ? [...items, { sep: true }, ...copy] : items);
      return;
    }
    if (e.target.closest("input, textarea, [contenteditable]")) return;
    e.preventDefault();
    const copy = copyMenuItems(e.target, root);
    if (copy.length) contextMenu(root, e.clientX, e.clientY, copy, { cls: "rw-ctx-copy" });
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
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const store = createStore(normalizeProject(host.getProject()), { persist: json => host.setProject(json) });
  // added 2026-11-03 v0.6.0: teardown. Every host listener, window listener and timer is released by destroy().
  let destroyed = false;
  const offs = [];
  const on = (type, cb) => { const off = host.on(type, cb); if (typeof off === "function") offs.push(off); };
  const timeouts = new Set();
  const later = (fn, ms) => { const t = setTimeout(() => { timeouts.delete(t); if (!destroyed) fn(); }, ms); timeouts.add(t); return t; };
  // added 2026-11-03 v0.6.0: a node loaded from a workflow is mounted before its widget holds the project; takes are
  // read after load(), never for the empty mount-time project
  const initialRaw = host.getProject();
  const hasInitial = typeof initialRaw === "string" ? !!initialRaw.trim() : !!initialRaw;
  // added 2026-11-03 v0.6.0: the widget write also tells ComfyUI's ChangeTracker (host.changed), so the workflow
  // knows about keyboard-only edits and keeps the last edit on a workflow switch; /autosave answering 409
  // slug_conflict opens the folder dialog
  const store = createStore(normalizeProject(withProjectId(initialRaw)), {
    persist: json => { host.setProject(json); try { host.changed?.(); } catch (err) { console.warn("Reelwright: change notice failed", err); } },
    // [OLD 2026-11-03 v0.6.0 review] onConflict: info => { later(() => resolveConflict(info), 0); },  (a background autosave opened the dialog and focused a button while the user typed)
    // added 2026-11-03 v0.6.0 review: only a save the user asked for (Ctrl+S) opens the folder dialog; the background
    // autosave shows "Folder in use" in the footer (click it to decide) and one toast
    onConflict: (info, { explicit = false } = {}) => {
      if (explicit) later(() => resolveConflict(info), 0);
      else later(() => conflictNotice(info), 0);
    },
  });
  const root = h("div", { class: "rw-root", tabindex: "0" });
  root.__rwHost = host; // added 2026-11-02 v0.3.0: the wheel guard forwards Ctrl + wheel to the canvas
  const tabbar = h("div", { class: "rw-tabbar" });
  const body = h("div", { class: "rw-body" });
  const footer = h("div", { class: "rw-footer" });
  const toasts = h("div", { class: "rw-toasts" });
  const drawer = h("div", { class: "rw-drawer" });
  // [OLD 2026-11-03 v0.5.0->v0.5.1] root.append(tabbar, body, footer, drawer, toasts);
  // added 2026-11-03 v0.5.1: ComfyUI watches every key press on the page (a capture listener on window, which runs
  // before anything in the editor) and runs its own workflow undo on Ctrl+Z unless the focused element is a text field.
  // Its undo rebuilt the whole graph, so the editor's Ctrl+Z also undid the workflow (and with Nodes 2.0 the node
  // went blank). Keyboard focus in the editor sits on this hidden read-only field, which ComfyUI leaves alone; the
  // editor's own key handler below still sees every key.
  const keys = h("input", { class: "rw-keys", readonly: true, tabindex: "-1", "aria-hidden": "true", autocomplete: "off" });
  root.append(tabbar, body, footer, drawer, toasts, keys);
  const focusRoot = opts => keys.focus(opts || { preventScroll: true });
  root.focus = focusRoot; // every root.focus() in the editor and its tabs lands on the key field
  root.addEventListener("focusin", e => { if (e.target === root) focusRoot(); });
  // added 2026-11-03 v0.6.0: the one focus helper (ui.js): focus never falls to the page, media elements and Ctrl on
  // a button hand it to the key field
  const unguard = focusGuard(root, keys);
  // added 2026-11-03 v0.6.0: IME. While a composition runs, nothing re-renders (it would replace the field and
  // garble the text); the render waits for compositionend.
  let composing = false;
  root.addEventListener("compositionstart", () => { composing = true; });
  root.addEventListener("compositionend", () => { composing = false; schedule(); });
  root.addEventListener("focusout", () => { if (composing) { composing = false; schedule(); } });
  // a button clicked with the mouse would keep focus; give it to the key field. Capture phase: the editor's buttons
  // stop their click from bubbling. Keyboard presses (detail 0) leave focus on the button.
  root.addEventListener("click", e => {
    const a = document.activeElement;
    if (e.detail > 0 && a && a !== keys && root.contains(a) && a.matches("button, [role=switch], [role=radio], a")) focusRoot();
  }, true);
  container.replaceChildren(root);
  const tips = installTooltips(root);

  const ctx = {
    store, host, root, tips, eph: store.eph,
    get p() { return store.project; },
    get scene() { return store.project.scenes.find(s => s.id === store.project.ui.selected) || store.project.scenes[0]; },
    planFor: id => store.eph.plan?.scenes?.[id] || null,
    statusOf: id => {
      // [OLD 2026-11-03 v0.5.1->v0.6.0] if (store.eph.progress[id] && !["done", "cached", "error"].includes(store.eph.progress[id].phase)) return "rendering";
      if (store.eph.progress[id] && !FINAL.has(store.eph.progress[id].phase)) return "rendering";
      return store.eph.plan?.scenes?.[id]?.status || "unknown";
    },
    // added 2026-11-03 v0.6.0: true for progress phases after which a scene no longer renders
    isFinal: phase => FINAL.has(phase),
    // added 2026-11-03 v0.6.0: how the last run ended for a scene: {kind: "failed"|"skipped", message} or null
    sceneRunResult(id) {
      const lr = store.eph.lastRun;
      const f = lr?.failed?.find(x => x.scene_id === id);
      if (f) return { kind: "failed", message: f.error || "" };
      const k = lr?.skipped?.find(x => x.scene_id === id);
      if (k) return { kind: "skipped", message: k.reason || "" };
      const pr = store.eph.progress[id];
      if (pr?.phase === "error") return { kind: "failed", message: pr.message || "" };
      if (pr?.phase === "skipped") return { kind: "skipped", message: pr.message || "" };
      return null;
    },
    takesFor: id => store.eph.takes?.scenes?.[id] || { starred: null, takes: [] },
    starredTake(id) {
      const t = this.takesFor(id);
      return t.takes.find(x => x.id === t.starred) || null;
    },
    actions: null,
  };

  let mergeInFlight = false; // added 2026-11-02 v0.2.1
  let conflictToastFor = ""; // added 2026-11-03 v0.6.0 review: the folder conflict the last "Autosave paused" toast was for
  // added 2026-11-03 v0.6.0: the merge this editor started (job id) and whether Stop was pressed; a queue request on its
  // way (a double click queued two runs and could reset the request of the first)
  let mergeJob = null, mergeCancelRequested = false, queueing = false;
  // added 2026-11-03 v0.6.0 review: runs this editor queued, oldest first: {key, per}. key: the sorted scene ids the
  // request names (null: the backend picks them, e.g. "pending"); per: takes rendered per scene (n for "variants",
  // where render.py sends a "done" after every take).
  const queuedRuns = [];
  const runKey = ids => [...ids].map(String).sort().join("|");
  function queuedRun(req) {
    const ids = req.action === "variants" ? (req.scene_ids || req.scenes || [])
      : req.action === "selected" || req.action === "take" ? (req.scenes || [])
        : req.action === "pass_retake" ? [req.scene_id] : null;
    const per = req.action === "variants" ? Math.max(1, Math.min(8, Math.round(Number(req.n) || 2))) : 1;
    return { key: ids && ids.length ? runKey(ids) : null, per };
  }
  // the queued run a "start" event belongs to (runs start in queue order): the first that names no scenes or names
  // these targets; it and the runs queued before it (they never started) are dropped
  function takeQueuedRun(targets) {
    const key = runKey(targets || []);
    const i = queuedRuns.findIndex(x => x.key === null || x.key === key);
    return i < 0 ? null : queuedRuns.splice(0, i + 1)[i];
  }
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
    /* [OLD 2026-11-03 v0.5.1->v0.6.0] no history label; the copy kept the original's seed (stable seeds)
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
    [/OLD] */
    addScene(afterId) {
      store.update(p => {
        // [OLD 2026-11-04 v0.6.0->v0.6.1] const i = afterId ? sceneIndex(p, afterId) : p.scenes.length - 1;  (an id no longer in the project gave -1: the scene went first)
        const at = afterId ? sceneIndex(p, afterId) : -1, i = at < 0 ? p.scenes.length - 1 : at; // added 2026-11-04 v0.6.1: unknown id -> at the end
        const s = defaultScene(p, { title: "Scene " + (p.scenes.length + 1) });
        if (!Number.isInteger(s.seed_n)) { const n = freshSeedN(p); if (n !== undefined) s.seed_n = n; } // added 2026-11-03 v0.6.0
        p.scenes.splice(i + 1, 0, s);
        p.ui.selected = s.id;
      }, { label: "Add scene" });
    },
    /* [OLD 2026-11-08 v0.13.0->v0.13.1] no word on what the copy keeps: its shots, pass texts and hand-edited prompts
       still decide what H3 gets, so editing only its sections rendered the original scene again (reported by Sencer)
    // added 2026-11-03 v0.6.0: new ids and a fresh seed number for the copy
    duplicateScene(id) {
      store.update(p => {
        const i = sceneIndex(p, id);
        if (i < 0) return;
        const [copy] = cloneScenes(p, [p.scenes[i]]);
        copy.title = copy.title + " (copy)";
        p.scenes.splice(i + 1, 0, copy);
        p.ui.selected = copy.id;
      }, { label: "Duplicate scene" });
    },
    [/OLD] */
    // added 2026-11-03 v0.6.0: new ids and a fresh seed number for the copy
    // added 2026-11-08 v0.13.1: a toast names what the copy keeps that wins over its sections (copyKeeps)
    duplicateScene(id) {
      let made = null;
      store.update(p => {
        const i = sceneIndex(p, id);
        if (i < 0) return;
        const [copy] = cloneScenes(p, [p.scenes[i]]);
        copy.title = copy.title + " (copy)";
        p.scenes.splice(i + 1, 0, copy);
        p.ui.selected = copy.id;
        made = copy;
      }, { label: "Duplicate scene" });
      if (!made) return;
      const keeps = copyKeeps(made);
      actions.toast(keeps.length ? `Duplicated. The copy keeps ${keeps.join(", ")}: change ${keeps.length > 1 ? "them" : "it"} too, or it renders the same scene.` : "Duplicated.", keeps.length ? "info" : "ok");
    },
    // added 2026-11-03 v0.6.0: paste: copies of `scenes` (plain scene objects) after `afterId` (or at the end), with
    // new ids and fresh seed numbers; the first copy is selected. Returns the new ids.
    insertScenes(scenes, afterId = null, { label = "Paste scenes" } = {}) {
      let ids = [];
      if (!Array.isArray(scenes) || !scenes.length) return ids;
      store.update(p => {
        // [OLD 2026-11-04 v0.6.0->v0.6.1] const i = afterId ? sceneIndex(p, afterId) : p.scenes.length - 1;  (an id no longer in the project gave -1: the copies went first)
        const at = afterId ? sceneIndex(p, afterId) : -1, i = at < 0 ? p.scenes.length - 1 : at; // added 2026-11-04 v0.6.1: unknown id -> at the end
        const copies = cloneScenes(p, scenes);
        p.scenes.splice(i + 1, 0, ...copies);
        if (p.scenes[0]) p.scenes[0].start.mode = "fresh";
        ids = copies.map(c => c.id);
        p.ui.selected = ids[0];
      }, { label });
      return ids;
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
      // [OLD 2026-11-03 v0.5.1->v0.6.0] });
      }, { label: last ? "Reset scene" : "Delete scene" });
      return true;
    },
    // added 2026-11-02 v0.3.0: delete an asset (with confirmation) and every reference to it
    async deleteAsset(id) {
      const p = store.project;
      const a = findAsset(p, id);
      if (!a) return false;
      const uses = assetUsage(p, id).length, castUses = assetCastUse(p, id).length;
      // [OLD 2026-11-03 v0.4.3->v0.5.0] const what = [uses ? `${uses} scene reference${uses > 1 ? "s" : ""}` : "", castUses ? `${castUses} cast link${castUses > 1 ? "s" : ""}` : ""].filter(Boolean).join(" and ");
      const trackUses = p.soundtrack.filter(t => t.asset === id).length; // added 2026-11-03 v0.5.0
      const what = [uses ? `${uses} scene reference${uses > 1 ? "s" : ""}` : "", castUses ? `${castUses} cast link${castUses > 1 ? "s" : ""}` : "",
        trackUses ? `${trackUses} soundtrack track${trackUses > 1 ? "s" : ""}` : ""].filter(Boolean).join(" and ");
      if (!(await confirmDialog(root, { title: `Delete ${a.code} “${a.name || a.file}”?`, confirmLabel: "Delete asset",
        message: (what ? `It is removed from the project together with its ${what}. ` : "It is removed from the project. ") +
          "The file stays in ComfyUI's input folder. Ctrl+Z undoes this." }))) return false;
      store.update(q => {
        q.assets = q.assets.filter(x => x.id !== id);
        for (const s of q.scenes) s.refs = s.refs.filter(r => r.asset !== id);
        // [OLD 2026-11-09 v0.15.1->v0.16.0] for (const c of q.cast) { c.anchors = c.anchors.filter(x => x !== id); if (c.voice === id) c.voice = ""; for (const o of c.outfits || []) o.assets = (o.assets || []).filter(x => x !== id); }
        // added 2026-11-10 v0.18.0: a video anchor that goes with the asset takes its frame picture with it
        for (const c of q.cast) for (const va of (c.video_anchors || []).filter(x => x.asset === id)) clearAnchorFrame(q, c, va);
        for (const c of q.cast) { c.anchors = c.anchors.filter(x => x !== id); if (c.voice === id) c.voice = ""; for (const o of c.outfits || []) o.assets = (o.assets || []).filter(x => x !== id);
          c.video_anchors = (c.video_anchors || []).filter(x => x.asset !== id); } // added 2026-11-09 v0.16.0: video anchors
        // added 2026-11-10 v0.18.0: a deleted frame picture unsets its video anchor's frame; the scenes forget the
        // asset and the removed video anchors in their anchor picks
        for (const c of q.cast) for (const va of c.video_anchors || []) if (va.frame_asset === id) { va.frame_asset = ""; va.frame = null; }
        const goneVa = new Set(store.project.cast.flatMap(c => (c.video_anchors || []).filter(x => x.asset === id).map(x => x.id)));
        for (const s of q.scenes) for (const e of s.cast) if (Array.isArray(e.skip)) e.skip = e.skip.filter(x => x !== id && !goneVa.has(x));
        if (q.global.merge.score.asset === id) q.global.merge.score.asset = "";
        q.soundtrack = q.soundtrack.filter(t => t.asset !== id); // added 2026-11-03 v0.5.0
      // [OLD 2026-11-03 v0.5.1->v0.6.0] });
      }, { label: `Delete ${a.code}` });
      store.setEph({ selectedAsset: "" });
      actions.toast(`Deleted ${a.code}.`, "info");
      return true;
    },
    // added 2026-11-02 v0.3.0: Global profiles
    /* [OLD 2026-11-03 v0.5.1->v0.6.0] a profile saved before v0.5.0 brought its old score back silently
    applyProfile(prof) {
      store.update(p => { p.global = normalizeGlobal(prof.global, p); });
      store.setEph({ fresh: false, profileSel: prof.id });
      actions.toast(`Applied profile “${prof.name}”. Ctrl+Z undoes this.`, "ok");
    },
    [/OLD] */
    applyProfile(prof) {
      let moved = false;
      store.update(p => { p.global = normalizeGlobal(prof.global, p); moved = migrateScoreIn(p); }, { label: `Apply profile “${prof.name}”` });
      store.setEph({ fresh: false, profileSel: prof.id });
      actions.toast(`Applied profile “${prof.name}”. Ctrl+Z undoes this.`, "ok");
      if (moved) actions.toast("The profile's score track (from before v0.5.0) is now a looping track on the Timeline's Soundtrack lane.", "warn");
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
      // [OLD 2026-11-03 v0.5.1->v0.6.0] });
      }, { label: "Move scene" });
    },
    // added 2026-11-08 v0.13.1: put a scene at position `to` (0-based, in the order without it), e.g. a drag on the
    // timeline (Sencer: "I should be able to reorganise scenes, move/drag them left/right"). One undo step; the first
    // scene starts fresh, as with Move left / right. Returns true when the order changed.
    moveSceneTo(id, to) {
      const i = sceneIndex(store.project, id);
      const n = store.project.scenes.length;
      const j = Math.max(0, Math.min(n - 1, Math.round(Number(to) || 0)));
      if (i < 0 || i === j) return false;
      store.update(p => {
        const k = sceneIndex(p, id);
        if (k < 0) return;
        const [s] = p.scenes.splice(k, 1);
        p.scenes.splice(Math.min(j, p.scenes.length), 0, s);
        p.scenes[0].start.mode = "fresh";
        p.ui.selected = id;
      }, { label: "Move scene" });
      return true;
    },
    /* [OLD 2026-11-03 v0.5.1->v0.6.0] the second half starts from the first half's last frame, so in the cut it began one frame early and the film lost a frame
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
    [/OLD] */
    // added 2026-11-03 v0.6.0: the film keeps its length. The second half starts as last_frame: its frame 0 repeats
    // the first half's last frame, so it is one frame longer and everything in it moves by (cut - 1 frame).
    splitScene(id, at) {
      const s = store.project.scenes.find(x => x.id === id);
      const minT = 1 / FPS;
      if (!s || !(at >= minT) || at > s.duration - minT) { actions.toast("Put the playhead inside the scene to split it.", "warn"); return; }
      // the split adds a link to a chain of continuing scenes: a later scene can pass "re-anchor after" and then
      // continue from the last frame only; say so (model.effectiveStart, when model.js has it)
      const starts = () => typeof M.effectiveStart === "function"
        ? Object.fromEntries(store.project.scenes.map((x, k) => [x.id, M.effectiveStart(store.project, k)])) : {};
      const before = starts();
      store.update(p => {
        const i = sceneIndex(p, id);
        const a = p.scenes[i];
        // [OLD 2026-11-04 v0.6.0->v0.6.1] const totalF = Math.max(2, Math.round(a.duration * FPS));  (a length of exactly n + ½ frames, n even, split into n + 1 frames: the film grew by one)
        const totalF = Math.max(2, M.framesOf(a.duration)); // added 2026-11-04 v0.6.1: the frame count the model and the renderer use (halves to even)
        const cutF = Math.max(1, Math.min(totalF - 1, Math.round(at * FPS)));
        const cut = cutF / FPS, shift = (cutF - 1) / FPS;
        const r4 = v => Math.round(v * 1e4) / 1e4;
        const b = structuredClone(a);
        b.id = newId("s");
        b.title = a.title + " (2)";
        const n = freshSeedN(p);
        if (n !== undefined) b.seed_n = n;
        a.duration = cutF / FPS;
        b.duration = (totalF - cutF + 1) / FPS;
        b.start = { mode: "last_frame", overlap_frames: a.start.overlap_frames };
        b.pass_names = {}; // added 2026-11-10 v0.19.0: the second part's passes are not the first part's (names by number)
        const keepA = x => x.t < cut, keepB = x => x.t >= cut;
        b.shots = a.shots.filter(keepB).map(x => ({ ...x, id: newId("h"), t: r4(x.t - shift) }));
        b.dialogue = a.dialogue.filter(keepB).map(x => ({ ...x, id: newId("d"), t: r4(x.t - shift) }));
        a.shots = a.shots.filter(keepA);
        a.dialogue = a.dialogue.filter(keepA);
        b.refs = a.refs.filter(r => r.role !== "keyframe" || r.time >= cut).map(r => ({ ...r, id: newId("r"), time: r.role === "keyframe" ? r4(r.time - shift) : r.time }));
        a.refs = a.refs.filter(r => r.role !== "keyframe" || r.time < cut);
        p.scenes.splice(i + 1, 0, b);
        p.ui.selected = b.id;
      }, { label: "Split scene" });
      const after = starts();
      const moved = store.project.scenes.filter(x => before[x.id] && after[x.id] && before[x.id] !== after[x.id]);
      if (moved.length) actions.toast(`The chain of continuing scenes got longer: ${moved.map(x => `“${x.title}”`).join(", ")} now ${moved.length === 1 ? "starts" : "start"} ${after[moved[0].id] === "last_frame" ? "from the last frame only (re-anchored)" : "differently"}. Ctrl+Z undoes the split.`, "warn");
    },
    // [OLD 2026-11-03 v0.5.1->v0.6.0] a second click while the first request was on its way queued twice; two merges could run at once; takes of an old folder could land after a slug change
    // async run(action, scenes = []) {
    //   const request = { action, scenes, token: Date.now() };
    //   host.setProject(JSON.stringify(store.project));
    //   try {
    //     await host.queue(request);
    //     store.setEph({ running: true });
    //     actions.toast(action === "take" ? "Queued a new take." : "Render queued.", "ok");
    //   } catch (err) {
    //     actions.toast("Could not queue: " + err.message, "error");
    //   }
    // },
    // async merge() {
    //   store.setEph({ merge: { phase: "start" } });
    //   mergeInFlight = true; // added 2026-11-02 v0.2.1: the HTTP reply reports errors, so the websocket toast is skipped
    //   try {
    //     const res = await rw.merge(store.project);
    //     store.setEph({ merge: { phase: "end", files: res.files, duration: res.duration } });
    //     actions.toast("Merged " + fmtTime(res.duration || 0) + " → " + (res.files?.video || ""), "ok");
    //   } catch (err) {
    //     store.setEph({ merge: { phase: "error", error: err.message } });
    //     actions.toast("Merge failed: " + err.message, "error");
    //   } finally {
    //     mergeInFlight = false;
    //   }
    // },
    // async refreshTakes() {
    //   try { store.setEph({ takes: await rw.takes(store.project.slug) }); } catch { /* backend offline: keep last */ }
    // },
    // [/OLD]
    // added 2026-11-03 v0.6.0: `extra` goes into the request too (e.g. {scene_id, pass} for "pass_retake",
    // {scene_ids, n} for "variants"); clicks while a request is on its way are ignored. Resolves true when queued.
    async run(action, scenes = [], extra = {}) {
      if (queueing) return false;
      // added 2026-11-03 v0.6.0 review: the folder holds another project (an autosave said so): the render would be
      // refused, so the folder dialog opens first (Render is an explicit action) and the render follows once settled
      const cf = store.eph.saveState === "conflict" && store.eph.conflict;
      if (cf && cf.slug === store.project.slug) {
        queueing = true;
        let settled = false;
        try { settled = await resolveConflict(cf); } finally { queueing = false; }
        if (!settled || destroyed) return false;
      }
      queueing = true;
      const request = { action, scenes, ...extra, token: Date.now() };
      store.flush();
      host.setProject(JSON.stringify(store.project));
      // added 2026-11-03 v0.6.0 (live check): the run can start, be rejected and end before queuePrompt resolves (a
      // fast pre-flight refusal); setting "running" after the await then left the editor stuck on "waiting for
      // ComfyUI". Mark it running first and leave it alone if a run ended meanwhile.
      const lastBefore = store.eph.lastRun;
      store.setEph({ running: true, queuedAt: Date.now() });
      // added 2026-11-03 v0.6.0 review: remembered before queueing (its "start" can come before queuePrompt returns) and
      // matched to that event: a variants run renders n takes of each scene
      const qr = queuedRun(request);
      queuedRuns.push(qr);
      try {
        await host.queue(request);
        if (destroyed) return true;
        // [OLD 2026-11-03 v0.6.0 live check] store.setEph({ running: true, queuedAt: Date.now() });  (too late, see above)
        if (store.eph.lastRun !== lastBefore) return true; // already started and ended (e.g. rejected): its toast is shown
        actions.toast(action === "take" ? "Queued a new take." : action === "variants" ? "Queued the variants." : "Render queued.", "ok");
        return true;
      } catch (err) {
        const qi = queuedRuns.indexOf(qr); // added 2026-11-03 v0.6.0 review: never queued
        if (qi >= 0) queuedRuns.splice(qi, 1);
        if (!destroyed && !store.eph.run && store.eph.lastRun === lastBefore) store.setEph({ running: false }); // added 2026-11-03 v0.6.0
        actions.toast("Could not queue: " + err.message, "error");
        return false;
      } finally {
        queueing = false;
      }
    },
    // added 2026-11-03 v0.6.0: options {draft, range: [from_sid, to_sid], stems}. One merge at a time: a second click
    // only shows a toast, and the server answers 409 while another merge of the project (e.g. the automatic one after a
    // render) is running. eph.merge carries the job id, so cancelMerge() can stop it. Resolves true when merged.
    async merge(opts = {}) {
      if (mergeInFlight) { actions.toast("This project is already being merged.", "warn"); return false; }
      const job = newJob("merge");
      mergeInFlight = true;
      mergeJob = job;
      mergeCancelRequested = false;
      const kind = { draft: !!opts.draft, range: opts.range || null, stems: !!opts.stems };
      store.setEph({ merge: { phase: "start", job, ...kind } });
      try {
        const res = await rw.merge(store.project, { ...opts, job });
        if (destroyed) return false;
        if (res?.cancelled) { store.setEph({ merge: { phase: "cancelled", job, ...kind } }); actions.toast("Merge stopped.", "info"); return false; }
        store.setEph({ merge: { phase: "end", job, ...kind, files: res.files, duration: res.duration, loudness: res.loudness || null } });
        actions.toast((kind.draft ? "Draft merged " : "Merged ") + fmtTime(res.duration || 0) + " → " + (res.files?.video || ""), "ok");
        // added 2026-11-05 v0.7.0 lead review: what the merge could not do as asked (e.g. a colour reference scene with no take)
        for (const w of (Array.isArray(res.warnings) ? res.warnings : []).slice(0, 3)) actions.toast("Merge: " + w, "warn");
        return true;
      } catch (err) {
        if (destroyed) return false;
        if (mergeCancelRequested || err.data?.cancelled || err.reason === "cancelled") {
          store.setEph({ merge: { phase: "cancelled", job, ...kind } });
          actions.toast("Merge stopped.", "info");
        } else if (err.status === 409 && (err.data?.reason === "slug_conflict" || err.reason === "slug_conflict")) {
          // added 2026-11-03 v0.6.0: /merge also answers 409 when the folder holds another project; that is the
          // folder dialog, not "busy"
          store.setEph({ merge: { phase: "error", job, ...kind, error: "The project folder holds another project." } });
          later(() => resolveConflict({ slug: store.project.slug, other: err.data?.other || {} }), 0);
        } else if (err.status === 409) {
          const cur = store.eph.merge;
          // the other merge's progress events may already show it; keep that
          if (!(cur && cur.job && cur.job !== job && (cur.phase === "start" || cur.phase === "progress"))) store.setEph({ merge: { phase: "error", job, ...kind, busy: true, error: "Another merge of this project is running." } });
          actions.toast("Another merge of this project is running. Wait for it to finish, or stop it.", "warn");
        } else {
          store.setEph({ merge: { phase: "error", job, ...kind, error: err.message } });
          actions.toast("Merge failed: " + err.message, "error");
        }
        return false;
      } finally {
        mergeInFlight = false;
        mergeJob = null;
      }
    },
    // added 2026-11-03 v0.6.0: stops the running merge of this project (this editor's, or the one eph.merge shows)
    async cancelMerge() {
      const cur = store.eph.merge;
      const job = mergeJob || ((cur?.phase === "start" || cur?.phase === "progress") ? cur.job : null);
      if (!job) return false;
      mergeCancelRequested = true;
      try { await rw.mergeCancel(job); return true; }
      catch (err) { actions.toast("Could not stop the merge: " + err.message, "error"); return false; }
    },
    // added 2026-11-03 v0.6.0: the takes of the current folder; an answer for a folder that is no longer the
    // project's is dropped
    async refreshTakes() {
      const slug = store.project.slug;
      try {
        const takes = await rw.takes(slug);
        if (destroyed || slug !== store.project.slug) return;
        store.setEph({ takes, takesSlug: slug });
      } catch { /* backend offline: keep last */ }
    },
    async refreshModels() {
      try { store.setEph({ models: await rw.models() }); } catch { store.setEph({ models: null }); }
    },
    async refreshInfo() {
      try { store.setEph({ info: await rw.info() }); } catch { store.setEph({ info: null }); }
    },
    /* [OLD 2026-11-03 v0.5.1->v0.6.0] its timer outlived the editor
    toast(message, kind = "info") {
      const t = { id: Math.random(), message, kind };
      store.setEph({ toasts: [...store.eph.toasts, t] });
      setTimeout(() => store.setEph({ toasts: store.eph.toasts.filter(x => x !== t) }), kind === "error" ? 7000 : 3500);
    },
    [/OLD] */
    toast(message, kind = "info") {
      if (destroyed) return;
      const t = { id: Math.random(), message, kind };
      store.setEph({ toasts: [...store.eph.toasts, t] });
      later(() => store.setEph({ toasts: store.eph.toasts.filter(x => x !== t) }), kind === "error" ? 7000 : 3500);
    },
    // added 2026-11-03 v0.6.0: Ctrl+S. Writes the widget, waits for the autosave and says whether it worked.
    async saveNow() {
      const r = await store.saveNow();
      if (destroyed) return r;
      if (r.ok) actions.toast(`Saved · output/reelwright/${store.project.slug}/project.json`, "ok");
      else if (!r.conflict) actions.toast(`Not saved to disk: ${r.error}. The workflow still holds your edits.`, "error");
      return r; // a folder conflict opens its dialog (onConflict)
    },
    // added 2026-11-03 v0.6.0: the named undo history as a menu under `anchor` (the History button)
    showHistory(anchor) {
      const steps = store.history();
      const applied = steps.filter(x => x.done).length;
      const time = at => new Date(at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      const items = [{ head: steps.length ? `History · ${applied} of ${steps.length} step${steps.length === 1 ? "" : "s"} applied` : "History" }];
      if (!steps.length) items.push({ label: "No edits yet", disabled: true, help: "app.history" });
      for (const x of steps.slice().reverse()) {
        items.push({ label: x.label, hint: time(x.at), icon: x.k === applied - 1 ? "check" : null, help: "app.history.item",
          cls: x.k === applied - 1 ? "current" : x.done ? "" : "future", onClick: () => store.jumpTo(x.k) });
      }
      if (steps.length) items.push({ sep: true }, { label: "Before these edits", icon: applied === 0 ? "check" : null, cls: applied === 0 ? "current" : "", help: "app.history.start", onClick: () => store.jumpTo(-1) });
      const r = (anchor || root).getBoundingClientRect();
      contextMenu(root, r.left, r.bottom + 4, items, { cls: "rw-history" });
    },
    // added 2026-11-03 v0.6.0: the folder dialog again (footer "Folder in use")
    resolveConflict: () => resolveConflict(store.eph.conflict),
    toggleIssues(open) {
      store.setEph({ issuesOpen: open ?? !store.eph.issuesOpen });
    },
    gotoIssue(issue) {
      if (issue.scene_id) actions.select(issue.scene_id, "scene");
      actions.toggleIssues(false);
    },
  };
  root.__rwToast = (message, kind) => actions.toast(message, kind); // added 2026-11-06 v0.10.0: ui.js copyWithToast

  // added 2026-11-03 v0.6.0: allIssues() runs sceneBudget for every scene; remember it per project version and plan
  let issuesMemo = { v: -1, plan: null, list: [] };
  function allIssues() {
    const p = store.project;
    const v = typeof p.__rwv === "number" ? p.__rwv : -1;
    if (v >= 0 && issuesMemo.v === v && issuesMemo.plan === store.eph.plan) return issuesMemo.list;
    const list = [...(store.eph.plan?.issues || [])];
    for (const s of p.scenes) {
      for (const msg of budgetIssues(sceneBudget(p, s))) list.push({ level: "warn", scene_id: s.id, message: `${s.title}: ${msg}` });
      for (const i of store.eph.plan?.scenes?.[s.id]?.issues || []) list.push({ scene_id: s.id, ...i });
    }
    const seen = new Set();
    // [OLD 2026-11-03 v0.6.0 review] return list.filter(...)  (now memoised)
    const out = list.filter(i => { const k = i.level + i.scene_id + i.message; if (seen.has(k)) return false; seen.add(k); return true; });
    issuesMemo = { v, plan: store.eph.plan, list: out };
    return out;
  }
  ctx.allIssues = allIssues;

  function pendingCount() {
    const plan = store.eph.plan?.scenes;
    if (!plan) return null;
    return store.project.scenes.filter(s => PENDING.has(plan[s.id]?.status)).length;
  }
  ctx.pendingCount = pendingCount;

  // added 2026-11-08 v0.13.0: a tab with a `when` shows only while it holds (Chat: an LLM is set); the tab shown when the
  // project's tab is hidden is the Timeline
  const tabShown = id => !!TABS[id] && (!TABS[id].when || TABS[id].when(ctx));
  const currentTabId = () => (tabShown(store.project.ui.tab) ? store.project.ui.tab : "timeline");
  ctx.tabShown = tabShown;
  function renderTabbar() {
    const p = store.project;
    // [OLD 2026-11-08 v0.12.0->v0.13.0] const active = p.ui.tab;
    const active = currentTabId();
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
      // [OLD 2026-11-08 v0.12.0->v0.13.0] ...Object.entries(TABS).map(([id, t]) => h("button", {
      ...Object.entries(TABS).filter(([id]) => tabShown(id)).map(([id, t]) => h("button", {
        type: "button", class: ["rw-tab", id === active && "on"], help: "tab." + id,
        onClick: () => actions.setTab(id),
      }, icon(t.icon, 15), t.label, counts[id] !== undefined && counts[id] !== "" && h("span", { class: ["rw-tab-count mono", id === "render" && pend ? "warn" : id === "scene" && "accent"] }, counts[id]))),
      h("span", { class: "rw-flex" }),
      h("span", { class: ["rw-backend", store.eph.backend], help: "app.backend" }, h("span", { class: "rw-led" }), store.eph.backend === "online" ? "backend" : store.eph.backend),
      button({ icon: "undo", help: "app.undo", onClick: () => store.undo(), disabled: !store.canUndo(), variant: "ghost" }),
      button({ icon: "redo", help: "app.redo", onClick: () => store.redo(), disabled: !store.canRedo(), variant: "ghost" }),
      // added 2026-11-03 v0.6.0: named undo history; click a step to go back (or forward) to it
      button({ icon: "history", help: "app.history", variant: "ghost", disabled: !store.canUndo() && !store.canRedo(), onClick: e => actions.showHistory(e.currentTarget) }),
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

  // added 2026-11-06 v0.10.2: the percentage of a running merge, as the Render tab's buttons and the footer show it
  function mergePct(d) { return d?.percent ? Math.round(d.percent) + "%" : ""; }
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
    // [OLD 2026-11-03 v0.5.1->v0.6.0] const running = Object.values(store.eph.progress).find(x => !["done", "cached", "error"].includes(x.phase));
    const running = Object.values(store.eph.progress).find(x => !FINAL.has(x.phase));
    footer.replaceChildren(
      h("span", { class: "rw-foot-item", help: "footer.issues" },
        h("span", { class: ["rw-led", issues.some(i => i.level === "error") ? "error" : issues.length ? "warn" : "ok"] }),
        issues.length ? issues[0].message : "All scenes within H3 limits"),
      h("span", { class: "rw-foot-sep" }),
      // [OLD 2026-11-10 v0.18.0->v0.19.0] h("span", { class: "rw-foot-item mono", help: "footer.output" }, `${g.output.width}×${g.output.height} · 24 fps · 32 kHz stereo · ${g.quality}`),
      h("span", { class: "rw-foot-item mono", help: "footer.output" }, `${g.output.width}×${g.output.height}${hiresLabel(g)} · 24 fps · 32 kHz stereo · ${g.quality}`), // v0.19.0: → the Hires size
      h("span", { class: "rw-foot-sep" }),
      h("span", { class: "rw-foot-item", help: "footer.status" }, store.eph.plan
        ? `On disk ${st.cached} · Stale ${st.stale} · Pending ${st.pending}` : "Render status unavailable"),
      running ? h("span", { class: "rw-foot-item rw-c-pic", help: "footer.running" },
        `Rendering ${p.scenes.find(s => s.id === running.scene_id)?.title || ""} · pass ${running.pass}/${running.passes} · ${running.phase} ${running.step ? running.step + "/" + running.steps : ""}`) : "",
      // added 2026-11-06 v0.10.2: a merge is running (one started here or elsewhere, or the one after a render)
      ["start", "progress"].includes(store.eph.merge?.phase) ? h("span", { class: "rw-foot-item rw-c-accent", help: "footer.merging" },
        icon("merge", 12), " Merging ", h("span", { class: "rw-merge-pct mono" }, mergePct(store.eph.merge))) : "",
      h("span", { class: "rw-flex" }),
      h("span", { class: "rw-foot-item mono", help: "footer.length" }, `${p.scenes.length} scenes · ${fmtTime(total)} · cut ${fmtTime(assembledDuration(p))}`),
      h("span", { class: "rw-foot-sep" }),
      // [OLD 2026-11-03 v0.5.1->v0.6.0] h("span", { class: ["rw-foot-item", "save-" + store.eph.saveState], help: "footer.save" }, store.eph.saveState === "saved" ? "Saved" : store.eph.saveState === "pending" ? "Saving…" : "Autosave offline"),
      // added 2026-11-03 v0.6.0: a folder that holds another project pauses autosaving until the user decides
      store.eph.saveState === "conflict"
        ? h("button", { type: "button", class: "rw-foot-item rw-foot-btn save-conflict", help: "footer.saveConflict", onClick: () => actions.resolveConflict() }, icon("warn", 12), "Folder in use")
        : h("span", { class: ["rw-foot-item", "save-" + store.eph.saveState], help: "footer.save", title: store.eph.saveState === "offline" && store.eph.saveError ? store.eph.saveError : null },
          store.eph.saveState === "saved" ? "Saved" : store.eph.saveState === "pending" ? "Saving…" : "Autosave offline"),
    );
  }

  function renderDrawer() {
    drawer.classList.toggle("on", !!store.eph.issuesOpen);
    if (!store.eph.issuesOpen) { drawer.replaceChildren(); return; }
    const issues = allIssues();
    // added 2026-11-03 v0.4.3: one click for every scene whose shots or lines start after its end
    const overrun = store.project.scenes.filter(s => overruns(s));
    drawer.replaceChildren(
      h("div", { class: "rw-drawer-head" }, h("b", null, "Issues"), h("span", { class: "rw-dim" }, `${issues.length}`),
        h("button", { type: "button", class: "rw-q", dataset: { more: "app.issues" }, help: "app.issues", "aria-label": "Help" }, "?"),
        h("span", { class: "rw-flex" }),
        // added 2026-11-06 v0.10.0: every issue as text, one per line (with its scene)
        issues.length ? copyButton({ label: "Copy all", help: "app.issues.copy", key: "issues-copy", what: "issues",
          text: () => allIssues().map(i => `[${i.level}] ${i.message}`).join("\n") }) : null,
        button({ icon: "close", help: "common.close", variant: "ghost", onClick: () => actions.toggleIssues(false) })),
      overrun.length ? h("div", { class: "rw-drawer-fix" },
        h("span", { class: "small grow" }, `${overrun.length} scene${overrun.length === 1 ? " has" : "s have"} shots or lines after the end.`),
        button({ label: `Lengthen ${overrun.length === 1 ? "it" : "them"} to fit`, small: true, help: "app.issues.fitShots", onClick: () => {
          const ids = new Set(overrun.map(s => s.id));
          actions.edit(p => { for (const s of p.scenes) if (ids.has(s.id)) lengthenToFit(s); });
          actions.toast(`Lengthened ${ids.size} scene${ids.size === 1 ? "" : "s"} to fit their shots. Ctrl+Z undoes it.`, "ok");
          root.focus?.({ preventScroll: true });
        } })) : null,
      /* [OLD 2026-11-06 v0.9.0->v0.10.0] no copy text on an issue
      issues.length ? h("div", { class: "rw-issue-list", dataset: { scroll: "issues" } }, issues.map(i => h("button", {
        type: "button", class: ["rw-issue", i.level], help: "app.issueItem", onClick: () => actions.gotoIssue(i),
      }, icon(i.level === "info" ? "info" : "warn", 13), h("span", null, i.message)))) : h("div", { class: "rw-empty" }, "No issues. Every scene fits H3's limits."));
      [/OLD] */
      // added 2026-11-06 v0.10.0: right-click an issue for Copy text (data-copy)
      issues.length ? h("div", { class: "rw-issue-list", dataset: { scroll: "issues" } }, issues.map(i => h("button", {
        type: "button", class: ["rw-issue", i.level], help: "app.issueItem", onClick: () => actions.gotoIssue(i), dataset: { copy: i.message },
      }, icon(i.level === "info" ? "info" : "warn", 13), h("span", null, i.message)))) : h("div", { class: "rw-empty" }, "No issues. Every scene fits H3's limits."));
  }

  function renderToasts() {
    toasts.replaceChildren(...store.eph.toasts.map(t => h("div", { class: ["rw-toast", t.kind] }, t.message)));
  }

  // added 2026-11-03 v0.6.0 review: unsaved typing. Most text fields store their value on change (Enter, Tab, leaving
  // the field). Rebuilding such a field while it holds typed text lost edits: Chrome commits a focused field it
  // removes (a "-" typed into a number field reads as "" and was put back), the copy lost a select-all of a number
  // field (no selection API there), and the copy got the typed text before focus, so Enter fired no change. While a
  // field is being edited the tab body is not rebuilt (the tab bar, footer, issues and toasts still are); it is
  // rebuilt after the change, Enter or leaving the field. Editing starts with a key or input in the field. A click or
  // focus into one keeps the body for HOLD_TOUCH_MS too, unless the project itself changed (an edit is shown at once).
  // Fields that store as they are typed (onInput, ui.js __rwLive), comboboxes and prompt editors are not held.
  const HOLD_TOUCH_MS = 1200;
  let hold = null; // {el, typed, until}
  let heldRender = false, holdTimer = 0, restoringFocus = false;
  let bodyTab = null, bodyVersion = -1; // the tab and project version the body was last built for
  const holdable = el => el instanceof Element && body.contains(el) && isTextField(el) && el.tagName !== "SELECT" && !el.isContentEditable
    && !el.__rwLive && !el.matches(".rw-combo-input, .rw-code-ta");
  const touchHold = el => { if (!(hold?.el === el && hold.typed)) hold = { el, typed: false, until: performance.now() + HOLD_TOUCH_MS }; };
  function releaseHold(el) {
    if (!hold || (el && hold.el !== el)) return;
    hold = null;
    if (heldRender) { heldRender = false; schedule(); }
  }
  // true while the focused field's editing keeps the body: always after typing; after a click or focus only for
  // HOLD_TOUCH_MS and only for renders without a project change (an edit elsewhere is shown at once)
  function holdActive() {
    if (!hold) return false;
    if (document.activeElement !== hold.el || !hold.el.isConnected) { hold = null; return false; }
    if (hold.typed) return true;
    const left = hold.until - performance.now();
    const v = typeof store.project.__rwv === "number" ? store.project.__rwv : -2;
    if (left <= 0 || v !== bodyVersion) return false;
    if (!holdTimer) holdTimer = later(() => { holdTimer = 0; if (heldRender) { heldRender = false; schedule(); } }, left + 20);
    return true;
  }
  // The whole text of a field is selected (Tab into it, select(), Ctrl+A): a rebuilt copy gets it selected too. A
  // number field has no selection API, so this is the only way to know (typing replaced the selection before; after
  // a rebuild it was added to the old value: Tab into the height, type 512 -> 768512).
  let tabAt = -1e9;
  const MODIFIER = new Set(["Control", "Shift", "Alt", "Meta"]);
  root.addEventListener("focusin", e => {
    if (!restoringFocus && holdable(e.target)) {
      touchHold(e.target);
      e.target.__rwSelAll = performance.now() - tabAt < 250; // keyboard focus selects the text
    }
  });
  root.addEventListener("select", e => {
    const t = e.target;
    if (!holdable(t)) return;
    t.__rwSelAll = typeof t.selectionStart === "number" ? t.selectionStart === 0 && t.selectionEnd === t.value.length : true;
    touchHold(t);
  }, true);
  root.addEventListener("pointerdown", e => { if (holdable(e.target)) { e.target.__rwSelAll = false; touchHold(e.target); } }, true);
  root.addEventListener("keydown", e => {
    const t = e.target;
    if (e.key === "Tab") tabAt = performance.now();
    if (e.isComposing || !holdable(t)) return;
    if (e.key === "Enter" && t.tagName === "INPUT") { releaseHold(t); return; } // the change (if any) follows
    if (e.key === "Tab" || e.key === "Escape" || MODIFIER.has(e.key)) return;
    t.__rwSelAll = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a";
    hold = { el: t, typed: true, until: 0 };
  }, true);
  root.addEventListener("input", e => { if (holdable(e.target)) { e.target.__rwSelAll = false; hold = { el: e.target, typed: true, until: 0 }; } }, true);
  root.addEventListener("change", e => releaseHold(e.target), true);
  // leaving the field ends the hold; the window losing focus (another app) does not: the field keeps its typing
  root.addEventListener("focusout", e => { const t = e.target; setTimeout(() => { if (document.activeElement !== t) releaseHold(t); }, 0); }, true);
  // The text field typed in since its last change, Enter or leaving it (any text field, held or live): its rebuilt
  // copy gets the typed text (a live field may store it later, e.g. a filter that waits 300 ms); any other rebuilt
  // field shows the stored value (a commit that rounded 1000 to 992 showed 1000).
  let typedIn = null;
  root.addEventListener("input", e => { if (isTextField(e.target)) typedIn = e.target; }, true);
  root.addEventListener("change", e => { if (typedIn === e.target) typedIn = null; }, true);
  root.addEventListener("keydown", e => { if (e.key === "Enter" && !e.isComposing && e.target === typedIn && e.target.tagName === "INPUT") typedIn = null; }, true);
  root.addEventListener("focusout", e => { const t = e.target; setTimeout(() => { if (typedIn === t && document.activeElement !== t) typedIn = null; }, 0); }, true);

  // added 2026-11-09 v0.17.3: the pictures and videos of the old body that the new one shows again (same tag, address and
  // class) replace their new copies, with the new copy's attributes. Not an element with handlers (h() __rwOn) or one
  // ui.kept() manages; a playing video moved within the same task keeps playing.
  function adoptMedia(old, fresh) {
    const id = el => el.tagName + "|" + (el.getAttribute("src") || "") + "|" + (el.getAttribute("class") || "");
    const free = el => !el.__rwOn && !el.__rwKept && !!el.getAttribute("src");
    const pool = new Map();
    for (const el of old.querySelectorAll("img, video")) {
      if (!free(el)) continue;
      const k = id(el);
      if (!pool.has(k)) pool.set(k, []);
      pool.get(k).push(el);
    }
    if (!pool.size) return;
    for (const el of fresh.querySelectorAll("img, video")) {
      if (!free(el)) continue;
      const prev = pool.get(id(el))?.shift();
      if (!prev) continue;
      for (const { name } of [...prev.attributes]) if (!el.hasAttribute(name)) prev.removeAttribute(name);
      for (const { name, value } of [...el.attributes]) if (prev.getAttribute(name) !== value) prev.setAttribute(name, value);
      el.replaceWith(prev);
    }
  }

  // added 2026-11-10 v0.18.0 (Sencer: "when any change is made, the card texts in scene tab are refreshed, but they also lose
  // scroll position. keep the position as accurate as possible"): a box scrolled away from its top or left that has no
  // data-scroll key (What H3 receives, a list) is found again in the new body by its key, else by its kind (tag, class,
  // help id) and its place among the boxes of that kind, and gets the same offset back
  function scrollSig(el) {
    return el.dataset.key ? "k:" + el.dataset.key : el.tagName + "." + (el.getAttribute("class") || "") + "|" + (el.dataset.help || "");
  }
  function scrollMarks(rootEl) {
    const marks = [], seen = new Map();
    const all = rootEl.querySelectorAll("*");
    let any = false; // most renders have nothing scrolled: no signatures then
    for (const el of all) if ((el.scrollTop > 0 || el.scrollLeft > 0) && !el.dataset.scroll) { any = true; break; }
    if (!any) return marks;
    for (const el of all) {
      if (el.dataset.scroll) continue;
      const sig = scrollSig(el);
      const nth = seen.get(sig) || 0;
      seen.set(sig, nth + 1);
      if (el.scrollTop > 0 || el.scrollLeft > 0) marks.push({ sig, nth, top: el.scrollTop, left: el.scrollLeft });
    }
    return marks;
  }
  function restoreScrollMarks(rootEl, marks) {
    if (!marks.length) return;
    const want = new Map(marks.map(m => [m.sig + "#" + m.nth, m]));
    const seen = new Map();
    for (const el of rootEl.querySelectorAll("*")) {
      if (el.dataset.scroll) continue;
      const sig = scrollSig(el);
      const nth = seen.get(sig) || 0;
      seen.set(sig, nth + 1);
      const m = want.get(sig + "#" + nth);
      if (m) { el.scrollTop = m.top; el.scrollLeft = m.left; }
    }
  }

  let frame = 0;
  // added 2026-11-03 v0.6.0: one render per animation frame; nothing after destroy()
  function schedule() { if (!frame && !destroyed) frame = requestAnimationFrame(render); }
  function render() {
    frame = 0;
    if (destroyed) return; // added 2026-11-03 v0.6.0
    // added 2026-11-02 v0.2.0: an open combobox list lives in the root; re-rendering under it would
    // orphan the list, so wait until it closes
    // [OLD 2026-11-03 v0.5.1->v0.6.0] if (comboState.open) { comboState.onClose = () => { if (!frame) frame = requestAnimationFrame(render); }; return; }  (one slot shared by every editor)
    if (root.__rwCombo > 0) { root.__rwComboClosed = schedule; return; }
    if (composing) return; // added 2026-11-03 v0.6.0: IME; compositionend renders
    // added 2026-11-03 v0.6.0 review: a field with unsaved typing keeps the tab body (see `hold` above)
    if (store.project.ui.tab === bodyTab && holdActive()) {
      heldRender = true;
      renderTabbar();
      renderFooter();
      renderDrawer();
      renderToasts();
      return;
    }
    heldRender = false;
    // the field being edited (if any) before this render: unsaved typing (bugs: focus jump, stale text); a click hold
    // is carried to the field's copy (removing the field fires focusout, which ends the hold)
    const pending = !!document.activeElement && (typedIn === document.activeElement || (!!hold?.typed && hold.el === document.activeElement));
    const carry = hold && !hold.typed && hold.el === document.activeElement ? hold : null;
    const scroll = {};
    root.querySelectorAll("[data-scroll]").forEach(el => { scroll[el.dataset.scroll] = [el.scrollLeft, el.scrollTop]; });
    const scrolledAway = scrollMarks(body); // added 2026-11-10 v0.18.0: every other scrolled box of the tab
    // [OLD 2026-11-03 v0.5.0->v0.5.1] const focused = root.querySelector(":focus");
    const focused = root.querySelector(":focus:not(.rw-keys)"); // the key field survives every render
    // added 2026-11-03 v0.5.1: focus was in the editor before this render (see the end of render)
    const hadFocus = root.contains(document.activeElement);
    const focusKey = focused?.dataset?.key;
    const sel = focused && typeof focused.selectionStart === "number" ? [focused.selectionStart, focused.selectionEnd] : null;
    // added 2026-11-03 v0.4.1: a text field being typed in keeps what is typed. Most fields store their value on
    // change (Enter or leaving the field), so a re-render in between (progress, plan refresh, autosave status) rebuilt
    // the field with the stored value and the caret landed in the wrong place: "Sencer" came out as "Seernc".
    const textField = !!focused?.matches?.("input:not([type=checkbox]):not([type=radio]):not([type=range]), textarea");
    const typing = textField ? focused.value : null;
    // a field without a key is found again by its help id and position (it used to lose focus)
    // added 2026-11-03 v0.6.0: keys are the reliable way (ui.js `key` prop -> data-key, unique in the editor, e.g.
    // `shot-t-${shot.id}`); without one, a field holding the same text wins over the same position (an edit can
    // re-sort rows)
    const helpId = textField && !focusKey ? focused.dataset.help : null;
    const helpPos = helpId ? [...root.querySelectorAll(`${focused.tagName}[data-help="${CSS.escape(helpId)}"]`)].indexOf(focused) : -1;

    renderTabbar();
    // [OLD 2026-11-08 v0.12.0->v0.13.0] const tab = TABS[store.project.ui.tab] || TABS.timeline;
    const tab = TABS[currentTabId()]; // added 2026-11-08 v0.13.0: a hidden tab shows the Timeline
    // [OLD 2026-11-09 v0.14.0->v0.14.1] body.replaceChildren(tab.mod.render(ctx));
    // [OLD 2026-11-09 v0.17.2->v0.17.3] body.replaceChildren(foldScope(ctx, () => tab.mod.render(ctx))); // added 2026-11-09 v0.14.1: every card folds
    // added 2026-11-09 v0.17.3 (Sencer: "the screen flickers whenever I change a setting or type anything. can we prevent the
    // flickering (something like doublebuffering?)"): the new body is built aside and swapped in at once, as before; a
    // picture or video it shows again is the one already on screen (moved over, not loaded and decoded again), so it
    // does not go blank for a frame
    const fresh = foldScope(ctx, () => tab.mod.render(ctx)); // every card folds (v0.14.1)
    adoptMedia(body, fresh);
    body.replaceChildren(fresh);
    bodyTab = store.project.ui.tab; // added 2026-11-03 v0.6.0 review
    bodyVersion = typeof store.project.__rwv === "number" ? store.project.__rwv : -2; // added 2026-11-03 v0.6.0 review
    renderFooter();
    renderDrawer();
    renderToasts();

    root.querySelectorAll("[data-scroll]").forEach(el => {
      const s = scroll[el.dataset.scroll];
      if (s) { el.scrollLeft = s[0]; el.scrollTop = s[1]; }
    });
    restoreScrollMarks(body, scrolledAway); // added 2026-11-10 v0.18.0
    // [OLD 2026-11-03 v0.4.0->v0.4.1] if (focusKey) {
    // [OLD 2026-11-03 v0.4.0->v0.4.1]   const el = root.querySelector(`[data-key="${CSS.escape(focusKey)}"]`);
    if (focusKey || helpPos >= 0) {
      /* [OLD 2026-11-03 v0.5.1->v0.6.0] by position only: after a re-sort the caret jumped to another row
      const el = focusKey ? root.querySelector(`[data-key="${CSS.escape(focusKey)}"]`)
        : root.querySelectorAll(`${focused.tagName}[data-help="${CSS.escape(helpId)}"]`)[helpPos];
      [/OLD] */
      /* [OLD 2026-11-03 v0.6.0 review] "same text wins" also while typing: the copy of the field being typed in still
         held the stored value, so another field whose stored value equals the typed text took the focus (height typed
         as 1344 jumped to the width, 1344)
      const byHelp = () => {
        const list = [...root.querySelectorAll(`${focused.tagName}[data-help="${CSS.escape(helpId)}"]`)];
        const same = list.filter(x => x.value === typing);
        return same.length === 1 ? same[0] : list[helpPos];
      };
      [/OLD] */
      // added 2026-11-03 v0.6.0 review: the same text identifies the field only when it held no unsaved typing (its
      // text is then the stored value)
      const byHelp = () => {
        const list = [...root.querySelectorAll(`${focused.tagName}[data-help="${CSS.escape(helpId)}"]`)];
        const same = pending ? [] : list.filter(x => x.value === typing);
        return same.length === 1 ? same[0] : list[helpPos];
      };
      const el = focusKey ? root.querySelector(`[data-key="${CSS.escape(focusKey)}"]`) : byHelp();
      if (el && el !== focused) {
        /* [OLD 2026-11-02 v0.1.0->v0.2.0] re-focusing a combobox would reopen its list
        el.focus({ preventScroll: true });
        [/OLD] */
        // [OLD 2026-11-03 v0.6.0 review] if (typing !== null && "value" in el && el.value !== typing) el.value = typing; // added 2026-11-03 v0.4.1  (also after a commit: 1000 stored as 992 kept showing 1000)
        // added 2026-11-03 v0.6.0 review: the typed text only when it was not stored yet; otherwise the stored value shows
        if (pending && typing !== null && "value" in el && el.value !== typing) el.value = typing;
        if (pending) typedIn = el; // the copy holds the unsaved typing now (removing the old field may have cleared it)
        comboState.restoring = true;
        restoringFocus = true; // added 2026-11-03 v0.6.0 review: not a click or focus by the user (no new hold)
        // [OLD 2026-11-03 v0.6.0 review] try { el.focus({ preventScroll: true }); } finally { comboState.restoring = false; }
        try { el.focus({ preventScroll: true }); } finally { comboState.restoring = false; restoringFocus = false; } // added 2026-11-03 v0.6.0 review: restoringFocus
        // added 2026-11-03 v0.6.0 review: a click hold on the old field moves to its copy
        if (carry && carry.el === focused) hold = { ...carry, el };
        // [OLD 2026-11-03 v0.6.0 review] if (sel && typeof el.setSelectionRange === "function") { try { el.setSelectionRange(sel[0], sel[1]); } catch { /* not a text field */ } }
        // added 2026-11-03 v0.6.0 review: a number field's selected text is selected again (see __rwSelAll)
        if (sel && typeof el.setSelectionRange === "function") { try { el.setSelectionRange(sel[0], sel[1]); } catch { /* not a text field */ } }
        else if (focused.__rwSelAll && typeof el.select === "function") { el.select(); el.__rwSelAll = true; }
      }
    } else if (focused === root || !root.contains(document.activeElement)) {
      /* keep focus where it was */
    }
    // added 2026-11-03 v0.5.1: the button that was clicked (Add scene, a tab, a toggle) is rebuilt by the render, so
    // focus fell to the page body. The next Ctrl+Z then went to ComfyUI, which undid the workflow instead of the
    // edit: it rebuilt the node and, with Nodes 2.0 on, the editor went blank. Focus stays in the editor now.
    if (hadFocus && !root.contains(document.activeElement)) root.focus({ preventScroll: true });
    tab.mod.afterRender?.(ctx);
  }
  ctx.render = render;
  // [OLD 2026-11-03 v0.5.1->v0.6.0] store.subscribe(() => { if (!frame) frame = requestAnimationFrame(render); });
  // added 2026-11-03 v0.6.0: takes are read again whenever the project's folder (slug) changes: a load, an edit of
  // the Folder field, undo, a duplicated node, the folder-conflict dialog. Never for the mount-time project.
  let lastSlug = store.project.slug;
  function takesSoon() { clearTimeout(takesSoon.t); timeouts.delete(takesSoon.t); takesSoon.t = later(() => actions.refreshTakes(), 120); }
  store.subscribe(() => {
    if (destroyed) return;
    if (store.eph.saveState !== "conflict") conflictToastFor = ""; // added 2026-11-03 v0.6.0 review: one toast per conflict
    if (store.project.slug !== lastSlug) {
      lastSlug = store.project.slug;
      store.eph.takes = null; // the old folder's takes are not this folder's
      store.eph.takesSlug = null;
      takesSoon();
    }
    schedule();
  });

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
    if (e.isComposing || composing) return; // added 2026-11-03 v0.6.0: keys that belong to an IME composition
    // [OLD 2026-11-03 v0.5.0->v0.5.1] const typing = e.target.matches?.("input, textarea, select, [contenteditable]");
    // [OLD 2026-11-03 v0.5.1->v0.6.0] const typing = e.target !== keys && e.target.matches?.("input, textarea, select, [contenteditable]"); // the key field is not typing
    // added 2026-11-03 v0.6.0: Ctrl+Z on a checkbox or slider (no browser undo there) is the editor's undo
    const field = e.target !== keys && !!e.target.matches?.("input, textarea, select, [contenteditable]"); // the key field is not typing
    const typing = field && isTextField(e.target);
    const mod = e.ctrlKey || e.metaKey;
    // [OLD 2026-11-03 v0.5.1->v0.6.0] if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); store.saveNow(); actions.toast("Saved.", "ok"); return; }
    if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); actions.saveNow(); return; } // says "Saved" only once the disk has it
    if (typing) return;
    if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); if (e.shiftKey) store.redo(); else store.undo(); return; }
    if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); store.redo(); return; }
    if (field) return; // added 2026-11-03 v0.6.0: a slider's arrows move the slider
    // added 2026-11-04 v0.6.1: Ctrl/Cmd/Alt combinations other than the editor's own (Ctrl+S, Ctrl+Z, Ctrl+Shift+Z,
    // Ctrl+Y above) belong to the browser and ComfyUI: none of them reaches the single-key shortcuts (Ctrl+D no longer
    // duplicates a scene, Cmd+← and Alt+← go back again, Ctrl+J opens the downloads)
    if (!plainKey(e)) return;
    if (e.key === "?") { e.preventDefault(); tips.openPopover("tab." + store.project.ui.tab, root.querySelector(".rw-tab.on") || root); return; }
    // [OLD 2026-11-08 v0.12.0->v0.13.0] const tab = TABS[store.project.ui.tab];
    const tab = TABS[currentTabId()]; // added 2026-11-08 v0.13.0
    if (tab.mod.onKey?.(ctx, e)) { e.preventDefault(); return; }
    if (timeline.sceneKeys(ctx, e)) e.preventDefault();
  });
  for (const ev of ["keyup", "keypress", "wheel", "copy", "paste", "cut"]) root.addEventListener(ev, e => e.stopPropagation());

  // added 2026-11-02 v0.3.0: progress of the whole run (scene k of n) for the Render tab and the node title
  function runProgress() {
    const run = store.eph.run;
    if (!run || !run.targets?.length) return null;
    const n = run.targets.length;
    // [OLD 2026-11-03 v0.5.1->v0.6.0] const cur = Object.values(store.eph.progress).find(x => run.targets.includes(x.scene_id) && !["done", "cached", "error"].includes(x.phase));
    const cur = Object.values(store.eph.progress).find(x => run.targets.includes(x.scene_id) && !FINAL.has(x.phase));
    let part = 0;
    if (cur) {
      const passes = Math.max(1, cur.passes || 1);
      // [OLD 2026-11-10 v0.18.0->v0.19.0] const within = cur.phase === "sample" && cur.steps ? cur.step / cur.steps : ["decode", "save"].includes(cur.phase) ? 1 : 0;
      const within = cur.phase === "sample" && cur.steps ? cur.step / cur.steps : ["decode", "save", "upscale", "refine"].includes(cur.phase) ? 1 : 0; // v0.19.0: Hires
      part = Math.min(1, ((Math.max(1, cur.pass || 1) - 1) + within) / passes);
    }
    /* [OLD 2026-11-03 v0.6.0 review] a scene counted once: a variants run read 100 % after its first take
    const done = run.done.length;
    return { n, done, index: Math.min(n, done + (cur ? 1 : 0)), current: cur || null, scenePart: part, total: Math.min(1, (done + part) / n), reused: run.reused || [] };
    [/OLD] */
    // added 2026-11-03 v0.6.0 review: a variants run counts takes (per per scene): "take 2 of 3"
    const per = Math.max(1, run.per || 1);
    if (per > 1) {
      const units = n * per;
      const doneUnits = run.targets.reduce((a, id) => a + (run.done.includes(id) ? per : Math.min(per, run.takes?.[id] || 0)), 0);
      return { n: units, done: doneUnits, index: Math.min(units, doneUnits + (cur ? 1 : 0)), current: cur || null, scenePart: part,
        total: Math.min(1, (doneUnits + part) / units), reused: run.reused || [], unit: "take", per };
    }
    const done = run.done.length;
    return { n, done, index: Math.min(n, done + (cur ? 1 : 0)), current: cur || null, scenePart: part, total: Math.min(1, (done + part) / n), reused: run.reused || [], unit: "scene", per: 1 };
  }
  ctx.runProgress = runProgress;
  function updateTitle() {
    const r = runProgress();
    host.setTitle?.(r ? `rendering ${Math.max(1, r.index)}/${r.n} · ${Math.round(r.total * 100)}%` : null);
  }

  const lastProgressRender = { at: 0 };
  /* [OLD 2026-11-03 v0.5.1->v0.6.0] every step re-rendered the whole tab (throttled); "error"/"skipped" phases did not exist
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
  [/OLD] */
  // added 2026-11-03 v0.6.0: a tab that exports onProgress(ctx, d) updates its own elements in place; the editor then
  // re-renders only when a scene starts or ends or its phase or pass changes, and refreshes the footer (throttled).
  // Tabs without onProgress get the old throttled re-render. "error" and "skipped" end a scene too.
  let lastProgressScene = null;
  const footerSoon = () => {
    const now = Date.now();
    if (now - lastProgressRender.at > 250) { lastProgressRender.at = now; renderFooter(); }
  };
  on("reelwright.progress", d => {
    if (!d || d.slug !== store.project.slug) return;
    const prev = store.eph.progress[d.scene_id];
    // [OLD 2026-11-03 v0.6.0 review] store.eph.progress[d.scene_id] = d;
    // [OLD 2026-11-03 v0.6.0 review] const final = FINAL.has(d.phase);
    // [OLD 2026-11-03 v0.6.0 review] const run = store.eph.run;
    const run = store.eph.run;
    // added 2026-11-03 v0.6.0 review: a variants run renders `per` takes of each scene and sends "done" after every
    // one; the scene ends with the last ("error" and "skipped" end it at once). Until then it shows as queued for
    // its next take.
    let final = FINAL.has(d.phase);
    if (run && run.per > 1 && d.phase === "done" && run.targets.includes(d.scene_id) && !run.done.includes(d.scene_id)) {
      const k = run.takes[d.scene_id] = (run.takes[d.scene_id] || 0) + 1;
      if (k < run.per) final = false;
    }
    store.eph.progress[d.scene_id] = final || d.phase !== "done" ? d : { ...d, phase: "queued", pass: 1, step: 0, steps: 0 };
    if (run && final && !run.done.includes(d.scene_id)) run.done.push(d.scene_id);
    if (run && d.phase === "error") (run.failed ||= []).push({ scene_id: d.scene_id, error: d.message || "" });
    if (run && d.phase === "skipped") (run.skipped ||= []).push({ scene_id: d.scene_id, reason: d.message || "" });
    updateTitle();
    // [OLD 2026-11-03 v0.6.0 review] if (final) {
    if (final || d.phase === "done") { // added 2026-11-03 v0.6.0 review: every variant take shows up as it is made
      actions.refreshTakes();
      store.refreshPlan();
    }
    if (d.phase === "error") actions.toast(`${titleOf(d.scene_id)} failed${d.message ? ": " + d.message : ""}. Scenes that don't depend on it keep rendering.`, "error");
    let changed = !prev || prev.phase !== d.phase || prev.pass !== d.pass || final || lastProgressScene !== d.scene_id;
    lastProgressScene = d.scene_id;
    // [OLD 2026-11-08 v0.12.0->v0.13.0] const tab = TABS[store.project.ui.tab] || TABS.timeline;
    const tab = TABS[currentTabId()]; // added 2026-11-08 v0.13.0
    if (tab.mod.onProgress) {
      try { tab.mod.onProgress(ctx, d); } catch (err) { console.warn("Reelwright: onProgress failed", err); changed = true; }
      if (changed) { lastProgressRender.at = Date.now(); store.notify(); } else footerSoon();
      return;
    }
    // [OLD 2026-11-06 v0.9.0->v0.10.0] const now = Date.now();
    // [OLD 2026-11-06 v0.9.0->v0.10.0] if (now - lastProgressRender.at > 250 || d.phase !== "sample") { lastProgressRender.at = now; store.notify(); }
    // added 2026-11-06 v0.10.0: the other tabs (Assets, Cast, Files, Global) show nothing that changes with a sampler
    // step, only statuses, which change with a scene's phase or pass: they are rebuilt then, and the footer follows
    // the steps. They were rebuilt four times a second while a render ran, and their pictures blinked.
    if (changed) { lastProgressRender.at = Date.now(); store.notify(); } else footerSoon();
  });
  // added 2026-11-03 v0.4.2: progress of LLM requests (Import, Rewrite, Split), at most four redraws a second
  const lastLlmRender = { at: 0 };
  // [OLD 2026-11-03 v0.5.1->v0.6.0] host.on("reelwright.llm", d => {
  /* [OLD 2026-11-06 v0.10.1->v0.10.2] every event (about two a second while a model writes, from any job of any
     browser tab) rebuilt the whole tab: its tooltips restarted and its text fields flickered
  on("reelwright.llm", d => {
    if (!d?.job) return;
    store.eph.llmJobs[d.job] = d;
    const now = Date.now();
    if (now - lastLlmRender.at > 250 || d.phase !== "writing") { lastLlmRender.at = now; store.notify(); }
  });
  [/OLD] */
  // added 2026-11-06 v0.10.2: only jobs made on this page; the progress lines that show the job (llmjob.jobText) are
  // rewritten in place, and nothing else is rebuilt. A tab drawn later reads eph.llmJobs.
  on("reelwright.llm", d => {
    if (!d?.job || !ownJobs.has(d.job)) return;
    store.eph.llmJobs[d.job] = d;
    // added 2026-11-09 v0.15.0: keep what the request received (llmjob.feedStream) and update the output popup
    try { feedStream(d); } catch { /* the progress line still updates */ }
    for (const el of root.querySelectorAll(".rw-llm-out")) { try { el.__rwFeed?.(d); } catch { /* keep the old text */ } }
    for (const el of root.querySelectorAll("[data-llm-job]")) {
      if (el.dataset.llmJob !== d.job) continue;
      // [OLD 2026-11-08 v0.12.0->v0.13.0] try { el.textContent = (el.__rwJobText || jobLine)(d); } catch { /* keep the old text */ }
      // added 2026-11-08 v0.13.0: an element can draw the event itself (the Chat tab's answer, as Markdown)
      try { if (el.__rwJobRender) el.__rwJobRender(el, d); else el.textContent = (el.__rwJobText || jobLine)(d); } catch { /* keep the old text */ }
    }
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
  // [OLD 2026-11-03 v0.5.1->v0.6.0] host.on("reelwright.preview", d => {
  on("reelwright.preview", d => {
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
      // [OLD 2026-11-03 v0.5.1->v0.6.0] if (seq !== comfySeq || !store.eph.running) return; // a newer one is on its way, or the run is over  (not after destroy)
      if (destroyed || seq !== comfySeq || !store.eph.running) return; // a newer one is on its way, or the run is over
      setPreview({ ...meta, blob: b });
    });
  }
  /* [OLD 2026-11-03 v0.5.1->v0.6.0] any other phase than "start" ended the run; a Stop or a pre-flight error never sent "end", so the editor stayed in "rendering"
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
  [/OLD] */
  // added 2026-11-03 v0.6.0: the run contract. "start" {run_id, targets, reused}; "end" (always sent) {rendered,
  // failed: [{scene_id, error}], skipped: [{scene_id, reason}], interrupted, error?}; "rejected" {error} when the
  // pre-flight check refused the run before any GPU work. ComfyUI's own events (below) clear a run whose "end" never
  // came (older backend, crash).
  const titleOf = id => store.project.scenes.find(s => s.id === id)?.title || id;
  function finishRun(d = {}, { quiet = false, source = "run" } = {}) {
    const run = store.eph.run;
    ourPrompt = null;
    setPreview(null);
    // progress entries that never reached an end belong to the run that just ended
    for (const [id, x] of Object.entries(store.eph.progress)) if (!FINAL.has(x.phase)) delete store.eph.progress[id];
    const failed = Array.isArray(d.failed) ? d.failed : (run?.failed || []);
    const skipped = Array.isArray(d.skipped) ? d.skipped : (run?.skipped || []);
    const rendered = Array.isArray(d.rendered) ? d.rendered : Array.isArray(d.targets) ? d.targets : [];
    const reused = Array.isArray(d.reused) ? d.reused : (run?.reused || []);
    // added 2026-11-03 v0.6.0 review: warnings [{scene_id, message}]: extra takes (a drift retake, variants 2..n) that
    // failed after the scene's first take was made (the scene still counts as rendered)
    const warnings = Array.isArray(d.warnings) ? d.warnings.filter(w => w && typeof w === "object") : [];
    /* [OLD 2026-11-03 v0.6.0 review] no warnings
    const lastRun = { run_id: d.run_id ?? run?.id ?? null, at: Date.now(), source, rendered, failed, skipped, reused,
      interrupted: !!d.interrupted, rejected: d.phase === "rejected", error: d.error || "" };
    [/OLD] */
    const lastRun = { run_id: d.run_id ?? run?.id ?? null, at: Date.now(), source, rendered, failed, skipped, reused, warnings,
      interrupted: !!d.interrupted, rejected: d.phase === "rejected", error: d.error || "" };
    store.setEph({ running: false, run: null, lastRun });
    host.setTitle?.(null);
    actions.refreshTakes();
    store.refreshPlan();
    if (quiet) return;
    const n = (k, word) => `${k} ${word}`;
    // [OLD 2026-11-03 v0.6.0 review] const extra = [failed.length && n(failed.length, "failed"), skipped.length && n(skipped.length, "skipped")].filter(Boolean).join(" · ");
    const extra = [failed.length && n(failed.length, "failed"), skipped.length && n(skipped.length, "skipped"),
      warnings.length && n(warnings.length, warnings.length === 1 ? "warning" : "warnings")].filter(Boolean).join(" · "); // added 2026-11-03 v0.6.0 review: warnings
    // added 2026-11-03 v0.6.0 review: the first warning, when nothing failed
    const firstWarning = warnings.length ? ` · ${titleOf(warnings[0].scene_id)}: ${warnings[0].message || "an extra take failed"}` : "";
    if (lastRun.rejected) actions.toast("Render not started: " + (d.error || "the project has errors"), "error");
    else if (lastRun.interrupted) actions.toast(`Render stopped · ${n(rendered.length, "rendered")}${extra ? " · " + extra : ""}`, "warn");
    else if (failed.length) actions.toast(`Render finished with errors · ${n(rendered.length, "rendered")} · ${extra} · ${titleOf(failed[0].scene_id)}: ${failed[0].error || "failed"}`, "error");
    else if (d.error) actions.toast("Render stopped: " + d.error, "error");
    // [OLD 2026-11-03 v0.6.0 review] else actions.toast(`Render finished · ${rendered.length} generated · ${reused.length} reused${extra ? " · " + extra : ""}`, "ok");
    else actions.toast(`Render finished · ${rendered.length} generated · ${reused.length} reused${extra ? " · " + extra : ""}${firstWarning}`, warnings.length ? "warn" : "ok"); // added 2026-11-03 v0.6.0 review: warnings
  }
  on("reelwright.run", d => {
    if (!d || d.slug !== store.project.slug) return;
    if (d.phase === "start") {
      setPreview(null);
      // [OLD 2026-11-03 v0.6.0 review] store.setEph({ running: true, run: { id: d.run_id ?? null, targets: d.targets || [], reused: d.reused || [], done: [], failed: [], skipped: [], started: Date.now() } });
      // added 2026-11-03 v0.6.0 review: per (takes per scene) and takes (done events so far) for a variants run
      const q = takeQueuedRun(d.targets || []);
      store.setEph({ running: true, run: { id: d.run_id ?? null, targets: d.targets || [], reused: d.reused || [], done: [], failed: [], skipped: [], started: Date.now(),
        per: q?.per || 1, takes: {} } });
      updateTitle();
    // [OLD 2026-11-03 v0.6.0 review] } else if (d.phase === "rejected") finishRun(d);
    } else if (d.phase === "rejected") { queuedRuns.shift(); finishRun(d); } // added 2026-11-03 v0.6.0 review: the oldest queued run was refused
    else finishRun(d); // "end" (and any older backend's last word)
  });
  // added 2026-11-03 v0.6.0: ComfyUI's view of the prompt that runs this node. `ourPrompt` is the prompt id that
  // executed (or cached) this node; its end, error or interrupt clears a run that is still shown as running.
  let comfyPrompt = null, ourPrompt = null;
  const ownNode = id => id !== null && id !== undefined && !!host.isOwnNode?.(id);
  const comfyEnd = (kind, message) => {
    if (!store.eph.running && !store.eph.run) { ourPrompt = null; return; }
    finishRun(kind === "interrupted" ? { interrupted: true } : kind === "error" ? { error: message || "ComfyUI reported an error" } : {},
      { source: "comfy", quiet: kind === "done" });
  };
  on("execution_start", d => { comfyPrompt = d?.prompt_id ?? null; });
  on("execution_cached", d => { if ((d?.nodes || []).some(ownNode)) ourPrompt = d?.prompt_id ?? comfyPrompt ?? "?"; });
  on("executing", d => {
    const node = d && typeof d === "object" ? (d.display_node ?? d.node ?? null) : d;
    if (node === null || node === undefined) {
      const pid = d && typeof d === "object" ? d.prompt_id : comfyPrompt;
      if (ourPrompt && (!pid || pid === ourPrompt)) comfyEnd("done");
    } else if (ownNode(node)) ourPrompt = comfyPrompt ?? "?";
  });
  on("execution_success", d => { if (ourPrompt && (!d?.prompt_id || d.prompt_id === ourPrompt)) comfyEnd("done"); });
  const mine = d => (!!ourPrompt && d?.prompt_id === ourPrompt) || ownNode(d?.node_id);
  on("execution_error", d => { if (mine(d)) comfyEnd("error", d?.exception_message); });
  on("execution_interrupted", d => { if (mine(d)) comfyEnd("interrupted"); });
  // a queued run whose node never executed (an error upstream, a cancelled prompt): the queue runs dry
  on("status", d => {
    // added 2026-11-03 v0.6.0 review: an empty queue has no run of ours left to start
    if (d?.exec_info?.queue_remaining === 0 && !store.eph.run && !queueing) queuedRuns.length = 0;
    if (d?.exec_info?.queue_remaining !== 0 || !store.eph.running || store.eph.run) return;
    later(() => {
      if (!store.eph.running || store.eph.run || Date.now() - (store.eph.queuedAt || 0) < 1500) return;
      finishRun({}, { source: "comfy", quiet: true });
      actions.toast("The render did not start: ComfyUI finished its queue without running this node.", "warn");
    }, 1500);
  });
  /* [OLD 2026-11-02 v0.2.0->v0.2.1] a failed merge (e.g. the automatic one after a render) was not shown
  host.on("reelwright.merge", d => {
    if (d.slug !== store.project.slug) return;
    store.setEph({ merge: d });
  });
  [/OLD] */
  /* [OLD 2026-11-03 v0.5.1->v0.6.0] no job ids, no Stop
  host.on("reelwright.merge", d => {
    if (d.slug !== store.project.slug) return;
    if (d.error) {
      store.setEph({ merge: { ...d, phase: "error" } });
      if (!mergeInFlight) actions.toast("Merge failed: " + d.error.split("\n").filter(Boolean).slice(-1)[0], "error");
      return;
    }
    store.setEph({ merge: d });
  });
  [/OLD] */
  // added 2026-11-03 v0.6.0: events carry the merge's job id; this editor's own merge reports its errors through the
  // HTTP answer, and a stopped merge is not an error
  on("reelwright.merge", d => {
    if (!d || d.slug !== store.project.slug) return;
    const own = mergeInFlight && (!d.job || d.job === mergeJob);
    if (d.error) {
      const stopped = (own && mergeCancelRequested) || d.cancelled;
      store.setEph({ merge: { ...d, phase: stopped ? "cancelled" : "error" } });
      if (!own && !stopped) actions.toast("Merge failed: " + String(d.error).split("\n").filter(Boolean).slice(-1)[0], "error");
      return;
    }
    // added 2026-11-06 v0.10.2: ffmpeg reports a merge's progress twice a second, and each event rebuilt the whole tab
    // (behind the Scene tab a long merge made its tooltips restart and its text fields flicker). A progress event of
    // the merge already shown only rewrites the percentages in place.
    const prev = store.eph.merge;
    if (d.phase === "progress" && (prev?.phase === "start" || prev?.phase === "progress") && (prev.job ?? null) === (d.job ?? null)) {
      store.eph.merge = d;
      const pct = mergePct(d);
      for (const el of root.querySelectorAll(".rw-merge-pct")) el.textContent = pct;
      return;
    }
    store.setEph({ merge: d });
  });

  /* [OLD 2026-11-03 v0.5.1->v0.6.0] takes were read at mount (the empty "untitled" project of a node still being
     loaded) and never after load(); new nodes shared the "untitled" folder; destroy() left listeners and timers behind
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
    get eph() { return store.eph; }, // added 2026-11-03 v0.4.2: session state, read by the test harness
    // [OLD 2026-11-02 v0.3.7->v0.3.8] destroy() { timeline.stopPlayback(ctx); root.remove(); },
    destroy() { timeline.stopPlayback(ctx); previewView.clear(); root.remove(); },
  };
  [/OLD] */

  // added 2026-11-03 v0.6.0: /autosave says the folder holds another project (a different project_id)
  let conflictOpen = false;
  /* [OLD 2026-11-03 v0.6.0 review] focused "Use a separate project" (a Space typed into a prompt pressed it) and
     returned nothing (Render could not wait for the decision)
  async function resolveConflict(info) {
    if (conflictOpen || destroyed || !info) return;
    conflictOpen = true;
    try {
      const p = store.project;
      const otherName = info.other?.name ? `“${info.other.name}”` : "another project";
      const choice = await choiceDialog(root, {
        title: "Another project uses this folder",
        message: `output/reelwright/${info.slug}/ holds ${otherName}. Saving “${p.name}” there would mix the two projects' renders.\n\n` +
          `Use a separate project to save this one in a new folder (its renders start fresh). Take over the folder only if ${otherName} is an older copy of this project.`,
        danger: true, help: "app.conflict", cancelValue: "later", focus: "separate",
        choices: [
          { value: "later", label: "Decide later", help: "app.conflict.later" },
          { value: "takeover", label: "Take over this folder", variant: "danger", help: "app.conflict.takeover" },
          { value: "separate", label: "Use a separate project", variant: "primary", help: "app.conflict.separate" },
        ],
      });
      if (destroyed) return;
      if (choice === "separate") await useSeparateFolder(info.slug);
      else if (choice === "takeover") {
        const r = await store.saveNow({ force: true });
        if (r.ok) actions.toast(`This project now owns output/reelwright/${store.project.slug}/.`, "ok");
        else if (!r.conflict) actions.toast("Not saved to disk: " + r.error, "error");
      } else actions.toast("Not saved to disk: the folder belongs to another project. The workflow keeps your edits; click “Folder in use” below to decide.", "warn");
    } finally {
      conflictOpen = false;
    }
  }
  [/OLD] */
  // added 2026-11-03 v0.6.0 review: opened only by Ctrl+S, Render, Merge or the footer's "Folder in use"; the harmless
  // "Decide later" has focus at first. Resolves true when the folder question is settled (separate folder or take over).
  async function resolveConflict(info) {
    if (conflictOpen || destroyed || !info) return false;
    conflictOpen = true;
    try {
      const p = store.project;
      const otherName = info.other?.name ? `“${info.other.name}”` : "another project";
      const choice = await choiceDialog(root, {
        title: "Another project uses this folder",
        message: `output/reelwright/${info.slug}/ holds ${otherName}. Saving “${p.name}” there would mix the two projects' renders.\n\n` +
          `Use a separate project to save this one in a new folder (its renders start fresh). Take over the folder only if ${otherName} is an older copy of this project.`,
        danger: true, help: "app.conflict", cancelValue: "later", focus: "later",
        choices: [
          { value: "later", label: "Decide later", help: "app.conflict.later" },
          { value: "takeover", label: "Take over this folder", variant: "danger", help: "app.conflict.takeover" },
          { value: "separate", label: "Use a separate project", variant: "primary", help: "app.conflict.separate" },
        ],
      });
      if (destroyed) return false;
      if (choice === "separate") return await useSeparateFolder(info.slug);
      if (choice === "takeover") {
        const r = await store.saveNow({ force: true });
        if (r.ok) actions.toast(`This project now owns output/reelwright/${store.project.slug}/.`, "ok");
        else if (!r.conflict) actions.toast("Not saved to disk: " + r.error, "error");
        return !!r.ok;
      }
      actions.toast("Not saved to disk: the folder belongs to another project. The workflow keeps your edits; click “Folder in use” below to decide.", "warn");
      return false;
    } finally {
      conflictOpen = false;
    }
  }
  // added 2026-11-03 v0.6.0 review: a background autosave found the folder in use. No dialog (it would take the
  // keyboard from whatever the user is typing): the footer shows "Folder in use" (click to decide) and one toast.
  function conflictNotice(info) {
    if (destroyed || !info) return;
    const key = `${info.slug}|${info.other?.id || ""}`;
    if (conflictToastFor === key) return;
    conflictToastFor = key;
    const otherName = info.other?.name ? `“${info.other.name}”` : "another project";
    actions.toast(`Autosave paused: output/reelwright/${info.slug}/ holds ${otherName}. The workflow keeps your edits; click “Folder in use” below to decide.`, "warn");
  }
  // the first free "<slug>-N" that no other node uses and the server accepts
  async function useSeparateFolder(fromSlug) {
    const base = String(fromSlug || store.project.slug || "untitled").replace(/-\d+$/, "").slice(0, 60) || "untitled";
    const taken = new Set(host.otherSlugs?.() || []);
    for (let n = 2; n < 100; n++) {
      const slug = `${base}-${n}`;
      if (taken.has(slug)) continue;
      try {
        await rw.autosave({ ...store.project, slug });
      } catch (err) {
        if (err.status === 409) continue;
        store.update(q => { q.slug = slug; }, { label: "Use a separate folder" });
        actions.toast(`Moved to output/reelwright/${slug}/, but not saved yet: ${err.message}`, "error");
        // [OLD 2026-11-03 v0.6.0 review] return;
        return true; // added 2026-11-03 v0.6.0 review: the folder is settled (resolveConflict's result)
      }
      // [OLD 2026-11-03 v0.6.0 review] if (destroyed) return;
      if (destroyed) return false; // added 2026-11-03 v0.6.0 review
      store.update(q => { q.slug = slug; }, { label: "Use a separate folder", autosave: false });
      store.setEph({ saveState: "saved", conflict: null, saveError: "" });
      actions.toast(`Saved as a separate project in output/reelwright/${slug}/.`, "ok");
      // [OLD 2026-11-03 v0.6.0 review] return;
      return true; // added 2026-11-03 v0.6.0 review
    }
    actions.toast("No free folder name found. Change the folder on the Global tab.", "error");
    return false; // added 2026-11-03 v0.6.0 review
  }

  render();
  // added 2026-11-03 v0.6.0: a node being loaded gets its plan and takes after load(); a new node after startNew()
  if (hasInitial) { store.refreshPlan(); actions.refreshTakes(); }
  actions.refreshModels();
  actions.refreshInfo();
  // added 2026-11-08 v0.13.0: the LLM settings stored on the server (its base URL shows the Chat tab); the Global tab
  // loaded them only when it was opened
  if (!store.eph.llm) {
    store.eph.llm = {};
    rw.llmSettings().then(st => { if (!destroyed) store.setEph({ llm: { ...store.eph.llm, ...st } }); }).catch(() => {});
  }

  return {
    root,
    showComfyPreview, // added 2026-11-02 v0.3.7: ComfyUI's preview stream for this node, redirected by reelwright.js
    // added 2026-11-02 v0.3.0: called for a node that was just added (not loaded from a workflow)
    // added 2026-11-03 v0.6.0: the new project gets its own folder "untitled-xxxx" (two new nodes never share one) and a
    // project id; a default profile from before v0.5.0 moves its score to the soundtrack
    async startNew() {
      store.setEph({ fresh: true });
      let tag = "";
      while (tag.length < 4) tag += Math.random().toString(36).slice(2).replace(/[^a-z0-9]/g, "");
      store.update(p => {
        if (!p.name) p.name = "Untitled";
        if (!p.slug || p.slug === "untitled") p.slug = "untitled-" + tag.slice(0, 4); // the default project's folder only
        if (!p.project_id) p.project_id = newId("p");
      }, { history: false, autosave: false });
      const r = await actions.loadProfiles();
      if (destroyed) return;
      const d = r?.profiles?.find(x => x.id === r.default);
      if (d) {
        let moved = false;
        store.update(p => { p.global = normalizeGlobal(d.global, p); moved = migrateScoreIn(p); }, { history: false });
        store.setEph({ profileSel: d.id });
        actions.toast(`New project: using profile “${d.name}”.`, "ok");
        if (moved) actions.toast("The profile's score track (from before v0.5.0) is now a looping track on the Timeline's Soundtrack lane.", "warn");
      }
    },
    // added 2026-11-03 v0.6.0: takes follow every load (a reopened workflow showed the "untitled" folder's takes)
    load(json) { store.load(json); takesSoon(); },
    // added 2026-11-03 v0.6.0: this node is a copy (paste, duplicate) of another Reelwright node in the graph: it
    // becomes a separate project with a new project id, folder "<slug>-N" (none of `usedSlugs`) and new scene ids.
    // Takes stay with the original; the copy starts fresh. Returns the new slug.
    forkProject(usedSlugs = []) {
      const used = new Set(usedSlugs);
      const p = JSON.parse(JSON.stringify(store.project));
      const base = String(p.slug || "untitled").replace(/-\d+$/, "").slice(0, 60) || "untitled";
      let n = 2;
      while (used.has(`${base}-${n}`) || `${base}-${n}` === p.slug) n++;
      const map = {};
      p.project_id = newId("p");
      p.slug = `${base}-${n}`;
      for (const sc of p.scenes) { const id = newId("s"); map[sc.id] = id; sc.id = id; }
      p.ui.selected = map[p.ui.selected] || p.scenes[0]?.id || "";
      if (p.global?.merge?.color_ref_scene) p.global.merge.color_ref_scene = map[p.global.merge.color_ref_scene] || "";
      // added 2026-11-05 v0.7.0: a scene's colour match names another scene by id (scene.merge.color_ref)
      for (const sc of p.scenes) if (sc.merge?.color_ref) sc.merge.color_ref = map[sc.merge.color_ref] || "";
      store.load(p, { persist: true });
      takesSoon();
      actions.toast(`This node is a copy of another Reelwright node, so it is now a separate project in its own folder “${p.slug}”. Its renders start fresh.`, "warn");
      return p.slug;
    },
    // added 2026-11-03 v0.6.0 review: this node shares its project id with an older node but has a folder of its own (a
    // copy that got its own folder before v0.6.0 gave projects ids): it only gets a project id of its own. Folder,
    // scene ids and renders stay, nothing is announced. The id is derived from the shared id and the folder, so loading
    // the same (unsaved) workflow again gives the same id and the folder's project.json keeps matching. Returns it.
    separateProjectId() {
      const p = store.project;
      const id = derivedProjectId(p.project_id || p.id || "", p.slug || "");
      if (id === p.project_id) return id;
      store.update(q => { q.project_id = id; }, { history: false, plan: false, autosave: false });
      return id;
    },
    flush: () => store.flush(), // added 2026-11-03 v0.6.0: write a pending edit into the widget now
    get project() { return store.project; },
    get eph() { return store.eph; }, // added 2026-11-03 v0.4.2: session state, read by the test harness
    get store() { return store; }, // added 2026-11-03 v0.6.0: for the test harness (history, jumpTo)
    get actions() { return actions; }, // added 2026-11-03 v0.6.0: for the test harness (merge, cancelMerge, run)
    get destroyed() { return destroyed; },
    // [OLD 2026-11-02 v0.3.7->v0.3.8] destroy() { timeline.stopPlayback(ctx); root.remove(); },
    // [OLD 2026-11-03 v0.5.1->v0.6.0] destroy() { timeline.stopPlayback(ctx); previewView.clear(); root.remove(); },
    // added 2026-11-03 v0.6.0: releases everything: host listeners, the focus guard, timers, the render frame, the
    // store (its pending widget write is flushed and a pending autosave is sent), an open dialog or menu, tooltips
    destroy() {
      if (destroyed) return;
      // [OLD 2026-11-03 v0.6.0 review] if (ctx.eph.playing) timeline.stopPlayback(ctx);  (a song excerpt kept playing)
      // added 2026-11-03 v0.6.0: always, so excerpt players and the playback loop stop with the node
      try { timeline.stopPlayback(ctx); } catch (err) { console.warn("Reelwright: stop playback failed", err); }
      root.__rwModalClose?.();
      root.__rwMenuClose?.();
      destroyed = true;
      for (const off of offs.splice(0)) { try { off(); } catch { /* already gone */ } }
      unguard();
      for (const t of timeouts) clearTimeout(t);
      timeouts.clear();
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      previewView.clear();
      tips.destroy?.();
      store.dispose();
      // a combobox list still open counts against the shared state
      if (root.__rwCombo) { comboState.open = Math.max(0, comboState.open - root.__rwCombo); root.__rwCombo = 0; }
      root.remove();
    },
  };
}
