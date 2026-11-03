// Scene tab: everything about one scene, plus its overrides of the Global tab.

import { h, icon, button, toggle, segmented, select, number, text, textarea, chip, dot, section, field, meter, keepChips, slider } from "../ui.js";
import { rw, viewURL } from "../api.js";
import { codeEditor } from "../codeedit.js";
import { sceneMenu } from "./timeline.js"; // added 2026-11-02 v0.2.2
import { highlightHTML, diffLines, unknownTags } from "../prompttext.js";
import {
  FPS, MIN_PASS_FRAMES, ROLES, SECTION_KEYS, STABLE_LANGUAGES, alignFramesUp, nearestGridFrames, framesOf, fmtTime,
  estimatePasses, sceneStarts, sceneIndex, findAsset, findCast, effective, overrideCount, retentionOptions,
  sceneBudget, tagCandidates, newId, effectiveLoras,
  castDescription, // added 2026-11-02 v0.3.4
  castPacks, sheetURL, // added 2026-11-03 v0.4.1
} from "../model.js";

const SECTION_LABEL = {
  subject_definitions: "subject_definitions", summary: "summary", retention_analysis: "retention_analysis",
  detailed_description: "detailed_description", overall_soundscape: "overall_soundscape", non_diegetic_music: "non_diegetic_music",
};
const OVERLAP_CHOICES = [22, 39, 56, 73, 90].map(f => ({ value: String(f), label: `${f} f · ${(f / FPS).toFixed(2)} s` }));

function kindClass(kind) {
  return kind === "image" ? "pic" : kind === "video" ? "vid" : "aud";
}

export function derivedTasks(p, s) {
  const tags = new Set();
  for (const r of s.refs) {
    const a = findAsset(p, r.asset);
    if (!a) continue;
    if (r.role === "reference") tags.add(a.kind === "video" && a.category === "edit_source" ? "video editing" : "reference generation");
    else tags.add("keyframe completion");
    if (a.kind === "audio") {
      const ret = r.retention || a.defaults.retention;
      tags.add(ret === "fully_copy" || ret === "partially_copy" ? "audio reuse" : "audio reference");
    }
  }
  if (s.cast.length) tags.add("reference generation");
  if (s.start.mode === "last_frame") tags.add("keyframe completion");
  if (s.start.mode === "tail") tags.add("video continuation");
  const order = ["reference generation", "keyframe completion", "video continuation", "audio reference", "audio reuse", "video editing"];
  return order.filter(t => tags.has(t));
}

function navigator(ctx) {
  const p = ctx.p;
  const s = ctx.scene;
  const i = sceneIndex(p, s.id);
  return h("div", { class: "rw-nav" },
    button({ icon: "chevLeft", help: "scene.nav.prev", disabled: i === 0, onClick: () => ctx.actions.select(p.scenes[i - 1].id) }),
    h("div", { class: "rw-nav-strip", help: "scene.nav.strip" }, p.scenes.map((x, j) => {
      const take = ctx.starredTake(x.id);
      return h("button", {
        type: "button", class: ["rw-nav-item", x.id === s.id && "on", "st-" + ctx.statusOf(x.id)], help: "scene.nav.strip",
        style: { "flex-grow": String(Math.max(0.6, x.duration)), "background-image": take?.files?.first ? `url("${viewURL(take.files.first)}")` : null },
        onClick: () => ctx.actions.select(x.id),
        menu: () => { ctx.actions.select(x.id); return sceneMenu(ctx, x); }, // added 2026-11-02 v0.2.2
      }, h("span", { class: "mono" }, String(j + 1).padStart(2, "0") + (x.id === s.id ? " · " + x.title : "")));
    })),
    button({ icon: "chevRight", help: "scene.nav.next", disabled: i === p.scenes.length - 1, onClick: () => ctx.actions.select(p.scenes[i + 1].id) }),
    h("span", { class: "rw-sep" }),
    button({ label: "Duplicate", icon: "copy", small: true, help: "timeline.duplicate", onClick: () => ctx.actions.duplicateScene(s.id) }),
    button({ label: "Delete", icon: "trash", small: true, variant: "danger-ghost", help: "timeline.delete", onClick: () => ctx.actions.deleteScene(s.id) }),
    button({ label: "Render scene", icon: "play", small: true, variant: "primary", help: "timeline.inspector.render", onClick: () => ctx.actions.run("selected", [s.id]) }));
}

function durationCard(ctx, s) {
  const p = ctx.p;
  const frames = framesOf(s.duration);
  const est = estimatePasses(s.duration, p.global.long);
  const plan = ctx.planFor(s.id);
  const { starts } = sceneStarts(p);
  const setFrames = f => ctx.actions.editScene(s.id, sc => { sc.duration = Math.max(1, f) / FPS; });
  const step = dir => {
    const g = nearestGridFrames(frames);
    const next = dir > 0 ? (g > frames ? g : g + 17) : (g < frames ? g : g - 17);
    setFrames(Math.max(5, next));
  };
  const pct = Math.min(100, (Math.min(frames, 362) - 5) / (362 - 5) * 100);
  return section({
    title: "Duration", help: "scene.duration",
    children: [
      h("div", { class: "rw-dur" },
        button({ icon: "minus", help: "scene.duration.step", onClick: () => step(-1) }),
        h("div", { class: "rw-dur-val" },
          h("input", {
            class: "rw-dur-input mono", type: "number", step: "0.01", min: "0.05", key: "dur-" + s.id, value: s.duration.toFixed(2), help: "scene.duration.input",
            onChange: e => { const v = Number(e.target.value); if (v > 0) setFrames(Math.round(v * FPS)); },
          }), h("span", null, "s"), h("span", { class: "mono rw-dim" }, frames + " f")),
        button({ icon: "plus", help: "scene.duration.step", onClick: () => step(1) })),
      h("div", { class: "rw-dur-bar", help: "scene.duration.bar" },
        h("span", { class: "rw-dur-trained" }), h("span", { class: "rw-dur-fill", style: { width: pct + "%" } })),
      h("div", { class: "rw-dur-scale mono rw-dim" }, h("span", null, "0.2 s"), h("span", { help: "scene.duration.trained" }, "trained 5.17–15.08 s"), h("span", null, "15.08 s+")),
      h("div", { class: ["rw-note", est.count > 1 ? "vid" : est.short ? "warn" : ""], help: "scene.duration.plan" },
        est.count > 1 ? `Longer than one pass: ${plan?.passes?.length || est.count} H3 passes, joined at shot cuts or with ${p.global.long.overlap_frames}-frame overlaps.`
          : est.short ? `Shorter than one pass: renders ${MIN_PASS_FRAMES} f (${(MIN_PASS_FRAMES / FPS).toFixed(2)} s) and keeps ${s.duration.toFixed(2)} s.`
            : est.trimmed ? `Renders ${alignFramesUp(frames)} f on the 17k+5 grid, trimmed to ${frames} f.` : `Exactly one pass of ${frames} f.`),
      h("div", { class: "rw-kv-grid two" },
        h("div", { class: "rw-kv", help: "scene.duration.in" }, h("span", null, "In"), h("b", { class: "mono" }, fmtTime(starts[s.id]))),
        h("div", { class: "rw-kv", help: "scene.duration.out" }, h("span", null, "Out"), h("b", { class: "mono" }, fmtTime(starts[s.id] + s.duration)))),
      est.short && shortWindow(ctx, s),
    ],
  });
}

