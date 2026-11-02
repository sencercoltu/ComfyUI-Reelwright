// Assets tab: upload, browse, per-asset defaults, usage, reference budget and
// camera presets.

import { h, icon, button, toggle, segmented, select, text, textarea, dot, section, field, keepChips, confirmInline } from "../ui.js";
import { rw, viewURL } from "../api.js";
import { assetMenu } from "./timeline.js"; // added 2026-11-02 v0.3.0
import {
  ASSET_CATEGORIES, ROLES, newId, assignCodes, retentionOptions, assetUsage, assetCastUse, sceneBudget, budgetIssues, findAsset,
  descriptionUses, sceneIndex, // added 2026-11-02 v0.3.4
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

function grid(ctx) {
  const p = ctx.p;
  const f = ctx.eph.assetFilter;
  const q = (ctx.eph.assetQuery || "").toLowerCase();
  const kinds = f === "all" ? ["image", "video", "audio"] : [f];
  const fileInput = h("input", { type: "file", multiple: true, accept: "image/*,video/*,audio/*", style: { display: "none" }, onChange: e => uploadFiles(ctx, [...e.target.files]) });
  const counts = { image: 0, video: 0, audio: 0 };
  for (const a of p.assets) counts[a.kind]++;
  const label = { image: "Pictures", video: "Videos", audio: "Audio" };
  return h("div", { class: "rw-col wide" },
    h("div", { class: "rw-row" },
      segmented({ value: f, help: "assets.filter", options: [
        { value: "all", label: `All ${p.assets.length}` },
        { value: "image", label: `Pictures ${counts.image}`, icon: "image" },
        { value: "video", label: `Videos ${counts.video}`, icon: "video" },
        { value: "audio", label: `Audio ${counts.audio}`, icon: "audio" }],
      onChange: v => ctx.store.setEph({ assetFilter: v }) }),
      h("input", { class: "rw-input", style: { width: "220px" }, key: "asset-q", placeholder: "Search name, code, category…", help: "assets.search", value: ctx.eph.assetQuery || "",
        onInput: e => { ctx.eph.assetQuery = e.target.value; ctx.store.notify(); } }),
      h("span", { class: "rw-flex" }),
      // added 2026-11-02 v0.2.0: pick files already in ComfyUI's input or output folders
      button({ label: "From ComfyUI", icon: "search", variant: ctx.eph.browse ? "accent-ghost" : "default", help: "assets.browse",
        onClick: () => { if (ctx.eph.browse) ctx.store.setEph({ browse: null }); else openBrowser(ctx); } }),
      button({ label: "Upload", icon: "upload", variant: "primary", help: "assets.upload", onClick: () => fileInput.click() }), fileInput),
    ctx.eph.browse && browserCard(ctx),
    h("div", {
      class: "rw-dropzone", help: "assets.drop",
      onDragover: e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); e.currentTarget.classList.add("over"); } },
      onDragleave: e => e.currentTarget.classList.remove("over"),
      onDrop: e => { e.preventDefault(); e.currentTarget.classList.remove("over"); uploadFiles(ctx, [...e.dataTransfer.files]); },
    }, icon("upload", 14), "Drop images, video or audio here. Video and audio references should be 2–15 s."),
    kinds.map(kind => {
      const items = p.assets.filter(a => a.kind === kind && (!q || `${a.code} ${a.name} ${a.category} ${a.file}`.toLowerCase().includes(q)));
      return section({
        title: label[kind], help: "assets.kind." + kind,
        actions: h("span", { class: "rw-dim small" }, { image: "identity, places, props, keyframes · up to 9 per pass", video: "motion, camera, edit source · up to 3 per pass", audio: "voice, ambience, music, SFX · up to 3 per pass" }[kind]),
        children: items.length ? h("div", { class: "rw-asset-grid" }, items.map(a => {
          const uses = assetUsage(p, a.id).length + assetCastUse(p, a.id).length;
          return h("button", {
            type: "button", class: ["rw-asset-card", ctx.eph.selectedAsset === a.id && "on"], help: "assets.card",
            draggable: "true",
            onDragstart: e => { e.dataTransfer.setData("application/x-rw-asset", a.id); },
            onClick: () => ctx.store.setEph({ selectedAsset: a.id }),
            menu: () => { ctx.store.setEph({ selectedAsset: a.id }); return assetMenu(ctx, a); }, // added 2026-11-02 v0.3.0
          }, thumb(a),
          h("span", { class: "rw-asset-meta" },
            h("span", { class: "rw-row" }, h("b", { class: "mono rw-c-" + KIND_CLASS[kind] }, a.code), h("b", { class: "rw-ellipsis" }, a.name || a.file.split("/").pop())),
            h("span", { class: "rw-row" }, h("span", { class: "rw-tag" }, a.category || "—"),
              a.duration ? h("span", { class: "mono rw-dim" }, a.duration.toFixed(1) + " s") : null,
              h("span", { class: "rw-flex" }), h("span", { class: "rw-dim small" }, uses ? `${uses} use${uses > 1 ? "s" : ""}` : "unused"))));
        })) : h("div", { class: "rw-empty sm", help: "assets.kind." + kind }, q ? "No matches." : `No ${label[kind].toLowerCase()} yet.`),
      });
    }),
    budgetMatrix(ctx),
    cameraPresets(ctx));
}

