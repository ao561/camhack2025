#!/usr/bin/env python3
"""
Quadtree → Rectangles (pygame), background-first.

What it does
------------
1) Compute the image's dominant color (palette-quantized or mean).
2) Show ONE big background rectangle (that dominant color) covering the frame.
3) Build a quadtree, score each leaf by "how much it improves over the background":
       score = area_in_window * ||mean_color - bg||^2
   Pick the top K (if --max-rects given), sort by area DESC (big first).
4) Reveal rectangles progressively (optionally fading each batch).

Controls
--------
SPACE          pause/play
[ / ]          decrease/increase rectangles-per-frame
F              toggle fade
B              toggle 1px borders
ESC / Q        quit
"""

import argparse
import math
import os
import random
import time
from collections import deque
from typing import List, Tuple

import pygame
from PIL import Image, ImageStat


# ──────────────────────────────────────────────────────────────────────────────
# Tunables (good defaults; can override most via CLI)
# ──────────────────────────────────────────────────────────────────────────────
TITLE_TEXT = "Quadtree Display"   # Window title
MARGIN = 0                       # Padding around the drawn image, in pixels
VARIANCE_THRESHOLD = 15           # Split a node only if avg channel stddev > this
MIN_WINDOW_SIZE = 15              # Stop splitting if either side < 2*MIN_WINDOW_SIZE
MAX_DEPTH = 8                     # Quadtree max depth
JITTER_POS = 0.00                 # Positional jitter fraction (0.1 = ±10% of rect size)
WINDOW_SCALE = 1.00                # Scale the image when drawing (0.5 = half size)
AUTO_CLOSE_SECONDS = 0            # Auto close after N seconds (0 = never)
RECTS_PER_FRAME = 60              # How many rects to add each animation frame
USE_FADE = True                   # Fade batches in?
FADE_DURATION = 0.15              # Seconds to fade a batch
DRAW_BORDERS = False              # Draw a 1px border around rectangles?