function shortWindow(ctx, s) {
  const gen = MIN_PASS_FRAMES / FPS;
  const spare = Math.max(0, gen - s.duration);
  const inPoint = s.trim.keep === "start" ? 0 : s.trim.keep === "end" ? spare : s.trim.keep === "middle" ? spare / 2 : Math.min(spare, s.trim.in);
  return h("div", { class: "rw-short" },
    h("div", { class: "rw-field" }, h("span", { class: "rw-field-label", help: "scene.trim.keep" }, "Keep"),
      segmented({ small: true, value: s.trim.keep, help: "scene.trim.keep", options: [
        { value: "start", label: "Start", help: "scene.trim.start" }, { value: "middle", label: "Middle", help: "scene.trim.middle" },
        { value: "end", label: "End", help: "scene.trim.end" }, { value: "custom", label: "Custom", help: "scene.trim.custom" }],
      onChange: v => ctx.actions.editScene(s.id, sc => { sc.trim.keep = v; if (v === "custom") sc.trim.in = inPoint; }) })),
    h("div", { class: "rw-trimbar", help: "scene.trim.window" },
      h("span", { class: "rw-trim-win", style: { left: (inPoint / gen) * 100 + "%", width: (s.duration / gen) * 100 + "%" } })),
    s.trim.keep === "custom" && field("In point", slider({ value: Number(inPoint.toFixed(3)), min: 0, max: Number(spare.toFixed(3)), step: 1 / FPS, help: "scene.trim.in",
      format: v => v.toFixed(2) + " s", onChange: v => ctx.actions.editScene(s.id, sc => { sc.trim.in = v; }) }), { help: "scene.trim.in" }),
    h("div", { class: "rw-dim small" }, `Handles kept on disk: ${inPoint.toFixed(2)} s before, ${(spare - inPoint).toFixed(2)} s after.`));
}

function startCard(ctx, s) {
  const p = ctx.p;
  const i = sceneIndex(p, s.id);
  const prev = p.scenes[i - 1];
  const opt = (mode, title, desc, ic) => h("button", {
    type: "button", class: ["rw-opt", s.start.mode === mode && "on", "o-" + mode], help: "scene.start." + mode,
    disabled: mode !== "fresh" && !prev,
    onClick: () => ctx.actions.editScene(s.id, sc => { sc.start.mode = mode; }),
  }, h("span", { class: "rw-radio" }), h("span", { class: "rw-opt-body" }, h("b", null, icon(ic, 12), title), h("span", null, desc)));
  return section({
    title: "Starts from", help: "scene.start",
    actions: prev ? h("span", { class: "rw-dim small" }, "previous: " + prev.title) : h("span", { class: "rw-dim small" }, "first scene"),
    children: [
      opt("fresh", "Fresh start", "Hard cut. Nothing is carried over.", "cut"),
      opt("last_frame", "Last frame of previous", "Its final frame is guide frame 0 of this scene (fully preserved).", "link"),
      opt("tail", "Tail clip of previous", "Its last frames (and audio) guide the start; the overlap is trimmed in the cut.", "tail"),
      s.start.mode === "tail" && field("Overlap", select({
        options: OVERLAP_CHOICES, value: String(s.start.overlap_frames), help: "scene.start.overlap",
        onChange: v => ctx.actions.editScene(s.id, sc => { sc.start.overlap_frames = Number(v); }),
      }), { help: "scene.start.overlap" }),
      transitionFields(ctx, s, i), // added 2026-11-02 v0.3.0
    ],
  });
}

