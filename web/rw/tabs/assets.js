// Assets tab: upload, browse, per-asset defaults, usage, reference budget and
// camera presets.

// [OLD 2026-11-03 v0.5.1->v0.6.0] import { h, icon, button, toggle, segmented, select, text, textarea, dot, section, field, keepChips, confirmInline } from "../ui.js";  (confirmInline is no longer used; deletes go through editor.deleteAsset and its dialog)
import { h, icon, button, toggle, segmented, select, text, textarea, dot, section, field, keepChips } from "../ui.js";
import { kept } from "../ui.js"; // added 2026-11-06 v0.10.0: pictures that survive re-renders
import { foldAll, foldMenu, setFolded, pauseMediaIn } from "../ui.js"; // added 2026-11-12 v0.14.1: groups fold like cards
import { rw, viewURL } from "../api.js";
import { assetMenu } from "./timeline.js"; // added 2026-11-02 v0.3.0
import {
  ASSET_CATEGORIES, ROLES, newId, assignCodes, retentionOptions, assetUsage, assetCastUse, sceneBudget, budgetIssues, findAsset,
  descriptionUses, sceneIndex, // added 2026-11-02 v0.3.4
  assetGroupName, assetTags, // added 2026-11-06 v0.9.0: groups and tags
} from "../model.js";

const KIND_CLASS = { image: "pic", video: "vid", audio: "aud" };

// added 2026-11-02 v0.2.0: one place that turns a backend file record into a project asset
// (used by uploads and by the ComfyUI input/output browser)
function addAsset(ctx, a, fallbackName, fallbackKind) {
  let id = "";
  ctx.actions.edit(p => {
    const kind = a.kind || fallbackKind;
    id = a.id || newId("a");
    p.assets.push({
      id, code: "", kind, name: a.name || fallbackName, file: a.file,
      duration: a.duration || 0, width: a.width || 0, height: a.height || 0, category: a.category || ASSET_CATEGORIES[kind][0],
      defaults: { role: "reference", retention: kind === "audio" ? "reference" : "fully_preserved", keep: [], soundtrack: false }, notes: "",
      description: "",
      group: "", tags: [], // added 2026-11-06 v0.9.0: no group, no tags yet (edits are not normalised)
    });
    assignCodes(p.assets);
  });
  return id;
}

