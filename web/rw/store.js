// Project state with undo/redo, debounced persistence to the node widget and
// the autosave route, and a debounced /plan request for statuses and prompts.

import { rw } from "./api.js";
import { normalizeProject } from "./model.js";

const HISTORY_LIMIT = 150;
const COALESCE_MS = 1200;

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
