// added 2026-11-02 v0.3.8: the Render tab's latent preview window.
//
// v0.3.5–v0.3.7 rebuilt the <img> on every re-render, set its src straight from the event (a data: URL from the
// backend, or an object URL from ComfyUI's preview stream), revoked the previous object URL as soon as a new one arrived,
// and only re-rendered every 250 ms. A picture that failed to load stayed on screen as a broken-image icon.
//
// Now one <figure> lives as long as the editor and the Render tab moves it into each new banner. A new preview is
// decoded off-screen first and swapped in only once it has loaded, so the window never shows a broken image; the
// previous object URL is released only after its replacement is on screen. Every preview is shown through a blob: URL,
// the backend's base64 JPEG too, the same kind of URL ComfyUI uses for the previews it draws under nodes.
import { h } from "./ui.js";

export function dataUrlToBlob(url) {
  const comma = url.indexOf(",");
  if (!url.startsWith("data:") || comma < 0) throw new Error("not a data: URL");
  const head = url.slice(5, comma);
  const body = url.slice(comma + 1);
  const mime = head.split(";")[0] || "application/octet-stream";
  if (!head.endsWith(";base64")) return new Blob([decodeURIComponent(body)], { type: mime });
  const bin = atob(body);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

// captionFor(meta) -> text under the picture; onVisible() is called when the window first has something to show
export function createPreviewView({ captionFor, onVisible }) {
  const img = h("img", { alt: "" });
  const caption = h("figcaption", { class: "mono" });
  const figure = h("figure", { class: "rw-run-preview", help: "render.preview" }, h("div", { class: "rw-run-preview-frame" }, img), caption);
  let shown = null;    // { url, owned, meta } on screen
  let pending = null;  // { url, owned, kind, size, probe } being decoded
  let warned = false;

  const release = x => { if (x?.owned) URL.revokeObjectURL(x.url); };
  function drop() {
    if (!pending) return;
    pending.probe.onload = pending.probe.onerror = null;
    release(pending);
    pending = null;
  }
  function source(p) {
    if (typeof Blob !== "undefined" && p.blob instanceof Blob) return { url: URL.createObjectURL(p.blob), owned: true, kind: "blob", size: p.blob.size };
    const s = p.image;
    if (typeof s !== "string" || !s) return null;
    if (s.startsWith("data:")) {
      try {
        const b = dataUrlToBlob(s);
        return { url: URL.createObjectURL(b), owned: true, kind: "data", size: b.size };
      } catch { /* not base64: try it as it is */ }
    }
    return { url: s, owned: false, kind: s.slice(0, 5), size: s.length };
  }
  function refresh() { if (shown) caption.textContent = captionFor(shown.meta) || ""; }

  function show(p) {
    const src = p && source(p);
    if (!src) return;
    drop(); // a newer step replaces one that is still decoding
    const probe = new Image();
    pending = { ...src, probe };
    probe.onload = () => {
      if (pending?.probe !== probe) return;
      const next = pending;
      pending = null;
      const prev = shown;
      img.src = next.url; // already decoded, so this is immediate; the old picture stays until it is replaced
      shown = { url: next.url, owned: next.owned, meta: p };
      figure.classList.remove("failed");
      refresh();
      release(prev);
      if (!prev) onVisible?.();
    };
    probe.onerror = () => {
      if (pending?.probe !== probe) return;
      const bad = pending;
      pending = null;
      release(bad);
      if (!warned) {
        warned = true;
        console.warn(`Reelwright: a render preview could not be decoded (${bad.kind}, ${bad.size} bytes); keeping the last one that worked`);
      }
      if (!shown && !figure.classList.contains("failed")) { // nothing to keep: an empty frame and a note
        figure.classList.add("failed");
        caption.textContent = "preview could not be decoded";
        onVisible?.();
      }
    };
    probe.src = src.url;
  }

  function clear() {
    drop();
    release(shown);
    shown = null;
    img.removeAttribute("src");
    caption.textContent = "";
    figure.classList.remove("failed");
  }

  return {
    show,
    clear,
    // the figure for the run banner, or null while there is nothing to show
    element() {
      if (!shown && !figure.classList.contains("failed")) return null;
      refresh();
      return figure;
    },
    get meta() { return shown?.meta || null; },
  };
}
