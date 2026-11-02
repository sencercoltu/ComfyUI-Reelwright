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

app.registerExtension({
  name: "reelwright.editor",

  nodeCreated(node) {
    if (node.constructor?.comfyClass !== "Reelwright") return;
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
    };

    const widget = node.addDOMWidget("reelwright_editor", "reelwright", container, {
      hideOnZoom: false,
      getMinHeight: () => 640,
      getValue: () => "",
      setValue: () => {},
    });
    widget.serialize = false;

    const editor = mountEditor(container, host);
    if (!projectW.value) host.setProject(JSON.stringify(editor.project));
    if (!runW.value) runW.value = IDLE_REQUEST;
    node.setSize([Math.max(node.size[0], 1600), Math.max(node.size[1], 1000)]);

    const onConfigure = node.onConfigure;
    node.onConfigure = function () {
      const r = onConfigure?.apply(this, arguments);
      editor.load(projectW.value);
      return r;
    };
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
      editor.destroy();
      return onRemoved?.apply(this, arguments);
    };
  },
});