// added 2026-11-02 v0.3.0: how the cut into this scene looks in the merge (per scene; empty follows Global -> Merge)
function transitionFields(ctx, s, i) {
  if (i === 0) return null;
  const m = ctx.p.global.merge;
  if (s.start.mode !== "fresh") {
    return h("div", { class: "rw-dim small", help: "scene.transition" }, s.start.mode === "tail"
      ? "Continuous start: the merge crossfades inside the tail overlap (Global → Long scenes → Crossfade), so there is no cut transition."
      : "Continuous start: the merge drops the repeated first frame, so there is no cut transition.");
  }
  const tr = s.transition || {};
  const setT = fn => ctx.actions.editScene(s.id, sc => { sc.transition = sc.transition || { mode: "", frames: null, audio_fade_frames: null }; fn(sc.transition); });
  const mode = tr.mode || m.hard_cut;
  const label = { cut: "cut", crossfade: "crossfade", dip: "dip to black" };
  return [
    h("div", { class: "rw-subhead", help: "scene.transition" }, "Cut into this scene"),
    field("Transition", segmented({ small: true, value: tr.mode || "", help: "scene.transition.mode", options: [
      { value: "", label: `Merge default · ${label[m.hard_cut] || m.hard_cut}`, help: "scene.transition.mode" },
      { value: "cut", label: "Cut", help: "scene.transition.mode" }, { value: "crossfade", label: "Crossfade", help: "scene.transition.mode" },
      { value: "dip", label: "Dip to black", help: "scene.transition.mode" }],
    onChange: v => setT(t => { t.mode = v; }) }), { help: "scene.transition.mode", dot: tr.mode ? "override" : "global", wide: true }),
    mode !== "cut" && field("Length", number({ value: tr.frames ?? m.transition_frames, min: 0, max: 96, unit: "f", help: "scene.transition.frames",
      onChange: v => setT(t => { t.frames = v; }) }), { help: "scene.transition.frames", dot: tr.frames != null ? "override" : "global",
      reset: tr.frames != null ? () => setT(t => { t.frames = null; }) : null }),
    field("Audio fade", number({ value: tr.audio_fade_frames ?? m.audio_fade_frames, min: 0, max: 48, unit: "f", help: "scene.transition.audioFade",
      onChange: v => setT(t => { t.audio_fade_frames = v; }) }), { help: "scene.transition.audioFade", dot: tr.audio_fade_frames != null ? "override" : "global",
      reset: tr.audio_fade_frames != null ? () => setT(t => { t.audio_fade_frames = null; }) : null }),
  ];
}

function overridesCard(ctx, s) {
  const p = ctx.p;
  const models = ctx.eph.models || {};
  const set = (k, v) => ctx.actions.editScene(s.id, sc => { if (v === null || v === "" || v === undefined) delete sc.overrides[k]; else sc.overrides[k] = v; });
  const row = (k, label, ctl) => {
    const e = effective(p, s, k);
    return field(label, ctl(e), { help: "scene.override." + k, dot: e.overridden ? "override" : "global", reset: e.overridden ? () => set(k, null) : null });
  };
  const sel = (list, k) => e => select({ options: list || [], value: e.value, help: "scene.override." + k, mono: true, onChange: v => set(k, v) });
  const num = (k, opts) => e => number({ value: e.value, help: "scene.override." + k, onChange: v => set(k, v), ...opts });
  return section({
    title: "Generation", help: "scene.overrides",
    actions: overrideCount(s) ? button({ label: "Reset to Global", small: true, help: "scene.override.resetAll", onClick: () => ctx.actions.editScene(s.id, sc => { sc.overrides = {}; }) }) : h("span", { class: "rw-dim small" }, "follows Global"),
    children: [
      // added 2026-11-02 v0.3.0: draft or final for this scene only
      row("quality", "Quality", () => segmented({ small: true, value: s.overrides.quality || "", help: "scene.override.quality",
        options: [{ value: "", label: `Global · ${p.global.quality}`, help: "scene.override.quality" }, { value: "draft", label: "Draft", help: "scene.override.quality" }, { value: "final", label: "Final", help: "scene.override.quality" }],
        onChange: v => set("quality", v || null) })),
      row("seed", "Seed", num("seed", { min: 0, width: "120px" })),
      row("steps", "Steps", num("steps", { min: 1, max: 200 })),
      row("sampler", "Sampler", sel(models.samplers, "sampler")),
      row("scheduler", "Scheduler", sel(models.schedulers, "scheduler")),
      row("width", "Width", num("width", { min: 32, step: 32 })),
      row("height", "Height", num("height", { min: 32, step: 32 })),
      row("diffusion", "Diffusion model", sel(models.diffusion_models, "diffusion")),
      row("text_encoder", "Text encoder", sel(models.text_encoders, "text_encoder")),
      row("video_vae", "Video VAE", sel(models.vae, "video_vae")),
      row("audio_vae", "Audio VAE", sel(models.vae, "audio_vae")),
    ],
  });
}

function promptCard(ctx, s) {
  const p = ctx.p;
  const cands = tagCandidates(p);
  const tasks = derivedTasks(p, s);
  const all = s.prompt.mode === "raw" ? s.prompt.raw : SECTION_KEYS.map(k => s.prompt.sections[k]).join("\n");
  const unknown = unknownTags(all, cands);
  const input = (path, keyName) => ({
    key: keyName,
    candidates: cands,
    onInput: v => ctx.actions.editScene(s.id, sc => { path(sc, v); }, { coalesce: keyName, render: false }),
    onChange: () => ctx.store.notify(),
  });
  const autoT = (k, label) => toggle({ value: s.prompt.auto[k], label, help: "scene.prompt.auto." + k, onChange: v => ctx.actions.editScene(s.id, sc => { sc.prompt.auto[k] = v; }) });
  const sectionEditor = k => h("div", { class: "rw-psec" },
    h("div", { class: "rw-psec-head" }, h("span", { class: "mono rw-dim", help: "scene.prompt.section." + k }, SECTION_LABEL[k]),
      k === "subject_definitions" && autoT("subjects", "auto from cast"),
      k === "retention_analysis" && autoT("retention", "auto from refs"),
      k === "detailed_description" && autoT("shots", "auto shots + dialogue")),
    codeEditor({ value: s.prompt.sections[k], help: "scene.prompt.section." + k, minRows: k === "detailed_description" ? 4 : 2,
      placeholder: placeholderFor(k), ...input((sc, v) => { sc.prompt.sections[k] = v; }, `sec-${s.id}-${k}`) }));
  return section({
    title: "Prompt", help: "scene.prompt",
    actions: [
      segmented({ small: true, value: s.prompt.mode, help: "scene.prompt.mode", options: [
        { value: "structured", label: "Structured", help: "scene.prompt.structured" }, { value: "raw", label: "Raw", help: "scene.prompt.raw" }],
      onChange: v => ctx.actions.editScene(s.id, sc => { sc.prompt.mode = v; }) }),
    ],
    children: [
      h("div", { class: "rw-tasks", help: "scene.prompt.tasks" }, h("span", { class: "rw-dim small" }, "Task"),
        tasks.length ? tasks.map((t, i) => [i > 0 && h("span", { class: "rw-dim mono" }, "+"), chip({ label: t, kind: "accent", help: "scene.prompt.tasks" })]) : h("span", { class: "rw-dim small" }, "plain text-to-video (no references)"),
        h("span", { class: "rw-dim small" }, "· derived from references and start")),
      unknown.length > 0 && h("div", { class: "rw-note warn", help: "scene.prompt.unknown" }, icon("warn", 12), `Unknown tag${unknown.length > 1 ? "s" : ""}: ${unknown.join(", ")}. Use @P1/@V1/@A1, a cast name, or @tail.`),
      s.prompt.mode === "raw"
        ? codeEditor({ value: s.prompt.raw, help: "scene.prompt.rawEditor", minRows: 10, maxHeight: 420, placeholder: "Write the whole prompt. Refer to assets as @P1, cast as @Mara, the previous tail as @tail.", ...input((sc, v) => { sc.prompt.raw = v; }, `raw-${s.id}`) })
        : SECTION_KEYS.map(sectionEditor),
    ],
  });
}

