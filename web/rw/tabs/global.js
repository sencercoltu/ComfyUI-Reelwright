// Global tab: models, LoRAs, output, sampling, draft, defaults, long scenes,
// LLM settings, script import and the override matrix.

import {
  h, icon, button, toggle, segmented, select, number, text, textarea, section, field, dot, confirmDialog, sortable,
  dragGrip, moveItem, slider, choiceDialog, copyWithToast,
} from "../ui.js";
import { rw } from "../api.js";
import { newJob, jobLine, jobText, outputButton } from "../llmjob.js";
import {
  ASPECTS, START_MODES, STABLE_LANGUAGES, OVERRIDE_KEYS, adaptCanvas, newId, slugify, defaultScene, effective, FPS,
  sceneIndex, overruns, lengthenToFit, nextSeedN, hiresSize, HIRES_SCALES, normalizeProject, defaultProject,
  normalizeGlobal, migrateScore,
} from "../model.js";
import { VERSION } from "../version.js";
import { runWrite, stopWrite } from "../passes.js";
import { withProjectId } from "../store.js";

const DTYPES = ["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"];

function modelRow(ctx, label, key, list, input, help) {
  const g = ctx.p.global.models;
  const wired = input && ctx.host.isInputLinked?.(input);
  return h("div", { class: ["rw-model", wired && "wired"] },
    h("div", { class: "rw-row" }, h("span", { class: "rw-model-label", help }, label), h("span", { class: "rw-flex" }),
      wired ? h("span", { class: "rw-badge pic", help: "global.models.wired" }, "wired input wins") : null),
    select({ options: list || [], value: g[key], placeholder: key === "latent_upscaler" ? "none (Global → Hires needs one)" : undefined, mono: true, help,
      onChange: v => ctx.actions.edit(q => { q.global.models[key] = v; }) }));
}

// Saved Global settings shared by every Reelwright node on this ComfyUI
function profilesCard(ctx) {
  const pr = ctx.eph.profiles;
  if (!pr && !ctx.eph.profilesLoading) {
    ctx.eph.profilesLoading = true;
    Promise.resolve(ctx.actions.loadProfiles()).finally(() => { ctx.eph.profilesLoading = false; });
  }
  const list = pr?.profiles || [];
  const sel = list.find(x => x.id === ctx.eph.profileSel) || null;
  const busy = !!ctx.eph.profileBusy;
  const run = async (fn, okMsg) => {
    ctx.store.setEph({ profileBusy: true });
    try { const r = await fn(); if (r) ctx.store.setEph({ profiles: { profiles: r.profiles, default: r.default } }); if (okMsg) ctx.actions.toast(okMsg, "ok"); return r; }
    catch (err) { ctx.actions.toast("Profiles: " + err.message, "error"); Promise.resolve(ctx.actions.loadProfiles()).catch(() => {}); return null; }
    finally { ctx.store.setEph({ profileBusy: false }); }
  };
  const nameInput = h("input", { class: "rw-input grow", key: "profile-name", placeholder: "New profile name, e.g. RTX 6000 · draft turbo", help: "global.profiles.name", value: ctx.eph.profileName || "",
    onInput: e => { ctx.eph.profileName = e.target.value; } });
  const saveNew = async () => {
    const name = (ctx.eph.profileName || "").trim();
    if (!name) { ctx.actions.toast("Type a name for the new profile.", "warn"); return; }
    const r = await run(() => rw.saveProfile(name, ctx.p.global), `Saved profile “${name}”.`);
    if (r?.profile) { ctx.eph.profileName = ""; ctx.store.setEph({ profileSel: r.profile.id }); }
  };
  return section({
    title: "Profiles", help: "global.profiles",
    actions: h("span", { class: "rw-dim small" }, pr?.offline ? "backend offline" : `${list.length} saved`),
    children: [
      h("div", { class: "rw-row" },
        select({ options: list.map(x => ({ value: x.id, label: x.name + (x.id === pr.default ? " · default for new nodes" : "") })), value: sel?.id || "",
          placeholder: list.length ? "pick a profile" : "no profiles yet", help: "global.profiles.pick", width: "100%", onChange: v => ctx.store.setEph({ profileSel: v }) }),
        button({ label: "Apply", small: true, variant: "primary", help: "global.profiles.apply", disabled: !sel || busy, onClick: async () => {
          if (await confirmDialog(ctx.root, { title: `Apply “${sel.name}”?`, danger: false, confirmLabel: "Apply profile",
            message: "This project's Global settings (models, LoRAs, output, sampling, draft, defaults, long scenes, memory, continuity, LLM and merge) are replaced by the profile. Scenes, assets and cast are not touched. Ctrl+Z undoes this." })) ctx.actions.applyProfile(sel);
        } })),
      sel && h("div", { class: "rw-row wrap" },
        button({ label: "Update with current settings", icon: "refresh", small: true, help: "global.profiles.update", disabled: busy, onClick: async () => {
          if (await confirmDialog(ctx.root, { title: `Overwrite “${sel.name}”?`, danger: false, confirmLabel: "Update profile",
            message: "The profile's saved settings are replaced by this project's current Global settings." })) run(() => rw.saveProfile(sel.name, ctx.p.global, sel.id), `Updated “${sel.name}”.`);
        } }),
        toggle({ value: pr.default === sel.id, label: "Use for new nodes", help: "global.profiles.default", disabled: busy,
          onChange: v => run(() => rw.defaultProfile(v ? sel.id : ""), v ? `New nodes start with “${sel.name}”.` : "New nodes start with the built-in defaults.") }),
        h("span", { class: "rw-flex" }),
        button({ label: "Delete", icon: "trash", small: true, variant: "danger-ghost", help: "global.profiles.delete", disabled: busy, onClick: async () => {
          if (await confirmDialog(ctx.root, { title: `Delete profile “${sel.name}”?`, confirmLabel: "Delete profile",
            message: "Only the saved profile is deleted. Projects that used it keep their settings." })) {
            const r = await run(() => rw.deleteProfile(sel.id), `Deleted “${sel.name}”.`);
            if (r) ctx.store.setEph({ profileSel: "" });
          }
        } })),
      h("div", { class: "rw-row" }, nameInput, button({ label: "Save as new", icon: "plus", small: true, help: "global.profiles.save", disabled: busy, onClick: saveNew })),
    ],
  });
}

// True only when the takes of folder `slug` were read (eph.takesSlug) and it has none; takes
// not read yet (just loaded, backend offline, another folder's list) count as "may have renders"
function folderIsEmpty(ctx, slug) {
  const t = ctx.eph.takes;
  if (!t || ctx.eph.takesSlug !== slug) return false;
  return !Object.values(t.scenes || {}).some(x => (x?.takes || []).length);
}

function projectCard(ctx) {
  const p = ctx.p;
  return section({
    title: "Project", help: "global.project",
    children: [
      field("Name", text({ value: p.name, key: "proj-name", help: "global.project.name", onChange: v => ctx.actions.edit(q => {
        const auto = q.slug === slugify(q.name) || /^untitled-[a-z0-9]{4}$/.test(q.slug);
        q.name = v;
        if (auto && folderIsEmpty(ctx, q.slug)) q.slug = slugify(v);
      }, { label: "Rename project" }) }), { help: "global.project.name" }),
      field("Folder", text({ value: p.slug, key: "proj-slug", mono: true, help: "global.project.slug", onChange: v => ctx.actions.edit(q => { q.slug = slugify(v); }, { label: "Change folder" }) }), { help: "global.project.slug" }),
      h("div", { class: "rw-dim small mono", help: "global.project.slug" }, `output/reelwright/${p.slug}/ · input/reelwright/${p.slug}/`),
      projectIO(ctx),
    ],
  });
}