export async function uploadFiles(ctx, files) {
  const list = files.filter(f => /^(image|video|audio)\//.test(f.type) || /\.(png|jpe?g|webp|gif|mp4|mov|webm|mkv|wav|mp3|flac|ogg|m4a)$/i.test(f.name));
  if (!list.length) { ctx.actions.toast("Only image, video and audio files can be used as assets.", "warn"); return; }
  for (const file of list) {
    try {
      const res = await rw.upload(file, ctx.p.slug);
      const a = res.asset || res;
      /* [OLD 2026-11-02 v0.1.0->v0.2.0] moved into addAsset() so the ComfyUI browser shares it
      ctx.actions.edit(p => {
        const kind = a.kind || (file.type.split("/")[0]);
        p.assets.push({
          id: a.id || newId("a"), code: "", kind, name: a.name || file.name.replace(/\.[^.]+$/, ""), file: a.file,
          duration: a.duration || 0, width: a.width || 0, height: a.height || 0, category: a.category || ASSET_CATEGORIES[kind][0],
          defaults: { role: "reference", retention: kind === "audio" ? "reference" : "fully_preserved", keep: [], soundtrack: false }, notes: "",
        });
        assignCodes(p.assets);
      });
      [/OLD] */
      addAsset(ctx, a, file.name.replace(/\.[^.]+$/, ""), file.type.split("/")[0]);
      ctx.actions.toast(`Uploaded ${file.name}.`, "ok");
    } catch (err) {
      ctx.actions.toast(`Upload failed for ${file.name}: ${err.message}`, "error");
    }
  }
}

function thumb(a, cls = "rw-asset-thumb") {
  if (a.kind === "image") return h("img", { class: cls, src: viewURL(a.file, "input"), alt: "", loading: "lazy" });
  if (a.kind === "video") return h("video", { class: cls, src: viewURL(a.file, "input"), muted: true, preload: "metadata", playsinline: true });
  return h("div", { class: cls + " rw-wave" }, Array.from({ length: 28 }, (_, i) => h("span", { style: { height: 20 + Math.abs(Math.sin(i * 1.7 + a.code.length)) * 70 + "%" } })));
}

// [OLD 2026-11-06 v0.8.0->v0.9.0] sections by kind only; no groups, tags or tag filter
// function grid(ctx) {
//   const p = ctx.p;
//   const f = ctx.eph.assetFilter;
//   const q = (ctx.eph.assetQuery || "").toLowerCase();
//   const kinds = f === "all" ? ["image", "video", "audio"] : [f];
//   const fileInput = h("input", { type: "file", multiple: true, accept: "image/*,video/*,audio/*", style: { display: "none" }, onChange: e => uploadFiles(ctx, [...e.target.files]) });
//   const counts = { image: 0, video: 0, audio: 0 };
//   for (const a of p.assets) counts[a.kind]++;
//   const label = { image: "Pictures", video: "Videos", audio: "Audio" };
//   return h("div", { class: "rw-col wide" },
//     h("div", { class: "rw-row" },
//       segmented({ value: f, help: "assets.filter", options: [
//         { value: "all", label: `All ${p.assets.length}` },
//         { value: "image", label: `Pictures ${counts.image}`, icon: "image" },
//         { value: "video", label: `Videos ${counts.video}`, icon: "video" },
//         { value: "audio", label: `Audio ${counts.audio}`, icon: "audio" }],
//       onChange: v => ctx.store.setEph({ assetFilter: v }) }),
//       h("input", { class: "rw-input", style: { width: "220px" }, key: "asset-q", placeholder: "Search name, code, category…", help: "assets.search", value: ctx.eph.assetQuery || "",
//         onInput: e => { ctx.eph.assetQuery = e.target.value; ctx.store.notify(); } }),
//       h("span", { class: "rw-flex" }),
//       // added 2026-11-02 v0.2.0: pick files already in ComfyUI's input or output folders
//       button({ label: "From ComfyUI", icon: "search", variant: ctx.eph.browse ? "accent-ghost" : "default", help: "assets.browse",
//         onClick: () => { if (ctx.eph.browse) ctx.store.setEph({ browse: null }); else openBrowser(ctx); } }),
//       button({ label: "Upload", icon: "upload", variant: "primary", help: "assets.upload", onClick: () => fileInput.click() }), fileInput),
//     ctx.eph.browse && browserCard(ctx),
//     h("div", {
//       class: "rw-dropzone", help: "assets.drop",
//       onDragover: e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); e.currentTarget.classList.add("over"); } },
//       onDragleave: e => e.currentTarget.classList.remove("over"),
//       onDrop: e => { e.preventDefault(); e.currentTarget.classList.remove("over"); uploadFiles(ctx, [...e.dataTransfer.files]); },
//     }, icon("upload", 14), "Drop images, video or audio here. Video and audio references should be 2–15 s."),
//     kinds.map(kind => {
//       const items = p.assets.filter(a => a.kind === kind && (!q || `${a.code} ${a.name} ${a.category} ${a.file}`.toLowerCase().includes(q)));
//       return section({
//         title: label[kind], help: "assets.kind." + kind,
//         actions: h("span", { class: "rw-dim small" }, { image: "identity, places, props, keyframes · up to 9 per pass", video: "motion, camera, edit source · up to 3 per pass", audio: "voice, ambience, music, SFX · up to 3 per pass" }[kind]),
//         children: items.length ? h("div", { class: "rw-asset-grid" }, items.map(a => {
//           const uses = assetUsage(p, a.id).length + assetCastUse(p, a.id).length;
//           return h("button", {
//             type: "button", class: ["rw-asset-card", ctx.eph.selectedAsset === a.id && "on"], help: "assets.card",
//             draggable: "true",
//             onDragstart: e => { e.dataTransfer.setData("application/x-rw-asset", a.id); },
//             onClick: () => ctx.store.setEph({ selectedAsset: a.id }),
//             menu: () => { ctx.store.setEph({ selectedAsset: a.id }); return assetMenu(ctx, a); }, // added 2026-11-02 v0.3.0
//           }, thumb(a),
//           h("span", { class: "rw-asset-meta" },
//             h("span", { class: "rw-row" }, h("b", { class: "mono rw-c-" + KIND_CLASS[kind] }, a.code), h("b", { class: "rw-ellipsis" }, a.name || a.file.split("/").pop())),
//             h("span", { class: "rw-row" }, h("span", { class: "rw-tag" }, a.category || "—"),
//               a.duration ? h("span", { class: "mono rw-dim" }, a.duration.toFixed(1) + " s") : null,
//               h("span", { class: "rw-flex" }), h("span", { class: "rw-dim small" }, uses ? `${uses} use${uses > 1 ? "s" : ""}` : "unused"))));
//         })) : h("div", { class: "rw-empty sm", help: "assets.kind." + kind }, q ? "No matches." : `No ${label[kind].toLowerCase()} yet.`),
//       });
//     }),
//     budgetMatrix(ctx),
//     cameraPresets(ctx));
// }
// [/OLD]

// added 2026-11-06 v0.9.0: the asset list by group (named groups with a description, in their order, then the assets
// in no group) or by kind (as before), filtered by kind, by the search field (code, name, category, file, group, tags)
// and by a tag (the tag row). Cards can be dragged onto a group to move them there.
const KIND_ORDER = ["image", "video", "audio"];
const tagsOf = a => (Array.isArray(a.tags) ? a.tags : []); // an asset added since the last load may have no tags yet
const KIND_LABEL = { image: "Pictures", video: "Videos", audio: "Audio" };
const KIND_NOTE = { image: "identity, places, props, keyframes · up to 9 per pass", video: "motion, camera, edit source · up to 3 per pass", audio: "voice, ambience, music, SFX · up to 3 per pass" };

function grid(ctx) {
  const p = ctx.p;
  const f = ctx.eph.assetFilter;
  const q = (ctx.eph.assetQuery || "").toLowerCase().trim();
  const tag = p.assets.some(a => tagsOf(a).includes(ctx.eph.assetTag)) ? ctx.eph.assetTag : "";
  const view = assetView(ctx);
  const fileInput = h("input", { type: "file", multiple: true, accept: "image/*,video/*,audio/*", style: { display: "none" }, onChange: e => uploadFiles(ctx, [...e.target.files]) });
  const counts = { image: 0, video: 0, audio: 0 };
  for (const a of p.assets) counts[a.kind]++;
  const hay = a => `${a.code} ${a.name} ${a.category} ${a.file} ${assetGroupName(p, a)} ${tagsOf(a).join(" ")}`.toLowerCase();
  const terms = q.split(/\s+/).filter(Boolean);
  const match = a => (f === "all" || a.kind === f) && (!tag || tagsOf(a).includes(tag)) && terms.every(x => hay(a).includes(x));
  return h("div", { class: "rw-col wide" },
    h("div", { class: "rw-row wrap" },
      segmented({ value: f, help: "assets.filter", options: [
        { value: "all", label: `All ${p.assets.length}` },
        { value: "image", label: `Pictures ${counts.image}`, icon: "image" },
        { value: "video", label: `Videos ${counts.video}`, icon: "video" },
        { value: "audio", label: `Audio ${counts.audio}`, icon: "audio" }],
      onChange: v => ctx.store.setEph({ assetFilter: v }) }),
      h("input", { class: "rw-input", style: { width: "220px" }, key: "asset-q", placeholder: "Search name, code, group, tag…", help: "assets.search", value: ctx.eph.assetQuery || "",
        onInput: e => { ctx.eph.assetQuery = e.target.value; ctx.store.notify(); } }),
      segmented({ small: true, value: view, help: "assets.view", key: "asset-view", options: [
        { value: "groups", label: "By group", icon: "folder", help: "assets.view" }, { value: "kinds", label: "By kind", icon: "assets", help: "assets.view" }],
      onChange: v => ctx.store.setEph({ assetView: v }) }),
      button({ label: "Group", icon: "plus", small: true, help: "assets.group.add", key: "asset-group-add", onClick: () => addGroup(ctx) }),
      h("span", { class: "rw-flex" }),
      button({ label: "From ComfyUI", icon: "search", variant: ctx.eph.browse ? "accent-ghost" : "default", help: "assets.browse",
        onClick: () => { if (ctx.eph.browse) ctx.store.setEph({ browse: null }); else openBrowser(ctx); } }),
      button({ label: "Upload", icon: "upload", variant: "primary", help: "assets.upload", onClick: () => fileInput.click() }), fileInput),
    tagRow(ctx, tag),
    ctx.eph.browse && browserCard(ctx),
    h("div", {
      class: "rw-dropzone", help: "assets.drop",
      onDragover: e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); e.currentTarget.classList.add("over"); } },
      onDragleave: e => e.currentTarget.classList.remove("over"),
      onDrop: e => { e.preventDefault(); e.currentTarget.classList.remove("over"); uploadFiles(ctx, [...e.dataTransfer.files]); },
    }, icon("upload", 14), "Drop images, video or audio here. Video and audio references should be 2–15 s."),
    view === "groups" ? groupsView(ctx, match, !!(q || tag || f !== "all")) : kindsView(ctx, match, f, !!(q || tag)),
    budgetMatrix(ctx),
    cameraPresets(ctx));
}

// "groups" or "kinds": the one picked, else by group once the project has groups
function assetView(ctx) {
  const v = ctx.eph.assetView;
  return v === "groups" || v === "kinds" ? v : ctx.p.asset_groups.length ? "groups" : "kinds";
}

// every tag of the project with its count; one click filters by it, a second click clears
function tagRow(ctx, active) {
  const p = ctx.p;
  const counts = new Map();
  for (const a of p.assets) for (const t of tagsOf(a)) counts.set(t, (counts.get(t) || 0) + 1);
  if (!counts.size) return null;
  const tags = [...counts.keys()].sort((x, y) => x.localeCompare(y));
  return h("div", { class: "rw-tag-row", help: "assets.tags.filter" },
    h("span", { class: "rw-dim small" }, icon("tag", 12), " Tags"),
    tags.map(t => h("button", { type: "button", class: ["rw-tag-btn", t === active && "on"], help: "assets.tags.filter", key: "atag-" + t,
      onClick: () => ctx.store.setEph({ assetTag: t === active ? "" : t }) }, "#" + t, h("span", { class: "mono rw-dim" }, " " + counts.get(t)))),
    active && button({ label: "Clear", small: true, variant: "ghost", help: "assets.tags.filter", onClick: () => ctx.store.setEph({ assetTag: "" }) }));
}

