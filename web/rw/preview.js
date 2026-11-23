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

// The frame of sprite sheet sheet ({frames, cols, frame_width, frame_height, cell_width, cell_height}) to draw at time
// t (seconds), playing at sheet.fps: [index, sx, sy]. A frame sits at the top left of its cell.
export function sheetFrame(sheet, t) {
  const n = Math.max(1, Math.trunc(sheet.frames) || 1), cols = Math.max(1, Math.trunc(sheet.cols) || 1);
  const fps = Number(sheet.fps) > 0 ? Number(sheet.fps) : 6;
  const i = ((Math.floor(t * fps) % n) + n) % n;
  const cw = Number(sheet.cell_width) || sheet.frame_width, ch = Number(sheet.cell_height) || sheet.frame_height;
  return [i, (i % cols) * cw, Math.floor(i / cols) * ch];
}

// captionFor(meta) -> text under the picture; onVisible() is called when the window first has something to show.
// A preview with frames > 1 is a sprite sheet of every latent frame of the pass (render.py preview_sheet), played on a
// canvas; a new sheet keeps the clip's clock, so the clip plays on while the steps refine it. Clicking the picture
// switches between the normal size and the whole width.
export function createPreviewView({ captionFor, onVisible }) {
  const img = h("img", { alt: "" });
  const canvas = h("canvas", { class: "rw-run-preview-anim" });
  const caption = h("figcaption", { class: "mono" });
  const frame = h("div", { class: "rw-run-preview-frame", title: "Click: larger / smaller" }, img, canvas);
  const figure = h("figure", { class: "rw-run-preview", help: "render.preview" }, frame, caption);
  frame.addEventListener("click", () => figure.classList.toggle("large"));
  let shown = null;    // { url, owned, meta, sprite } on screen
  let pending = null;  // { url, owned, kind, size, probe } being decoded
  let warned = false;
  let raf = 0, clock = null;
  // the frame is copied out 1:1 first: scaling straight from the sheet would blend in the edge of the next cell
  const cell = document.createElement("canvas");

  function draw() {
    raf = 0;
    const sheet = shown?.sprite ? shown.meta : null;
    if (!sheet) return;
    const ctx = canvas.getContext("2d"), cctx = cell.getContext("2d");
    const [, sx, sy] = sheetFrame(sheet, (performance.now() - clock) / 1000);
    const fw = sheet.frame_width, fh = sheet.frame_height;
    if (ctx && cctx) {
      if (cell.width !== fw || cell.height !== fh) { cell.width = fw; cell.height = fh; }
      cctx.drawImage(shown.sprite, sx, sy, fw, fh, 0, 0, fw, fh);
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(cell, 0, 0, fw, fh, 0, 0, canvas.width, canvas.height);
    }
    raf = requestAnimationFrame(draw);
  }
  function play() {
    if (clock === null) clock = performance.now();
    if (!raf) raf = requestAnimationFrame(draw);
  }
  function stop() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    clock = null;
  }

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
      const anim = Number(p.frames) > 1 && Number(p.cols) > 0 && Number(p.frame_width) > 0 && Number(p.frame_height) > 0;
      shown = { url: next.url, owned: next.owned, meta: p, sprite: anim ? probe : null };
      figure.classList.toggle("anim", anim);
      if (anim) {
        // twice the frame's pixels, so a Latent2RGB frame (a few dozen pixels) is smoothed rather than blocky
        const k = Math.max(1, Math.min(4, Math.round(480 / Math.max(p.frame_width, p.frame_height))));
        if (canvas.width !== p.frame_width * k || canvas.height !== p.frame_height * k) {
          canvas.width = p.frame_width * k;
          canvas.height = p.frame_height * k;
        }
        frame.style.aspectRatio = `${p.frame_width} / ${p.frame_height}`;
        play();
      } else {
        stop();
        if (probe.naturalWidth && probe.naturalHeight) frame.style.aspectRatio = `${probe.naturalWidth} / ${probe.naturalHeight}`;
      }
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
    stop();
    release(shown);
    shown = null;
    img.removeAttribute("src");
    caption.textContent = "";
    figure.classList.remove("failed", "anim");
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
