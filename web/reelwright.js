// ComfyUI extension: replaces the Reelwright node's hidden `project` and
// `run_request` widgets with the timeline editor.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { mountEditor } from "./rw/editor.js";

const css = document.createElement("link");
css.rel = "stylesheet";
css.href = new URL("./rw/reelwright.css", import.meta.url).href;
document.head.appendChild(css);

const IDLE_REQUEST = JSON.stringify({ action: "pending" });

// ComfyUI paints a sampler's latent preview under the node that is running. For a
// Reelwright node that image is moved into the editor's Render tab instead. This covers previews from any
// source (an older Reelwright backend, or anything else that reports previews for this node).
const editors = new Set(); // {node, editor}
// With Nodes 2.0, ComfyUI's own undo (Ctrl+Z on the canvas) rebuilds the graph, and Vue
// keeps showing the DOM element of the node it replaced (same id) instead of the new node's. That element was
// emptied when the old node was removed, so the node went blank. The old element is remembered here for a moment,
// and the new editor moves into it while its own element is not on the page.
const orphans = new Map(); // node id -> container of a removed Reelwright node
let editorSeq = 0;

// A node pasted or duplicated from another Reelwright node carries the same project id, folder
// and scene ids, so both would write into one folder. The newer node becomes a separate project (editor.forkProject).
// Only nodes that are in a graph count, on both sides
const inGraph = x => !!x.node.graph && !x.editor.destroyed && !x.detached;
// A node pasted onto the canvas (Ctrl+V, Paste, Clone, Alt-drag, an inserted workflow
// or blueprint: everything that goes through LGraphCanvas._deserializeItems) is always a separate project: new
// project id, folder and scene ids. Otherwise, when an older node in the graph has the same project id, only a shared
// folder makes the newer one a full copy; with a folder of its own it only gets its own project id and keeps its
// folder, scene ids and renders (a copy renamed before v0.6.0). Save As / a workflow opened twice stays one project.
function checkCopy(entry) {
  if (!editors.has(entry) || !inGraph(entry)) return;
  const pj = entry.editor.project;
  const id = pj?.project_id;
  const pasted = entry.pasted;
  entry.pasted = false;
  const live = [...editors].filter(x => x !== entry && inGraph(x));
  const slugs = live.map(x => x.editor.project?.slug).filter(Boolean);
  if (pasted) { entry.editor.forkProject?.(slugs); return; }
  if (!id) return;
  const older = live.filter(x => x.seq < entry.seq);
  if (!older.some(x => x.editor.project?.project_id === id)) return;
  if (older.some(x => x.editor.project?.slug === pj.slug)) entry.editor.forkProject?.(slugs);
  else entry.editor.separateProjectId?.();
}
// Nodes configured while the canvas pastes are copies (checkCopy). ComfyUI's clone of a
// node for the clipboard is made before the paste starts (and never joins a graph), so it is not counted.
let pasteDepth = 0;
function installPasteHook() {
  const C = app.canvas?.constructor || window.LiteGraph?.LGraphCanvas || window.LGraphCanvas;
  const proto = C?.prototype;
  if (!proto || proto.__rwPasteHook || typeof proto._deserializeItems !== "function") return;
  const original = proto._deserializeItems;
  proto._deserializeItems = function (...args) {
    pasteDepth++;
    try { return original.apply(this, args); } finally { pasteDepth--; }
  };
  proto.__rwPasteHook = true;
}
let executingId = null;
let swallowedBlob = null;
// The execution ids of a node: its id in the root graph, or "<instance path>:<id>" for every
// subgraph instance that holds it (ComfyUI's ids for nodes inside subgraphs)
function executionIds(node) {
  const own = String(node.id);
  const g = node.graph;
  const root = app.rootGraph ?? app.graph;
  if (!g || !root || g === root || g.isRootGraph) return [own];
  const out = [];
  const walk = (graph, prefix, depth) => {
    if (!graph || depth > 12) return;
    for (const n of graph._nodes || graph.nodes || []) {
      const sg = n?.subgraph;
      if (!sg) continue;
      const path = prefix ? `${prefix}:${n.id}` : String(n.id);
      if (sg === g) out.push(`${path}:${own}`);
      else walk(sg, path, depth + 1);
    }
  };
  walk(root, "", 0);
  return out.length ? out : [own];
}
const isNode = (node, id) => id !== null && id !== undefined && executionIds(node).includes(String(id));
function editorFor(id) {
  if (id === null || id === undefined) return null;
  for (const x of editors) if (isNode(x.node, id)) return x.editor;
  return null;
}
function installPreviewRedirect() {
  if (api.__rwPreviewRedirect || typeof api.dispatchCustomEvent !== "function") return;
  api.__rwPreviewRedirect = true;
  api.addEventListener("executing", e => {
    const d = e.detail;
    executingId = d && typeof d === "object" ? (d.display_node ?? d.node ?? null) : d;
  });
  const original = api.dispatchCustomEvent.bind(api);
  api.dispatchCustomEvent = function (type, detail) {
    try {
      if (type === "b_preview_with_metadata" && detail?.blob) {
        const ed = editorFor(detail.displayNodeId) || editorFor(detail.nodeId) || editorFor(detail.realNodeId);
        if (ed) { swallowedBlob = detail.blob; ed.showComfyPreview?.(detail.blob); return true; }
      } else if (type === "b_preview" && detail instanceof Blob) {
        if (detail === swallowedBlob) { swallowedBlob = null; return true; } // the same image, sent the old way too
        const ed = editorFor(executingId);
        if (ed) { ed.showComfyPreview?.(detail); return true; }
      }
    } catch (err) {
      console.warn("Reelwright: preview redirect failed", err);
    }
    return original(type, detail);
  };
}