function assetCard(ctx, a, { showGroup = false } = {}) {
  // added 2026-11-06 v0.10.0: the card's picture or video is the same element across renders (a video went black)
  const pic = kept(ctx, "acard-" + a.id, a.kind + "|" + a.file, () => thumb(a));
  const p = ctx.p;
  const uses = assetUsage(p, a.id).length + assetCastUse(p, a.id).length;
  const group = showGroup ? assetGroupName(p, a) : "";
  return h("button", {
    type: "button", class: ["rw-asset-card", ctx.eph.selectedAsset === a.id && "on"], help: "assets.card", key: "acard-" + a.id,
    draggable: "true",
    onDragstart: e => { e.dataTransfer.setData("application/x-rw-asset", a.id); e.dataTransfer.effectAllowed = "copyMove"; },
    onClick: () => ctx.store.setEph({ selectedAsset: a.id }),
    menu: () => { ctx.store.setEph({ selectedAsset: a.id }); return assetMenu(ctx, a); },
  // [OLD 2026-11-06 v0.9.0->v0.10.0] }, thumb(a),
  }, pic,
  h("span", { class: "rw-asset-meta" },
    h("span", { class: "rw-row" }, h("b", { class: "mono rw-c-" + KIND_CLASS[a.kind] }, a.code),
      h("b", { class: "rw-ellipsis" }, group ? h("span", { class: "rw-dim rw-asset-grp" }, group + " · ") : null, a.name || a.file.split("/").pop())),
    h("span", { class: "rw-row" }, h("span", { class: "rw-tag" }, a.category || "—"),
      a.duration ? h("span", { class: "mono rw-dim" }, a.duration.toFixed(1) + " s") : null,
      h("span", { class: "rw-flex" }), h("span", { class: "rw-dim small" }, uses ? `${uses} use${uses > 1 ? "s" : ""}` : "unused")),
    tagsOf(a).length ? h("span", { class: "rw-asset-tags" }, tagsOf(a).slice(0, 3).map(t => h("span", { class: "rw-chip-mini" }, "#" + t)),
      tagsOf(a).length > 3 ? h("span", { class: "rw-dim small" }, "+" + (tagsOf(a).length - 3)) : null) : null));
}

// by kind, as before v0.9.0; the cards show their group before the name
function kindsView(ctx, match, f, filtered) {
  const p = ctx.p;
  return (f === "all" ? KIND_ORDER : [f]).map(kind => {
    const items = p.assets.filter(a => a.kind === kind && match(a));
    return section({
      title: KIND_LABEL[kind], help: "assets.kind." + kind,
      actions: h("span", { class: "rw-dim small" }, KIND_NOTE[kind]),
      children: items.length ? h("div", { class: "rw-asset-grid" }, items.map(a => assetCard(ctx, a, { showGroup: true })))
        : h("div", { class: "rw-empty sm", help: "assets.kind." + kind }, filtered ? "No matches." : `No ${KIND_LABEL[kind].toLowerCase()} yet.`),
    });
  });
}

// by group: each group in its order, then "No group"; pictures, videos and audio in that order inside a group
function groupsView(ctx, match, filtered) {
  const p = ctx.p;
  const byKind = list => KIND_ORDER.flatMap(k => list.filter(a => a.kind === k));
  const out = p.asset_groups.map((g, i) => {
    const all = p.assets.filter(a => (a.group || "") === g.id);
    return groupSection(ctx, g, i, byKind(all.filter(match)), all.length, filtered);
  });
  const loose = p.assets.filter(a => !a.group);
  if (loose.length || !p.asset_groups.length) out.push(groupSection(ctx, null, -1, byKind(loose.filter(match)), loose.length, filtered));
  return out;
}

