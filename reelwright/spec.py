"""MiniMax H3 constants and frame/canvas math.

Mirrors comfy_extras/nodes_minimax_h3.py so the planner gives the same numbers
as the native nodes without importing ComfyUI.
"""

import math
import re  # added 2026-11-03 v0.6.0: numeric text check in num()

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
# [OLD 2026-11-08 v0.11.0->v0.12.0] ROLES = ("reference", "first_frame", "last_frame", "keyframe")
ROLES = ("reference", "first_frame", "last_frame", "keyframe", "pose")  # v0.12.0: pose (model.pose_refs)
START_MODES = ("fresh", "last_frame", "tail")
TASK_TAG_ORDER = ("reference generation", "keyframe completion", "video continuation",
                  "video editing", "audio reuse", "audio reference")
ASPECTS = {"21:9": (21, 9), "16:9": (16, 9), "4:3": (4, 3), "1:1": (1, 1), "3:4": (3, 4), "9:16": (9, 16)}


# [OLD 2026-11-03 v0.5.1->v0.6.0] loops; NaN/inf raised (model.js looped forever on NaN): now arithmetic, garbage -> 5
# def align_frames_up(n):
#     """Smallest 17k+5 frame count >= n (and >= 5)."""
#     n = max(5, int(round(n)))
#     while n % 17 != 5:
#         n += 1
#     return n
#
#
# def align_frames_down(n):
#     """Largest 17k+5 frame count <= n, never below 5."""
#     n = int(n)
#     if n < 5:
#         return 5
#     while n % 17 != 5:
#         n -= 1
#     return n
# [/OLD]
def align_frames_up(n):
    """Smallest 17k+5 frame count >= n (and >= 5). Not a finite number -> 5 (same as model.js alignFramesUp)."""
    n = num(n, 0)
    n = max(5, int(round(n)))
    return n + (5 - n) % 17


def align_frames_down(n):
    """Largest 17k+5 frame count <= n, never below 5. Not a finite number -> 5."""
    n = int(num(n, 0))
    if n < 5:
        return 5
    return n - (n - 5) % 17


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


# ---- added 2026-11-03 v0.6.0: value coercion shared by the normalisers (model.py, soundtrack.py). model.js has the
# same three (num, flag, text) so Python and the editor make the same project out of the same JSON.
_NUM_TEXT = re.compile(r"^[ \t\n\r]*[-+]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?[ \t\n\r]*$")


def num(v, default=0.0):
    """v as a finite number (numbers, or text such as "12.5"), else default. True/False are not numbers."""
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        try:
            return v if math.isfinite(v) else default
        except OverflowError:  # an int too big for a float
            return default
    if isinstance(v, str) and _NUM_TEXT.match(v):
        x = float(v)
        return x if math.isfinite(x) else default
    return default


def flag(v, default=False):
    """v as a bool: booleans as they are, numbers are True unless 0, anything else is default."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        x = num(v, None)
        return default if x is None else x != 0
    return default


def text(v, default=""):
    """v as a string: strings as they are, finite numbers written the way JavaScript's String() writes them,
    anything else (None, lists, objects, booleans) is default."""
    if isinstance(v, str):
        return v
    x = num(v, None) if isinstance(v, (int, float)) else None
    return default if x is None else js_number(x)


def js_number(x):
    """A finite number as JavaScript's String(x) writes it (1.0 -> "1", 1e-7 -> "1e-7")."""
    if isinstance(x, int) and abs(x) < 2 ** 53:
        return str(x)
    x = float(x)
    if x == 0:
        return "0"
    if x.is_integer() and abs(x) < 2 ** 53:
        return str(int(x))
    import decimal
    sign = "-" if x < 0 else ""
    t = decimal.Decimal(repr(abs(x))).normalize().as_tuple()  # repr: the shortest digits that read back as x
    digits = "".join(str(d) for d in t.digits)
    k = len(digits)
    n = t.exponent + k  # x = 0.digits * 10**n
    if k <= n <= 21:
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        return sign + digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * (-n) + digits
    e = n - 1
    return sign + digits[0] + ("." + digits[1:] if k > 1 else "") + "e" + ("+" if e > 0 else "-") + str(abs(e))
