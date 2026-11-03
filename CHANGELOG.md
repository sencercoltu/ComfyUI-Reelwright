# Changelog

## v0.4.3 — 2026-11-03

- **Imported scenes no longer have shots after their end.** A scene made from several timed rows of a script could come back with the wrong length: for example a 68 s chorus came back as 30 s, with shots starting up to 61.8 s. Those shots were never rendered.
  - Import now asks for each shot's duration, and the scene lasts the sum of its shots. Each shot starts where the one before it ends. Durations are easier for a model to copy from a table than running start times, so they win over the given starts and the given scene length.
  - Without durations, the shots are sorted and a scene that is too short is lengthened; its last shot gets the scene's typical shot length (the median gap between shots). A dialogue line after the end lengthens the scene to the line plus 2 s.
  - The review list notes each scene whose length was changed ("length set from its shots (68.04 s; the LLM gave 30.00 s)").
- **Fixing existing scenes:**
  - the Shots card says how many shots or lines start after the end and offers **Lengthen to …** (make the scene long enough) or **Fit into …** (keep the length and move every shot and line closer together in proportion);
  - the Issues list has **Lengthen them to fit** for every such scene at once.

  All three can be undone with Ctrl+Z, and focus stays in the editor so Ctrl+Z works right away.
- **Shot length beside each shot's start** ("for 8.42 s"). A shot lasts until the next one starts; the last one runs to the end of the scene ("· end"). A shot after the end says so.

## v0.4.2 — 2026-11-03

- **Script import works for long scripts: it sends them in parts.** The whole script used to go out as one request with a 6,000-token budget and a fixed 180 s timeout. A 46-shot table answers with roughly 15,000 tokens of JSON, so the answer was cut off (unreadable JSON) or timed out. A timeout showed no message at all, because the error had no text.
  - The script is cut at its own structure: screenplay scene headings (INT. / EXT., Fountain `.HEADING`), table rows, Markdown headings, "Scene N" lines, or paragraphs when there are none. Parts are about **Part size** characters (default 3,000); a scene is cut only if it is more than twice that.
  - Text before the first scene (a premise or style note) and a table's column headings go with every part. Each part also gets the cast found so far, so names stay the same. Cast is merged by name across parts.
  - The Import card lists the parts with live progress ("writing · ≈3,120 tokens of 16,384 · 48 s"). **Stop** keeps the finished parts and **Continue** picks up the rest. A failed part can be retried on its own, and the other parts' scenes are kept.
  - A part whose answer is cut off at the token budget is split in two and sent again automatically.
- **New LLM limits** (Global → Prompt rewriter → Limits; saved with the project and in profiles):
  - *Stall timeout* (120 s): no data for this long ends a request.
  - *Give up after* (900 s): the longest a request may take, even while text keeps arriving.
  - *Retries* (2): after a timeout, a dropped connection, a server error or unreadable JSON. A wrong model name or a prompt too big for the context window is not retried.
  - *Context window* (0 = ask the server): vLLM and SGLang report it on `/models`, and Test connection shows it. When it is known, the answer budget is lowered so prompt + answer fit, and a request that can't fit is refused before it is sent, with the numbers.
  - Script import: *Part size*, *Max tokens* per part (16,384), *Thinking* (same as above, or off for Import only), and *H3 guides* (off by default: Import writes scenes, not H3 prompts, so this saves about 10,000 prompt tokens per part).
- **Every LLM request streams its answer.** A slow model that is still writing is no longer mistaken for a dead server. Servers that ignore streaming and answer with one JSON body still work.
  - Rewrite and Split show the same progress line and have a Stop button.
  - Stopping a request closes the connection, so SGLang and vLLM stop generating too.
- **Errors say what happened**, for example "No answer from … for 120 s; raise Stall timeout", "Gave up after 900 s with about 9,800 tokens received", or "cut off at 16,384 tokens before its JSON was complete". Any route error without a message now reports the error type.
- New routes: `POST /reelwright/llm/script/parts`, `POST /reelwright/llm/cancel`; `/reelwright/llm/script` takes one part (`part`, `parts`, `notes`, `known_cast`, `job`, `can_split`); `reelwright.llm` progress events.

## v0.4.1 — 2026-11-03

