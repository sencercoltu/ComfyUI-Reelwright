// added 2026-11-05 v0.8.0: per-pass prompt texts (scene.prompt.passes), dialogue lengths, the camera picker's lists
// and "Write prompts" (POST /reelwright/llm/passes, one LLM request per pass). Used by the Scene tab's Prompt, Shots
// and Dialogue cards and by Global → Import a script (the batch after an import).
//
// model.js gains passTexts / dialogueSeconds and the official camera presets in v0.8.0 (Agent P); this module uses
// them when they are there and falls back to the same rules (PLAN contract P1) when they are not.

import * as model from "./model.js";
import { rw } from "./api.js";
import { newJob } from "./llmjob.js";
// [OLD 2026-11-12 v0.14.2->v0.14.3] import { fillScene, fillWords } from "./shotfill.js"; // added 2026-11-12 v0.14.2: a scene written without shots gets them
// [OLD 2026-11-12 v0.14.3->v0.14.4] import { writeShots, fillWords } from "./shotfill.js"; // v0.14.2: a scene written without shots gets them; v0.14.3: shots on the timeline take their written text, framing and camera move
import { writeShots, takePassShots, fillWords } from "./shotfill.js"; // v0.14.2-v0.14.4: the written shots go into the scene's shots

const { FPS, SECTION_KEYS, planScene, sceneIndex } = model;

export const emptySections = () => Object.fromEntries(SECTION_KEYS.map(k => [k, ""]));
const str = v => (typeof v === "string" ? v : typeof v === "number" ? String(v) : "");
const num = (v, d = 0) => (Number.isFinite(Number(v)) && v !== null && v !== "" ? Number(v) : d);
const hasText = sec => !!sec && SECTION_KEYS.some(k => str(sec[k]).trim());

// The passes of a scene as the planner makes them (model.planScene, the same as the backend's planner).
export function passLayout(p, s) {
  const i = sceneIndex(p, s.id);
  return planScene(p, s, i < 0 ? undefined : i);
}

// Stored pass texts mapped onto the current passes: {texts: [sections per current pass], moved: bool, movedPasses:
// [1-based], stored: bool}. model.passTexts when it exists, else the contract's rule: each current pass takes the
// stored entry it overlaps most; it "moved" when that entry's range differs by more than a frame.
export function passTextsOf(p, s, plan = passLayout(p, s)) {
  const stored = Array.isArray(s.prompt?.passes) ? s.prompt.passes.filter(x => x && typeof x === "object") : [];
  const passes = plan?.passes || [];
  const any = stored.some(x => hasText(x.sections));
  let texts, movedList, unused = [];
  if (typeof model.passTexts === "function") {
    const r = model.passTexts(p, s, plan) || {};
    texts = passes.map((_, k) => ({ ...emptySections(), ...(r.texts?.[k] || {}) }));
    movedList = Array.isArray(r.moved) ? r.moved : [];
    unused = Array.isArray(r.unused) ? r.unused : [];
  } else {
    texts = [];
    movedList = [];
    passes.forEach((ps, k) => {
      let best = null, bestOv = 0;
      for (const st of stored) {
        const ov = Math.min(ps.end, num(st.end)) - Math.max(ps.start, num(st.start));
        if (ov > bestOv + 1e-9) { best = st; bestOv = ov; }
      }
      const sec = emptySections();
      if (best) for (const key of SECTION_KEYS) sec[key] = str(best.sections?.[key]);
      texts.push(sec);
      if (best && hasText(best.sections) && (Math.abs(num(best.start) - ps.start) > 1 / FPS + 1e-6 || Math.abs(num(best.end) - ps.end) > 1 / FPS + 1e-6)) movedList.push(k + 1);
    });
  }
  // the editor offers "Use the new layout" only when a text would move (empty stored entries move nothing) or no pass
  // gets it any more (unused: 1-based stored entries)
  return { texts, moved: any && (movedList.length > 0 || unused.length > 0), movedPasses: movedList, unused, stored: any };
}

// Store the texts shown for the current passes with the current ranges (what "Use the new layout" does, and what any
// edit of a pass section does first, so the stored entries are what the tabs show).
export function adoptLayout(sc, p, plan = passLayout(p, sc)) {
  if (typeof model.relayoutPassTexts === "function") { sc.prompt.passes = model.relayoutPassTexts(p, sc, plan); return; }
  const { texts } = passTextsOf(p, sc, plan);
  sc.prompt.passes = plan.passes.map((ps, k) => ({ start: ps.start, end: ps.end, sections: { ...emptySections(), ...texts[k] } }));
}

