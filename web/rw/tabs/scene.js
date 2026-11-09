// Scene tab: everything about one scene, plus its overrides of the Global tab.

import { h, icon, button, toggle, segmented, select, number, text, textarea, chip, dot, section, field, meter, keepChips, slider } from "../ui.js";
import { choiceDialog } from "../ui.js"; // added 2026-11-05 v0.7.0: "Apply to all scenes" asks which scenes
import { confirmDialog } from "../ui.js"; // added 2026-11-12 v0.15.0: Reset scene asks first
import { resizableList, uiNum } from "../ui.js"; // added 2026-11-06 v0.9.0: shot and dialogue lists scroll in a box you can resize
import { kept } from "../ui.js"; // added 2026-11-06 v0.10.0: pictures that survive re-renders
import { copyButton } from "../ui.js"; // added 2026-11-06 v0.10.0: copy a pass prompt
import { sortable, dragGrip, moveItem } from "../ui.js"; // added 2026-11-12 v0.15.0: references, cast and LoRAs in the order you drag them to
import { seamFixes, seamFixTime } from "../passes.js"; // added 2026-11-06 v0.10.0: quick fixes for lines past a seam
// added 2026-11-05 v0.7.0: the "In the cut" card (scene.merge)
import { TRANSITIONS, DIRECTIONS, DIRECTED, mergeOf, ensureMerge, mergeDefaults, joinOf, transitionLabel } from "../cut.js";
import { rw, viewURL } from "../api.js";
import { newJob, jobLine } from "../llmjob.js"; // added 2026-11-03 v0.4.2
import { jobText } from "../llmjob.js"; // added 2026-11-06 v0.10.2: progress lines updated in place
import { outputButton } from "../llmjob.js"; // added 2026-11-12 v0.15.0: the reasoning and answer as they arrive
import { codeEditor } from "../codeedit.js";
// added 2026-11-05 v0.8.0: per-pass prompt texts, dialogue lengths, pass seams, the camera picker, "Write prompts"
import {
  passLayout, passTextsOf, adoptLayout, setPassSection, dialogueSecs, lineSeam, shotSeams, cameraOptions, framingOptions,
  runWrite, stopWrite, stillMove,
} from "../passes.js";
import { applyWritten } from "../passes.js"; // added 2026-11-06 v0.10.0: the rewriter on a pass tab
import { fillScene, fillable, fillWords } from "../shotfill.js"; // added 2026-11-12 v0.14.2: shots and lines from the description
// [OLD 2026-11-03 v0.5.1->v0.6.0] import { sceneMenu } from "./timeline.js"; // added 2026-11-02 v0.2.2
import { sceneMenu, setSceneDuration, autoRollOn } from "./timeline.js"; // added 2026-11-02 v0.2.2; v0.6.0: auto-roll
import { beatTimes } from "./soundtrack.js"; // added 2026-11-03 v0.6.0: shot times on the beat
// [OLD 2026-11-03 v0.5.1->v0.6.0] import { highlightHTML, diffLines, unknownTags } from "../prompttext.js";
import { highlightHTML, diffLines, tagMatches, looksLikeAssetCode } from "../prompttext.js";
import {
  FPS, MIN_PASS_FRAMES, ROLES, SECTION_KEYS, STABLE_LANGUAGES, alignFramesUp, nearestGridFrames, framesOf, fmtTime,
  estimatePasses, sceneStarts, sceneIndex, findAsset, findCast, effective, overrideCount, retentionOptions,
  sceneBudget, tagCandidates, newId, effectiveLoras,
  castDescription, // added 2026-11-02 v0.3.4
  castPacks, sheetURL, // added 2026-11-03 v0.4.1
  shotLengths, overruns, fitLength, lengthenToFit, squeezeToFit, // added 2026-11-03 v0.4.3
  // added 2026-11-03 v0.6.0: visible start ("In"), how a scene really starts, passes and their song part, per-pass budget
  visibleStart, effectiveStart, tailOverlapFrames, planScene, passSoundtrack,
  soundtrackLocked, // added 2026-11-05 v0.7.0: transitions play as dips while a soundtrack sets the timing
} from "../model.js";
import { assetGroupName } from "../model.js"; // added 2026-11-06 v0.9.0: the group before an asset in pickers
import { partOwner } from "../model.js"; // added 2026-11-08 v0.11.0: a prop that is part of a character
import { sceneTilePixels, SMALL_TILE_PX } from "../model.js"; // added 2026-11-12 v0.16.0: sheet pictures too small for identity
import { scenePeople } from "../model.js"; // added 2026-11-12 v0.12.0: the characters a pose reference can be for
import { refClip, refTrimmed, refTokens, snapFrame } from "../model.js"; // added 2026-11-12 v0.14.0: clips of video / audio references
import { copyWithToast } from "../ui.js"; // added 2026-11-12 v0.14.0: copy a clip's @ tag

// added 2026-11-03 v0.6.0: a render step changes nothing on this tab (status changes come with a full render), so
// progress events no longer rebuild it
export function onProgress() {}

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
  // [OLD 2026-11-03 v0.5.1->v0.6.0] const setFrames = f => ctx.actions.editScene(s.id, sc => { sc.duration = Math.max(1, f) / FPS; });
  // added 2026-11-03 v0.6.0: with Auto-roll (a soundtrack sets the timing) the next scene gives or takes the time
  const roll = autoRollOn(p) && sceneIndex(p, s.id) < p.scenes.length - 1;
  const setFrames = f => setSceneDuration(ctx, s.id, Math.max(1, f) / FPS, { roll });
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
        // [OLD 2026-11-03 v0.5.1->v0.6.0] h("div", { class: "rw-kv", help: "scene.duration.in" }, h("span", null, "In"), h("b", { class: "mono" }, fmtTime(starts[s.id]))),
        h("div", { class: "rw-kv", help: "scene.duration.in" }, h("span", null, "In"), h("b", { class: "mono" }, fmtTime(visibleStart(p, s.id) ?? starts[s.id]))),
        h("div", { class: "rw-kv", help: "scene.duration.out" }, h("span", null, "Out"), h("b", { class: "mono" }, fmtTime(starts[s.id] + s.duration)))),
      roll && h("div", { class: "rw-dim small", help: "timeline.autoRoll" }, "Auto-roll: the next scene gives or takes the time, so later scenes stay on the soundtrack."), // added 2026-11-03 v0.6.0
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
      startNote(p, s, i), // added 2026-11-03 v0.6.0
      // [OLD 2026-11-05 v0.6.1->v0.7.0] transitionFields(ctx, s, i), // added 2026-11-02 v0.3.0  (the join moved to the "In the cut" card, scene.merge)
    ],
  });
}

// added 2026-11-03 v0.6.0: when a tail start is not what the scene really gets (model.effectiveStart): re-anchored to
// the last frame, or a shorter overlap because one of the two scenes is short
function startNote(p, s, i) {
  if (i === 0 || s.start.mode !== "tail") return null;
  if (effectiveStart(p, i) !== "tail") {
    return h("div", { class: "rw-note", help: "scene.start.effective" }, icon("link", 12),
      "This scene continues from the last frame only: it is deeper in a chain of continuing scenes than Global → Continuity allows, or it or the scene before is shorter than 5 frames.");
  }
  const f = tailOverlapFrames(p, i);
  if (f < Math.trunc(s.start.overlap_frames)) {
    return h("div", { class: "rw-dim small", help: "scene.start.effective" }, `The overlap is ${f} f here (${(f / FPS).toFixed(2)} s): a tail clip can't be longer than this scene or the one before.`);
  }
  return null;
}

/* [OLD 2026-11-05 v0.6.1->v0.7.0] scene.transition with Global -> Merge defaults; replaced by cutCard (scene.merge)
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
[/OLD] */

// added 2026-11-05 v0.7.0: "In the cut": how the merge joins this scene to the one before, fades it in and out, sets
// its sound and grades its colour (scene.merge, contract B). Every edit is one named undo step; inputs have keys.
const HEX_COLOR = /^#[0-9a-f]{6}$/i;

// a frame count with its length in seconds next to it
function framesBox({ value, onChange, key, help, min = 0, max = 240 }) {
  const f = Math.max(0, Math.round(Number(value) || 0));
  return h("span", { class: "rw-frames" },
    number({ value: f, min, max, step: 1, width: "62px", unit: "f", key, help, onChange: v => onChange(v === null ? null : Math.round(v)) }),
    h("span", { class: "rw-dim small mono rw-frames-s", help }, (f / FPS).toFixed(2) + " s"));
}

function colorBox({ value, onChange, key, help, label }) {
  return h("input", { type: "color", class: "rw-color sm", value: HEX_COLOR.test(value || "") ? value.toLowerCase() : "#000000", key, help,
    "aria-label": label, title: label, onChange: e => { if (HEX_COLOR.test(e.target.value)) onChange(e.target.value.toLowerCase()); } });
}