- **"What H3 receives" no longer repeats sections after a rewrite.** With subject definitions, retention or shot lines set to automatic, a rewritten section used to be added after the automatic lines instead of replacing them, so the same subject or shot appeared twice. Now:
  - a written `<Subject N>` line or `[Shot N]` replaces the automatic line with the same label; lines with new labels follow;
  - the rewriter's reply is tidied before it is shown: a whole prompt returned in one field is split back into its sections, `summary:`-style labels are removed, `<Picture N>`-style names are turned back into the `@` tags they stand for, and sections the editor writes automatically keep their previous text;
  - leading task tags in a written summary are not doubled.
- **A subject keeps its picture reference.** A written `<Subject N>` line that names none of the subject's pictures or videos gets ", shown in `<Picture k>`" added, so H3 still knows which reference it is. A rewritten `[Shot N]` that drops a spoken `<d>` line gets it back word for word.
- **Anchor sheets: Auto, One sheet or Separate.** Each character with several anchors has a three-way choice (new characters default to Auto):
  - *Auto* packs the anchors into one sheet only when the pass would not fit H3's 9 pictures otherwise; when they fit, each anchor is sent on its own at full size;
  - *One sheet* always packs (existing characters keep this, as before); *Separate* never packs.

  The Cast tab shows the actual sheet the render sends and how many pixels each anchor gets in it, and the Scene tab's cast avatar shows the sheet when it is packed (it used to show the first anchor, which looked as if only that one was sent). Sheets have no 3×3 limit: the grid is ceil(√n) columns, as many rows as needed, and cells take the median shape of the pictures, so portrait anchors are no longer letterboxed into square cells. Each anchor gets less of the picture as the grid grows; the size note says how much.
- **Files tab: preview.** Click a file's name, or the eye on any row, to see it next to the tree: pictures, videos (a take or cut shows its video), audio, and text files (`.srt`, `.json`, `.otio`, `.fcpxml`, logs; the first 200 KB). The preview stays put while the tree refreshes and has open-in-tab, delete and close buttons.
- **Typing in a text field during a render no longer scrambles letters.** Progress events re-render the editor many times a second. A field without its own key was rebuilt, focus moved to the new copy, and the caret ended up in the wrong place, so "Sencer" became "Seernc". The focused field is now found again by its help id and position, and keeps what you typed and the caret.
- **A failed face check no longer fails the render.** insightface 0.7.x imports `albumentations` on load, and a mismatched `albumentations`/`albucore` pair raised `ImportError: cannot import name 'median_blur' from 'albucore'` after the take was saved. Reelwright now:
  - retries loading insightface without that part (face analysis does not use it);
  - if the check still can't run, keeps the take, logs a warning and shows "face check skipped" in the render progress;
  - shows the load error in Global → About instead of just "face checks off".
- New route `GET /reelwright/sheet?files=[...]&cell=` returns a sheet as JPEG; `/reelwright/info` adds `insightface_error`.

## v0.4.0 — 2026-11-03

- **New Files tab: disk use, and deleting.** Everything Reelwright wrote to disk, for every project on the server (the open one first), as a tree:
  - each project, then its scenes and takes (starred take marked; pass videos as their own folder);
  - merged cuts grouped by version (video plus side files), autosaved versions, cast training sets;
  - the project's asset folder, each file marked used, unused or not in the project.

  Every row shows its size, its share of the folder above, the number of files and the date. Rows can be sorted in timeline order or largest first. Files can be opened in a new tab.
- **Deleting:** tick rows (a folder or a take takes everything in it) and press Delete, or use a row's bin. Quick selections add common clean-ups: unstarred takes, pass videos, older cuts, autosaves, and things the project no longer lists. The confirmation shows the total and what it means for the open project.
  - A deleted take is also removed from its scene's take list; if it was starred, the newest remaining take becomes starred.
  - Asset files the open project uses are also removed from the project (Ctrl+Z restores the project entries, not the files).
  - Whole projects other than the open one can be deleted (output and input folders).
- **Safety:**
  - only `output/reelwright/<slug>` and `input/reelwright/<slug>` can be named, and the server checks every id again;
  - the open project can't be deleted as a whole, and every `project.json` is kept;
  - a symlink is removed, never its target, and hard links are counted as freeing nothing;
  - the open project's rows are locked while it renders.
- New routes `GET /reelwright/storage` and `POST /reelwright/storage/delete` (`reelwright/files.py`).
- Confirmation dialogs keep line breaks in their message.

## v0.3.9 — 2026-11-02

