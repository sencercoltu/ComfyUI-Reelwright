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

// added 2026-11-02 v0.3.7: ComfyUI paints a sampler's latent preview under the node that is running. For a
// Reelwright node that image is moved into the editor's Render tab instead. This covers previews from any
// source (an older Reelwright backend, or anything else that reports previews for this node).
const editors = new Set(); // {node, editor}
let executingId = null;
let swallowedBlob = null;
function editorFor(id) {
  if (id === null || id === undefined) return null;
  const s = String(id), last = s.split(":").pop();
  for (const x of editors) if (String(x.node.id) === s || String(x.node.id) === last) return x.editor;
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

  nodeCreated(node) {
    if (node.constructor?.comfyClass !== "Reelwright") return;
    installPreviewRedirect(); // added 2026-11-02 v0.3.7
    const projectW = node.widgets?.find(w => w.name === "project");
    const runW = node.widgets?.find(w => w.name === "run_request");
    if (!projectW || !runW) return;
    projectW.hidden = true;
    runW.hidden = true;

    const container = document.createElement("div");
    container.className = "rw-host";
    const host = {
      getProject: () => projectW.value || "",
      setProject(json) {
        projectW.value = json;
        node.graph?.setDirtyCanvas?.(true, false);
      },
      fetchApi: (route, opts) => api.fetchApi(route, opts),
      apiURL: route => api.apiURL(route),
      on: (type, cb) => api.addEventListener(type, e => cb(e.detail)),
      async queue(request) {
        runW.value = JSON.stringify(request);
        try {
          const ok = await app.queuePrompt(0, 1, [String(node.id)]);
          if (ok === false) throw new Error("ComfyUI refused the queue request");
        } finally {
          runW.value = IDLE_REQUEST;
        }
      },
      interrupt: () => api.interrupt(),
      isInputLinked: name => (node.inputs || []).some(i => i.name === name && i.link != null),
      // added 2026-11-02 v0.3.0: Ctrl + wheel over the editor zooms the canvas like it does over empty space
      forwardWheel(e) {
        const canvas = app.canvas?.canvas;
        if (!canvas) return;
        canvas.dispatchEvent(new WheelEvent("wheel", {
          clientX: e.clientX, clientY: e.clientY, screenX: e.screenX, screenY: e.screenY,
          deltaX: e.deltaX, deltaY: e.deltaY, deltaZ: e.deltaZ, deltaMode: e.deltaMode,
          ctrlKey: e.ctrlKey, metaKey: e.metaKey, shiftKey: e.shiftKey, altKey: e.altKey, bubbles: true, cancelable: true,
        }));
      },
      // added 2026-11-02 v0.3.0: render progress in the node title ("Reelwright · rendering 2/5 · 43%")
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
    const entry = { node, editor }; // added 2026-11-02 v0.3.7: for the preview redirect
    editors.add(entry);
    if (!projectW.value) host.setProject(JSON.stringify(editor.project));
    // added 2026-11-02 v0.3.0: a workflow load configures the node right after creating it; a node that is
    // still unconfigured a moment later was just added, so offer the saved Global profiles
    let configured = false;
    setTimeout(() => { if (!configured) editor.startNew?.().catch(() => {}); }, 0);
    if (!runW.value) runW.value = IDLE_REQUEST;
    node.setSize([Math.max(node.size[0], 1600), Math.max(node.size[1], 1000)]);

    const onConfigure = node.onConfigure;
    node.onConfigure = function () {
      configured = true; // added 2026-11-02 v0.3.0
      const r = onConfigure?.apply(this, arguments);
      // added 2026-11-02 v0.3.0: a workflow saved mid-render carries the progress suffix in its title
      if (typeof node.title === "string") node.title = node.title.replace(/ · rendering \d+\/\d+ · \d+%$/, "");
      editor.load(projectW.value);
      return r;
    };
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
      editors.delete(entry); // added 2026-11-02 v0.3.7
      editor.destroy();
      return onRemoved?.apply(this, arguments);
    };
  },
});