// ---- ComfyUI input/output browser (added 2026-11-02 v0.2.0) ----

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

function browserCard(ctx) {
  const b = ctx.eph.browse;
  const have = new Set(ctx.p.assets.map(a => a.file));
  const picked = new Set(b.picked);
  let timer = 0;
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
        h("input", { class: "rw-input grow", key: "browse-q", placeholder: "Filter by path, e.g. ComfyUI_0 or portraits", help: "assets.browse.search", value: b.q,
          onInput: e => { const v = e.target.value; clearTimeout(timer); timer = setTimeout(() => openBrowser(ctx, { q: v, busy: true }), 300); } })),
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
  const edit = (id, fn) => ctx.actions.edit(q => { const c = q.camera_presets.find(x => x.id === id); if (c) fn(c); });
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

function inspector(ctx) {
  const p = ctx.p;
  const a = findAsset(p, ctx.eph.selectedAsset) || p.assets[0];
  if (!a) return h("div", { class: "rw-col mid" }, section({ title: "Asset", help: "assets.inspector", children: h("div", { class: "rw-empty" }, "Upload an asset to see its settings.") }));
  const edit = fn => ctx.actions.edit(q => { const x = q.assets.find(y => y.id === a.id); if (x) fn(x); });
  const usage = assetUsage(p, a.id);
  const castUse = assetCastUse(p, a.id);
  const kc = KIND_CLASS[a.kind];
  const preview = a.kind === "image" ? h("img", { class: "rw-asset-preview", src: viewURL(a.file, "input"), alt: a.name })
    : a.kind === "video" ? h("video", { class: "rw-asset-preview", src: viewURL(a.file, "input"), controls: true, preload: "metadata" })
      : h("div", { class: "rw-asset-preview aud" }, thumb(a, "rw-asset-wave"), h("audio", { src: viewURL(a.file, "input"), controls: true, preload: "metadata" }));
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
          options: ROLES.map(r => ({ value: r, label: { reference: "reference", first_frame: "first", last_frame: "last", keyframe: "keyframe" }[r], help: "scene.refs.role" })), onChange: v => edit(x => { x.defaults.role = v; }) }), { help: "assets.defaults.role", wide: true }),
        field("Retention", h("div", { class: "rw-ret-grid" }, retentionOptions(a.kind).map(r => h("button", {
          type: "button", class: ["rw-ret", a.defaults.retention === r && "on", "rw-ret-" + kc], help: "retention." + r,
          onClick: () => edit(x => { x.defaults.retention = r; }),
        }, r))), { help: "assets.defaults.retention", wide: true }),
        field("Keep", keepChips({ values: a.defaults.keep, help: "assets.defaults.keep", onChange: v => edit(x => { x.defaults.keep = v; }) }), { help: "assets.defaults.keep", wide: true }),
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
