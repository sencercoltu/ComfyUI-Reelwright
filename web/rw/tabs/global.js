// Global tab: models, LoRAs, output, sampling, draft, defaults, long scenes,
// LLM settings, script import and the override matrix.

// [OLD 2026-11-02 v0.2.2->v0.3.0] import { h, icon, button, toggle, segmented, select, number, text, textarea, section, field, dot } from "../ui.js";
import { h, icon, button, toggle, segmented, select, number, text, textarea, section, field, dot, confirmDialog } from "../ui.js";
import { rw } from "../api.js";
import { newJob, jobLine } from "../llmjob.js"; // added 2026-11-03 v0.4.2
import {
  ASPECTS, START_MODES, STABLE_LANGUAGES, OVERRIDE_KEYS, adaptCanvas, newId, slugify, defaultScene, effective, FPS,
  sceneIndex, // added 2026-11-02 v0.3.1
  overruns, lengthenToFit, // added 2026-11-03 v0.4.3
  nextSeedN, // added 2026-11-03 v0.6.0: a seed number per imported scene
} from "../model.js";
import { VERSION } from "../version.js";

const DTYPES = ["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"];

function modelRow(ctx, label, key, list, input, help) {
  const g = ctx.p.global.models;
  const wired = input && ctx.host.isInputLinked?.(input);
  return h("div", { class: ["rw-model", wired && "wired"] },
    h("div", { class: "rw-row" }, h("span", { class: "rw-model-label", help }, label), h("span", { class: "rw-flex" }),
      wired ? h("span", { class: "rw-badge pic", help: "global.models.wired" }, "wired input wins") : null),
    select({ options: list || [], value: g[key], placeholder: key === "latent_upscaler" ? "none (no hires pass)" : undefined, mono: true, help,
      onChange: v => ctx.actions.edit(q => { q.global.models[key] = v; }) }));
}

// added 2026-11-02 v0.3.0: saved Global settings shared by every Reelwright node on this ComfyUI
function profilesCard(ctx) {
  const pr = ctx.eph.profiles;
  // [OLD 2026-11-03 v0.5.1->v0.6.0] if (!pr) ctx.actions.loadProfiles();  (every re-render while the first GET was on its way sent another)
  // added 2026-11-03 v0.6.0: one request at a time (loadProfiles sets eph.profiles, also when the backend is offline)
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
    catch (err) { ctx.actions.toast("Profiles: " + err.message, "error"); return null; }
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

// added 2026-11-03 v0.6.0: true only when the takes of folder `slug` were read (eph.takesSlug) and it has none; takes
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
      /* [OLD 2026-11-03 v0.5.1->v0.6.0] with no takes loaded (not read yet, or another folder's) a rename moved the folder away from its renders; a new node's untitled-xxxx folder never followed the name
      field("Name", text({ value: p.name, key: "proj-name", help: "global.project.name", onChange: v => ctx.actions.edit(q => {
        const auto = q.slug === slugify(q.name);
        q.name = v;
        if (auto && !(ctx.eph.takes?.scenes && Object.keys(ctx.eph.takes.scenes).length)) q.slug = slugify(v);
      }) }), { help: "global.project.name" }),
      field("Folder", text({ value: p.slug, key: "proj-slug", mono: true, help: "global.project.slug", onChange: v => ctx.actions.edit(q => { q.slug = slugify(v); }) }), { help: "global.project.slug" }),
      [/OLD] */
      // added 2026-11-03 v0.6.0: the folder follows the name only while it is an automatic one (the slug of the name, or a
      // new node's untitled-xxxx) and the take list of this very folder has been read and holds no takes
      field("Name", text({ value: p.name, key: "proj-name", help: "global.project.name", onChange: v => ctx.actions.edit(q => {
        const auto = q.slug === slugify(q.name) || /^untitled-[a-z0-9]{4}$/.test(q.slug);
        q.name = v;
        if (auto && folderIsEmpty(ctx, q.slug)) q.slug = slugify(v);
      }, { label: "Rename project" }) }), { help: "global.project.name" }),
      field("Folder", text({ value: p.slug, key: "proj-slug", mono: true, help: "global.project.slug", onChange: v => ctx.actions.edit(q => { q.slug = slugify(v); }, { label: "Change folder" }) }), { help: "global.project.slug" }),
      h("div", { class: "rw-dim small mono", help: "global.project.slug" }, `output/reelwright/${p.slug}/ · input/reelwright/${p.slug}/`),
    ],
  });
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
      modelRow(ctx, "Latent upscaler · optional", "latent_upscaler", m.latent_upscale_models, null, "global.models.upscaler"),
    ],
  });
}

