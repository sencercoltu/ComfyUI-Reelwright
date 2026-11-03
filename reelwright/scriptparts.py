"""Split a long script into parts for the LLM import (added 2026-11-03 v0.4.2).

A whole script in one request makes one very long answer: a 46-row shot table came back as roughly 15,000 tokens
of JSON, which ran past the token budget or the timeout most of the time. The script is cut into blocks (scene
headings, table rows, Markdown headings, "Scene N" lines; paragraphs when there are none) and the blocks are
grouped into parts of about `part_chars` characters. Text before the first block (a premise, a style note) and the
heading of a table are sent with every part as notes, so each part knows what the story is.

Pure Python, no ComfyUI imports.
"""

import re

SCENE_START = re.compile(
    r"^\s*(?:"
    r"(?:INT|EXT|EST|INT\.?\s*/\s*EXT|I\s*/\s*E)[.\s]"  # Fountain / screenplay scene headings
    r"|\.(?!\.)\w"                                      # Fountain forced heading ".OSSUARY"
    r"|#{1,6}\s"                                        # Markdown heading
    r"|(?:SCENE|Scene|scene)\s+[\w-]+"                  # "Scene 12", "SCENE TWO"
    r")")
TABLE_ROW = re.compile(r"^\s*\|.*\S")
TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
NOTES_MAX = 2000  # a longer text before the first block is treated as script, not as notes


def _rule(line):
    return "|" in line and bool(TABLE_RULE.match(line))


def _paragraphs(text):
    return [p.strip("\n") for p in re.split(r"\n\s*\n", text) if p.strip()]


def _fit(block, limit):
    """A block longer than twice the part size is cut at blank lines, then at line ends."""
    if len(block) <= 2 * limit:
        return [block]
    out = []
    for para in _paragraphs(block):
        if len(para) <= 2 * limit:
            out.append(para)
            continue
        cur = []
        for line in para.split("\n"):
            if cur and sum(len(x) + 1 for x in cur) + len(line) > limit:
                out.append("\n".join(cur))
                cur = []
            cur.append(line)
        if cur:
            out.append("\n".join(cur))
    return out


def split_script(text, part_chars=3000):
    """{"notes": str, "parts": [[block, ...], ...], "chars": int, "blocks": int}. A part's text is its blocks joined
    by newlines. part_chars <= 0, or a script no longer than part_chars, gives one part with the script as written."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    whole = {"notes": "", "parts": [[text]] if text.strip() else [], "chars": len(text), "blocks": 1 if text.strip() else 0}
    if part_chars <= 0 or len(text) <= part_chars:
        return whole
    lines = text.split("\n")
    heads, skip = [], set()
    for i in range(len(lines) - 1):
        if TABLE_ROW.match(lines[i]) and not _rule(lines[i]) and _rule(lines[i + 1]):
            heads.append(lines[i].strip() + "\n" + lines[i + 1].strip())
            skip.update((i, i + 1))
    pre, blocks, cur = [], [], None
    for i, line in enumerate(lines):
        if i in skip or _rule(line):
            continue
        if SCENE_START.match(line) or TABLE_ROW.match(line):
            if cur is not None:
                blocks.append("\n".join(cur).strip("\n"))
            cur = [line]
        elif cur is None:
            pre.append(line)
        else:
            cur.append(line)
    if cur is not None:
        blocks.append("\n".join(cur).strip("\n"))
    preamble = "\n".join(pre).strip("\n")
    if not blocks:  # no headings or table rows: paragraphs are the blocks
        blocks, preamble = _paragraphs(text), ""
    notes = []
    if preamble and len(preamble) <= NOTES_MAX:
        notes.append(preamble)
    elif preamble:
        blocks = _paragraphs(preamble) + blocks
    notes += ["Table columns:\n" + h for h in heads]
    sized = [b for block in blocks if block.strip() for b in _fit(block, part_chars)]
    parts, cur, size = [], [], 0
    for b in sized:
        if cur and size + len(b) + 1 > part_chars:
            parts.append(cur)
            cur, size = [], 0
        cur.append(b)
        size += len(b) + 1
    if cur:
        parts.append(cur)
    return {"notes": "\n\n".join(notes), "parts": parts, "chars": len(text), "blocks": len(sized)}


# ---- scene length vs shots (added 2026-11-03 v0.4.3) -------------------------------------------------------------
# An imported scene could list shots that start after its end: the LLM grouped several table rows into one scene,
# wrote their start times, and gave the scene a shorter length (a 68 s chorus came back as 30 s with shots up to
# 61.8 s). Shot durations are easier for a model to copy from a script than running start times, so the import asks
# for both and the durations win.

FPS = 24


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def _frames_up(t):
    return -(-round(t * FPS * 1000) // 1000) / FPS  # round up to a whole frame


def typical_shot(starts):
    """Median gap between consecutive shot starts, 1-15 s; 4 s with fewer than two shots."""
    gaps = sorted(b - a for a, b in zip(starts, starts[1:]) if b - a > 0)
    if not gaps:
        return 4.0
    return max(1.0, min(15.0, gaps[len(gaps) // 2]))


def fit_scene(scene):
    """Make an imported scene's timing consistent, in place; returns a note ("" when nothing changed).
    - every shot has a duration: shots start one after another and the scene lasts their sum;
    - otherwise shots are sorted by start and the scene is lengthened so no shot starts in its last half second
      (the last shot gets the scene's typical shot length);
    - a dialogue line after the end lengthens the scene to the line plus 2 s."""
    given = _num(scene.get("duration"))
    shots = [s for s in (scene.get("shots") or []) if isinstance(s, dict)]
    lengths = [_num(s.get("duration")) for s in shots]
    length = given if given and given > 0 else None
    how = ""
    if shots and all(x and x > 0 for x in lengths):
        t = 0.0
        for s, d in zip(shots, lengths):
            s["t"] = round(t, 3)
            t += d
        total = round(t, 3)
        if length is None or abs(total - length) > 0.5:
            how = "length set from its shots"
        length = total
    elif shots:
        for s in shots:
            s["t"] = max(0.0, _num(s.get("t")) or 0.0)
        shots.sort(key=lambda s: s["t"])
        starts = [s["t"] for s in shots]
        need = starts[-1] + typical_shot(starts)
        if length is None or starts[-1] > length - 0.5:
            how = "lengthened to fit its shots" if length is not None else "length taken from its shots"
            length = max(length or 0.0, need)
    lines = [t for t in (_num(d.get("t")) for d in (scene.get("dialogue") or []) if isinstance(d, dict)) if t is not None]
    last_line = max(lines) if lines else None
    if last_line is not None and (length is None or last_line > length - 0.5):
        length = max(length or 0.0, last_line + 2.0)
        how = how or "lengthened to fit its dialogue"
    if length is None:
        return ""
    length = round(_frames_up(length), 4)
    scene["shots"] = shots
    scene["duration"] = length
    if how and given is not None and abs(length - given) > 0.01:
        return "{} ({:.2f} s; the LLM gave {:.2f} s)".format(how, length, given)
    return how if given is None and how else ""