function placeholderFor(k) {
  return {
    subject_definitions: "Extra subject notes. Cast descriptions are added automatically.",
    summary: "One or two sentences: what happens in this scene.",
    retention_analysis: "Anything to keep beyond the per-reference retention labels.",
    detailed_description: "Overall look and action. Shots and dialogue below are written in automatically.",
    overall_soundscape: "Diegetic sound: room tone, footsteps, props. No dialogue here.",
    non_diegetic_music: "Score for the audience, or N/A for no music.",
  }[k];
}

function shotsCard(ctx, s) {
  const p = ctx.p;
  const presets = p.camera_presets.map(c => c.text);
  const listId = "rw-cam-" + s.id;
  const edit = (id, fn) => ctx.actions.editScene(s.id, sc => { const x = sc.shots.find(q => q.id === id); if (x) fn(x, sc); });
  return section({
    title: "Shots", help: "scene.shots",
    actions: button({ label: "Shot", icon: "plus", small: true, help: "scene.shots.add", onClick: () => ctx.actions.editScene(s.id, sc => {
      const last = sc.shots[sc.shots.length - 1];
      const t = last ? Math.min(sc.duration - 0.5, last.t + Math.max(1, (sc.duration - last.t) / 2)) : 0;
      sc.shots.push({ id: newId("h"), t: Math.max(0, Math.round(t * FPS) / FPS), camera: "", text: "" });
      sc.shots.sort((a, b) => a.t - b.t);
    }) }),
    children: [
      h("datalist", { id: listId }, presets.map(v => h("option", { value: v }))),
      s.shots.length === 0 ? h("div", { class: "rw-empty sm", help: "scene.shots" }, "No shots: the scene is written as one continuous take.")
        : s.shots.map((sh, i) => h("div", { class: "rw-list-row shot" },
          // [OLD 2026-11-02 v0.1.0->v0.2.0] h("span", { class: "mono rw-dim", help: "scene.shots.index" }, `[Shot${i + 1}]`),  (guide writes [Shot 1])
          h("span", { class: "mono rw-dim", help: "scene.shots.index" }, `[Shot ${i + 1}]`),
          number({ value: Number(sh.t.toFixed(3)), min: 0, max: s.duration, step: 1 / FPS, width: "86px", unit: "s", help: "scene.shots.time",
            onChange: v => edit(sh.id, (x, sc) => { x.t = Math.round((v ?? 0) * FPS) / FPS; sc.shots.sort((a, b) => a.t - b.t); }) }),
          h("input", { class: "rw-input", list: listId, placeholder: "camera", value: sh.camera, key: `shot-cam-${sh.id}`, help: "scene.shots.camera",
            onChange: e => edit(sh.id, x => { x.camera = e.target.value; }) }),
          h("input", { class: "rw-input grow", placeholder: "what happens in this shot", value: sh.text, key: `shot-text-${sh.id}`, help: "scene.shots.text",
            onChange: e => edit(sh.id, x => { x.text = e.target.value; }) }),
          button({ icon: "trash", small: true, variant: "ghost", help: "scene.shots.remove", onClick: () => ctx.actions.editScene(s.id, sc => { sc.shots = sc.shots.filter(x => x.id !== sh.id); }) }))),
      s.shots.some(x => x.t > s.duration) && h("div", { class: "rw-note warn" }, "A shot starts after the end of the scene."),
    ],
  });
}