// Set one section of pass k (0-based) in a scene being edited.
export function setPassSection(sc, p, k, key, value) {
  const plan = passLayout(p, sc);
  if (typeof model.setPassSection === "function") { model.setPassSection(p, sc, plan, k + 1, key, value); return; } // k: 1-based there
  const { moved } = passTextsOf(p, sc, plan);
  const cur = Array.isArray(sc.prompt.passes) ? sc.prompt.passes : [];
  if (moved || cur.length !== plan.passes.length) adoptLayout(sc, p, plan);
  const list = sc.prompt.passes;
  if (!list[k]) list[k] = { start: plan.passes[k]?.start ?? 0, end: plan.passes[k]?.end ?? 0, sections: emptySections() };
  list[k].sections = { ...emptySections(), ...(list[k].sections || {}), [key]: value };
}

// ---- dialogue (contract P1: duration, else max(1.0, words / 2.5); CJK characters count as a quarter word) ----
const CJK = /[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]/gu;
export function estimateSeconds(text) {
  const t = str(text);
  const cjk = (t.match(CJK) || []).length;
  const words = t.replace(CJK, " ").split(/\s+/).filter(Boolean).length;
  return Math.max(1.0, (words + cjk / 4) / 2.5);
}
export function dialogueSecs(d) {
  if (typeof model.dialogueSeconds === "function") return model.dialogueSeconds(d);
  const v = Number(d?.duration);
  return Number.isFinite(v) && v > 0 ? v : estimateSeconds(d?.text);
}

// Where a line or shot meets a pass seam: [{k (1-based pass after the seam), t (seconds), kind: "cut"|"overlap"}].
// A pass after an overlap seam takes over at the end of the pass before (new content starts there).
export function seamsOf(plan) {
  const ps = plan?.passes || [];
  return ps.slice(1).map((x, j) => ({ k: j + 2, t: x.seam_before === "overlap" ? ps[j].end : x.start, kind: x.seam_before, from: x.start, to: ps[j].end }));
}

// The pass that holds a dialogue line (as planScene places it) and where it runs past that pass's end.
export function lineSeam(plan, s, d) {
  if (typeof model.dialogueSpans === "function") {
    const x = model.dialogueSpans(s, plan).find(q => q.id === d.id);
    if (x?.past_end) return { kind: "end", t: s.duration, end: x.end };
    if (x && x.seam !== null && x.seam !== undefined) return { kind: "seam", t: x.seam, end: x.end, pass: (x.pass || 0) + 1 };
    if (x) return null;
  }
  const passes = plan?.passes || [];
  const owner = passes.find(ps => ps.dialogue?.some(x => x.id === d.id));
  const end = d.t + dialogueSecs(d);
  if (end > s.duration + 1e-6) return { kind: "end", t: s.duration, end };
  if (owner && owner.index < passes.length && end > owner.end + 1e-6) return { kind: "seam", t: owner.end, end, pass: owner.index + 1 };
  return null;
}

// added 2026-11-06 v0.10.0: where a line that runs past its seam could start instead (the seam note's quick fixes and
// the Dialogue card's "Fix lines at seams"; the seams themselves stay where they are). null when the line fits:
// {seam (lineSeam), earlier: a start in its own pass that ends 0.1 s before the seam or the scene's end (null when the
// line is longer than the room), later: one frame after the seam, where the next pass has it (null for a line past
// the scene's end, or when it would run past the end from there)}. Times are on whole frames, in scene seconds.
export function seamFixes(plan, s, d) {
  const seam = lineSeam(plan, s, d);
  if (!seam) return null;
  const secs = dialogueSecs(d);
  const owner = (plan?.passes || []).find(ps => ps.dialogue?.some(x => x.id === d.id));
  const from = !owner || owner.index === 1 ? 0 : owner.start + (owner.overlap_frames || 0) / FPS;
  const ms = t => Math.round(t * 1000) / 1000;
  const e = Math.floor((seam.t - 0.1 - secs) * FPS + 1e-6) / FPS;
  const earlier = e >= from - 1e-6 && e < d.t - 1e-6 ? ms(Math.max(e, from)) : null;
  const l = (Math.round(seam.t * FPS) + 1) / FPS;
  const later = seam.kind === "seam" && l + secs <= s.duration + 1e-6 ? ms(l) : null;
  return { seam, earlier, later };
}