# How to pick background color:
BG_MODE = "mean"                  # "palette" or "mean"
PALETTE_COLORS = 10               # If BG_MODE=="palette": how many colors to quantize to


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def rgb_dist2(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
    """Squared Euclidean distance in RGB space."""
    dr = a[0] - b[0]
    dg = a[1] - b[1]
    db = a[2] - b[2]
    return dr * dr + dg * dg + db * db


def dominant_color(img: Image.Image, mode: str = BG_MODE, colors: int = PALETTE_COLORS) -> Tuple[int, int, int]:
    """Return a robust dominant color for the whole image."""
    if mode == "mean":
        stat = ImageStat.Stat(img)
        return tuple(int(x) for x in stat.mean[:3])

    # Palette-quantized dominant color
    small = img.copy()
    small.thumbnail((256, 256), Image.LANCZOS)
    pal_img = small.convert("P", palette=Image.ADAPTIVE, colors=colors)
    palette = pal_img.getpalette()        # [R0,G0,B0, R1,G1,B1, ...]
    counts = pal_img.getcolors()          # [(count, palette_index), ...]
    if not counts:
        stat = ImageStat.Stat(img)
        return tuple(int(x) for x in stat.mean[:3])
    _, idx = max(counts, key=lambda t: t[0])
    r, g, b = palette[3 * idx: 3 * idx + 3]
    return int(r), int(g), int(b)


# ──────────────────────────────────────────────────────────────────────────────
# Quadtree
# ──────────────────────────────────────────────────────────────────────────────

class QuadNode:
    """Axis-aligned rectangle over the image with cached mean color + variance."""
    __slots__ = ("x", "y", "w", "h", "depth", "children", "color", "variance")

    def __init__(self, x, y, w, h, img: Image.Image, depth=0):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.depth = depth
        self.children: List["QuadNode"] = []
        self.color = self._avg(img)
        self.variance = self._var(img)

    def _box(self, img: Image.Image):
        x0 = int(max(0, self.x))
        y0 = int(max(0, self.y))
        x1 = int(min(img.width, self.x + self.w))
        y1 = int(min(img.height, self.y + self.h))
        return x0, y0, x1, y1

    def _avg(self, img: Image.Image) -> Tuple[int, int, int]:
        x0, y0, x1, y1 = self._box(img)
        if x1 <= x0 or y1 <= y0:
            return (0, 0, 0)
        stat = ImageStat.Stat(img.crop((x0, y0, x1, y1)))
        return int(stat.mean[0]), int(stat.mean[1]), int(stat.mean[2])

    def _var(self, img: Image.Image) -> float:
        x0, y0, x1, y1 = self._box(img)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        stat = ImageStat.Stat(img.crop((x0, y0, x1, y1)))
        return sum(stat.stddev) / 3.0 if hasattr(stat, "stddev") else 0.0

    def should_split(self) -> bool:
        return (
            self.variance > VARIANCE_THRESHOLD
            and min(self.w, self.h) > MIN_WINDOW_SIZE * 2
            and self.depth < MAX_DEPTH
        )

    def split(self, img: Image.Image):
        hw, hh = self.w / 2.0, self.h / 2.0
        d = self.depth + 1
        self.children = [
            QuadNode(self.x,        self.y,        hw, hh, img, d),
            QuadNode(self.x + hw,   self.y,        hw, hh, img, d),
            QuadNode(self.x,        self.y + hh,   hw, hh, img, d),
            QuadNode(self.x + hw,   self.y + hh,   hw, hh, img, d),
        ]

    def leaves(self) -> List["QuadNode"]:
        if not self.children:
            return [self]
        out: List[QuadNode] = []
        for c in self.children:
            out.extend(c.leaves())
        return out


def build_quadtree(img: Image.Image) -> QuadNode:
    """BFS growth for better balance + temporal locality."""
    root = QuadNode(0, 0, img.width, img.height, img)
    q = deque([root])
    while q:
        n = q.popleft()
        if n.should_split():
            n.split(img)
            q.extend(n.children)
    return root


# ──────────────────────────────────────────────────────────────────────────────
# Pygame rendering
# ──────────────────────────────────────────────────────────────────────────────

def run(
    image_path: str,
    max_rects: int | None = None,
    rects_per_frame: int = RECTS_PER_FRAME,
    window_scale: float = WINDOW_SCALE,
    fade: bool = USE_FADE,
    borders: bool = DRAW_BORDERS,
    bg_mode: str = BG_MODE,
    palette_colors: int = PALETTE_COLORS,
    auto_close: float = AUTO_CLOSE_SECONDS,
):
    img = Image.open(image_path).convert("RGB")
    img_w, img_h = img.size

    # 1) Choose background color once, then start by drawing only that.
    bg = dominant_color(img, mode=bg_mode, colors=palette_colors)
    print(f"Background (dominant): {bg}  mode={bg_mode}")

    # Window geometry
    W = int(img_w * window_scale)
    H = int(img_h * window_scale)

    pygame.init()
    window = pygame.display.set_mode((W + 2 * MARGIN, H + 2 * MARGIN))
    pygame.display.set_caption(TITLE_TEXT)
    clock = pygame.time.Clock()

    # 2) Build quadtree and prep rectangle candidates
    print("Building quadtree...")
    root = build_quadtree(img)
    leaves = root.leaves()
    print(f"Total leaves: {len(leaves)}")

    # score = (area on screen) * (squared color distance to bg)
    candidates: List[Tuple[pygame.Rect, Tuple[int, int, int], int, int]] = []
    for node in leaves:
        sw = max(1, int(node.w * window_scale))
        sh = max(1, int(node.h * window_scale))
        area = sw * sh
        score = area * rgb_dist2(node.color, bg)
        # jitter center for that "window storm" feel
        sx = int(MARGIN + node.x * window_scale)
        sy = int(MARGIN + node.y * window_scale)
        rect = pygame.Rect(sx-1, sy-1, sw+2, sh+2)
        candidates.append((rect, node.color, area, score))

    # Keep best K by score, then render big → small
    candidates.sort(key=lambda t: t[3], reverse=True)
    if max_rects is not None:
        candidates = candidates[:max_rects]
    candidates.sort(key=lambda t: t[2], reverse=True)

    # Progressive reveal state
    revealed = 0
    playing = True
    start_time = time.time()
    batch_times: List[Tuple[float, int, int]] = []  # (t0, start_idx, end_idx)

    # Reusable alpha layer (avoid realloc per batch)
    alpha_layer = pygame.Surface(window.get_size(), pygame.SRCALPHA)

    # --- Main loop ---
    running = True
    while running:
        _dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_SPACE:
                    playing = not playing
                elif event.key == pygame.K_LEFTBRACKET:
                    rects_per_frame = max(1, rects_per_frame - 10)
                    print(f"Rects/frame: {rects_per_frame}")
                elif event.key == pygame.K_RIGHTBRACKET:
                    rects_per_frame += 10
                    print(f"Rects/frame: {rects_per_frame}")
                elif event.key == pygame.K_f:
                    fade = not fade
                    print(f"Fade: {'on' if fade else 'off'}")
                elif event.key == pygame.K_b:
                    borders = not borders
                    print(f"Borders: {'on' if borders else 'off'}")

        if playing and revealed < len(candidates):
            s = revealed
            revealed = min(len(candidates), revealed + rects_per_frame)
            e = revealed
            if fade:
                batch_times.append((time.time(), s, e))

        # Background first: draw one full rectangle of bg color
        window.fill((0, 0, 0))  # outer margin
        pygame.draw.rect(window, bg, pygame.Rect(MARGIN, MARGIN, W, H))

        # Draw all fully revealed rects (opaque)
        if fade:
            # Find the earliest start idx of any fading batch; everything < that is fully opaque
            fully_opaque_upto = min((bt[1] for bt in batch_times), default=revealed)
            for i in range(fully_opaque_upto):
                rect, color, _, _ = candidates[i]
                pygame.draw.rect(window, color, rect)
                if borders:
                    pygame.draw.rect(window, (0, 0, 0), rect, 1)
        else:
            for i in range(revealed):
                rect, color, _, _ = candidates[i]
                pygame.draw.rect(window, color, rect)
                if borders:
                    pygame.draw.rect(window, (0, 0, 0), rect, 1)

        # Fade currently revealing batches on top (single reused layer)
        if fade and batch_times:
            alpha_layer.fill((0, 0, 0, 0))
            now = time.time()
            finished = []
            for (t0, s, e) in batch_times:
                a = max(0.0, min(1.0, (now - t0) / FADE_DURATION))
                if a >= 1.0:
                    finished.append((t0, s, e))
                    for i in range(s, e):
                        rect, color, _, _ = candidates[i]
                        pygame.draw.rect(window, color, rect)
                        if borders:
                            pygame.draw.rect(window, (0, 0, 0), rect, 1)
                else:
                    a255 = int(a * 255)
                    for i in range(s, e):
                        rect, color, _, _ = candidates[i]
                        r, g, b = color
                        pygame.draw.rect(alpha_layer, (r, g, b, a255), rect)
                        if borders:
                            pygame.draw.rect(alpha_layer, (0, 0, 0, a255), rect, 1)
            # composite once per frame
            window.blit(alpha_layer, (0, 0))
            # drop finished batches
            batch_times = [bt for bt in batch_times if bt not in finished]

        pygame.display.flip()

        # Termination logic
        if auto_close > 0 and (time.time() - start_time) >= auto_close:
            running = False
        if revealed >= len(candidates) and (not fade or not batch_times) and auto_close == 0:
            # fully revealed; pause but keep window visible
            playing = False

    pygame.quit()


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Quadtree tiling with dominant background and best-K rectangle selection"
    )
    ap.add_argument("image", help="Path to image (e.g., obama.jpg)")
    ap.add_argument("--max-rects", type=int, default=None,
                    help="Limit to best K rectangles vs background")
    ap.add_argument("--rects-per-frame", type=int, default=RECTS_PER_FRAME,
                    help="Reveal speed (rectangles per frame)")
    ap.add_argument("--scale", type=float, default=WINDOW_SCALE,
                    help="Window scale relative to image")
    ap.add_argument("--fade", action="store_true", help="Enable fade-in batches")
    ap.add_argument("--no-fade", dest="fade", action="store_false")
    ap.set_defaults(fade=USE_FADE)
    ap.add_argument("--borders", action="store_true", help="Draw a 1px border per rectangle")
    ap.add_argument("--bg-mode", choices=["palette", "mean"], default=BG_MODE,
                    help="How to choose the background color")
    ap.add_argument("--palette-colors", type=int, default=PALETTE_COLORS,
                    help="If bg-mode=palette, number of palette colors")
    ap.add_argument("--auto-close", type=float, default=AUTO_CLOSE_SECONDS,
                    help="Auto close seconds (0=never)")
    args = ap.parse_args()

    run(
        image_path=args.image,
        max_rects=args.max_rects,
        rects_per_frame=args.rects_per_frame,
        window_scale=args.scale,
        fade=args.fade,
        borders=args.borders,
        bg_mode=args.bg_mode,
        palette_colors=args.palette_colors,
        auto_close=args.auto_close,
    )


if __name__ == "__main__":
    main()
