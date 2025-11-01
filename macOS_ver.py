#!/usr/bin/env python3
"""
Cross-platform quadtree display with progressive reveal (pygame).

Keys:
  SPACE  : pause / play
  [ and ]: decrease / increase rects-per-frame
  F      : toggle fade-in for new batches
  ESC/Q  : quit
"""

import os, sys, random, time
import pygame
from PIL import Image, ImageStat

# -------- SETTINGS --------
IMAGE_PATH = "obama.jpg"
TITLE_TEXT = "Quadtree Display"
MARGIN = 80
VARIANCE_THRESHOLD = 20
MIN_WINDOW_SIZE = 20
MAX_DEPTH = 8
JITTER_POS = 0.05
WINDOW_SCALE = 1.0
AUTO_CLOSE_SECONDS = 0      # 0 disables
RECTS_PER_FRAME = 5        # how many rectangles to reveal each frame
USE_FADE = True             # fade-in each batch?
FADE_DURATION = 0.20        # seconds to fade a batch

# -------- Quadtree logic --------
class QuadNode:
    def __init__(self, x, y, w, h, img, depth=0):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.depth = depth
        self.children = []
        self.color = self.calc_avg_color(img)
        self.variance = self.calc_variance(img)

    def _clamped_box(self, img):
        ix0 = int(max(0, self.x)); iy0 = int(max(0, self.y))
        ix1 = int(min(img.width,  self.x + self.w))
        iy1 = int(min(img.height, self.y + self.h))
        return ix0, iy0, ix1, iy1

    def calc_avg_color(self, img):
        ix0, iy0, ix1, iy1 = self._clamped_box(img)
        if ix1 <= ix0 or iy1 <= iy0:
            return (0,0,0)
        stat = ImageStat.Stat(img.crop((ix0, iy0, ix1, iy1)))
        return (int(stat.mean[0]), int(stat.mean[1]), int(stat.mean[2]))

    def calc_variance(self, img):
        ix0, iy0, ix1, iy1 = self._clamped_box(img)
        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0
        stat = ImageStat.Stat(img.crop((ix0, iy0, ix1, iy1)))
        return sum(stat.stddev) / 3.0 if hasattr(stat, "stddev") else 0.0

    def should_split(self):
        return (self.variance > VARIANCE_THRESHOLD and
                min(self.w, self.h) > MIN_WINDOW_SIZE * 2 and
                self.depth < MAX_DEPTH)

    def split(self, img):
        hw, hh = self.w / 2.0, self.h / 2.0
        self.children = [
            QuadNode(self.x,        self.y,        hw, hh, img, self.depth+1),
            QuadNode(self.x + hw,   self.y,        hw, hh, img, self.depth+1),
            QuadNode(self.x,        self.y + hh,   hw, hh, img, self.depth+1),
            QuadNode(self.x + hw,   self.y + hh,   hw, hh, img, self.depth+1),
        ]

    def get_leaf_nodes(self):
        if not self.children:
            return [self]
        leaves = []
        for c in self.children:
            leaves.extend(c.get_leaf_nodes())
        return leaves

def build_quadtree(img):
    root = QuadNode(0, 0, img.width, img.height, img)
    queue = [root]  # BFS, matches your original approach
    while queue:
        node = queue.pop(0)
        if node.should_split():
            node.split(img)
            queue.extend(node.children)
    return root