function groupSection(ctx, g, i, items, total, filtered) {
  const p = ctx.p;
  const id = g ? g.id : "";
  // [OLD 2026-11-12 v0.14.0->v0.14.1] const closedMap = ctx.eph.assetGroupsClosed || {};
  // [OLD 2026-11-12 v0.14.0->v0.14.1] const closed = !!closedMap[id || "-"];
  // added 2026-11-12 v0.14.1: a group folds like every card: project.ui.collapsed["agroup:<id>"] (kept with the
  // project, no undo step), with the cards' right-click menu and Alt+click (fold or open everything on the tab)
  const foldId = "agroup:" + (id || "-");
  const closed = !!p.ui?.collapsed?.[foldId];
  const flip = e => {
    e.stopPropagation();
    if (e.altKey) { foldAll(ctx, e.currentTarget, !closed); return; }
    if (!closed) pauseMediaIn([e.currentTarget.closest(".rw-card")]);
    setFolded(ctx, [foldId], !closed);
  };
  const editing = !!g && ctx.eph.editGroup === g.id;
  const name = g ? (g.name.trim() || "Unnamed group") : "No group";
  const editG = (fn, label) => ctx.actions.edit(q => { const x = q.asset_groups.find(y => y.id === id); if (x) fn(x, q); }, { label });
  const drop = e => {
    const aid = e.dataTransfer.getData("application/x-rw-asset");
    e.preventDefault();
    e.currentTarget.classList.remove("over");
    const a = findAsset(p, aid);
    if (!a || a.group === id) return;
    ctx.actions.edit(q => { const x = q.assets.find(y => y.id === aid); if (x) x.group = id; }, { label: `Move ${a.code} to ${g ? name : "no group"}` });
  };
  return h("section", {
    // [OLD 2026-11-12 v0.14.0->v0.14.1] class: ["rw-card", "rw-agroup", !g && "loose", closed && "closed"], key: "agroup-" + (id || "-"), help: g ? "assets.group" : "assets.group.none",
    class: ["rw-card", "rw-agroup", !g && "loose", closed && "closed", closed && "folded"], key: "agroup-" + (id || "-"), help: g ? "assets.group" : "assets.group.none", dataset: { fold: foldId }, // added 2026-11-12 v0.14.1
    onDragover: e => { if (e.dataTransfer.types.includes("application/x-rw-asset")) { e.preventDefault(); e.dataTransfer.dropEffect = "move"; e.currentTarget.classList.add("over"); } },
    onDragleave: e => { if (!e.currentTarget.contains(e.relatedTarget)) e.currentTarget.classList.remove("over"); },
    onDrop: drop,
  },
  /* [OLD 2026-11-12 v0.14.0->v0.14.1] the group's fold was kept for the session only; no menu, no Alt+click
  h("div", { class: "rw-card-head" },
    h("button", { type: "button", class: "rw-agroup-caret", help: "assets.group.collapse", key: "agroup-caret-" + (id || "-"), "aria-expanded": closed ? "false" : "true",
      onClick: () => ctx.store.setEph({ assetGroupsClosed: { ...closedMap, [id || "-"]: !closed } }) }, icon(closed ? "chevRight" : "chevDown", 12)),
    h("span", { class: g ? "rw-c-accent" : "rw-dim" }, icon("folder", 13)),
    h("span", { class: "rw-card-title" }, name),
  [/OLD] */
  // added 2026-11-12 v0.14.1
  h("div", { class: "rw-card-head", menu: e => foldMenu(ctx, foldId, closed, e.target.closest(".rw-card"), "group") },
    h("button", { type: "button", class: "rw-agroup-caret", help: "assets.group.collapse", key: "agroup-caret-" + (id || "-"), "aria-expanded": closed ? "false" : "true",
      onClick: flip }, icon(closed ? "chevRight" : "chevDown", 12)),
    h("span", { class: g ? "rw-c-accent" : "rw-dim" }, icon("folder", 13)),
    h("span", { class: "rw-card-title clickable", onClick: flip }, name),
    h("span", { class: "mono rw-dim small" }, filtered && items.length !== total ? `${items.length} of ${total}` : String(total)),
    g && g.description && !editing ? h("span", { class: "rw-dim small rw-ellipsis rw-agroup-desc", title: g.description }, g.description) : null,
    h("span", { class: "rw-flex" }),
    g && button({ label: editing ? "Done" : "Edit", small: true, variant: editing ? "primary" : "ghost", help: "assets.group.edit", key: "agroup-edit-" + id,
      onClick: () => ctx.store.setEph({ editGroup: editing ? "" : id }) }),
    g && button({ label: "↑", small: true, variant: "ghost", help: "assets.group.move", ariaLabel: "Move group up", disabled: i === 0, key: "agroup-up-" + id,
      onClick: () => moveGroup(ctx, id, -1) }),
    g && button({ label: "↓", small: true, variant: "ghost", help: "assets.group.move", ariaLabel: "Move group down", disabled: i === p.asset_groups.length - 1, key: "agroup-down-" + id,
      onClick: () => moveGroup(ctx, id, 1) }),
    g && button({ icon: "trash", small: true, variant: "danger-ghost", help: "assets.group.delete", key: "agroup-del-" + id, onClick: () => deleteGroup(ctx, g) })),
  editing && h("div", { class: "rw-agroup-edit" },
    // stored as typed (one undo step per field while typing) without redrawing, so "Done" is never moved from under the pointer
    field("Name", text({ value: g.name, key: "agroup-name-" + id, help: "assets.group.name", placeholder: "e.g. Harbor set",
      onInput: v => ctx.actions.edit(q => { const x = q.asset_groups.find(y => y.id === id); if (x) x.name = v; }, { label: "Group name", coalesce: "agroup-name-" + id, render: false }),
      onChange: () => ctx.store.notify() }), { help: "assets.group.name" }),
    textarea({ value: g.description, rows: 2, key: "agroup-desc-" + id, help: "assets.group.description", placeholder: "What belongs here, e.g. night exteriors of the harbor: pier, lamps, boats",
      onInput: v => ctx.actions.edit(q => { const x = q.asset_groups.find(y => y.id === id); if (x) x.description = v; }, { label: "Group description", coalesce: "agroup-desc-" + id, render: false }),
      onChange: () => ctx.store.notify() })),
  closed ? null : items.length ? h("div", { class: "rw-asset-grid" }, items.map(a => assetCard(ctx, a)))
    : h("div", { class: "rw-empty sm", help: g ? "assets.group" : "assets.group.none" },
      filtered && total ? "No matches in this group." : g ? "Empty: drag assets here, or pick this group in an asset's settings." : "Every asset is in a group."));
}

// added 2026-11-06 v0.9.0: group actions; each is one undo step
export function addGroup(ctx, name = "New group", assetId = "") {
  const id = newId("g");
  ctx.actions.edit(q => {
    q.asset_groups.push({ id, name, description: "" });
    if (assetId) { const a = q.assets.find(x => x.id === assetId); if (a) a.group = id; }
  }, { label: `New group ${name}` });
  ctx.store.setEph({ editGroup: assetId ? "" : id, assetView: "groups" });
  return id;
}

function moveGroup(ctx, id, by) {
  ctx.actions.edit(q => {
    const i = q.asset_groups.findIndex(g => g.id === id);
    const j = i + by;
    if (i < 0 || j < 0 || j >= q.asset_groups.length) return;
    const [g] = q.asset_groups.splice(i, 1);
    q.asset_groups.splice(j, 0, g);
  }, { label: "Move group" });
}

function deleteGroup(ctx, g) {
  const n = ctx.p.assets.filter(a => a.group === g.id).length;
  ctx.actions.edit(q => {
    q.asset_groups = q.asset_groups.filter(x => x.id !== g.id);
    for (const a of q.assets) if (a.group === g.id) a.group = "";
  }, { label: `Delete group ${g.name || ""}`.trim() });
  ctx.actions.toast(`Removed the group${g.name ? " " + g.name : ""}${n ? `; its ${n} asset${n === 1 ? " has" : "s have"} no group now` : ""}. Ctrl+Z undoes it.`, "ok");
}


// ---- ComfyUI input/output browser (added 2026-11-02 v0.2.0) ----

const browseTimers = new WeakMap(); // added 2026-11-04 v0.6.1: ctx -> the filter field's pending timer (browserCard)

function openBrowser(ctx, patch = {}) {
  const b = { root: "input", q: "", kind: "all", picked: [], files: null, busy: true, ...(ctx.eph.browse || {}), ...patch };
  ctx.store.setEph({ browse: b });
  const token = (ctx.eph.browseToken || 0) + 1;
  ctx.eph.browseToken = token;
  rw.files(b.root, b.q, b.kind === "all" ? "" : b.kind).then(r => {
    if (ctx.eph.browseToken !== token || !ctx.eph.browse) return;
    ctx.store.setEph({ browse: { ...ctx.eph.browse, files: r.files || [], total: r.total || 0, truncated: !!r.truncated, busy: false, error: "" } });
  }).catch(err => {
    if (ctx.eph.browseToken !== token || !ctx.eph.browse) return;
    ctx.store.setEph({ browse: { ...ctx.eph.browse, files: [], busy: false, error: err.message } });
  });
}

/* [OLD 2026-11-03 v0.5.1->v0.6.0] closing the card while files were being added brought it back as a broken card ({picked, importing} only)
async function importPicked(ctx) {
  const b = ctx.eph.browse;
  let n = 0;
  ctx.store.setEph({ browse: { ...b, importing: true } });
  for (const rel of b.picked) {
    try {
      const r = await rw.importFile(ctx.p.slug, b.root, rel);
      const a = r.asset || r;
      if (b.root === "input" && ctx.p.assets.some(x => x.file === a.file)) continue;
      addAsset(ctx, a, rel.split("/").pop().replace(/\.[^.]+$/, ""), a.kind);
      n++;
    } catch (err) { ctx.actions.toast(`Could not add ${rel}: ${err.message}`, "error"); }
  }
  ctx.store.setEph({ browse: { ...ctx.eph.browse, picked: [], importing: false } });
  ctx.actions.toast(n ? `Added ${n} asset${n > 1 ? "s" : ""} from ComfyUI ${b.root}.` : "Nothing new to add.", n ? "ok" : "info");
}
[/OLD] */
// added 2026-11-03 v0.6.0: the picked files are added even when the card is closed meanwhile; the card is only updated
// while it is still open (the same one), never brought back
async function importPicked(ctx) {
  const b = ctx.eph.browse;
  if (!b || b.importing) return;
  let n = 0;
  const card = { ...b, importing: true };
  ctx.store.setEph({ browse: card });
  for (const rel of b.picked) {
    try {
      const r = await rw.importFile(ctx.p.slug, b.root, rel);
      const a = r.asset || r;
      if (b.root === "input" && ctx.p.assets.some(x => x.file === a.file)) continue;
      addAsset(ctx, a, rel.split("/").pop().replace(/\.[^.]+$/, ""), a.kind);
      n++;
    } catch (err) { ctx.actions.toast(`Could not add ${rel}: ${err.message}`, "error"); }
  }
  const now = ctx.eph.browse;
  if (now && now.root === b.root) ctx.store.setEph({ browse: { ...now, picked: [], importing: false } });
  else if (now) ctx.store.setEph({ browse: { ...now, importing: false } });
  ctx.actions.toast(n ? `Added ${n} asset${n > 1 ? "s" : ""} from ComfyUI ${b.root}.` : "Nothing new to add.", n ? "ok" : "info");
}

