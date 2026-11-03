// added 2026-11-03 v0.4.0: Files tab. Everything Reelwright wrote to disk, for every project, as a tree with sizes:
// takes (and their intermediate pass videos), merged cuts, autosaved versions, cast training sets and the
// project's assets. Pick what to delete; the backend (reelwright/files.py) checks every id again.
import { h, icon, button, segmented, section, confirmDialog } from "../ui.js";
import { rw, viewURL } from "../api.js";

export function fmtBytes(n) {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i === 0 ? n : n >= 100 ? Math.round(n) : n.toFixed(1)) + " " + u[i];
}
const fmtWhen = ts => {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short" }) + " " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
};

const ICON = { project: "clapper", group: "folder", scene: "scene", take: "film", passes: "folder", cut: "cut", version: "sheet", asset: "image", dir: "folder", file: "file" };
const FLAG = {
  current: ["open", "accent"], starred: ["★ starred", "ok"], orphan: ["not in the project", "warn"], unused: ["unused", "warn"],
  unlisted: ["not in the take list", "warn"], newest: ["newest", "ok"], unfinished: ["unfinished", "warn"],
  linked: ["hard link", "dim"], intermediate: ["intermediate", "dim"], used: ["used", "ok"],
};

// Index of the scanned tree: id → node and id → parent id. Rebuilt whenever a new scan arrives.
const indexes = new WeakMap();
function indexOf(data) {
  let ix = indexes.get(data);
  if (ix) return ix;
  ix = { node: new Map(), parent: new Map(), project: new Map() };
  const walk = (n, parent, proj) => {
    ix.node.set(n.id, n);
    ix.parent.set(n.id, parent);
    ix.project.set(n.id, proj);
    for (const c of n.children || []) walk(c, n.id, proj);
  };
  for (const p of data.projects || []) walk(p, null, p.slug);
  indexes.set(data, ix);
  return ix;
}
const hasDeletable = n => n.del || (n.children || []).some(hasDeletable);

function selection(ctx) {
  if (!ctx.eph.filesSel) ctx.eph.filesSel = {};
  return ctx.eph.filesSel;
}
function coveredBy(ix, sel, id) {
  for (let p = ix.parent.get(id); p; p = ix.parent.get(p)) if (sel[p]) return p;
  return null;
}
function state(ix, sel, n) {
  if (sel[n.id] || coveredBy(ix, sel, n.id)) return "on";
  const kids = (n.children || []).filter(hasDeletable);
  if (!kids.length) return "off";
  const st = kids.map(c => state(ix, sel, c));
  if (!n.del && st.every(x => x === "on")) return "on";
  return st.some(x => x !== "off") ? "mixed" : "off";
}
function clearBelow(sel, n) {
  for (const c of n.children || []) { delete sel[c.id]; clearBelow(sel, c); }
}
function selectOn(ix, sel, n) {
  if (n.del) { clearBelow(sel, n); sel[n.id] = true; return; }
  for (const c of (n.children || []).filter(hasDeletable)) if (state(ix, sel, c) !== "on") selectOn(ix, sel, c);
}
function toggle(ctx, ix, n) {
  const sel = selection(ctx);
  if (state(ix, sel, n) === "on") {
    if (sel[n.id]) delete sel[n.id];
    else clearBelow(sel, n);
  } else selectOn(ix, sel, n);
  ctx.store.notify();
}

function blocked(ctx, ix, n) {
  // nothing of the open project is deleted while it renders
  return ctx.eph.running && ix.project.get(n.id) === ctx.p.slug;
}

export const refresh = ctx => load(ctx);