# -------- Display using pygame --------
def main():
    global RECTS_PER_FRAME, USE_FADE
    if not os.path.isfile(IMAGE_PATH):
        print(f"File not found: {IMAGE_PATH}")
        sys.exit(1)

    img = Image.open(IMAGE_PATH).convert("RGB")
    img_w, img_h = img.size

    # Window size with margins
    screen_w = int(img_w * WINDOW_SCALE)
    screen_h = int(img_h * WINDOW_SCALE)

    pygame.init()
    window = pygame.display.set_mode((screen_w + MARGIN * 2, screen_h + MARGIN * 2))
    pygame.display.set_caption(TITLE_TEXT)
    clock = pygame.time.Clock()

    print("Building quadtree...")
    root = build_quadtree(img)
    leaves = root.get_leaf_nodes()
    print(f"Leaf count: {len(leaves)}")

    # Precompute rects (with jitter) so reveal loop is cheap
    prepped = []
    for node in leaves:
        sx = node.x * WINDOW_SCALE
        sy = node.y * WINDOW_SCALE
        sw = max(1, int(node.w * WINDOW_SCALE))
        sh = max(1, int(node.h * WINDOW_SCALE))
        jx = random.uniform(-JITTER_POS, JITTER_POS) * sw
        jy = random.uniform(-JITTER_POS, JITTER_POS) * sh
        rect = pygame.Rect(
            int(MARGIN + sx + jx),
            int(MARGIN + sy + jy),
            sw, sh
        )
        prepped.append((rect, node.color))

    # Progressive reveal state
    revealed = 0
    playing = True
    start_time = time.time()
    batch_times = []  # (start_time, start_index, end_index) for fade tracking

    # Main loop
    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        # events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_SPACE:
                    playing = not playing
                elif event.key == pygame.K_LEFTBRACKET:   # [
                    RECTS_PER_FRAME = max(1, RECTS_PER_FRAME - 10)
                    print(f"Rects/frame: {RECTS_PER_FRAME}")
                elif event.key == pygame.K_RIGHTBRACKET:  # ]
                    RECTS_PER_FRAME += 10
                    print(f"Rects/frame: {RECTS_PER_FRAME}")
                elif event.key == pygame.K_f:
                    USE_FADE = not USE_FADE
                    print(f"Fade-in: {'on' if USE_FADE else 'off'}")

        # reveal logic
        if playing and revealed < len(prepped):
            start_idx = revealed
            revealed = min(len(prepped), revealed + RECTS_PER_FRAME)
            end_idx = revealed
            if USE_FADE:
                batch_times.append((time.time(), start_idx, end_idx))

        # draw background
        window.fill((0, 0, 0))

        # draw all fully revealed rects (before current fading batches)
        if USE_FADE:
            # draw rects before the first fading batch fully opaque
            fully_opaque_upto = min([bt[1] for bt in batch_times], default=revealed)
            for i in range(fully_opaque_upto):
                rect, color = prepped[i]
                pygame.draw.rect(window, color, rect)
        else:
            # no fade: draw all revealed
            for i in range(revealed):
                rect, color = prepped[i]
                pygame.draw.rect(window, color, rect)

        # draw fading batches on top
        if USE_FADE:
            now = time.time()
            finished = []
            for (t0, s, e) in batch_times:
                t = (now - t0) / FADE_DURATION
                alpha = max(0.0, min(1.0, t))
                if alpha >= 1.0:
                    # this batch is done; mark to remove
                    finished.append((t0, s, e))
                    # draw them fully now
                    for i in range(s, e):
                        rect, color = prepped[i]
                        pygame.draw.rect(window, color, rect)
                else:
                    # draw with alpha using a per-batch surface
                    fade_surface = pygame.Surface(window.get_size(), pygame.SRCALPHA)
                    for i in range(s, e):
                        rect, color = prepped[i]
                        r, g, b = color
                        pygame.draw.rect(fade_surface, (r, g, b, int(alpha * 255)), rect)
                    window.blit(fade_surface, (0, 0))
            # clear finished batches
            batch_times = [bt for bt in batch_times if bt not in finished]

        pygame.display.flip()

        # auto-close
        if AUTO_CLOSE_SECONDS > 0 and (time.time() - start_time) >= AUTO_CLOSE_SECONDS:
            running = False

        # stop when fully revealed and no fades active
        if revealed >= len(prepped) and (not USE_FADE or not batch_times) and AUTO_CLOSE_SECONDS == 0:
            # keep window open; pause animation
            playing = False

    pygame.quit()

if __name__ == "__main__":
    main()