function browserCard(ctx) {
  const b = ctx.eph.browse;
  const have = new Set(ctx.p.assets.map(a => a.file));
  const picked = new Set(b.picked);
  // [OLD 2026-11-04 v0.6.0->v0.6.1] let timer = 0;  (now browseTimers, one per editor)
  const shown = (b.files || []).slice(0, 160);
  const tile = f => {
    const used = b.root === "input" && have.has(f.rel);
    const url = viewURL(f.rel, b.root);
    const media = f.kind === "image" ? h("img", { src: url, alt: "", loading: "lazy" })
      : f.kind === "video" ? h("video", { src: url, muted: true, preload: "metadata", playsinline: true })
        : h("span", { class: "rw-browse-aud rw-c-aud" }, icon("audio", 22));
    return h("button", {
      type: "button", class: ["rw-browse-tile", picked.has(f.rel) && "on", used && "used"], title: f.rel, help: used ? "assets.browse.used" : "assets.browse.tile", disabled: used,
      onClick: () => {
        const next = picked.has(f.rel) ? b.picked.filter(x => x !== f.rel) : [...b.picked, f.rel];
        ctx.store.setEph({ browse: { ...ctx.eph.browse, picked: next } });
      },
    }, media, h("span", { class: "rw-browse-name mono rw-ellipsis" }, f.rel.split("/").pop()),
    used ? h("span", { class: "rw-browse-badge" }, "added") : picked.has(f.rel) ? h("span", { class: "rw-browse-badge on" }, icon("check", 11)) : null);
  };
  return section({
    title: "ComfyUI files", help: "assets.browse", cls: "rw-browse",
    actions: [
      h("span", { class: "rw-dim small" }, b.busy ? "loading…" : `${b.total ?? 0} file${b.total === 1 ? "" : "s"}${b.truncated ? " (showing the newest)" : ""}`),
      button({ icon: "close", small: true, variant: "ghost", help: "common.close", onClick: () => ctx.store.setEph({ browse: null }) }),
    ],
    children: [
      h("div", { class: "rw-row wrap" },
        segmented({ small: true, value: b.root, help: "assets.browse.root", options: [
          { value: "input", label: "Input", help: "assets.browse.root" }, { value: "output", label: "Output (generated)", help: "assets.browse.root" }],
        onChange: v => openBrowser(ctx, { root: v, picked: [], files: null, busy: true }) }),
        segmented({ small: true, value: b.kind, help: "assets.browse.kind", options: [
          { value: "all", label: "All" }, { value: "image", label: "Pictures", icon: "image" }, { value: "video", label: "Videos", icon: "video" }, { value: "audio", label: "Audio", icon: "audio" }],
        onChange: v => openBrowser(ctx, { kind: v, busy: true }) }),
        // [OLD 2026-11-04 v0.6.0->v0.6.1] h("input", { class: "rw-input grow", key: "browse-q", placeholder: "Filter by path, e.g. ComfyUI_0 or portraits", help: "assets.browse.search", value: b.q,
        // [OLD 2026-11-04 v0.6.0->v0.6.1]   onInput: e => { const v = e.target.value; clearTimeout(timer); timer = setTimeout(() => openBrowser(ctx, { q: v, busy: true }), 300); } })),
        // (the timer lived in this render: a re-render between two keys left the first one running, and a timer still
        // running when the card was closed opened it again)
        // added 2026-11-04 v0.6.1: one filter timer per editor, and it does nothing once the card is closed
        h("input", { class: "rw-input grow", key: "browse-q", placeholder: "Filter by path, e.g. ComfyUI_0 or portraits", help: "assets.browse.search", value: b.q,
          onInput: e => {
            const v = e.target.value;
            clearTimeout(browseTimers.get(ctx));
            browseTimers.set(ctx, setTimeout(() => { browseTimers.delete(ctx); if (ctx.eph.browse) openBrowser(ctx, { q: v, busy: true }); }, 300));
          } })),
      b.error ? h("div", { class: "rw-note err" }, icon("warn", 12), b.error) : null,
      shown.length ? h("div", { class: "rw-browse-grid", dataset: { scroll: "browse" } }, shown.map(tile))
        : h("div", { class: "rw-empty sm" }, b.busy ? "Reading ComfyUI's " + b.root + " folder…" : "No pictures, videos or audio here" + (b.q ? " match." : ".")),
      h("div", { class: "rw-row" },
        h("span", { class: "rw-dim small" }, b.root === "output" ? "Generated files are linked into this project's input folder." : "Input files are used where they are."),
        h("span", { class: "rw-flex" }),
        b.picked.length ? button({ label: "Clear", small: true, variant: "ghost", help: "assets.browse.clear", onClick: () => ctx.store.setEph({ browse: { ...b, picked: [] } }) }) : null,
        button({ label: b.importing ? "Adding…" : `Add ${b.picked.length || ""} to assets`, icon: "plus", small: true, variant: "primary", help: "assets.browse.add",
          disabled: !b.picked.length || b.importing, onClick: () => importPicked(ctx) })),
    ],
  });
}