function lorasCard(ctx) {
  const list = ctx.eph.models?.loras || [];
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const edit = fn => ctx.actions.edit(q => fn(q.global.loras));  (no History menu name)
  const edit = fn => ctx.actions.edit(q => fn(q.global.loras), { label: "Global LoRAs" }); // added 2026-11-03 v0.6.0: History menu name
  const loras = ctx.p.global.loras;
  return section({
    title: "Global LoRA stack", help: "global.loras",
    actions: h("span", { class: "rw-dim small" }, "applied to every scene first"),
    children: [
      loras.length === 0 && h("div", { class: "rw-empty sm", help: "global.loras" }, "No global LoRAs."),
      loras.map((l, i) => {
        const overriders = ctx.p.scenes.filter(s => s.overrides.loras?.strengths?.[l.id] !== undefined || s.overrides.loras?.mode === "replace").length;
        /* [OLD 2026-11-03 v0.5.1->v0.6.0] no keys: after a reorder the focus went back to the row in the same position
        return h("div", { class: ["rw-lora-row", !l.enabled && "off"] },
          toggle({ value: l.enabled, help: "global.loras.enabled", onChange: v => edit(ls => { ls[i].enabled = v; }) }),
          h("div", { class: "grow" },
            select({ options: list, value: l.name, placeholder: "choose LoRA", mono: true, help: "global.loras.name", onChange: v => edit(ls => { ls[i].name = v; }) }),
            overriders > 0 && h("div", { class: "rw-c-accent small" }, `${overriders} scene${overriders > 1 ? "s" : ""} override this`)),
          number({ value: l.strength, min: -4, max: 4, step: 0.05, width: "74px", help: "global.loras.strength", onChange: v => edit(ls => { ls[i].strength = v ?? 1; }) }),
        [/OLD] */
        // added 2026-11-03 v0.6.0: stable keys (the LoRA's id) so focus stays on the same LoRA after a re-render
        return h("div", { class: ["rw-lora-row", !l.enabled && "off"] },
          toggle({ value: l.enabled, key: `glora-on-${l.id || i}`, help: "global.loras.enabled", onChange: v => edit(ls => { ls[i].enabled = v; }) }),
          h("div", { class: "grow" },
            select({ options: list, value: l.name, key: `glora-name-${l.id || i}`, placeholder: "choose LoRA", mono: true, help: "global.loras.name", onChange: v => edit(ls => { ls[i].name = v; }) }),
            overriders > 0 && h("div", { class: "rw-c-accent small" }, `${overriders} scene${overriders > 1 ? "s" : ""} override this`)),
          number({ value: l.strength, key: `glora-str-${l.id || i}`, min: -4, max: 4, step: 0.05, width: "74px", help: "global.loras.strength", onChange: v => edit(ls => { ls[i].strength = v ?? 1; }) }),
          button({ icon: "chevLeft", small: true, variant: "ghost", help: "global.loras.order", disabled: i === 0, onClick: () => edit(ls => { [ls[i - 1], ls[i]] = [ls[i], ls[i - 1]]; }) }),
          button({ icon: "trash", small: true, variant: "ghost", help: "global.loras.remove", onClick: () => edit(ls => { ls.splice(i, 1); }) }));
      }),
      button({ label: "Add LoRA", icon: "plus", small: true, help: "global.loras.add", onClick: () => edit(ls => { ls.push({ id: newId("l"), name: list[0] || "", strength: 0.8, enabled: true }); }) }),
    ],
  });
}

