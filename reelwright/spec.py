"""MiniMax H3 constants and frame/canvas math.

Mirrors comfy_extras/nodes_minimax_h3.py so the planner gives the same numbers
as the native nodes without importing ComfyUI.
"""

import math

FPS = 24
AUDIO_SAMPLE_RATE = 32000
MIN_PASS_FRAMES = 124      # bottom of the trained range (~5.17 s)
MAX_PASS_FRAMES = 362      # top of the trained range (~15.08 s)
CANVAS_MULTIPLE = 32
BASE_SHORT_EDGE = 768
MAX_PIXELS = 768 * 1344

MAX_REF_IMAGES = 9
MAX_REF_VIDEOS = 3
MAX_REF_AUDIOS = 3
MAX_REF_FILES = 12
REF_MEDIA_MIN_SECONDS = 2.0
REF_MEDIA_MAX_SECONDS = 15.0
REF_MEDIA_TOTAL_SECONDS = 15.0

STABLE_LANGUAGES = ("Arabic", "Chinese", "English", "French", "German", "Italian",
                    "Japanese", "Korean", "Portuguese", "Russian", "Spanish")
VISUAL_RETENTION = ("fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference")
AUDIO_RETENTION = ("fully_copy", "partially_copy", "reference", "weak_reference")
ROLES = ("reference", "first_frame", "last_frame", "keyframe")
START_MODES = ("fresh", "last_frame", "tail")
TASK_TAG_ORDER = ("reference generation", "keyframe completion", "video continuation",
                  "video editing", "audio reuse", "audio reference")
ASPECTS = {"21:9": (21, 9), "16:9": (16, 9), "4:3": (4, 3), "1:1": (1, 1), "3:4": (3, 4), "9:16": (9, 16)}


def align_frames_up(n):
    """Smallest 17k+5 frame count >= n (and >= 5)."""
    n = max(5, int(round(n)))
    while n % 17 != 5:
        n += 1
    return n


def align_frames_down(n):
    """Largest 17k+5 frame count <= n, never below 5."""
    n = int(n)
    if n < 5:
        return 5
    while n % 17 != 5:
        n -= 1
    return n


def frames_of(seconds):
    return int(round(seconds * FPS))


def clamp_pass_frames(n):
    """Valid generated length for a pass that has to cover n frames."""
    return min(MAX_PASS_FRAMES, align_frames_up(max(MIN_PASS_FRAMES, n)))


def adapt_canvas(width, height):
    """768-short-edge canvas with 768*1344 area cap, per-axis round to 32."""
    ratio = width / height
    if ratio >= 1.0:
        nom_w, nom_h = BASE_SHORT_EDGE * ratio, BASE_SHORT_EDGE
    else:
        nom_w, nom_h = BASE_SHORT_EDGE, BASE_SHORT_EDGE / ratio
    if nom_w * nom_h > MAX_PIXELS:
        s = math.sqrt(MAX_PIXELS / (nom_w * nom_h))
        nom_w, nom_h = nom_w * s, nom_h * s
    return (max(CANVAS_MULTIPLE, round(nom_w / CANVAS_MULTIPLE) * CANVAS_MULTIPLE),
            max(CANVAS_MULTIPLE, round(nom_h / CANVAS_MULTIPLE) * CANVAS_MULTIPLE))


def snap_canvas(width, height):
    return (max(CANVAS_MULTIPLE, int(round(width / CANVAS_MULTIPLE)) * CANVAS_MULTIPLE),
            max(CANVAS_MULTIPLE, int(round(height / CANVAS_MULTIPLE)) * CANVAS_MULTIPLE))


def fmt_time(t):
    """00:05.000 style used by the H3 prompt guide."""
    t = max(0.0, t)
    m = int(t // 60)
    return "{:02d}:{:06.3f}".format(m, t - m * 60)