async function load(ctx) {
  if (ctx.eph.filesLoading) return;
  ctx.store.setEph({ filesLoading: true });
  try {
    const data = await rw.storage(ctx.p.slug);
    const open = ctx.eph.filesOpen || {};
    if (!ctx.eph.filesOpen) { // first look: the open project and its takes
      const cur = data.projects.find(p => p.flags.includes("current"));
      if (cur) { open[cur.id] = true; const sc = cur.children.find(c => c.id.endsWith("/scenes")); if (sc) open[sc.id] = true; }
    }
    // drop selections of things that are gone
    const ix = indexOf(data);
    const sel = selection(ctx);
    for (const id of Object.keys(sel)) if (!ix.node.has(id)) delete sel[id];
    ctx.store.setEph({ files: data, filesOpen: open, filesError: "", filesLoading: false });
  } catch (err) {
    ctx.store.setEph({ filesError: err.message, filesLoading: false });
  }
}

// assets of the open project whose files are among (or inside) the deleted nodes
function deletedAssets(ix, ids, slug) {
  const out = new Set();
  const walk = n => { for (const a of n.asset_ids || []) out.add(a); for (const c of n.children || []) walk(c); };
  for (const id of ids) if (ix.project.get(id) === slug && ix.node.get(id)) walk(ix.node.get(id));
  return [...out];
}

async function remove(ctx, ids) {
  const data = ctx.eph.files;
  const ix = indexOf(data);
  const nodes = ids.map(id => ix.node.get(id)).filter(Boolean);
  if (!nodes.length) return;
  const slug = ctx.p.slug;
  const total = nodes.reduce((a, n) => a + n.size, 0);
  const notes = [];
  const starred = nodes.filter(n => ix.project.get(n.id) === slug).flatMap(function all(n) { return n.kind === "take" ? [n] : (n.children || []).flatMap(all); })
    .filter(n => n.flags.includes("starred"));
  if (starred.length) notes.push(`${starred.length} starred take${starred.length > 1 ? "s" : ""} of this project: the scene uses its next newest take, or needs rendering again.`);
  const assets = deletedAssets(ix, ids, slug).filter(id => ctx.p.assets.some(a => a.id === id));
  if (assets.length) notes.push(`${assets.length} asset${assets.length > 1 ? "s are" : " is"} in this project; ${assets.length > 1 ? "they are" : "it is"} removed from it too (Ctrl+Z brings the project entries back, not the files).`);
  const projects = nodes.filter(n => n.kind === "project");
  if (projects.length) notes.push(`Whole project${projects.length > 1 ? "s" : ""}: ${projects.map(p => p.label).join(", ")} (output and input folders).`);
  if (nodes.some(function linked(n) { return n.flags.includes("linked") || (n.children || []).some(linked); })) notes.push("Hard-linked files free no space while their other link exists.");
  const one = nodes.length === 1 ? nodes[0] : null;
  if (!(await confirmDialog(ctx.root, {
    title: one ? `Delete “${one.label}” · ${fmtBytes(total)}?` : `Delete ${nodes.length} items · ${fmtBytes(total)}?`,
    confirmLabel: "Delete from disk",
    message: [...notes, "The files are removed for good; there is no undo for them."].join("\n"),
  }))) return;
  try {
    const r = await rw.deleteStorage(ids, slug);
    const sel = selection(ctx);
    for (const id of r.deleted || []) delete sel[id];
    if (assets.length) {
      const gone = new Set(deletedAssets(ix, r.deleted || [], slug));
      ctx.actions.edit(q => {
        q.assets = q.assets.filter(x => !gone.has(x.id));
        for (const s of q.scenes) s.refs = s.refs.filter(x => !gone.has(x.asset));
        for (const c of q.cast) { c.anchors = c.anchors.filter(x => !gone.has(x)); if (gone.has(c.voice)) c.voice = ""; for (const o of c.outfits || []) o.assets = (o.assets || []).filter(x => !gone.has(x)); }
        if (gone.has(q.global.merge.score.asset)) q.global.merge.score.asset = "";
      });
    }
    ctx.actions.toast(`Deleted ${r.removed} item${r.removed === 1 ? "" : "s"} · ${fmtBytes(r.freed)} freed.`, "ok");
    if (r.errors?.length) ctx.actions.toast(`${r.errors.length} not deleted: ${r.errors[0].error}`, "error");
  } catch (err) {
    ctx.actions.toast("Delete failed: " + err.message, "error");
  }
  await load(ctx);
  ctx.actions.refreshTakes();
  ctx.store.refreshPlan();
  // the clicked button is gone after the rescan; keep the editor's shortcuts (Ctrl+Z) working
  if (!ctx.root.contains(document.activeElement)) ctx.root.focus({ preventScroll: true });
}