function outputCard(ctx) {
  const o = ctx.p.global.output;
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const set = fn => ctx.actions.edit(q => fn(q.global.output));  (no History menu name)
  const set = fn => ctx.actions.edit(q => fn(q.global.output), { label: "Output setting" }); // added 2026-11-03 v0.6.0: History menu name
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
      /* [OLD 2026-11-03 v0.6.0 review] no keys: render() found the focused one again by "the same text" and moved
         focus from the height to the width when both read 1344
      field("Width × height", h("span", { class: "rw-row" },
        number({ value: o.width, min: 32, step: 32, help: "global.output.size", onChange: v => set(x => { x.width = Math.max(32, Math.round((v ?? 32) / 32) * 32); x.aspect = "custom"; }) }),
        h("span", { class: "rw-dim" }, "×"),
        number({ value: o.height, min: 32, step: 32, help: "global.output.size", onChange: v => set(x => { x.height = Math.max(32, Math.round((v ?? 32) / 32) * 32); x.aspect = "custom"; }) })), { help: "global.output.size" }),
      [/OLD] */
      // added 2026-11-03 v0.6.0 review: keys, so a re-render puts focus back into the right one
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

function samplingCard(ctx) {
  const sm = ctx.p.global.sampling;
  const m = ctx.eph.models || {};
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const set = fn => ctx.actions.edit(q => fn(q.global.sampling));  (no History menu name)
  const set = fn => ctx.actions.edit(q => fn(q.global.sampling), { label: "Sampling setting" }); // added 2026-11-03 v0.6.0: History menu name
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
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const set = fn => ctx.actions.edit(q => fn(q.global.draft));  (no History menu name)
  const set = fn => ctx.actions.edit(q => fn(q.global.draft), { label: "Draft setting" }); // added 2026-11-03 v0.6.0: History menu name
  return section({
    title: "Draft quality", help: "global.draft",
    actions: segmented({ small: true, value: ctx.p.global.quality, help: "render.quality", options: [{ value: "draft", label: "Draft" }, { value: "final", label: "Final" }], onChange: v => ctx.actions.edit(q => { q.global.quality = v; }) }),
    children: [
      field("Resolution scale", number({ value: d.scale, min: 0.25, max: 1, step: 0.05, help: "global.draft.scale", onChange: v => set(x => { x.scale = v ?? 0.5; }) }), { help: "global.draft.scale" }),
      field("Steps", number({ value: d.steps, min: 1, max: 100, help: "global.draft.steps", onChange: v => set(x => { x.steps = v ?? 8; }) }), { help: "global.draft.steps" }),
      field("Turbo LoRA", h("span", { class: "rw-row" },
        select({ options: ctx.eph.models?.loras || [], value: d.lora, placeholder: "none", mono: true, help: "global.draft.lora", onChange: v => set(x => { x.lora = v; }) }),
        number({ value: d.lora_strength, min: -4, max: 4, step: 0.05, width: "74px", help: "global.draft.loraStrength", onChange: v => set(x => { x.lora_strength = v ?? 1; }) })), { help: "global.draft.lora" }),
    ],
  });
}

function defaultsCard(ctx) {
  const d = ctx.p.global.defaults;
  const L = ctx.p.global.long;
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const set = fn => ctx.actions.edit(q => fn(q.global.defaults));  (no History menu name)
  const set = fn => ctx.actions.edit(q => fn(q.global.defaults), { label: "New-scene default" }); // added 2026-11-03 v0.6.0: History menu name
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const setL = fn => ctx.actions.edit(q => fn(q.global.long));  (no History menu name)
  const setL = fn => ctx.actions.edit(q => fn(q.global.long), { label: "Long-scene setting" }); // added 2026-11-03 v0.6.0: History menu name
  return section({
    title: "New scenes and long scenes", help: "global.defaults",
    children: [
      field("Duration", number({ value: d.duration, min: 0.25, step: 0.25, unit: "s", help: "global.defaults.duration", onChange: v => set(x => { x.duration = v ?? 8; }) }), { help: "global.defaults.duration" }),
      field("Starts from", segmented({ small: true, value: d.start_mode, help: "global.defaults.start", options: START_MODES.map(m => ({ value: m, label: m.replace("_", " "), help: "scene.start." + m })), onChange: v => set(x => { x.start_mode = v; }) }), { help: "global.defaults.start" }),
      /* [OLD 2026-11-02 v0.1.0->v0.2.0] language is now typed or picked (free combobox)
      field("Language", select({ options: STABLE_LANGUAGES, value: d.language, help: "global.defaults.language", onChange: v => set(x => { x.language = v; }) }), { help: "global.defaults.language" }),
      [/OLD] */
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
    ],
  });
}

function llmCard(ctx) {
  const l = ctx.p.global.llm;
  const st = ctx.eph.llm || {};
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const set = fn => ctx.actions.edit(q => fn(q.global.llm));  (no History menu name)
  const set = fn => ctx.actions.edit(q => fn(q.global.llm), { label: "LLM setting" }); // added 2026-11-03 v0.6.0: History menu name
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
        /* [OLD 2026-11-02 v0.1.0->v0.2.0] one filterable combobox replaces the list/text switch
        st.models?.length ? select({ options: st.models, value: l.model, mono: true, help: "global.llm.model", onChange: v => { set(x => { x.model = v; }); syncServer({ model: v }); } })
          : text({ value: l.model, key: "llm-model", mono: true, placeholder: st.model || "model id", help: "global.llm.model", onChange: v => { set(x => { x.model = v; }); syncServer({ model: v }); } }),
        [/OLD] */
        select({ options: st.models || [], value: l.model, free: true, mono: true, width: "100%", placeholder: st.model ? "server default · " + st.model : "server default",
          help: "global.llm.model", onChange: v => { set(x => { x.model = v; }); syncServer({ model: v }); } }),
        button({ icon: "refresh", small: true, variant: "ghost", help: "global.llm.listModels", onClick: async () => {
          try { const r = await rw.llmModels(l.base_url); ctx.store.setEph({ llm: { ...st, models: r.models || [] } }); }
          catch (err) { ctx.store.setEph({ llm: { ...st, error: err.message } }); }
        } })), { help: "global.llm.model" }),
      field("Temperature", number({ value: l.temperature, min: 0, max: 2, step: 0.05, help: "global.llm.temperature", onChange: v => set(x => { x.temperature = v ?? 0.4; }) }), { help: "global.llm.temperature" }),
      // [OLD 2026-11-03 v0.4.1->v0.4.2] field("Max tokens", number({ value: l.max_tokens, min: 128, max: 32768, step: 128, help: "global.llm.maxTokens", onChange: v => set(x => { x.max_tokens = v ?? 2048; }) }), { help: "global.llm.maxTokens" }),
      field("Max tokens", number({ value: l.max_tokens, min: 128, max: 1000000, step: 128, width: "96px", help: "global.llm.maxTokens", onChange: v => set(x => { x.max_tokens = v ?? 2048; }) }), { help: "global.llm.maxTokens" }),
      // added 2026-11-02 v0.3.2: thinking models (Qwen3 and similar) can spend the whole budget reasoning
      field("Thinking", segmented({ small: true, value: l.thinking === "off" ? "off" : "auto", help: "global.llm.thinking", options: [
        { value: "auto", label: "Model default", help: "global.llm.thinking.auto" }, { value: "off", label: "Off", help: "global.llm.thinking.off" }],
      onChange: v => set(x => { x.thinking = v; }) }), { help: "global.llm.thinking" }),
      field("Preset", select({ options: [
        { value: "h3_ref2va", label: "H3 ref2va · six sections" }, { value: "h3_compact", label: "H3 · compact prose" }, { value: "h3_cinematic", label: "H3 · cinematic detail" }],
      value: l.preset, help: "global.llm.preset", onChange: v => set(x => { x.preset = v; }) }), { help: "global.llm.preset" }),
      // added 2026-11-02 v0.2.0: MiniMax's official prompt guides go into the system prompt
      guidesField(ctx, l, st, set),
      h("div", { class: "rw-row" },
        /* [OLD 2026-11-02 v0.2.2->v0.3.0] no busy state and only a tiny status in the card header, so a slow or failing server looked like "nothing happens"
        button({ label: "Test connection", small: true, help: "global.llm.test", onClick: async () => {
          try { const r = await rw.llmTest(); ctx.store.setEph({ llm: { ...st, ok: true, ms: r.ms, error: null } }); }
          catch (err) { ctx.store.setEph({ llm: { ...st, ok: false, error: err.message } }); }
        } }),
        [/OLD] */
        button({ label: st.testing ? "Testing…" : "Test connection", small: true, help: "global.llm.test", disabled: !!st.testing, onClick: async () => {
          ctx.store.setEph({ llm: { ...ctx.eph.llm, testing: true, error: null } });
          try {
            const r = await rw.llmTestProject(ctx.p);
            // [OLD 2026-11-02 v0.3.1->v0.3.2] ctx.store.setEph({ llm: { ...ctx.eph.llm, testing: false, ok: true, ms: r.ms, error: null, testedModel: r.model, testedUrl: r.base_url, reply: r.reply } });
            // [OLD 2026-11-03 v0.4.1->v0.4.2] ctx.store.setEph({ llm: { ...ctx.eph.llm, testing: false, ok: true, ms: r.ms, error: null, testedModel: r.model, testedUrl: r.base_url, reply: r.reply, note: r.note || "" } });
            ctx.store.setEph({ llm: { ...ctx.eph.llm, testing: false, ok: true, ms: r.ms, error: null, testedModel: r.model, testedUrl: r.base_url, reply: r.reply, note: r.note || "", context: r.context || 0 } });
            ctx.actions.toast(`LLM answered in ${r.ms} ms · ${r.model || "server default model"}`, "ok");
          } catch (err) {
            ctx.store.setEph({ llm: { ...ctx.eph.llm, testing: false, ok: false, error: err.message } });
            ctx.actions.toast("LLM test failed: " + err.message, "error");
          }
        } }),
        h("span", { class: "rw-dim small" }, "Only used when you press Rewrite, Split or Import — never during a render.")),
      // added 2026-11-02 v0.3.0: the result of the last test, in full
      st.ok && st.testedUrl ? h("div", { class: "rw-note ok small", help: "global.llm.status" }, icon("check", 12), `${st.testedUrl} · ${st.testedModel || "default model"} · ${st.ms} ms${st.reply ? ` · replied “${st.reply}”` : ""}`) : null,
      st.error ? h("div", { class: "rw-note err small", help: "global.llm.status" }, icon("warn", 12), st.error) : null,
      st.ok && st.note ? h("div", { class: "rw-note small", help: "global.llm.thinking" }, icon("info", 12), st.note) : null, // added 2026-11-02 v0.3.2
      // [OLD 2026-11-03 v0.5.0->v0.5.1] ...limitFields(l, st, set), // added 2026-11-03 v0.4.2
      ...limitFields(ctx, l, st, set), // added 2026-11-03 v0.4.2; ctx: v0.5.1 (the groups fold)
    ],
  });
}