function cutCard(ctx, s) {
  const p = ctx.p;
  const i = sceneIndex(p, s.id);
  const m = mergeOf(s);
  const D = mergeDefaults();
  const join = joinOf(p, i, s);
  const key = k => `cut-${k}-${s.id}`;
  const set = (label, fn) => ctx.actions.editScene(s.id, sc => fn(ensureMerge(sc)), { label });
  // a reset button where the value differs from a new scene's (null keeps the column aligned)
  const reset = (same, label, fn) => (same ? null : () => set(label, fn));
  const opt = { resetHelp: "scene.cut.reset" };
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const next = p.scenes[i + 1];
  const nextContinues = !!next && effectiveStart(p, i + 1) !== "fresh";
  const changed = !same(m, D);

  const transitionSelect = disabled => {
    const el = select({ options: TRANSITIONS.map(t => ({ value: t.value, label: t.label })), value: m.transition, key: key("tr"),
      help: "scene.cut.transition", width: "150px", onChange: v => set("Transition", x => { x.transition = v; }) });
    if (disabled) { el.classList.add("rw-disabled"); el.querySelectorAll("input, button").forEach(c => { c.disabled = true; }); }
    return el;
  };

  // Join: how this scene follows the one before
  const joinRows = [];
  if (join.kind === "first") {
    joinRows.push(field("Transition", transitionSelect(true), { help: "scene.cut.transition" }),
      h("div", { class: "rw-dim small", help: "scene.cut.first" }, "The first scene: nothing comes before it, so there is no join. Fades, sound and colour below still apply."));
  } else if (join.kind === "continuation") {
    joinRows.push(field("Transition", transitionSelect(true), { help: "scene.cut.transition" }),
      h("div", { class: "rw-note rw-cut-cont", help: "scene.cut.continuation" }, icon(join.mode === "tail" ? "tail" : "link", 12),
        h("span", null, join.mode === "tail"
          ? `Joins by its continuation: the ${join.overlap}-frame tail it repeats is crossfaded over ${Math.min(join.crossfade, join.overlap)} f (Global → Long scenes → Crossfade). The transition is not used.`
          : "Joins by its continuation: it starts on the last frame of the scene before, and that repeated frame is dropped. The transition is not used.")));
  } else {
    const t = m.transition;
    const overlapping = t !== "cut";
    joinRows.push(field("Transition", transitionSelect(false), { help: "scene.cut.transition",
      reset: reset(t === D.transition, "Reset transition", x => { x.transition = D.transition; }), ...opt }));
    if (DIRECTED.has(t)) {
      joinRows.push(field("Direction", segmented({ small: true, value: m.direction, key: key("dir"), help: "scene.cut.direction",
        options: DIRECTIONS.map(d => ({ value: d.value, label: d.label, help: "scene.cut.direction" })),
        onChange: v => set("Transition direction", x => { x.direction = v; }) }), { help: "scene.cut.direction" }));
    }
    if (overlapping) {
      joinRows.push(field("Length", framesBox({ value: m.frames, min: 1, max: 96, key: key("frames"), help: "scene.cut.frames",
        onChange: v => set("Transition length", x => { x.frames = v ?? D.frames; }) }),
      { help: "scene.cut.frames", reset: reset(m.frames === D.frames, "Reset transition length", x => { x.frames = D.frames; }), ...opt }));
    }
    // the dip colour: a dip, or any transition that plays as a dip under a soundtrack
    if (t === "dip" || (overlapping && join.asDip)) {
      joinRows.push(field(t === "dip" ? "Colour" : "Dip colour", colorBox({ value: m.color, key: key("color"), help: "scene.cut.color", label: "Dip colour",
        onChange: v => set("Dip colour", x => { x.color = v; }) }),
      { help: "scene.cut.color", reset: reset(m.color === D.color, "Reset dip colour", x => { x.color = D.color; }), ...opt }));
    }
    /* [OLD 2026-11-05 v0.7.0 lead review] an overlapping transition showed "Audio crossfade", but the merge crossfades the
       sound over the whole transition there and only uses audio_frames at a cut or a dip that keeps the timing
    joinRows.push(field(overlapping ? "Audio crossfade" : "Audio fade", framesBox({ value: m.audio_frames, max: 96, key: key("afr"), help: "scene.cut.audio",
      onChange: v => set(overlapping ? "Audio crossfade" : "Audio fade", x => { x.audio_frames = v ?? D.audio_frames; }) }),
    { help: "scene.cut.audio", reset: reset(m.audio_frames === D.audio_frames, "Reset audio fade", x => { x.audio_frames = D.audio_frames; }), ...opt }));
    [/OLD] */
    // added 2026-11-05 v0.7.0 lead review: the field only where the merge reads it (a cut, or a dip that keeps the timing)
    if (overlapping && !join.asDip) {
      joinRows.push(h("div", { class: "rw-note", help: "scene.cut.audio" }, "The sound crossfades over the whole transition."));
    } else {
      joinRows.push(field("Audio fade", framesBox({ value: m.audio_frames, max: 96, key: key("afr"), help: "scene.cut.audio",
        onChange: v => set("Audio fade", x => { x.audio_frames = v ?? D.audio_frames; }) }),
      { help: "scene.cut.audio", reset: reset(m.audio_frames === D.audio_frames, "Reset audio fade", x => { x.audio_frames = D.audio_frames; }), ...opt }));
    }
    if (overlapping && join.asDip) {
      joinRows.push(h("div", { class: "rw-note rw-cut-dip", help: "scene.cut.locked" }, icon("music", 12),
        h("span", null, t === "dip"
          ? "A soundtrack sets the timing, so the dip plays inside both scenes: nothing overlaps and every scene keeps its place on the song."
          : `A soundtrack sets the timing, so this ${transitionLabel(m).toLowerCase()} plays as a dip through `,
        t !== "dip" && h("span", { class: "rw-cut-swatch", style: { background: m.color } }),
        t !== "dip" && " inside both scenes: nothing overlaps and every scene keeps its place on the song.")));
    }
  }

  const fadeRow = (which, label, help, colorHelp, word) => {
    const f = m[which];
    return field(label, h("span", { class: "rw-frames" },
      framesBox({ value: f.frames, key: key(which), help, onChange: v => set(label, x => { x[which].frames = v ?? 0; }) }),
      h("span", { class: "rw-dim small" }, word),
      colorBox({ value: f.color, key: key(which + "-c"), help: colorHelp, label: label + " colour",
        onChange: v => set(label + " colour", x => { x[which].color = v; }) })),
    { help, reset: reset(same(f, D[which]), "Reset " + label.toLowerCase(), x => { x[which] = structuredClone(D[which]); }), ...opt });
  };
  const audioRow = (k, label, help) => field(label, framesBox({ value: m[k], key: key(k), help, onChange: v => set(label, x => { x[k] = v ?? 0; }) }),
    { help, reset: reset(m[k] === D[k], "Reset " + label.toLowerCase(), x => { x[k] = D[k]; }), ...opt });

  const scenes = p.scenes.filter(x => x.id !== s.id).map(x => ({ value: x.id, label: `${String(sceneIndex(p, x.id) + 1).padStart(2, "0")} · ${x.title}` }));
  const grade = (k, label, min, max, fmt) => field(label, slider({ value: Number(m[k]), min, max, step: 0.01, key: key(k), help: "scene.cut." + k, format: fmt,
    onChange: v => set(label, x => { x[k] = Math.round(v * 100) / 100; }) }),
  { help: "scene.cut." + k, reset: reset(m[k] === D[k], "Reset " + label.toLowerCase(), x => { x[k] = D[k]; }), ...opt });
  const signed = v => (v > 0 ? "+" : "") + v.toFixed(2);

  const applyAll = async () => {
    const q = ctx.p, k = sceneIndex(q, s.id), later = q.scenes.length - 1 - k;
    if (q.scenes.length < 2) return;
    const v = await choiceDialog(ctx.root, {
      title: "Apply these cut settings to other scenes?", help: "scene.cut.applyAll",
      message: `Copies this scene's join, fades, sound and colour settings to other scenes, in one undo step. Scenes that continue the one before keep joining by their continuation.`,
      cancelValue: null, focus: "all",
      choices: [
        { value: null, label: "Cancel", help: "common.cancel" },
        later > 0 && k > 0 ? { value: "after", label: `Scenes after this one (${later})`, help: "scene.cut.applyAfter" } : null,
        { value: "all", label: `All scenes (${q.scenes.length - 1} other${q.scenes.length === 2 ? "" : "s"})`, variant: "primary", help: "scene.cut.applyAll" },
      ].filter(Boolean),
    });
    if (!v) return;
    const src = mergeOf(ctx.p.scenes.find(x => x.id === s.id) || s);
    let n = 0;
    ctx.actions.edit(pq => {
      const from = sceneIndex(pq, s.id);
      pq.scenes.forEach((sc, j) => {
        if (sc.id === s.id || (v === "after" && j <= from)) return;
        const copy = structuredClone(src);
        if (copy.color_match === "scene" && copy.color_ref === sc.id) copy.color_match = "off"; // nothing to match itself to
        sc.merge = copy;
        n++;
      });
    }, { label: v === "all" ? "Cut settings → all scenes" : "Cut settings → later scenes" });
    ctx.actions.toast(`Copied the cut settings to ${n} scene${n === 1 ? "" : "s"}. Ctrl+Z undoes it.`, "ok");
  };

  return section({
    title: "In the cut", help: "scene.cut", cls: "rw-cut",
    actions: [
      changed && button({ label: "Reset", small: true, variant: "ghost", help: "scene.cut.resetAll", key: key("reset-all"),
        onClick: () => set("Reset cut settings", x => { for (const k of Object.keys(x)) delete x[k]; Object.assign(x, mergeDefaults()); }) }),
      p.scenes.length > 1 && button({ label: "Apply to all…", icon: "copy", small: true, help: "scene.cut.applyAll", key: key("apply"), onClick: applyAll }),
    ],
    children: [
      h("div", { class: "rw-subhead", help: "scene.cut.join" }, "Join"),
      ...joinRows,
      h("div", { class: "rw-subhead", help: "scene.cut.start" }, "Start"),
      fadeRow("fade_in", "Fade in", "scene.cut.fadeIn", "scene.cut.fadeInColor", "from"),
      audioRow("audio_fade_in", "Audio fade in", "scene.cut.audioFadeIn"),
      m.fade_in.frames > 0 && join.kind === "continuation" && h("div", { class: "rw-note warn", help: "scene.cut.fadeInWarn" }, icon("warn", 12),
        "This scene continues the one before: a fade in breaks the continuous join."),
      h("div", { class: "rw-subhead", help: "scene.cut.end" }, "End"),
      fadeRow("fade_out", "Fade out", "scene.cut.fadeOut", "scene.cut.fadeOutColor", "to"),
      audioRow("audio_fade_out", "Audio fade out", "scene.cut.audioFadeOut"),
      m.fade_out.frames > 0 && nextContinues && h("div", { class: "rw-note warn", help: "scene.cut.fadeOutWarn" }, icon("warn", 12),
        `${next.title} continues from this scene's end, which it takes before the fade: the cut jumps from the faded frame back to the picture.`),
      h("div", { class: "rw-subhead", help: "scene.cut.sound" }, "Sound"),
      field("Level", h("span", { class: "rw-row" },
        number({ value: m.volume_db, min: -60, max: 24, step: 0.5, /* v0.7.0 lead review: max 24 like the project file (was 12) */ width: "70px", unit: "dB", key: key("vol"), help: "scene.cut.volume",
          onChange: v => set("Scene sound level", x => { x.volume_db = v ?? 0; }) }),
        toggle({ value: m.mute, label: "Mute", key: key("mute"), help: "scene.cut.mute", onChange: v => set(v ? "Mute scene sound" : "Unmute scene sound", x => { x.mute = v; }) })),
      { help: "scene.cut.volume", reset: reset(m.volume_db === D.volume_db && m.mute === D.mute, "Reset scene sound", x => { x.volume_db = D.volume_db; x.mute = D.mute; }), ...opt }),
      h("div", { class: "rw-subhead", help: "scene.cut.colour" }, "Colour"),
      field("Match", segmented({ small: true, value: m.color_match, key: key("cm"), help: "scene.cut.colorMatch", options: [
        { value: "off", label: "Off", help: "scene.cut.colorMatch" }, { value: "previous", label: "Previous", help: "scene.cut.colorMatch.previous" },
        { value: "scene", label: "A scene", help: "scene.cut.colorMatch.scene" }],
      onChange: v => set("Colour match", x => {
        x.color_match = v;
        if (v === "scene" && (!x.color_ref || x.color_ref === s.id)) x.color_ref = ctx.p.scenes.find(y => y.id !== s.id)?.id || "";
      }) }), { help: "scene.cut.colorMatch", reset: reset(m.color_match === D.color_match, "Reset colour match", x => { x.color_match = D.color_match; x.color_ref = D.color_ref; }), ...opt }),
      m.color_match === "scene" && field("Reference", select({ options: scenes, value: m.color_ref, key: key("cref"), help: "scene.cut.colorRef", width: "190px",
        onChange: v => set("Colour match scene", x => { x.color_ref = v; }) }), { help: "scene.cut.colorRef" }),
      m.color_match === "previous" && i === 0 && h("div", { class: "rw-dim small", help: "scene.cut.colorMatch.previous" }, "The first scene has no scene before it, so it is not matched."),
      grade("brightness", "Brightness", -1, 1, signed),
      grade("contrast", "Contrast", 0, 2, v => v.toFixed(2)),
      grade("saturation", "Saturation", 0, 3, v => v.toFixed(2)),
    ],
  });
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

// [OLD 2026-11-05 v0.7.0->v0.8.0] one set of sections per scene; v0.8.0: pass tabs with their own sections (promptCard below)
// function promptCard(ctx, s) {
//   const p = ctx.p;
//   const cands = tagCandidates(p);
//   const tasks = derivedTasks(p, s);
//   const all = s.prompt.mode === "raw" ? s.prompt.raw : SECTION_KEYS.map(k => s.prompt.sections[k]).join("\n");
//   // [OLD 2026-11-03 v0.5.1->v0.6.0] const unknown = unknownTags(all, cands);
//   const tags = tagNotes(p, s, all, cands); // added 2026-11-03 v0.6.0: levels as in the backend (prompt.py)
//   const list = xs => xs.join(", ");
//   const input = (path, keyName) => ({
//     key: keyName,
//     candidates: cands,
//     onInput: v => ctx.actions.editScene(s.id, sc => { path(sc, v); }, { coalesce: keyName, render: false }),
//     onChange: () => ctx.store.notify(),
//   });
//   const autoT = (k, label) => toggle({ value: s.prompt.auto[k], label, help: "scene.prompt.auto." + k, onChange: v => ctx.actions.editScene(s.id, sc => { sc.prompt.auto[k] = v; }) });
//   const sectionEditor = k => h("div", { class: "rw-psec" },
//     h("div", { class: "rw-psec-head" }, h("span", { class: "mono rw-dim", help: "scene.prompt.section." + k }, SECTION_LABEL[k]),
//       k === "subject_definitions" && autoT("subjects", "auto from cast"),
//       k === "retention_analysis" && autoT("retention", "auto from refs"),
//       k === "detailed_description" && autoT("shots", "auto shots + dialogue")),
//     codeEditor({ value: s.prompt.sections[k], help: "scene.prompt.section." + k, minRows: k === "detailed_description" ? 4 : 2,
//       placeholder: placeholderFor(k), ...input((sc, v) => { sc.prompt.sections[k] = v; }, `sec-${s.id}-${k}`) }));
//   return section({
//     title: "Prompt", help: "scene.prompt",
//     actions: [
//       segmented({ small: true, value: s.prompt.mode, help: "scene.prompt.mode", options: [
//         { value: "structured", label: "Structured", help: "scene.prompt.structured" }, { value: "raw", label: "Raw", help: "scene.prompt.raw" }],
//       onChange: v => ctx.actions.editScene(s.id, sc => { sc.prompt.mode = v; }) }),
//     ],
//     children: [
//       h("div", { class: "rw-tasks", help: "scene.prompt.tasks" }, h("span", { class: "rw-dim small" }, "Task"),
//         tasks.length ? tasks.map((t, i) => [i > 0 && h("span", { class: "rw-dim mono" }, "+"), chip({ label: t, kind: "accent", help: "scene.prompt.tasks" })]) : h("span", { class: "rw-dim small" }, "plain text-to-video (no references)"),
//         h("span", { class: "rw-dim small" }, "· derived from references and start")),
//       // [OLD 2026-11-03 v0.5.1->v0.6.0] unknown.length > 0 && h("div", { class: "rw-note warn", help: "scene.prompt.unknown" }, icon("warn", 12), `Unknown tag${unknown.length > 1 ? "s" : ""}: ${unknown.join(", ")}. Use @P1/@V1/@A1, a cast name, or @tail.`),
//       // added 2026-11-03 v0.6.0: only a mistyped asset code stops the render; other unknown names are written as text
//       tags.errors.length > 0 && h("div", { class: "rw-note err", help: "scene.prompt.unknownCode" }, icon("warn", 12),
//         `${list(tags.errors)} ${tags.errors.length > 1 ? "match" : "matches"} no asset of this project. Check the code (the Asset bin lists them: @P1, @V1, @A1 …).`),
//       tags.warns.length > 0 && h("div", { class: "rw-note warn", help: "scene.prompt.unknown" }, icon("warn", 12),
//         `${list(tags.warns)}: not a cast member, asset or @soundtrack, so H3 gets ${tags.warns.length > 1 ? "them" : "it"} as plain text. Write @@ for a literal @.`),
//       tags.notInScene.length > 0 && h("div", { class: "rw-note warn", help: "scene.prompt.notInScene" }, icon("warn", 12),
//         `${list(tags.notInScene)} ${tags.notInScene.length > 1 ? "are" : "is"} not in this scene's cast, so only the name is written. Add ${tags.notInScene.length > 1 ? "them" : "it"} under “Cast in this scene” to send the pictures.`),
//       s.prompt.mode === "raw"
//         ? codeEditor({ value: s.prompt.raw, help: "scene.prompt.rawEditor", minRows: 10, maxHeight: 420, placeholder: "Write the whole prompt. Refer to assets as @P1, cast as @Mara, the previous tail as @tail.", ...input((sc, v) => { sc.prompt.raw = v; }, `raw-${s.id}`) })
//         : SECTION_KEYS.map(sectionEditor),
//     ],
//   });
// }
// [/OLD]
// added 2026-11-05 v0.8.0: the Prompt card (contract P4). A single-pass scene edits its six sections as before. A
// multi-pass scene gets tabs: "Whole scene" (the scene note, which is not sent, and the sections every pass shares)
// and one tab per pass ("Pass 2 · 00:14.375–00:22.000", scene times) with that pass's own six sections (empty =
// shared or automatic, shown as the placeholder), its shots and dialogue, and "Write this pass". "Write prompts"
// writes every pass with the LLM (one request per pass); each answer is one undo step.
const SECTION_NAME = {
  subject_definitions: "subject definitions", summary: "summary", retention_analysis: "retention analysis",
  detailed_description: "detailed description", overall_soundscape: "soundscape", non_diegetic_music: "music",
};

function promptCard(ctx, s) {
  const p = ctx.p;
  // [OLD 2026-11-12 v0.13.1->v0.14.0] const cands = tagCandidates(p);
  const cands = tagCandidates(p, s); // added 2026-11-12 v0.14.0: with @V1.2 ...
  const tasks = derivedTasks(p, s);
  const raw = s.prompt.mode === "raw";
  const plan = passLayout(p, s);
  const multi = plan.passes.length > 1;
  const pt = passTextsOf(p, s, plan);
  const passText = pt.stored ? pt.texts.map(t => SECTION_KEYS.map(k => t[k]).join("\n")).join("\n") : "";
  const all = raw ? s.prompt.raw : SECTION_KEYS.map(k => s.prompt.sections[k]).join("\n") + (passText ? "\n" + passText : "");
  const tags = tagNotes(p, s, all, cands);
  const list = xs => xs.join(", ");
  const input = (path, keyName, label) => ({
    key: keyName,
    candidates: cands,
    onInput: v => ctx.actions.editScene(s.id, (sc, q) => { path(sc, v, q); }, { coalesce: keyName, render: false, label }),
    onChange: () => ctx.store.notify(),
  });
  const autoT = (k, label) => toggle({ value: s.prompt.auto[k], label, help: "scene.prompt.auto." + k, key: `auto-${k}-${s.id}`,
    onChange: v => ctx.actions.editScene(s.id, sc => { sc.prompt.auto[k] = v; }, { label: (v ? "Automatic " : "No automatic ") + label.replace(/^auto /, "") }) });
  // the scene's own sections; in a multi-pass scene the summary is the whole-scene note
  /* [OLD 2026-11-12 v0.13.0->v0.13.1] "shared by every pass" even when the passes had their own text for the section
     (Write prompts), so an edit here changed nothing H3 gets; a single-pass scene never said its prompt was edited by hand
  const sectionEditor = k => h("div", { class: "rw-psec" },
    h("div", { class: "rw-psec-head" }, h("span", { class: "mono rw-dim", help: "scene.prompt.section." + k }, SECTION_LABEL[k]),
      multi && k === "summary" && h("span", { class: "rw-psec-src note", help: "scene.prompt.sceneNote" }, "whole-scene note · not sent"),
      multi && k !== "summary" && h("span", { class: "rw-psec-src", help: "scene.prompt.shared" }, "shared by every pass"),
      k === "subject_definitions" && autoT("subjects", "auto from cast"),
      k === "retention_analysis" && autoT("retention", "auto from refs"),
      k === "detailed_description" && autoT("shots", "auto shots + dialogue")),
  [/OLD] */
  // added 2026-11-12 v0.13.1: which passes use a shared section (sharedUse), and the shot lines H3 gets with the
  // description (shotLines); a duplicated scene keeps both from the scene it was copied from
  const use = multi ? sharedUse(s, plan, pt) : null;
  const lines = shotLines(s);
  const sectionEditor = k => h("div", { class: "rw-psec" },
    h("div", { class: "rw-psec-head" }, h("span", { class: "mono rw-dim", help: "scene.prompt.section." + k }, SECTION_LABEL[k]),
      multi && k === "summary" && h("span", { class: "rw-psec-src note", help: "scene.prompt.sceneNote" }, "whole-scene note · not sent"),
      multi && k !== "summary" && sharedLabel(ctx, s, use, k),
      k === "detailed_description" && lines && h("span", { class: "rw-psec-src", help: "scene.prompt.shotLines" }, lines),
      k === "subject_definitions" && autoT("subjects", "auto from cast"),
      k === "retention_analysis" && autoT("retention", "auto from refs"),
      k === "detailed_description" && autoT("shots", "auto shots + dialogue"),
      multi && k !== "summary" && sharedAllButton(ctx, s, use, k)),
    codeEditor({ value: s.prompt.sections[k], help: multi && k === "summary" ? "scene.prompt.sceneNote" : "scene.prompt.section." + k, minRows: k === "detailed_description" ? 4 : 2,
      placeholder: multi && k === "summary" ? "The whole scene in a few sentences: a note for you and the LLM. Each pass gets its own summary." : placeholderFor(k),
      ...input((sc, v) => { sc.prompt.sections[k] = v; }, `sec-${s.id}-${k}`, multi && k === "summary" ? "Scene note" : `Prompt ${SECTION_NAME[k]}`) }));

  const run = ctx.eph.passWrite;
  const busy = !!run?.running;
  const mine = busy && run.items[run.at]?.sid === s.id;
  const write = passes => runWrite(ctx, [{ sid: s.id, passes }], { origin: "scene" }).then(r => writeToast(ctx, r));
  // [OLD 2026-11-06 v0.8.0->v0.9.0] const tab = multi ? Math.max(-1, Math.min(plan.passes.length - 1, ctx.eph.promptTabs?.[s.id] ?? -1)) : -1;
  const tab = multi ? promptTabOf(ctx, s, plan, true) : -1; // added 2026-11-06 v0.9.0: one rule for every card
  const setTab = k => ctx.store.setEph({ promptTabs: { ...(ctx.eph.promptTabs || {}), [s.id]: k },
    ...(k >= 0 ? { openPasses: { ...ctx.eph.openPasses, [s.id]: k } } : {}) });

  let body;
  if (raw) {
    body = codeEditor({ value: s.prompt.raw, help: "scene.prompt.rawEditor", minRows: 10, maxHeight: 420, placeholder: "Write the whole prompt. Refer to assets as @P1, cast as @Mara, the previous tail as @tail.", ...input((sc, v) => { sc.prompt.raw = v; }, `raw-${s.id}`, "Raw prompt") });
  } else if (!multi) {
    // [OLD 2026-11-12 v0.13.0->v0.13.1] body = [singlePassNote(ctx, s, pt), SECTION_KEYS.map(sectionEditor)];
    body = [singlePassNote(ctx, s, pt), handEditedNote(ctx, s), SECTION_KEYS.map(sectionEditor)]; // added 2026-11-12 v0.13.1
  } else {
    const ownDot = k => SECTION_KEYS.some(key => pt.texts[k][key].trim());
    body = [
      pt.moved && h("div", { class: "rw-note warn rw-layout-note", help: "scene.prompt.layout" }, icon("warn", 12),
        h("span", { class: "grow" }, `The pass texts were written for another pass layout: the scene's length, its shots or Global → Long scenes changed. Each pass shows the stored text that overlaps it most${pt.movedPasses.length ? ` (pass ${pt.movedPasses.join(", ")} moved)` : ""}${pt.unused.length ? `; ${pt.unused.length} stored text${pt.unused.length === 1 ? " fits" : "s fit"} no pass now and ${pt.unused.length === 1 ? "is" : "are"} dropped by the new layout or by writing in a pass` : ""}.`),
        button({ label: "Use the new layout", small: true, variant: "warn-ghost", key: `layout-${s.id}`, help: "scene.prompt.useLayout",
          onClick: () => { ctx.actions.editScene(s.id, (sc, q) => adoptLayout(sc, q), { label: "Use the new pass layout" }); ctx.root.focus?.({ preventScroll: true }); } })),
      h("div", { class: "rw-ptabs", role: "tablist", help: "scene.prompt.tabs" },
        h("button", { type: "button", role: "tab", "aria-selected": tab < 0 ? "true" : "false", class: ["rw-ptab", tab < 0 && "on"], key: `ptab-${s.id}-scene`, help: "scene.prompt.tab.scene", onClick: () => setTab(-1) },
          h("b", null, "Whole scene")),
        plan.passes.map((ps, k) => h("button", { type: "button", role: "tab", "aria-selected": tab === k ? "true" : "false", class: ["rw-ptab", tab === k && "on", pt.movedPasses.includes(k + 1) && "moved"],
          key: `ptab-${s.id}-${k + 1}`, help: "scene.prompt.tab.pass", onClick: () => setTab(k) },
        h("b", null, `Pass ${k + 1}`), h("span", { class: "mono" }, ` · ${fmtTime(ps.start)}–${fmtTime(ps.end)}`),
        ownDot(k) && h("span", { class: "rw-ptab-dot", help: "scene.prompt.tab.pass" })))),
      tab < 0 ? SECTION_KEYS.map(sectionEditor) : passPane(ctx, s, plan, pt, tab, { cands, write, busy }),
    ];
  }
  // added 2026-11-12 v0.15.0: the Write prompts brief (scene.prompt.brief), the author's own words for the LLM, which
  // nothing the LLM writes replaces; the Brief button shows or hides it (ui.brief_open, every scene, no undo step)
  const hasBrief = !!String(s.prompt.brief || "").trim();
  const briefOpen = !raw && !!p.ui.brief_open;
  const briefBox = briefOpen && h("div", { class: "rw-psec rw-brief", help: "scene.prompt.brief" },
    h("div", { class: "rw-psec-head" }, h("span", { class: "mono rw-dim", help: "scene.prompt.brief" }, "write prompts brief"),
      h("span", { class: "rw-psec-src note", help: "scene.prompt.brief" }, "sent to the LLM · never overwritten · not sent to H3")),
    codeEditor({ value: s.prompt.brief || "", help: "scene.prompt.brief", minRows: 3, maxHeight: 300,
      placeholder: "What you want this scene to be, in your words: who does what, the mood, the lines. Write prompts reads it every time and never changes it.",
      ...input((sc, v) => { sc.prompt.brief = v; }, `brief-${s.id}`, "Write prompts brief") }));
  // added 2026-11-12 v0.15.0: Reset scene (Sencer: "add a "reset scene" button with confirmation, which clears all 6
  // sections"): the six sections and every pass's own text go, as one undo step; shots, dialogue, references, cast,
  // LoRAs, the raw prompt and the brief stay
  /* [OLD 2026-11-12 v0.16.0->v0.16.1] the shots and dialogue stayed (Sencer: "reset scene's doesn't remove the shots.")
  const sectionsUsed = SECTION_KEYS.some(k => String(s.prompt.sections[k] || "").trim()) || pt.stored ||
    Object.keys(s.prompt.pass_prompts || {}).length > 0;
  const reset = async () => {
    const ok = await confirmDialog(ctx.root, {
      title: "Reset this scene's prompt?", okLabel: "Reset scene", danger: true, help: "scene.prompt.reset",
      message: `Clears the six sections (subject definitions, summary, retention analysis, detailed description, soundscape, music)${multi || pt.stored ? " and every pass's own text" : ""}. The shots, dialogue, references, cast, LoRAs${hasBrief ? ", the Write prompts brief" : ""} and the raw prompt stay. Ctrl+Z undoes it.`,
    });
    if (!ok) return;
    ctx.actions.editScene(s.id, sc => {
      for (const k of SECTION_KEYS) sc.prompt.sections[k] = "";
      sc.prompt.passes = [];
      sc.prompt.pass_prompts = {};
    }, { label: "Reset scene" });
    ctx.actions.toast("Cleared the six sections. Ctrl+Z brings them back.", "ok");
  };
  [/OLD] */
  // added 2026-11-12 v0.16.1: the shots and the dialogue lines go too (Sencer chose "shots and dialogue"), so Write
  // prompts starts the scene from scratch; references, cast, LoRAs, the brief and the raw prompt stay
  const nShots = (s.shots || []).length, nLines = (s.dialogue || []).length;
  const sectionsUsed = SECTION_KEYS.some(k => String(s.prompt.sections[k] || "").trim()) || pt.stored ||
    Object.keys(s.prompt.pass_prompts || {}).length > 0 || nShots > 0 || nLines > 0;
  const reset = async () => {
    const what = [multi || pt.stored ? "every pass's own text" : "",
      nShots ? `the ${nShots} shot${nShots === 1 ? "" : "s"}` : "", nLines ? `the ${nLines} dialogue line${nLines === 1 ? "" : "s"}` : ""].filter(Boolean);
    const ok = await confirmDialog(ctx.root, {
      title: "Reset this scene?", okLabel: "Reset scene", danger: true, help: "scene.prompt.reset",
      message: `Clears the six sections (subject definitions, summary, retention analysis, detailed description, soundscape, music)${what.length ? ", " + what.slice(0, -1).join(", ") + (what.length > 1 ? " and " : "") + what[what.length - 1] : ""}. The references, cast, LoRAs${hasBrief ? ", the Write prompts brief" : ""} and the raw prompt stay. Ctrl+Z undoes it.`,
    });
    if (!ok) return;
    ctx.actions.editScene(s.id, sc => {
      for (const k of SECTION_KEYS) sc.prompt.sections[k] = "";
      sc.prompt.passes = [];
      sc.prompt.pass_prompts = {};
      sc.shots = [];
      sc.dialogue = [];
    }, { label: "Reset scene" });
    ctx.actions.toast("Cleared the sections, shots and dialogue. Ctrl+Z brings them back.", "ok");
  };
  return section({
    title: "Prompt", help: "scene.prompt",
    actions: [
      // added 2026-11-12 v0.15.0: Reset scene
      !raw && button({ label: "Reset scene", icon: "refresh", small: true, variant: "danger-ghost", key: `reset-${s.id}`, help: "scene.prompt.reset",
        disabled: busy || !sectionsUsed, onClick: reset }),
      // added 2026-11-12 v0.15.0: show / hide the brief; the dot says this scene has one
      !raw && button({ label: "Brief", icon: "file", small: true, variant: briefOpen ? "accent-ghost" : "ghost", key: `brief-btn-${s.id}`,
        help: "scene.prompt.briefToggle", ariaLabel: briefOpen ? "Hide the Write prompts brief" : "Show the Write prompts brief",
        extra: hasBrief && h("span", { class: "rw-ptab-dot rw-brief-dot", help: "scene.prompt.briefToggle" }),
        onClick: () => ctx.store.update(q => { q.ui.brief_open = !q.ui.brief_open; }, { history: false, plan: false, autosave: false }) }),
      // added 2026-11-12 v0.15.0: the last Write prompts output of this scene, after it ended (while it runs, the
      // progress row has the button)
      !raw && !mine && ctx.eph.lastWrite?.[s.id] && outputButton(ctx, { job: ctx.eph.lastWrite[s.id], title: "Write prompts · last LLM output", key: `write-out-last-${s.id}`, label: false }),
      !raw && button({ label: mine && !run.items[run.at]?.passes ? "Writing…" : "Write prompts", icon: "wand", small: true, variant: "pink", key: `write-${s.id}`,
        help: multi ? "scene.prompt.write" : "scene.prompt.writeOne", disabled: busy, onClick: () => write(null) }),
      segmented({ small: true, value: s.prompt.mode, help: "scene.prompt.mode", key: `pmode-${s.id}`, options: [
        { value: "structured", label: "Structured", help: "scene.prompt.structured" }, { value: "raw", label: "Raw", help: "scene.prompt.raw" }],
      onChange: v => ctx.actions.editScene(s.id, sc => { sc.prompt.mode = v; }, { label: v === "raw" ? "Raw prompt mode" : "Structured prompt mode" }) }),
    ],
    children: [
      h("div", { class: "rw-tasks", help: "scene.prompt.tasks" }, h("span", { class: "rw-dim small" }, "Task"),
        tasks.length ? tasks.map((t, i) => [i > 0 && h("span", { class: "rw-dim mono" }, "+"), chip({ label: t, kind: "accent", help: "scene.prompt.tasks" })]) : h("span", { class: "rw-dim small" }, "plain text-to-video (no references)"),
        h("span", { class: "rw-dim small" }, "· derived from references and start")),
      tags.errors.length > 0 && h("div", { class: "rw-note err", help: "scene.prompt.unknownCode" }, icon("warn", 12),
        // [OLD 2026-11-06 v0.8.0->v0.9.0] `${list(tags.errors)} ${tags.errors.length > 1 ? "match" : "matches"} no asset of this project. Check the code (the Asset bin lists them: @P1, @V1, @A1 …).`),
        `${list(tags.errors)} ${tags.errors.length > 1 ? "match" : "matches"} no asset of this project. Check the code (the Assets tab lists them: @P1, @V1, @A1 …).`),
      tags.warns.length > 0 && h("div", { class: "rw-note warn", help: "scene.prompt.unknown" }, icon("warn", 12),
        `${list(tags.warns)}: not a cast member, asset or @soundtrack, so H3 gets ${tags.warns.length > 1 ? "them" : "it"} as plain text. Write @@ for a literal @.`),
      tags.notInScene.length > 0 && h("div", { class: "rw-note warn", help: "scene.prompt.notInScene" }, icon("warn", 12),
        `${list(tags.notInScene)} ${tags.notInScene.length > 1 ? "are" : "is"} not in this scene's cast, so only the name is written. Add ${tags.notInScene.length > 1 ? "them" : "it"} under “Cast in this scene” to send the pictures.`),
      briefBox, // added 2026-11-12 v0.15.0
      mine && writeRow(ctx, run, plan),
      body,
    ],
  });
}

// added 2026-11-06 v0.9.0: the Prompt card's tab (-1 = Whole scene, k = pass k + 1). The Shots and Dialogue cards show
// only on Whole scene (a pass tab has its own rows), and What H3 receives shows the tab's pass, or every pass in turn on
// Whole scene. Single-pass scenes and raw prompts have no tabs (-1); `anyMode` gives the stored tab in raw mode too.
export function promptTabOf(ctx, s, plan = passLayout(ctx.p, s), anyMode = false) {
  if (plan.passes.length < 2 || (!anyMode && s.prompt.mode === "raw")) return -1;
  return Math.max(-1, Math.min(plan.passes.length - 1, ctx.eph.promptTabs?.[s.id] ?? -1));
}

// added 2026-11-06 v0.9.0: rows in a box that scrolls, with a grip under it to set its height (ui.shots_h for shot lists,
// ui.lines_h for dialogue, shared by the scene's cards and the pass tabs; double-click the grip for the default)
const LIST_H = { shots: ["shots_h", 380], lines: ["lines_h", 300] };
function rowsBox(ctx, kind, scroll, rows) {
  const [k, dflt] = LIST_H[kind];
  return resizableList({
    height: uiNum(ctx.p, k, dflt, 90, 2000), scroll, help: "scene.list.resize",
    onResize: v => ctx.store.update(q => { if (v === null) delete q.ui[k]; else q.ui[k] = v; }, { history: false, plan: false, autosave: false }),
    children: h("div", { class: "rw-rows" }, rows),
  });
}

// added 2026-11-05 v0.8.0: a single-pass scene whose pass texts were written when it had more passes: its one pass
// uses them, so they are shown here with a way to keep them as the scene's sections or drop them
function singlePassNote(ctx, s, pt) {
  const t = pt.texts[0];
  if (!pt.stored || !t || !SECTION_KEYS.some(k => t[k].trim())) return null;
  const used = SECTION_KEYS.filter(k => t[k].trim()).map(k => SECTION_LABEL[k]);
  return h("div", { class: "rw-note warn rw-layout-note", help: "scene.prompt.onePass" }, icon("warn", 12),
    h("span", { class: "grow" }, `Pass texts written when this scene had more passes are used for its one pass (${used.join(", ")}), not the sections below.`),
    button({ label: "Move into the sections", small: true, variant: "warn-ghost", key: `onepass-move-${s.id}`, help: "scene.prompt.onePassMove", onClick: () => {
      ctx.actions.editScene(s.id, sc => { for (const k of SECTION_KEYS) if (t[k].trim()) sc.prompt.sections[k] = t[k]; sc.prompt.passes = []; }, { label: "Pass texts → scene sections" });
      ctx.root.focus?.({ preventScroll: true });
    } }),
    button({ label: "Drop them", small: true, variant: "ghost", key: `onepass-drop-${s.id}`, help: "scene.prompt.onePassDrop", onClick: () => {
      ctx.actions.editScene(s.id, sc => { sc.prompt.passes = []; }, { label: "Drop pass texts" });
      ctx.root.focus?.({ preventScroll: true });
    } }));
}

// ---- added 2026-11-12 v0.13.1: what really reaches H3 from the Prompt card (Sencer: a duplicated scene rendered the
// original whatever he wrote in its sections). A pass uses a shared section only when it has no text of its own for it
// and its prompt is not edited by hand (model.pass_sections, prompt.build_pass); the shots and spoken lines become
// [Shot N] lines after the description while "auto shots + dialogue" is on.

// {hand: [1-based passes edited by hand], own: {section: [1-based passes with their own text]}, n}
export function sharedUse(s, plan, pt) {
  const n = plan.passes.length;
  const pp = s.prompt.pass_prompts || {};
  const hand = plan.passes.map((_, k) => k + 1).filter(k => String(pp[String(k)] ?? "").trim());
  const own = {};
  for (const key of SECTION_KEYS) own[key] = plan.passes.map((_, k) => k + 1).filter(k => !hand.includes(k) && String(pt.texts[k - 1]?.[key] ?? "").trim());
  return { hand, own, n };
}

const passList = ks => (ks.length === 1 ? "pass " : "passes ") + ks.join(", ");

// the label of a shared section on the Whole scene tab
function sharedLabel(ctx, s, use, key) {
  const own = use.own[key], hand = use.hand;
  const users = Array.from({ length: use.n }, (_, k) => k + 1).filter(k => !own.includes(k) && !hand.includes(k));
  if (users.length === use.n) return h("span", { class: "rw-psec-src", help: "scene.prompt.shared" }, "shared by every pass");
  const why = [own.length && `${passList(own)} ${own.length === 1 ? "has" : "have"} its own`, hand.length && `${passList(hand)} edited by hand`].filter(Boolean).join(", ");
  return h("span", { class: ["rw-psec-src", !users.length && "note"], help: "scene.prompt.sharedUse" },
    users.length ? `used by ${passList(users)} · ${why}` : `not used · ${why}`);
}

// "Use in every pass" (the end of the section's head) when passes have their own text for it
function sharedAllButton(ctx, s, use, key) {
  const own = use.own[key];
  if (!own.length) return null;
  return button({ label: "Use in every pass", small: true, variant: "ghost", key: `shared-all-${s.id}-${key}`, help: "scene.prompt.sharedAll",
    onClick: () => {
      ctx.actions.editScene(s.id, (sc, q) => { for (const k of own) setPassSection(sc, q, k - 1, key, ""); }, { label: `Shared ${SECTION_NAME[key]} in every pass` });
      ctx.root.focus?.({ preventScroll: true });
    } });
}

// "+ 3 shot lines, 2 spoken lines" (the Shots and Dialogue cards) when auto shots + dialogue is on, else ""
export function shotLines(s) {
  if (s.prompt.mode === "raw" || s.prompt.auto?.shots === false) return "";
  const t = x => String(x ?? "").trim();
  const shots = (s.shots || []).filter(x => t(x.text) || t(x.camera)).length;
  const lines = (s.dialogue || []).filter(x => t(x.text)).length;
  const bits = [shots && `${shots} shot line${shots === 1 ? "" : "s"}`, lines && `${lines} spoken line${lines === 1 ? "" : "s"}`].filter(Boolean);
  return bits.length ? "+ " + bits.join(", ") + " from the scene" : "";
}

// a single-pass scene whose prompt is edited by hand (What H3 receives): the sections are not used
function handEditedNote(ctx, s) {
  if (!String(s.prompt.pass_prompts?.["1"] ?? "").trim()) return null;
  return h("div", { class: "rw-note warn rw-layout-note", help: "scene.preview.override" }, icon("warn", 12),
    h("span", { class: "grow" }, "This scene's prompt is edited by hand (What H3 receives), so the sections below are not used."),
    button({ label: "Use the sections", small: true, variant: "warn-ghost", key: `hand-auto-${s.id}`, help: "scene.prompt.passAuto", onClick: () => {
      ctx.actions.editScene(s.id, sc => { delete sc.prompt.pass_prompts["1"]; }, { label: "Automatic prompt" });
      ctx.root.focus?.({ preventScroll: true });
    } }));
}

// added 2026-11-05 v0.8.0: one pass of a multi-pass scene: its own sections, its shots and dialogue (scene times)
function passPane(ctx, s, plan, pt, k, { cands, write, busy }) {
  const ps = plan.passes[k];
  const own = pt.texts[k];
  const n = k + 1;
  const handEdited = s.prompt.pass_prompts?.[String(n)] !== undefined;
  const seam = ps.seam_before === "cut" ? "starts at a shot cut"
    : ps.seam_before === "overlap" ? `continues the last ${ps.overlap_frames} f of pass ${k}` : "the scene's start";
  const shared = key => s.prompt.sections[key] || "";
  const clip = t => (t.length > 150 ? t.slice(0, 149).trimEnd() + "…" : t).replace(/\s+/g, " ");
  const placeholder = key => {
    if (key === "summary") return "Automatic: a summary of this pass made from its shots and dialogue. The scene note is not sent.";
    if (key === "detailed_description") return shared(key).trim() ? `Shared: the scene's description (its part for this pass), with this pass's shots and dialogue. ${clip(shared(key))}` : "Automatic: this pass's shots and dialogue.";
    if (shared(key).trim()) return "Shared: " + clip(shared(key));
    if (key === "subject_definitions" && s.prompt.auto.subjects) return "Automatic: a line for every cast member in the scene.";
    if (key === "retention_analysis" && s.prompt.auto.retention) return "Automatic: one line per reference.";
    return "Empty: nothing of its own (N/A).";
  };
  const passSection = key => {
    const v = own[key];
    const keyName = `psec-${s.id}-${n}-${key}`;
    const mine = v.trim() !== "";
    return h("div", { class: ["rw-psec", mine && "own"] },
      h("div", { class: "rw-psec-head" }, h("span", { class: "mono rw-dim", help: "scene.prompt.section." + key }, SECTION_LABEL[key]),
        h("span", { class: ["rw-psec-src", mine && "own"], help: "scene.prompt.passOwn" }, mine ? `pass ${n} only` : key === "summary" ? "automatic" : shared(key).trim() ? "shared" : "automatic"),
        mine && button({ label: "Use shared", small: true, variant: "ghost", key: `psec-clear-${s.id}-${n}-${key}`, help: "scene.prompt.passClear",
          onClick: () => { ctx.actions.editScene(s.id, (sc, q) => setPassSection(sc, q, k, key, ""), { label: `Pass ${n} ${SECTION_NAME[key]} → shared` }); ctx.root.focus?.({ preventScroll: true }); } })),
      codeEditor({ value: v, help: "scene.prompt.passSection", minRows: key === "detailed_description" ? (mine ? 5 : 2) : (mine ? 2 : 1), maxHeight: key === "detailed_description" ? 360 : 220,
        placeholder: placeholder(key), key: keyName, candidates: cands,
        onInput: val => ctx.actions.editScene(s.id, (sc, q) => setPassSection(sc, q, k, key, val), { coalesce: keyName, render: false, label: `Pass ${n} ${SECTION_NAME[key]}` }),
        onChange: () => ctx.store.notify() }));
  };
  const lens = shotLengths(s);
  const shotRows = ps.shots.map((x, j) => {
    const i = s.shots.findIndex(q => q.id === x.id);
    return i < 0 ? null : shotRow(ctx, s, s.shots[i], i, { plan, lens, prefix: `p${n}-`, label: `[Shot ${j + 1}]`, sceneNumber: i + 1, continuing: x.continuing });
  });
  const lineRows = ps.dialogue.map(x => {
    const d = s.dialogue.find(q => q.id === x.id);
    return d ? dialogueRow(ctx, s, d, { plan, prefix: `p${n}-` }) : null;
  });
  return h("div", { class: "rw-pass-pane", help: "scene.prompt.tab.pass" },
    h("div", { class: "rw-pass-head" },
      h("b", null, `Pass ${n} of ${plan.passes.length}`),
      h("span", { class: "mono rw-dim small" }, `${fmtTime(ps.start)}–${fmtTime(ps.end)} · ${(ps.end - ps.start).toFixed(2)} s · ${ps.gen_frames} f`),
      h("span", { class: "rw-dim small" }, "· " + seam),
      h("span", { class: "rw-flex" }),
      button({ label: busy && ctx.eph.passWrite?.items?.[ctx.eph.passWrite.at]?.passes?.[0] === n && ctx.eph.passWrite.items[ctx.eph.passWrite.at].sid === s.id ? "Writing…" : "Write this pass",
        icon: "wand", small: true, variant: "pink", key: `write-${s.id}-${n}`, help: "scene.prompt.writePass", disabled: busy, onClick: () => write([n]) })),
    handEdited && h("div", { class: "rw-note warn", help: "scene.preview.override" }, icon("warn", 12),
      h("span", { class: "grow" }, "This pass's prompt is edited by hand (What H3 receives), so these sections are not used for it."),
      button({ label: "Use the sections", small: true, variant: "warn-ghost", key: `pass-auto-${s.id}-${n}`, help: "scene.prompt.passAuto", onClick: () => {
        ctx.actions.editScene(s.id, sc => { delete sc.prompt.pass_prompts[String(n)]; }, { label: `Pass ${n}: automatic prompt` });
        ctx.root.focus?.({ preventScroll: true });
      } })),
    SECTION_KEYS.map(passSection),
    h("div", { class: "rw-subhead", help: "scene.prompt.passShots" }, `Shots in this pass (${ps.shots.length})`),
    // [OLD 2026-11-06 v0.8.0->v0.9.0] ps.shots.length ? h("div", { class: "rw-rows" }, shotRows) : h("div", { class: "rw-empty sm", help: "scene.prompt.passShots" }, "No shots: this pass is one continuous take."),
    ps.shots.length ? rowsBox(ctx, "shots", `pshots-${s.id}-${n}`, shotRows) : h("div", { class: "rw-empty sm", help: "scene.prompt.passShots" }, "No shots: this pass is one continuous take."), // added 2026-11-06 v0.9.0
    h("div", { class: "rw-subhead", help: "scene.prompt.passLines" }, `Dialogue in this pass (${ps.dialogue.length})`),
    // [OLD 2026-11-06 v0.8.0->v0.9.0] ps.dialogue.length ? h("div", { class: "rw-rows" }, lineRows) : h("div", { class: "rw-empty sm", help: "scene.prompt.passLines" }, "No spoken lines start in this pass."));
    ps.dialogue.length ? rowsBox(ctx, "lines", `plines-${s.id}-${n}`, lineRows) : h("div", { class: "rw-empty sm", help: "scene.prompt.passLines" }, "No spoken lines start in this pass.")); // added 2026-11-06 v0.9.0
}

// added 2026-11-05 v0.8.0: what the running "Write prompts" is doing (this scene), and Stop
function writeRow(ctx, run, plan) {
  const d = ctx.eph.llmJobs[run.job];
  const it = run.items[run.at];
  /* [OLD 2026-11-06 v0.10.1->v0.10.2] the text was fixed at render time (each LLM event rebuilt the tab)
  const total = d?.passes || it?.passes?.length || plan.passes.length;
  const which = d?.pass ? `pass ${d.pass} of ${total} · ` : "";
  [/OLD] */
  // added 2026-11-06 v0.10.2: editor.js rewrites the line on each progress event of the job
  const line = x => "Writing " + (x?.pass ? `pass ${x.pass} of ${x?.passes || it?.passes?.length || plan.passes.length} · ` : "") + jobLine(x);
  return h("div", { class: "rw-row rw-llm-busy", help: "scene.prompt.writeProgress" },
    // [OLD 2026-11-06 v0.10.1->v0.10.2] h("span", { class: "rw-dim small mono grow" }, "Writing " + which + jobLine(d)),
    jobText(run.job, d, { fmt: line, class: "rw-dim small mono grow" }), // added 2026-11-06 v0.10.2
    // added 2026-11-12 v0.15.0: show what the LLM thinks and writes (follows the run to its next job)
    outputButton(ctx, { job: run.job, follow: () => (ctx.eph.passWrite?.running ? ctx.eph.passWrite.job : null), title: "Write prompts · LLM output", key: "write-out" }),
    button({ label: run.stop ? "Stopping…" : "Stop", icon: "close", small: true, key: "write-stop", help: "scene.prompt.writeStop", disabled: !!run.stop, onClick: () => stopWrite(ctx) }));
}

// added 2026-11-05 v0.8.0: the toast after "Write prompts" for one scene
function writeToast(ctx, r) {
  if (!r) return;
  const it = r.items[0];
  if (!it) return;
  if (it.state === "done") ctx.actions.toast(`Wrote the prompt${r.items[0].passes?.length === 1 ? ` of pass ${r.items[0].passes[0]}` : "s"}. Ctrl+Z undoes it.`, "ok");
  else if (it.state === "stopped") ctx.actions.toast(r.wrote ? "Stopped: the passes written so far are in. Ctrl+Z undoes them." : "Writing stopped.", "warn");
  else if (it.state === "failed") ctx.actions.toast((r.wrote ? "Some passes were written, then: " : "Write prompts failed: ") + it.error, "error");
  if (it.warnings?.length) ctx.actions.toast(it.warnings.slice(0, 2).join(" · "), "warn");
}

// added 2026-11-03 v0.6.0: the tags of a prompt that need a note, by the levels prompt.py uses:
// errors: an unknown name that looks like an asset code (@P3, @V1, @A2); warns: any other unknown name (@handle), which
// is written as plain text; notInScene: a cast member who is not in this scene. @soundtrack, @song and @tail are never
// unknown. "@Mara's" is @Mara with a possessive.
function tagNotes(p, s, text, cands) {
  const key = x => String(x).replace(/’/g, "'").replace(/\s+/g, " ").trim().toLowerCase();
  const nameOf = tag => (tag.startsWith("@{") ? tag.slice(2, -1) : tag.slice(1));
  const known = new Set(cands.map(c => key(nameOf(c.tag))));
  const castByKey = new Map(p.cast.filter(c => c.name).map(c => [key(c.name), c]));
  const inScene = new Set(s.cast.map(c => c.id));
  const errors = new Set(), warns = new Set(), notInScene = new Set();
  for (const m of tagMatches(text)) {
    let k = key(m.name);
    if (k === "soundtrack" || k === "song" || k === "tail") continue;
    if (!known.has(k) && /'s$/.test(k) && known.has(k.slice(0, -2))) k = k.slice(0, -2);
    if (known.has(k)) {
      const c = castByKey.get(k);
      if (c && !inScene.has(c.id)) notInScene.add(m.tag.replace(/['’]s$/i, ""));
      continue;
    }
    (looksLikeAssetCode(m.tag) ? errors : warns).add(m.tag);
  }
  return { errors: [...errors], warns: [...warns], notInScene: [...notInScene] };
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

// [OLD 2026-11-05 v0.7.0->v0.8.0] one-line rows (start + length, camera text, one-line text); v0.8.0: shotRow below
// function shotsCard(ctx, s) {
//   const p = ctx.p;
//   const presets = p.camera_presets.map(c => c.text);
//   const listId = "rw-cam-" + s.id;
//   // [OLD 2026-11-03 v0.5.1->v0.6.0] const edit = (id, fn) => ctx.actions.editScene(s.id, sc => { const x = sc.shots.find(q => q.id === id); if (x) fn(x, sc); });
//   const edit = (id, fn, label = "Edit shot") => ctx.actions.editScene(s.id, sc => { const x = sc.shots.find(q => q.id === id); if (x) fn(x, sc); }, { label });
//   const lens = shotLengths(s); // added 2026-11-03 v0.4.3
//   const over = overruns(s);
//   // added 2026-11-03 v0.6.0: "On the beat" proposes shot start times on the soundtrack's beats (applied on click)
//   const songs = p.soundtrack.some(t => !t.mute);
//   const beatPlan = songs && ctx.eph.beatShots === s.id ? beatShotPlan(ctx, s) : null;
//   const proposed = new Map((beatPlan || []).map(m => [m.id, m]));
//   return section({
//     title: "Shots", help: "scene.shots",
//     /* [OLD 2026-11-03 v0.5.1->v0.6.0] one action
//     actions: button({ label: "Shot", icon: "plus", small: true, help: "scene.shots.add", onClick: () => ctx.actions.editScene(s.id, sc => {
//       const last = sc.shots[sc.shots.length - 1];
//       const t = last ? Math.min(sc.duration - 0.5, last.t + Math.max(1, (sc.duration - last.t) / 2)) : 0;
//       sc.shots.push({ id: newId("h"), t: Math.max(0, Math.round(t * FPS) / FPS), camera: "", text: "" });
//       sc.shots.sort((a, b) => a.t - b.t);
//     }) }),
//     [/OLD] */
//     actions: [
//       songs && s.shots.length > 0 && button({ label: "On the beat", icon: "music", small: true, help: "scene.shots.beat",
//         onClick: () => ctx.store.setEph({ beatShots: ctx.eph.beatShots === s.id ? null : s.id }) }),
//       button({ label: "Shot", icon: "plus", small: true, help: "scene.shots.add", onClick: () => ctx.actions.editScene(s.id, sc => {
//         const last = sc.shots[sc.shots.length - 1];
//         const t = last ? Math.min(sc.duration - 0.5, last.t + Math.max(1, (sc.duration - last.t) / 2)) : 0;
//         sc.shots.push({ id: newId("h"), t: Math.max(0, Math.round(t * FPS) / FPS), camera: "", text: "" });
//         sc.shots.sort((a, b) => a.t - b.t);
//       }, { label: "Add shot" }) }),
//     ],
//     children: [
//       h("datalist", { id: listId }, presets.map(v => h("option", { value: v }))),
//       ctx.eph.beatShots === s.id && songs && beatPlanNote(ctx, s, beatPlan), // added 2026-11-03 v0.6.0
//       s.shots.length === 0 ? h("div", { class: "rw-empty sm", help: "scene.shots" }, "No shots: the scene is written as one continuous take.")
//         : s.shots.map((sh, i) => h("div", { class: "rw-list-row shot" },
//           // [OLD 2026-11-02 v0.1.0->v0.2.0] h("span", { class: "mono rw-dim", help: "scene.shots.index" }, `[Shot${i + 1}]`),  (guide writes [Shot 1])
//           h("span", { class: "mono rw-dim", help: "scene.shots.index" }, `[Shot ${i + 1}]`),
//           /* [OLD 2026-11-03 v0.5.1->v0.6.0] no key: after a re-sort the caret went to the field now in this row (scene.js:282)
//           number({ value: Number(sh.t.toFixed(3)), min: 0, max: s.duration, step: 1 / FPS, width: "86px", unit: "s", help: "scene.shots.time",
//             onChange: v => edit(sh.id, (x, sc) => { x.t = Math.round((v ?? 0) * FPS) / FPS; sc.shots.sort((a, b) => a.t - b.t); }) }),
//           [/OLD] */
//           number({ value: Number(sh.t.toFixed(3)), min: 0, max: s.duration, step: 1 / FPS, width: "86px", unit: "s", help: "scene.shots.time", key: `shot-t-${sh.id}`,
//             onChange: v => edit(sh.id, (x, sc) => { x.t = Math.round((v ?? 0) * FPS) / FPS; sc.shots.sort((a, b) => a.t - b.t); }, "Shot time") }),
//           proposed.has(sh.id) && h("span", { class: "mono small rw-beat-to", help: "scene.shots.beatPlan" }, `→ ${proposed.get(sh.id).to.toFixed(2)} s`), // added 2026-11-03 v0.6.0
//           // added 2026-11-03 v0.4.3: how long the shot lasts (until the next shot, the last one until the scene ends)
//           h("span", { class: ["mono small rw-shot-len", lens[i].past ? "rw-c-warn" : "rw-dim"], help: "scene.shots.length" },
//             lens[i].past ? "after the end" : `for ${lens[i].length.toFixed(2)} s${lens[i].last ? " · end" : ""}`),
//           h("input", { class: "rw-input", list: listId, placeholder: "camera", value: sh.camera, key: `shot-cam-${sh.id}`, help: "scene.shots.camera",
//             onChange: e => edit(sh.id, x => { x.camera = e.target.value; }) }),
//           h("input", { class: "rw-input grow", placeholder: "what happens in this shot", value: sh.text, key: `shot-text-${sh.id}`, help: "scene.shots.text",
//             onChange: e => edit(sh.id, x => { x.text = e.target.value; }) }),
//           button({ icon: "trash", small: true, variant: "ghost", help: "scene.shots.remove", onClick: () => ctx.actions.editScene(s.id, sc => { sc.shots = sc.shots.filter(x => x.id !== sh.id); }) }))),
//       // [OLD 2026-11-03 v0.4.2->v0.4.3] s.shots.some(x => x.t > s.duration) && h("div", { class: "rw-note warn" }, "A shot starts after the end of the scene."),
//       // added 2026-11-03 v0.4.3: say how many, and offer to lengthen the scene or move the shots closer together
//       over && h("div", { class: "rw-note warn rw-overrun", help: "scene.shots.overrun" }, icon("warn", 12),
//         h("span", { class: "grow" }, [over.shots && `${over.shots} shot${over.shots === 1 ? "" : "s"}`, over.lines && `${over.lines} dialogue line${over.lines === 1 ? "" : "s"}`]
//           .filter(Boolean).join(" and ") + ` start${over.shots + over.lines === 1 ? "s" : ""} after the scene ends (${s.duration.toFixed(2)} s).`),
//         // the buttons vanish once it fits: focus goes back to the editor so Ctrl+Z works right away
//         button({ label: `Lengthen to ${fitLength(s).toFixed(2)} s`, small: true, help: "scene.shots.lengthen", onClick: () => { ctx.actions.editScene(s.id, sc => lengthenToFit(sc)); ctx.root.focus?.({ preventScroll: true }); } }),
//         button({ label: `Fit into ${s.duration.toFixed(2)} s`, small: true, help: "scene.shots.squeeze", onClick: () => { ctx.actions.editScene(s.id, sc => squeezeToFit(sc)); ctx.root.focus?.({ preventScroll: true }); } })),
//     ],
//   });
// }
// [/OLD]
// added 2026-11-05 v0.8.0: the shots as rows: start, end and length in scene time (the length is editable: it moves
// the next shot's start; the last shot's length sets the scene's length, by the timeline's Ripple / Roll rule), the
// camera picker (official H3 moves + amplitude + speed + framing), a text field that grows with its text, and a note
// where a pass seam falls inside the shot. The Prompt card's pass tabs use the same rows (keys with a prefix).
function shotsCard(ctx, s) {
  const p = ctx.p;
  const lens = shotLengths(s);
  const over = overruns(s);
  const plan = passLayout(p, s);
  const songs = p.soundtrack.some(t => !t.mute);
  const beatPlan = songs && ctx.eph.beatShots === s.id ? beatShotPlan(ctx, s) : null;
  const proposed = new Map((beatPlan || []).map(m => [m.id, m]));
  return section({
    title: "Shots", help: "scene.shots",
    collapse: { ctx, id: "shots", summary: `${s.shots.length} shot${s.shots.length === 1 ? "" : "s"}` }, // added 2026-11-06 v0.10.0
    actions: [
      songs && s.shots.length > 0 && button({ label: "On the beat", icon: "music", small: true, help: "scene.shots.beat",
        onClick: () => ctx.store.setEph({ beatShots: ctx.eph.beatShots === s.id ? null : s.id }) }),
      button({ label: "Shot", icon: "plus", small: true, help: "scene.shots.add", key: `shot-add-${s.id}`, onClick: () => ctx.actions.editScene(s.id, sc => {
        const last = sc.shots[sc.shots.length - 1];
        const t = last ? Math.min(sc.duration - 0.5, last.t + Math.max(1, (sc.duration - last.t) / 2)) : 0;
        sc.shots.push({ id: newId("h"), t: Math.max(0, Math.round(t * FPS) / FPS), camera: "", text: "" });
        sc.shots.sort((a, b) => a.t - b.t);
      }, { label: "Add shot" }) }),
    ],
    children: [
      ctx.eph.beatShots === s.id && songs && beatPlanNote(ctx, s, beatPlan),
      // [OLD 2026-11-12 v0.14.1->v0.14.2] s.shots.length === 0 ? h("div", { class: "rw-empty sm", help: "scene.shots" }, "No shots: the scene is written as one continuous take.")
      s.shots.length === 0 ? fillNote(ctx, s, "shots") // added 2026-11-12 v0.14.2: or take them from the description
        // [OLD 2026-11-06 v0.8.0->v0.9.0] : h("div", { class: "rw-rows" }, s.shots.map((sh, i) => shotRow(ctx, s, sh, i, { plan, lens, proposed: proposed.get(sh.id) }))),
        : rowsBox(ctx, "shots", "shots-" + s.id, s.shots.map((sh, i) => shotRow(ctx, s, sh, i, { plan, lens, proposed: proposed.get(sh.id) }))), // added 2026-11-06 v0.9.0
      over && h("div", { class: "rw-note warn rw-overrun", help: "scene.shots.overrun" }, icon("warn", 12),
        h("span", { class: "grow" }, [over.shots && `${over.shots} shot${over.shots === 1 ? "" : "s"}`, over.lines && `${over.lines} dialogue line${over.lines === 1 ? "" : "s"}`]
          .filter(Boolean).join(" and ") + ` start${over.shots + over.lines === 1 ? "s" : ""} after the scene ends (${s.duration.toFixed(2)} s).`),
        button({ label: `Lengthen to ${fitLength(s).toFixed(2)} s`, small: true, help: "scene.shots.lengthen", onClick: () => { ctx.actions.editScene(s.id, sc => lengthenToFit(sc), { label: "Lengthen to fit" }); ctx.root.focus?.({ preventScroll: true }); } }),
        button({ label: `Fit into ${s.duration.toFixed(2)} s`, small: true, help: "scene.shots.squeeze", onClick: () => { ctx.actions.editScene(s.id, sc => squeezeToFit(sc), { label: "Fit into the scene" }); ctx.root.focus?.({ preventScroll: true }); } })),
    ],
  });
}

const sec3 = t => (Math.round(t * 1000) / 1000).toFixed(3);

// one shot (also in the Prompt card's pass tabs: prefix keeps the keys unique, label is the pass's own numbering)
function shotRow(ctx, s, sh, i, { plan, lens, prefix = "", label, sceneNumber, continuing, proposed }) {
  const p = ctx.p;
  const key = x => `${prefix}shot-${x}-${sh.id}`;
  const edit = (fn, lbl) => ctx.actions.editScene(s.id, sc => { const x = sc.shots.find(q => q.id === sh.id); if (x) fn(x, sc); }, { label: lbl });
  const len = lens[i] || { length: 0, last: true, past: true };
  const end = sh.t + len.length;
  const next = s.shots[i + 1], after = s.shots[i + 2];
  const setLength = v => {
    if (v === null || !(v > 0)) return;
    const to = Math.round((sh.t + v) * FPS) / FPS;
    if (!next) { setSceneDuration(ctx, s.id, Math.max(1 / FPS, to), { label: "Last shot length" }); return; }
    const lo = sh.t + 1 / FPS, hi = (after ? after.t : s.duration) - 1 / FPS;
    const t = Math.round(Math.min(hi, Math.max(lo, to)) * FPS) / FPS;
    ctx.actions.editScene(s.id, sc => { const x = sc.shots.find(q => q.id === next.id); if (x) x.t = t; sc.shots.sort((a, b) => a.t - b.t); }, { label: "Shot length" });
  };
  const seams = len.past ? [] : shotSeams(plan, sh.t, end);
  const hasCam = !!(sh.camera || "").trim() && !stillMove(sh.camera); // Static Shot, POV, Shake: no amplitude or speed
  const seg = (k, value, options, lbl, help) => {
    const el = segmented({ small: true, value: value || "", key: key(k), help, options: options.map(([v, l]) => ({ value: v, label: l, help })),
      onChange: v => edit(x => { x[k === "amp" ? "camera_amp" : "camera_speed"] = v; }, lbl) });
    if (!hasCam) { el.classList.add("rw-disabled"); el.querySelectorAll("button").forEach(b => { b.disabled = true; }); }
    return el;
  };
  return h("div", { class: ["rw-shot-row", len.past && "past", seams.length && "seam"] },
    h("div", { class: "rw-list-row shot" },
      h("span", { class: "mono rw-dim rw-shot-label", help: "scene.shots.index", title: sceneNumber ? `Shot ${sceneNumber} of the scene` : null }, label || `[Shot ${i + 1}]`),
      sceneNumber && h("span", { class: "mono rw-dim small", help: "scene.shots.index" }, `#${sceneNumber}`),
      number({ value: Number(sh.t.toFixed(3)), min: 0, max: s.duration, step: 1 / FPS, width: "86px", unit: "s", help: "scene.shots.time", key: key("t"),
        onChange: v => edit((x, sc) => { x.t = Math.round((v ?? 0) * FPS) / FPS; sc.shots.sort((a, b) => a.t - b.t); }, "Shot time") }),
      proposed && h("span", { class: "mono small rw-beat-to", help: "scene.shots.beatPlan" }, `→ ${proposed.to.toFixed(2)} s`),
      len.past ? h("span", { class: "mono small rw-shot-len rw-c-warn", help: "scene.shots.length" }, "after the end")
        : [h("span", { class: "mono small rw-dim rw-shot-end", help: "scene.shots.end" }, `→ ${sec3(end)}${len.last ? " · end" : ""}`),
          h("span", { class: "rw-dim small", help: len.last ? "scene.shots.lastLength" : "scene.shots.duration" }, "for"),
          number({ value: Number(len.length.toFixed(3)), min: 1 / FPS, max: 600, step: 1 / FPS, width: "76px", unit: "s", help: len.last ? "scene.shots.lastLength" : "scene.shots.duration", key: key("len"), onChange: setLength })],
      continuing && h("span", { class: "rw-chip-mini", help: "scene.shots.continuing" }, "continues"),
      seams.map(x => h("span", { class: "rw-seam-chip", help: "scene.shots.seam",
        title: `Pass ${x.k} takes over at ${fmtTime(x.t)}, inside this shot (${x.kind === "overlap" ? "an overlap seam: the passes share frames there" : "a cut seam"}). A shot cut near it lets the passes join at a cut.` },
      icon("warn", 11), `seam ${fmtTime(x.t)}`)),
      h("span", { class: "rw-flex" }),
      button({ icon: "trash", small: true, variant: "ghost", help: "scene.shots.remove", key: key("del"), onClick: () => ctx.actions.editScene(s.id, sc => { sc.shots = sc.shots.filter(x => x.id !== sh.id); }, { label: "Remove shot" }) })),
    h("div", { class: "rw-shot-cam" },
      select({ options: cameraOptions(p), value: sh.camera || "", free: true, placeholder: "no camera move", key: key("cam"), help: "scene.shots.camera", width: "160px",
        onChange: v => edit(x => { x.camera = v; if (stillMove(v)) { x.camera_amp = ""; x.camera_speed = ""; } }, "Camera move") }),
      h("span", { class: "rw-dim small", help: "scene.shots.amplitude" }, "amplitude"),
      seg("amp", sh.camera_amp, [["small", "Small"], ["", "Medium"], ["large", "Large"]], "Camera amplitude", "scene.shots.amplitude"),
      h("span", { class: "rw-dim small", help: "scene.shots.speed" }, "speed"),
      seg("speed", sh.camera_speed, [["slow", "Slow"], ["", "Normal"], ["fast", "Fast"]], "Camera speed", "scene.shots.speed"),
      select({ options: framingOptions(), value: sh.framing || "", key: key("frame"), help: "scene.shots.framing", width: "136px", placeholder: "any framing",
        onChange: v => edit(x => { x.framing = v; }, "Framing") })),
    codeEditor({ value: sh.text, key: key("text"), help: "scene.shots.text", candidates: tagCandidates(p, s), /* v0.14.0: with the scene's @V1.2 ... */ placeholder: "What happens in this shot: subject, action, sound. Use @tags for cast and assets.",
      minRows: 2, maxHeight: 220, cls: "sans",
      onInput: v => ctx.actions.editScene(s.id, sc => { const x = sc.shots.find(q => q.id === sh.id); if (x) x.text = v; }, { coalesce: key("text"), render: false, label: "Shot text" }),
      onChange: () => ctx.store.notify() }));
}


// added 2026-11-03 v0.6.0: shot start times on the beat. Every shot after the opening one moves to the nearest beat
// of the soundtrack (a bar start when one is about as near), in order and at least half a beat apart, never into the
// repeated start of a continuing scene. [{id, number, from, to}] for the shots that move; null while there are no beats.
function beatShotPlan(ctx, s) {
  const p = ctx.p;
  const { times, down } = beatTimes(ctx);
  if (!times.length) return null;
  const start = sceneStarts(p).starts[s.id];
  const ov = (visibleStart(p, s.id) ?? start) - start;
  const lo = ov + 1 / FPS, hi = s.duration - 1 / FPS;
  const local = [];
  for (let k = 0; k < times.length; k++) {
    const t = times[k] - start;
    if (t >= lo && t <= hi) local.push({ t, down: !!down[k] });
  }
  const out = [];
  if (!local.length) return out;
  const gaps = local.slice(1).map((b, k) => b.t - local[k].t).sort((a, b) => a - b);
  const beat = gaps.length ? gaps[gaps.length >> 1] : 0.5;
  let prev = -Infinity;
  s.shots.forEach((sh, k) => {
    if (k === 0 && sh.t <= ov + 1e-6) { prev = sh.t; return; } // the opening shot starts with the scene
    const cands = local.filter(b => b.t > prev + beat * 0.5);
    if (!cands.length) { prev = Math.max(prev, sh.t); return; }
    const dist = b => Math.abs(b.t - sh.t);
    let best = cands.reduce((a, b) => (dist(b) < dist(a) ? b : a));
    const bars = cands.filter(b => b.down);
    const bar = bars.length ? bars.reduce((a, b) => (dist(b) < dist(a) ? b : a)) : null;
    if (bar && dist(bar) <= dist(best) + beat * 0.5) best = bar;
    const to = Math.round(best.t * FPS) / FPS;
    prev = to;
    if (Math.abs(to - sh.t) >= 0.5 / FPS) out.push({ id: sh.id, number: k + 1, from: sh.t, to });
  });
  return out;
}

function beatPlanNote(ctx, s, plan) {
  const close = button({ icon: "close", small: true, variant: "ghost", help: "common.close", onClick: () => ctx.store.setEph({ beatShots: null }) });
  if (plan === null) return h("div", { class: "rw-note rw-beat-plan", help: "scene.shots.beat" }, icon("music", 12), h("span", { class: "grow" }, "Finding the soundtrack's beats… (none under this scene yet)"), close);
  if (!plan.length) return h("div", { class: "rw-note ok rw-beat-plan", help: "scene.shots.beat" }, icon("music", 12), h("span", { class: "grow" }, "Every shot cut is already on a beat."), close);
  const apply = () => {
    ctx.actions.editScene(s.id, sc => {
      for (const m of plan) { const x = sc.shots.find(q => q.id === m.id); if (x) x.t = m.to; }
      sc.shots.sort((a, b) => a.t - b.t);
    }, { label: "Shots on the beat" });
    ctx.store.setEph({ beatShots: null });
    ctx.actions.toast(`Moved ${plan.length} shot cut${plan.length === 1 ? "" : "s"} onto the beat. Ctrl+Z undoes it.`, "ok");
  };
  return h("div", { class: "rw-note rw-beat-plan", help: "scene.shots.beatPlan" }, icon("music", 12),
    h("span", { class: "grow" }, `On the beat: ${plan.map(m => `[Shot ${m.number}] ${m.from.toFixed(2)} → ${m.to.toFixed(2)} s`).join(", ")}.`),
    button({ label: "Apply", small: true, variant: "primary", help: "scene.shots.beatApply", onClick: apply }), close);
}

// [OLD 2026-11-05 v0.7.0->v0.8.0] one-line rows without end, length or seam note; v0.8.0: dialogueRow below
// function dialogueCard(ctx, s) {
//   const p = ctx.p;
//   /* [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs now follow speaking order per clip (see the prompt preview)
//   const speakers = p.cast.filter(c => c.kind === "character").map(c => ({ value: c.id, label: `${c.name} (${c.speaker || "S?"})` }));
//   [/OLD] */
//   const speakers = p.cast.filter(c => c.kind === "character").map(c => ({ value: c.id, label: c.name }));
//   const langs = STABLE_LANGUAGES.map(l => ({ value: l, label: l }));
//   // [OLD 2026-11-03 v0.5.1->v0.6.0] const edit = (id, fn) => ctx.actions.editScene(s.id, sc => { const x = sc.dialogue.find(q => q.id === id); if (x) fn(x, sc); });
//   const edit = (id, fn) => ctx.actions.editScene(s.id, sc => { const x = sc.dialogue.find(q => q.id === id); if (x) fn(x, sc); }, { label: "Edit line" });
//   return section({
//     title: "Dialogue", help: "scene.dialogue",
//     /* [OLD 2026-11-03 v0.5.1->v0.6.0] a scene shorter than 0.5 s got a line at a negative time
//     actions: button({ label: "Line", icon: "plus", small: true, help: "scene.dialogue.add", onClick: () => ctx.actions.editScene(s.id, sc => {
//       const sp = sc.cast.find(c => findCast(p, c.id)?.kind === "character")?.id || speakers[0]?.value || "";
//       sc.dialogue.push({ id: newId("d"), speaker: sp, t: Math.min(sc.duration - 0.5, 1), language: findCast(p, sp)?.language || p.global.defaults.language, delivery: "says", text: "" });
//       sc.dialogue.sort((a, b) => a.t - b.t);
//     }) }),
//     [/OLD] */
//     // added 2026-11-03 v0.6.0: the new line starts 1 s after the scene first shows (never before 0 s or the end)
//     actions: button({ label: "Line", icon: "plus", small: true, help: "scene.dialogue.add", onClick: () => {
//       const ov = (visibleStart(p, s.id) ?? 0) - (sceneStarts(p).starts[s.id] ?? 0);
//       ctx.actions.editScene(s.id, sc => {
//         const sp = sc.cast.find(c => findCast(p, c.id)?.kind === "character")?.id || speakers[0]?.value || "";
//         const t = Math.max(0, Math.min(sc.duration - 0.5, ov + 1));
//         sc.dialogue.push({ id: newId("d"), speaker: sp, t: Math.round(t * FPS) / FPS, language: findCast(p, sp)?.language || p.global.defaults.language, delivery: "says", text: "" });
//         sc.dialogue.sort((a, b) => a.t - b.t);
//       }, { label: "Add line" });
//     } }),
//     children: [
//       !speakers.length && h("div", { class: "rw-note", help: "scene.dialogue.noCast" }, "Add a character in the Cast tab to give lines a speaker and a voice."),
//       s.dialogue.length === 0 ? h("div", { class: "rw-empty sm", help: "scene.dialogue" }, "No spoken lines.")
//         : s.dialogue.map(d => h("div", { class: "rw-list-row dlg" },
//           /* [OLD 2026-11-03 v0.5.1->v0.6.0] no keys: after a re-sort the caret went to the field now in this row (scene.js:324)
//           select({ options: speakers, value: d.speaker, placeholder: "speaker", help: "scene.dialogue.speaker", width: "130px", onChange: v => edit(d.id, x => { x.speaker = v; }) }),
//           number({ value: Number(d.t.toFixed(3)), min: 0, max: s.duration, step: 1 / FPS, width: "80px", unit: "s", help: "scene.dialogue.time",
//             onChange: v => edit(d.id, (x, sc) => { x.t = v ?? 0; sc.dialogue.sort((a, b) => a.t - b.t); }) }),
//           [/OLD] */
//           select({ options: speakers, value: d.speaker, placeholder: "speaker", help: "scene.dialogue.speaker", width: "130px", key: `dlg-sp-${d.id}`, onChange: v => edit(d.id, x => { x.speaker = v; }) }),
//           number({ value: Number(d.t.toFixed(3)), min: 0, max: s.duration, step: 1 / FPS, width: "80px", unit: "s", help: "scene.dialogue.time", key: `dlg-t-${d.id}`,
//             onChange: v => edit(d.id, (x, sc) => { x.t = v ?? 0; sc.dialogue.sort((a, b) => a.t - b.t); }) }),
//           /* [OLD 2026-11-02 v0.1.0->v0.2.0] language is now typed or picked (free combobox)
//           select({ options: langs, value: d.language, help: "scene.dialogue.language", width: "104px", onChange: v => edit(d.id, x => { x.language = v; }) }),
//           [/OLD] */
//           // [OLD 2026-11-03 v0.5.1->v0.6.0] select({ options: langs, value: d.language, free: true, help: "scene.dialogue.language", width: "104px", onChange: v => edit(d.id, x => { x.language = v; }) }),
//           select({ options: langs, value: d.language, free: true, help: "scene.dialogue.language", width: "104px", key: `dlg-lang-${d.id}`, onChange: v => edit(d.id, x => { x.language = v; }) }),
//           h("input", { class: "rw-input", style: { width: "90px" }, placeholder: "delivery", value: d.delivery, key: `dlg-del-${d.id}`, help: "scene.dialogue.delivery",
//             onChange: e => edit(d.id, x => { x.delivery = e.target.value; }) }),
//           h("input", { class: "rw-input grow", placeholder: "the spoken line", value: d.text, key: `dlg-text-${d.id}`, help: "scene.dialogue.text",
//             onChange: e => edit(d.id, x => { x.text = e.target.value; }) }),
//           button({ icon: "trash", small: true, variant: "ghost", help: "scene.dialogue.remove", onClick: () => ctx.actions.editScene(s.id, sc => { sc.dialogue = sc.dialogue.filter(x => x.id !== d.id); }) }))),
//       s.dialogue.some(d => d.language && !STABLE_LANGUAGES.includes(d.language)) && h("div", { class: "rw-note" }, "Some lines use a language outside H3's 11 stable ones."),
//     ],
//   });
// }
// [/OLD]
// added 2026-11-05 v0.8.0: dialogue lines as rows: speaker, start, end and length in scene time (the length is
// editable; empty = estimated from the words, shown as the placeholder), language, delivery, a growing text field,
// and a note when the line runs past a pass seam or the scene's end
function dialogueCard(ctx, s) {
  const p = ctx.p;
  const speakers = p.cast.filter(c => c.kind === "character");
  const plan = passLayout(p, s);
  // added 2026-11-06 v0.10.0: the lines past a seam that a move can fix (Fix lines at seams)
  const fixable = s.dialogue.filter(d => seamFixTime(seamFixes(plan, s, d), d.t) !== null).length;
  const crossing = s.dialogue.filter(d => lineSeam(plan, s, d)).length;
  return section({
    title: "Dialogue", help: "scene.dialogue",
    collapse: { ctx, id: "dialogue", summary: `${s.dialogue.length} line${s.dialogue.length === 1 ? "" : "s"}${crossing ? ` · ${crossing} past a seam` : ""}` }, // added 2026-11-06 v0.10.0
    /* [OLD 2026-11-06 v0.9.0->v0.10.0] one action; v0.10.0 adds Fix lines at seams before it
    actions: button({ label: "Line", icon: "plus", small: true, help: "scene.dialogue.add", key: `dlg-add-${s.id}`, onClick: () => {
    [/OLD] */
    actions: [fixable ? button({ label: `Fix ${fixable} at seams`, icon: "wand", small: true, variant: "ghost", help: "scene.dialogue.seamFixAll", key: `dlg-seamfix-${s.id}`,
      onClick: () => fixSeamLines(ctx, s) }) : null,
    button({ label: "Line", icon: "plus", small: true, help: "scene.dialogue.add", key: `dlg-add-${s.id}`, onClick: () => {
      const ov = (visibleStart(p, s.id) ?? 0) - (sceneStarts(p).starts[s.id] ?? 0);
      ctx.actions.editScene(s.id, sc => {
        const sp = sc.cast.find(c => findCast(p, c.id)?.kind === "character")?.id || speakers[0]?.id || "";
        const t = Math.max(0, Math.min(sc.duration - 0.5, ov + 1));
        sc.dialogue.push({ id: newId("d"), speaker: sp, t: Math.round(t * FPS) / FPS, language: findCast(p, sp)?.language || p.global.defaults.language, delivery: "says", text: "" });
        sc.dialogue.sort((a, b) => a.t - b.t);
      }, { label: "Add line" });
    } })],
    children: [
      !speakers.length && h("div", { class: "rw-note", help: "scene.dialogue.noCast" }, "Add a character in the Cast tab to give lines a speaker and a voice."),
      // [OLD 2026-11-12 v0.14.1->v0.14.2] s.dialogue.length === 0 ? h("div", { class: "rw-empty sm", help: "scene.dialogue" }, "No spoken lines.")
      s.dialogue.length === 0 ? fillNote(ctx, s, "lines") // added 2026-11-12 v0.14.2: or take them from the description
        // [OLD 2026-11-06 v0.8.0->v0.9.0] : h("div", { class: "rw-rows" }, s.dialogue.map(d => dialogueRow(ctx, s, d, { plan }))),
        : rowsBox(ctx, "lines", "lines-" + s.id, s.dialogue.map(d => dialogueRow(ctx, s, d, { plan }))), // added 2026-11-06 v0.9.0
      s.dialogue.some(d => d.language && !STABLE_LANGUAGES.includes(d.language)) && h("div", { class: "rw-note" }, "Some lines use a language outside H3's 11 stable ones."),
    ],
  });
}

function dialogueRow(ctx, s, d, { plan, prefix = "" }) {
  const p = ctx.p;
  const key = x => `${prefix}dlg-${x}-${d.id}`;
  const speakers = p.cast.filter(c => c.kind === "character").map(c => ({ value: c.id, label: c.name }));
  const langs = STABLE_LANGUAGES.map(l => ({ value: l, label: l }));
  const edit = (fn, lbl) => ctx.actions.editScene(s.id, sc => { const x = sc.dialogue.find(q => q.id === d.id); if (x) fn(x, sc); }, { label: lbl });
  const secs = dialogueSecs(d);
  const given = Number(d.duration) > 0 ? Number(d.duration) : null;
  const est = dialogueSecs({ ...d, duration: null });
  const seam = lineSeam(plan, s, d);
  return h("div", { class: ["rw-dlg-row", seam && "seam"] },
    h("div", { class: "rw-list-row dlg" },
      select({ options: speakers, value: d.speaker, placeholder: "speaker", help: "scene.dialogue.speaker", width: "130px", key: key("sp"), onChange: v => edit(x => { x.speaker = v; }, "Line speaker") }),
      number({ value: Number(d.t.toFixed(3)), min: 0, max: s.duration, step: 1 / FPS, width: "80px", unit: "s", help: "scene.dialogue.time", key: key("t"),
        onChange: v => edit((x, sc) => { x.t = Math.round((v ?? 0) * 1000) / 1000; sc.dialogue.sort((a, b) => a.t - b.t); }, "Line time") }),
      h("span", { class: "mono small rw-dim rw-shot-end", help: "scene.dialogue.end" }, `→ ${sec3(d.t + secs)}`),
      h("span", { class: "rw-dim small", help: "scene.dialogue.duration" }, "for"),
      number({ value: given === null ? null : Number(given.toFixed(3)), min: 0, max: 600, step: 0.05, width: "70px", unit: "s", help: "scene.dialogue.duration", key: key("len"),
        placeholder: est.toFixed(2), onChange: v => edit(x => { x.duration = v === null || !(v > 0) ? null : Math.round(v * 1000) / 1000; }, "Line length") }),
      select({ options: langs, value: d.language, free: true, help: "scene.dialogue.language", width: "100px", key: key("lang"), onChange: v => edit(x => { x.language = v; }, "Line language") }),
      h("input", { class: "rw-input grow", style: { "min-width": "70px", "max-width": "130px" }, placeholder: "delivery", value: d.delivery, key: key("del"), help: "scene.dialogue.delivery",
        onChange: e => edit(x => { x.delivery = e.target.value; }, "Line delivery") }),
      h("span", { class: "rw-flex" }),
      button({ icon: "trash", small: true, variant: "ghost", help: "scene.dialogue.remove", key: key("del-btn"), onClick: () => ctx.actions.editScene(s.id, sc => { sc.dialogue = sc.dialogue.filter(x => x.id !== d.id); }, { label: "Remove line" }) })),
    codeEditor({ value: d.text, key: key("text"), help: "scene.dialogue.text", candidates: tagCandidates(p, s), /* v0.14.0: with the scene's @V1.2 ... */ placeholder: "The spoken line, word for word.",
      minRows: 1, maxHeight: 160, cls: "sans",
      onInput: v => ctx.actions.editScene(s.id, sc => { const x = sc.dialogue.find(q => q.id === d.id); if (x) x.text = v; }, { coalesce: key("text"), render: false, label: "Line text" }),
      onChange: () => ctx.store.notify() }),
    /* [OLD 2026-11-06 v0.9.0->v0.10.0] the note only warned; v0.10.0 adds quick fixes (the seams stay where they are)
    seam && h("div", { class: "rw-seam-note", help: "scene.dialogue.seam" }, icon("warn", 11),
      seam.kind === "end" ? `Runs to ${fmtTime(seam.end)}, past the scene's end (${fmtTime(seam.t)}): the end of the line is cut off.`
        : `Runs to ${fmtTime(seam.end)}, past the seam at ${fmtTime(seam.t)} where pass ${seam.pass} takes over: the end of the line is cut off.`));
    [/OLD] */
    seam && seamNote(ctx, s, d, plan, seam, key, edit)); // added 2026-11-06 v0.10.0
}

// added 2026-11-06 v0.10.0: the seam note with its quick fixes: start the line just after the seam (the next pass says
// it) or move it earlier so it ends before the seam (or the scene's end). Buttons that can't help are disabled and say why.
function seamNote(ctx, s, d, plan, seam, key, edit) {
  const fx = seamFixes(plan, s, d) || { earlier: null, later: null };
  const move = (t, lbl) => edit((x, sc) => { x.t = t; sc.dialogue.sort((a, b) => a.t - b.t); }, lbl);
  const secs = dialogueSecs(d);
  return h("div", { class: "rw-seam-note", help: "scene.dialogue.seam" }, icon("warn", 11),
    h("span", { class: "grow" }, seam.kind === "end" ? `Runs to ${fmtTime(seam.end)}, past the scene's end (${fmtTime(seam.t)}): the end of the line is cut off.`
      : `Runs to ${fmtTime(seam.end)}, past the seam at ${fmtTime(seam.t)} where pass ${seam.pass} takes over: the end of the line is cut off.`),
    seam.kind === "seam" && button({ label: "Start after the seam", small: true, variant: "ghost", key: key("seam-later"), help: "scene.dialogue.seamLater",
      disabled: fx.later === null, detail: fx.later === null ? `From the seam the line (${secs.toFixed(1)} s) would run past the scene's end.` : `Starts at ${fmtTime(fx.later)}, in pass ${seam.pass}.`,
      onClick: () => move(fx.later, "Line after the seam") }),
    button({ label: seam.kind === "end" ? "End before the scene's end" : "End before the seam", small: true, variant: "ghost", key: key("seam-earlier"), help: "scene.dialogue.seamEarlier",
      disabled: fx.earlier === null, detail: fx.earlier === null ? `The line (${secs.toFixed(1)} s) is longer than the room before ${seam.kind === "end" ? "the end" : "the seam"} in its pass: shorten it, or start it after the seam.` : `Starts at ${fmtTime(fx.earlier)} and ends just before ${fmtTime(seam.t)}.`,
      onClick: () => move(fx.earlier, "Line before the seam") }));
}

// added 2026-11-06 v0.10.0: every line of the scene that runs past a seam, moved the smaller way (one undo step)
function fixSeamLines(ctx, s) {
  const plan = passLayout(ctx.p, s);
  const moves = new Map();
  for (const d of s.dialogue) { const t = seamFixTime(seamFixes(plan, s, d), d.t); if (t !== null) moves.set(d.id, t); }
  if (!moves.size) return;
  ctx.actions.editScene(s.id, sc => {
    for (const x of sc.dialogue) if (moves.has(x.id)) x.t = moves.get(x.id);
    sc.dialogue.sort((a, b) => a.t - b.t);
  }, { label: `Move ${moves.size} line${moves.size === 1 ? "" : "s"} off the seams` });
}

function previewCard(ctx, s) {
  const plan = ctx.planFor(s.id);
  const prompts = plan?.prompts || [];
  const passes = plan?.passes || [];
  const open = Math.min(ctx.eph.openPasses[s.id] || 0, Math.max(0, prompts.length - 1));
  const long = passes.length > 1 || estimatePasses(s.duration, ctx.p.global.long).count > 1;
  const overrides = s.prompt.pass_prompts || {};
  const hasOverride = overrides[String(open + 1)] !== undefined;
  const splitting = ctx.eph.splitJob?.scene_id === s.id ? ctx.eph.splitJob : null; // added 2026-11-03 v0.4.2
  // added 2026-11-06 v0.9.0: which passes to show, from the Prompt card's tab (raw prompts: every pass)
  const tab = promptTabOf(ctx, s);
  const shownPasses = !prompts.length ? [0] : tab >= 0 ? [Math.min(tab, prompts.length - 1)] : prompts.map((_, i) => i);
  return section({
    title: "What H3 receives", help: "scene.preview",
    collapse: { ctx, id: "h3", summary: prompts.length > 1 ? `${prompts.length} passes` : "" }, // added 2026-11-06 v0.10.0
    actions: [
      /* [OLD 2026-11-03 v0.4.1->v0.4.2] no busy state, no progress, no way to stop
      long && button({ label: "Split with LLM", icon: "wand", small: true, help: "scene.preview.splitLlm", onClick: async () => {
        try {
          const res = await rw.split(ctx.p, s.id);
          ctx.actions.editScene(s.id, sc => { sc.prompt.pass_prompts = res.pass_prompts || {}; });
          ctx.actions.toast("Pass prompts written by the LLM. Edit them below.", "ok");
        } catch (err) { ctx.actions.toast("Split failed: " + err.message, "error"); }
      } }),
      [/OLD] */
      long && button({ label: splitting ? "Splitting…" : "Split with LLM", icon: "wand", small: true, help: "scene.preview.splitLlm", disabled: !!splitting, onClick: async () => {
        const job = newJob("split");
        ctx.store.setEph({ splitJob: { scene_id: s.id, job } });
        try {
          const res = await rw.split(ctx.p, s.id, job);
          if (res.cancelled) { ctx.actions.toast("Split stopped.", "warn"); return; }
          ctx.actions.editScene(s.id, sc => { sc.prompt.pass_prompts = res.pass_prompts || {}; });
          ctx.actions.toast("Pass prompts written by the LLM. Edit them below.", "ok");
        } catch (err) { ctx.actions.toast("Split failed: " + err.message, "error"); }
        finally { delete ctx.store.eph.llmJobs[job]; ctx.store.setEph({ splitJob: null }); }
      } }),
      long && Object.keys(overrides).length > 0 && button({ label: "Automatic split", small: true, help: "scene.preview.splitAuto", onClick: () => ctx.actions.editScene(s.id, sc => { sc.prompt.pass_prompts = {}; }) }),
    ],
    /* [OLD 2026-11-06 v0.8.0->v0.9.0] its own row of pass tabs (eph.openPasses); the Prompt card's tabs choose now
    children: [
      splitting && llmBusyRow(ctx, splitting.job, "scene.preview.splitStop"), // added 2026-11-03 v0.4.2
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
      excerptRow(ctx, s, open), // added 2026-11-03 v0.6.0: listen to the part of the song this pass is sent
      long && !hasOverride && prompts[open] && button({ label: "Edit this pass by hand", small: true, help: "scene.preview.override", onClick: () => ctx.actions.editScene(s.id, sc => { sc.prompt.pass_prompts[String(open + 1)] = prompts[open]; }) }),
      plan?.key && h("div", { class: "rw-dim small mono", help: "render.cacheKey" }, "cache key " + plan.key.slice(0, 16)),
    ],
    [/OLD] */
    // added 2026-11-06 v0.9.0: the pass of the Prompt card's tab, or every pass in turn on Whole scene (each with a head:
    // its range, frames and seam), each with its excerpt and "Edit this pass by hand"
    children: [
      splitting && llmBusyRow(ctx, splitting.job, "scene.preview.splitStop"),
      shownPasses.map(i => {
        const ps = passes[i];
        const own = overrides[String(i + 1)] !== undefined;
        return h("div", { class: "rw-h3-pass", key: `h3pass-${s.id}-${i + 1}` },
          shownPasses.length > 1 || (prompts.length > 1 && tab >= 0) ? h("div", { class: "rw-h3-pass-head", help: "scene.preview.pass" },
            h("b", null, `Pass ${i + 1} of ${prompts.length}`),
            ps && h("span", { class: "mono rw-dim small" }, ` ${fmtTime(ps.start, false)}–${fmtTime(ps.end, false)} · ${ps.gen_frames} f${ps.seam_before && ps.seam_before !== "none" ? " · " + ps.seam_before : ""}`),
            own && h("span", { class: "rw-c-accent small", help: "scene.preview.override" }, " ● edited by hand"),
            // added 2026-11-06 v0.10.0: copy this pass's prompt
            h("span", { class: "rw-flex" }), prompts[i] && copyButton({ text: () => prompts[i], key: `h3copy-${s.id}-${i + 1}`, help: "scene.preview.copy", what: "prompt" })) : null,
          // added 2026-11-06 v0.10.0: a single prompt (no pass head) gets its copy button here
          !(shownPasses.length > 1 || (prompts.length > 1 && tab >= 0)) && prompts[i] ? h("div", { class: "rw-h3-copy" },
            copyButton({ label: "Copy prompt", text: () => prompts[i], key: `h3copy-${s.id}-${i + 1}`, help: "scene.preview.copy", what: "prompt" })) : null,
          // [OLD 2026-11-12 v0.13.0->v0.13.1] long && own  (a single-pass scene showed a hand-edited prompt as plain text, with no sign it was one)
          own && (long || String(overrides[String(i + 1)]).trim() !== "") // added 2026-11-12 v0.13.1
            ? codeEditor({ value: overrides[String(i + 1)], help: "scene.preview.override", minRows: 6, maxHeight: 300, key: `pass-${s.id}-${i + 1}`, candidates: tagCandidates(ctx.p, s), /* v0.14.0: with the scene's @V1.2 ... */
              onInput: v => ctx.actions.editScene(s.id, sc => { sc.prompt.pass_prompts[String(i + 1)] = v; }, { coalesce: `pass-${s.id}-${i + 1}`, render: false }),
              onChange: () => ctx.store.notify() })
            : h("pre", { class: "rw-prompt-preview mono tall", help: "scene.preview", html: prompts[i] ? highlightHTML(prompts[i]) : "" },
              prompts[i] ? null : h("span", { class: "rw-dim" }, ctx.eph.backend === "online" ? "Nothing to send yet: add a summary, shots or references." : "The exact prompt is built by the Reelwright backend; it appears here when ComfyUI is running.")),
          excerptRow(ctx, s, i),
          long && !own && prompts[i] && button({ label: "Edit this pass by hand", small: true, help: "scene.preview.override", key: `h3edit-${s.id}-${i + 1}`,
            onClick: () => ctx.actions.editScene(s.id, sc => { sc.prompt.pass_prompts[String(i + 1)] = prompts[i]; }, { label: `Pass ${i + 1}: edit by hand` }) }));
      }),
      plan?.key && h("div", { class: "rw-dim small mono", help: "render.cacheKey" }, "cache key " + plan.key.slice(0, 16)),
    ],
  });
}

// added 2026-11-03 v0.6.0: the part of the soundtrack a pass is sent, to listen to (POST /reelwright/soundtrack/excerpt
// builds the same WAV the render uses). The <audio> element is kept across renders, so a progress event or a plan
// refresh does not stop it (files.js keeps its previews the same way). A changed song part asks again.
const excerpts = new WeakMap(); // ctx -> Map(key -> { state: "loading"|"ok"|"none"|"error", el, reason, error, info })

function excerptRow(ctx, s, open) {
  const p = ctx.p;
  const i = sceneIndex(p, s.id);
  const pass = planScene(p, s, i).passes[open];
  if (!pass) return null;
  const song = passSoundtrack(p, sceneStarts(p).starts[s.id] ?? 0, pass);
  if (!song) return null; // this pass gets no part of the song
  const map = excerpts.get(ctx) || new Map();
  excerpts.set(ctx, map);
  const key = `${s.id}|${open + 1}|${JSON.stringify(song.pieces)}|${song.marker}`;
  const ex = map.get(key);
  const what = `${song.codes.join(" + ") || "song"} · ${fmtTime(song.start, false)}–${fmtTime(song.start + song.length, false)} of the film · ${song.marker.replace("_", " ")}`;
  const listen = async () => {
    const entry = { state: "loading" };
    // older excerpts of this pass are stale: stop and forget them
    for (const [k, v] of map) if (k.startsWith(`${s.id}|${open + 1}|`)) { v.el?.pause(); ctx.excerptPlayers?.delete(v.el); map.delete(k); }
    map.set(key, entry);
    ctx.store.notify();
    try {
      /* [OLD 2026-11-03 v0.6.0 review] the route read the saved project.json, so a pending edit was saved first
      if (ctx.eph.saveState === "pending") await ctx.store.saveNow();
      const res = await rw.soundtrackExcerpt(p.slug, s.id, open + 1);
      [/OLD] */
      const res = await rw.soundtrackExcerpt(p.slug, s.id, open + 1, p); // added 2026-11-03 v0.6.0: the unsaved project
      if (!res?.url) Object.assign(entry, { state: "none", reason: res?.reason || "This pass gets no part of the soundtrack." });
      else {
        const src = res.file ? viewURL(res.file, "output") : ctx.host.apiURL(res.url);
        entry.el = h("audio", { class: "rw-excerpt-audio", controls: true, preload: "auto", src, help: "scene.preview.excerpt" });
        (ctx.excerptPlayers ||= new Set()).add(entry.el); // the timeline pauses them when it plays or the editor closes
        Object.assign(entry, { state: "ok", info: res });
        entry.el.play?.().catch(() => {});
      }
    } catch (err) {
      Object.assign(entry, { state: "error", error: String(err?.message || err) });
    }
    ctx.store.notify();
  };
  const body = !ex
    ? [button({ label: "Listen", icon: "play", small: true, help: "scene.preview.listen", onClick: listen }), h("span", { class: "rw-dim small grow" }, what)]
    : ex.state === "loading" ? [button({ label: "Preparing…", icon: "music", small: true, disabled: true, help: "scene.preview.listen" }), h("span", { class: "rw-dim small grow" }, what)]
      : ex.state === "ok" ? [ex.el, h("span", { class: "rw-dim small grow", help: "scene.preview.excerpt" }, what)]
        : [h("span", { class: "small grow " + (ex.state === "error" ? "rw-c-err" : "rw-dim") }, ex.state === "error" ? "Could not build the excerpt: " + ex.error : ex.reason),
          button({ label: "Try again", small: true, help: "scene.preview.listen", onClick: listen })];
  return h("div", { class: "rw-row rw-excerpt", help: "scene.preview.excerpt" }, icon("music", 12), h("b", { class: "small" }, `Pass ${open + 1} song`), ...body);
}

// added 2026-11-12 v0.14.2: the empty Shots / Dialogue card of a scene whose description holds [Shot N] lines or
// spoken lines (written before v0.14.2, or by hand) offers to put them on the timeline (shotfill.fillScene)
function fillNote(ctx, s, what) {
  const empty = what === "shots" ? "No shots: the scene is written as one continuous take." : "No spoken lines.";
  const got = fillable(ctx.p, s);
  const n = got && { shots: got.shots.length, lines: s.dialogue.length ? 0 : got.lines.length };
  if (!got || (what === "lines" && !n.lines)) return h("div", { class: "rw-empty sm", help: what === "shots" ? "scene.shots" : "scene.dialogue" }, empty);
  return h("div", { class: "rw-note rw-fill-note", help: "scene.shots.fill" }, icon("wand", 12),
    h("span", { class: "grow" }, `${what === "shots" ? "No shots" : "No spoken lines"} on the timeline yet, but the description has ${fillWords(n)}.`),
    button({ label: `Take ${fillWords(n)} from it`, icon: "wand", small: true, help: "scene.shots.fill", key: `fill-${what}-${s.id}`,
      onClick: () => {
        let done = null;
        ctx.actions.editScene(s.id, (sc, q) => { done = fillScene(q, sc); }, { label: "Shots from the description" });
        if (done) ctx.actions.toast(`Put ${fillWords(done)} on the timeline; the description keeps the style. Undo with Ctrl+Z.`, "ok");
      } }));
}

function rewriteCard(ctx, s) {
  // added 2026-11-06 v0.10.0: on a pass tab the rewriter rewrites that pass's own sections (Write prompts' request for
  // one pass, with the instruction); a proposal made for another pass or tab is not shown
  const plan = passLayout(ctx.p, s);
  const tab = promptTabOf(ctx, s, plan);
  const passK = s.prompt.mode !== "raw" && plan.passes.length > 1 && tab >= 0 ? tab : -1;
  const pt = passK >= 0 ? passTextsOf(ctx.p, s, plan) : null;
  // [OLD 2026-11-06 v0.9.0->v0.10.0] const rwState = ctx.eph.rewrite?.scene_id === s.id ? ctx.eph.rewrite : null;
  const rwState = ctx.eph.rewrite?.scene_id === s.id && (ctx.eph.rewrite.pass ?? -1) === passK ? ctx.eph.rewrite : null; // added 2026-11-06 v0.10.0
  const instr = h("input", { class: "rw-input grow", key: "rewrite-instr", placeholder: "Optional instruction, e.g. make shot 2 more intimate", help: "scene.rewrite.instruction", value: ctx.eph.rewriteInstr || "",
    onInput: e => { ctx.eph.rewriteInstr = e.target.value; } });
  const llm = ctx.p.global.llm;
  /* [OLD 2026-11-03 v0.4.1->v0.4.2] no job id: no progress line and no Stop
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
  [/OLD] */
  /* [OLD 2026-11-06 v0.9.0->v0.10.0] whole-scene sections only
  const run = async () => {
    const job = newJob("rewrite");
    ctx.store.setEph({ rewrite: { scene_id: s.id, busy: true, job } });
    try {
      const res = await rw.rewrite(ctx.p, s.id, ctx.eph.rewriteInstr || "", job);
      if (res.cancelled) { ctx.store.setEph({ rewrite: null }); ctx.actions.toast("Rewrite stopped.", "warn"); return; }
      ctx.store.setEph({ rewrite: { scene_id: s.id, proposal: res, warnings: res.warnings || [], editing: false } });
    } catch (err) {
      ctx.store.setEph({ rewrite: null });
      ctx.actions.toast("Rewrite failed: " + err.message, "error");
    } finally {
      delete ctx.store.eph.llmJobs[job];
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
  [/OLD] */
  // added 2026-11-06 v0.10.0: a pass tab sends the pass (POST /reelwright/llm/passes for that one pass)
  const run = async () => {
    const job = newJob("rewrite");
    ctx.store.setEph({ rewrite: { scene_id: s.id, pass: passK, busy: true, job } });
    try {
      let res;
      if (passK >= 0) {
        const r = await rw.llmPasses(ctx.p, s.id, [passK + 1], job, ctx.eph.rewriteInstr || "Improve clarity and visual precision, following the guide.");
        const got = (r.passes || []).find(x => Number(x.index) === passK + 1);
        if (r.cancelled && !got) { ctx.store.setEph({ rewrite: null }); ctx.actions.toast("Rewrite stopped.", "warn"); return; }
        if (!got) throw new Error(r.reason || r.error || "the LLM wrote nothing for this pass");
        res = { pass: got, sections: { ...got.sections }, warnings: r.warnings || [] };
      } else {
        res = await rw.rewrite(ctx.p, s.id, ctx.eph.rewriteInstr || "", job);
        if (res.cancelled) { ctx.store.setEph({ rewrite: null }); ctx.actions.toast("Rewrite stopped.", "warn"); return; }
      }
      ctx.store.setEph({ rewrite: { scene_id: s.id, pass: passK, proposal: res, warnings: res.warnings || [], editing: false } });
    } catch (err) {
      ctx.store.setEph({ rewrite: null });
      ctx.actions.toast("Rewrite failed: " + err.message, "error");
    } finally {
      delete ctx.store.eph.llmJobs[job];
    }
  };
  const accept = () => {
    const prop = rwState.proposal;
    if (prop.pass) {
      ctx.actions.editScene(s.id, (sc, q) => { applyWritten(sc, q, { passes: [{ ...prop.pass, sections: prop.sections }] }); }, { label: `Rewrite pass ${passK + 1}` });
    } else {
      /* [OLD 2026-11-12 v0.14.1->v0.14.2] the shots and lines written for a scene without shots stayed in the description
      ctx.actions.editScene(s.id, sc => {
        if (prop.raw !== undefined && prop.raw !== null) { sc.prompt.raw = prop.raw; sc.prompt.mode = "raw"; }
        if (prop.sections) for (const k of SECTION_KEYS) if (prop.sections[k] !== undefined) sc.prompt.sections[k] = prop.sections[k];
      }, { label: "Rewrite" });
    }
    ctx.store.setEph({ rewrite: null });
    ctx.actions.toast("Rewrite applied. Undo with Ctrl+Z.", "ok");
    [/OLD] */
      // added 2026-11-12 v0.14.2: a scene without shots takes the shots and spoken lines the rewrite wrote
      let filled = null;
      ctx.actions.editScene(s.id, (sc, q) => {
        if (prop.raw !== undefined && prop.raw !== null) { sc.prompt.raw = prop.raw; sc.prompt.mode = "raw"; }
        if (prop.sections) for (const k of SECTION_KEYS) if (prop.sections[k] !== undefined) sc.prompt.sections[k] = prop.sections[k];
        filled = fillScene(q, sc);
      }, { label: "Rewrite" });
      ctx.store.setEph({ rewrite: null });
      ctx.actions.toast(filled ? `Rewrite applied: ${fillWords(filled)} put on the timeline. Undo with Ctrl+Z.` : "Rewrite applied. Undo with Ctrl+Z.", "ok");
      return;
    }
    ctx.store.setEph({ rewrite: null });
    ctx.actions.toast("Rewrite applied. Undo with Ctrl+Z.", "ok");
  };
  let diffView = null;
  if (rwState?.proposal) {
    const prop = rwState.proposal;
    const cur = prop.pass && pt ? pt.texts[passK] : s.prompt.sections; // added 2026-11-06 v0.10.0: a pass's own texts
    const pairs = prop.raw !== undefined && prop.raw !== null ? [["raw", s.prompt.raw, prop.raw]]
      : SECTION_KEYS.filter(k => prop.sections?.[k] !== undefined && prop.sections[k] !== (cur[k] || "")).map(k => [k, cur[k] || "", prop.sections[k]]);
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
    // [OLD 2026-11-06 v0.9.0->v0.10.0] title: "Prompt rewriter", help: "scene.rewrite", tint: "dlg",
    title: passK >= 0 ? `Prompt rewriter · pass ${passK + 1}` : "Prompt rewriter", help: "scene.rewrite", tint: "dlg", // added 2026-11-06 v0.10.0
    actions: h("span", { class: "mono rw-dim small", help: "global.llm" }, llm.model ? `${llm.model}` : "set up in Global → LLM"),
    children: [
      h("div", { class: "rw-row" }, instr,
        button({ label: rwState?.busy ? "Rewriting…" : "Rewrite", icon: "wand", variant: "pink", help: "scene.rewrite.run", key: `rewrite-run-${s.id}`, disabled: !!rwState?.busy, onClick: run })),
      rwState?.busy && llmBusyRow(ctx, rwState.job, "scene.rewrite.stop"), // added 2026-11-03 v0.4.2
      h("div", { class: "rw-dim small" }, "Runs only when you press Rewrite, never during a render. Tags and <d>…</d> lines are kept as written."),
      /* [OLD 2026-11-06 v0.9.0->v0.10.0] on Whole scene of a multi-pass scene; the card is now only on a pass tab there
      // added 2026-11-05 v0.8.0: what Rewrite changes in a scene of several passes (Write prompts writes the passes)
      passLayout(ctx.p, s).passes.length > 1 && h("div", { class: "rw-dim small", help: "scene.rewrite.passes" }, "This scene has several passes: Rewrite changes the scene note and the shared sections. Write prompts (Prompt card) writes each pass's own sections."),
      [/OLD] */
      // added 2026-11-06 v0.10.0
      passK >= 0 && h("div", { class: "rw-dim small", help: "scene.rewrite.passes" }, `Rewrites pass ${passK + 1}'s own sections (${fmtTime(plan.passes[passK].start)}–${fmtTime(plan.passes[passK].end)}), with its shots and spoken lines. Other passes and the Whole scene texts stay as they are.`),
      diffView,
    ],
  });
}

// added 2026-11-03 v0.4.2: what a running LLM request is doing, and a button to stop it
function llmBusyRow(ctx, job, stopHelp) {
  return h("div", { class: "rw-row rw-llm-busy" },
    // [OLD 2026-11-06 v0.10.1->v0.10.2] h("span", { class: "rw-dim small mono grow", help: "global.llm.progress" }, jobLine(ctx.eph.llmJobs[job])),
    jobText(job, ctx.eph.llmJobs[job], { class: "rw-dim small mono grow", help: "global.llm.progress" }), // added 2026-11-06 v0.10.2: updated in place
    outputButton(ctx, { job, title: "LLM output", key: `llm-out-${job}` }), // added 2026-11-12 v0.15.0
    button({ label: "Stop", icon: "close", small: true, help: stopHelp, onClick: () => rw.llmCancel(job).catch(() => {}) }));
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
      // added 2026-11-03 v0.5.0
      b.song && h("div", { class: "rw-dim small", help: "scene.budget.song" }, "One audio slot is the soundtrack: every pass gets the part of the song it covers, so cast voice samples are not sent."),
      passBudgets(ctx, s), // added 2026-11-03 v0.6.0
    ],
  });
}

// added 2026-11-03 v0.6.0: a long scene's budget per pass (model.sceneBudget(p, s, pass)); the meters above show the
// fullest pass. A pass over a limit is marked.
function passBudgets(ctx, s) {
  const p = ctx.p;
  const passes = planScene(p, s, sceneIndex(p, s.id)).passes;
  if (passes.length < 2) return null;
  const over = x => x.pictures > 9 || x.videos > 3 || x.audio > 3 || x.files > 12 || x.videoSeconds > 15 || x.audioSeconds > 15;
  return h("div", { class: "rw-budget-passes", help: "scene.budget.pass" },
    h("div", { class: "rw-dim small" }, `The meters show the fullest of ${passes.length} passes. Each pass:`),
    passes.map((ps, k) => {
      const x = sceneBudget(p, s, ps);
      return h("div", { class: ["rw-budget-pass mono small", over(x) && "over"], help: "scene.budget.pass" },
        h("b", null, `Pass ${k + 1}`),
        h("span", null, `${x.pictures} pic · ${x.videos} vid · ${x.audio} aud${x.song ? " (song)" : ""} · ${x.files} files`),
        over(x) && icon("warn", 11));
    }));
}

function refsCard(ctx, s) {
  const p = ctx.p;
  const edit = (id, fn) => ctx.actions.editScene(s.id, sc => { const r = sc.refs.find(q => q.id === id); if (r) fn(r); });
  // [OLD 2026-11-06 v0.8.0->v0.9.0] const addable = p.assets.map(a => ({ value: a.id, label: `${a.code} · ${a.name || a.file.split("/").pop()}` }));
  const addable = p.assets.map(a => ({ value: a.id, label: `${a.code} · ${a.name || a.file.split("/").pop()}`, pre: assetGroupName(p, a) })); // added 2026-11-06 v0.9.0: group first
  return section({
    title: "References", help: "scene.refs",
    actions: h("span", { class: "rw-dim small" }, "tags renumber per pass"),
    children: [
      // [OLD 2026-11-06 v0.8.0->v0.9.0] s.refs.length === 0 && h("div", { class: "rw-empty sm", help: "scene.refs" }, "No references. Add one below or drag from the Timeline's asset bin."),
      s.refs.length === 0 && h("div", { class: "rw-empty sm", help: "scene.refs" }, "No references. Add one below."),  // added 2026-11-06 v0.9.0: no asset bin
      // [OLD 2026-11-12 v0.14.4->v0.15.0] s.refs.map(r => {  (no reordering)
      // added 2026-11-12 v0.15.0: drag a reference's grip to put it elsewhere in the list (one undo step)
      sortable({ id: `refs-${s.id}`, onMove: (from, to) => ctx.actions.editScene(s.id, sc => { moveItem(sc.refs, from, to); }, { label: "Reorder references" }), rows: s.refs.map(r => {
        const a = findAsset(p, r.asset);
        // [OLD 2026-11-12 v0.14.4->v0.15.0] if (!a) return h("div", { class: "rw-note warn" }, "A reference points at a deleted asset.", button({ label: "Remove", small: true, help: "scene.refs.remove", onClick: () => ctx.actions.editScene(s.id, sc => { sc.refs = sc.refs.filter(x => x.id !== r.id); }) }));
        if (!a) return h("div", { class: "rw-note warn" }, dragGrip({ help: "scene.refs.order", key: `ref-grip-${r.id}` }), "A reference points at a deleted asset.", button({ label: "Remove", small: true, help: "scene.refs.remove", onClick: () => ctx.actions.editScene(s.id, sc => { sc.refs = sc.refs.filter(x => x.id !== r.id); }) })); // added 2026-11-12 v0.15.0: grip
        const kc = kindClass(a.kind);
        const ret = r.retention || a.defaults.retention;
        const overridden = (r.retention && r.retention !== a.defaults.retention) || r.role !== a.defaults.role;
        const roles = a.kind === "image" ? ROLES : ["reference"];
        return h("div", { class: ["rw-ref", overridden && "over"] },
          dragGrip({ help: "scene.refs.order", key: `ref-grip-${r.id}` }), // added 2026-11-12 v0.15.0
          // [OLD 2026-11-06 v0.9.0->v0.10.0] a.kind === "image" ? h("img", { class: "rw-ref-thumb", src: viewURL(a.file, "input"), alt: "" }) : h("span", { class: "rw-ref-thumb rw-bg-" + kc + "-soft" }, icon(a.kind, 16)),
          // added 2026-11-06 v0.10.0: the same <img> across renders (it blinked while a render ran)
          a.kind === "image" ? kept(ctx, "ref-" + r.id, viewURL(a.file, "input"), () => h("img", { class: "rw-ref-thumb", src: viewURL(a.file, "input"), alt: "" })) : h("span", { class: "rw-ref-thumb rw-bg-" + kc + "-soft" }, icon(a.kind, 16)),
          h("div", { class: "rw-ref-body" },
            h("div", { class: "rw-row" }, h("b", { class: "mono rw-c-" + kc }, a.code), h("b", { class: "rw-ellipsis" }, a.name || a.file.split("/").pop()),
              overridden && dot("override", "scene.refs.overridden"), h("span", { class: "rw-flex" }),
              button({ icon: "trash", small: true, variant: "ghost", help: "scene.refs.remove", onClick: () => ctx.actions.editScene(s.id, sc => { sc.refs = sc.refs.filter(x => x.id !== r.id); }) })),
            h("div", { class: "rw-row wrap" },
              /* [OLD 2026-11-03 v0.5.1->v0.6.0] no keys (focus came back by position)
              select({ options: roles, value: r.role, help: "scene.refs.role", onChange: v => edit(r.id, x => { x.role = v; }) }),
              r.role === "keyframe" && number({ value: Number(r.time.toFixed(3)), min: 0, max: s.duration, step: 1 / FPS, width: "80px", unit: "s", help: "scene.refs.time", onChange: v => edit(r.id, x => { x.time = v ?? 0; }) }),
              r.role === "reference" && select({ options: retentionOptions(a.kind), value: ret, help: "scene.refs.retention", mono: true, onChange: v => edit(r.id, x => { x.retention = v === a.defaults.retention ? "" : v; }) }),
              a.kind === "video" && toggle({ value: r.soundtrack, label: "soundtrack", help: "scene.refs.soundtrack", onChange: v => edit(r.id, x => { x.soundtrack = v; }) })),
              [/OLD] */
              // added 2026-11-03 v0.6.0: keys by reference id
              // [OLD 2026-11-12 v0.11.0->v0.12.0] select({ options: roles, value: r.role, help: "scene.refs.role", key: `ref-role-${r.id}`, onChange: v => edit(r.id, x => { x.role = v; }) }),
              // [OLD 2026-11-12 v0.11.0->v0.12.0] r.role === "keyframe" && number({ value: Number(r.time.toFixed(3)), min: 0, max: s.duration, step: 1 / FPS, width: "80px", unit: "s", help: "scene.refs.time", key: `ref-t-${r.id}`, onChange: v => edit(r.id, x => { x.time = v ?? 0; }) }),
              // added 2026-11-12 v0.12.0: a pose reference picks its character (the first one of the scene to start with)
              select({ options: roles, value: r.role, help: "scene.refs.role", key: `ref-role-${r.id}`, onChange: v => edit(r.id, x => { x.role = v; if (v === "pose" && !x.cast) x.cast = sceneChars(p, s)[0]?.id || ""; }) }),
              r.role === "pose" && poseCast(ctx, s, r, edit),
              (r.role === "keyframe" || r.role === "pose") && number({ value: Number(r.time.toFixed(3)), min: 0, max: s.duration, step: 1 / FPS, width: "80px", unit: "s", help: r.role === "pose" ? "scene.refs.poseTime" : "scene.refs.time", key: `ref-t-${r.id}`, onChange: v => edit(r.id, x => { x.time = v ?? 0; }) }),
              r.role === "reference" && select({ options: retentionOptions(a.kind), value: ret, help: "scene.refs.retention", mono: true, key: `ref-ret-${r.id}`, onChange: v => edit(r.id, x => { x.retention = v === a.defaults.retention ? "" : v; }) }),
              // [OLD 2026-11-12 v0.13.1->v0.14.0] a.kind === "video" && toggle({ value: r.soundtrack, label: "soundtrack", help: "scene.refs.soundtrack", key: `ref-snd-${r.id}`, onChange: v => edit(r.id, x => { x.soundtrack = v; }) })),
              a.kind === "video" && toggle({ value: r.soundtrack, label: "with sound", help: "scene.refs.soundtrack", key: `ref-snd-${r.id}`, onChange: v => edit(r.id, x => { x.soundtrack = v; }) })), // added 2026-11-12 v0.14.0: plainer label
            // added 2026-11-12 v0.14.0: the part of a video or audio asset this reference sends
            (a.kind === "video" || a.kind === "audio") && r.role === "reference" && clipEditor(ctx, s, r, a, edit),
            // [OLD 2026-11-03 v0.6.0 review] r.role === "reference" && keepChips({ values: r.keep.length ? r.keep : a.defaults.keep, help: "scene.refs.keep", onChange: v => edit(r.id, x => { x.keep = v; }) }),
            r.role === "reference" && keepChips({ values: r.keep.length ? r.keep : a.defaults.keep, help: "scene.refs.keep", key: `ref-keep-${r.id}`, onChange: v => edit(r.id, x => { x.keep = v; }) }), // added 2026-11-03 v0.6.0 review: key
            r.role === "pose" && poseNote(p, s, r, a), // added 2026-11-12 v0.12.0
            // added 2026-11-02 v0.3.4: the asset's description as it is used here (edit it in the Assets tab)
            a.kind !== "audio" && h("button", { type: "button", class: ["rw-ref-desc link rw-ellipsis", !a.description && "empty"], help: "scene.refs.description",
              title: a.description || "", onClick: () => { ctx.store.setEph({ selectedAsset: a.id }); ctx.actions.setTab("assets"); } },
            a.description ? a.description : r.role === "reference" ? "No description: add one in the Assets tab" : "No description")));
      // [OLD 2026-11-12 v0.14.4->v0.15.0] }),
      }) }), // added 2026-11-12 v0.15.0: end of sortable
      // [OLD 2026-11-12 v0.13.1->v0.14.0] addable.length ? h("div", { class: "rw-row" }, select({ options: addable, value: "", placeholder: "+ Add a reference…", help: "scene.refs.add", onChange: v => {
      addable.length ? h("div", { class: "rw-row" }, select({ options: addable, value: "", placeholder: "+ Add a reference…", help: "scene.refs.add", key: `ref-add-${s.id}`, onChange: v => { // added 2026-11-12 v0.14.0: key
        const a = findAsset(p, v);
        // [OLD 2026-11-12 v0.11.0->v0.12.0] if (a) ctx.actions.editScene(s.id, sc => { sc.refs.push({ id: newId("r"), asset: a.id, role: a.defaults.role, time: 0, retention: "", keep: [], soundtrack: !!a.defaults.soundtrack }); });
        // added 2026-11-12 v0.12.0: cast (a pose picture's default role starts it with the scene's first character)
        const role = a && a.defaults.role === "pose" && a.kind !== "image" ? "reference" : a?.defaults.role; // only a picture poses
        if (a) ctx.actions.editScene(s.id, sc => { sc.refs.push({ id: newId("r"), asset: a.id, role, time: 0, retention: "", keep: [], soundtrack: !!a.defaults.soundtrack, cast: role === "pose" ? sceneChars(p, s)[0]?.id || "" : "" }); });
      } })) : h("div", { class: "rw-dim small" }, "Upload assets in the Assets tab first."),
    ],
  });
}

// ---- added 2026-11-12 v0.14.0: clips of video and audio references (Sencer: "when using video or audio references,
// allow to select from-to timestamps/frames of source video. we should be able to use the same video/audio asset in a
// single scene multiple times, with different start/end timestamps/durations, with or without audio (for videos)").
// Each reference has From / To (r.in / r.out, seconds on whole frames; To empty = the asset's end). The fields take
// seconds (4.5), frames (108f) or a time (0:04.5, 1:02:03.25). The bar shows the clip in the whole file; drag its ends.
// Preview plays the file: From here / To here take its position, Play clip plays From to To. Each reference's @ tag
// (@V1, @V1.2 for the second one of V1) names that clip in the prompt.

// "4.5", "4.5s", "108f", "0:04.5", "1:02:03.25" -> seconds; "" -> null; anything else -> NaN
export function parseClipTime(text) {
  const t = String(text ?? "").trim().toLowerCase().replace(",", ".");
  if (!t) return null;
  let m = /^(\d+(?:\.\d+)?)\s*f$/.exec(t);
  if (m) return Number(m[1]) / FPS;
  m = /^(\d+(?:\.\d+)?)\s*s?$/.exec(t);
  if (m) return Number(m[1]);
  m = /^(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)$/.exec(t);
  if (m) return (Number(m[1] || 0) * 60 + Number(m[2])) * 60 + Number(m[3]);
  return NaN;
}

// [OLD 2026-11-12 v0.15.1->v0.16.0] function clipTimeField(ctx, { label, value, placeholder, help, key, onCommit }) {
export function clipTimeField(ctx, { label, value, placeholder, help, key, onCommit }) { // exported 2026-11-12 v0.16.0: Cast → Video anchors
  const show = v => (v === null || v === undefined ? "" : fmtTime(v));
  return h("label", { class: "rw-clip-field", help },
    h("span", { class: "rw-dim small" }, label, value !== null && value !== undefined && h("span", { class: "mono" }, ` · ${framesOf(value)} f`)),
    h("input", {
      type: "text", class: "rw-input mono", value: show(value), placeholder, help, key, spellcheck: false,
      onChange: e => {
        const v = parseClipTime(e.target.value);
        if (Number.isNaN(v)) { e.target.value = show(value); ctx.actions.toast("Type seconds (4.5), frames (108f) or a time (0:04.5).", "warn"); return; }
        onCommit(v === null ? null : snapFrame(Math.max(0, v)));
      },
      onKeydown: e => { if (e.key === "Enter") { e.preventDefault(); e.target.blur(); } },
    }));
}

/* [OLD 2026-11-12 v0.16.0->v0.16.1] scene references only; Cast → Video anchors uses the same editor now (see below)
function clipEditor(ctx, s, r, a, edit) {
  const c = refClip(r, a);
  const dur = Number(a.duration) || 0;
  const tok = refTokens(ctx.p, s)[r.id] || "@" + a.code;
  const many = s.refs.filter(x => x.asset === a.id && x.role === "reference").length > 1;
  const secs = c.seconds;
  const bad = dur > 0 && c.start >= dur - 0.5 / FPS ? `starts after the end of ${a.code} (${fmtTime(dur)})`
    : r.out !== null && r.out !== undefined && r.out <= c.start + 0.5 / FPS ? "ends before it starts"
      : "";
  const note = bad || (secs !== null && secs > 15 + 1e-6 ? "only the first 15 s is sent" : secs !== null && secs < 2 - 1e-6 ? "H3 references are 2–15 s" : "");
  const open = !!ctx.eph.clipPreview?.[r.id];
  const setOpen = v => ctx.store.setEph({ clipPreview: { ...(ctx.eph.clipPreview || {}), [r.id]: v } });
  return h("div", { class: "rw-clip", help: "scene.refs.clip" },
    h("div", { class: "rw-row rw-clip-row" },
      h("button", { type: "button", class: ["rw-clip-tok mono", many && "many"], help: "scene.refs.token", key: `clip-tok-${r.id}`,
        onClick: e => copyWithToast(tok, e.currentTarget, "tag") }, tok),
      h("span", { class: "rw-dim small rw-ellipsis" }, refTrimmed(r) ? "a part of the file" : "the whole file"),
      h("span", { class: "rw-flex" }),
      refTrimmed(r) && button({ label: "Whole file", small: true, variant: "ghost", help: "scene.refs.clipReset", key: `clip-reset-${r.id}`, onClick: () => edit(r.id, x => { x.in = 0; x.out = null; }) }),
      button({ label: open ? "Hide" : "Preview", icon: a.kind === "video" ? "video" : "audio", small: true, variant: "ghost", help: "scene.refs.clipPreview", key: `clip-prev-${r.id}`, onClick: () => setOpen(!open) })),
    h("div", { class: "rw-clip-grid" },
      clipTimeField(ctx, { label: "From", value: r.in || 0, help: "scene.refs.clipFrom", key: `clip-in-${r.id}`, onCommit: v => edit(r.id, x => { x.in = v ?? 0; }) }),
      clipTimeField(ctx, { label: "To", value: r.out ?? null, placeholder: "end", help: "scene.refs.clipTo", key: `clip-out-${r.id}`,
        onCommit: v => edit(r.id, x => { x.out = v; }) }),
      clipTimeField(ctx, { label: "Length", value: secs, placeholder: "?", help: "scene.refs.clipLength", key: `clip-len-${r.id}`,
        onCommit: v => edit(r.id, x => { x.out = v === null ? null : snapFrame((x.in || 0) + Math.max(1 / FPS, v)); }) })),
    dur > 0 && clipBar(ctx, r, a, c, edit),
    note && h("div", { class: ["rw-note", bad ? "err" : "warn", "rw-clip-note"], help: "scene.refs.clip" }, icon("warn", 12), `${tok} ${note}.`),
    open && clipPreview(ctx, r, a, c, edit));
}
[/OLD] */

// added 2026-11-12 v0.16.1: the same clip editor for a scene reference and for a cast member's video anchor (Sencer:
// "add the same options to video anchors as in scene tab/reference card/video reference. preview, from and to buttons
// etc."). `r` is anything with id / in / out; `s` is the scene (null for a video anchor). opts:
//   help  name -> help key (default "scene.refs." + name)       key   data-key prefix (default "clip")
//   tok   the clip's name in its notes (default its @ tag)       token false: no @ tag chip (a video anchor has none)
//   short the note for a clip under 2 s
export function clipEditor(ctx, s, r, a, edit, opts = {}) {
  const o = clipOpts(opts);
  const c = refClip(r, a);
  const dur = Number(a.duration) || 0;
  const tok = opts.tok || (s && refTokens(ctx.p, s)[r.id]) || "@" + a.code;
  const many = !!s && s.refs.filter(x => x.asset === a.id && x.role === "reference").length > 1;
  const secs = c.seconds;
  const bad = dur > 0 && c.start >= dur - 0.5 / FPS ? `starts after the end of ${a.code} (${fmtTime(dur)})`
    : r.out !== null && r.out !== undefined && r.out <= c.start + 0.5 / FPS ? "ends before it starts"
      : "";
  const note = bad || (secs !== null && secs > 15 + 1e-6 ? "only the first 15 s is sent" : secs !== null && secs < 2 - 1e-6 ? (opts.short || "H3 references are 2–15 s") : "");
  const open = !!ctx.eph.clipPreview?.[r.id];
  const setOpen = v => ctx.store.setEph({ clipPreview: { ...(ctx.eph.clipPreview || {}), [r.id]: v } });
  return h("div", { class: "rw-clip", help: o.hk("clip") },
    h("div", { class: "rw-row rw-clip-row" },
      opts.token !== false && h("button", { type: "button", class: ["rw-clip-tok mono", many && "many"], help: o.hk("token"), key: `${o.kp}-tok-${r.id}`,
        onClick: e => copyWithToast(tok, e.currentTarget, "tag") }, tok),
      h("span", { class: "rw-dim small rw-ellipsis" }, refTrimmed(r) ? "a part of the file" : "the whole file"),
      h("span", { class: "rw-flex" }),
      refTrimmed(r) && button({ label: "Whole file", small: true, variant: "ghost", help: o.hk("clipReset"), key: `${o.kp}-reset-${r.id}`, onClick: () => edit(r.id, x => { x.in = 0; x.out = null; }) }),
      button({ label: open ? "Hide" : "Preview", icon: a.kind === "video" ? "video" : "audio", small: true, variant: "ghost", help: o.hk("clipPreview"), key: `${o.kp}-prev-${r.id}`, onClick: () => setOpen(!open) })),
    h("div", { class: "rw-clip-grid" },
      clipTimeField(ctx, { label: "From", value: r.in || 0, help: o.hk("clipFrom"), key: `${o.kp}-in-${r.id}`, onCommit: v => edit(r.id, x => { x.in = v ?? 0; }) }),
      clipTimeField(ctx, { label: "To", value: r.out ?? null, placeholder: "end", help: o.hk("clipTo"), key: `${o.kp}-out-${r.id}`,
        onCommit: v => edit(r.id, x => { x.out = v; }) }),
      clipTimeField(ctx, { label: "Length", value: secs, placeholder: "?", help: o.hk("clipLength"), key: `${o.kp}-len-${r.id}`,
        onCommit: v => edit(r.id, x => { x.out = v === null ? null : snapFrame((x.in || 0) + Math.max(1 / FPS, v)); }) })),
    dur > 0 && clipBar(ctx, r, a, c, edit, o),
    note && h("div", { class: ["rw-note", bad ? "err" : "warn", "rw-clip-note"], help: o.hk("clip") }, icon("warn", 12), `${tok} ${note}.`),
    open && clipPreview(ctx, r, a, c, edit, o));
}
// added 2026-11-12 v0.16.1: help keys and data-key prefix of one clip editor
function clipOpts(opts = {}) {
  return { hk: name => (opts.help ? opts.help(name) : "scene.refs." + name), kp: opts.key || "clip" };
}

// the whole file as a bar with the clip on it; drag an end to move From / To (on frames)
// [OLD 2026-11-12 v0.16.0->v0.16.1] function clipBar(ctx, r, a, c, edit) {
function clipBar(ctx, r, a, c, edit, o = clipOpts()) { // added 2026-11-12 v0.16.1: o = help keys (video anchors)
  const dur = Number(a.duration) || 0;
  const end = c.end ?? dur;
  const pct = t => Math.max(0, Math.min(100, (t / dur) * 100)) + "%";
  const sel = h("span", { class: "rw-clip-sel", style: { left: pct(c.start), width: `calc(${pct(end)} - ${pct(c.start)})` } });
  const tip = h("span", { class: "rw-clip-tip mono" });
  // [OLD 2026-11-12 v0.16.0->v0.16.1] const bar = h("div", { class: "rw-clip-bar", help: "scene.refs.clipBar" }, sel, tip);
  const bar = h("div", { class: "rw-clip-bar", help: o.hk("clipBar"), dataset: { clipBar: `${o.kp}-${r.id}` } }, sel, tip); // added 2026-11-12 v0.16.1: found again after a re-render
  const handle = which => {
    // [OLD 2026-11-12 v0.16.0->v0.16.1] const el = h("span", { class: ["rw-clip-h", which], help: "scene.refs.clipBar", style: { left: pct(which === "in" ? c.start : end) } });
    const el = h("span", { class: ["rw-clip-h", which], help: o.hk("clipBar"), style: { left: pct(which === "in" ? c.start : end) } }); // added 2026-11-12 v0.16.1
    el.addEventListener("pointerdown", e => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      let v = which === "in" ? c.start : end;
      /* [OLD 2026-11-12 v0.16.0->v0.16.1] measured and drew on this render's bar: a re-render during the drag (autosave,
         a render's progress) detached it, its width became 0 and To jumped to the end of the file
      const move = ev => {
        const rect = bar.getBoundingClientRect();
        const t = snapFrame(Math.max(0, Math.min(dur, ((ev.clientX - rect.left) / Math.max(1, rect.width)) * dur)));
        v = which === "in" ? Math.min(t, end - 1 / FPS) : Math.max(t, c.start + 1 / FPS);
        el.style.left = pct(v);
        const a0 = which === "in" ? v : c.start, b0 = which === "in" ? end : v;
        sel.style.left = pct(a0);
        sel.style.width = `calc(${pct(b0)} - ${pct(a0)})`;
        tip.textContent = `${fmtTime(a0)} – ${fmtTime(b0)} · ${(b0 - a0).toFixed(2)} s`;
        tip.style.left = pct(v);
        bar.classList.add("dragging");
      };
      [/OLD] */
      // added 2026-11-12 v0.16.1: the bar on screen now (a re-render replaces it; found by its data-clip-bar), and
      // nothing measured on a bar that is not on screen
      const root = bar.closest(".rw-root") || document;
      const live = () => (bar.isConnected ? bar : root.querySelector(`.rw-clip-bar[data-clip-bar="${CSS.escape(bar.dataset.clipBar)}"]`));
      const move = ev => {
        const b = live();
        const rect = b?.getBoundingClientRect();
        if (!rect || rect.width < 1) return;
        const t = snapFrame(Math.max(0, Math.min(dur, ((ev.clientX - rect.left) / rect.width) * dur)));
        v = which === "in" ? Math.min(t, end - 1 / FPS) : Math.max(t, c.start + 1 / FPS);
        const a0 = which === "in" ? v : c.start, b0 = which === "in" ? end : v;
        const hEl = b.querySelector(`.rw-clip-h.${which}`), sEl = b.querySelector(".rw-clip-sel"), tEl = b.querySelector(".rw-clip-tip");
        if (hEl) hEl.style.left = pct(v);
        if (sEl) { sEl.style.left = pct(a0); sEl.style.width = `calc(${pct(b0)} - ${pct(a0)})`; }
        if (tEl) { tEl.textContent = `${fmtTime(a0)} – ${fmtTime(b0)} · ${(b0 - a0).toFixed(2)} s`; tEl.style.left = pct(v); }
        b.classList.add("dragging");
      };
      const up = ev => {
        window.removeEventListener("pointermove", move, true);
        window.removeEventListener("pointerup", up, true);
        window.removeEventListener("pointercancel", up, true);
        // [OLD 2026-11-12 v0.16.0->v0.16.1] bar.classList.remove("dragging");
        bar.classList.remove("dragging");
        live()?.classList.remove("dragging"); // added 2026-11-12 v0.16.1
        if (ev.type === "pointercancel") return;
        if (which === "in" && v !== c.start) edit(r.id, x => { x.in = v; });
        if (which === "out" && v !== end) edit(r.id, x => { x.out = v >= dur - 0.5 / FPS ? null : v; });
      };
      window.addEventListener("pointermove", move, true);
      window.addEventListener("pointerup", up, true);
      window.addEventListener("pointercancel", up, true);
    });
    return el;
  };
  bar.append(handle("in"), handle("out"));
  return bar;
}

// the file in a player kept across renders; From here / To here / Play clip
// [OLD 2026-11-12 v0.16.0->v0.16.1] function clipPreview(ctx, r, a, c, edit) {
function clipPreview(ctx, r, a, c, edit, o = clipOpts()) { // added 2026-11-12 v0.16.1: o = help keys and data-key prefix
  const url = viewURL(a.file, "input");
  const el = kept(ctx, "clip-" + r.id, url, () => {
    const m = h(a.kind === "video" ? "video" : "audio", { class: "rw-clip-media", src: url, controls: true, preload: "metadata", playsinline: true });
    m.addEventListener("timeupdate", () => { if (m.__rwStopAt != null && m.currentTime >= m.__rwStopAt) { m.pause(); m.__rwStopAt = null; } });
    return m;
  });
  const end = c.end;
  /* [OLD 2026-11-12 v0.16.0->v0.16.1] fixed help keys and data-keys (scene references only)
  return h("div", { class: "rw-clip-prev", help: "scene.refs.clipPreview" }, el,
    h("div", { class: "rw-row wrap" },
      button({ label: "From here", small: true, help: "scene.refs.clipHere", key: `clip-here-in-${r.id}`, onClick: () => {
        const t = snapFrame(el.currentTime || 0);
        edit(r.id, x => { x.in = t; if (x.out !== null && x.out !== undefined && x.out <= t) x.out = null; });
      } }),
      button({ label: "To here", small: true, help: "scene.refs.clipHere", key: `clip-here-out-${r.id}`, onClick: () => {
        const t = snapFrame(el.currentTime || 0);
        if (t <= (r.in || 0)) { ctx.actions.toast("To must be after From.", "warn"); return; }
        edit(r.id, x => { x.out = t; });
      } }),
      button({ label: "Play clip", icon: "play", small: true, help: "scene.refs.clipPlay", key: `clip-play-${r.id}`, onClick: () => {
        el.currentTime = c.start;
        el.__rwStopAt = end ?? null;
        el.play?.()?.catch?.(() => {});
      } }),
      h("span", { class: "rw-dim small mono" }, `${fmtTime(c.start)} – ${end !== null ? fmtTime(end) : "end"}`)));
  [/OLD] */
  // added 2026-11-12 v0.16.1: the help keys and data-keys of the editor it is in (a scene reference or a video anchor)
  return h("div", { class: "rw-clip-prev", help: o.hk("clipPreview") }, el,
    h("div", { class: "rw-row wrap" },
      button({ label: "From here", small: true, help: o.hk("clipHere"), key: `${o.kp}-here-in-${r.id}`, onClick: () => {
        const t = snapFrame(el.currentTime || 0);
        edit(r.id, x => { x.in = t; if (x.out !== null && x.out !== undefined && x.out <= t) x.out = null; });
      } }),
      button({ label: "To here", small: true, help: o.hk("clipHere"), key: `${o.kp}-here-out-${r.id}`, onClick: () => {
        const t = snapFrame(el.currentTime || 0);
        if (t <= (r.in || 0)) { ctx.actions.toast("To must be after From.", "warn"); return; }
        edit(r.id, x => { x.out = t; });
      } }),
      button({ label: "Play clip", icon: "play", small: true, help: o.hk("clipPlay"), key: `${o.kp}-play-${r.id}`, onClick: () => {
        el.currentTime = c.start;
        el.__rwStopAt = end ?? null;
        el.play?.()?.catch?.(() => {});
      } }),
      h("span", { class: "rw-dim small mono" }, `${fmtTime(c.start)} – ${end !== null ? fmtTime(end) : "end"}`)));
}

// added 2026-11-12 v0.12.0: pose references (role "pose"): a picture whose body pose one character of the scene takes,
// in the shot at its time. The prompt cites it in that character's line and transfers only the pose (Sencer: "so the
// real characters can use the same pose as from a given picture").
function sceneChars(p, s) {
  return scenePeople(p, s).people.map(x => x.c).filter(c => c.kind === "character");
}
function poseCast(ctx, s, r, edit) {
  const p = ctx.p;
  const here = sceneChars(p, s);
  const others = p.cast.filter(c => c.kind === "character" && !here.some(x => x.id === c.id));
  const options = [...here.map(c => ({ value: c.id, label: c.name || "Unnamed" })), ...others.map(c => ({ value: c.id, label: `${c.name || "Unnamed"} (not in this scene)` }))];
  return select({ options, value: r.cast || "", placeholder: "+ Whose pose?", help: "scene.refs.poseCast", key: `ref-cast-${r.id}`, width: "170px", onChange: v => edit(r.id, x => { x.cast = v; }) });
}
function poseNote(p, s, r, a) {
  const c = p.cast.find(x => x.id === r.cast && x.kind === "character");
  const here = c && sceneChars(p, s).some(x => x.id === c.id);
  const shot = s.shots.filter(x => Number(x.t) <= Number(r.time) + 1e-6).length || 1;
  const tag = n => n && /^[\p{L}\p{N}_'’-]+$/u.test(n) ? "@" + n : `@{${n}}`;
  if (a.kind !== "image") return h("div", { class: "small rw-c-warn", help: "scene.refs.pose" }, "Only a picture can be a pose reference: this one is not sent.");
  if (!c) return h("div", { class: "small rw-c-warn", help: "scene.refs.pose" }, "Pick whose pose it is. Until then it is not sent.");
  if (!here) return h("div", { class: "small rw-c-warn", help: "scene.refs.pose" }, `${c.name} is not in this scene, so it is not sent. Add ${c.name} under Cast.`);
  return h("div", { class: "small rw-dim", help: "scene.refs.pose" }, `${c.name} takes this pose in shot ${shot}; only the pose is used, the person in the picture does not appear. Say it in the shot, e.g. “${tag(c.name)} strikes the pose from @${a.code}”.`);
}

function castCard(ctx, s) {
  const p = ctx.p;
  const inScene = new Set(s.cast.map(c => c.id));
  const avail = p.cast.filter(c => !inScene.has(c.id)).map(c => ({ value: c.id, label: `${c.name} · ${c.kind}` }));
  return section({
    title: "Cast in this scene", help: "scene.cast",
    children: [
      s.cast.length === 0 && h("div", { class: "rw-empty sm", help: "scene.cast" }, "Nobody from the story bible yet."),
      // [OLD 2026-11-12 v0.14.4->v0.15.0] s.cast.map(sc => {  (no reordering)
      // added 2026-11-12 v0.15.0: drag a cast member's grip to put them elsewhere in the list (one undo step)
      sortable({ id: `cast-${s.id}`, onMove: (from, to) => ctx.actions.editScene(s.id, x => { moveItem(x.cast, from, to); }, { label: "Reorder cast" }), rows: s.cast.map(sc => {
        const c = findCast(p, sc.id);
        if (!c) return null;
        const anchor = findAsset(p, c.anchors[0]);
        // added 2026-11-03 v0.4.1: when the anchors go as one sheet in this scene, the sheet is what is shown
        const packed = castPacks(p, s, c);
        return h("div", { class: "rw-list-row" },
          dragGrip({ help: "scene.cast.order", key: `cast-grip-${c.id}` }), // added 2026-11-12 v0.15.0
          // [OLD 2026-11-03 v0.4.0->v0.4.1] anchor ? h("img", { class: "rw-avatar", src: viewURL(anchor.file, "input"), alt: "" }) : h("span", { class: "rw-avatar empty" }, icon("cast", 14)),
          // [OLD 2026-11-06 v0.9.0->v0.10.0] packed ? h("img", { class: "rw-avatar sheet", src: ctx.host.apiURL(sheetURL(p, c, 96)), alt: "", help: "scene.cast.sheet" })
          // [OLD 2026-11-06 v0.9.0->v0.10.0]   : anchor ? h("img", { class: "rw-avatar", src: viewURL(anchor.file, "input"), alt: "" }) : h("span", { class: "rw-avatar empty" }, icon("cast", 14)),
          // added 2026-11-06 v0.10.0: the same <img> across renders; the sheet is made by the server (not cached), so a
          // new <img> fetched and drew it again on every render and it blinked while a render ran
          packed ? kept(ctx, "castsheet-" + c.id, sheetURL(p, c, 96), () => h("img", { class: "rw-avatar sheet", src: ctx.host.apiURL(sheetURL(p, c, 96)), alt: "", help: "scene.cast.sheet" }))
            : anchor ? kept(ctx, "castav-" + c.id, viewURL(anchor.file, "input"), () => h("img", { class: "rw-avatar", src: viewURL(anchor.file, "input"), alt: "" })) : h("span", { class: "rw-avatar empty" }, icon("cast", 14)),
          /* [OLD 2026-11-02 v0.1.0->v0.2.0] speaker IDs are assigned per clip now
          h("div", { class: "grow" }, h("b", null, c.name), h("div", { class: "rw-dim small" }, `${c.kind}${c.speaker ? " · " + c.speaker : ""} · ${c.anchors.length} anchor${c.anchors.length === 1 ? "" : "s"}${c.lora?.name ? " · LoRA" : ""}`)),
          [/OLD] */
          /* [OLD 2026-11-02 v0.3.3->v0.3.4] no description shown
          h("div", { class: "grow" }, h("b", null, c.name), h("div", { class: "rw-dim small" }, `${c.kind} · ${c.anchors.length} anchor${c.anchors.length === 1 ? "" : "s"}${c.lora?.name ? " · LoRA" : ""}`)),
          [/OLD] */
          (() => {
            const d = castDescription(p, c);
            // added 2026-11-12 v0.16.0: how big each picture of its sheet reaches H3 here (0: no sheet)
            const tilePx = sceneTilePixels(p, s, c);
            const tileN = tilePx ? scenePeople(p, s).people.find(x => x.c.id === c.id)?.ids.length || 0 : 0;
            // added 2026-11-08 v0.11.0: a part says whose; without its character in the scene it is left out
            const owner = findCast(p, partOwner(c, new Map(p.cast.map(x => [x.id, x]))));
            const ownerHere = owner && (inScene.has(owner.id) || s.dialogue.some(x => x.speaker === owner.id));
            return h("div", { class: "grow", style: { "min-width": "0" } }, h("b", null, c.name),
              // [OLD 2026-11-08 v0.10.3->v0.11.0] h("div", { class: "rw-dim small" }, `${c.kind} · ${c.anchors.length} anchor${c.anchors.length === 1 ? "" : "s"}${c.lora?.name ? " · LoRA" : ""}`),
              owner ? h("div", { class: ["small", ownerHere ? "rw-dim" : "rw-c-warn"], help: "scene.cast.part" },
                ownerHere ? `part of ${owner.name}: in ${owner.name}'s subject · ${c.anchors.length} anchor${c.anchors.length === 1 ? "" : "s"}` : `part of ${owner.name}, who is not in this scene: left out`)
                // [OLD 2026-11-12 v0.15.1->v0.16.0] : h("div", { class: "rw-dim small" }, `${c.kind} · ${c.anchors.length} anchor${c.anchors.length === 1 ? "" : "s"}${c.lora?.name ? " · LoRA" : ""}`),
                : h("div", { class: "rw-dim small" }, `${c.kind} · ${c.anchors.length} anchor${c.anchors.length === 1 ? "" : "s"}${(c.video_anchors || []).length ? ` · ${c.video_anchors.length} video anchor${c.video_anchors.length === 1 ? "" : "s"}` : ""}${c.lora?.name ? " · LoRA" : ""}`), // v0.16.0: video anchors
              // [OLD 2026-11-12 v0.15.1->v0.16.0] h("div", { class: "rw-dim small rw-ellipsis", help: "scene.cast.description", title: d.text }, d.text ? (d.asset ? `from ${d.asset.code}: ${d.text}` : d.text) : "No description"));
              h("div", { class: "rw-dim small rw-ellipsis", help: "scene.cast.description", title: d.text }, d.text ? (d.asset ? `from ${d.asset.code}: ${d.text}` : d.text) : "No description"),
              // added 2026-11-12 v0.16.0: its sheet makes each picture too small for a reliable identity
              tilePx > 0 && tilePx < SMALL_TILE_PX && h("div", { class: "small rw-c-warn", help: "scene.cast.smallSheet" },
                `${tileN} pictures in one sheet: about ${tilePx} px each in H3, too small for identity`));
          })(),
          // [OLD 2026-11-03 v0.5.1->v0.6.0] c.outfits.length > 0 && select({ options: c.outfits.map(o => ({ value: o.id, label: o.name })), value: sc.outfit || c.default_outfit, help: "scene.cast.outfit",
          c.outfits.length > 0 && select({ options: c.outfits.map(o => ({ value: o.id, label: o.name })), value: sc.outfit || c.default_outfit, help: "scene.cast.outfit", key: `cast-outfit-${c.id}`,
            onChange: v => ctx.actions.editScene(s.id, x => { x.cast.find(q => q.id === c.id).outfit = v; }) }),
          button({ icon: "close", small: true, variant: "ghost", help: "scene.cast.remove", onClick: () => ctx.actions.editScene(s.id, x => { x.cast = x.cast.filter(q => q.id !== c.id); }) }));
      // [OLD 2026-11-12 v0.14.4->v0.15.0] }),
      }) }), // added 2026-11-12 v0.15.0: end of sortable
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
          // [OLD 2026-11-03 v0.5.1->v0.6.0] number({ value: ov ?? gl.strength, min: -4, max: 4, step: 0.05, width: "74px", help: "scene.loras.strength", onChange: v => setL(l => {
          number({ value: ov ?? gl.strength, min: -4, max: 4, step: 0.05, width: "74px", help: "scene.loras.strength", key: `lora-g-${gl.id}`, onChange: v => setL(l => {
            l.strengths = l.strengths || {};
            if (v === null || v === gl.strength) delete l.strengths[gl.id]; else l.strengths[gl.id] = v;
          }) }),
          ov !== undefined ? button({ icon: "refresh", small: true, variant: "ghost", help: "common.reset", onClick: () => setL(l => { delete l.strengths[gl.id]; }) }) : h("span", { class: "rw-reset-ph" }));
      }),
      // [OLD 2026-11-12 v0.14.4->v0.15.0] (o.items || []).map(it => h("div", { class: "rw-lora-row" },  (no reordering)
      // added 2026-11-12 v0.15.0: drag a scene LoRA's grip to put it elsewhere among the scene's own LoRAs (one undo step;
      // Global's LoRAs keep Global's order, set on the Global tab)
      sortable({ id: `loras-${s.id}`, onMove: (from, to) => ctx.actions.editScene(s.id, sc => { if (sc.overrides.loras) moveItem(sc.overrides.loras.items, from, to); }, { label: "Reorder scene LoRAs" }), rows: (o.items || []).map(it => h("div", { class: "rw-lora-row" },
        dragGrip({ help: "scene.loras.order", key: `lora-grip-${it.id}` }), // added 2026-11-12 v0.15.0
        dot("override"),
        /* [OLD 2026-11-03 v0.5.1->v0.6.0] no keys
        select({ options: loraList, value: it.name, placeholder: "choose LoRA", mono: true, help: "scene.loras.name", onChange: v => setL(l => { l.items.find(x => x.id === it.id).name = v; }) }),
        h("span", { class: "rw-dim small" }, "scene"),
        number({ value: it.strength, min: -4, max: 4, step: 0.05, width: "74px", help: "scene.loras.strength", onChange: v => setL(l => { l.items.find(x => x.id === it.id).strength = v ?? 1; }) }),
        [/OLD] */
        select({ options: loraList, value: it.name, placeholder: "choose LoRA", mono: true, help: "scene.loras.name", key: `lora-name-${it.id}`, onChange: v => setL(l => { l.items.find(x => x.id === it.id).name = v; }) }),
        h("span", { class: "rw-dim small" }, "scene"),
        number({ value: it.strength, min: -4, max: 4, step: 0.05, width: "74px", help: "scene.loras.strength", key: `lora-s-${it.id}`, onChange: v => setL(l => { l.items.find(x => x.id === it.id).strength = v ?? 1; }) }),
        // [OLD 2026-11-12 v0.14.4->v0.15.0] button({ icon: "trash", small: true, variant: "ghost", help: "scene.loras.remove", onClick: () => setL(l => { l.items = l.items.filter(x => x.id !== it.id); }) }))),
        button({ icon: "trash", small: true, variant: "ghost", help: "scene.loras.remove", onClick: () => setL(l => { l.items = l.items.filter(x => x.id !== it.id); }) }))) }), // added 2026-11-12 v0.15.0: end of sortable
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

// added 2026-11-05 v0.7.0: Render → Merge scenes' "Scene tab → In the cut" brings the card into view once
export function afterRender(ctx) {
  if (!ctx.eph.scrollToCut) return;
  ctx.eph.scrollToCut = false;
  const card = ctx.root.querySelector(".rw-cut");
  const box = card?.closest(".rw-cols");
  if (!card || !box) return;
  const sc = (ctx.root.getBoundingClientRect().width / (ctx.root.offsetWidth || 1)) || 1;
  box.scrollTop += (card.getBoundingClientRect().top - box.getBoundingClientRect().top) / sc - 8;
  card.classList.add("rw-flash");
  setTimeout(() => card.classList.remove("rw-flash"), 1400);
}

export function render(ctx) {
  const s = ctx.scene;
  const issues = ctx.planFor(s.id)?.issues || [];
  const wholeScene = promptTabOf(ctx, s) < 0; // added 2026-11-06 v0.9.0
  return h("div", { class: "rw-scene-tab" },
    navigator(ctx),
    issues.length > 0 && h("div", { class: "rw-banner warn", help: "app.issues" }, icon("warn", 13), issues.map(i => i.message).join(" · ")),
    h("div", { class: "rw-cols", dataset: { scroll: "scene-cols" } },
      // [OLD 2026-11-05 v0.6.1->v0.7.0] h("div", { class: "rw-col narrow" }, durationCard(ctx, s), startCard(ctx, s), overridesCard(ctx, s), notesCard(ctx, s)),
      h("div", { class: "rw-col narrow" }, durationCard(ctx, s), startCard(ctx, s), cutCard(ctx, s), overridesCard(ctx, s), notesCard(ctx, s)), // added 2026-11-05 v0.7.0: In the cut
      // [OLD 2026-11-06 v0.8.0->v0.9.0] h("div", { class: "rw-col wide" }, promptCard(ctx, s), shotsCard(ctx, s), dialogueCard(ctx, s), previewCard(ctx, s), rewriteCard(ctx, s)),
      // added 2026-11-06 v0.9.0: on a pass tab the pass's own shots and dialogue are in the Prompt card, so the whole
      // scene's cards are hidden
      // [OLD 2026-11-06 v0.9.0->v0.10.0] h("div", { class: "rw-col wide" }, promptCard(ctx, s), wholeScene && shotsCard(ctx, s), wholeScene && dialogueCard(ctx, s), previewCard(ctx, s), rewriteCard(ctx, s)),
      // added 2026-11-06 v0.10.0: the rewriter works on one pass: hidden on Whole scene of a scene with several passes
      // (structured), shown on a pass tab (it rewrites that pass) and in single-pass or raw scenes
      h("div", { class: "rw-col wide" }, promptCard(ctx, s), wholeScene && shotsCard(ctx, s), wholeScene && dialogueCard(ctx, s), previewCard(ctx, s),
        !(wholeScene && s.prompt.mode !== "raw" && passLayout(ctx.p, s).passes.length > 1) && rewriteCard(ctx, s)),
      h("div", { class: "rw-col mid" }, budgetCard(ctx, s), refsCard(ctx, s), castCard(ctx, s), lorasCard(ctx, s))));
}

