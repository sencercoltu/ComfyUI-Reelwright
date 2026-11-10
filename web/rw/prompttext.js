// Syntax highlighting for prompt text: H3 tags, editor @tags, shots, timestamps
// and dialogue. Returns HTML-safe markup for the editor overlay and previews.

// A tag is @Name or @{Two Words}; see tagMatches() below
const NAME = "[\\p{L}\\p{N}\\p{M}_]+(?:['’.\\-][\\p{L}\\p{N}\\p{M}_]+)*";
export const TAG_SOURCE = `(?<![\\p{L}\\p{N}\\p{M}_@])@(?!@)(?:\\{([^}\\n]+)\\}|(${NAME}))`;

const RULES = [
  [/^(?:subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music):$/gm, "hl-sec"],
  [/&lt;d&gt;[\s\S]*?&lt;\/d&gt;/g, "hl-dlg"],
  [/&lt;(?:Picture|Subject) \d+&gt;/g, "hl-pic"],
  [/&lt;Video \d+&gt;/g, "hl-vid"],
  [/&lt;Audio \d+&gt;/g, "hl-aud"],
  [/@@/g, "hl-esc"],
  [new RegExp(TAG_SOURCE, "gu"), "hl-at"],
  [/\[Shot ?\d+\]/g, "hl-shot"],
  [/\bAt \d{2}:\d{2}(?:\.\d{1,3})?/g, "hl-time"],
  [/\[(?:reference generation|keyframe completion|video continuation|audio reference|audio reuse|video editing)(?: \+ [a-z ]+)*\]/g, "hl-task"],
  [/\((?:S\d+)\)/g, "hl-spk"],
  [/\b(?:fully_preserved|partially_preserved|attribute_transfer|weak_reference|fully_copy|partially_copy)\b/g, "hl-ret"],
];

function escape(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// NUL characters in the text are shown as ␀ (one character, so the overlay stays aligned
// with the textarea) and can never be read as a placeholder; resolving stops after a few rounds and drops unknown ids
export function highlightHTML(text) {
  let html = escape(String(text ?? "").replace(/\u0000/g, "\u2400"));
  const marks = [];
  for (const [re, cls] of RULES) {
    html = html.replace(re, m => {
      marks.push(`<span class="${cls}">${m}</span>`);
      return `\u0000${marks.length - 1}\u0000`;
    });
  }
  // Placeholders can nest (a tag inside dialogue); resolve until none are left.
  for (let round = 0; round < 8 && html.includes("\u0000"); round++) {
    html = html.replace(/\u0000(\d+)\u0000/g, (_, i) => marks[Number(i)] ?? "");
  }
  return html.replace(/\u0000/g, "") + "\n";
}

// Every tag in `text`: [{tag: "@Anna" | "@{Old Keeper}", name: "Anna" | "Old Keeper", index}]
// ("@Anna." -> "Anna"; "mail@host.com" and "@@x" are not tags)
export function tagMatches(text) {
  const out = [];
  for (const m of String(text ?? "").matchAll(new RegExp(TAG_SOURCE, "gu"))) out.push({ tag: m[0], name: m[1] ?? m[2], index: m.index });
  return out;
}

// An unknown name that looks like an asset code (P3, V1, A2) is an error, any other unknown
// name (an @handle) a warning: it is written as plain text
export const looksLikeAssetCode = tag => /^@[PVA]\d+$/i.test(String(tag || ""));

export function unknownTags(text, candidates) {
  const known = new Set(candidates.map(c => c.tag.toLowerCase()));
  return [...new Set(tagMatches(text).map(m => m.tag).filter(t => !known.has(t.toLowerCase())))];
}

// Line-level diff (LCS) used by the rewrite preview.
export function diffLines(a, b) {
  const x = a ? a.split("\n") : [], y = b ? b.split("\n") : [];
  const n = x.length, m = y.length;
  const dp = Array.from({ length: n + 1 }, () => new Int32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) {
    dp[i][j] = x[i] === y[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  }
  const out = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) { out.push(["=", x[i]]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) out.push(["-", x[i++]]);
    else out.push(["+", y[j++]]);
  }
  while (i < n) out.push(["-", x[i++]]);
  while (j < m) out.push(["+", y[j++]]);
  return out;
}