// added 2026-11-03 v0.4.2: timeouts, retries, context window, and script import's own budget
// [OLD 2026-11-03 v0.5.0->v0.5.1] function limitFields(l, st, set) {
// added 2026-11-03 v0.5.1: Limits and Script import fold away (closed by default); a closed group shows its values
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
    // [OLD 2026-11-03 v0.5.0->v0.5.1] h("div", { class: "rw-subhead", help: "global.llm.limits" }, "Limits"),
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
    // [OLD 2026-11-03 v0.5.0->v0.5.1] h("div", { class: "rw-subhead", help: "global.llm.import" }, "Script import"),
    ...group("import", "Script import", "global.llm.import", importSummary, [
    field("Part size", h("span", { class: "rw-row grow" },
      number({ value: l.import_part_chars, min: 0, max: 1000000, step: 500, width: "96px", unit: "chars", help: "global.llm.importPart", onChange: v => set(x => { x.import_part_chars = v ?? 3000; }) }),
      hint(l.import_part_chars ? "a long script is sent in parts of about this size" : "0 = the whole script in one request", "global.llm.importPart")), { help: "global.llm.importPart" }),
    field("Max tokens", h("span", { class: "rw-row grow" },
      number({ value: l.import_max_tokens, min: 256, max: 1000000, step: 1024, width: "96px", unit: "tokens", help: "global.llm.importTokens", onChange: v => set(x => { x.import_max_tokens = v ?? 16384; }) }),
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

// added 2026-11-02 v0.2.0: guide status, download button and the include switch
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
  /* [OLD 2026-11-03 v0.4.1->v0.4.2] one request for the whole script; a long script timed out or came back cut off
  const run = async () => {
    const script = ctx.eph.scriptText || "";
    if (!script.trim()) { ctx.actions.toast("Paste a script first.", "warn"); return; }
    ctx.store.setEph({ scriptDraft: { busy: true } });
    try {
      const r = await rw.script(ctx.p, script);
      ctx.store.setEph({ scriptDraft: { scenes: (r.scenes || []).map(s => ({ ...s, _on: true })), cast: (r.cast || []).map(c => ({ ...c, _on: true })) } });
    } catch (err) {
      ctx.store.setEph({ scriptDraft: null });
      ctx.actions.toast("Script import failed: " + err.message, "error");
    }
  };
  [/OLD] */
  // added 2026-11-03 v0.4.2: the script is cut into parts (Global → Limits → Part size) and each part is its own request
  const run = async () => {
    const script = ctx.eph.scriptText || "";
    if (!script.trim()) { ctx.actions.toast("Paste a script first.", "warn"); return; }
    const old = ctx.store.eph.scriptDraft;
    if (old?.busy) return;
    let sp;
    try { sp = await rw.scriptParts(script, ctx.p.global.llm.import_part_chars ?? 3000); }
    catch (err) { ctx.actions.toast("Script import failed: " + err.message, "error"); return; }
    const draft = { busy: false, notes: sp.notes || "", chars: sp.chars, parts: (sp.parts || []).map(blocks => ({ blocks, status: "wait", scenes: [], cast: [] })), scenes: [], cast: [], splits: 0 };
    await runParts(ctx, draft);
  };
  const stop = () => {
    if (!draft?.busy) return;
    draft.stop = true;
    if (draft.job) rw.llmCancel(draft.job).catch(() => {});
    ctx.store.setEph({ scriptDraft: draft });
  };
  /* [OLD 2026-11-02 v0.3.0->v0.3.1] scenes were always appended at the end
  const apply = () => {
    ctx.actions.edit(p => {
      const ids = {};
      for (const c of p.cast) ids[c.name.toLowerCase()] = c.id;
      let sn = p.cast.filter(c => c.speaker).length;
      for (const c of draft.cast.filter(x => x._on)) {
        if (ids[(c.name || "").toLowerCase()]) continue;
        const id = newId("c");
        ids[(c.name || "").toLowerCase()] = id;
        const kind = c.kind || "character";
        p.cast.push({ id, kind, name: c.name || "Unnamed", speaker: kind === "character" ? c.speaker || "S" + (++sn) : "", description: c.description || "",
          // [OLD 2026-11-03 v0.4.0->v0.4.1] anchors: [], pack_sheet: true, outfits: [], ...
          anchors: [], pack_sheet: "auto", outfits: [], default_outfit: "", voice: "", language: c.language || p.global.defaults.language, lora: { name: "", strength: 0.8 } });
      }
      for (const s of draft.scenes.filter(x => x._on)) {
        const sc = defaultScene(p, { title: s.title || "Imported scene", duration: Number(s.duration) > 0 ? Number(s.duration) : p.global.defaults.duration });
        sc.prompt.sections.summary = s.summary || "";
        sc.prompt.sections.overall_soundscape = s.soundscape || "";
        sc.prompt.sections.non_diegetic_music = s.music || "";
        sc.shots = (s.shots || []).map(x => ({ id: newId("h"), t: Number(x.t) || 0, camera: x.camera || "", text: x.text || "" }));
        sc.dialogue = (s.dialogue || []).map(d => ({ id: newId("d"), speaker: ids[(d.speaker || "").toLowerCase()] || "", t: Number(d.t) || 0, language: d.language || p.global.defaults.language, delivery: d.delivery || "says", text: d.text || "" }));
        const names = new Set([...(s.cast || []), ...(s.dialogue || []).map(d => d.speaker)].map(n => (n || "").toLowerCase()));
        sc.cast = [...names].filter(n => ids[n]).map(n => ({ id: ids[n], outfit: "" }));
        p.scenes.push(sc);
      }
    });
    ctx.store.setEph({ scriptDraft: null });
    ctx.actions.toast("Script imported. Review the new scenes on the Timeline.", "ok");
  };
  [/OLD] */
  // added 2026-11-02 v0.3.1: where the imported scenes go: after the last scene, after the selected one, or instead of all
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
          // [OLD 2026-11-03 v0.4.0->v0.4.1] anchors: [], pack_sheet: true, outfits: [], ...
          anchors: [], pack_sheet: "auto", outfits: [], default_outfit: "", voice: "", language: c.language || p.global.defaults.language, lora: { name: "", strength: 0.8 } });
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
        // added 2026-11-03 v0.4.3: the backend already fits the length to the shots; this catches anything left
        sc.shots.sort((a, b) => a.t - b.t);
        if (overruns(sc)) lengthenToFit(sc);
        return sc;
      });
      if (!made.length) return;
      // added 2026-11-03 v0.6.0: each imported scene gets its own seed number (defaultScene gave all of them the same
      // one, so "+1 per scene" seeds repeated). One edit, so a single Ctrl+Z undoes the import.
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
      p.ui.selected = firstId;
    // [OLD 2026-11-03 v0.5.1->v0.6.0] });  (no name in the History menu)
    }, { label: mode === "replace" ? "Replace scenes with script" : "Import script" });
    ctx.store.setEph({ scriptDraft: null });
    ctx.root.focus?.({ preventScroll: true }); // the button is gone after the re-render; keep Ctrl+Z working
    const where = mode === "replace" ? "replaced the old scenes" : mode === "insert" ? `inserted after ${selScene?.title || "the selected scene"}` : "added at the end";
    ctx.actions.toast(pickedScenes.length ? `Imported ${pickedScenes.length} scene${pickedScenes.length > 1 ? "s" : ""} (${where}). Ctrl+Z undoes this.` : "Imported the cast.", "ok");
  };
  return section({
    title: "Import a script", help: "global.script",
    children: [
      textarea({ value: ctx.eph.scriptText || "", rows: 5, mono: true, key: "script-text", help: "global.script.text", placeholder: "Paste a screenplay (Fountain or plain text). The LLM proposes scenes, shots, dialogue and cast; you choose what to add.",
        onInput: v => { ctx.eph.scriptText = v; } }),
      /* [OLD 2026-11-03 v0.4.1->v0.4.2] one busy label, no progress, no way to stop
      h("div", { class: "rw-row" }, button({ label: draft?.busy ? "Reading script…" : "Propose scenes", icon: "wand", variant: "pink", help: "global.script.run", disabled: !!draft?.busy, onClick: run }),
        draft?.scenes && button({ label: "Discard", small: true, help: "global.script.discard", onClick: () => ctx.store.setEph({ scriptDraft: null }) })),
      draft?.scenes && h("div", { class: "rw-script-review" },
      [/OLD] */
      h("div", { class: "rw-row" }, button({ label: draft?.busy ? `Reading part ${runningIndex(draft) + 1} of ${draft.parts.length}…` : "Propose scenes", icon: "wand", variant: "pink", help: "global.script.run", disabled: !!draft?.busy, onClick: run }),
        draft?.busy && button({ label: draft.stop ? "Stopping…" : "Stop", icon: "close", small: true, help: "global.script.stop", disabled: !!draft.stop, onClick: stop }),
        draft && !draft.busy && draft.parts.some(p => p.status !== "done") && button({ label: draft.parts.some(p => p.status === "failed") ? "Retry failed parts" : "Continue", icon: "refresh", small: true, help: "global.script.retry", onClick: () => runParts(ctx, draft) }),
        draft && !draft.busy && button({ label: "Discard", small: true, help: "global.script.discard", onClick: () => ctx.store.setEph({ scriptDraft: null }) })),
      draft && partsView(ctx, draft),
      draft && (draft.scenes.length > 0 || draft.cast.length > 0) && h("div", { class: "rw-script-review" },
        // [OLD 2026-11-02 v0.3.0->v0.3.1] said "1 scenes"
        // h("div", { class: "rw-subhead" }, `${draft.cast.length} cast · ${draft.scenes.length} scenes proposed`),
        h("div", { class: "rw-subhead" }, `${draft.cast.length} cast · ${draft.scenes.length} scene${draft.scenes.length === 1 ? "" : "s"} proposed`),
        draft.cast.map(c => h("label", { class: "rw-check", help: "global.script.pick" }, h("input", { type: "checkbox", checked: c._on, onChange: e => { c._on = e.target.checked; } }),
          h("b", null, c.name), h("span", { class: "rw-dim small" }, ` ${c.kind || "character"}${c.description ? " · " + c.description.slice(0, 60) : ""}`))),
        draft.scenes.map(s => h("label", { class: "rw-check", help: "global.script.pick" }, h("input", { type: "checkbox", checked: s._on, onChange: e => { s._on = e.target.checked; } }),
          // [OLD 2026-11-03 v0.4.2->v0.4.3] h("b", null, s.title || "Untitled"), h("span", { class: "rw-dim small mono" }, ` ${Number(s.duration || 0).toFixed(1)} s · ${(s.shots || []).length} shots · ${(s.dialogue || []).length} lines`))),
          h("b", null, s.title || "Untitled"), h("span", { class: "rw-dim small mono" }, ` ${Number(s.duration || 0).toFixed(1)} s · ${(s.shots || []).length} shots · ${(s.dialogue || []).length} lines`),
          s.fit_note ? h("span", { class: "rw-c-warn small", help: "global.script.fitNote" }, ` · ${s.fit_note}`) : null)), // added 2026-11-03 v0.4.3
        // [OLD 2026-11-02 v0.3.0->v0.3.1] one button that always appended: button({ label: "Add selected to the project", icon: "plus", variant: "primary", small: true, help: "global.script.apply", onClick: apply })),
      ),
      // added 2026-11-02 v0.3.1: choose where the scenes go
      // [OLD 2026-11-03 v0.4.1->v0.4.2] draft?.scenes && field("Add scenes", segmented({ small: true, value: mode, help: "global.script.mode", options: [
      draft && !draft.busy && (draft.scenes.length > 0 || draft.cast.length > 0) && field("Add scenes", segmented({ small: true, value: mode, help: "global.script.mode", options: [
        { value: "append", label: "At the end", help: "global.script.mode.append" },
        { value: "insert", label: `After ${String(sceneIndex(ctx.p, selScene?.id) + 1).padStart(2, "0")} · ${short(selScene?.title || "selected")}`, help: "global.script.mode.insert" },
        { value: "replace", label: "Replace all scenes", help: "global.script.mode.replace" }],
      onChange: v => ctx.store.setEph({ scriptMode: v }) }), { help: "global.script.mode", wide: true }),
      // [OLD 2026-11-03 v0.4.1->v0.4.2] draft?.scenes && h("div", { class: "rw-row" },
      draft && !draft.busy && (draft.scenes.length > 0 || draft.cast.length > 0) && h("div", { class: "rw-row" },
        button({ label: mode === "replace" ? "Replace scenes with the selected" : "Add selected to the project", icon: mode === "replace" ? "refresh" : "plus",
          variant: mode === "replace" ? "danger" : "primary", small: true, help: "global.script.apply", onClick: apply })),
    ],
  });
}