- **Render-tab preview works with VideoHelperSuite's animated previews turned on.** VHS's "Display animated previews when sampling" setting replaces ComfyUI's `latent_preview.get_previewer`. Its previewer sends its own animated frames to the frontend for whichever node is running, and returns no image. For Reelwright this meant:
  - a preview reappeared under the node after v0.3.5;
  - from v0.3.7 the Render tab caught those frames, which start with 24 bytes of VHS's own data before the JPEG, so they showed as "preview could not be decoded";
  - Reelwright's own preview got nothing (ComfyUI log: "no latent preview … cannot unpack non-iterable NoneType").

  Reelwright now asks ComfyUI's own previewer underneath any wrapper (`render.stock_previewer`, following `__wrapped__`), so VHS is not involved in its preview at all. VHS's animated previews for other nodes are unchanged.
- The preview window drops any header in front of a JPEG, PNG or WebP picture it receives, and its console warning now shows the first bytes of anything it can't decode.
- A previewer that returns no image is reported by name in the ComfyUI log instead of as an unpacking error.

## v0.3.8 — 2026-11-02

- **The Render tab's preview no longer shows a broken image.** The window used to be rebuilt on every re-render straight from the event's URL, and a picture that failed to load stayed on screen as a broken-image icon. It is now one element that lives as long as the editor:
  - each new preview is decoded off-screen and swapped in only once it has loaded;
  - if one can't be decoded, the last good picture stays (or an empty frame says so) and the browser console gets one warning;
  - every preview is shown through a `blob:` URL, the same kind ComfyUI uses for its own node previews; the backend's base64 JPEG is converted in the browser, so nothing depends on `data:` images being allowed;
  - an object URL is released only after its replacement is on screen.
- **Previews follow every sampler step.** The backend's gap between previews went from one second to 0.25 s, and a new preview updates the window in place without re-rendering the tab.
- A preview that can't be made (for example a missing TAESD file) is now a warning in the ComfyUI console, once per pass, instead of a hidden debug line.

## v0.3.7 — 2026-11-02

- **No latent preview under the node, whatever sends it.** v0.3.5 stopped Reelwright's backend from handing previews to ComfyUI, but a backend that hadn't been restarted (or anything else reporting previews for the node) still made ComfyUI paint them under the node. The extension now intercepts ComfyUI's preview stream (`b_preview_with_metadata`, and `b_preview` while a Reelwright node is executing) for Reelwright nodes only and shows those images in the Render tab's preview window. Other nodes keep their previews.

## v0.3.6 — 2026-11-02

- **Autosaved versions can be deleted** (Render tab): a delete button on each row, and **Delete all** in the card header (with confirmation). Only the version snapshots are removed; the project and its latest autosave stay.
- Each version is one line: date and time (from the file name), size, Restore and Delete; the file name is in the tooltip.
- README: why ComfyUI Manager's list doesn't show Reelwright and how to update it.

## v0.3.5 — 2026-11-02

- **Latent preview moves to the Render tab.** ComfyUI painted each sampling step's preview over the whole node. Reelwright now sends the preview to its own Render tab instead: a 200 px window next to the progress bars, about once a second, with the scene, pass and step. ComfyUI's progress bar still updates, and its preview setting (Latent2RGB, TAESD or none) still decides the image. The preview disappears when the run ends.

## v0.3.4 — 2026-11-02