// The project as a .json file or as text on the clipboard (to keep, to share, to paste
// somewhere), and a project read back from a file or pasted JSON. An import replaces the project in this node; Ctrl+Z
// brings the current one back. Pictures, sounds and renders are files in ComfyUI's input and output folders: the JSON
// names them but does not carry them.
export function projectText(p) {
  return JSON.stringify(p, null, 2);
}
export function exportName(p) {
  return `${p.slug || "project"}.reelwright.json`;
}
function downloadText(name, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = h("a", { href: url, download: name, style: { display: "none" } });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
// {project} or {error}: a project object, or one inside {project: …} (a saved version, a bundle's project file)
export function parseProjectText(text) {
  let j;
  try { j = JSON.parse(String(text || "").trim()); } catch (err) { return { error: "That is not JSON: " + err.message }; }
  if (j && typeof j === "object" && !Array.isArray(j) && !Array.isArray(j.scenes) && j.project && typeof j.project === "object") j = j.project;
  if (!j || typeof j !== "object" || Array.isArray(j) || !Array.isArray(j.scenes)) return { error: "That is not a Reelwright project: it has no list of scenes." };
  return { project: j };
}
export async function importProject(ctx, text, source = "Pasted JSON") {
  const { project, error } = parseProjectText(text);
  if (error) { ctx.actions.toast(error, "error"); return false; }
  let q;
  try { q = normalizeProject(withProjectId(structuredClone(project))); } catch (err) { ctx.actions.toast("Could not read the project: " + err.message, "error"); return false; }
  const cur = ctx.p;
  const n = (x, one, many = one + "s") => `${x} ${x === 1 ? one : many}`;
  const same = q.slug === cur.slug;
  const message = `${source}: “${q.name}”, ${n(q.scenes.length, "scene")}, ${n(q.cast.length, "cast entry", "cast entries")}, ${n(q.assets.length, "asset")}.\n\n`
    + `It replaces the whole project in this node. Ctrl+Z brings “${cur.name}” back.`
    + (same ? "" : `\n\nIts folder is ${q.slug}; this node's is ${cur.slug}. Keep this node's folder to stay with the files and renders here, or use the imported folder to pick up what was rendered for it on this ComfyUI.`)
    + (q.assets.length ? "\n\nAssets are files in ComfyUI's input folder: copy them too when the project comes from another machine." : "");
  const choice = await choiceDialog(ctx.root, {
    title: `Import “${q.name}”?`, message, help: "global.project.import", cancelValue: "cancel", focus: "keep",
    choices: same
      ? [{ value: "cancel", label: "Cancel" }, { value: "keep", label: "Replace this project", variant: "primary", help: "global.project.import.keep" }]
      : [{ value: "cancel", label: "Cancel" }, { value: "theirs", label: `Use ${q.slug}`, help: "global.project.import.theirs" },
        { value: "keep", label: `Keep ${cur.slug}`, variant: "primary", help: "global.project.import.keep" }],
  });
  if (choice !== "keep" && choice !== "theirs") return false;
  if (choice === "keep") { q.slug = cur.slug; q.project_id = cur.project_id; }
  ctx.store.replaceProject(q, { label: `Import project “${q.name}”` });
  ctx.store.setEph({ projImport: false, projImportText: "" });
  ctx.actions.toast(`Imported “${q.name}” (${n(q.scenes.length, "scene")}). Ctrl+Z brings the previous project back.`, "ok");
  return true;
}
// New project. This node gets an
// empty project (one scene) in a folder of its own, untitled-xxxx, as one undo step. Nothing is deleted: the current
// project stays in its folder (project.json, uploads, renders; saved there first) and Ctrl+Z brings it back to this
// node. The new project keeps this project's Global settings, or takes the default profile's.
export async function newProject(ctx) {
  const cur = ctx.store.project;
  if (ctx.eph.running || ["start", "progress"].includes(ctx.eph.merge?.phase) || ctx.eph.passWrite?.running) {
    ctx.actions.toast(`“${cur.name}” is rendering, merging or writing prompts. Stop it or let it finish, then start a new project.`, "warn");
    return false;
  }
  const r = await ctx.actions.loadProfiles();
  const prof = r?.profiles?.find(x => x.id === r.default) || null;
  let tag = "";
  while (tag.length < 4) tag += Math.random().toString(36).slice(2).replace(/[^a-z0-9]/g, "");
  const slug = "untitled-" + tag.slice(0, 4);
  const message = `“${cur.name}” is replaced in this node by an empty project with one scene, in a new folder ${slug}.\n\n`
    + `Nothing is deleted: “${cur.name}” stays in its folder ${cur.slug} (its project.json, uploads and renders), and Ctrl+Z brings it back to this node.\n\n`
    + (prof ? `The new project keeps this project's Global settings (models, quality, LLM, merge), or takes them from your default profile “${prof.name}”.`
      : "The new project keeps this project's Global settings (models, quality, LLM, merge).");
  const choice = await choiceDialog(ctx.root, {
    title: "Start a new project?", message, help: "global.project.new", cancelValue: "cancel", focus: "keep",
    choices: [{ value: "cancel", label: "Cancel" },
      ...(prof ? [{ value: "profile", label: `Use profile “${prof.name}”`, help: "global.project.new.profile" }] : []),
      { value: "keep", label: "New project", variant: "primary", help: "global.project.new.keep" }],
  });
  if (choice !== "keep" && choice !== "profile") return false;
  // the current project's last edits reach its folder before it leaves this node
  const st = ctx.store.eph.saveState;
  if (st === "conflict") {
    ctx.actions.toast(`“${cur.name}” is not saved: its folder ${cur.slug} holds another project. Choose a folder for it first (Folder, above).`, "error");
    return false;
  }
  if (st === "pending" || st === "offline") {
    const s = await ctx.store.saveNow();
    if (!s?.ok) {
      if (!s?.conflict) ctx.actions.toast(`Could not save “${cur.name}” to its folder first (${s?.error || "no answer"}). Nothing changed: try again, or Export it first.`, "error");
      return false;
    }
  }
  const q = defaultProject("Untitled");
  q.slug = slug;
  q.global = structuredClone(choice === "profile" ? prof.global : ctx.store.project.global);
  if (choice === "profile") migrateScore(q); // a profile from before v0.5.0 names a score: a soundtrack track, as Apply profile does
  else if (q.global?.merge?.score) q.global.merge.score.asset = ""; // an asset of the old project
  q.global = normalizeGlobal(q.global, q);
  if (q.global.merge) q.global.merge.color_ref_scene = ""; // a scene of the old project
  q.scenes = [defaultScene(q, { title: "Scene 1", start: { mode: "fresh", overlap_frames: 39 } })]; // with these Global defaults
  q.ui.selected = q.scenes[0].id;
  ctx.store.replaceProject(q, { label: `New project (was “${cur.name}”)` });
  ctx.store.setEph({ fresh: false, projImport: false, projImportText: "", ...(choice === "profile" ? { profileSel: prof.id } : {}) });
  ctx.actions.toast(`New project in folder ${slug}${choice === "profile" ? ` with profile “${prof.name}”` : ""}. Ctrl+Z brings “${cur.name}” back.`, "ok");
  return true;
}

function projectIO(ctx) {
  const p = ctx.p;
  const open = !!ctx.eph.projImport;
  const file = h("input", { type: "file", accept: ".json,application/json", class: "rw-hidden-file", key: "proj-import-file", tabindex: "-1", "aria-hidden": "true",
    onChange: async e => {
      const f = e.target.files?.[0];
      e.target.value = "";
      if (!f) return;
      let t;
      try { t = await f.text(); } catch (err) { ctx.actions.toast("Could not read " + f.name + ": " + err.message, "error"); return; }
      await importProject(ctx, t, f.name);
    } });
  return h("div", { class: "rw-io" },
    h("div", { class: "rw-io-row" },
      button({ label: "New project…", icon: "plus", small: true, help: "global.project.new", key: "proj-new", onClick: () => newProject(ctx) }),
      button({ label: "Export", icon: "download", small: true, help: "global.project.export", key: "proj-export", onClick: () => {
        downloadText(exportName(p), projectText(ctx.p));
        ctx.actions.toast(`Saved ${exportName(p)} to your downloads.`, "ok");
      } }),
      button({ label: "Copy JSON", icon: "copy", small: true, help: "global.project.copy", key: "proj-copy",
        onClick: e => copyWithToast(projectText(ctx.p), e.currentTarget || e.target, "project as JSON") }),
      button({ label: open ? "Close import" : "Import…", icon: open ? "close" : "upload", small: true, variant: open ? "ghost" : "default", help: "global.project.import", key: "proj-import",
        onClick: () => ctx.store.setEph({ projImport: !open }) }),
      file),
    open && h("div", { class: "rw-io-panel" },
      h("textarea", { class: "rw-input rw-io-paste", key: "proj-import-text", placeholder: "Paste a project's JSON here, or choose a file.", spellcheck: "false", help: "global.project.importText",
        value: ctx.eph.projImportText || "", onInput: e => { ctx.eph.projImportText = e.target.value; } }),
      h("div", { class: "rw-io-row" },
        button({ label: "Choose file…", icon: "file", small: true, help: "global.project.importFile", key: "proj-import-choose", onClick: () => file.click() }),
        h("span", { class: "rw-flex" }),
        button({ label: "Import pasted JSON", icon: "upload", small: true, variant: "primary", help: "global.project.importPasted", key: "proj-import-go",
          onClick: () => {
            const t = ctx.eph.projImportText || "";
            if (!t.trim()) { ctx.actions.toast("Paste a project's JSON first.", "warn"); return; }
            importProject(ctx, t);
          } }))));
}

function modelsCard(ctx) {
  const m = ctx.eph.models || {};
  const g = ctx.p.global.models;
  return section({
    title: "Models", help: "global.models",
    actions: button({ label: "Rescan", icon: "refresh", small: true, help: "global.models.rescan", onClick: () => ctx.actions.refreshModels() }),
    children: [
      !ctx.eph.models && h("div", { class: "rw-note warn" }, icon("warn", 12), "Model lists come from ComfyUI; the backend is not reachable."),
      modelRow(ctx, "Diffusion model · ref2va", "diffusion", m.diffusion_models, "model", "global.models.diffusion"),
      field("Weight dtype", select({ options: DTYPES, value: g.weight_dtype, help: "global.models.dtype", onChange: v => ctx.actions.edit(q => { q.global.models.weight_dtype = v; }) }), { help: "global.models.dtype" }),
      modelRow(ctx, "Text encoder · Qwen3-VL (minimax)", "text_encoder", m.text_encoders, "clip", "global.models.textEncoder"),
      field("Text encoder device", segmented({ small: true, value: g.clip_device, help: "global.models.clipDevice", options: ["default", "cpu"], onChange: v => ctx.actions.edit(q => { q.global.models.clip_device = v; }) }), { help: "global.models.clipDevice" }),
      modelRow(ctx, "Video VAE", "video_vae", m.vae, "vae", "global.models.videoVae"),
      modelRow(ctx, "Audio VAE", "audio_vae", m.vae, "audio_vae", "global.models.audioVae"),
      modelRow(ctx, "Latent upscaler · for Hires", "latent_upscaler", m.latent_upscale_models, null, "global.models.upscaler"),
    ],
  });
}

function lorasCard(ctx) {
  const list = ctx.eph.models?.loras || [];
  const edit = fn => ctx.actions.edit(q => fn(q.global.loras), { label: "Global LoRAs" });
  const loras = ctx.p.global.loras;
  return section({
    title: "Global LoRA stack", help: "global.loras",
    actions: h("span", { class: "rw-dim small" }, "applied to every scene first"),
    children: [
      loras.length === 0 && h("div", { class: "rw-empty sm", help: "global.loras" }, "No global LoRAs."),
      sortable({ id: "global-loras", onMove: (from, to) => ctx.actions.edit(q => { moveItem(q.global.loras, from, to); }, { label: "Reorder global LoRAs" }), rows: loras.map((l, i) => {
        const overriders = ctx.p.scenes.filter(s => s.overrides.loras?.strengths?.[l.id] !== undefined || s.overrides.loras?.mode === "replace").length;
        return h("div", { class: ["rw-lora-row", !l.enabled && "off"] },
          dragGrip({ help: "global.loras.order", key: `glora-grip-${l.id || i}` }),
          toggle({ value: l.enabled, key: `glora-on-${l.id || i}`, help: "global.loras.enabled", onChange: v => edit(ls => { ls[i].enabled = v; }) }),
          h("div", { class: "grow" },
            select({ options: list, value: l.name, key: `glora-name-${l.id || i}`, placeholder: "choose LoRA", mono: true, help: "global.loras.name", onChange: v => edit(ls => { ls[i].name = v; }) }),
            overriders > 0 && h("div", { class: "rw-c-accent small" }, `${overriders} scene${overriders > 1 ? "s" : ""} override this`)),
          number({ value: l.strength, key: `glora-str-${l.id || i}`, min: -4, max: 4, step: 0.05, width: "74px", help: "global.loras.strength", onChange: v => edit(ls => { ls[i].strength = v ?? 1; }) }),
          button({ icon: "trash", small: true, variant: "ghost", help: "global.loras.remove", onClick: () => edit(ls => { ls.splice(i, 1); }) }));
      }) }),
      button({ label: "Add LoRA", icon: "plus", small: true, help: "global.loras.add", onClick: () => edit(ls => { ls.push({ id: newId("l"), name: list[0] || "", strength: 0.8, enabled: true }); }) }),
    ],
  });
}

function outputCard(ctx) {
  const o = ctx.p.global.output;
  const set = fn => ctx.actions.edit(q => fn(q.global.output), { label: "Output setting" });
  const mp = (o.width * o.height / 1e6).toFixed(2);
  return section({
    title: "Output", help: "global.output",
    actions: h("span", { class: "mono small" }, `${o.width}×${o.height} · ${mp} MP`),
    children: [
      h("div", { class: "rw-aspects" }, Object.entries(ASPECTS).map(([k, [w, hh]]) => {
        const r = w / hh;
        const bw = r >= 1 ? 30 : 30 * r, bh = r >= 1 ? 30 / r : 30;
        return h("button", {
          type: "button", class: ["rw-aspect", o.aspect === k && "on"], help: "global.output.aspect",
          onClick: () => set(x => { const [cw, ch] = adaptCanvas(w, hh); x.aspect = k; x.width = cw; x.height = ch; }),
        }, h("span", { class: "rw-aspect-box", style: { width: bw + "px", height: bh + "px" } }), k);
      }),
      h("button", { type: "button", class: ["rw-aspect", o.aspect === "custom" && "on"], help: "global.output.custom", onClick: () => set(x => { x.aspect = "custom"; }) },
        h("span", { class: "rw-aspect-box dashed", style: { width: "22px", height: "22px" } }), "custom")),
      field("Width × height", h("span", { class: "rw-row" },
        number({ value: o.width, min: 32, step: 32, help: "global.output.size", key: "out-width", onChange: v => set(x => { x.width = Math.max(32, Math.round((v ?? 32) / 32) * 32); x.aspect = "custom"; }) }),
        h("span", { class: "rw-dim" }, "×"),
        number({ value: o.height, min: 32, step: 32, help: "global.output.size", key: "out-height", onChange: v => set(x => { x.height = Math.max(32, Math.round((v ?? 32) / 32) * 32); x.aspect = "custom"; }) })), { help: "global.output.size" }),
      field("Frame rate", h("span", { class: "rw-locked mono", help: "global.output.fps" }, icon("lock", 11), "24 fps"), { help: "global.output.fps" }),
      field("Audio", h("span", { class: "rw-locked mono", help: "global.output.audio" }, icon("lock", 11), "32 kHz stereo"), { help: "global.output.audio" }),
      field("Reference images", segmented({ small: true, value: o.ref_image_size, help: "global.output.refSize", options: [
        { value: "match", label: "match", help: "global.output.refSize" }, { value: "max", label: "max (2048)", help: "global.output.refSize" }],
      onChange: v => set(x => { x.ref_image_size = v; }) }), { help: "global.output.refSize" }),
    ],
  });
}

// Global → Hires: every pass is sampled at Output, enlarged by the
// H3 latent upscaler to Output × scale (the same size for every scene and the film), and optionally sampled again at
// that size (refine). Scenes can turn it off or change the refine (Scene → Generation).
function hiresCard(ctx) {
  const p = ctx.p, g = p.global, hi = g.hires, o = g.output;
  const set = (fn, label = "Hires setting") => ctx.actions.edit(q => fn(q.global.hires), { label });
  const [fw, fh] = hiresSize(g);
  const up = g.models.latent_upscaler || "";
  const list = ctx.eph.models?.latent_upscale_models;
  const scales = HIRES_SCALES.includes(hi.scale) ? HIRES_SCALES : [...HIRES_SCALES, hi.scale].sort((a, b) => a - b);
  const off = p.scenes.filter(s => s.overrides?.hires === "off").length;
  const area = (fw * fh) / (o.width * o.height);
  return section({
    title: "Hires", help: "global.hires",
    actions: [hi.enabled && hi.scale > 1 && h("span", { class: "mono small", help: "global.hires.scale" }, `${fw}×${fh}`),
      toggle({ value: hi.enabled, help: "global.hires.enabled", key: "hires-on", label: hi.enabled ? "on" : "off",
        onChange: v => set(x => { x.enabled = v; }, v ? "Hires on" : "Hires off") })],
    children: [
      h("div", { class: "rw-dim small", help: "global.hires" }, hi.enabled
        ? `Each pass is sampled at ${o.width}×${o.height}; the latent upscaler enlarges it to ${fw}×${fh}${hi.refine_steps > 0 ? `, then ${hi.refine_steps} refine step${hi.refine_steps === 1 ? "" : "s"} at that size` : ""}. Every scene and the merged film end at ${fw}×${fh}.`
        : `Off: scenes are made at ${o.width}×${o.height}. On: H3's latent upscaler enlarges every pass to Output × scale, so the whole film is bigger.`),
      field("Scale", segmented({ small: true, value: hi.scale, help: "global.hires.scale", key: "hires-scale",
        options: scales.map(v => ({ value: v, label: `${v}×`, help: "global.hires.scale" })), onChange: v => set(x => { x.scale = v; }) }),
      { help: "global.hires.scale" }),
      field("Refine steps", number({ value: hi.refine_steps, min: 0, max: 100, help: "global.hires.refineSteps", key: "hires-steps",
        onChange: v => set(x => { x.refine_steps = Math.min(100, Math.max(0, Math.trunc(v ?? 0))); }) }), { help: "global.hires.refineSteps" }),
      hi.refine_steps > 0 && field("Refine denoise", slider({ value: hi.refine_denoise, min: 0.05, max: 1, step: 0.05, key: "hires-denoise",
        help: "global.hires.refineDenoise", format: v => Number(v).toFixed(2), onChange: v => set(x => { x.refine_denoise = Math.round(v * 100) / 100; }) }),
      { help: "global.hires.refineDenoise" }),
      hi.enabled && !up && h("div", { class: "rw-note err", help: "global.models.upscaler" }, icon("warn", 12),
        h("span", null, "No latent upscaler is chosen: pick one under Global → Models (models/latent_upscale_models). Rendering is refused until then.")),
      hi.enabled && up && list && !list.includes(up) && h("div", { class: "rw-note warn", help: "global.models.upscaler" }, icon("warn", 12),
        h("span", null, `${up} is not in this ComfyUI's models/latent_upscale_models.`)),
      hi.enabled && hi.refine_steps > 0 && h("div", { class: "rw-note warn small", help: "global.hires.refineSteps" }, icon("info", 12),
        h("span", null, `The refine samples H3 again at ${fw}×${fh}, ${area.toFixed(1)}× the pixels of ${o.width}×${o.height} (the size H3 is made for), so each refine step costs several normal steps and the result is not guaranteed. 0 steps = upscaler only.`)),
      hi.enabled && off > 0 && h("div", { class: "rw-dim small", help: "scene.override.hires" },
        `${off} scene${off === 1 ? " turns" : "s turn"} it off (Scene → Generation); the merge enlarges ${off === 1 ? "it" : "them"} to ${fw}×${fh}.`),
      hi.enabled && h("div", { class: "rw-dim small", help: "global.draft.hires" }, g.draft.hires
        ? "Drafts go through the upscaler too (no refine)." : "Drafts skip it (Draft quality → Upscale drafts); the merge enlarges them."),
    ],
  });
}

function samplingCard(ctx) {
  const sm = ctx.p.global.sampling;
  const m = ctx.eph.models || {};
  const set = fn => ctx.actions.edit(q => fn(q.global.sampling), { label: "Sampling setting" });
  return section({
    title: "Sampling", help: "global.sampling",
    children: [
      field("Steps", number({ value: sm.steps, min: 1, max: 200, help: "global.sampling.steps", onChange: v => set(x => { x.steps = v ?? 20; }) }), { help: "global.sampling.steps" }),
      field("CFG", h("span", { class: "rw-locked mono", help: "global.sampling.cfg" }, icon("lock", 11), "1.0 · distilled"), { help: "global.sampling.cfg" }),
      field("Sampler", select({ options: m.samplers || [sm.sampler], value: sm.sampler, mono: true, help: "global.sampling.sampler", onChange: v => set(x => { x.sampler = v; }) }), { help: "global.sampling.sampler" }),
      field("Scheduler", select({ options: m.schedulers || [sm.scheduler], value: sm.scheduler, mono: true, help: "global.sampling.scheduler", onChange: v => set(x => { x.scheduler = v; }) }), { help: "global.sampling.scheduler" }),
      field("Seed", h("span", { class: "rw-row" },
        number({ value: sm.seed, min: 0, width: "120px", help: "global.sampling.seed", onChange: v => set(x => { x.seed = v ?? 0; }) }),
        button({ icon: "refresh", small: true, variant: "ghost", help: "global.sampling.reroll", onClick: () => set(x => { x.seed = Math.floor(Math.random() * 2 ** 32); }) })), { help: "global.sampling.seed" }),
      field("Seed per scene", segmented({ small: true, value: sm.seed_mode, help: "global.sampling.seedMode", options: [
        { value: "fixed", label: "same", help: "global.sampling.seedMode" }, { value: "increment", label: "+1 per scene", help: "global.sampling.seedMode" }, { value: "random", label: "random", help: "global.sampling.seedMode" }],
      onChange: v => set(x => { x.seed_mode = v; }) }), { help: "global.sampling.seedMode" }),
      field("Sigma shift", toggle({ value: sm.sigma_shift, help: "global.sampling.shift", onChange: v => set(x => { x.sigma_shift = v; }) }), { help: "global.sampling.shift" }),
      sm.sigma_shift && field("Shift video / audio", h("span", { class: "rw-row" },
        number({ value: sm.shift_video, min: 0.01, max: 100, step: 0.5, width: "64px", help: "global.sampling.shiftVideo", onChange: v => set(x => { x.shift_video = v ?? 12; }) }),
        number({ value: sm.shift_audio, min: 0.01, max: 100, step: 0.5, width: "64px", help: "global.sampling.shiftAudio", onChange: v => set(x => { x.shift_audio = v ?? 3; }) })), { help: "global.sampling.shiftVideo" }),
    ],
  });
}

function draftCard(ctx) {
  const d = ctx.p.global.draft;
  const set = fn => ctx.actions.edit(q => fn(q.global.draft), { label: "Draft setting" });
  return section({
    title: "Draft quality", help: "global.draft",
    actions: segmented({ small: true, value: ctx.p.global.quality, help: "render.quality", options: [{ value: "draft", label: "Draft" }, { value: "final", label: "Final" }], onChange: v => ctx.actions.edit(q => { q.global.quality = v; }) }),
    children: [
      field("Resolution scale", number({ value: d.scale, min: 0.25, max: 1, step: 0.05, help: "global.draft.scale", onChange: v => set(x => { x.scale = v ?? 0.5; }) }), { help: "global.draft.scale" }),
      field("Steps", number({ value: d.steps, min: 1, max: 100, help: "global.draft.steps", onChange: v => set(x => { x.steps = v ?? 8; }) }), { help: "global.draft.steps" }),
      field("Upscale drafts", toggle({ value: !!d.hires, help: "global.draft.hires", key: "draft-hires",
        label: ctx.p.global.hires.enabled ? (d.hires ? "with Hires (upscaler only)" : "no, the merge enlarges them") : "only with Hires on",
        onChange: v => set(x => { x.hires = v; }) }), { help: "global.draft.hires" }),
      field("Turbo LoRA", h("span", { class: "rw-row" },
        select({ options: ctx.eph.models?.loras || [], value: d.lora, placeholder: "none", mono: true, help: "global.draft.lora", onChange: v => set(x => { x.lora = v; }) }),
        number({ value: d.lora_strength, min: -4, max: 4, step: 0.05, width: "74px", help: "global.draft.loraStrength", onChange: v => set(x => { x.lora_strength = v ?? 1; }) })), { help: "global.draft.lora" }),
    ],
  });
}

function defaultsCard(ctx) {
  const d = ctx.p.global.defaults;
  const L = ctx.p.global.long;
  const set = fn => ctx.actions.edit(q => fn(q.global.defaults), { label: "New-scene default" });
  const setL = fn => ctx.actions.edit(q => fn(q.global.long), { label: "Long-scene setting" });
  return section({
    title: "New scenes and long scenes", help: "global.defaults",
    children: [
      field("Duration", number({ value: d.duration, min: 0.25, step: 0.25, unit: "s", help: "global.defaults.duration", onChange: v => set(x => { x.duration = v ?? 8; }) }), { help: "global.defaults.duration" }),
      field("Starts from", segmented({ small: true, value: d.start_mode, help: "global.defaults.start", options: START_MODES.map(m => ({ value: m, label: m.replace("_", " "), help: "scene.start." + m })), onChange: v => set(x => { x.start_mode = v; }) }), { help: "global.defaults.start" }),
      field("Language", select({ options: STABLE_LANGUAGES, value: d.language, free: true, help: "global.defaults.language", onChange: v => set(x => { x.language = v; }) }), { help: "global.defaults.language" }),
      h("div", { class: "rw-subhead" }, "Long scenes"),
      field("Longest pass", number({ value: L.max_pass_frames, min: 124, max: 362, step: 17, unit: "f", help: "global.long.maxPass", onChange: v => setL(x => { x.max_pass_frames = Math.max(124, Math.min(362, 17 * Math.round(((v ?? 362) - 5) / 17) + 5)); }) }), { help: "global.long.maxPass" }),
      field("Overlap", number({ value: L.overlap_frames, min: 5, max: 107, step: 17, unit: "f", help: "global.long.overlap", onChange: v => setL(x => { x.overlap_frames = Math.max(5, 17 * Math.round(((v ?? 39) - 5) / 17) + 5); }) }), { help: "global.long.overlap" }),
      field("Crossfade", number({ value: L.crossfade_frames, min: 0, max: 48, unit: "f", help: "global.long.crossfade", onChange: v => setL(x => { x.crossfade_frames = v ?? 12; }) }), { help: "global.long.crossfade" }),
      field("Seams", segmented({ small: true, value: L.seam_mode, help: "global.long.seams", options: [
        { value: "auto", label: "Auto: cuts first", help: "global.long.seams" }, { value: "cuts", label: "Cuts only", help: "global.long.seams" }, { value: "overlap", label: "Overlap only", help: "global.long.seams" }],
      onChange: v => setL(x => { x.seam_mode = v; }) }), { help: "global.long.seams" }),
      field("Snap seam to cut", number({ value: L.cut_snap_seconds, min: 0, max: 10, step: 0.25, unit: "s", help: "global.long.snap", onChange: v => setL(x => { x.cut_snap_seconds = v ?? 2; }) }), { help: "global.long.snap" }),
      h("div", { class: "rw-dim small" }, `Longest pass ${(L.max_pass_frames / FPS).toFixed(2)} s · overlap ${(L.overlap_frames / FPS).toFixed(2)} s · crossfade ${(L.crossfade_frames / FPS).toFixed(2)} s`),
      ...seamFields(ctx, L),
    ],
  });
}

// The long-scene continuity settings (global.long: guide_vae, carry_audio, seam_video_ref,
// handoff, pass_cache). Missing keys (a project from before v0.8.0) show their defaults, which keep the old behaviour.
function seamFields(ctx, L) {
  const setLn = (label, fn) => ctx.actions.edit(q => fn(q.global.long), { label });
  const vaes = (ctx.eph.models?.vae || []).filter(v => !/audio/i.test(v));
  const named = ctx.p.global.continuity?.name_continuation !== false;
  const seamVideo = L.seam_video_ref !== false;
  const handoff = L.handoff === "latent" ? "latent" : "pixels";
  const cache = L.pass_cache === "lossless" ? "lossless" : "near_lossless";
  const videoEl = toggle({ value: seamVideo, key: "long-seam-video", help: "global.long.seamVideo", disabled: !named,
    onChange: v => setLn(v ? "Send the pass before as <Video 1>" : "Don't send the pass before as <Video 1>", x => { x.seam_video_ref = v; }) });
  return [
    h("div", { class: "rw-subhead", help: "global.long.seamsHead" }, "Pass seams"),
    field("Guide VAE", select({ options: vaes, value: L.guide_vae || "", placeholder: "Same as the video VAE", mono: true, key: "long-guide-vae", help: "global.long.guideVae",
      onChange: v => setLn("Guide VAE", x => { x.guide_vae = v || ""; }) }), { help: "global.long.guideVae", wide: true }),
    field("Carry sound", toggle({ value: L.carry_audio !== false, key: "long-carry-audio", help: "global.long.carryAudio",
      onChange: v => setLn(v ? "Carry sound across seams" : "Picture only across seams", x => { x.carry_audio = v; }) }), { help: "global.long.carryAudio" }),
    field("<Video 1> at seams", h("span", { class: "rw-row" }, videoEl,
      h("span", { class: "rw-dim small", help: "global.long.seamVideo" }, named ? (seamVideo ? "the pass before is sent as a clip" : "guide frames only") : "off: Cast → Name the continuation is off")),
    { help: "global.long.seamVideo" }),
    field("Hand-off", segmented({ small: true, value: handoff, key: "long-handoff", help: "global.long.handoff", options: [
      { value: "pixels", label: "Pixels", help: "global.long.handoff.pixels" }, { value: "latent", label: "Latent · experimental", help: "global.long.handoff.latent" }],
    onChange: v => setLn(v === "latent" ? "Latent hand-off" : "Pixel hand-off", x => { x.handoff = v; }) }), { help: "global.long.handoff" }),
    field("Pass cache", segmented({ small: true, value: cache, key: "long-pass-cache", help: "global.long.passCache", options: [
      { value: "near_lossless", label: "Near-lossless", help: "global.long.passCache.near" }, { value: "lossless", label: "Lossless", help: "global.long.passCache.lossless" }],
    onChange: v => setLn(v === "lossless" ? "Lossless pass cache" : "Near-lossless pass cache", x => { x.pass_cache = v; }) }), { help: "global.long.passCache" }),
    h("div", { class: "rw-long-note", help: "global.long.seamsHead" }, handoff === "latent"
      ? "Latent hand-off is experimental: a pass whose size or settings differ from the pass before falls back to pixels."
      : `Every overlap seam decodes ${L.overlap_frames} frames and encodes them again${L.guide_vae ? " with the guide VAE" : ""}. Shot cuts as seams avoid that.`),
  ];
}

function llmCard(ctx) {
  const l = ctx.p.global.llm;
  const st = ctx.eph.llm || {};
  const set = fn => ctx.actions.edit(q => fn(q.global.llm), { label: "LLM setting" });
  const keyInput = h("input", { type: "password", class: "rw-input mono", key: "llm-key", placeholder: st.has_key ? "•••••••• stored — type to replace" : "API key (optional for local servers)", help: "global.llm.key", autocomplete: "off" });
  const saveKey = async () => {
    try {
      await rw.saveLlmSettings({ api_key: keyInput.value, base_url: l.base_url, model: l.model });
      keyInput.value = "";
      ctx.store.setEph({ llm: { ...st, has_key: true } });
      ctx.actions.toast("API key stored in the ComfyUI user folder.", "ok");
    } catch (err) { ctx.actions.toast("Could not store the key: " + err.message, "error"); }
  };
  const syncServer = patch => rw.saveLlmSettings(patch).catch(() => {});
  return section({
    title: "Prompt rewriter · LLM", help: "global.llm", tint: "dlg",
    actions: h("span", { class: ["small", st.ok ? "rw-c-aud" : st.error ? "rw-c-err" : "rw-dim"], help: "global.llm.status" }, st.ok ? `● connected${st.ms ? ` · ${st.ms} ms` : ""}` : st.error ? "● " + st.error : "not tested"),
    children: [
      field("Base URL", text({ value: l.base_url, key: "llm-url", mono: true, placeholder: st.base_url || "http://localhost:30000/v1", help: "global.llm.baseUrl", onChange: v => { set(x => { x.base_url = v.trim(); }); syncServer({ base_url: v.trim() }); } }), { help: "global.llm.baseUrl" }),
      field("API key", h("span", { class: "rw-row grow" }, keyInput, button({ label: "Store", small: true, help: "global.llm.storeKey", onClick: saveKey })), { help: "global.llm.key" }),
      field("Model", h("span", { class: "rw-row grow" },
        select({ options: st.models || [], value: l.model, free: true, mono: true, width: "100%", placeholder: st.model ? "server default · " + st.model : "server default",
          help: "global.llm.model", onChange: v => { set(x => { x.model = v; }); syncServer({ model: v }); } }),
        button({ icon: "refresh", small: true, variant: "ghost", help: "global.llm.listModels", onClick: async () => {
          try { const r = await rw.llmModels(l.base_url); ctx.store.setEph({ llm: { ...st, models: r.models || [] } }); }
          catch (err) { ctx.store.setEph({ llm: { ...st, error: err.message } }); }
        } })), { help: "global.llm.model" }),
      field("Temperature", number({ value: l.temperature, min: 0, max: 2, step: 0.05, help: "global.llm.temperature", onChange: v => set(x => { x.temperature = v ?? 0.4; }) }), { help: "global.llm.temperature" }),
      field("Max tokens", number({ value: l.max_tokens, min: 128, max: 1000000, step: 128, width: "96px", help: "global.llm.maxTokens", onChange: v => set(x => { x.max_tokens = v ?? 2048; }) }), { help: "global.llm.maxTokens" }),
      field("Thinking", segmented({ small: true, value: l.thinking === "off" ? "off" : "auto", help: "global.llm.thinking", options: [
        { value: "auto", label: "Model default", help: "global.llm.thinking.auto" }, { value: "off", label: "Off", help: "global.llm.thinking.off" }],
      onChange: v => set(x => { x.thinking = v; }) }), { help: "global.llm.thinking" }),
      field("Describe videos", segmented({ small: true, value: ["video", "frames"].includes(l.describe_video) ? l.describe_video : "auto", help: "global.llm.describeVideo", options: [
        { value: "auto", label: "Auto", help: "global.llm.describeVideo.auto" }, { value: "video", label: "As video", help: "global.llm.describeVideo.video" },
        { value: "frames", label: "As frames", help: "global.llm.describeVideo.frames" }],
      onChange: v => set(x => { x.describe_video = v; }) }), { help: "global.llm.describeVideo" }),
      field("Preset", select({ options: [
        { value: "h3_ref2va", label: "H3 ref2va · six sections" }, { value: "h3_compact", label: "H3 · compact prose" }, { value: "h3_cinematic", label: "H3 · cinematic detail" }],
      value: l.preset, help: "global.llm.preset", onChange: v => set(x => { x.preset = v; }) }), { help: "global.llm.preset" }),
      guidesField(ctx, l, st, set),
      h("div", { class: "rw-row" },
        button({ label: st.testing ? "Testing…" : "Test connection", small: true, help: "global.llm.test", disabled: !!st.testing, onClick: async () => {
          ctx.store.setEph({ llm: { ...ctx.eph.llm, testing: true, error: null } });
          try {
            const r = await rw.llmTestProject(ctx.p);
            ctx.store.setEph({ llm: { ...ctx.eph.llm, testing: false, ok: true, ms: r.ms, error: null, testedModel: r.model, testedUrl: r.base_url, reply: r.reply, note: r.note || "", context: r.context || 0 } });
            ctx.actions.toast(`LLM answered in ${r.ms} ms · ${r.model || "server default model"}`, "ok");
          } catch (err) {
            ctx.store.setEph({ llm: { ...ctx.eph.llm, testing: false, ok: false, error: err.message } });
            ctx.actions.toast("LLM test failed: " + err.message, "error");
          }
        } }),
        h("span", { class: "rw-dim small" }, "Only used when you press Rewrite, Split or Import — never during a render.")),
      st.ok && st.testedUrl ? h("div", { class: "rw-note ok small", help: "global.llm.status" }, icon("check", 12), `${st.testedUrl} · ${st.testedModel || "default model"} · ${st.ms} ms${st.reply ? ` · replied “${st.reply}”` : ""}`) : null,
      st.error ? h("div", { class: "rw-note err small", help: "global.llm.status" }, icon("warn", 12), st.error) : null,
      st.ok && st.note ? h("div", { class: "rw-note small", help: "global.llm.thinking" }, icon("info", 12), st.note) : null,
      ...limitFields(ctx, l, st, set),
    ],
  });
}

// timeouts, retries, context window, and script import's own budget
// Limits and Script import fold away (closed by default); a closed group shows its values
function limitFields(ctx, l, st, set) {
  const n = v => Math.round(v).toLocaleString("en-US");
  const hint = (t, help) => h("span", { class: "rw-dim small", help }, t);
  const opened = ctx.eph.llmOpen || {};
  const group = (key, label, help, summary, fields) => [
    h("button", {
      type: "button", class: ["rw-subhead", "rw-fold", opened[key] && "open"], help, "aria-expanded": opened[key] ? "true" : "false",
      onClick: () => ctx.store.setEph({ llmOpen: { ...(ctx.eph.llmOpen || {}), [key]: !opened[key] } }),
    }, icon(opened[key] ? "chevDown" : "chevRight", 12), h("span", { class: "rw-fold-label" }, label),
    !opened[key] && h("span", { class: "rw-fold-sum" }, summary)),
    ...(opened[key] ? fields : []),
  ];
  const limitsSummary = `stall ${l.timeout_s} s · give up ${l.max_wait_s} s · ${l.retries} retr${l.retries === 1 ? "y" : "ies"} · context ${l.context_tokens ? n(l.context_tokens) : st.context ? n(st.context) + " (server)" : "from the server"}`;
  const importSummary = `${l.import_part_chars ? "parts of " + n(l.import_part_chars) + " chars" : "whole script"} · ${n(l.import_max_tokens)} tokens · thinking ${l.import_thinking === "off" ? "off" : "as above"} · guides ${l.import_guides ? "on" : "off"}`;
  return [
    ...group("limits", "Limits", "global.llm.limits", limitsSummary, [
    field("Stall timeout", h("span", { class: "rw-row grow" },
      number({ value: l.timeout_s, min: 10, max: 3600, step: 10, unit: "s", help: "global.llm.timeout", onChange: v => set(x => { x.timeout_s = v ?? 120; }) }),
      hint("no data from the server for this long ends the request", "global.llm.timeout")), { help: "global.llm.timeout" }),
    field("Give up after", h("span", { class: "rw-row grow" },
      number({ value: l.max_wait_s, min: 30, max: 7200, step: 30, unit: "s", help: "global.llm.maxWait", onChange: v => set(x => { x.max_wait_s = v ?? 900; }) }),
      hint("longest one request may take, even while text keeps arriving", "global.llm.maxWait")), { help: "global.llm.maxWait" }),
    field("Retries", h("span", { class: "rw-row grow" },
      number({ value: l.retries, min: 0, max: 5, step: 1, help: "global.llm.retries", onChange: v => set(x => { x.retries = v ?? 2; }) }),
      hint("after a timeout, a dropped connection, a server error or an unreadable answer", "global.llm.retries")), { help: "global.llm.retries" }),
    field("Context window", h("span", { class: "rw-row grow" },
      number({ value: l.context_tokens, min: 0, max: 4000000, step: 1024, width: "96px", unit: "tokens", help: "global.llm.context", onChange: v => set(x => { x.context_tokens = v ?? 0; }) }),
      hint(l.context_tokens ? "prompt + answer must fit" : st.context ? `0 = ask the server · it says ${n(st.context)} tokens` : "0 = ask the server (Test connection shows its answer)", "global.llm.context")), { help: "global.llm.context" }),
    ]),
    ...group("import", "Script import", "global.llm.import", importSummary, [
    field("Part size", h("span", { class: "rw-row grow" },
      number({ value: l.import_part_chars, min: 0, max: 1000000, step: 500, width: "96px", unit: "chars", help: "global.llm.importPart", onChange: v => set(x => { x.import_part_chars = v ?? 3000; }) }),
      hint(l.import_part_chars ? "a long script is sent in parts of about this size" : "0 = the whole script in one request", "global.llm.importPart")), { help: "global.llm.importPart" }),
    field("Max tokens", h("span", { class: "rw-row grow" },
      number({ value: l.import_max_tokens, min: 256, max: 1000000, step: 1024, width: "96px", unit: "tokens", help: "global.llm.importTokens", onChange: v => set(x => { x.import_max_tokens = v ?? 24576; }) }),
      hint("per part, thinking included; a part that runs out is split in two", "global.llm.importTokens")), { help: "global.llm.importTokens" }),
    field("Thinking", segmented({ small: true, value: l.import_thinking === "off" ? "off" : "same", help: "global.llm.importThinking", options: [
      { value: "same", label: "Same as above", help: "global.llm.importThinking.same" }, { value: "off", label: "Off", help: "global.llm.importThinking.off" }],
    onChange: v => set(x => { x.import_thinking = v; }) }), { help: "global.llm.importThinking" }),
    field("H3 guides", h("span", { class: "rw-row grow" },
      toggle({ value: !!l.import_guides, help: "global.llm.importGuides", onChange: v => set(x => { x.import_guides = v; }) }),
      hint(l.import_guides ? "sent with every part (about 10,000 tokens)" : "not sent: about 10,000 fewer prompt tokens per part", "global.llm.importGuides")), { help: "global.llm.importGuides" }),
    ]),
  ];
}

// Guide status, download button and the include switch
function guidesField(ctx, l, st, set) {
  const have = st.guides || {};
  const names = Object.keys(st.guide_urls || { "ref-en.txt": 1, "base-en.txt": 1 });
  const got = names.filter(n => have[n]);
  const when = got.length ? new Date(Math.max(...got.map(n => have[n].fetched)) * 1000).toLocaleDateString() : "";
  const fetchGuides = async () => {
    ctx.store.setEph({ llm: { ...ctx.eph.llm, guidesBusy: true } });
    try {
      const r = await rw.llmGuides();
      ctx.store.setEph({ llm: { ...ctx.eph.llm, guides: r.guides, guidesBusy: false } });
      ctx.actions.toast("Downloaded MiniMax's H3 prompt guides.", "ok");
    } catch (err) {
      ctx.store.setEph({ llm: { ...ctx.eph.llm, guidesBusy: false } });
      ctx.actions.toast("Could not download the guides: " + err.message, "error");
    }
  };
  return field("H3 guides", h("span", { class: "rw-row grow" },
    toggle({ value: l.include_guides !== false, help: "global.llm.guides", onChange: v => set(x => { x.include_guides = v; }) }),
    h("span", { class: ["small", got.length === names.length ? "rw-c-aud" : "rw-dim"], help: "global.llm.guidesStatus" },
      got.length === names.length ? `official · ${when}` : got.length ? `${got.length}/${names.length} downloaded` : "built-in summary"),
    h("span", { class: "rw-flex" }),
    button({ label: st.guidesBusy ? "Downloading…" : got.length ? "Update" : "Download", icon: "download", small: true, disabled: !!st.guidesBusy,
      help: "global.llm.guidesFetch", onClick: fetchGuides })), { help: "global.llm.guides" });
}

function scriptCard(ctx) {
  const draft = ctx.eph.scriptDraft;
  const run = async () => {
    const script = ctx.eph.scriptText || "";
    if (!script.trim()) { ctx.actions.toast("Paste a script first.", "warn"); return; }
    const old = ctx.store.eph.scriptDraft;
    if (old?.busy || ctx.store.eph.scriptSplitting) return;
    ctx.store.setEph({ scriptSplitting: true });
    let sp;
    try { sp = await rw.scriptParts(script, ctx.p.global.llm.import_part_chars ?? 3000); }
    catch (err) { ctx.store.setEph({ scriptSplitting: false }); ctx.actions.toast("Script import failed: " + err.message, "error"); return; }
    ctx.store.eph.scriptSplitting = false; // runParts renders next, with the draft busy
    const draft = { busy: false, notes: sp.notes || "", chars: sp.chars, parts: (sp.parts || []).map(blocks => ({ blocks, status: "wait", scenes: [], cast: [] })), scenes: [], cast: [], splits: 0 };
    await runParts(ctx, draft);
  };
  const stop = () => {
    if (!draft?.busy) return;
    draft.stop = true;
    if (draft.job) rw.llmCancel(draft.job).catch(() => {});
    ctx.store.setEph({ scriptDraft: draft });
  };
  const mode = ctx.eph.scriptMode || "append";
  const selScene = ctx.scene;
  const short = t => (t.length > 18 ? t.slice(0, 17) + "…" : t);
  const apply = async () => {
    const pickedScenes = draft.scenes.filter(x => x._on);
    const pickedCast = draft.cast.filter(x => x._on);
    if (!pickedScenes.length && !pickedCast.length) { ctx.actions.toast("Tick at least one scene or cast member.", "warn"); return; }
    if (mode === "replace") {
      if (!pickedScenes.length) { ctx.actions.toast("Tick at least one scene to replace the current ones.", "warn"); return; }
      const n = ctx.p.scenes.length;
      if (!(await confirmDialog(ctx.root, { title: `Replace all ${n} scene${n > 1 ? "s" : ""}?`, confirmLabel: "Replace scenes",
        message: `The ${n} current scene${n > 1 ? "s are" : " is"} removed and the ${pickedScenes.length} imported scene${pickedScenes.length > 1 ? "s" : ""} take${pickedScenes.length > 1 ? "" : "s"} their place. Cast, assets and Global settings stay. Rendered takes stay on disk. Ctrl+Z undoes this.` }))) return;
    }
    let firstId = null;
    let importedIds = [];
    ctx.actions.edit(p => {
      const ids = {};
      for (const c of p.cast) ids[c.name.toLowerCase()] = c.id;
      let sn = p.cast.filter(c => c.speaker).length;
      for (const c of pickedCast) {
        if (ids[(c.name || "").toLowerCase()]) continue;
        const id = newId("c");
        ids[(c.name || "").toLowerCase()] = id;
        const kind = c.kind || "character";
        p.cast.push({ id, kind, name: c.name || "Unnamed", speaker: kind === "character" ? c.speaker || "S" + (++sn) : "", description: c.description || "",
          anchors: [], pack_sheet: "auto", outfits: [], default_outfit: "", voice: "", voice_desc: kind === "character" ? c.voice_desc || "" : "", language: c.language || p.global.defaults.language, lora: { name: "", strength: 0.8 } });
      }
      const made = pickedScenes.map(s => {
        const sc = defaultScene(p, { title: s.title || "Imported scene", duration: Number(s.duration) > 0 ? Number(s.duration) : p.global.defaults.duration });
        sc.prompt.sections.summary = s.summary || "";
        sc.prompt.sections.overall_soundscape = s.soundscape || "";
        sc.prompt.sections.non_diegetic_music = s.music || "";
        sc.shots = (s.shots || []).map(x => ({ id: newId("h"), t: Number(x.t) || 0, camera: x.camera || "", text: x.text || "" }));
        sc.dialogue = (s.dialogue || []).map(d => ({ id: newId("d"), speaker: ids[(d.speaker || "").toLowerCase()] || "", t: Number(d.t) || 0, language: d.language || p.global.defaults.language, delivery: d.delivery || "says", text: d.text || "" }));
        const names = new Set([...(s.cast || []), ...(s.dialogue || []).map(d => d.speaker)].map(n => (n || "").toLowerCase()));
        sc.cast = [...names].filter(n => ids[n]).map(n => ({ id: ids[n], outfit: "" }));
        sc.shots.sort((a, b) => a.t - b.t);
        if (overruns(sc)) lengthenToFit(sc);
        return sc;
      });
      if (!made.length) return;
      let seedN = typeof nextSeedN === "function" ? nextSeedN(p) : null;
      if (Number.isInteger(seedN)) for (const sc of made) sc.seed_n = seedN++;
      if (mode === "replace") {
        p.scenes = made;
        if (p.global.merge.color_ref_scene && !made.some(s => s.id === p.global.merge.color_ref_scene)) p.global.merge.color_ref_scene = "";
      } else if (mode === "insert") {
        const i = sceneIndex(p, selScene?.id);
        p.scenes.splice(i < 0 ? p.scenes.length : i + 1, 0, ...made);
      } else {
        p.scenes.push(...made);
      }
      p.scenes[0].start.mode = "fresh";
      firstId = made[0].id;
      importedIds = made.map(x => x.id);
      p.ui.selected = firstId;
    }, { label: mode === "replace" ? "Replace scenes with script" : "Import script" });
    ctx.store.setEph({ scriptDraft: null, imported: importedIds.length ? { ids: importedIds } : ctx.eph.imported });
    ctx.root.focus?.({ preventScroll: true }); // the button is gone after the re-render; keep Ctrl+Z working
    const where = mode === "replace" ? "replaced the old scenes" : mode === "insert" ? `inserted after ${selScene?.title || "the selected scene"}` : "added at the end";
    ctx.actions.toast(pickedScenes.length ? `Imported ${pickedScenes.length} scene${pickedScenes.length > 1 ? "s" : ""} (${where}). Ctrl+Z undoes this. Write prompts (below) writes their passes in full.` : "Imported the cast.", "ok");
  };
  return section({
    title: "Import a script", help: "global.script",
    children: [
      textarea({ value: ctx.eph.scriptText || "", rows: 5, mono: true, key: "script-text", help: "global.script.text", placeholder: "Paste a screenplay (Fountain or plain text). The LLM proposes scenes, shots, dialogue and cast; you choose what to add.",
        onInput: v => { ctx.eph.scriptText = v; } }),
      h("div", { class: "rw-row" }, button({ label: draft?.busy ? `Reading part ${runningIndex(draft) + 1} of ${draft.parts.length}…` : ctx.eph.scriptSplitting ? "Reading script…" : "Propose scenes", icon: "wand", variant: "pink", help: "global.script.run", disabled: !!draft?.busy || !!ctx.eph.scriptSplitting, onClick: run }),
        draft?.busy && button({ label: draft.stop ? "Stopping…" : "Stop", icon: "close", small: true, help: "global.script.stop", disabled: !!draft.stop, onClick: stop }),
        draft && !draft.busy && draft.parts.some(p => p.status !== "done") && button({ label: draft.parts.some(p => p.status === "failed") ? "Retry failed parts" : "Continue", icon: "refresh", small: true, help: "global.script.retry", onClick: () => runParts(ctx, draft) }),
        draft && !draft.busy && button({ label: "Discard", small: true, help: "global.script.discard", onClick: () => ctx.store.setEph({ scriptDraft: null }) })),
      draft && partsView(ctx, draft),
      draft && (draft.scenes.length > 0 || draft.cast.length > 0) && h("div", { class: "rw-script-review" },
        h("div", { class: "rw-subhead" }, `${draft.cast.length} cast · ${draft.scenes.length} scene${draft.scenes.length === 1 ? "" : "s"} proposed`),
        draft.cast.map(c => h("label", { class: "rw-check", help: "global.script.pick" }, h("input", { type: "checkbox", checked: c._on, onChange: e => { c._on = e.target.checked; } }),
          h("b", null, c.name), h("span", { class: "rw-dim small" }, ` ${c.kind || "character"}${c.description ? " · " + c.description.slice(0, 60) : ""}`))),
        draft.scenes.map(s => h("label", { class: "rw-check", help: "global.script.pick" }, h("input", { type: "checkbox", checked: s._on, onChange: e => { s._on = e.target.checked; } }),
          h("b", null, s.title || "Untitled"), h("span", { class: "rw-dim small mono" }, ` ${Number(s.duration || 0).toFixed(1)} s · ${(s.shots || []).length} shots · ${(s.dialogue || []).length} lines`),
          s.fit_note ? h("span", { class: "rw-c-warn small", help: "global.script.fitNote" }, ` · ${s.fit_note}`) : null)),
      ),
      draft && !draft.busy && (draft.scenes.length > 0 || draft.cast.length > 0) && field("Add scenes", segmented({ small: true, value: mode, help: "global.script.mode", options: [
        { value: "append", label: "At the end", help: "global.script.mode.append" },
        { value: "insert", label: `After ${String(sceneIndex(ctx.p, selScene?.id) + 1).padStart(2, "0")} · ${short(selScene?.title || "selected")}`, help: "global.script.mode.insert" },
        { value: "replace", label: "Replace all scenes", help: "global.script.mode.replace" }],
      onChange: v => ctx.store.setEph({ scriptMode: v }) }), { help: "global.script.mode", wide: true }),
      draft && !draft.busy && (draft.scenes.length > 0 || draft.cast.length > 0) && h("div", { class: "rw-row" },
        button({ label: mode === "replace" ? "Replace scenes with the selected" : "Add selected to the project", icon: mode === "replace" ? "refresh" : "plus",
          variant: mode === "replace" ? "danger" : "primary", small: true, help: "global.script.apply", onClick: apply })),
      writeBatchBox(ctx),
    ],
  });
}

// After an import, the LLM can write every pass of the imported scenes (POST /llm/passes,
// one request per pass, one scene after another, each scene one undo step), with progress and Stop
function writeBatchBox(ctx) {
  const imp = ctx.eph.imported;
  const scenes = ctx.p.scenes;
  let run = ctx.eph.passWrite?.origin === "import" ? ctx.eph.passWrite : null;
  // a finished run whose scenes are all gone (another project loaded, undo of the import) is not shown
  if (run && !run.running && !run.items.some(x => scenes.some(s => s.id === x.sid))) run = null;
  const ids = (imp?.ids || []).filter(id => scenes.some(s => s.id === id));
  if (!ids.length && !run) return null;
  const title = id => scenes.find(s => s.id === id)?.title || "(deleted scene)";
  const num = id => String(sceneIndex(ctx.p, id) + 1).padStart(2, "0");
  const n = ids.length;
  const start = items => runWrite(ctx, items, { origin: "import" }).then(r => {
    if (!r) return;
    const done = r.items.filter(x => x.state === "done").length, failed = r.items.filter(x => x.state === "failed").length;
    const left = r.items.length - done;
    if (failed) ctx.actions.toast(`Wrote ${done} of ${r.items.length} scenes; ${failed} failed. Retry them in Global → Import a script.`, "error");
    else if (left) ctx.actions.toast(`Stopped after ${done} of ${r.items.length} scenes. Ctrl+Z undoes them one scene at a time.`, "warn");
    else ctx.actions.toast(`Wrote the prompts of ${done} scene${done === 1 ? "" : "s"}. Ctrl+Z undoes them one scene at a time.`, "ok");
  });
  const dismiss = button({ label: "Dismiss", small: true, variant: "ghost", key: "write-batch-dismiss", help: "global.script.writeDismiss",
    onClick: () => { ctx.store.setEph({ imported: null, passWrite: run?.running ? ctx.eph.passWrite : null }); ctx.root.focus?.({ preventScroll: true }); } });
  if (!run) {
    return h("div", { class: "rw-write-box", help: "global.script.write" },
      h("div", { class: "small" }, `Imported ${n} scene${n === 1 ? "" : "s"} with a short outline each. The LLM can now write every pass in full (one request per pass).`),
      h("div", { class: "rw-row" },
        button({ label: `Write prompts for the ${n} imported scene${n === 1 ? "" : "s"}`, icon: "wand", small: true, variant: "pink", key: "write-batch", help: "global.script.write",
          disabled: !!ctx.eph.passWrite?.running, onClick: () => start(ids.map(sid => ({ sid, passes: null }))) }),
        dismiss));
  }
  const d = run.running ? ctx.eph.llmJobs[run.job] : null;
  const cur = run.items[run.at];
  const doneN = run.items.filter(x => x.state === "done").length;
  const retry = run.items.filter(x => x.state === "failed" || x.state === "stopped" || x.state === "wait");
  const mark = { wait: "·", run: "…", done: "✓", failed: "✕", stopped: "–" };
  return h("div", { class: "rw-write-box", help: "global.script.write" },
    h("div", { class: "rw-row" },
      h("b", { class: "small grow" }, run.running ? `Writing scene ${run.at + 1} of ${run.items.length}: ${cur ? num(cur.sid) + " · " + title(cur.sid) : ""}` : `Wrote ${doneN} of ${run.items.length} scene${run.items.length === 1 ? "" : "s"}`),
      run.running && outputButton(ctx, { job: run.job, follow: () => (ctx.eph.passWrite?.running ? ctx.eph.passWrite.job : null), title: "Write prompts · LLM output", key: "write-batch-out" }),
      run.running && button({ label: run.stop ? "Stopping…" : "Stop", icon: "close", small: true, key: "write-batch-stop", help: "global.script.writeStop", disabled: !!run.stop, onClick: () => stopWrite(ctx) }),
      !run.running && retry.length > 0 && button({ label: `Retry ${retry.length}`, icon: "refresh", small: true, key: "write-batch-retry", help: "global.script.writeRetry",
        onClick: () => start(retry.filter(x => scenes.some(s => s.id === x.sid)).map(x => ({ sid: x.sid, passes: x.passes || null }))) }),
      !run.running && dismiss),
    run.running && jobText(run.job, d, { tag: "div", class: "rw-dim small mono", help: "scene.prompt.writeProgress",
      fmt: x => (x?.pass ? `pass ${x.pass}${x.passes ? " of " + x.passes : ""} · ` : "") + jobLine(x) }),
    run.items.map(x => h("div", { class: ["rw-write-item", x.state], help: "global.script.writeItem" },
      h("span", { class: "st mono" }, mark[x.state] || "·"),
      h("span", { class: "rw-ellipsis" }, `${num(x.sid)} · ${title(x.sid)}`),
      h("span", { class: ["small", x.state === "failed" ? "rw-c-err" : "rw-dim"] }, x.state === "failed" ? x.error : x.state === "run" ? "writing" : x.state === "done" ? "written" : x.state === "stopped" ? "stopped" : "waiting"))));
}

// ---- script import in parts -----------------------------------------------------------------------------------

function runningIndex(draft) {
  const i = draft.parts.findIndex(p => p.status === "run");
  return i < 0 ? 0 : i;
}

// Cast proposed by the parts, one entry per name; a later part may fill in a missing description. Speaker ids are
// numbered again when the cast is added (each part numbers its own from S1).
function addCast(draft, list) {
  for (const c of list) {
    const key = (c.name || "").trim().toLowerCase();
    if (!key) continue;
    const had = draft.cast.find(x => (x.name || "").trim().toLowerCase() === key);
    if (had) { if (!had.description && c.description) had.description = c.description; if (!had.voice_desc && c.voice_desc) had.voice_desc = c.voice_desc; continue; }
    draft.cast.push({ ...c, speaker: "", _on: true });
  }
}

// Two halves of a part's blocks by size, for a part whose answer did not fit the token budget.
function halves(blocks) {
  const total = blocks.reduce((a, b) => a + b.length, 0);
  let acc = 0, i = 0;
  while (i < blocks.length - 1 && acc + blocks[i].length <= total / 2) acc += blocks[i++].length;
  i = Math.max(1, i);
  return [blocks.slice(0, i), blocks.slice(i)];
}

async function runParts(ctx, draft) {
  const store = ctx.store;
  Object.assign(draft, { busy: true, stop: false });
  store.setEph({ scriptDraft: draft });
  for (let i = 0; i < draft.parts.length; i++) {
    const part = draft.parts[i];
    if (part.status === "done") continue;
    if (draft.stop || store.eph.scriptDraft !== draft) break;
    const job = newJob("import");
    Object.assign(part, { status: "run", error: "" });
    draft.job = job;
    store.setEph({ scriptDraft: draft });
    try {
      const partText = part.blocks.reduce((s, b, k) => k ? s + (/^\s*\|/.test(b) && /^\s*\|/.test(part.blocks[k - 1]) ? "\n" : "\n\n") + b : b, "");
      const r = await rw.scriptPart(store.project, { script: partText, part: i + 1, parts: draft.parts.length, notes: draft.notes,
        known_cast: draft.cast.map(c => ({ name: c.name, kind: c.kind })), job, can_split: part.blocks.length > 1 });
      if (r.cancelled) { part.status = "stopped"; break; }
      Object.assign(part, { status: "done", scenes: (r.scenes || []).map(s => ({ ...s, _on: true })), cast: r.cast || [], tokens: r.tokens || 0, ms: r.ms || 0, attempts: r.attempts || 1,
        warnings: Array.isArray(r.warnings) ? r.warnings.map(String) : [] });
      addCast(draft, r.cast || []);
    } catch (err) {
      if (err.reason === "cut" && part.blocks.length > 1) {
        const [a, b] = halves(part.blocks);
        draft.parts.splice(i, 1, { blocks: a, status: "wait", scenes: [], cast: [] }, { blocks: b, status: "wait", scenes: [], cast: [] });
        draft.splits += 1;
        i -= 1;
      } else {
        Object.assign(part, { status: "failed", error: err.message || "failed" });
      }
    } finally {
      delete store.eph.llmJobs[job];
    }
    draft.scenes = draft.parts.flatMap(p => p.scenes || []);
  }
  Object.assign(draft, { busy: false, stop: false, job: "" });
  for (const p of draft.parts) if (p.status === "run") p.status = "stopped";
  draft.scenes = draft.parts.flatMap(p => p.scenes || []);
  if (store.eph.scriptDraft !== draft) return; // discarded meanwhile
  store.setEph({ scriptDraft: draft });
  const failed = draft.parts.filter(p => p.status === "failed").length;
  const open = draft.parts.filter(p => p.status !== "done").length;
  const got = `${draft.scenes.length} scene${draft.scenes.length === 1 ? "" : "s"} and ${draft.cast.length} cast proposed`;
  if (failed) ctx.actions.toast(`${failed} of ${draft.parts.length} parts failed (${got}). Retry them below.`, "error");
  else if (open) ctx.actions.toast(`Stopped: ${got}. Continue picks up the remaining parts.`, "warn");
  else if (!draft.scenes.length && !draft.cast.length) ctx.actions.toast("The LLM proposed nothing for this script.", "warn");
}

function partsView(ctx, draft) {
  const n = v => Math.round(v || 0).toLocaleString("en-US");
  const many = draft.parts.length > 1;
  const rows = draft.parts.map((p, i) => {
    const first = (p.blocks[0] || "").split("\n")[0];
    const status = p.status === "done" ? `✓ ${p.scenes.length} scene${p.scenes.length === 1 ? "" : "s"} · ≈${n(p.tokens)} tokens · ${Math.round((p.ms || 0) / 1000)} s${p.attempts > 1 ? ` · ${p.attempts} tries` : ""}`
      : p.status === "run" ? ""
      : p.status === "failed" ? p.error
      : p.status === "stopped" ? "stopped" : "waiting";
    return h("div", { class: ["rw-script-part", p.status], help: "global.script.part" },
      h("span", { class: "mono rw-dim" }, many ? `Part ${i + 1}` : "Script"),
      h("span", { class: "rw-ellipsis rw-dim small mono", title: first }, first.length > 48 ? first.slice(0, 47) + "…" : first),
      p.status === "run" ? jobText(draft.job, ctx.eph.llmJobs[draft.job], { class: "small rw-dim" })
        : h("span", { class: ["small", p.status === "failed" ? "rw-c-err" : p.status === "done" ? "rw-c-aud" : "rw-dim"] }, status),
      p.status === "run" && outputButton(ctx, { job: draft.job, follow: () => (ctx.eph.scriptDraft?.busy ? ctx.eph.scriptDraft.job : null), title: "Import a script · LLM output", key: "script-out", label: false }));
  });
  const show = many || draft.parts.some(p => p.status !== "done");
  return h("div", { class: "rw-script-parts" },
    show ? rows : null,
    draft.notes && many ? h("div", { class: "rw-dim small", help: "global.script.notes", title: draft.notes }, `Sent with every part: ${draft.notes.split("\n")[0].slice(0, 90)}${draft.notes.length > 90 ? "…" : ""}`) : null,
    draft.splits ? h("div", { class: "rw-note small", help: "global.script.part" }, icon("info", 12), `${draft.splits} part${draft.splits === 1 ? " was" : "s were"} too long for the token budget and ${draft.splits === 1 ? "was" : "were"} split in two.`) : null,
    importWarnings(ctx, draft));
}

// What the backend fixed or left out of the LLM's answer (wrong types, items without a name);
// the first few lines, the rest behind "more"
function importWarnings(ctx, draft) {
  const list = draft.parts.flatMap((p, i) => (p.warnings || []).map(w => (draft.parts.length > 1 ? `Part ${i + 1}: ` : "") + w));
  if (!list.length) return null;
  const all = !!ctx.eph.scriptWarnAll;
  const shown = all ? list : list.slice(0, 4);
  return h("div", { class: "rw-note warn small rw-import-warn", help: "global.script.warnings" }, icon("warn", 12),
    h("div", { class: "grow" },
      h("b", null, `${list.length} note${list.length === 1 ? "" : "s"} on the answer: fixed or left out`),
      shown.map(w => h("div", null, w)),
      list.length > 4 && h("button", { type: "button", class: "link small", help: "global.script.warnings.more", onClick: () => ctx.store.setEph({ scriptWarnAll: !all }) },
        all ? "Show fewer" : `Show all ${list.length}`)));
}

function matrixCard(ctx) {
  const p = ctx.p;
  const keys = [...OVERRIDE_KEYS, "loras"];
  const label = { seed: "Seed", steps: "Steps", sampler: "Sampler", scheduler: "Scheduler", width: "Width", height: "Height", diffusion: "Model", text_encoder: "Text enc.", video_vae: "Video VAE", audio_vae: "Audio VAE", quality: "Quality",
    hires: "Hires", refine_steps: "Refine steps", refine_denoise: "Refine dn.", loras: "LoRAs" };
  return section({
    title: "Where scenes override Global", help: "global.matrix",
    children: h("div", { class: "rw-matrix", style: { "grid-template-columns": `90px repeat(${p.scenes.length}, minmax(22px, 1fr))` } },
      h("span", null),
      p.scenes.map((s, i) => h("button", { type: "button", class: "mono rw-dim link", help: "global.matrix.scene", onClick: () => ctx.actions.select(s.id, "scene") }, String(i + 1).padStart(2, "0"))),
      keys.map(k => [
        h("span", { class: "rw-dim small" }, label[k]),
        p.scenes.map(s => {
          const over = k === "loras" ? !!s.overrides.loras : effective(p, s, k).overridden;
          return h("span", { class: "rw-matrix-cell" }, over ? dot("override", "global.matrix.cell") : h("span", { class: "rw-dim" }, "·"));
        }),
      ])),
  });
}

function infoCard(ctx) {
  const i = ctx.eph.info;
  const row = (label, ok, textOk, textNo, help) => h("div", { class: "rw-list-row", help }, h("span", { class: ["rw-led", ok ? "ok" : "warn"] }), h("span", { class: "grow" }, label), h("span", { class: "rw-dim small" }, ok ? textOk : textNo));
  return section({
    title: "About", help: "global.info",
    actions: h("span", { class: "mono rw-dim small" }, "editor v" + VERSION),
    children: i ? [
      row("Reelwright backend", true, "v" + (i.version || "?"), "", "global.info.backend"),
      row("Native MiniMax H3 nodes", i.h3_nodes, "found", i.h3_error ? "not loaded: " + i.h3_error : "update ComfyUI", "global.info.h3"),
      row("ffmpeg", !!i.ffmpeg, typeof i.ffmpeg === "string" ? i.ffmpeg : "found", "merge needs ffmpeg on PATH", "global.info.ffmpeg"),
      row("insightface", !!i.insightface, "face checks on", i.insightface_error ? "failed to load: " + i.insightface_error : "face checks off", "global.info.insightface"),
    ] : h("div", { class: "rw-note warn" }, icon("warn", 12), "The Reelwright backend did not answer. Is the node installed and ComfyUI restarted?"),
  });
}

export function render(ctx) {
  if (!ctx.eph.llm) {
    ctx.eph.llm = {};
    rw.llmSettings().then(s => ctx.store.setEph({ llm: { ...ctx.eph.llm, ...s } })).catch(() => {});
  }
  return h("div", { class: "rw-cols", dataset: { scroll: "global-cols" } },
    h("div", { class: "rw-col flex" }, profilesCard(ctx), projectCard(ctx), modelsCard(ctx), lorasCard(ctx)),
    h("div", { class: "rw-col flex" }, outputCard(ctx), hiresCard(ctx), samplingCard(ctx), draftCard(ctx), defaultsCard(ctx)),
    h("div", { class: "rw-col flex" }, llmCard(ctx), scriptCard(ctx), matrixCard(ctx), infoCard(ctx)));
}
