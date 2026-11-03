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
