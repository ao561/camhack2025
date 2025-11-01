import tkinter as tk
from PIL import Image, ImageStat
import random
import math

# --- SETTINGS ---
IMAGE_PATH = "obama.jpg"
MAX_WINDOWS = 30            # target number of windows
TITLE_TEXT = "Program Window"  # title bar text
MARGIN = 80                    # screen margin for the mosaic area
OVERLAP_FACTOR = 0.25          # windows are bigger than their cell by this fraction
SIZE_VARIANCE = 0.25           # +/- % variance of window size
JITTER_POS = 0.10              # position jitter as a fraction of cell size

# --- LOAD IMAGE ---
img = Image.open(IMAGE_PATH).convert("RGB")
img_w, img_h = img.size
aspect = img_w / img_h

root = tk.Tk()
root.withdraw()
windows = []

def close_all(event=None):
    for w in windows:
        try:
            w.destroy()
        except:
            pass
    root.quit()

root.bind_all("<Escape>", close_all)

# --- SCREEN/AREA SETUP ---
screen_w = root.winfo_screenwidth()
screen_h = root.winfo_screenheight()

usable_w = max(300, screen_w - 2 * MARGIN)
usable_h = max(300, screen_h - 2 * MARGIN)

# fit area to the image aspect ratio
if usable_w / usable_h > aspect:
    area_h = usable_h
    area_w = int(area_h * aspect)
else:
    area_w = usable_w
    area_h = int(area_w / aspect)

area_x0 = (screen_w - area_w) // 2
area_y0 = (screen_h - area_h) // 2

# --- CHOOSE GRID close to MAX_WINDOWS while respecting aspect ---
# cols/rows chosen to match aspect and be <= MAX_WINDOWS
cols = max(1, int(round(math.sqrt(MAX_WINDOWS * aspect))))
rows = max(1, int(round(MAX_WINDOWS / cols)))
# clamp to not exceed MAX_WINDOWS
while cols * rows > MAX_WINDOWS:
    if cols >= rows:
        cols -= 1
    else:
        rows -= 1
while cols * rows < MAX_WINDOWS:  # try to reach MAX_WINDOWS if underfilled
    if (cols + 1) * rows <= MAX_WINDOWS and (cols + 1) / rows <= 2 * aspect:
        cols += 1
    elif cols * (rows + 1) <= MAX_WINDOWS:
        rows += 1
    else:
        break

cell_w = area_w / cols
cell_h = area_h / rows

# helper to get average color of an image region (in image coords)
def avg_color(ix0, iy0, ix1, iy1):
    # clamp and ensure non-empty
    ix0, iy0 = int(max(0, min(ix0, img_w - 1))), int(max(0, min(iy0, img_h - 1)))
    ix1, iy1 = int(max(ix0 + 1, min(ix1, img_w))), int(max(iy0 + 1, min(iy1, img_h)))
    region = img.crop((ix0, iy0, ix1, iy1))
    stat = ImageStat.Stat(region)
    r, g, b = (int(stat.mean[0]), int(stat.mean[1]), int(stat.mean[2]))
    return f"#{r:02x}{g:02x}{b:02x}"

# --- CREATE WINDOWS, each mapped to a specific cell ---
for row in range(rows):
    for col in range(cols):
        # Map this cell to image coordinates for correct color sampling
        ix0 = int(col / cols * img_w)
        ix1 = int((col + 1) / cols * img_w)
        iy0 = int(row / rows * img_h)
        iy1 = int((row + 1) / rows * img_h)
        color = avg_color(ix0, iy0, ix1, iy1)

        # Base cell position on screen
        base_x = area_x0 + col * cell_w
        base_y = area_y0 + row * cell_h

        # Window size: base = cell size, scaled up for overlap, plus variance
        sx = cell_w * (1.0 + OVERLAP_FACTOR)
        sy = cell_h * (1.0 + OVERLAP_FACTOR)
        s_scale = 1.0 + random.uniform(-SIZE_VARIANCE, SIZE_VARIANCE)
        win_w = max(80, int(sx * s_scale))
        win_h = max(80, int(sy * s_scale))

        # Position jitter, but keep roughly aligned so the image reads correctly
        jx = random.uniform(-JITTER_POS, JITTER_POS) * cell_w
        jy = random.uniform(-JITTER_POS, JITTER_POS) * cell_h

        # Position window so its top-left is near the cell top-left (so gaps are covered by overlap)
        pos_x = int(base_x + jx)
        pos_y = int(base_y + jy)

        # Keep within screen bounds
        pos_x = max(0, min(pos_x, screen_w - win_w))
        pos_y = max(0, min(pos_y, screen_h - win_h))

        w = tk.Toplevel()
        w.title("Program Window")  # title bar → close options at top
        w.protocol("WM_DELETE_WINDOW", close_all)
        w.configure(bg=color)
        w.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")

        windows.append(w)

        if len(windows) >= MAX_WINDOWS:
            break
    if len(windows) >= MAX_WINDOWS:
        break

root.mainloop()
