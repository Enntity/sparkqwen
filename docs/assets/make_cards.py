#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Compose the two-model SparkQwen cards from the 0.4.0 cards.

    make_cards.py BASE_DIR FONT.ttf OUT_DIR

BASE_DIR holds the 0.4.0 `banner.png` and `social-preview.png` (this
directory at commit a0d38a3). The frame, starfield, logo, title lettering,
tunnel and URL are kept as they are; the version, subtitle, metric columns
and supporting lines are painted out and the new text is set in Press Start 2P
(SIL OFL 1.1, not shipped here). Needs Pillow. The JPEG is a format export
of the social card.
"""
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

WHITE, YELLOW, ORANGE = (255, 255, 255), (255, 232, 26), (255, 150, 40)
PURPLE, VIOLET, DIM = (190, 120, 255), (150, 90, 235), (170, 170, 190)
STAR_COLORS = [WHITE] * 5 + [YELLOW] * 3 + [(170, 100, 255), (90, 220, 255)]


class Card:
    def __init__(self, base, font_path):
        self.im = Image.open(base).convert("RGB")
        self.font_path = font_path
        self.draw = ImageDraw.Draw(self.im)
        self.cleared, self.inked = [], []

    def font(self, size):
        return ImageFont.truetype(self.font_path, size)

    def clear(self, box):
        """Paint a region black; `stars` refills it once the text is set."""
        self.draw.rectangle(box, fill=(0, 0, 0))
        self.cleared.append(box)

    def clear_warm(self, box, stars=None):
        """Paint out only a region's warm pixels (the old version and its
        orange glow), so the tunnel's dim blue haze beside it keeps no edge.
        `stars` is the part that gets new stars."""
        region = self.im.crop(box)
        r, _, b = region.split()
        ink = ImageChops.subtract(r, b).point(lambda v: 255 if v > 2 else 0)
        region.paste((0, 0, 0), mask=ink.filter(ImageFilter.MaxFilter(9)))
        self.im.paste(region, box[:2])
        self.draw = ImageDraw.Draw(self.im)
        if stars:
            self.cleared.append(stars)

    def stars(self, seed, pad=14):
        """Scatter stars over the cleared regions at the base card's density, clear of the text."""
        rng = random.Random(seed)
        for x0, y0, x1, y1 in self.cleared:
            if x1 - x0 < 40 or y1 - y0 < 40:
                continue
            for _ in range(max(1, (x1 - x0) * (y1 - y0) // 24000)):
                s = rng.choice([3, 3, 4, 5])
                x, y = rng.randrange(x0 + 6, x1 - s - 6), rng.randrange(y0 + 6, y1 - s - 6)
                if not any(a - pad < x < c + pad and b - pad < y < d + pad for a, b, c, d in self.inked):
                    self.draw.rectangle((x, y, x + s, y + s), fill=rng.choice(STAR_COLORS))

    def text(self, xy, parts, size, color, glow=None, gap=None):
        """Draw `parts` left to right from `xy`, a square dot between them."""
        font = self.font(size)
        gap = size if gap is None else gap
        width = sum(int(font.getlength(p)) for p in parts) + 2 * gap * (len(parts) - 1)
        self.draw.rectangle((xy[0] - 8, xy[1] - 8, xy[0] + width + 8, xy[1] + size + 8), fill=(0, 0, 0))
        layer = Image.new("RGB", self.im.size, (0, 0, 0))
        d = ImageDraw.Draw(layer)
        x, y = xy
        for i, part in enumerate(parts):
            if i:
                dot = max(3, size // 5)
                cy = y + size // 2
                d.rectangle((x + gap - dot // 2, cy - dot // 2, x + gap + dot - dot // 2, cy + dot - dot // 2), fill=color)
                x += 2 * gap
            d.text((x, y), part, font=font, fill=color)
            x += int(font.getlength(part))
        if glow:
            tint = Image.new("RGB", self.im.size, glow)
            mask = layer.convert("L").point(lambda v: 255 if v else 0)
            halo = Image.composite(tint, Image.new("RGB", self.im.size, (0, 0, 0)), mask)
            halo = halo.filter(ImageFilter.GaussianBlur(max(2, size // 5)))
            self.im = ImageChops.screen(self.im, halo)
        self.im = ImageChops.lighter(self.im, layer) if not glow else Image.composite(
            layer, self.im, layer.convert("L").point(lambda v: 255 if v else 0))
        self.draw = ImageDraw.Draw(self.im)
        self.inked.append((xy[0], y, x, y + size))
        return x

    def rule(self, x, y0, y1):
        self.draw.rectangle((x, y0, x + 2, y1), fill=(170, 60, 230))
        self.inked.append((x, y0, x + 2, y1))


def lanes(card, x0, x1, y, k, ky):
    """Two lanes between x0 and x1 from y down; k scales the type, ky the leading."""
    mid = (x0 + x1) // 2
    card.rule(mid - int(18 * k), y, y + int(160 * ky))
    lane = [
        (x0, ["ONE DGX SPARK", "CANDIDATE"], "Qwen3.8-27B", "./start.sh --model 27b",
         ["NVFP4", "DFlash2", "exact verify", "262K"]),
        (mid + int(18 * k), ["TWO DGX SPARKS", "TP=2"], "Qwen3.8-Flash-Next", "./start.sh --model flash-next",
         ["FP4-Local", "native MTP", "262K"]),
    ]
    for x, label, name, cmd, detail in lane:
        card.text((x, y), label, int(19 * k), PURPLE)
        card.text((x, y + int(38 * ky)), [name], int(33 * k), YELLOW, glow=ORANGE)
        card.text((x, y + int(95 * ky)), [cmd], int(18 * k), WHITE)
        card.text((x, y + int(138 * ky)), detail, int(15 * k), VIOLET, gap=int(11 * k))


def banner(base, font, out):
    c = Card(base, font)
    c.clear_warm((1062, 60, 1540, 244), (1075, 70, 1480, 240))  # the version
    c.clear((75, 244, 1345, 520))         # subtitle and metric columns
    c.clear((150, 521, 1200, 700))        # supporting lines (icons stay)
    c.text((1100, 118), ["ONE REPO"], 30, ORANGE, glow=(255, 90, 30))
    c.text((1100, 168), ["TWO MODELS"], 30, YELLOW, glow=ORANGE)
    c.text((88, 258), ["Qwen3.8 on NVIDIA DGX Spark", "switch with --model"], 23, WHITE)
    lanes(c, 100, 1500, 322, 1.0, 1.0)
    for y, parts in ((537, ["Common Atlas engine", "prefix caching"]),
                     (580, ["Tool-call exfiltration guard", "on by default"]),
                     (624, ["Flash-Next: 106.4 tok/s code", "4,142 tok/s prefill"])):
        c.text((172, y), parts, 20, WHITE)
    c.text((172, 668), ["0.3.1 benchmarks", "RigMark 1.1.0", "low effort"], 14, DIM, gap=10)
    c.stars(1)
    c.im.save(out, optimize=True)


def social(base, font, out):
    c = Card(base, font)
    c.clear_warm((866, 130, 1215, 250), (880, 140, 1150, 285))  # the version,
    c.clear_warm((866, 250, 1185, 268))                         # stepped along
    c.clear_warm((866, 268, 1160, 292))                         # the tunnel's edge
    c.clear_warm((1185, 250, 1202, 260))
    c.clear_warm((1160, 268, 1174, 280))
    c.clear((70, 292, 1136, 585))         # subtitle and metric columns
    c.clear((150, 596, 1050, 815))        # supporting lines (icons stay)
    c.text((888, 180), ["ONE REPO"], 22, ORANGE, glow=(255, 90, 30))
    c.text((888, 218), ["TWO MODELS"], 22, YELLOW, glow=ORANGE)
    c.text((82, 308), ["Qwen3.8 on NVIDIA DGX Spark", "switch with --model"], 19, WHITE)
    lanes(c, 82, 1150, 384, 0.84, 1.08)
    for y, parts in ((618, ["Common Atlas engine", "prefix caching"]),
                     (668, ["Tool-call exfiltration guard", "on by default"]),
                     (718, ["Flash-Next: 106.4 tok/s code", "4,142 prefill"])):
        c.text((170, y), parts, 17, WHITE, gap=12)
    c.text((170, 770), ["0.3.1 benchmarks", "RigMark 1.1.0", "low effort"], 13, DIM, gap=9)
    c.stars(2)
    c.im.save(out, optimize=True)
    c.im.save(Path(out).with_suffix(".jpg"), quality=90)


if __name__ == "__main__":
    base, font, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    banner(base / "banner.png", font, out / "banner.png")
    social(base / "social-preview.png", font, out / "social-preview.png")