function dialogueCard(ctx, s) {
  const p = ctx.p;
  /* [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs now follow speaking order per clip (see the prompt preview)
  const speakers = p.cast.filter(c => c.kind === "character").map(c => ({ value: c.id, label: `${c.name} (${c.speaker || "S?"})` }));
  [/OLD] */
  const speakers = p.cast.filter(c => c.kind === "character").map(c => ({ value: c.id, label: c.name }));
  const langs = STABLE_LANGUAGES.map(l => ({ value: l, label: l }));
  const edit = (id, fn) => ctx.actions.editScene(s.id, sc => { const x = sc.dialogue.find(q => q.id === id); if (x) fn(x, sc); });
  return section({
    title: "Dialogue", help: "scene.dialogue",
    actions: button({ label: "Line", icon: "plus", small: true, help: "scene.dialogue.add", onClick: () => ctx.actions.editScene(s.id, sc => {
      const sp = sc.cast.find(c => findCast(p, c.id)?.kind === "character")?.id || speakers[0]?.value || "";
      sc.dialogue.push({ id: newId("d"), speaker: sp, t: Math.min(sc.duration - 0.5, 1), language: findCast(p, sp)?.language || p.global.defaults.language, delivery: "says", text: "" });
      sc.dialogue.sort((a, b) => a.t - b.t);
    }) }),
    children: [
      !speakers.length && h("div", { class: "rw-note", help: "scene.dialogue.noCast" }, "Add a character in the Cast tab to give lines a speaker and a voice."),
      s.dialogue.length === 0 ? h("div", { class: "rw-empty sm", help: "scene.dialogue" }, "No spoken lines.")
        : s.dialogue.map(d => h("div", { class: "rw-list-row dlg" },
          select({ options: speakers, value: d.speaker, placeholder: "speaker", help: "scene.dialogue.speaker", width: "130px", onChange: v => edit(d.id, x => { x.speaker = v; }) }),
          number({ value: Number(d.t.toFixed(3)), min: 0, max: s.duration, step: 1 / FPS, width: "80px", unit: "s", help: "scene.dialogue.time",
            onChange: v => edit(d.id, (x, sc) => { x.t = v ?? 0; sc.dialogue.sort((a, b) => a.t - b.t); }) }),
          /* [OLD 2026-11-02 v0.1.0->v0.2.0] language is now typed or picked (free combobox)
          select({ options: langs, value: d.language, help: "scene.dialogue.language", width: "104px", onChange: v => edit(d.id, x => { x.language = v; }) }),
          [/OLD] */
          select({ options: langs, value: d.language, free: true, help: "scene.dialogue.language", width: "104px", onChange: v => edit(d.id, x => { x.language = v; }) }),
          h("input", { class: "rw-input", style: { width: "90px" }, placeholder: "delivery", value: d.delivery, key: `dlg-del-${d.id}`, help: "scene.dialogue.delivery",
            onChange: e => edit(d.id, x => { x.delivery = e.target.value; }) }),
          h("input", { class: "rw-input grow", placeholder: "the spoken line", value: d.text, key: `dlg-text-${d.id}`, help: "scene.dialogue.text",
            onChange: e => edit(d.id, x => { x.text = e.target.value; }) }),
          button({ icon: "trash", small: true, variant: "ghost", help: "scene.dialogue.remove", onClick: () => ctx.actions.editScene(s.id, sc => { sc.dialogue = sc.dialogue.filter(x => x.id !== d.id); }) }))),
      s.dialogue.some(d => d.language && !STABLE_LANGUAGES.includes(d.language)) && h("div", { class: "rw-note" }, "Some lines use a language outside H3's 11 stable ones."),
    ],
  });
}

function previewCard(ctx, s) {
  const plan = ctx.planFor(s.id);
  const prompts = plan?.prompts || [];
  const passes = plan?.passes || [];
  const open = Math.min(ctx.eph.openPasses[s.id] || 0, Math.max(0, prompts.length - 1));
  const long = passes.length > 1 || estimatePasses(s.duration, ctx.p.global.long).count > 1;
  const overrides = s.prompt.pass_prompts || {};
  const hasOverride = overrides[String(open + 1)] !== undefined;
  return section({
    title: "What H3 receives", help: "scene.preview",
    actions: [
      long && button({ label: "Split with LLM", icon: "wand", small: true, help: "scene.preview.splitLlm", onClick: async () => {
        try {
          const res = await rw.split(ctx.p, s.id);
          ctx.actions.editScene(s.id, sc => { sc.prompt.pass_prompts = res.pass_prompts || {}; });
          ctx.actions.toast("Pass prompts written by the LLM. Edit them below.", "ok");
        } catch (err) { ctx.actions.toast("Split failed: " + err.message, "error"); }
      } }),
      long && Object.keys(overrides).length > 0 && button({ label: "Automatic split", small: true, help: "scene.preview.splitAuto", onClick: () => ctx.actions.editScene(s.id, sc => { sc.prompt.pass_prompts = {}; }) }),
    ],
    children: [
      prompts.length > 1 && h("div", { class: "rw-pass-tabs" }, prompts.map((_, i) => {
        const ps = passes[i];
        return h("button", {
          type: "button", class: ["rw-pass-tab", i === open && "on"], help: "scene.preview.pass",
          onClick: () => ctx.store.setEph({ openPasses: { ...ctx.eph.openPasses, [s.id]: i } }),
        }, `Pass ${i + 1}`, ps && h("span", { class: "mono rw-dim" }, ` ${fmtTime(ps.start, false)}–${fmtTime(ps.end, false)} · ${ps.gen_frames} f${ps.seam_before && ps.seam_before !== "none" ? " · " + ps.seam_before : ""}`),
        overrides[String(i + 1)] !== undefined && h("span", { class: "rw-c-accent" }, " ●"));
      })),
      long && hasOverride
        ? codeEditor({ value: overrides[String(open + 1)], help: "scene.preview.override", minRows: 6, maxHeight: 300, key: `pass-${s.id}-${open + 1}`, candidates: tagCandidates(ctx.p),
          onInput: v => ctx.actions.editScene(s.id, sc => { sc.prompt.pass_prompts[String(open + 1)] = v; }, { coalesce: `pass-${s.id}-${open + 1}`, render: false }),
          onChange: () => ctx.store.notify() })
        : h("pre", { class: "rw-prompt-preview mono tall", help: "scene.preview", html: prompts[open] ? highlightHTML(prompts[open]) : "" },
          prompts[open] ? null : h("span", { class: "rw-dim" }, ctx.eph.backend === "online" ? "Nothing to send yet: add a summary, shots or references." : "The exact prompt is built by the Reelwright backend; it appears here when ComfyUI is running.")),
      long && !hasOverride && prompts[open] && button({ label: "Edit this pass by hand", small: true, help: "scene.preview.override", onClick: () => ctx.actions.editScene(s.id, sc => { sc.prompt.pass_prompts[String(open + 1)] = prompts[open]; }) }),
      plan?.key && h("div", { class: "rw-dim small mono", help: "render.cacheKey" }, "cache key " + plan.key.slice(0, 16)),
    ],
  });
}