// added 2026-11-06 v0.10.0: the smaller of the two moves (Fix lines at seams), null when neither is possible
export function seamFixTime(fx, t) {
  const c = [fx?.earlier, fx?.later].filter(x => x !== null && x !== undefined);
  return c.length ? c.reduce((a, b) => (Math.abs(b - t) < Math.abs(a - t) ? b : a)) : null;
}

// The seams inside a shot (a cut seam at its start is where it begins, so it does not count).
export function shotSeams(plan, start, end) {
  return seamsOf(plan).filter(x => x.t > start + 0.5 / FPS && x.t < end - 0.5 / FPS);
}

// ---- camera picker (contract P1; base-en.txt 4.3) ----
// The official H3 moves: [label, phrase]. model.js lists them as presets from v0.8.0 (project.camera_presets); this
// list fills in when a project does not have them yet.
export const OFFICIAL_MOVES = [
  ["Zoom In", "the camera zooms in"], ["Zoom Out", "the camera zooms out"],
  ["Push In", "the camera pushes in"], ["Pull Out", "the camera pulls out"],
  ["Pan Left", "the camera pans left"], ["Pan Right", "the camera pans right"],
  ["Truck Left", "the camera trucks left"], ["Truck Right", "the camera trucks right"],
  ["Tilt Up", "the camera tilts up"], ["Tilt Down", "the camera tilts down"],
  ["Pedestal Up", "the camera pedestals up"], ["Pedestal Down", "the camera pedestals down"],
  ["Arc Shot", "the camera arcs around the subject"], ["Tracking Shot", "the camera tracks the moving subject"],
  ["Static Shot", "the camera holds a static shot"],
  ["Shake Slightly", "the camera shakes slightly"], ["Shake Strongly", "the camera shakes strongly"],
  ["POV", "the camera takes the subject's point of view"],
  ["Roll Clockwise", "the camera rolls clockwise"], ["Roll Counterclockwise", "the camera rolls counterclockwise"],
];
export const FRAMINGS = ["extreme wide", "wide", "medium wide", "medium", "medium close-up", "close-up", "extreme close-up",
  "over-the-shoulder", "two-shot", "insert", "low angle", "high angle", "overhead", "dutch angle"];
const cap = t => t.charAt(0).toUpperCase() + t.slice(1);

// Options of the camera combobox: the project's presets (official moves first), then any official move it lacks.
export function cameraOptions(p) {
  const official = Array.isArray(model.DEFAULT_CAMERA) && model.DEFAULT_CAMERA.length >= 20 ? model.DEFAULT_CAMERA : OFFICIAL_MOVES;
  const names = new Set(official.map(m => (Array.isArray(m) ? m[0] : m.name)));
  const presets = (p.camera_presets || []).filter(c => c && c.text);
  const out = [], seen = new Set();
  const add = (value, label) => { if (value && !seen.has(value)) { seen.add(value); out.push({ value, label }); } };
  for (const c of presets) if (names.has(c.name)) add(c.text, c.name);
  for (const m of official) { const [n, t] = Array.isArray(m) ? m : [m.name, m.text]; add(t, n); }
  for (const c of presets) if (!names.has(c.name)) add(c.text, c.name);
  return out;
}
// Moves where amplitude and speed mean little (notes_P): the picker disables them and a switch to one clears them.
const STILL_MOVES = new Set(["Static Shot", "POV", "Shake Slightly", "Shake Strongly"]);
export function stillMove(camera) {
  const official = Array.isArray(model.DEFAULT_CAMERA) && model.DEFAULT_CAMERA.length >= 20 ? model.DEFAULT_CAMERA : OFFICIAL_MOVES;
  return !!camera && official.some(m => { const [n, t] = Array.isArray(m) ? m : [m.name, m.text]; return t === camera && STILL_MOVES.has(n); });
}
export const framingOptions = () => [{ value: "", label: "any framing" },
  ...(Array.isArray(model.FRAMINGS) ? model.FRAMINGS : FRAMINGS).filter(Boolean).map(f => ({ value: f, label: cap(f) }))];

