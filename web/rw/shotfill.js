// Reelwright: shots and spoken lines taken from a written description.
// added 2026-11-12 v0.14.2 (Sencer: "when creating a single shot scene, the shot section (and dialogues) are not
// populated. They should be populated. currently everything shows only in detailed_description section.")
//
// A scene with no shots on the timeline is written by the LLM (Write prompts, the Prompt rewriter) as [Shot N] lines
// in its detailed_description, with the spoken lines in <d>…</d>. readWritten() takes that text apart:
// - the text before [Shot 1] (the style sentences) stays the description;
// - each [Shot N] becomes a shot: its "At MM:SS.mmm, the shot cuts to" is its start, the rest its text, without the
//   spoken lines;
// - each spoken line becomes a dialogue line: the speaker is the @name, cast name or (S1) before it, the language its
//   [Language], the delivery the verb ("mutters"), with the clause around it ("as the rain starts", ", her voice
//   breaking"); a line is timed after the one before it inside its shot (dialogueSeconds).
// fillScene() puts them in the scene. With automatic shots + dialogue on, the editor writes them back into the prompt
// ("[Shot 1] … <Subject 1> (S1) mutters, <d>[English] Almost home.</d>"), so H3 gets the same scene and every list
// (timeline lanes, captions, subtitles, voices) has it.

import { FPS, newId, planScene, sceneIndex, dialogueSeconds, snapFrame } from "./model.js";

const LABEL = /\[\s*shot\s*(\d+)\s*\]/gi;
const SPAN = /<d>([\s\S]*?)<\/d>/gi;
const CUT = /^At\s+(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\s*,\s*(?:the\s+shot\s+cuts\s+to\s*)?/i;
const LANG = /^\s*\[([^\]\n]{1,40})\]\s*/;
const NAME = "[\\p{L}\\p{N}\\p{M}_]+(?:['’.\\-][\\p{L}\\p{N}\\p{M}_]+)*";
const tagRe = () => new RegExp("@\\{([^}\\n]+)\\}|(?<![\\p{L}\\p{N}\\p{M}_@])@(?!@)(" + NAME + ")", "gu");
const SID_AT = /^\s*,?\s*\(\s*S(\d+)\s*\)/;
const SIDS = /\(\s*S(\d+)\s*\)/g;
const OFF = /\b(?:an?\s+|the\s+)?(?:off-?screen\s+voice|narrator|voice\s+from\s+off-?screen)\b/gi;
const STOP = /[.!?…](?=\s)|\n/g;
// what only finishes the line's sentence: a stop, or a clause after a comma / dash / a lower-case word (llm.py
// drop_foreign_lines uses the same rule)
const TAIL = /^\s*[.!?…]|^(?:\s*[,;:—–-]|\s+(?=[a-z]))[^<.!?\n]{0,120}[.!?…]/;
const VOICE = /,?\s*\b(?:with|in)\s+(?:(?:a|an|the|his|her|their|its)\s+)?[^,<:]*?\bvoice\b(?![\w-])[^,<:]*/gi;
const LEADS = /^(?:(?:as|while|when)\s+(?:he|she|they|it|we|i|you)\s+|who\s+|and\s+|then\s+)/i;

const key = s => String(s ?? "").replace(/’/g, "'").split(/\s+/).filter(Boolean).join(" ").toLowerCase();
const wordCount = s => String(s || "").split(/\s+/).filter(w => /[\p{L}\p{N}]/u.test(w)).length;
const squash = s => String(s || "").replace(/\s+/g, " ").replace(/\s+([,.;:!?…])/g, "$1").replace(/([,;:])\s*(?=[.!?…])/g, "").trim();
const escapeRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const lowerFirst = s => (s && /^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s);
const edges = s => squash(s).replace(/^[,;:—–\-\s]+/, "").replace(/[,;:—–\-\s]+$/, "").trim();