function rewriteCard(ctx, s) {
  const rwState = ctx.eph.rewrite?.scene_id === s.id ? ctx.eph.rewrite : null;
  const instr = h("input", { class: "rw-input grow", key: "rewrite-instr", placeholder: "Optional instruction, e.g. make shot 2 more intimate", help: "scene.rewrite.instruction", value: ctx.eph.rewriteInstr || "",
    onInput: e => { ctx.eph.rewriteInstr = e.target.value; } });
  const llm = ctx.p.global.llm;
  const run = async () => {
    ctx.store.setEph({ rewrite: { scene_id: s.id, busy: true } });
    try {
      const res = await rw.rewrite(ctx.p, s.id, ctx.eph.rewriteInstr || "");
      ctx.store.setEph({ rewrite: { scene_id: s.id, proposal: res, warnings: res.warnings || [], editing: false } });
    } catch (err) {
      ctx.store.setEph({ rewrite: null });
      ctx.actions.toast("Rewrite failed: " + err.message, "error");
    }
  };
  const accept = () => {
    const prop = rwState.proposal;
    ctx.actions.editScene(s.id, sc => {
      if (prop.raw !== undefined && prop.raw !== null) { sc.prompt.raw = prop.raw; sc.prompt.mode = "raw"; }
      if (prop.sections) for (const k of SECTION_KEYS) if (prop.sections[k] !== undefined) sc.prompt.sections[k] = prop.sections[k];
    });
    ctx.store.setEph({ rewrite: null });
    ctx.actions.toast("Rewrite applied. Undo with Ctrl+Z.", "ok");
  };
  let diffView = null;
  if (rwState?.proposal) {
    const prop = rwState.proposal;
    const pairs = prop.raw !== undefined && prop.raw !== null ? [["raw", s.prompt.raw, prop.raw]]
      : SECTION_KEYS.filter(k => prop.sections?.[k] !== undefined && prop.sections[k] !== s.prompt.sections[k]).map(k => [k, s.prompt.sections[k], prop.sections[k]]);
    diffView = h("div", { class: "rw-diff", help: "scene.rewrite.diff" },
      h("div", { class: "rw-dim small mono" }, `PREVIEW · ${pairs.length} section${pairs.length === 1 ? "" : "s"} changed`),
      rwState.warnings.map(w => h("div", { class: "rw-note warn" }, icon("warn", 12), w)),
      pairs.map(([k, a, b]) => h("div", { class: "rw-diff-sec" },
        h("div", { class: "mono rw-dim small" }, k),
        rwState.editing
          ? textarea({ value: b, rows: 4, mono: true, key: "rw-edit-" + k, help: "scene.rewrite.edit", onInput: v => {
            if (k === "raw") prop.raw = v; else prop.sections[k] = v;
          } })
          : diffLines(a, b).map(([op, line]) => h("div", { class: "rw-diff-line d" + (op === "+" ? "add" : op === "-" ? "del" : "eq") }, (op === "=" ? "  " : op + " ") + line)))),
      h("div", { class: "rw-row end" },
        button({ label: "Discard", small: true, help: "scene.rewrite.discard", onClick: () => ctx.store.setEph({ rewrite: null }) }),
        !rwState.editing && button({ label: "Edit before accepting", small: true, help: "scene.rewrite.edit", onClick: () => ctx.store.setEph({ rewrite: { ...rwState, editing: true } }) }),
        button({ label: "Accept", small: true, variant: "solid", help: "scene.rewrite.accept", onClick: accept })));
  }
  return section({
    title: "Prompt rewriter", help: "scene.rewrite", tint: "dlg",
    actions: h("span", { class: "mono rw-dim small", help: "global.llm" }, llm.model ? `${llm.model}` : "set up in Global → LLM"),
    children: [
      h("div", { class: "rw-row" }, instr,
        button({ label: rwState?.busy ? "Rewriting…" : "Rewrite", icon: "wand", variant: "pink", help: "scene.rewrite.run", disabled: !!rwState?.busy, onClick: run })),
      h("div", { class: "rw-dim small" }, "Runs only when you press Rewrite, never during a render. Tags and <d>…</d> lines are kept as written."),
      diffView,
    ],
  });
}

function budgetCard(ctx, s) {
  const b = sceneBudget(ctx.p, s);
  return section({
    title: "Reference budget", help: "scene.budget",
    actions: h("span", { class: ["mono small", b.files > 12 && "rw-c-warn"] }, `${b.files} / 12 files`),
    children: [
      meter({ label: "Pictures", value: b.pictures, max: 9, text: `${b.pictures} / 9`, kind: "pic", help: "scene.budget.pictures" }),
      meter({ label: "Videos", value: b.videos, max: 3, text: `${b.videos} / 3 · ${b.videoSeconds.toFixed(1)}/15 s`, kind: "vid", help: "scene.budget.videos" }),
      meter({ label: "Audio", value: Math.max(b.audio, b.audioSeconds > 15 ? 4 : 0), max: 3, text: `${b.audio} / 3 · ${b.audioSeconds.toFixed(1)}/15 s`, kind: "aud", help: "scene.budget.audio" }),
    ],
  });
}