// ---- "Write prompts" (POST /reelwright/llm/passes) ----
// eph.passWrite: {origin: "scene"|"import", items: [{sid, passes: [1-based]|null, state: "wait"|"run"|"done"|"failed"|
// "stopped", error}], at, job, stop, label}. One run at a time; each scene's answer is one undo step.

export function writeBusy(ctx) {
  return !!ctx.eph.passWrite?.running;
}

// Put a written answer into a scene being edited: a single-pass scene gets it in its own sections (it has no tabs; its
// pass 1 uses them), a multi-pass scene in scene.prompt.passes (the current layout, then the written passes).
// added 2026-11-12 v0.14.2: a single-pass scene with no shots on the timeline takes the shots and spoken lines the
// answer wrote (shotfill.fillScene); report.fill gets the counts
// [OLD 2026-11-12 v0.14.1->v0.14.2] export function applyWritten(sc, p, res) {
export function applyWritten(sc, p, res, report = null) {
  const plan = passLayout(p, sc);
  const got = (Array.isArray(res?.passes) ? res.passes : []).filter(x => x && typeof x === "object" && x.sections);
  if (!got.length) return 0;
  const clean = sec => Object.fromEntries(SECTION_KEYS.map(k => [k, str(sec?.[k])]));
  if (plan.passes.length < 2) {
    // an empty section means "the shared / automatic text" (the LLM leaves auto subjects and retention empty), so it
    // keeps what the scene has
    const one = got.find(x => num(x.index, 1) === 1) || got[0];
    const sec = clean(one.sections);
    for (const k of SECTION_KEYS) if (sec[k].trim()) sc.prompt.sections[k] = sec[k];
    sc.prompt.passes = [];
    // [OLD 2026-11-12 v0.14.2->v0.14.3] const filled = fillScene(p, sc); // added 2026-11-12 v0.14.2
    const filled = writeShots(p, sc); // added 2026-11-12 v0.14.3: also a scene that already has its shots
    if (report) report.fill = filled;
    return 1;
  }
  // passes that were written for another range (the scene changed while the LLM wrote) keep the range they were
  // written for, so the Prompt card offers "Use the new layout"; otherwise model.writePassTexts (current layout)
  const far = (a, b) => Math.abs(a - b) > 1 / FPS + 1e-6;
  const moved = got.some(x => {
    const ps = plan.passes[Math.round(num(x.index, 0)) - 1];
    return !ps || far(num(x.start, ps.start), ps.start) || far(num(x.end, ps.end), ps.end);
  });
  if (typeof model.writePassTexts === "function" && !moved) {
    const items = got.map(x => ({ index: Math.round(num(x.index, 0)), sections: clean(x.sections) })).filter(x => x.index >= 1 && x.index <= plan.passes.length);
    // added 2026-11-12 v0.14.4: the shots that start in a written pass take their written text, framing and move
    const took = takePassShots(p, sc, plan, items);
    if (report) report.fill = took;
    model.writePassTexts(p, sc, plan, items);
    return items.length;
  }
  adoptLayout(sc, p, plan);
  let n = 0;
  for (const x of got) {
    const k = Math.round(num(x.index, 0)) - 1;
    if (k < 0 || k >= plan.passes.length) continue;
    sc.prompt.passes[k] = { start: num(x.start, plan.passes[k].start), end: num(x.end, plan.passes[k].end), sections: clean(x.sections) };
    n++;
  }
  return n;
}

// added 2026-11-12 v0.14.4: what Write prompts did with the shots it wrote (shotfill.writeShots / takePassShots)
function fillToast(f) {
  const s = n => `${n} shot${n === 1 ? "" : "s"}`;
  if (!f.updated) return `Put ${fillWords(f)} on the timeline from what the LLM wrote, with framing and camera moves; the description keeps the style.`;
  const done = f.added ? `Updated ${s(f.shots - f.added)} and added ${s(f.added)}` : `Updated ${s(f.shots)}`;
  const kept = f.kept ? `; the LLM wrote no line for ${f.kept === 1 ? "the last shot, which keeps its text" : `the last ${f.kept}, which keep their text`}` : "";
  return `${done}${f.lines ? ` and ${f.lines} spoken line${f.lines === 1 ? "" : "s"}` : ""} from what the LLM wrote (text, framing, camera move)${kept}. The description keeps the style.`;
}