// quick selections: everything of a kind that is usually safe to let go
const PICKS = [
  { id: "takes", label: "Unstarred takes", test: n => n.kind === "take" && !n.flags.includes("starred") },
  { id: "passes", label: "Pass videos", test: n => n.kind === "passes" },
  { id: "cuts", label: "Older cuts", test: n => (n.kind === "cut" && !n.flags.includes("newest")) || n.flags.includes("unfinished") },
  { id: "versions", label: "Autosaves", test: n => n.kind === "version" },
  { id: "orphans", label: "Not in the project", test: n => n.flags.includes("orphan") || n.flags.includes("unlisted") },
];

function pick(ctx, ix, roots, test) {
  const sel = selection(ctx);
  let n = 0;
  const walk = node => {
    if (node.del && test(node) && !coveredBy(ix, sel, node.id) && !sel[node.id] && !blocked(ctx, ix, node)) { clearBelow(sel, node); sel[node.id] = true; n++; return; }
    for (const c of node.children || []) walk(c);
  };
  roots.forEach(walk);
  ctx.store.notify();
  if (!n) ctx.actions.toast("Nothing more of that kind.", "info");
}

// added 2026-11-03 v0.4.1: preview next to the tree. Pictures, videos, audio and text files (subtitles, timelines,
// project JSON) open in a pane; a take or a cut previews its video. The media element survives re-renders (progress
// events re-render the tab several times a second), so a playing video keeps playing.
const MEDIA = [
  ["image", /\.(png|jpe?g|webp|gif|bmp)$/i], ["video", /\.(mp4|webm|mov|mkv|m4v)$/i],
  ["audio", /\.(wav|mp3|flac|ogg|m4a|aac|opus)$/i], ["text", /\.(json|txt|srt|otio|fcpxml|xml|md|csv|log)$/i],
];
export const mediaKind = name => (MEDIA.find(([, re]) => re.test(name || "")) || [""])[0];
function previewTarget(n) {
  if (!n) return null;
  if (n.view) return n;
  const kids = n.children || [];
  if (n.kind === "take") return kids.find(c => c.view && mediaKind(c.label) === "video" && c.label !== "tail.mp4") || null;
  if (n.kind === "cut") return kids.find(c => mediaKind(c.label) === "video" && !c.flags.includes("unfinished")) || kids.find(c => c.view) || null;
  return null;
}
const panes = new WeakMap(); // ctx -> { key, media }

function previewMedia(ctx, file) {
  const url = viewURL(file.view, file.type);
  const kind = mediaKind(file.label);
  if (kind === "image") return h("img", { class: "rw-fprev-media", src: url, alt: file.label });
  if (kind === "video") return h("video", { class: "rw-fprev-media", src: url, controls: true, preload: "metadata", playsInline: true });
  if (kind === "audio") return h("audio", { class: "rw-fprev-audio", src: url, controls: true, preload: "metadata" });
  if (kind === "text") {
    const pre = h("pre", { class: "rw-fprev-text mono" }, "Loading…");
    fetch(url).then(r => { if (!r.ok) throw new Error(r.status + " " + r.statusText); return r.text(); })
      .then(t => {
        const odd = (t.slice(0, 4000).match(/[\u0000\ufffd]/g) || []).length;
        pre.textContent = odd > 8 ? "This file doesn't look like text." : t.length > 200000 ? t.slice(0, 200000) + "\n… (" + fmtBytes(t.length) + ", first 200 KB shown)" : t;
      })
      .catch(err => { pre.textContent = "Couldn't load the file: " + err.message; });
    return pre;
  }
  return h("div", { class: "rw-empty sm" }, "No preview for this kind of file.");
}