function refsCard(ctx, s) {
  const p = ctx.p;
  const edit = (id, fn) => ctx.actions.editScene(s.id, sc => { const r = sc.refs.find(q => q.id === id); if (r) fn(r); });
  const addable = p.assets.map(a => ({ value: a.id, label: `${a.code} · ${a.name || a.file.split("/").pop()}` }));
  return section({
    title: "References", help: "scene.refs",
    actions: h("span", { class: "rw-dim small" }, "tags renumber per pass"),
    children: [
      s.refs.length === 0 && h("div", { class: "rw-empty sm", help: "scene.refs" }, "No references. Add one below or drag from the Timeline's asset bin."),
      s.refs.map(r => {
        const a = findAsset(p, r.asset);
        if (!a) return h("div", { class: "rw-note warn" }, "A reference points at a deleted asset.", button({ label: "Remove", small: true, help: "scene.refs.remove", onClick: () => ctx.actions.editScene(s.id, sc => { sc.refs = sc.refs.filter(x => x.id !== r.id); }) }));
        const kc = kindClass(a.kind);
        const ret = r.retention || a.defaults.retention;
        const overridden = (r.retention && r.retention !== a.defaults.retention) || r.role !== a.defaults.role;
        const roles = a.kind === "image" ? ROLES : ["reference"];
        return h("div", { class: ["rw-ref", overridden && "over"] },
          a.kind === "image" ? h("img", { class: "rw-ref-thumb", src: viewURL(a.file, "input"), alt: "" }) : h("span", { class: "rw-ref-thumb rw-bg-" + kc + "-soft" }, icon(a.kind, 16)),
          h("div", { class: "rw-ref-body" },
            h("div", { class: "rw-row" }, h("b", { class: "mono rw-c-" + kc }, a.code), h("b", { class: "rw-ellipsis" }, a.name || a.file.split("/").pop()),
              overridden && dot("override", "scene.refs.overridden"), h("span", { class: "rw-flex" }),
              button({ icon: "trash", small: true, variant: "ghost", help: "scene.refs.remove", onClick: () => ctx.actions.editScene(s.id, sc => { sc.refs = sc.refs.filter(x => x.id !== r.id); }) })),
            h("div", { class: "rw-row wrap" },
              select({ options: roles, value: r.role, help: "scene.refs.role", onChange: v => edit(r.id, x => { x.role = v; }) }),
              r.role === "keyframe" && number({ value: Number(r.time.toFixed(3)), min: 0, max: s.duration, step: 1 / FPS, width: "80px", unit: "s", help: "scene.refs.time", onChange: v => edit(r.id, x => { x.time = v ?? 0; }) }),
              r.role === "reference" && select({ options: retentionOptions(a.kind), value: ret, help: "scene.refs.retention", mono: true, onChange: v => edit(r.id, x => { x.retention = v === a.defaults.retention ? "" : v; }) }),
              a.kind === "video" && toggle({ value: r.soundtrack, label: "soundtrack", help: "scene.refs.soundtrack", onChange: v => edit(r.id, x => { x.soundtrack = v; }) })),
            r.role === "reference" && keepChips({ values: r.keep.length ? r.keep : a.defaults.keep, help: "scene.refs.keep", onChange: v => edit(r.id, x => { x.keep = v; }) }),
            // added 2026-11-02 v0.3.4: the asset's description as it is used here (edit it in the Assets tab)
            a.kind !== "audio" && h("button", { type: "button", class: ["rw-ref-desc link rw-ellipsis", !a.description && "empty"], help: "scene.refs.description",
              title: a.description || "", onClick: () => { ctx.store.setEph({ selectedAsset: a.id }); ctx.actions.setTab("assets"); } },
            a.description ? a.description : r.role === "reference" ? "No description: add one in the Assets tab" : "No description")));
      }),
      addable.length ? h("div", { class: "rw-row" }, select({ options: addable, value: "", placeholder: "+ Add a reference…", help: "scene.refs.add", onChange: v => {
        const a = findAsset(p, v);
        if (a) ctx.actions.editScene(s.id, sc => { sc.refs.push({ id: newId("r"), asset: a.id, role: a.defaults.role, time: 0, retention: "", keep: [], soundtrack: !!a.defaults.soundtrack }); });
      } })) : h("div", { class: "rw-dim small" }, "Upload assets in the Assets tab first."),
    ],
  });
}

function castCard(ctx, s) {
  const p = ctx.p;
  const inScene = new Set(s.cast.map(c => c.id));
  const avail = p.cast.filter(c => !inScene.has(c.id)).map(c => ({ value: c.id, label: `${c.name} · ${c.kind}` }));
  return section({
    title: "Cast in this scene", help: "scene.cast",
    children: [
      s.cast.length === 0 && h("div", { class: "rw-empty sm", help: "scene.cast" }, "Nobody from the story bible yet."),
      s.cast.map(sc => {
        const c = findCast(p, sc.id);
        if (!c) return null;
        const anchor = findAsset(p, c.anchors[0]);
        // added 2026-11-03 v0.4.1: when the anchors go as one sheet in this scene, the sheet is what is shown
        const packed = castPacks(p, s, c);
        return h("div", { class: "rw-list-row" },
          // [OLD 2026-11-03 v0.4.0->v0.4.1] anchor ? h("img", { class: "rw-avatar", src: viewURL(anchor.file, "input"), alt: "" }) : h("span", { class: "rw-avatar empty" }, icon("cast", 14)),
          packed ? h("img", { class: "rw-avatar sheet", src: ctx.host.apiURL(sheetURL(p, c, 96)), alt: "", help: "scene.cast.sheet" })
            : anchor ? h("img", { class: "rw-avatar", src: viewURL(anchor.file, "input"), alt: "" }) : h("span", { class: "rw-avatar empty" }, icon("cast", 14)),
          /* [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs are assigned per clip now
          h("div", { class: "grow" }, h("b", null, c.name), h("div", { class: "rw-dim small" }, `${c.kind}${c.speaker ? " · " + c.speaker : ""} · ${c.anchors.length} anchor${c.anchors.length === 1 ? "" : "s"}${c.lora?.name ? " · LoRA" : ""}`)),
          [/OLD] */
          /* [OLD 2026-11-02 v0.3.3->v0.3.4] no description shown
          h("div", { class: "grow" }, h("b", null, c.name), h("div", { class: "rw-dim small" }, `${c.kind} · ${c.anchors.length} anchor${c.anchors.length === 1 ? "" : "s"}${c.lora?.name ? " · LoRA" : ""}`)),
          [/OLD] */
          (() => {
            const d = castDescription(p, c);
            return h("div", { class: "grow", style: { "min-width": "0" } }, h("b", null, c.name),
              h("div", { class: "rw-dim small" }, `${c.kind} · ${c.anchors.length} anchor${c.anchors.length === 1 ? "" : "s"}${c.lora?.name ? " · LoRA" : ""}`),
              h("div", { class: "rw-dim small rw-ellipsis", help: "scene.cast.description", title: d.text }, d.text ? (d.asset ? `from ${d.asset.code}: ${d.text}` : d.text) : "No description"));
          })(),
          c.outfits.length > 0 && select({ options: c.outfits.map(o => ({ value: o.id, label: o.name })), value: sc.outfit || c.default_outfit, help: "scene.cast.outfit",
            onChange: v => ctx.actions.editScene(s.id, x => { x.cast.find(q => q.id === c.id).outfit = v; }) }),
          button({ icon: "close", small: true, variant: "ghost", help: "scene.cast.remove", onClick: () => ctx.actions.editScene(s.id, x => { x.cast = x.cast.filter(q => q.id !== c.id); }) }));
      }),
      avail.length > 0 && select({ options: avail, value: "", placeholder: "+ Add from the story bible…", help: "scene.cast.add", onChange: v => {
        const c = findCast(p, v);
        if (c) ctx.actions.editScene(s.id, x => { x.cast.push({ id: c.id, outfit: c.default_outfit || "" }); });
      } }),
    ],
  });
}

