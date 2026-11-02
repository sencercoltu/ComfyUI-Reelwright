// Syntax highlighting for prompt text: H3 tags, editor @tags, shots, timestamps
// and dialogue. Returns HTML-safe markup for the editor overlay and previews.

const RULES = [
  // added 2026-11-02 v0.2.0: the six Ref2VA section labels, each on its own line
  [/^(?:subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music):$/gm, "hl-sec"],
  [/&lt;d&gt;[\s\S]*?&lt;\/d&gt;/g, "hl-dlg"],
  [/&lt;(?:Picture|Subject) \d+&gt;/g, "hl-pic"],
  [/&lt;Video \d+&gt;/g, "hl-vid"],
  [/&lt;Audio \d+&gt;/g, "hl-aud"],
  [/@\{[^}\n]+\}|@[A-Za-z][\w-]*/g, "hl-at"],
  [/\[Shot ?\d+\]/g, "hl-shot"],
  [/\bAt \d{2}:\d{2}(?:\.\d{1,3})?/g, "hl-time"],
  [/\[(?:reference generation|keyframe completion|video continuation|audio reference|audio reuse|video editing)(?: \+ [a-z ]+)*\]/g, "hl-task"],
  [/\((?:S\d+)\)/g, "hl-spk"],
  [/\b(?:fully_preserved|partially_preserved|attribute_transfer|weak_reference|fully_copy|partially_copy)\b/g, "hl-ret"],
];

function escape(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function highlightHTML(text) {
  let html = escape(text || "");
  const marks = [];
  for (const [re, cls] of RULES) {
    html = html.replace(re, m => {
      marks.push(`<span class="${cls}">${m}</span>`);
      return `\u0000${marks.length - 1}\u0000`;
    });
  }
  // Placeholders can nest (a tag inside dialogue); resolve until none are left.
  let prev;
  do {
    prev = html;
    html = html.replace(/\u0000(\d+)\u0000/g, (_, i) => marks[Number(i)]);
  } while (html !== prev);
  return html + "\n";
}

export function unknownTags(text, candidates) {
  const known = new Set(candidates.map(c => c.tag.toLowerCase()));
  const found = (text || "").match(/@\{[^}\n]+\}|@[A-Za-z][\w-]*/g) || [];
  return [...new Set(found.filter(t => !known.has(t.toLowerCase())))];
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