// Run "Write prompts" for scenes [{sid, passes}] one after another. Resolves when done, stopped or failed.
export async function runWrite(ctx, items, { origin = "scene", label = "" } = {}) {
  const store = ctx.store;
  if (writeBusy(ctx)) return null;
  const run = { origin, label, running: true, stop: false, job: "", at: 0, items: items.map(x => ({ ...x, state: "wait", error: "" })) };
  store.setEph({ passWrite: run });
  let wrote = 0;
  for (let i = 0; i < run.items.length; i++) {
    const it = run.items[i];
    if (it.state === "done") continue;
    if (run.stop || store.eph.passWrite !== run) break;
    const scene = store.project.scenes.find(x => x.id === it.sid);
    if (!scene) { it.state = "failed"; it.error = "the scene was deleted"; continue; }
    const job = newJob("passes");
    Object.assign(run, { at: i, job });
    it.state = "run";
    store.setEph({ passWrite: run });
    try {
      const res = await rw.llmPasses(store.project, it.sid, it.passes, job);
      const n = Array.isArray(res?.passes) ? res.passes.length : 0;
      if (n && store.project.scenes.some(x => x.id === it.sid)) {
        const multi = passLayout(store.project, store.project.scenes.find(x => x.id === it.sid)).passes.length > 1;
        const what = it.passes?.length === 1 && multi ? `Write pass ${it.passes[0]}` : "Write prompts";
        // [OLD 2026-11-12 v0.14.1->v0.14.2] ctx.actions.editScene(it.sid, (sc, q) => { applyWritten(sc, q, res); }, { label: origin === "import" ? `${what}: ${scene.title}` : what });
        // added 2026-11-12 v0.14.2: say when the answer's shots and spoken lines were put on the timeline
        const rep = {};
        ctx.actions.editScene(it.sid, (sc, q) => { applyWritten(sc, q, res, rep); }, { label: origin === "import" ? `${what}: ${scene.title}` : what });
        // [OLD 2026-11-12 v0.14.2->v0.14.3] if (rep.fill && origin !== "import") ctx.actions.toast(`Put ${fillWords(rep.fill)} on the timeline from what the LLM wrote; the description keeps the style.`, "ok");
        /* [OLD 2026-11-12 v0.14.3->v0.14.4] no word on added shots or shots the answer left out
        if (rep.fill && origin !== "import") ctx.actions.toast(rep.fill.updated // added 2026-11-12 v0.14.3
          ? `Updated ${fillWords(rep.fill)} from what the LLM wrote (text, framing, camera move); the description keeps the style.`
          : `Put ${fillWords(rep.fill)} on the timeline from what the LLM wrote, with framing and camera moves; the description keeps the style.`, "ok");
        [/OLD] */
        if (rep.fill && origin !== "import") ctx.actions.toast(fillToast(rep.fill), "ok"); // added 2026-11-12 v0.14.4
        wrote++;
      }
      if (Array.isArray(res?.warnings) && res.warnings.length) it.warnings = res.warnings.map(String);
      // what is left of this scene after a Stop or a failure part way (/llm/passes answers the passes written so far)
      const asked = it.passes?.length ? it.passes : Array.from({ length: Number(res?.pass_count) || 0 }, (_, k) => k + 1);
      const left = asked.filter(k => !(res?.passes || []).some(x => Number(x?.index) === k));
      if (res?.cancelled) { it.state = "stopped"; if (n && left.length) it.passes = left; run.stop = true; break; }
      if (res?.error) { it.state = "failed"; it.error = String(res.error); if (n && left.length) it.passes = left; continue; }
      it.state = n ? "done" : "failed";
      if (!n) it.error = "the LLM wrote no pass";
    } catch (err) {
      it.state = "failed";
      it.error = err?.status === 404 ? "this Reelwright backend cannot write pass prompts yet (no /llm/passes)" : (err?.message || "failed");
      if (err?.status === 404) run.stop = true;
    } finally {
      delete store.eph.llmJobs[job];
    }
  }
  for (const it of run.items) if (it.state === "run" || (run.stop && it.state === "wait")) it.state = "stopped";
  Object.assign(run, { running: false, job: "", stop: false, wrote });
  if (store.eph.passWrite === run) store.setEph({ passWrite: run });
  return run;
}

export function stopWrite(ctx) {
  const run = ctx.eph.passWrite;
  if (!run?.running) return;
  run.stop = true;
  if (run.job) rw.llmCancel(run.job).catch(() => {});
  ctx.store.notify();
}
