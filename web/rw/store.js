// Project state with undo/redo, debounced persistence to the node widget and
// the autosave route, and a debounced /plan request for statuses and prompts.
//
// added 2026-11-03 v0.6.0, the store contract (docs: notes_F1.md "APIs for F2"):
// - update(fn, {label, history, coalesce, plan, render, autosave}): `label` names the step in the undo history
//   (History menu in the top bar). Undo/redo/jumpTo never change the view: `project.ui` (tab, zoom, snap, ripple,
//   playhead, selection) stays as it is, only the selection falls back when its scene is gone.
// - history() -> [{k, label, at, done}] oldest first (done=false: undone steps that redo brings back); jumpTo(k)
//   moves to the state right after step k (-1: before the oldest step kept).
// - project.__rwv: a non-enumerable number that changes on every update, undo, redo, load and replace. model.js
//   memoises per version; JSON.stringify and structuredClone leave it out.
// - flush() writes a pending widget update now; dispose() flushes, sends a pending autosave and stops every timer.
// - saveNow() -> {ok, error?, conflict?}; an autosave answered with 409 slug_conflict calls onConflict(info) and
//   pauses autosaving for that folder until autosave({force}) or a new slug.
//   added 2026-11-03 v0.6.0 review: onConflict(info, {explicit}): explicit is true for saveNow() (Ctrl+S, the folder
//   dialog) and false for the background autosave.

import { rw } from "./api.js";
import { normalizeProject } from "./model.js";

const HISTORY_LIMIT = 150;
const COALESCE_MS = 1200;

/* [OLD 2026-11-03 v0.5.1->v0.6.0] rewritten below: named history, undo without view state, version stamp, flush/dispose, honest save, folder conflicts
export function createStore(project, { persist }) {
  let state = project;
  const undoStack = [];
  const redoStack = [];
  let lastCoalesce = { key: null, at: 0 };
  const listeners = new Set();
  const timers = {};
  let planSeq = 0;

  const eph = {
    plan: null, takes: null, models: null, info: null, llm: null, versions: null,
    backend: "connecting", saveState: "saved", progress: {}, running: false, merge: null,
    playing: false, toasts: [], rewrite: null, scriptDraft: null, compare: null, seam: null,
    assetFilter: "all", assetQuery: "", selectedAsset: "", selectedCast: "", openPasses: {},
    llmJobs: {}, // added 2026-11-03 v0.4.2: latest reelwright.llm progress event per job id
  };

  function notify() {
    for (const fn of listeners) fn();
  }

  function debounce(name, ms, fn) {
    clearTimeout(timers[name]);
    timers[name] = setTimeout(fn, ms);
  }

  function schedulePersist(autosave) {
    debounce("persist", 200, () => persist(JSON.stringify(state)));
    if (autosave) {
      eph.saveState = "pending";
      debounce("autosave", 4000, async () => {
        try {
          await rw.autosave(state);
          eph.saveState = "saved";
        } catch {
          eph.saveState = "offline";
        }
        notify();
      });
    }
  }

  async function requestPlan() {
    const seq = ++planSeq;
    try {
      const plan = await rw.plan(state);
      if (seq !== planSeq) return;
      eph.plan = plan;
      eph.backend = "online";
    } catch (err) {
      if (seq !== planSeq) return;
      eph.backend = "offline";
      eph.planError = String(err.message || err);
    }
    notify();
  }

  function schedulePlan() {
    debounce("plan", 450, requestPlan);
  }

  return {
    get project() { return state; },
    eph,
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    notify,

    // history: record an undo step; coalesce: merge rapid edits with the same key;
    // plan: re-request /plan; render: re-render the view.
    update(mutator, { history = true, coalesce = null, plan = true, render = true, autosave = true } = {}) {
      if (history) {
        const now = Date.now();
        const merge = coalesce && lastCoalesce.key === coalesce && now - lastCoalesce.at < COALESCE_MS;
        if (!merge) {
          undoStack.push(JSON.stringify(state));
          if (undoStack.length > HISTORY_LIMIT) undoStack.shift();
          redoStack.length = 0;
        }
        lastCoalesce = { key: coalesce, at: now };
      }
      mutator(state);
      schedulePersist(autosave && history);
      if (plan) schedulePlan();
      if (render) notify();
    },

    setEph(patch, render = true) {
      Object.assign(eph, patch);
      if (render) notify();
    },

    replaceProject(next) {
      undoStack.push(JSON.stringify(state));
      redoStack.length = 0;
      state = normalizeProject(next);
      schedulePersist(true);
      schedulePlan();
      notify();
    },

    undo() {
      if (!undoStack.length) return false;
      redoStack.push(JSON.stringify(state));
      state = JSON.parse(undoStack.pop());
      lastCoalesce = { key: null, at: 0 };
      schedulePersist(true);
      schedulePlan();
      notify();
      return true;
    },

    redo() {
      if (!redoStack.length) return false;
      undoStack.push(JSON.stringify(state));
      state = JSON.parse(redoStack.pop());
      schedulePersist(true);
      schedulePlan();
      notify();
      return true;
    },

    canUndo: () => undoStack.length > 0,
    canRedo: () => redoStack.length > 0,
    refreshPlan: requestPlan,

    async saveNow() {
      clearTimeout(timers.autosave);
      persist(JSON.stringify(state));
      try {
        await rw.autosave(state);
        eph.saveState = "saved";
      } catch {
        eph.saveState = "offline";
      }
      notify();
    },

    // External replacement of the widget value (workflow loaded, paste).
    load(json) {
      state = normalizeProject(json);
      undoStack.length = 0;
      redoStack.length = 0;
      schedulePlan();
      notify();
    },
  };
}
[/OLD] */