// added 2026-11-02 v0.3.4: where this asset's description is used, read live from the project. Scenes build their
// prompts from it every time, so an edit here reaches all of them at once.
function descriptionWhere(ctx, a) {
  const p = ctx.p;
  const uses = descriptionUses(p, a.id);
  const num = s => String(sceneIndex(p, s.id) + 1).padStart(2, "0");
  const sceneLinks = list => list.map((u, k) => [k ? ", " : "", h("button", { type: "button", class: "link mono", help: "assets.description.scene", onClick: () => ctx.actions.select(u.scene.id, "scene") }, num(u.scene))]);
  const castLink = c => h("button", { type: "button", class: "link", help: "assets.description.cast", onClick: () => { ctx.store.setEph({ selectedCast: c.id }); ctx.actions.setTab("cast"); } }, c.name);
  const refs = uses.filter(u => u.how === "ref"), guides = uses.filter(u => u.how === "guide");
  const rows = [];
  if (refs.length) rows.push(h("div", null, `In the prompt of scene${refs.length > 1 ? "s" : ""} `, sceneLinks(refs), "."));
  for (const u of uses) {
    const own = u.cast?.kind === "character" ? "their own" : "its own";
    if (u.how === "cast") rows.push(h("div", null, castLink(u.cast), `'s subject line in ${u.scenes} scene${u.scenes === 1 ? "" : "s"} (no description of ${own} in the Cast tab).`));
    if (u.how === "castOwn") rows.push(h("div", { class: "rw-dim" }, "Not used for ", castLink(u.cast), `: ${own} description (Cast tab) is used instead.`));
    if (u.how === "castOther") rows.push(h("div", { class: "rw-dim" }, "Not used for ", castLink(u.cast), `: ${u.by.code} is an earlier anchor with a description.`));
    if (u.how === "castNone") rows.push(h("div", { class: "rw-dim" }, castLink(u.cast), "'s subject line will use this once it has text."));
    if (u.how === "outfit") rows.push(h("div", { class: "rw-dim" }, "Outfit picture of ", castLink(u.cast), ": the outfit's name is used, not this text."));
  }
  if (guides.length) rows.push(h("div", { class: "rw-dim" }, "Guide frame in scene ", sceneLinks(guides), ": sent only when the prompt mentions @" + a.code + "."));
  if (!rows.length) rows.push(h("div", { class: "rw-dim" }, "Not used in any scene yet."));
  return h("div", { class: "rw-desc-uses small", help: "assets.description.uses" }, h("b", null, "Used in"), rows);
}

// ---- describe with a vision LLM (added 2026-11-02 v0.2.0) ----

const DESCRIBE_PROMPTS = {
  subject: "Describe the person or character: build, face, hair, clothing and accessories.",
  location: "Describe this place: setting, architecture, materials, lighting and time of day.",
  prop: "Describe the main object: what it is, shape, material, colour and condition.",
  style: "Describe the visual style: medium, palette, lighting, texture and lens look.",
  keyframe: "Describe what is visible in this frame and how it is composed.",
  motion: "Describe the subject and how it moves across these frames.",
  camera: "Describe the camera movement across these frames.",
  edit_source: "Describe what this clip shows.",
};

export async function describeAssets(ctx, ids, prompt, key) {
  ctx.store.setEph({ describe: { key, busy: true } });
  try {
    const r = await rw.describe(ctx.p, ids, prompt);
    // [OLD 2026-11-02 v0.3.1->v0.3.2] ctx.store.setEph({ describe: { key, text: r.text, model: r.model, ms: r.ms } });
    ctx.store.setEph({ describe: { key, text: r.text, model: r.model, ms: r.ms, note: r.note || "" } });
  } catch (err) {
    ctx.store.setEph({ describe: { key, error: err.message } });
  }
}

// prompt box + button + suggestion; `apply(text, mode)` writes the result ("use" or "append")
export function describeBox(ctx, { key, ids, defaultPrompt, apply, help = "assets.describe" }) {
  const prompts = ctx.eph.describePrompts || (ctx.eph.describePrompts = {});
  const d = ctx.eph.describe?.key === key ? ctx.eph.describe : null;
  const prompt = h("input", { class: "rw-input grow", key: "describe-q-" + key, placeholder: defaultPrompt, value: prompts[key] || "", help: help + ".prompt",
    onInput: e => { prompts[key] = e.target.value; },
    onKeydown: e => { if (e.key === "Enter") { e.preventDefault(); describeAssets(ctx, ids, prompts[key] || defaultPrompt, key); } } });
  return h("div", { class: "rw-describe" },
    h("div", { class: "rw-row" }, prompt,
      button({ label: d?.busy ? "Looking…" : "Describe", icon: "wand", small: true, variant: "pink", help, disabled: !!d?.busy || !ids.length,
        onClick: () => describeAssets(ctx, ids, prompts[key] || defaultPrompt, key) })),
    d?.error ? h("div", { class: "rw-note err" }, icon("warn", 12), d.error) : null,
    d?.text ? h("div", { class: "rw-suggest", help: help + ".result" },
      h("div", { class: "rw-suggest-text" }, d.text),
      d.note ? h("div", { class: "rw-dim small" }, d.note) : null, // added 2026-11-02 v0.3.2
      h("div", { class: "rw-row" },
        h("span", { class: "rw-dim small mono rw-ellipsis grow" }, [d.model, d.ms ? d.ms + " ms" : ""].filter(Boolean).join(" · ")),
        button({ label: "Use", small: true, variant: "primary", help: help + ".use", onClick: () => { apply(d.text, "use"); ctx.store.setEph({ describe: null }); } }),
        button({ label: "Append", small: true, help: help + ".append", onClick: () => { apply(d.text, "append"); ctx.store.setEph({ describe: null }); } }),
        button({ label: "Dismiss", small: true, variant: "ghost", help: "common.close", onClick: () => ctx.store.setEph({ describe: null }) }))) : null);
}

function budgetMatrix(ctx) {
  const p = ctx.p;
  const rows = p.scenes.map((s, i) => ({ s, i, b: sceneBudget(p, s) }));
  const warn = rows.filter(r => budgetIssues(r.b).length);
  const cell = (v, over, t) => h("span", { class: ["mono", over && "rw-c-warn"] }, t ?? v);
  return section({
    title: "Reference budget per scene", help: "assets.budget",
    actions: h("span", { class: "rw-dim small" }, "H3 limits per pass: ≤9 pictures · ≤3 videos (≤15 s) · ≤3 audio (≤15 s) · ≤12 files"),
    children: [
      h("div", { class: "rw-table budget" },
        h("span", { class: "th" }, "Scene"), h("span", { class: "th rw-c-pic" }, "Pictures"), h("span", { class: "th rw-c-vid" }, "Videos"),
        h("span", { class: "th rw-c-aud" }, "Audio"), h("span", { class: "th" }, "Files"),
        rows.map(({ s, i, b }) => [
          h("button", { type: "button", class: "td link", help: "assets.budget.row", onClick: () => ctx.actions.select(s.id, "scene") }, `${String(i + 1).padStart(2, "0")} ${s.title}`),
          h("span", { class: "td" }, cell(b.pictures, b.pictures > 9, `${b.pictures} / 9`)),
          h("span", { class: "td" }, cell(b.videos, b.videos > 3 || b.videoSeconds > 15, `${b.videos} · ${b.videoSeconds.toFixed(1)} s`)),
          h("span", { class: "td" }, cell(b.audio, b.audio > 3 || b.audioSeconds > 15, `${b.audio} · ${b.audioSeconds.toFixed(1)} s`)),
          h("span", { class: "td" }, cell(b.files, b.files > 12, `${b.files} / 12`)),
        ])),
      warn.map(r => h("div", { class: "rw-note warn", help: "assets.budget.warn" }, icon("warn", 12),
        `${r.s.title}: ${budgetIssues(r.b).join(", ")}. H3 still runs; quality may drop.`,
        button({ label: "Open scene", small: true, help: "assets.budget.row", onClick: () => ctx.actions.select(r.s.id, "scene") }))),
    ],
  });
}