function previewPane(ctx, ix) {
  const id = ctx.eph.filesPreview;
  const n = id && ix.node.get(id);
  const file = previewTarget(n);
  if (!n || !file) { panes.delete(ctx); return null; }
  let cached = panes.get(ctx);
  if (!cached || cached.key !== file.id) { cached = { key: file.id, media: previewMedia(ctx, file) }; panes.set(ctx, cached); }
  const lock = blocked(ctx, ix, n);
  const cover = coveredBy(ix, selection(ctx), n.id);
  return h("div", { class: "rw-fprev", help: "files.preview" },
    h("div", { class: "rw-fprev-head" },
      h("span", { class: "rw-ftree-icon" }, icon(ICON[n.kind] || "file", 13)),
      h("b", { class: "rw-ellipsis grow", title: file.view }, n === file ? n.label : `${n.label} · ${file.label}`),
      button({ icon: "link", small: true, variant: "ghost", help: "files.open", onClick: () => window.open(viewURL(file.view, file.type), "_blank", "noopener") }),
      n.del && !cover ? button({ icon: "trash", small: true, variant: "danger-ghost", help: "files.delete", disabled: lock, onClick: () => remove(ctx, [n.id]) }) : null,
      button({ icon: "close", small: true, variant: "ghost", help: "files.preview.close", onClick: () => ctx.store.setEph({ filesPreview: "" }) })),
    cached.media,
    h("div", { class: "rw-fprev-meta mono rw-dim small" },
      h("div", { class: "rw-ellipsis", title: file.view }, (file.type === "input" ? "input/" : "output/") + file.view),
      h("div", null, [fmtBytes(file.size), fmtWhen(file.mtime)].filter(Boolean).join(" · ")),
      n.note ? h("div", { class: "rw-fprev-note" }, n.note) : null));
}

