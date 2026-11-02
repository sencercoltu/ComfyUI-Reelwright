// Assets tab: upload, browse, per-asset defaults, usage, reference budget and
// camera presets.

import { h, icon, button, toggle, segmented, select, text, textarea, dot, section, field, keepChips, confirmInline } from "../ui.js";
import { rw, viewURL } from "../api.js";
import {
  ASSET_CATEGORIES, ROLES, newId, assignCodes, retentionOptions, assetUsage, assetCastUse, sceneBudget, budgetIssues, findAsset,
} from "../model.js";

const KIND_CLASS = { image: "pic", video: "vid", audio: "aud" };

export async function uploadFiles(ctx, files) {
  const list = files.filter(f => /^(image|video|audio)\//.test(f.type) || /\.(png|jpe?g|webp|gif|mp4|mov|webm|mkv|wav|mp3|flac|ogg|m4a)$/i.test(f.name));
  if (!list.length) { ctx.actions.toast("Only image, video and audio files can be used as assets.", "warn"); return; }
  for (const file of list) {
    try {
      const res = await rw.upload(file, ctx.p.slug);
      const a = res.asset || res;
      ctx.actions.edit(p => {
        const kind = a.kind || (file.type.split("/")[0]);
        p.assets.push({
          id: a.id || newId("a"), code: "", kind, name: a.name || file.name.replace(/\.[^.]+$/, ""), file: a.file,
          duration: a.duration || 0, width: a.width || 0, height: a.height || 0, category: a.category || ASSET_CATEGORIES[kind][0],
          defaults: { role: "reference", retention: kind === "audio" ? "reference" : "fully_preserved", keep: [], soundtrack: false }, notes: "",
        });
        assignCodes(p.assets);
      });
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
      button({ label: "Upload", icon: "upload", variant: "primary", help: "assets.upload", onClick: () => fileInput.click() }), fileInput),
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
      actions: h("span", { class: "mono rw-dim small" }, a.width ? `${a.width}×${a.height}` : "", a.duration ? ` · ${a.duration.toFixed(2)} s` : ""),
      children: [
        preview,
        h("div", { class: "rw-row" }, h("b", { class: "mono rw-c-" + kc, help: "assets.code" }, a.code),
          text({ value: a.name, key: "asset-name-" + a.id, help: "assets.name", onChange: v => edit(x => { x.name = v; }) })),
        h("div", { class: "rw-dim small mono rw-ellipsis", help: "assets.file" }, a.file),
        field("Category", select({ options: ASSET_CATEGORIES[a.kind], value: a.category, help: "assets.category", onChange: v => edit(x => { x.category = v; }) }), { help: "assets.category" }),
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
  return card;
}

export function render(ctx) {
  return h("div", { class: "rw-cols", dataset: { scroll: "assets-cols" } }, grid(ctx), inspector(ctx));
}