- **Asset descriptions reach characters too.** Scenes already read an asset's description live when it is a scene reference, but a character's subject line only used the Cast tab description, so describing an anchor picture changed nothing. A cast member with no description of its own now uses the description of its first anchor picture that has one, in every scene it appears in, in the LLM's scene context and in the training-set caption. A character's own description still wins.
- The asset inspector shows **where the description is used**: scene prompts (with links), the characters it describes, and why it isn't used where it isn't (the character has its own description, an earlier anchor is used, guide frames only send it when @mentioned, outfit pictures use the outfit's name).
- Scene tab: each reference shows its asset's description (click to edit it in the Assets tab; empty ones are flagged), and each cast member shows the description its subject line uses.
- Cast tab: an empty description shows which anchor's description is used instead.
- Rewrite and Split now give the LLM each reference's description, not only its name.
- New lint: a character with no description and no described anchor.

## v0.3.3 — 2026-11-02

- **Mouse wheel scrolls the timeline sideways** when the scenes don't fit. Shift + wheel scrolls up and down; Alt + wheel still zooms.
- **The playhead only moves where you click** (the ruler or an empty part of a lane). It no longer follows the mouse: the ruler's drag tracking used window listeners that could miss the button release inside ComfyUI and keep running. Drags now track the button state and always end.
- **Dragging the timeline pans it**, from the ruler, an empty lane or a scene block; the playhead stays put and the press doesn't select a scene or drag the node. To scrub, drag the playhead's time label.
- Timeline mouse maths (click, pan, scrub, shot ticks, scene resize, dropping an asset) now account for ComfyUI's canvas zoom; at zoom levels other than 100 % they were off.

## v0.3.2 — 2026-11-02

- **Describe with thinking models** (Qwen3 and similar on SGLang or vLLM): Describe gave the model only 400 tokens. A model that reasons first often used them all on reasoning, so the reply had no answer and Describe said "The model returned no text. Is it a vision model?". How long the reasoning runs varies per picture and per try, which is why it worked sometimes.
  - Describe now allows max(Max tokens, 6000) tokens. If the model still runs out while thinking, it asks once more with thinking off and says so under the answer.
  - New **Thinking** setting (Global → Prompt rewriter): *Model default* or *Off*. Off sends `chat_template_kwargs: {"enable_thinking": false}`, which SGLang and vLLM pass to Qwen3-style chat templates; faster, and Describe then uses 600 tokens.
  - Every LLM call reads the reasoning (`reasoning_content`, `reasoning` or an unclosed `<think>`) and `finish_reason`, so a cut-off reply says "used all N tokens thinking" instead of "no text". The "Is it a vision model?" hint only appears when the model really answered with nothing.
  - Test connection notes when the model thinks before answering.

## v0.3.1 — 2026-11-02

- Script import (Global → Import a script) asks where the proposed scenes go: **at the end**, **after the selected scene**, or **replace all scenes**. Replacing asks first; cast, assets and Global settings stay, and rendered takes stay on disk. The first imported scene is selected, the film's first scene always starts fresh, and Ctrl+Z undoes the import.

## v0.3.0 — 2026-11-02

- **Profiles** (Global tab): save the Global settings under a name, apply them to any project, update or delete them, and mark one as the default for new nodes. They live in `user/reelwright/profiles.json` and are shared by every Reelwright node. A new node starts with the default profile and shows a banner to pick another one.
- **Per-scene quality**: a scene can render as Draft or Final regardless of the Global switch (Scene tab → Generation → Quality, or the scene's right-click menu). Draft scenes get a tag on the timeline. Quality is part of the cache key.
- **Per-scene transitions**: a scene that starts fresh can set its own cut, crossfade or dip, its length and its audio fade (Scene tab → Starts from → Cut into this scene). The Merge card's values are now the defaults.
- Deleting a scene asks first. Deleting the only scene resets it to an empty scene instead of leaving it unchanged.
- **Assets can be deleted** from the inspector or their right-click menu (asset cards and the timeline bin), with confirmation. They are removed from every scene, cast anchor, voice, outfit and the score track; the file stays on disk.
- Ctrl + wheel over the node zooms the ComfyUI canvas, as the wheel does over empty space. Over text fields and lists it does nothing. Alt + wheel still zooms the timeline.
- Render progress: the Render tab shows "Scene k of n" with a bar for the scene and one for the whole run, and the node title shows `rendering k/n · NN%`.
- LLM **Test connection** now reports its result under the button and as a message, and gives up after 20 seconds instead of appearing to do nothing. It tests the URL and model shown on the tab.

## v0.2.2 — 2026-11-02

- Right-click inside the editor no longer opens ComfyUI's node menu, where Delete removed the whole node. Scenes, on the timeline and on the Scene tab strip, get their own menu: open, render, new take, split at playhead, duplicate, move, lock and delete. Text fields keep the browser's copy/paste menu.
- Mouse wheel inside the editor scrolls the editor instead of zooming the canvas. This mostly affected ComfyUI's "Nodes 2.0" mode. Alt or Ctrl + wheel on the timeline still zooms the timeline.
- Dropdown lists stay open when you press or drag their scrollbar, and keep what you typed. The list scrollbar is now always visible.

## v0.2.1 — 2026-11-02

Fixes a crash after a render when the automatic merge failed.

- Merge: the final audio is pinned to 48 kHz stereo (`aformat` plus `-ac 2`). Newer ffmpeg builds (for example conda-forge's) failed with "Cannot select channel layout for the link between filters … and format_out".
- Merge writes to `<cut>.partial.mp4` and renames it only on success, so a failed merge no longer leaves a broken `<slug>_cut_vN.mp4`.
- Node: after a failed merge it outputs the last scene's take instead of the newest cut, and skips any video ffprobe can't read. `merge.probe` now raises a readable `MergeError` instead of `CalledProcessError`.
- Editor: a failed automatic merge now shows a toast and the error in the Merge card.

## v0.2.0 — 2026-11-02

Prompts now follow MiniMax's official Ref2VA guide, and the editor gets searchable pickers, ComfyUI file browsing and vision descriptions.

- Prompt format (MiniMax H3 `ref-en.txt`):
  - six labelled sections, each label on its own line: `subject_definitions:`, `summary:`, `retention_analysis:`, `detailed_description:`, `overall_soundscape:`, `non_diegetic_music:` (empty ones are `N/A`);
  - reference pictures that define a character, place, prop or style become `<Subject N>`, with a subject line from the asset's new description;
  - retention lines name the shots a subject appears in;
  - shots read `[Shot 1] A wide shot: …` and `[Shot 2] At 00:06.000, the shot cuts to …`;
  - speaker IDs follow speaking order in each clip (S1, S2…), so the Cast tab no longer has a Speaker ID field;
  - info lints for a short detailed description, an empty soundscape and an undescribed reference asset.
- LLM:
  - **Download** MiniMax's official H3 guides (Ref2VA and base) into `user/reelwright/guides/`; they are sent with rewrite, split and script import when *H3 guides* is on, otherwise a built-in summary is sent;
  - Rewrite now sees the built pass-1 prompt;
  - **Describe with LLM** for assets (picture, or three video frames) and **From anchors** for cast entries, with your own question; the answer is a suggestion you can use or append.
- Assets: **From ComfyUI** browses ComfyUI's input and output folders (filter by path and kind, multi-select); output files are linked into the project's input folder.
- Pickers: every drop-down is a type-to-filter combobox. Language and LLM model also accept typed values.
- Help: **?** popovers open beside their icon, stay inside the node at any canvas zoom, and can be dragged by the header; tooltips are clamped to the node.
- Render tab: **Merge** moved from the tab bar to the scenes-and-takes table, with a link to the last cut; a **File** column shows each scene's rendered video.
- Take videos are named `<project>_<NN>_<scene title>_<take>.mp4` instead of `video.mp4` (older takes keep their names).
- New routes: `/reelwright/llm/guides`, `/reelwright/llm/describe`, `/reelwright/files`, `/reelwright/import`.

## v0.1.0 — 2026-11-02

First version.

- Reelwright node with an editor inside it: Timeline, Scene, Assets, Cast, Render and Global tabs.
- Scenes of any length: planner on the H3 17k+5 grid (124–362 frames per pass).
  - Long scenes are split at shot cuts or with guided overlaps.
  - Short scenes are trimmed from the shortest pass, keeping handles.
- Scene starts: fresh, last frame of the previous scene, or tail clip of the previous scene (`MiniMaxH3AddGuide` clip and audio).
- Global settings with per-scene overrides: models, VAEs, LoRA stack (add or replace), seed, steps, sampler, size.
- Cast: anchor sheets, outfits, voice, speaker IDs, identity LoRA.
  - Re-anchor rule.
  - Optional insightface drift check.
- References, renumbered per pass in native order:
  - retention labels, keyframes, first and last frames;
  - video soundtracks;
  - budget warnings.
- Structured six-section prompt editor with `@tags`, auto subjects, retention, shots and dialogue, and a per-pass preview.
- Render:
  - content cache keys, takes and stars;
  - resume, lock;
  - render scopes (pending, selected, from playhead, all, new take);
  - draft/final;
  - memory policies, encode-first;
  - live progress.
- Merge (ffmpeg):
  - cut, crossfade, dip, continuation crossfades;
  - loudnorm, ducked score track, colour match;
  - SRT, chapters, OTIO, FCPXML, bundle.
- OpenAI-compatible prompt rewriter, pass splitter and script import. Runs only on click.
- Autosave with versions, undo and redo, keyboard shortcuts, a tooltip and **?** help for every control.