function row(ctx, ix, n, depth, parentSize) {
  const sel = selection(ctx);
  const open = ctx.eph.filesOpen || {};
  const kids = n.children || [];
  const st = state(ix, sel, n);
  const cover = coveredBy(ix, sel, n.id);
  const lock = blocked(ctx, ix, n);
  const canCheck = !lock && !cover && (n.del || kids.some(hasDeletable));
  const box = h("input", { type: "checkbox", class: "rw-ftree-check", help: "files.check", checked: st === "on", disabled: !canCheck,
    title: lock ? "Rendering: wait until the run ends" : cover ? "Selected with the folder above" : !n.del && !kids.some(hasDeletable) ? n.why || "Kept" : "",
    onClick: e => { e.stopPropagation(); toggle(ctx, ix, n); } });
  box.indeterminate = st === "mixed";
  // a row that can never be selected on its own (a take's video, index.json) gets no box; covered or locked rows keep a disabled one
  const tick = n.del || kids.some(hasDeletable) ? box : h("span", { class: "rw-ftree-check-ph" });
  const expand = () => { ctx.store.setEph({ filesOpen: { ...open, [n.id]: !open[n.id] } }); };
  const target = previewTarget(n); // added 2026-11-03 v0.4.1
  const showPreview = () => ctx.store.setEph({ filesPreview: n.id });
  const pct = parentSize ? Math.max(1, Math.round((n.size / parentSize) * 100)) : 100;
  const out = [h("div", {
    // [OLD 2026-11-03 v0.4.0->v0.4.1] class: ["rw-ftree-row", "k-" + n.kind, st === "on" && "sel", lock && "locked"], dataset: { id: n.id },
    class: ["rw-ftree-row", "k-" + n.kind, st === "on" && "sel", lock && "locked", ctx.eph.filesPreview === n.id && "previewed"], dataset: { id: n.id },
    style: { "--depth": depth },
  },
    tick,
    kids.length ? h("button", { type: "button", class: ["rw-ftree-caret", open[n.id] && "open"], help: "files.expand", "aria-label": open[n.id] ? "Collapse" : "Expand", onClick: e => { e.stopPropagation(); expand(); } }, icon("chevRight", 12))
      : h("span", { class: "rw-ftree-caret" }),
    h("span", { class: "rw-ftree-icon" }, icon(ICON[n.kind] || "file", 13)),
    // [OLD 2026-11-03 v0.4.0->v0.4.1] h("span", { class: "rw-ftree-label", help: "files.kind." + (ICON[n.kind] ? n.kind : "file"), onClick: kids.length ? expand : undefined }, n.label),
    h("span", { class: ["rw-ftree-label", !kids.length && target && "clickable"], help: "files.kind." + (ICON[n.kind] ? n.kind : "file"), onClick: kids.length ? expand : target ? showPreview : undefined }, n.label),
    ...n.flags.filter(f => FLAG[f]).map(f => h("span", { class: ["rw-ftree-flag", FLAG[f][1]], help: "files.flag." + f }, FLAG[f][0])),
    h("span", { class: "rw-ftree-note rw-ellipsis", title: n.note || "" }, n.note || (n.why && !n.del ? "kept: " + n.why : "")),
    h("span", { class: "rw-ftree-bar", help: "files.size" }, h("span", { style: { width: pct + "%" } })),
    h("span", { class: "rw-ftree-size mono", help: "files.size" }, fmtBytes(n.size), n.count > 1 && h("span", { class: "rw-dim" }, ` · ${n.count}`)),
    h("span", { class: "rw-ftree-when mono rw-dim" }, fmtWhen(n.mtime)),
    h("span", { class: "rw-ftree-actions" },
      // [OLD 2026-11-03 v0.4.0->v0.4.1] n.view ? button({ icon: "eye", small: true, variant: "ghost", help: "files.open", onClick: () => window.open(viewURL(n.view, n.type), "_blank", "noopener") }) : null,
      target ? button({ icon: "eye", small: true, variant: ctx.eph.filesPreview === n.id ? "default" : "ghost", help: "files.preview.show", onClick: showPreview }) : null,
      n.del && !cover ? button({ icon: "trash", small: true, variant: "danger-ghost", help: "files.delete", disabled: lock, onClick: () => remove(ctx, [n.id]) }) : null))];
  if (kids.length && open[n.id]) {
    const order = ctx.eph.filesOrder === "size" ? [...kids].sort((a, b) => b.size - a.size) : kids;
    for (const c of order) out.push(...row(ctx, ix, c, depth + 1, n.size));
  }
  return out;
}