app.registerExtension({
  name: "reelwright.editor",

  setup() { installPasteHook(); },

  nodeCreated(node) {
    if (node.constructor?.comfyClass !== "Reelwright") return;
    installPreviewRedirect();
    installPasteHook();
    const projectW = node.widgets?.find(w => w.name === "project");
    const runW = node.widgets?.find(w => w.name === "run_request");
    if (!projectW || !runW) return;
    projectW.hidden = true;
    runW.hidden = true;

    const container = document.createElement("div");
    container.className = "rw-host";
    let queueChain = Promise.resolve();
    let serializing = 0, removing = false;
    let entry = null;
    const host = {
      getProject: () => projectW.value || "",
      setProject(json) {
        if (entry?.detached) return;
        projectW.value = json;
        node.graph?.setDirtyCanvas?.(true, false);
      },
      fetchApi: (route, opts) => api.fetchApi(route, opts),
      apiURL: route => api.apiURL(route),
      // Returns a function that removes the listener (editor.destroy() calls it)
      on(type, cb) {
        const fn = e => cb(e.detail);
        api.addEventListener(type, fn);
        return () => api.removeEventListener(type, fn);
      },
      queue(request) {
        const run = queueChain.then(async () => {
          runW.value = JSON.stringify(request);
          try {
            const ok = await app.queuePrompt(0, 1, [executionIds(node)[0]]);
            if (ok === false) throw new Error("ComfyUI refused the queue request");
          } finally {
            runW.value = IDLE_REQUEST;
          }
        });
        queueChain = run.catch(() => {});
        return run;
      },
      // The editor wrote the widget; ComfyUI's ChangeTracker records it now (marks the
      // workflow modified, keeps it in workflow undo and in the state a workflow switch restores)
      changed() {
        if (removing) return;
        if (serializing) { setTimeout(() => host.changed(), 0); return; }
        const ct = app.extensionManager?.workflow?.activeWorkflow?.changeTracker;
        const fn = ct?.captureCanvasState ?? ct?.checkState;
        if (typeof fn === "function") fn.call(ct);
      },
      isOwnNode: id => isNode(node, id),
      otherSlugs: () => [...editors].filter(x => x.node !== node).map(x => x.editor.project?.slug).filter(Boolean),
      interrupt: () => api.interrupt(),
      isInputLinked: name => (node.inputs || []).some(i => i.name === name && i.link != null),
      // Ctrl + wheel over the editor zooms the canvas like it does over empty space
      forwardWheel(e) {
        const canvas = app.canvas?.canvas;
        if (!canvas) return;
        canvas.dispatchEvent(new WheelEvent("wheel", {
          clientX: e.clientX, clientY: e.clientY, screenX: e.screenX, screenY: e.screenY,
          deltaX: e.deltaX, deltaY: e.deltaY, deltaZ: e.deltaZ, deltaMode: e.deltaMode,
          ctrlKey: e.ctrlKey, metaKey: e.metaKey, shiftKey: e.shiftKey, altKey: e.altKey, bubbles: true, cancelable: true,
        }));
      },
      // Render progress in the node title ("Reelwright · rendering 2/5 · 43%")
      setTitle(status) {
        if (baseTitle === null) baseTitle = node.title;
        node.title = status ? `${baseTitle} · ${status}` : baseTitle;
        if (!status) baseTitle = null;
        node.setDirtyCanvas?.(true, true);
      },
    };
    let baseTitle = null;

    const widget = node.addDOMWidget("reelwright_editor", "reelwright", container, {
      hideOnZoom: false,
      getMinHeight: () => 640,
      getValue: () => "",
      setValue: () => {},
    });
    widget.serialize = false;

    const editor = mountEditor(container, host);
    entry = { node, editor, seq: ++editorSeq, detached: false };
    editors.add(entry);
    const editorRoot = container.firstElementChild;
    const keepShown = setInterval(() => {
      if (!editorRoot || editorRoot.isConnected) return;
      if (container.isConnected) { container.appendChild(editorRoot); return; }
      const old = orphans.get(String(node.id));
      if (old && old !== container && old.isConnected) {
        old.replaceChildren(editorRoot);
      }
    }, 250);
    setTimeout(() => {
      if (node.graph || editor.destroyed) return;
      entry.detached = true;
      editors.delete(entry);
      clearInterval(keepShown);
      removing = true;
      editor.destroy();
    }, 5000);
    if (!projectW.value) host.setProject(JSON.stringify(editor.project));
    let configured = false;
    setTimeout(() => { if (!configured) editor.startNew?.().catch(() => {}); }, 0);
    if (!runW.value) runW.value = IDLE_REQUEST;
    node.setSize([Math.max(node.size[0], 1600), Math.max(node.size[1], 1000)]);

    const onConfigure = node.onConfigure;
    node.onConfigure = function () {
      configured = true;
      const r = onConfigure?.apply(this, arguments);
      if (typeof node.title === "string") node.title = node.title.replace(/ · rendering \d+\/\d+ · \d+%$/, "");
      editor.load(projectW.value);
      if (pasteDepth > 0 && entry) entry.pasted = true;
      setTimeout(() => checkCopy(entry), 0);
      return r;
    };
    const onSerialize = node.onSerialize;
    node.onSerialize = function (o) {
      const r = onSerialize?.apply(this, arguments);
      serializing++;
      try {
        if (editor.flush?.() && o) {
          const i = (node.widgets || []).filter(w => w.serialize !== false).indexOf(projectW);
          if (Array.isArray(o.widgets_values) && i >= 0) o.widgets_values[i] = projectW.value;
          if (o.widgets_values_named && "project" in o.widgets_values_named) o.widgets_values_named.project = projectW.value;
        }
      } catch (err) {
        console.warn("Reelwright: could not write the latest edit into the workflow", err);
      } finally {
        serializing--;
      }
      return r;
    };
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
      editors.delete(entry);
      clearInterval(keepShown);
      const id = String(node.id), shown = editorRoot?.parentElement || container;
      removing = true;
      editor.destroy();
      orphans.set(id, shown);
      setTimeout(() => { if (orphans.get(id) === shown) orphans.delete(id); }, 10000);
      return onRemoved?.apply(this, arguments);
    };
  },
});