// ---- script import in parts (added 2026-11-03 v0.4.2) ---------------------------------------------------------

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
    if (had) { if (!had.description && c.description) had.description = c.description; continue; }
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
      const r = await rw.scriptPart(store.project, { script: part.blocks.join("\n"), part: i + 1, parts: draft.parts.length, notes: draft.notes,
        known_cast: draft.cast.map(c => ({ name: c.name, kind: c.kind })), job, can_split: part.blocks.length > 1 });
      if (r.cancelled) { part.status = "stopped"; break; }
      // [OLD 2026-11-03 v0.5.1->v0.6.0] Object.assign(part, { status: "done", scenes: (r.scenes || []).map(s => ({ ...s, _on: true })), cast: r.cast || [], tokens: r.tokens || 0, ms: r.ms || 0, attempts: r.attempts || 1 });  (the answer's warnings were dropped)
      Object.assign(part, { status: "done", scenes: (r.scenes || []).map(s => ({ ...s, _on: true })), cast: r.cast || [], tokens: r.tokens || 0, ms: r.ms || 0, attempts: r.attempts || 1,
        warnings: Array.isArray(r.warnings) ? r.warnings.map(String) : [] }); // added 2026-11-03 v0.6.0: what the backend fixed or left out
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
      : p.status === "run" ? jobLine(ctx.eph.llmJobs[draft.job])
      : p.status === "failed" ? p.error
      : p.status === "stopped" ? "stopped" : "waiting";
    return h("div", { class: ["rw-script-part", p.status], help: "global.script.part" },
      h("span", { class: "mono rw-dim" }, many ? `Part ${i + 1}` : "Script"),
      h("span", { class: "rw-ellipsis rw-dim small mono", title: first }, first.length > 48 ? first.slice(0, 47) + "…" : first),
      h("span", { class: ["small", p.status === "failed" ? "rw-c-err" : p.status === "done" ? "rw-c-aud" : "rw-dim"] }, status));
  });
  const show = many || draft.parts.some(p => p.status !== "done");
  return h("div", { class: "rw-script-parts" },
    show ? rows : null,
    draft.notes && many ? h("div", { class: "rw-dim small", help: "global.script.notes", title: draft.notes }, `Sent with every part: ${draft.notes.split("\n")[0].slice(0, 90)}${draft.notes.length > 90 ? "…" : ""}`) : null,
    draft.splits ? h("div", { class: "rw-note small", help: "global.script.part" }, icon("info", 12), `${draft.splits} part${draft.splits === 1 ? " was" : "s were"} too long for the token budget and ${draft.splits === 1 ? "was" : "were"} split in two.`) : null,
    importWarnings(ctx, draft)); // added 2026-11-03 v0.6.0
}