function sentence(s) {
  s = edges(s);
  if (!s) return "";
  s = s[0].toUpperCase() + s.slice(1);
  return /[.!?…"'”]$/.test(s) ? s : s + ".";
}

// cast members by name (case and ’ do not matter; "@Mara's" is Mara), and the plain names to look for, longest first
function castFinder(p) {
  const all = (p.cast || []).filter(c => c && typeof c.name === "string" && c.name.trim());
  const by = new Map(all.map(c => [key(c.name), c]));
  const find = name => {
    const c = by.get(key(name));
    if (c) return c;
    const m = /^(.+?)['’][sS]$/.exec(String(name || ""));
    return m ? by.get(key(m[1])) || null : null;
  };
  const plain = all.filter(c => (c.kind || "character") === "character").sort((a, b) => b.name.length - a.name.length)
    .map(c => ({ c, re: new RegExp("(?<![\\p{L}\\p{N}_@{])" + escapeRe(c.name.trim()) + "(?![\\p{L}\\p{N}_])", "giu") }));
  return { find, plain };
}

// the last speaker named in `lead` (the text of the line's sentence before it): {start, end, cast, off, sid, idOnly}
function lastMention(lead, cf) {
  let best = null;
  const take = (start, end, cast, off) => { if (!best || start >= best.start) best = { start, end, cast, off, sid: null }; };
  for (const m of lead.matchAll(tagRe())) { const c = cf.find(m[1] ?? m[2]); if (c) take(m.index, m.index + m[0].length, c, false); }
  for (const { c, re } of cf.plain) for (const m of lead.matchAll(re)) take(m.index, m.index + m[0].length, c, false);
  for (const m of lead.matchAll(OFF)) take(m.index, m.index + m[0].length, null, true);
  if (best) {
    const s = SID_AT.exec(lead.slice(best.end));
    if (s) { best.sid = "S" + s[1]; best.end += s[0].length; }
    else { const later = [...lead.slice(best.end).matchAll(SIDS)][0]; if (later) best.sid = "S" + later[1]; }
    return best;
  }
  const ids = [...lead.matchAll(SIDS)];
  const last = ids[ids.length - 1];
  return last ? { start: last.index, end: last.index + last[0].length, cast: null, off: false, sid: "S" + last[1], idOnly: true } : null;
}

// "folds the letter and mutters" -> ["folds the letter", "mutters"]; "mutters" -> ["", "mutters"]
function actionAndVerb(a) {
  a = edges(a);
  if (!a) return ["", ""];
  let at = -1, len = 0;
  for (const sep of [", and ", " and ", ", ", " then "]) {
    const i = a.lastIndexOf(sep);
    if (i > at) { at = i; len = sep.length; }
  }
  let action = at >= 0 ? a.slice(0, at) : "", verb = at >= 0 ? a.slice(at + len) : a;
  verb = edges(verb).replace(LEADS, "");
  if (wordCount(verb) > 6) return [a, ""];
  return [edges(action), edges(verb)];
}

// One shot's text without its spoken lines, and the lines: {text, lines: [{speaker, sid, language, delivery, text}]}.
// sMap: speaker IDs seen so far ("S1" -> cast id), shared by the shots of a scene.
function takeLines(body, cf, sMap) {
  const spans = [...body.matchAll(SPAN)];
  if (!spans.length) return { text: body, lines: [] };
  const lines = [], cuts = [];
  let floor = 0;
  for (const m of spans) {
    const at = m.index, end0 = at + m[0].length;
    let start = floor;
    for (const s of body.slice(floor, at).matchAll(STOP)) start = floor + s.index + s[0].length;
    const lead = body.slice(start, at);
    const men = lastMention(lead, cf);
    let speaker = "";
    if (men?.cast) speaker = men.cast.id;
    else if (men?.off) speaker = (/narrator/i.test(lead.slice(men.start, men.end)) && cf.find("narrator")?.id) || "";
    else if (men?.sid && sMap.has(men.sid)) speaker = sMap.get(men.sid);
    if (men?.sid && !sMap.has(men.sid) && (men.cast || men.off)) sMap.set(men.sid, speaker);
    const before = men ? lead.slice(0, men.start) : "";
    const named = men && !men.idOnly ? edges(lead.slice(men.start, men.end).replace(SIDS, "")) : "";
    const rest = (men ? lead.slice(men.end) : lead).replace(SIDS, " ").replace(VOICE, " ");
    const [action, verb] = actionAndVerb(rest);
    // a clause before the speaker that sets the moment ("As the rain starts, ") goes with the delivery; one that
    // frames the shot ("a close-up of ") stays in the text with the speaker
    let extra = "";
    const b = squash(before);
    let kept = "";
    if (action && wordCount(action) >= 2) kept = [b, named, action].filter(Boolean).join(" ");
    else if (b && /,$/.test(b) && wordCount(b) <= 10 && !named.startsWith("<")) extra = lowerFirst(edges(b));
    else if (b && wordCount(b) >= 2) kept = [b, named].filter(Boolean).join(" ");
    // the end of the sentence: ", her voice breaking." joins the delivery; the voiceover's closed lips are the
    // editor's own words
    let end = end0;
    const tail = TAIL.exec(body.slice(end0));
    let after = "";
    if (tail) {
      end += tail[0].length;
      const t = edges(tail[0].replace(/[.!?…]+\s*$/, ""));
      if (t && !/lips\s+remain/i.test(t)) after = t;
    }
    const inner = m[1];
    const lang = LANG.exec(inner);
    const words = squash(lang ? inner.slice(lang[0].length) : inner);
    const voiceover = /voice-?\s?over/i.test(rest);
    let delivery = voiceover ? "voiceover" : verb || "says";
    if (!voiceover) {
      const more = [extra, after].filter(Boolean).join(", ");
      if (more && (delivery + " " + more).length <= 80) delivery = extra && !after ? `${delivery} ${extra}` : after && !extra ? `${delivery}, ${after}` : `${delivery} ${extra}, ${after}`;
    }
    if (words) lines.push({ speaker, sid: men?.sid || null, who: named, language: lang ? lang[1].trim() : "", delivery, text: words });
    cuts.push([start, end, kept ? sentence(kept) : ""]);
    floor = end;
  }
  let out = "", pos = 0;
  for (const [a, z, kept] of cuts) {
    out += body.slice(pos, a) + (kept ? " " + kept + " " : " ");
    pos = z;
  }
  out += body.slice(pos);
  return { text: squash(out), lines };
}

// times inside a window, each after the one before, never past `end`
function spread(n, start, end, lengths) {
  const room = Math.max(0, end - start);
  const lead = Math.min(0.5, room * 0.1);
  const out = [];
  let t = start + lead;
  for (let i = 0; i < n; i++) { out.push(t); t += (lengths[i] || 1) + 0.3; }
  if (n && out[n - 1] > end - Math.min(0.5, room / (n + 1))) {
    for (let i = 0; i < n; i++) out[i] = start + lead + (room - lead) * i / n;
  }
  return out;
}

// The shots and spoken lines written in `desc` for scene sc (made in one pass: x), in scene time, or null when the
// text has no [Shot N] line and no spoken line. {pre, shots: [{t, text}], lines: [{speaker, t, language, delivery,
// text}]}
export function readWritten(p, sc, desc, x = null) {
  const text = String(desc || "").replace(/\r\n?/g, "\n");
  const spans = [...text.matchAll(SPAN)].map(m => [m.index, m.index + m[0].length]);
  const labels = [...text.matchAll(LABEL)].filter(m => !spans.some(([a, b]) => m.index > a && m.index < b));
  if (!labels.length && !spans.length) return null;
  const pre = labels.length ? squash(text.slice(0, labels[0].index)) : "";
  const chunks = labels.length ? labels.map((m, i) => text.slice(m.index + m[0].length, i + 1 < labels.length ? labels[i + 1].index : text.length))
    : [text];
  const duration = Math.max(1 / FPS, Number(sc.duration) || 0);
  // times written in a pass of a short scene are times in what H3 makes: the cut starts at keep_in
  const offset = x ? (Number(x.start) || 0) - (Number(x.keep_in) || 0) : 0;
  const cf = castFinder(p);
  const sMap = new Map();
  const shots = chunks.map((c, i) => {
    let body = c.trim();
    let t = i === 0 ? 0 : null;
    const cut = CUT.exec(body);
    if (cut) {
      if (i > 0) t = Number(cut[1]) * 60 + Number(cut[2]) + offset;
      body = body.slice(cut[0].length);
    }
    const got = takeLines(body, cf, sMap);
    // a shot that was only its speaker's line ("the shot cuts to @Bob (S2), who replies, <d>…</d>") shows the speaker
    const text = got.text || (got.lines[0]?.who || "");
    return { t, text: sentence(text), lines: got.lines };
  });
  // a start that is missing, outside the scene or not after the one before is spread between its neighbours
  const minGap = Math.min(0.5, duration / (shots.length + 1));
  const valid = shots.map((sh, i) => i === 0 || (sh.t !== null && sh.t > 0 && sh.t < duration - minGap / 2));
  for (let i = 1, last = 0; i < shots.length; i++) {
    if (!valid[i]) continue;
    if (shots[i].t < last + minGap) valid[i] = false; else last = shots[i].t;
  }
  shots[0].t = 0;
  for (let i = 1; i < shots.length; i++) {
    if (valid[i]) continue;
    let j = i;
    while (j < shots.length && !valid[j]) j++;
    const lo = shots[i - 1].t, hi = j < shots.length ? shots[j].t : duration;
    for (let k = i; k < j; k++) shots[k].t = lo + (hi - lo) * (k - i + 1) / (j - i + 1);
    i = j;
  }
  for (const sh of shots) sh.t = Math.max(0, Math.min(snapFrame(sh.t), duration - 1 / FPS));
  const lines = [];
  shots.forEach((sh, i) => {
    const end = i + 1 < shots.length ? shots[i + 1].t : duration;
    const at = spread(sh.lines.length, sh.t, end, sh.lines.map(d => dialogueSeconds({ text: d.text })));
    sh.lines.forEach((d, k) => lines.push({ ...d, t: Math.max(0, Math.min(snapFrame(at[k]), duration - 1 / FPS)) }));
  });
  return { pre, shots: shots.map(sh => ({ t: sh.t, text: sh.text })), lines };
}

// Can scene sc take its shots and lines from its description? (a structured prompt, made in one pass, no shots on the
// timeline yet). The reading, or null.
export function fillable(p, sc) {
  if (!sc || sc.prompt?.mode === "raw" || (sc.shots || []).length) return null;
  const i = sceneIndex(p, sc.id);
  const plan = planScene(p, sc, i < 0 ? undefined : i);
  if (plan.passes.length !== 1) return null;
  const got = readWritten(p, sc, sc.prompt?.sections?.detailed_description, plan.passes[0]);
  if (!got || (!got.shots.some(s => s.text) && !got.lines.length)) return null;
  return got;
}

// Put the shots and spoken lines written in sc's description on the timeline (sc is the scene being edited, p its
// project). The lines are added only when the scene has none; a speaker, and a cast member named with @ in a shot,
// joins the scene's cast (so their pictures and voice are sent). With automatic shots + dialogue on, the description
// keeps only the text before [Shot 1]. Returns {shots, lines} (counts) or null.
export function fillScene(p, sc) {
  const got = fillable(p, sc);
  if (!got) return null;
  sc.shots = got.shots.map(s => ({ id: newId("h"), t: s.t, camera: "", text: s.text }));
  let lines = 0;
  if (!(sc.dialogue || []).length && got.lines.length) {
    const lang = id => (p.cast || []).find(c => c.id === id)?.language || p.global?.defaults?.language || "English";
    sc.dialogue = got.lines.map(d => ({ id: newId("d"), speaker: d.speaker, t: d.t, language: d.language || lang(d.speaker), delivery: d.delivery || "says", text: d.text }));
    lines = sc.dialogue.length;
  }
  sc.cast = Array.isArray(sc.cast) ? sc.cast : [];
  const cf = castFinder(p);
  const named = [];
  for (const t of [got.pre, ...got.shots.map(x => x.text)]) for (const m of String(t || "").matchAll(tagRe())) { const c = cf.find(m[1] ?? m[2]); if (c) named.push(c.id); }
  for (const id of [...(sc.dialogue || []).map(d => d.speaker), ...named]) if (id && !sc.cast.some(c => c.id === id)) sc.cast.push({ id, outfit: "" });
  if (sc.prompt.auto?.shots) sc.prompt.sections.detailed_description = got.pre;
  return { shots: sc.shots.length, lines };
}

// "1 shot and 2 spoken lines"
export function fillWords(n) {
  if (!n) return "";
  const s = `${n.shots} shot${n.shots === 1 ? "" : "s"}`;
  return n.lines ? `${s} and ${n.lines} spoken line${n.lines === 1 ? "" : "s"}` : s;
}
