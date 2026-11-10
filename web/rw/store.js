// Project state with undo/redo, debounced persistence to the node widget and
// the autosave route, and a debounced /plan request for statuses and prompts.

import { rw } from "./api.js";
import { normalizeProject } from "./model.js";

const HISTORY_LIMIT = 150;
const COALESCE_MS = 1200;

// Version stamp for memoised model helpers (see the contract above)
let VERSION_SEQ = 0;
export function stampVersion(p) {
  if (p && typeof p === "object") Object.defineProperty(p, "__rwv", { value: ++VERSION_SEQ, enumerable: false, configurable: true, writable: true });
  return p;
}

// Projects saved before v0.6.0 have no project_id but a stable `id` made once by
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

// Rewritten for named history, view state outside undo, version stamps, flush/dispose,
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
    llmJobs: {},
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

  // One /autosave request at a time. A save asked for while one is on its way (the debounce,
  // Ctrl+S) waits for it and then sends the project as it is by then; several waiting saves become one (the latest
  // state), so an older snapshot never reaches the disk after a newer one. The answer of a request that is no longer
  // the latest (a newer save waits, or edits were made since it left) does not change the footer: the newer one's does.
  let inflight = null; // the request on its way: a promise of its result (never rejects)
  let queued = null; // {force, explicit, waiters}: the save that follows it

  // one autosave request now (or after the one on its way); {ok} or {ok: false, error, conflict}
  function autosaveNow({ force = false, explicit = false } = {}) {
    clearTimeout(timers.autosave);
    autosavePending = false;
    if (inflight) {
      queued ||= { force: false, explicit: false, waiters: [] };
      queued.force ||= !!force;
      queued.explicit ||= !!explicit;
      const q = queued;
      return new Promise(resolve => q.waiters.push(resolve));
    }
    return sendAutosave({ force, explicit });
  }

  function sendAutosave({ force = false, explicit = false }) {
    const slug = state.slug; // the folder this request writes (the project may move on while it runs)
    let request;
    // rw.autosave serialises the project before its first await: the request carries the state of this moment
    try { request = rw.autosave(state, force ? { force: true } : undefined); } catch (err) { request = Promise.reject(err); }
    inflight = request.then(() => null, err => err || new Error("autosave failed")).then(err => settleAutosave(err, { slug, explicit }));
    return inflight;
  }

  function settleAutosave(err, { slug, explicit }) {
    inflight = null;
    if (disposed) return err ? { ok: false, error: String(err?.message || err) } : { ok: true }; // dispose() sends the rest
    const next = queued;
    queued = null;
    const newer = !!next || autosavePending; // this answer is out of date for the footer
    const moved = slug !== state.slug; // the project uses another folder now
    let res;
    if (!err) {
      if (!newer) { eph.saveState = "saved"; eph.saveError = ""; eph.conflict = null; }
      res = { ok: true };
    } else if (isConflict(err)) {
      const other = err.data?.other || {};
      const info = { slug, other };
      const error = `the folder “${slug}” holds another project${other.name ? ` (“${other.name}”)` : ""}`;
      if (!newer && !moved) { eph.saveState = "conflict"; eph.conflict = info; eph.saveError = error; }
      // a save the user asked for gets its dialog; a background one only while it is the latest (the newer request
      // reports the folder itself); never for a folder the project has left
      if (!moved && (explicit || !newer)) {
        try { onConflict?.(info, { explicit }); } catch (e) { console.warn("Reelwright: conflict handler failed", e); }
      }
      res = { ok: false, conflict: true, error };
    } else {
      const error = String(err?.message || err);
      if (!newer) { eph.saveState = "offline"; eph.saveError = error; }
      res = { ok: false, error };
    }
    if (next) sendAutosave(next).then(r => { for (const w of next.waiters) w(r); });
    notify();
    return res;
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
    // A mutator that throws changes nothing when the step has its own undo snapshot (the state,
    // the undo and redo lists go back to how they were); otherwise (coalesced or history: false) its partial change is
    // stamped, saved and shown like any other, so the editor never shows one state while holding another. The error
    // goes on to the caller.
    update(mutator, { history = true, coalesce = null, plan = true, render = true, autosave = true, label = "" } = {}) {
      if (disposed) return;
      let snapshot = null, dropped = null, redoBefore = null;
      const coalesceBefore = lastCoalesce;
      if (history) {
        const now = Date.now();
        const merge = coalesce && lastCoalesce.key === coalesce && now - lastCoalesce.at < COALESCE_MS;
        if (!merge) {
          snapshot = { json: JSON.stringify(state), label: label || "Edit", at: now };
          undoStack.push(snapshot);
          if (undoStack.length > HISTORY_LIMIT) dropped = undoStack.shift();
          redoBefore = redoStack.splice(0);
        }
        lastCoalesce = { key: coalesce, at: now };
      }
      try {
        mutator(state);
      } catch (err) {
        if (snapshot) {
          undoStack.pop();
          if (dropped) undoStack.unshift(dropped);
          redoStack.push(...redoBefore);
          lastCoalesce = coalesceBefore;
          state = stampVersion(JSON.parse(snapshot.json));
          if (render) notify();
        } else {
          stampVersion(state);
          schedulePersist(autosave && history);
          if (plan) schedulePlan();
          if (render) notify();
        }
        throw err;
      }
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
      return autosaveNow({ ...(opts || {}), explicit: true });
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
      const waiting = queued;
      queued = null;
      const sendLast = autosavePending || !!waiting;
      for (const k of Object.keys(timers)) clearTimeout(timers[k]);
      planSeq++;
      disposed = true;
      listeners.clear();
      if (sendLast) {
        const last = state, force = !!waiting?.force;
        const send = () => rw.autosave(last, force ? { force: true } : undefined).then(() => ({ ok: true }), err => ({ ok: false, error: String(err?.message || err) }));
        const done = inflight ? inflight.then(send) : send();
        if (waiting) done.then(r => { for (const w of waiting.waiters) w(r); });
      }
    },
  };
}