// added 2026-11-03 v0.6.0: what the backend fixed or left out of the LLM's answer (wrong types, items without a name);
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
  // [OLD 2026-11-02 v0.2.2->v0.3.0] const label = { seed: "Seed", steps: "Steps", sampler: "Sampler", scheduler: "Scheduler", width: "Width", height: "Height", diffusion: "Model", text_encoder: "Text enc.", video_vae: "Video VAE", audio_vae: "Audio VAE", loras: "LoRAs" };
  const label = { seed: "Seed", steps: "Steps", sampler: "Sampler", scheduler: "Scheduler", width: "Width", height: "Height", diffusion: "Model", text_encoder: "Text enc.", video_vae: "Video VAE", audio_vae: "Audio VAE", quality: "Quality", loras: "LoRAs" };
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
      // [OLD 2026-11-03 v0.5.1->v0.6.0] row("Native MiniMax H3 nodes", i.h3_nodes, "found", "update ComfyUI", "global.info.h3"),  (did not say why they failed to load)
      row("Native MiniMax H3 nodes", i.h3_nodes, "found", i.h3_error ? "not loaded: " + i.h3_error : "update ComfyUI", "global.info.h3"), // added 2026-11-03 v0.6.0
      row("ffmpeg", !!i.ffmpeg, typeof i.ffmpeg === "string" ? i.ffmpeg : "found", "merge needs ffmpeg on PATH", "global.info.ffmpeg"),
      // [OLD 2026-11-03 v0.4.0->v0.4.1] row("insightface", !!i.insightface, "face checks on", "face checks off", "global.info.insightface"),
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
    // [OLD 2026-11-02 v0.2.2->v0.3.0] h("div", { class: "rw-col flex" }, projectCard(ctx), modelsCard(ctx), lorasCard(ctx)),
    h("div", { class: "rw-col flex" }, profilesCard(ctx), projectCard(ctx), modelsCard(ctx), lorasCard(ctx)),
    h("div", { class: "rw-col flex" }, outputCard(ctx), samplingCard(ctx), draftCard(ctx), defaultsCard(ctx)),
    h("div", { class: "rw-col flex" }, llmCard(ctx), scriptCard(ctx), matrixCard(ctx), infoCard(ctx)));
}