// added 2026-11-03 v0.6.0: version stamp for memoised model helpers (see the contract above)
let VERSION_SEQ = 0;
export function stampVersion(p) {
  if (p && typeof p === "object") Object.defineProperty(p, "__rwv", { value: ++VERSION_SEQ, enumerable: false, configurable: true, writable: true });
  return p;
}

// added 2026-11-03 v0.6.0: projects saved before v0.6.0 have no project_id but a stable `id` made once by
// defaultProject; using it keeps the identity stable across reloads (a random new id on every load would make the
// autosave report a folder conflict with the project's own folder)
export function withProjectId(raw) {
  let p = raw;
  if (typeof p === "string") {
    try { p = p.trim() ? JSON.parse(p) : null; } catch { p = null; }
  }
  if (p && typeof p === "object" && !Array.isArray(p) && !(typeof p.project_id === "string" && p.project_id) && typeof p.id === "string" && p.id) p.project_id = p.id;
  return p ?? raw;
}

// added 2026-11-03 v0.6.0: rewritten for named history, view state outside undo, version stamps, flush/dispose,
// honest saving and the folder-conflict answer of /autosave
export function createStore(project, { persist, onConflict } = {}) {
  let state = stampVersion(project);
  const undoStack = []; // {json: state before the step, label, at}
  const redoStack = []; // {json: state after the step, label, at}
  let lastCoalesce = { key: null, at: 0 };
  const listeners = new Set();
  const timers = {};
  let planSeq = 0;
  let persistPending = false, autosavePending = false, disposed = false;

  const eph = {
    plan: null, takes: null, models: null, info: null, llm: null, versions: null,
    backend: "connecting", saveState: "saved", progress: {}, running: false, merge: null,
    playing: false, toasts: [], rewrite: null, scriptDraft: null, compare: null, seam: null,
    assetFilter: "all", assetQuery: "", selectedAsset: "", selectedCast: "", openPasses: {},
    llmJobs: {}, // added 2026-11-03 v0.4.2: latest reelwright.llm progress event per job id
    // added 2026-11-03 v0.6.0: saveError (last autosave failure), conflict ({slug, other} while /autosave reports
    // that the folder holds another project), lastRun (the last reelwright.run "end"), takesSlug (folder of `takes`)
    saveError: "", conflict: null, lastRun: null, takesSlug: null,
  };

  function notify() {
    if (disposed) return;
    for (const fn of [...listeners]) fn();
  }

  function debounce(name, ms, fn) {
    clearTimeout(timers[name]);
    timers[name] = setTimeout(fn, ms);
  }

  function flush() {
    if (!persistPending) return false;
    clearTimeout(timers.persist);
    persistPending = false;
    persist?.(JSON.stringify(state));
    return true;
  }

  const isConflict = err => err?.status === 409 && (err.reason === "slug_conflict" || err.data?.reason === "slug_conflict");

  // one autosave request now; {ok} or {ok: false, error, conflict}
  // [OLD 2026-11-03 v0.6.0 review] async function autosaveNow({ force = false } = {}) {
  // added 2026-11-03 v0.6.0 review: `explicit` (Ctrl+S, the folder dialog) is passed on to onConflict, so a background
  // autosave can report a folder conflict quietly instead of opening a dialog under the user's typing
  async function autosaveNow({ force = false, explicit = false } = {}) {
    clearTimeout(timers.autosave);
    autosavePending = false;
    const sent = state;
    try {
      await rw.autosave(sent, force ? { force: true } : undefined);
      if (disposed) return { ok: true };
      eph.saveState = "saved";
      eph.saveError = "";
      eph.conflict = null;
      return { ok: true };
    } catch (err) {
      if (disposed) return { ok: false, error: String(err?.message || err) };
      if (isConflict(err)) {
        const other = err.data?.other || {};
        eph.saveState = "conflict";
        eph.conflict = { slug: sent.slug, other };
        eph.saveError = `the folder “${sent.slug}” holds another project${other.name ? ` (“${other.name}”)` : ""}`;
        // [OLD 2026-11-03 v0.6.0 review] try { onConflict?.(eph.conflict); } catch (e) { console.warn("Reelwright: conflict handler failed", e); }
        try { onConflict?.(eph.conflict, { explicit }); } catch (e) { console.warn("Reelwright: conflict handler failed", e); } // added 2026-11-03 v0.6.0 review: {explicit}
        return { ok: false, conflict: true, error: eph.saveError };
      }
      eph.saveState = "offline";
      eph.saveError = String(err?.message || err);
      return { ok: false, error: eph.saveError };
    } finally {
      notify();
    }
  }

  function schedulePersist(autosave) {
    if (disposed) return;
    persistPending = true;
    debounce("persist", 200, () => { persistPending = false; persist?.(JSON.stringify(state)); });
    if (autosave) {
      // a folder conflict pauses autosaving until it is resolved (or the folder changes)
      if (eph.saveState === "conflict" && eph.conflict?.slug === state.slug) return;
      eph.saveState = "pending";
      autosavePending = true;
      debounce("autosave", 4000, () => autosaveNow());
    }
  }

  async function requestPlan() {
    if (disposed) return;
    const seq = ++planSeq;
    try {
      const plan = await rw.plan(state);
      if (seq !== planSeq || disposed) return;
      eph.plan = plan;
      eph.backend = "online";
    } catch (err) {
      if (seq !== planSeq || disposed) return;
      eph.backend = "offline";
      eph.planError = String(err.message || err);
    }
    notify();
  }

  function schedulePlan() {
    if (disposed) return;
    debounce("plan", 450, requestPlan);
  }

  // the view (tab, zoom, snap, ripple, playhead, selection) is not part of the history: a restored state keeps
  // the current view; the selection falls back to the restored state's own when its scene is gone
  function restore(json) {
    const next = JSON.parse(json);
    const view = state?.ui && typeof state.ui === "object" ? structuredClone(state.ui) : null;
    if (view && next && typeof next === "object") {
      const own = next.ui?.selected;
      next.ui = { ...(next.ui || {}), ...view };
      const ids = Array.isArray(next.scenes) ? next.scenes.map(s => s?.id) : [];
      if (!ids.includes(next.ui.selected)) next.ui.selected = ids.includes(own) ? own : ids[0] || "";
    }
    state = stampVersion(next);
  }

  function stepBack() {
    const step = undoStack.pop();
    if (!step) return false;
    redoStack.push({ json: JSON.stringify(state), label: step.label, at: step.at });
    restore(step.json);
    return true;
  }

  function stepForward() {
    const step = redoStack.pop();
    if (!step) return false;
    undoStack.push({ json: JSON.stringify(state), label: step.label, at: step.at });
    restore(step.json);
    return true;
  }

  function afterJump() {
    lastCoalesce = { key: null, at: 0 };
    schedulePersist(true);
    schedulePlan();
    notify();
  }

  return {
    get project() { return state; },
    eph,
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    notify,

    // history: record an undo step; coalesce: merge rapid edits with the same key; label: the step's name in the
    // History menu; plan: re-request /plan; render: re-render the view; autosave: save to disk after a while.
    update(mutator, { history = true, coalesce = null, plan = true, render = true, autosave = true, label = "" } = {}) {
      if (disposed) return;
      if (history) {
        const now = Date.now();
        const merge = coalesce && lastCoalesce.key === coalesce && now - lastCoalesce.at < COALESCE_MS;
        if (!merge) {
          undoStack.push({ json: JSON.stringify(state), label: label || "Edit", at: now });
          if (undoStack.length > HISTORY_LIMIT) undoStack.shift();
          redoStack.length = 0;
        }
        lastCoalesce = { key: coalesce, at: now };
      }
      mutator(state);
      stampVersion(state);
      schedulePersist(autosave && history);
      if (plan) schedulePlan();
      if (render) notify();
    },

    setEph(patch, render = true) {
      Object.assign(eph, patch);
      if (render) notify();
    },

    replaceProject(next, { label = "Restore version" } = {}) {
      if (disposed) return;
      undoStack.push({ json: JSON.stringify(state), label, at: Date.now() });
      if (undoStack.length > HISTORY_LIMIT) undoStack.shift();
      redoStack.length = 0;
      state = stampVersion(normalizeProject(withProjectId(next)));
      lastCoalesce = { key: null, at: 0 };
      schedulePersist(true);
      schedulePlan();
      notify();
    },

    undo() {
      if (disposed || !stepBack()) return false;
      afterJump();
      return true;
    },

    redo() {
      if (disposed || !stepForward()) return false;
      afterJump();
      return true;
    },

    canUndo: () => undoStack.length > 0,
    canRedo: () => redoStack.length > 0,

    // oldest first; `done` steps are applied, the others were undone and redo brings them back
    history() {
      return [
        ...undoStack.map((x, i) => ({ k: i, label: x.label, at: x.at, done: true })),
        ...redoStack.slice().reverse().map((x, j) => ({ k: undoStack.length + j, label: x.label, at: x.at, done: false })),
      ];
    },
    // the state right after step k (-1: before the oldest step kept); one persist, plan and render
    jumpTo(k) {
      if (disposed) return false;
      const target = Math.max(0, Math.min(undoStack.length + redoStack.length, Math.round(Number(k)) + 1));
      if (!Number.isFinite(target) || target === undoStack.length) return false;
      while (undoStack.length > target && stepBack()) { /* undo */ }
      while (undoStack.length < target && stepForward()) { /* redo */ }
      afterJump();
      return true;
    },

    refreshPlan: requestPlan,
    flush,

    // writes the widget now and waits for the autosave: {ok} or {ok: false, error, conflict}
    async saveNow(opts) {
      if (disposed) return { ok: false, error: "the editor was closed" };
      flush();
      persist?.(JSON.stringify(state));
      eph.saveState = "pending";
      notify();
      // [OLD 2026-11-03 v0.6.0 review] return autosaveNow(opts);
      return autosaveNow({ ...(opts || {}), explicit: true }); // added 2026-11-03 v0.6.0 review: a save the user asked for
    },

    // External replacement of the widget value (workflow loaded, paste). With {persist: true} the widget gets the
    // normalised project at once (used when the editor itself rewrites the project, e.g. a duplicated node).
    load(json, { persist: write = false } = {}) {
      if (disposed) return;
      state = stampVersion(normalizeProject(withProjectId(json)));
      undoStack.length = 0;
      redoStack.length = 0;
      lastCoalesce = { key: null, at: 0 };
      if (eph.saveState === "conflict") { eph.saveState = "saved"; eph.conflict = null; eph.saveError = ""; }
      if (write) schedulePersist(true);
      schedulePlan();
      notify();
    },

    get disposed() { return disposed; },
    // flushes the widget, sends a pending autosave (the last edit reaches the disk) and stops every timer
    dispose() {
      if (disposed) return;
      flush();
      const sendAutosave = autosavePending;
      for (const k of Object.keys(timers)) clearTimeout(timers[k]);
      planSeq++;
      disposed = true;
      listeners.clear();
      if (sendAutosave) rw.autosave(state).catch(() => {});
    },
  };
}
