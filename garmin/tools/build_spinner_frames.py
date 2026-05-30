#!/usr/bin/env python3
"""Generate pre-rendered glyph bitmaps for the watch history view.

All status glyphs (bracketed ASCII like [+], [~], [!]) and the animated
spinner frames ([·], [✦], [✧], …) are shipped as identically-sized PNG
bitmaps.  This guarantees pixel-perfect column alignment on Garmin's
proportional system fonts — every glyph occupies the exact same
rectangle regardless of character width.

Bitmap inventory (15 total):
  Static glyphs (8):
    glyph_plus_green.png       [+]  #55DD55  (CHECK, GREEN_CIRCLE)
    glyph_minus_white.png      [-]  #FFFFFF  (default / unknown)
    glyph_tilde_chrome.png     [~]  #888888  (PAUSE)
    glyph_bang_amber.png       [!]  #E89030  (WARNING, FLAG_ACCENT)
    glyph_question_amber.png   [?]  #E89030  (QUESTION)
    glyph_x_chrome.png         [x]  #888888  (STOP)
    glyph_x_amber.png          [x]  #E89030  (NO_ENTRY)
    glyph_dot_white.png        [.]  #FFFFFF  (STATUS_DOT)

  Spinner frames (7 — cycled at 150 ms):
    spinner_0.png              [·]  #E89030  (dot → bloom)
    spinner_1.png              [✦]  #E89030
    spinner_2.png              [✧]  #E89030
    spinner_3.png              [✶]  #E89030
    spinner_4.png              [✷]  #E89030
    spinner_5.png              [✸]  #E89030
    spinner_6.png              [✹]  #E89030

Usage:
    python tools/build_spinner_frames.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "resources" / "drawables"

# ---------------------------------------------------------------------------
# Palette (must match Palette.mc)
# ---------------------------------------------------------------------------

COLOR_AMBER = (0xE8, 0x90, 0x30, 0xFF)  # Palette.active()
COLOR_GREEN = (0x55, 0xDD, 0x55, 0xFF)  # Palette.done()
COLOR_WHITE = (0xFF, 0xFF, 0xFF, 0xFF)  # Palette.text()
COLOR_CHROME = (0x88, 0x88, 0x88, 0xFF)  # Palette.chrome()

# ---------------------------------------------------------------------------
# Glyph definitions
# ---------------------------------------------------------------------------

# Static glyphs: (filename, display_text, color)
STATIC_GLYPHS: list[tuple[str, str, tuple[int, int, int, int]]] = [
    ("glyph_plus_green", "[+]", COLOR_GREEN),
    ("glyph_minus_white", "[-]", COLOR_WHITE),
    ("glyph_tilde_chrome", "[~]", COLOR_CHROME),
    ("glyph_bang_amber", "[!]", COLOR_AMBER),
    ("glyph_question_amber", "[?]", COLOR_AMBER),
    ("glyph_x_chrome", "[x]", COLOR_CHROME),
    ("glyph_x_amber", "[x]", COLOR_AMBER),
    ("glyph_dot_white", "[.]", COLOR_WHITE),
]

# Spinner frames: dot first, then expanding stars — all in brackets.
SPINNER_GLYPHS: list[str] = ["·", "✦", "✧", "✶", "✷", "✸", "✹"]

# ---------------------------------------------------------------------------
# Font resolution
# ---------------------------------------------------------------------------

FONT_CANDIDATES = [
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    # Must be last, as it's the only font that supports the spinner glyphs.
    "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf",
    # macOS
    "/Library/Fonts/Arial Unicode.ttf",
    # Windows
    "C:/Windows/Fonts/seguisym.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def pick_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError(
        "No suitable font found.  Install fonts-noto or fonts-dejavu, or "
        "edit FONT_CANDIDATES at the top of this script."
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def measure_max_bbox(
    font: ImageFont.FreeTypeFont,
    texts: list[str],
) -> tuple[int, int]:
    """Return (max_width, max_height) across all texts."""
    tmp = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(tmp)
    max_w, max_h = 0, 0
    for text in texts:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w > max_w:
            max_w = w
        if h > max_h:
            max_h = h
    return max_w, max_h


def measure_bracket_layout(
    font: ImageFont.FreeTypeFont,
    texts: list[str],
) -> tuple[int, int, int, int]:
    """Return fixed bracket layout: (left_w, inner_max_w, right_w, max_h)."""
    tmp = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(tmp)

    left_bbox = draw.textbbox((0, 0), "[", font=font)
    right_bbox = draw.textbbox((0, 0), "]", font=font)
    left_w = left_bbox[2] - left_bbox[0]
    left_h = left_bbox[3] - left_bbox[1]
    right_w = right_bbox[2] - right_bbox[0]
    right_h = right_bbox[3] - right_bbox[1]

    inner_max_w = 0
    max_h = max(left_h, right_h)
    for text in texts:
        if len(text) < 3 or not text.startswith("[") or not text.endswith("]"):
            raise ValueError(f"Expected bracketed glyph text, got {text!r}")
        inner = text[1:-1]
        bbox = draw.textbbox((0, 0), inner, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w > inner_max_w:
            inner_max_w = w
        if h > max_h:
            max_h = h

    return left_w, inner_max_w, right_w, max_h


def render_glyph(
    text: str,
    font: ImageFont.FreeTypeFont,
    color: tuple[int, int, int, int],
    canvas_w: int,
    canvas_h: int,
    bracket_layout: tuple[int, int, int, int],
) -> Image.Image:
    """Render bracketed glyph text with fixed bracket alignment."""
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if len(text) < 3 or not text.startswith("[") or not text.endswith("]"):
        # Fallback for any future non-bracketed glyph: old centered rendering.
        bbox = draw.textbbox((0, 0), text, font=font)
        gw = bbox[2] - bbox[0]
        gh = bbox[3] - bbox[1]
        x = (canvas_w - gw) // 2 - bbox[0]
        y = (canvas_h - gh) // 2 - bbox[1]
        draw.text((x, y), text, font=font, fill=color)
        return img

    left_w, inner_max_w, right_w, max_h = bracket_layout
    inner = text[1:-1]
    frame_w = left_w + inner_max_w + right_w
    frame_x = (canvas_w - frame_w) // 2
    frame_y = (canvas_h - max_h) // 2

    left_bbox = draw.textbbox((0, 0), "[", font=font)
    right_bbox = draw.textbbox((0, 0), "]", font=font)
    inner_bbox = draw.textbbox((0, 0), inner, font=font)

    left_h = left_bbox[3] - left_bbox[1]
    right_h = right_bbox[3] - right_bbox[1]
    inner_w = inner_bbox[2] - inner_bbox[0]
    inner_h = inner_bbox[3] - inner_bbox[1]

    left_target_x = frame_x
    inner_target_x = frame_x + left_w + (inner_max_w - inner_w) // 2
    right_target_x = frame_x + left_w + inner_max_w

    left_target_y = frame_y + (max_h - left_h) // 2
    inner_target_y = frame_y + (max_h - inner_h) // 2
    right_target_y = frame_y + (max_h - right_h) // 2

    draw.text(
        (left_target_x - left_bbox[0], left_target_y - left_bbox[1]),
        "[",
        font=font,
        fill=color,
    )
    draw.text(
        (inner_target_x - inner_bbox[0], inner_target_y - inner_bbox[1]),
        inner,
        font=font,
        fill=color,
    )
    draw.text(
        (right_target_x - right_bbox[0], right_target_y - right_bbox[1]),
        "]",
        font=font,
        fill=color,
    )
    return img


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Font size 22 produces bitmaps that visually match FONT_SMALL on
    # Garmin devices (typically 22-26 px tall).  The previous size (14)
    # was barely legible on device.
    font_size = 22
    font = pick_font(font_size)

    # Collect every text string we'll render so we can compute a uniform
    # canvas size (all bitmaps must be identical dimensions for alignment).
    all_texts: list[str] = []
    for _, text, _ in STATIC_GLYPHS:
        all_texts.append(text)
    for g in SPINNER_GLYPHS:
        all_texts.append(f"[{g}]")

    max_w, max_h = measure_max_bbox(font, all_texts)
    bracket_layout = measure_bracket_layout(font, all_texts)
    frame_w = bracket_layout[0] + bracket_layout[1] + bracket_layout[2]
    frame_h = bracket_layout[3]
    if frame_w > max_w:
        max_w = frame_w
    if frame_h > max_h:
        max_h = frame_h
    # Add 2px padding on each side for breathing room.
    canvas_w = max_w + 4
    canvas_h = max_h + 4
    print(f"Uniform bitmap size: {canvas_w} x {canvas_h}")

    # --- Static glyphs ---
    for filename, text, color in STATIC_GLYPHS:
        img = render_glyph(text, font, color, canvas_w, canvas_h, bracket_layout)
        out = OUT_DIR / f"{filename}.png"
        img.save(out, "PNG")
        print(
            f"  wrote {out.name:30s}  {text}  #{color[0]:02x}{color[1]:02x}{color[2]:02x}"
        )

    # --- Spinner frames ---
    for i, glyph in enumerate(SPINNER_GLYPHS):
        bracketed = f"[{glyph}]"
        img = render_glyph(
            bracketed, font, COLOR_AMBER, canvas_w, canvas_h, bracket_layout
        )
        out = OUT_DIR / f"spinner_{i}.png"
        img.save(out, "PNG")
        # Use repr() for the glyph to avoid Windows console encoding errors.
        safe = bracketed.encode("ascii", "replace").decode("ascii")
        print(
            f"  wrote {out.name:30s}  {safe}  #{COLOR_AMBER[0]:02x}{COLOR_AMBER[1]:02x}{COLOR_AMBER[2]:02x}"
        )

    print(f"\n  {len(STATIC_GLYPHS) + len(SPINNER_GLYPHS)} bitmaps generated.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