function cameraPresets(ctx) {
  const p = ctx.p;
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const edit = (id, fn) => ctx.actions.edit(q => { const c = q.camera_presets.find(x => x.id === id); if (c) fn(c); });  (no History menu name)
  const edit = (id, fn) => ctx.actions.edit(q => { const c = q.camera_presets.find(x => x.id === id); if (c) fn(c); }, { label: "Camera preset" }); // added 2026-11-03 v0.6.0: History menu name
  return section({
    title: "Camera presets", help: "assets.camera",
    actions: button({ label: "Preset", icon: "plus", small: true, help: "assets.camera.add", onClick: () => ctx.actions.edit(q => { q.camera_presets.push({ id: newId("k"), name: "New move", text: "" }); }) }),
    children: p.camera_presets.map(c => h("div", { class: "rw-list-row" },
      h("span", { class: "rw-c-cam" }, icon("camera", 14)),
      text({ value: c.name, key: "cam-name-" + c.id, help: "assets.camera.name", width: "160px", onChange: v => edit(c.id, x => { x.name = v; }) }),
      h("input", { class: "rw-input grow", value: c.text, key: "cam-text-" + c.id, help: "assets.camera.text", placeholder: "wording written into shot lines",
        onChange: e => edit(c.id, x => { x.text = e.target.value; }) }),
      button({ icon: "trash", small: true, variant: "ghost", help: "assets.camera.remove", onClick: () => ctx.actions.edit(q => { q.camera_presets = q.camera_presets.filter(x => x.id !== c.id); }) }))),
  });
}

// added 2026-11-03 v0.6.0: the inspector's preview survives re-renders (as the Files tab's does), so a video or sound
// keeps playing while progress events, autosaves or plan refreshes redraw the tab
const previews = new WeakMap(); // ctx -> {key, el}
function assetPreview(ctx, a) {
  const key = `${a.id}|${a.kind}|${a.file}`;
  const cached = previews.get(ctx);
  if (cached?.key === key) return cached.el;
  const el = a.kind === "image" ? h("img", { class: "rw-asset-preview", src: viewURL(a.file, "input"), alt: a.name })
    : a.kind === "video" ? h("video", { class: "rw-asset-preview", src: viewURL(a.file, "input"), controls: true, preload: "metadata" })
      : h("div", { class: "rw-asset-preview aud" }, thumb(a, "rw-asset-wave"), h("audio", { src: viewURL(a.file, "input"), controls: true, preload: "metadata" }));
  previews.set(ctx, { key, el });
  return el;
}

// added 2026-11-06 v0.9.0: the inspector's group picker: a group id, "" (no group), or a typed name (an existing group's
// name, any case, or a new group made with it)
function pickGroup(ctx, a, v) {
  const p = ctx.p;
  if (v === "" || p.asset_groups.some(g => g.id === v)) {
    ctx.actions.edit(q => { const x = q.assets.find(y => y.id === a.id); if (x) x.group = v; }, { label: `Group of ${a.code}` });
    return;
  }
  const name = String(v).trim();
  if (!name) return;
  const same = p.asset_groups.find(g => g.name.trim().toLowerCase() === name.toLowerCase());
  if (same) ctx.actions.edit(q => { const x = q.assets.find(y => y.id === a.id); if (x) x.group = same.id; }, { label: `Group of ${a.code}` });
  else addGroup(ctx, name, a.id);
}

