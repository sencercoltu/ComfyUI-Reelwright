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

// The picture inside a preview message. VideoHelperSuite's animated latent previews send
// each frame as a normal preview message with 24 bytes of their own (frame index, node id) before the JPEG; shown as
// is, that is "a render preview could not be decoded". Any bytes before a JPEG, PNG or WebP signature are dropped.
const SIGNATURES = [[0xff, 0xd8, 0xff], [0x89, 0x50, 0x4e, 0x47], [0x52, 0x49, 0x46, 0x46]];
export async function imageBlob(blob) {
  const head = new Uint8Array(await blob.slice(0, 64).arrayBuffer());
  const at = i => SIGNATURES.some(sig => sig.every((b, k) => head[i + k] === b));
  if (at(0)) return blob;
  for (let i = 1; i < head.length - 3; i++) if (at(i)) return blob.slice(i, blob.size, blob.type);
  return blob; // no image signature: let the decoder report it
}
const hexHead = async blob => [...new Uint8Array(await blob.slice(0, 12).arrayBuffer())].map(b => b.toString(16).padStart(2, "0")).join(" ");

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
        const say = head => console.warn(`Reelwright: a render preview could not be decoded (${bad.kind}, ${bad.size} bytes${head ? ", starts " + head : ""}); keeping the last one that worked`);
        if (p.blob instanceof Blob) hexHead(p.blob).then(say, () => say(""));
        else say(typeof p.image === "string" ? JSON.stringify(p.image.slice(0, 30)) : "");
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
