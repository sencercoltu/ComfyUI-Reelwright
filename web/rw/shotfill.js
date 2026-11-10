// Reelwright: shots and spoken lines taken from a written description.

import { FPS, newId, planScene, sceneIndex, dialogueSeconds, snapFrame, DEFAULT_CAMERA, FRAMINGS, fmtTime } from "./model.js";

const LABEL = /\[\s*shot\s*(\d+)\s*\]/gi;
const SPAN = /<d>([\s\S]*?)<\/d>/gi;
const CUT = /^At\s+(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\s*,\s*(?:the\s+shot\s+cuts\s+to\s*)?/i;
// A leading time is a cut with the cut's words (prompt.py CUT_STRICT),
// or when no spoken line follows in its sentence; "At 00:01.500, @Mara (S1) says, <d>…</d>" is that line's time
const CUT_STRICT = /^At\s+(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\s*,\s*the\s+(?:shot|camera)\s+(?:cuts|transitions|changes|switches|dissolves|fades)\s+to\s*/i;
function leadKind(body) {
  const m = CUT.exec(body);
  if (!m) return "";
  if (CUT_STRICT.test(body)) return "cut";
  const rest = body.slice(m[0].length);
  const d = rest.indexOf("<d>");
  const stop = /[.!?…](?=\s|$)/.exec(rest);
  return d >= 0 && (!stop || d < stop.index) ? "line" : "time";
}
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
// The time that opens a spoken line's sentence ("At 00:03.200, @Mara (S1) mutters, <d>…")
// or an action's, and the "At MM:SS.mmm," cues of a text (prompt.py CUE_TIME)
// The same as prompt.py CUE_TIME ("At" only; also after a colon)
const LINE_CUE = /^\s*At\s+(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\s*,\s*/;
const CUES = /(^\s*|[.!?…]\s+|:\s+)(At\s+)(\d{1,2}):(\d{2}(?:\.\d{1,3})?)(?=\s*,)/g;
// a word that reads in lower case after "At 00:04.600, " (names keep their capital)
const CUE_LOWER = /^(?:The|A|An|He|She|They|It|His|Her|Their|Its|Then|As|While|When|We|You|Both|Everyone|Someone|Nobody|This|That|These|Those|There|Now|Finally|Suddenly)\b/;

const key = s => String(s ?? "").replace(/’/g, "'").split(/\s+/).filter(Boolean).join(" ").toLowerCase();
const wordCount = s => String(s || "").split(/\s+/).filter(w => /[\p{L}\p{N}]/u.test(w)).length;
const squash = s => String(s || "").replace(/\s+/g, " ").replace(/\s+([,.;:!?…])/g, "$1").replace(/([,;:])\s*(?=[.!?…])/g, "").trim();
const escapeRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const lowerFirst = s => (s && /^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s);
const edges = s => squash(s).replace(/^[,;:—–\-\s]+/, "").replace(/[,;:—–\-\s]+$/, "").trim();

// ---- camera move and framing of a written shot ----------------------------------------------------------------
// The move of H3's guide (model.DEFAULT_CAMERA names) a sentence describes, first match wins; the sentence has to be
// about the camera ("camera" or "lens" in it) unless it is a short phrase such as "Slow push-in."
const MOVES = [
  ["Zoom In", /\bzoom(?:s|ing|ed)?\s+(?:slowly\s+|gently\s+)?in\b|\bzoom-in\b/],
  ["Zoom Out", /\bzoom(?:s|ing|ed)?\s+(?:slowly\s+|gently\s+)?out\b|\bzoom-out\b/],
  ["Pull Out", /\bpull(?:s|ing|ed)?\s+(?:slowly\s+|gently\s+)?(?:out|back|away)\b|\bpull-?(?:out|back)\b|\bdoll(?:y|ies|ying|ied)\s+(?:out|back)\b|\bdolly-out\b|\b(?:moves?|moving|drifts?|drifting|retreats?|retreating|backs?|backing)\s+(?:slowly\s+)?(?:back|away|out)\b/],
  ["Push In", /\bpush(?:es|ing|ed)?\s+(?:slowly\s+|gently\s+|steadily\s+)?(?:in|forward|closer)\b|\bpush-in\b|\bdoll(?:y|ies|ying|ied)\s+(?:in|forward|toward|towards|closer)\b|\bdolly-in\b|\b(?:moves?|moving|creeps?|creeping|drifts?|drifting|glides?|gliding|edges?|edging|inches?|inching)\s+(?:slowly\s+|gently\s+)?(?:in|forward|closer|toward|towards)\b|\bcloses?\s+in\b/],
  ["Pan Left", /\bpan(?:s|ning|ned)?\s+(?:slowly\s+|gently\s+|quickly\s+)?(?:to\s+the\s+)?left\b/],
  ["Pan Right", /\bpan(?:s|ning|ned)?\s+(?:slowly\s+|gently\s+|quickly\s+)?(?:to\s+the\s+)?right\b/],
  ["Truck Left", /\b(?:truck(?:s|ing|ed)?|slides?|sliding|crab(?:s|bing|bed)?|moves?|moving|tracks?|tracking)\s+(?:slowly\s+|gently\s+|sideways\s+)?(?:to\s+the\s+)?left\b/],
  ["Truck Right", /\b(?:truck(?:s|ing|ed)?|slides?|sliding|crab(?:s|bing|bed)?|moves?|moving|tracks?|tracking)\s+(?:slowly\s+|gently\s+|sideways\s+)?(?:to\s+the\s+)?right\b/],
  ["Tilt Up", /\btilt(?:s|ing|ed)?\s+(?:slowly\s+|gently\s+)?up(?:ward)?\b/],
  ["Tilt Down", /\btilt(?:s|ing|ed)?\s+(?:slowly\s+|gently\s+)?down(?:ward)?\b/],
  ["Pedestal Up", /\b(?:pedestal(?:s|ing|led)?|crane(?:s|ing|d)?|boom(?:s|ing|ed)?|rises?|rising|lifts?|lifting|ascends?|ascending)\s+(?:slowly\s+|gently\s+)?up(?:ward)?\b|\bcrane-?up\b|\b(?:rises|ascends)\b/],
  ["Pedestal Down", /\b(?:pedestal(?:s|ing|led)?|crane(?:s|ing|d)?|boom(?:s|ing|ed)?|lowers?|lowering|descends?|descending|sinks?|sinking)\s+(?:slowly\s+|gently\s+)?down(?:ward)?\b|\bcrane-?down\b|\b(?:descends|lowers)\b/],
  ["Arc Shot", /\barc(?:s|ing|ed)?\s+(?:slowly\s+|gently\s+)?(?:around|round)\b|\borbit(?:s|ing|ed)?\b|\bcircl(?:es|ing|ed)\s+(?:slowly\s+)?(?:around|round)\b|\barc shot\b/],
  ["Roll Counterclockwise", /\broll(?:s|ing|ed)?\s+(?:slowly\s+|gently\s+)?(?:counter-?clockwise|anti-?clockwise)\b/],
  ["Roll Clockwise", /\broll(?:s|ing|ed)?\s+(?:slowly\s+|gently\s+)?clockwise\b/],
  ["Shake Strongly", /\bshak(?:es|ing|e)\s+(?:strongly|violently|hard|wildly|heavily)\b|\b(?:violent|strong|heavy)\s+(?:camera\s+)?shak/],
  ["Shake Slightly", /\bshak(?:es|ing|e)\s+(?:slightly|gently|subtly|a little)\b|\b(?:slight|subtle|gentle)\s+(?:handheld\s+)?(?:camera\s+)?shak|\bhandheld\b/],
  ["POV", /\bpoint of view\b|\bpov\b/],
  ["Static Shot", /\bstatic\b|\bholds?\s+(?:still|steady|static|a\s+static|its\s+position)|\blocked[- ]off\b|\b(?:remains?|stays?|is)\s+(?:still|static|fixed|stationary|locked)\b|\bdoes(?:\s+not|n't)\s+move\b|\bstationary\b|\bmotionless\b|\bfixed\s+(?:camera|frame|shot)\b/],
  ["Tracking Shot", /\btrack(?:s|ing|ed)?\b|\bfollow(?:s|ing|ed)?\b|\btracking shot\b/],
];
const STILL = new Set(["Static Shot", "POV", "Shake Slightly", "Shake Strongly"]);
const AMP = [["small", /\bsmall(?:\s+amplitude)?\b|\bslight(?:ly)?\b|\bsubtl(?:e|y)\b|\bgentl(?:e|y)\b|\ba little\b|\bbarely\b/],
  ["large", /\blarge(?:\s+amplitude)?\b|\bdramatic(?:ally)?\b|\bsweeping\b|\bwide\s+arc\b|\bbig\b|\bdeep(?:ly)?\b/]];
const SPEED = [["slow", /\bslow(?:ly)?\b|\bgradual(?:ly)?\b|\bleisurely\b|\bunhurried\b|\bcreep(?:s|ing)?\b|\binch(?:es|ing)\b/],
  ["fast", /\bfast\b|\bquick(?:ly)?\b|\brapid(?:ly)?\b|\bswift(?:ly)?\b|\bsudden(?:ly)?\b|\bwhip\b|\bbrisk(?:ly)?\b/]];
// words of a camera sentence that only say the move ("The camera slowly pushes in with small amplitude at slow
// speed."): when nothing else is left (two words at most), the fields say it all and the sentence leaves the text
const MOVE_WORDS = /\b(?:the|a|an|camera|lens|shot|with|at|amplitude|speed|small|medium|large|slow|normal|fast|slowly|gently|steadily|quickly|smoothly|subtly|slightly|gradually|then|and|holds?|remains?|stays?|is|still|steady|static|locked|off|fixed|throughout|whole|entire|zooms?|zoom|in|out|push(?:es)?|pull(?:s)?|back|forward|closer|toward|towards|pans?|left|right|trucks?|tilts?|up|down|upward|downward|pedestals?|cranes?|rises|descends|arcs?|around|orbits?|tracks?|tracking|follows?|shakes?|handheld|point|of|view|pov|rolls?|clockwise|counterclockwise|counter-clockwise|dolly|dollies|push-in|pull-out|moves?|movement|motion)\b/gi;
// a framing written at the start of a shot ("A medium shot of", "A close-up:", "Low angle,")
const FRAME_LEAD = /^(?:an?\s+)?(extreme[\s-]wide|extreme[\s-]close-?up|medium[\s-]close-?up|medium[\s-]wide|wide|medium|close-?up|over[\s-]the[\s-]shoulder|two[\s-]shot|insert|low[\s-]angle|high[\s-]angle|overhead|dutch[\s-]angle)((?:\s+(?:shot|angle|view))?)(?=[\s:,.\u2014-]|$)\s*(?:(?::|,|\.|\u2014|\s-\s)\s*|of\s+|on\s+|showing\s+)?/i;
const NEEDS_NOUN = new Set(["extreme wide", "wide", "medium", "medium wide"]);

// "Close-up" -> "close-up", "low-angle" -> "low angle" (a FRAMINGS value), "" when it is not one
function framingOf(word) {
  const k = word.toLowerCase().replace(/closeup/g, "close-up").replace(/[\s-]+/g, " ")
    .replace("close up", "close-up").replace("two shot", "two-shot").replace("over the shoulder", "over-the-shoulder");
  return FRAMINGS.includes(k) ? k : "";
}

// {text, camera, camera_amp, camera_speed, framing} of a written shot's text: its framing (from its start) and the
// move of its first camera sentence, in the shot's fields; the text without them when nothing else is said there
export function cameraOf(p, text) {
  let body = String(text || "").trim();
  const out = { text: body, camera: "", camera_amp: "", camera_speed: "", framing: "" };
  const lead = FRAME_LEAD.exec(body);
  if (lead) {
    const f = framingOf(lead[1]);
    if (f && (!NEEDS_NOUN.has(f) || lead[2])) { out.framing = f; body = body.slice(lead[0].length); }
  }
  const parts = body.split(/(?<=[.!?…])\s+/);
  for (let i = 0; i < parts.length; i++) {
    const sen = parts[i];
    if (/<d>/i.test(sen)) continue;
    const low = sen.toLowerCase();
    const aboutCamera = /\bcamera\b|\blens\b/.test(low) || wordCount(sen) <= 5;
    if (!aboutCamera) continue;
    const hit = MOVES.find(([, re]) => re.test(low));
    if (!hit) continue;
    const [name] = hit;
    const still = STILL.has(name);
    const amp = still ? "" : (AMP.find(([, re]) => re.test(low))?.[0] || "");
    const speed = still ? "" : (SPEED.find(([, re]) => re.test(low))?.[0] || "");
    const rest = wordCount(sen.replace(MOVE_WORDS, " "));
    const preset = (p?.camera_presets || []).find(c => key(c.name) === key(name));
    out.camera = preset?.text || DEFAULT_CAMERA.find(([n]) => n === name)?.[1] || "";
    out.camera_amp = amp;
    out.camera_speed = speed;
    if (rest <= 2) parts.splice(i, 1);
    break;
  }
  out.text = sentence(parts.join(" "));
  return out;
}

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
    let lead = body.slice(start, at);
    const lc = LINE_CUE.exec(lead);
    const cueAt = lc ? Number(lc[1]) * 60 + Number(lc[2]) : null;
    const cueText = lc ? `At ${lc[1]}:${lc[2]}, ` : "";
    if (lc) lead = lead.slice(lc[0].length);
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
    if (words) lines.push({ speaker, sid: men?.sid || null, who: named, language: lang ? lang[1].trim() : "", delivery, text: words, at: cueAt });
    cuts.push([start, end, kept ? sentence(cueText ? cueText + cueLower(edges(kept)) : kept) : "", words ? lines.length - 1 : -1]);
    floor = end;
  }
  let out = "", pos = 0;
  const pieces = [], cutLines = [];
  for (const [a, z, kept, li] of cuts) {
    const piece = body.slice(pos, a) + (kept ? " " + kept + " " : " ");
    out += piece;
    pieces.push(squash(piece));
    cutLines.push(li);
    pos = z;
  }
  out += body.slice(pos);
  pieces.push(squash(body.slice(pos)));
  return { text: squash(out), lines, pieces, cutLines };
}

// "she pockets the key" after "At 00:04.600, " (a name keeps its capital)
function cueLower(s) {
  return CUE_LOWER.test(s) ? s[0].toLowerCase() + s.slice(1) : s;
}

// The "At MM:SS.mmm," cues of a text moved by `offset` seconds (pass time -> scene time)
function shiftCues(text, offset) {
  if (!text || Math.abs(offset) < 1e-9) return text;
  return text.replace(CUES, (m, pre, at, mm, ss) => pre + at + fmtTime(Math.max(0, snapFrame(Number(mm) * 60 + Number(ss) + offset))));
}

// A shot's text with each spoken line's place kept: an action written after a line (with no
// time of its own) opens with the time between that line and the next one, at the line's end when there is room
// ("At 00:04.600, she pockets the key."), so the prompt puts the line before it (prompt.py _place_lines). Its own
// "At MM:SS.mmm," cues move from pass time to scene time.
function placedText(got, times, end, offset, cut = false) {
  if (!got.pieces) return shiftCues(got.text, offset); // no spoken line
  const parts = [];
  if (cut && !got.pieces[0] && got.cutLines[0] >= 0 && got.lines[got.cutLines[0]]?.who && got.pieces.slice(1).some(Boolean)) parts.push(sentence(got.lines[got.cutLines[0]].who));
  got.pieces.forEach((piece, k) => {
    let s = shiftCues(piece, offset);
    const li = k > 0 ? got.cutLines[k - 1] : -1;
    if (s && li >= 0 && !LINE_CUE.test(s)) {
      const t0 = times[li];
      const next = li + 1 < times.length ? times[li + 1] : end;
      const tc = snapFrame(Math.min(Math.max(t0 + dialogueSeconds({ text: got.lines[li].text }), t0 + 1 / FPS), next - 1 / FPS));
      if (tc > t0 + 1e-6) s = `At ${fmtTime(tc)}, ${cueLower(s)}`;
    }
    if (s) parts.push(s);
  });
  return squash(parts.join(" "));
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

// The times of a shot's spoken lines in scene time: the time written before a line
// ("At MM:SS.mmm," in pass time, + offset), or the time the scene's own line has (known, takePassShots), when it lies
// inside the shot and after the line before it (an earlier one put the lines out of order); a line without one
// follows the line before it; with no time at all, they are spread over the shot as before
function lineTimes(lines, start, end, offset, duration, known = []) {
  const lengths = lines.map(d => dialogueSeconds({ text: d.text }));
  const given = lines.map((d, k) => (known[k] !== null && known[k] !== undefined ? known[k]
    : d.at === null || d.at === undefined ? null : d.at + offset));
  let at;
  if (given.every(g => g === null)) at = spread(lines.length, start, end, lengths);
  else {
    at = [];
    let cur = start + Math.min(0.5, Math.max(0, end - start) * 0.1), prev = -Infinity;
    given.forEach((g, k) => {
      let v = g !== null && g >= start - 1e-6 && g < end - 1e-6 && g > prev + 1e-6 ? g : Math.max(cur, prev + 1 / FPS);
      if (v > end - 1 / FPS) v = Math.max(start, prev) + (end - Math.max(start, prev)) / 2;
      at.push(v);
      prev = v;
      cur = v + (lengths[k] || 1) + 0.3;
    });
  }
  return at.map(v => Math.max(0, Math.min(snapFrame(v), duration - 1 / FPS)));
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
  const offset = x ? Number(x.start) || 0 : 0;
  const cf = castFinder(p);
  const sMap = new Map();
  const shots = chunks.map((c, i) => {
    let body = c.trim();
    let t = i === 0 ? 0 : null;
    const cut = CUT.exec(body);
    if (cut) {
      const kind = leadKind(body);
      if (i > 0) t = Number(cut[1]) * 60 + Number(cut[2]) + offset;
      if (kind === "cut" || (kind === "time" && i > 0)) body = body.slice((CUT_STRICT.exec(body) || cut)[0].length);
    }
    const got = takeLines(body, cf, sMap);
    return { t, got, lines: got.lines };
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
    const times = lineTimes(sh.lines, sh.t, end, offset, duration);
    sh.lines.forEach((d, k) => { const { at: _at, ...line } = d; lines.push({ ...line, t: times[k] }); });
    // a shot that was only its speaker's line ("the shot cuts to @Bob (S2), who replies, <d>…</d>") shows the speaker
    const text = placedText(sh.got, times, end, offset, i > 0) || (sh.got.lines[0]?.who || "");
    Object.assign(sh, cameraOf(p, sentence(text)));
  });
  return { pre, shots: shots.map(sh => ({ t: sh.t, text: sh.text, camera: sh.camera, camera_amp: sh.camera_amp, camera_speed: sh.camera_speed, framing: sh.framing })), lines };
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
  sc.shots = got.shots.map(s => ({ id: newId("h"), t: s.t, camera: s.camera, camera_amp: s.camera_amp, camera_speed: s.camera_speed, framing: s.framing, text: s.text }));
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

// The written shots replace the scene's shots after Write prompts on a scene made in one pass. No shots
// yet: fillScene. Shots on the timeline: the written [Shot N] lines replace them in order, whatever their count:
// each shot takes its written text, framing and camera move (a shot whose line names none keeps its own) and keeps
// its time; written shots past the scene's last one join the timeline at their written start (or spread over the
// time left); shots the answer did not write keep their text. The description keeps the text before [Shot 1];
// spoken lines the scene does not have yet are added. Only with automatic shots + dialogue on (else the written lines
// are what H3 gets). Returns {shots, lines, updated, added, kept} or null.
function takeShot(sh, w) {
  if (w.text) sh.text = w.text;
  if (w.framing) sh.framing = w.framing;
  if (w.camera) Object.assign(sh, { camera: w.camera, camera_amp: w.camera_amp, camera_speed: w.camera_speed });
}

export function writeShots(p, sc) {
  if (!sc || sc.prompt?.mode === "raw") return null;
  if (!(sc.shots || []).length) return fillScene(p, sc);
  if (!sc.prompt.auto?.shots) return null;
  const i = sceneIndex(p, sc.id);
  const plan = planScene(p, sc, i < 0 ? undefined : i);
  if (plan.passes.length !== 1) return null;
  const got = readWritten(p, sc, sc.prompt.sections.detailed_description, plan.passes[0]);
  if (!got || !got.shots.length) return null;
  const order = [...sc.shots].sort((a, b) => a.t - b.t);
  const n = Math.min(order.length, got.shots.length);
  for (let k = 0; k < n; k++) takeShot(order[k], got.shots[k]);
  const duration = Number(sc.duration) || 0;
  const extra = got.shots.slice(n);
  let last = order[order.length - 1].t;
  extra.forEach((w, j) => {
    const left = extra.length - j;
    const gap = Math.min(0.5, (duration - last) / (left + 1));
    let t = w.t;
    if (!(t >= last + gap && t < duration - gap / 2)) t = last + (duration - last) / (left + 1);
    t = Math.max(0, Math.min(snapFrame(t), duration - 1 / FPS));
    sc.shots.push({ id: newId("h"), t, camera: w.camera, camera_amp: w.camera_amp, camera_speed: w.camera_speed, framing: w.framing, text: w.text });
    last = t;
  });
  sc.shots.sort((a, b) => a.t - b.t);
  let lines = 0;
  if (!(sc.dialogue || []).length && got.lines.length) {
    const lang = id => (p.cast || []).find(c => c.id === id)?.language || p.global?.defaults?.language || "English";
    sc.dialogue = got.lines.map(d => ({ id: newId("d"), speaker: d.speaker, t: d.t, language: d.language || lang(d.speaker), delivery: d.delivery || "says", text: d.text }));
    lines = sc.dialogue.length;
    sc.cast = Array.isArray(sc.cast) ? sc.cast : [];
    for (const d of sc.dialogue) if (d.speaker && !sc.cast.some(c => c.id === d.speaker)) sc.cast.push({ id: d.speaker, outfit: "" });
  }
  sc.prompt.sections.detailed_description = got.pre;
  return { shots: n + extra.length, lines, updated: true, added: extra.length, kept: order.length - n };
}

// Write prompts on a scene made in several passes. items: the written passes of the current
// layout [{index (1-based), sections}], changed in place before they are stored. In each pass whose [Shot N] lines
// match its shots one to one, a shot that starts in that pass takes its written text, framing and camera move, and
// its line leaves the pass's description; a shot that continues from the pass before keeps its written line there
// (the pass's own part of that shot, which replaces the automatic one). Returns {shots, lines, updated} or null.
export function takePassShots(p, sc, plan, items) {
  if (!sc || sc.prompt?.mode === "raw" || !sc.prompt.auto?.shots) return null;
  const byId = new Map((sc.shots || []).map(x => [x.id, x]));
  const cf = castFinder(p);
  let n = 0;
  for (const it of items || []) {
    const x = plan.passes[it.index - 1];
    if (!x || !x.shots.length || !it.sections) continue;
    const text = String(it.sections.detailed_description || "").replace(/\r\n?/g, "\n");
    const spans = [...text.matchAll(SPAN)].map(m => [m.index, m.index + m[0].length]);
    const labels = [...text.matchAll(LABEL)].filter(m => !spans.some(([a, b]) => m.index > a && m.index < b));
    if (labels.length !== x.shots.length) continue;
    const pre = squash(text.slice(0, labels[0].index));
    const keep = [];
    labels.forEach((m, j) => {
      const whole = text.slice(m.index, j + 1 < labels.length ? labels[j + 1].index : text.length).trim();
      const ps = x.shots[j];
      const sh = byId.get(ps.id);
      if (ps.continuing || !sh) { keep.push(whole); return; }
      let body = whole.slice(m[0].length).trim();
      const cut = CUT.exec(body);
      if (cut && leadKind(body) !== "line") body = body.slice((CUT_STRICT.exec(body) || cut)[0].length);
      const got = takeLines(body, cf, new Map());
      const offset = Number(x.start) || 0;
      const next = (sc.shots || []).filter(o => o.t > sh.t + 1e-6).reduce((m, o) => Math.min(m, o.t), Infinity);
      const end = Math.min(Number.isFinite(next) ? next : Infinity, Number(sc.duration) || Infinity);
      const known = got.lines.map(d => (sc.dialogue || []).find(q => key(q.text) === key(d.text) && q.t >= sh.t - 1e-6 && q.t < end)?.t ?? null);
      const times = lineTimes(got.lines, sh.t, Number.isFinite(end) ? end : sh.t + 15, offset, Number(sc.duration) || sh.t + 15, known);
      takeShot(sh, cameraOf(p, sentence(placedText(got, times, Number.isFinite(end) ? end : sh.t + 15, offset, sh.t > 1e-6) || got.lines[0]?.who || "")));
      n++;
    });
    it.sections.detailed_description = [pre, ...keep].filter(Boolean).join("\n");
  }
  return n ? { shots: n, lines: 0, updated: true, added: 0, kept: 0 } : null;
}

// "1 shot and 2 spoken lines"
export function fillWords(n) {
  if (!n) return "";
  const s = `${n.shots} shot${n.shots === 1 ? "" : "s"}`;
  return n.lines ? `${s} and ${n.lines} spoken line${n.lines === 1 ? "" : "s"}` : s;
}