function lorasCard(ctx, s) {
  const p = ctx.p;
  const o = s.overrides.loras || { mode: "add", items: [], strengths: {} };
  const loraList = ctx.eph.models?.loras || [];
  const setL = fn => ctx.actions.editScene(s.id, sc => {
    sc.overrides.loras = sc.overrides.loras || { mode: "add", items: [], strengths: {} };
    fn(sc.overrides.loras);
    const l = sc.overrides.loras;
    if (l.mode === "add" && !l.items.length && !Object.keys(l.strengths).length) delete sc.overrides.loras;
  });
  const eff = effectiveLoras(p, s);
  return section({
    title: "Scene LoRAs", help: "scene.loras",
    actions: segmented({ small: true, value: o.mode, help: "scene.loras.mode", options: [
      { value: "add", label: "Add to Global", help: "scene.loras.add" }, { value: "replace", label: "Replace Global", help: "scene.loras.replace" }],
    onChange: v => setL(l => { l.mode = v; }) }),
    children: [
      o.mode !== "replace" && p.global.loras.map(gl => {
        const ov = o.strengths?.[gl.id];
        return h("div", { class: ["rw-lora-row", !gl.enabled && "off"] },
          dot(ov !== undefined ? "override" : "global"),
          h("span", { class: "mono grow rw-ellipsis" }, gl.name.replace(/\.safetensors$/, "")),
          h("span", { class: "rw-dim small" }, ov !== undefined ? `Global ${gl.strength} →` : "Global"),
          number({ value: ov ?? gl.strength, min: -4, max: 4, step: 0.05, width: "74px", help: "scene.loras.strength", onChange: v => setL(l => {
            l.strengths = l.strengths || {};
            if (v === null || v === gl.strength) delete l.strengths[gl.id]; else l.strengths[gl.id] = v;
          }) }),
          ov !== undefined ? button({ icon: "refresh", small: true, variant: "ghost", help: "common.reset", onClick: () => setL(l => { delete l.strengths[gl.id]; }) }) : h("span", { class: "rw-reset-ph" }));
      }),
      (o.items || []).map(it => h("div", { class: "rw-lora-row" },
        dot("override"),
        select({ options: loraList, value: it.name, placeholder: "choose LoRA", mono: true, help: "scene.loras.name", onChange: v => setL(l => { l.items.find(x => x.id === it.id).name = v; }) }),
        h("span", { class: "rw-dim small" }, "scene"),
        number({ value: it.strength, min: -4, max: 4, step: 0.05, width: "74px", help: "scene.loras.strength", onChange: v => setL(l => { l.items.find(x => x.id === it.id).strength = v ?? 1; }) }),
        button({ icon: "trash", small: true, variant: "ghost", help: "scene.loras.remove", onClick: () => setL(l => { l.items = l.items.filter(x => x.id !== it.id); }) }))),
      eff.filter(l => l.source === "cast").map(l => h("div", { class: "rw-lora-row" },
        dot("auto", "scene.loras.cast"), h("span", { class: "mono grow rw-ellipsis" }, l.name.replace(/\.safetensors$/, "")),
        h("span", { class: "rw-c-pic small" }, "auto · Cast: " + l.castName), h("span", { class: "mono" }, Number(l.strength).toFixed(2)))),
      button({ label: "Add LoRA", icon: "plus", small: true, help: "scene.loras.addItem", onClick: () => setL(l => { l.items.push({ id: newId("l"), name: loraList[0] || "", strength: 0.8, enabled: true }); }) }),
    ],
  });
}

function notesCard(ctx, s) {
  return section({
    title: "Scene", help: "scene.misc",
    children: [
      field("Title", text({ value: s.title, key: "title-" + s.id, help: "scene.title", onChange: v => ctx.actions.editScene(s.id, sc => { sc.title = v; }) }), { help: "scene.title" }),
      field("Lock take", toggle({ value: s.lock, help: "scene.lock", onChange: v => ctx.actions.editScene(s.id, sc => { sc.lock = v; }) }), { help: "scene.lock" }),
      field("Tint", h("input", { type: "color", class: "rw-color", value: s.color || "#3a4150", help: "scene.color", onChange: e => ctx.actions.editScene(s.id, sc => { sc.color = e.target.value; }) }), { help: "scene.color" }),
      textarea({ value: s.notes, rows: 2, key: "notes-" + s.id, placeholder: "Notes for yourself (not sent to H3)", help: "scene.notes", onChange: v => ctx.actions.editScene(s.id, sc => { sc.notes = v; }) }),
    ],
  });
}

export function render(ctx) {
  const s = ctx.scene;
  const issues = ctx.planFor(s.id)?.issues || [];
  return h("div", { class: "rw-scene-tab" },
    navigator(ctx),
    issues.length > 0 && h("div", { class: "rw-banner warn", help: "app.issues" }, icon("warn", 13), issues.map(i => i.message).join(" · ")),
    h("div", { class: "rw-cols", dataset: { scroll: "scene-cols" } },
      h("div", { class: "rw-col narrow" }, durationCard(ctx, s), startCard(ctx, s), overridesCard(ctx, s), notesCard(ctx, s)),
      h("div", { class: "rw-col wide" }, promptCard(ctx, s), shotsCard(ctx, s), dialogueCard(ctx, s), previewCard(ctx, s), rewriteCard(ctx, s)),
      h("div", { class: "rw-col mid" }, budgetCard(ctx, s), refsCard(ctx, s), castCard(ctx, s), lorasCard(ctx, s))));
}