function inspector(ctx) {
  const p = ctx.p;
  const a = findAsset(p, ctx.eph.selectedAsset) || p.assets[0];
  if (!a) return h("div", { class: "rw-col mid" }, section({ title: "Asset", help: "assets.inspector", children: h("div", { class: "rw-empty" }, "Upload an asset to see its settings.") }));
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const edit = fn => ctx.actions.edit(q => { const x = q.assets.find(y => y.id === a.id); if (x) fn(x); });  (no History menu name)
  const edit = fn => ctx.actions.edit(q => { const x = q.assets.find(y => y.id === a.id); if (x) fn(x); }, { label: `Edit ${a.code}` }); // added 2026-11-03 v0.6.0: History menu name
  const usage = assetUsage(p, a.id);
  const castUse = assetCastUse(p, a.id);
  const kc = KIND_CLASS[a.kind];
  /* [OLD 2026-11-03 v0.5.1->v0.6.0] a new element on every re-render: a playing video or sound restarted on each progress event
  const preview = a.kind === "image" ? h("img", { class: "rw-asset-preview", src: viewURL(a.file, "input"), alt: a.name })
    : a.kind === "video" ? h("video", { class: "rw-asset-preview", src: viewURL(a.file, "input"), controls: true, preload: "metadata" })
      : h("div", { class: "rw-asset-preview aud" }, thumb(a, "rw-asset-wave"), h("audio", { src: viewURL(a.file, "input"), controls: true, preload: "metadata" }));
  [/OLD] */
  const preview = assetPreview(ctx, a); // added 2026-11-03 v0.6.0: the same element while the same file is shown
  const card = h("div", { class: "rw-col mid" },
    section({
      title: "Asset", help: "assets.inspector",
      // [OLD 2026-11-02 v0.2.2->v0.3.0] actions: h("span", { class: "mono rw-dim small" }, a.width ? `${a.width}×${a.height}` : "", a.duration ? ` · ${a.duration.toFixed(2)} s` : ""),
      actions: [h("span", { class: "mono rw-dim small" }, a.width ? `${a.width}×${a.height}` : "", a.duration ? ` · ${a.duration.toFixed(2)} s` : ""),
        button({ icon: "trash", small: true, variant: "danger-ghost", help: "assets.delete", onClick: () => ctx.actions.deleteAsset(a.id) })],
      children: [
        preview,
        h("div", { class: "rw-row" }, h("b", { class: "mono rw-c-" + kc, help: "assets.code" }, a.code),
          text({ value: a.name, key: "asset-name-" + a.id, help: "assets.name", onChange: v => edit(x => { x.name = v; }) })),
        h("div", { class: "rw-dim small mono rw-ellipsis", help: "assets.file" }, a.file),
        field("Category", select({ options: ASSET_CATEGORIES[a.kind], value: a.category, help: "assets.category", onChange: v => edit(x => { x.category = v; }) }), { help: "assets.category" }),
        // added 2026-11-06 v0.9.0: its group (type a new name to make one) and tags; both only sort this tab
        field("Group", select({ options: p.asset_groups.map(g => ({ value: g.id, label: g.name.trim() || "Unnamed group" })), value: a.group || "", free: true, placeholder: "No group",
          help: "assets.group.pick", key: "asset-group-" + a.id, onChange: v => pickGroup(ctx, a, v) }), { help: "assets.group.pick" }),
        field("Tags", keepChips({ values: tagsOf(a), help: "assets.tags", placeholder: "+ tag", key: "asset-tags-" + a.id,
          onChange: v => {
            const known = new Map(); // a new tag takes the spelling the project already uses
            for (const x of p.assets) for (const tg of tagsOf(x)) if (!known.has(tg.toLowerCase())) known.set(tg.toLowerCase(), tg);
            edit(x => { x.tags = assetTags(v.map(tg => known.get(String(tg).trim().toLowerCase()) || tg)); });
          } }), { help: "assets.tags", wide: true }),
      ],
    }),
    // added 2026-11-02 v0.2.0: the description becomes this asset's subject line ("<Subject 1> is …")
    a.kind !== "audio" && section({
      title: "Description", help: "assets.description",
      // [OLD 2026-11-02 v0.3.3->v0.3.4] actions: h("span", { class: "rw-dim small" }, "goes into subject_definitions"),
      actions: h("span", { class: "rw-dim small" }, "every scene that uses it, live"),
      children: [
        textarea({ value: a.description || "", rows: 3, key: "asset-desc-" + a.id, help: "assets.description",
          placeholder: a.category === "location" ? "the wooden pier at dusk, wet planks, iron lamps" : "the young woman with long dark hair and a blue cardigan",
          onChange: v => edit(x => { x.description = v.trim(); }) }),
        describeBox(ctx, {
          key: "asset-" + a.id, ids: [a.id], defaultPrompt: DESCRIBE_PROMPTS[a.category] || "Describe the main subject.",
          apply: (t, mode) => edit(x => { x.description = mode === "append" && x.description ? x.description.replace(/[.\s]*$/, "") + "; " + t : t; }),
        }),
        descriptionWhere(ctx, a), // added 2026-11-02 v0.3.4
      ],
    }),
    section({
      title: "Defaults", help: "assets.defaults",
      actions: h("span", { class: "rw-dim small" }, "any scene can override"),
      children: [
        a.kind === "image" && field("Role", segmented({ small: true, value: a.defaults.role, help: "assets.defaults.role",
          // [OLD 2026-11-12 v0.11.0->v0.12.0] options: ROLES.map(r => ({ value: r, label: { reference: "reference", first_frame: "first", last_frame: "last", keyframe: "keyframe" }[r], help: "scene.refs.role" })), onChange: v => edit(x => { x.defaults.role = v; }) }), { help: "assets.defaults.role", wide: true }),
          options: ROLES.map(r => ({ value: r, label: { reference: "reference", first_frame: "first", last_frame: "last", keyframe: "keyframe", pose: "pose" }[r] || r, help: "scene.refs.role" })), onChange: v => edit(x => { x.defaults.role = v; }) }), { help: "assets.defaults.role", wide: true }), // added 2026-11-12 v0.12.0: pose
        field("Retention", h("div", { class: "rw-ret-grid" }, retentionOptions(a.kind).map(r => h("button", {
          type: "button", class: ["rw-ret", a.defaults.retention === r && "on", "rw-ret-" + kc], help: "retention." + r,
          onClick: () => edit(x => { x.defaults.retention = r; }),
        }, r))), { help: "assets.defaults.retention", wide: true }),
        // [OLD 2026-11-03 v0.6.0 review] field("Keep", keepChips({ values: a.defaults.keep, help: "assets.defaults.keep", onChange: v => edit(x => { x.defaults.keep = v; }) }), { help: "assets.defaults.keep", wide: true }),
        field("Keep", keepChips({ values: a.defaults.keep, help: "assets.defaults.keep", key: "asset-keep-" + a.id, onChange: v => edit(x => { x.defaults.keep = v; }) }), { help: "assets.defaults.keep", wide: true }), // added 2026-11-03 v0.6.0 review: key
        a.kind === "video" && field("Soundtrack", toggle({ value: a.defaults.soundtrack, help: "assets.defaults.soundtrack", onChange: v => edit(x => { x.defaults.soundtrack = v; }) }), { help: "assets.defaults.soundtrack" }),
        textarea({ value: a.notes, rows: 2, key: "asset-notes-" + a.id, placeholder: "Notes", help: "assets.notes", onChange: v => edit(x => { x.notes = v; }) }),
      ],
    }),
    section({
      title: `Used in ${usage.length} scene${usage.length === 1 ? "" : "s"}${castUse.length ? ` · ${castUse.length} cast link${castUse.length > 1 ? "s" : ""}` : ""}`, help: "assets.usage",
      actions: [
        button({ label: "Add to current scene", icon: "plus", small: true, help: "assets.addToScene", onClick: () => {
          const s = ctx.scene;
          ctx.actions.editScene(s.id, sc => { sc.refs.push({ id: newId("r"), asset: a.id, role: a.defaults.role, time: 0, retention: "", keep: [], soundtrack: !!a.defaults.soundtrack }); });
          ctx.actions.toast(`Added ${a.code} to ${s.title}.`, "ok");
        } }),
        usage.length > 0 && button({ label: "Push defaults to all", small: true, help: "assets.pushDefaults", onClick: () => ctx.actions.edit(q => {
          for (const s of q.scenes) for (const r of s.refs) if (r.asset === a.id) { r.retention = ""; r.keep = []; r.role = a.defaults.role; }
        }) }),
      ],
      children: [castUse.map(u => h("div", { class: "rw-list-row", help: "assets.usage.cast" },
        h("span", { class: "rw-c-pic" }, icon("cast", 13)),
        h("button", { type: "button", class: "link grow", help: "assets.usage.cast", onClick: () => { ctx.store.setEph({ selectedCast: u.cast.id }); ctx.actions.setTab("cast"); } }, `${u.as === "anchor" ? "Anchor" : "Voice"} of ${u.cast.name}`),
        h("span", { class: "rw-dim small" }, `${u.scenes} scene${u.scenes === 1 ? "" : "s"}`))),
      usage.length ? h("div", { class: "rw-table usage" }, usage.map(u => {
        const over = (u.ref.retention && u.ref.retention !== a.defaults.retention) || u.ref.role !== a.defaults.role;
        return [
          h("button", { type: "button", class: "td link mono", help: "assets.usage.row", onClick: () => ctx.actions.select(u.scene.id, "scene") }, String(u.index + 1).padStart(2, "0")),
          h("span", { class: "td" }, u.scene.title),
          h("span", { class: "td rw-dim" }, u.ref.role === "keyframe" ? `keyframe @ ${u.ref.time.toFixed(2)} s` : u.ref.role),
          h("span", { class: ["td mono", over && "rw-c-accent"] }, u.ref.retention || a.defaults.retention),
          h("span", { class: "td" }, dot(over ? "override" : "global")),
        ];
      })) : !castUse.length && h("div", { class: "rw-empty sm" }, "Not used yet.")],
    }));
  /* [OLD 2026-11-02 v0.2.2->v0.3.0] the confirmation bar appeared at the bottom of a long column, out of sight, so deleting looked broken
  card.append(h("div", { class: "rw-row end" }, button({ label: "Delete asset", icon: "trash", variant: "danger-ghost", help: "assets.delete", onClick: () => {
    confirmInline(card, usage.length ? `Remove ${a.code} and its ${usage.length} reference${usage.length > 1 ? "s" : ""}?` : `Remove ${a.code} from the project?`, () => {
      ctx.actions.edit(q => {
        q.assets = q.assets.filter(x => x.id !== a.id);
        for (const s of q.scenes) s.refs = s.refs.filter(r => r.asset !== a.id);
        for (const c of q.cast) { c.anchors = c.anchors.filter(x => x !== a.id); if (c.voice === a.id) c.voice = ""; }
      });
      ctx.store.setEph({ selectedAsset: "" });
    });
  } })));
  [/OLD] */
  card.append(h("div", { class: "rw-row end" }, button({ label: "Delete asset", icon: "trash", variant: "danger-ghost", help: "assets.delete", onClick: () => ctx.actions.deleteAsset(a.id) })));
  return card;
}

export function render(ctx) {
  return h("div", { class: "rw-cols", dataset: { scroll: "assets-cols" } }, grid(ctx), inspector(ctx));
}