export function render(ctx) {
  const data = ctx.eph.files;
  if (data === undefined && !ctx.eph.filesLoading && !ctx.eph.filesError) queueMicrotask(() => load(ctx));
  const scope = ctx.eph.filesScope || "all";
  const ix = data ? indexOf(data) : null;
  const roots = data ? data.projects.filter(p => scope === "all" || p.flags.includes("current")) : [];
  const sel = selection(ctx);
  const picked = ix ? Object.keys(sel).map(id => ix.node.get(id)).filter(Boolean) : [];
  const pickedSize = picked.reduce((a, n) => a + n.size, 0);
  const cur = data?.projects.find(p => p.flags.includes("current"));

  const head = h("div", { class: "rw-files-summary" },
    h("div", { class: "rw-files-stat", help: "files.total" }, h("span", { class: "rw-dim small" }, "All projects"), h("b", { class: "mono" }, data ? fmtBytes(data.size) : "…"), h("span", { class: "rw-dim small" }, data ? `${data.projects.length} project${data.projects.length === 1 ? "" : "s"}` : "")),
    h("div", { class: "rw-files-stat", help: "files.current" }, h("span", { class: "rw-dim small" }, "This project"), h("b", { class: "mono" }, cur ? fmtBytes(cur.size) : "…"), h("span", { class: "rw-dim small" }, cur ? `${cur.count} files` : "")),
    h("div", { class: "rw-files-stat", help: "files.selected" }, h("span", { class: "rw-dim small" }, "Selected"), h("b", { class: ["mono", picked.length && "rw-c-err"] }, fmtBytes(pickedSize)), h("span", { class: "rw-dim small" }, `${picked.length} item${picked.length === 1 ? "" : "s"}`)),
    h("span", { class: "rw-flex" }),
    button({ label: "Clear selection", small: true, variant: "ghost", help: "files.clear", disabled: !picked.length, onClick: () => { ctx.store.setEph({ filesSel: {} }); } }),
    button({ label: picked.length ? `Delete ${picked.length} · ${fmtBytes(pickedSize)}` : "Delete selected", icon: "trash", variant: "danger", help: "files.deleteSelected", disabled: !picked.length,
      onClick: () => remove(ctx, picked.map(n => n.id)) }));

  const tools = h("div", { class: "rw-files-tools" },
    segmented({ small: true, value: scope, help: "files.scope", onChange: v => ctx.store.setEph({ filesScope: v }), options: [
      { value: "all", label: "All projects", help: "files.scope.all" }, { value: "current", label: "This project", help: "files.scope.current" }] }),
    segmented({ small: true, value: ctx.eph.filesOrder || "natural", help: "files.order", onChange: v => ctx.store.setEph({ filesOrder: v }), options: [
      { value: "natural", label: "In order", help: "files.order.natural" }, { value: "size", label: "Largest first", help: "files.order.size" }] }),
    h("span", { class: "rw-sep" }),
    h("span", { class: "rw-dim small", help: "files.pick" }, "Select:"),
    ...PICKS.map(x => button({ label: x.label, small: true, help: "files.pick." + x.id, disabled: !ix, onClick: () => pick(ctx, ix, roots, x.test) })),
    h("span", { class: "rw-flex" }),
    button({ label: "Expand all", small: true, variant: "ghost", help: "files.expandAll", disabled: !ix, onClick: () => {
      const open = { ...(ctx.eph.filesOpen || {}) };
      const walk = n => { if ((n.children || []).length && n.kind !== "take" && n.kind !== "cut" && n.kind !== "passes") { open[n.id] = true; n.children.forEach(walk); } };
      roots.forEach(walk);
      ctx.store.setEph({ filesOpen: open });
    } }),
    button({ label: "Collapse", small: true, variant: "ghost", help: "files.collapseAll", onClick: () => ctx.store.setEph({ filesOpen: {} }) }),
    button({ label: ctx.eph.filesLoading ? "Scanning…" : "Rescan", icon: "refresh", small: true, help: "files.refresh", disabled: ctx.eph.filesLoading, onClick: () => load(ctx) }));

  const body = ctx.eph.filesError ? h("div", { class: "rw-banner warn" }, icon("warn", 14), h("span", null, "Couldn't read the folders: " + ctx.eph.filesError))
    : !data ? h("div", { class: "rw-empty" }, "Scanning Reelwright's folders…")
      : !roots.length ? h("div", { class: "rw-empty" }, "Nothing on disk yet. Takes, cuts and uploaded assets show up here.")
        // [OLD 2026-11-03 v0.4.0->v0.4.1] : h("div", { class: "rw-ftree", dataset: { scroll: "files" }, help: "files.tree" }, roots.flatMap(p => row(ctx, ix, p, 0, data.size)));
        : h("div", { class: "rw-files-main" },
          h("div", { class: "rw-ftree", dataset: { scroll: "files" }, help: "files.tree" }, roots.flatMap(p => row(ctx, ix, p, 0, data.size))),
          previewPane(ctx, ix));

  return h("div", { class: "rw-files-tab" },
    section({
      title: "Files on disk", help: "files.card",
      actions: h("span", { class: "rw-dim small" }, "output/reelwright · input/reelwright"),
      children: [
        ctx.eph.running ? h("div", { class: "rw-banner info" }, icon("render", 14), h("span", null, "A render is running: this project's files can be deleted when it ends.")) : null,
        head, tools, body],
    }));
}
