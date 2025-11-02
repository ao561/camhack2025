import tkinter as tk
from PIL import Image, ImageStat
import random

# --- SETTINGS ---
IMAGE_PATH = "obama.jpg"
TITLE_TEXT = "Program Window"
MARGIN = 80
VARIANCE_THRESHOLD = 20    # Higher = fewer subdivisions, Lower = more detail
MIN_WINDOW_SIZE = 20     # Minimum window dimension in pixels
MAX_DEPTH = 8            # Maximum subdivision depth
JITTER_POS = 0.05        # Small position jitter for organic look

# --- QUADTREE NODE CLASS ---
class QuadNode:
    def __init__(self, x, y, w, h, img, depth=0):
        self.x = x  # position in image coordinates
        self.y = y
        self.w = w  # size in image coordinates
        self.h = h
        self.depth = depth
        self.children = []
        self.color = self.calc_avg_color(img)
        self.variance = self.calc_variance(img)
    
    def calc_avg_color(self, img):
        """Calculate average color of this region"""
        ix0 = int(max(0, self.x))
        iy0 = int(max(0, self.y))
        ix1 = int(min(img.width, self.x + self.w))
        iy1 = int(min(img.height, self.y + self.h))
        
        if ix1 <= ix0 or iy1 <= iy0:
            return "#000000"
        
        region = img.crop((ix0, iy0, ix1, iy1))
        stat = ImageStat.Stat(region)
        r, g, b = int(stat.mean[0]), int(stat.mean[1]), int(stat.mean[2])
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def calc_variance(self, img):
        """Calculate color variance (standard deviation) of this region"""
        ix0 = int(max(0, self.x))
        iy0 = int(max(0, self.y))
        ix1 = int(min(img.width, self.x + self.w))
        iy1 = int(min(img.height, self.y + self.h))
        
        if ix1 <= ix0 or iy1 <= iy0:
            return 0
        
        region = img.crop((ix0, iy0, ix1, iy1))
        stat = ImageStat.Stat(region)
        # Average the stddev across RGB channels
        variance = sum(stat.stddev) / 3 if hasattr(stat, 'stddev') else 0
        return variance
    
    def should_split(self):
        """Determine if this node should be split"""
        return (self.variance > VARIANCE_THRESHOLD and 
                min(self.w, self.h) > MIN_WINDOW_SIZE * 2 and
                self.depth < MAX_DEPTH)
    
    def split(self, img):
        """Split this node into 4 children (quadrants)"""
        hw = self.w / 2
        hh = self.h / 2
        
        self.children = [
            QuadNode(self.x, self.y, hw, hh, img, self.depth + 1),           # Top-left
            QuadNode(self.x + hw, self.y, hw, hh, img, self.depth + 1),      # Top-right
            QuadNode(self.x, self.y + hh, hw, hh, img, self.depth + 1),      # Bottom-left
            QuadNode(self.x + hw, self.y + hh, hw, hh, img, self.depth + 1)  # Bottom-right
        ]
    
    def get_leaf_nodes(self):
        """Get all leaf nodes (nodes without children) - these become windows"""
        if not self.children:
            return [self]
        
        leaves = []
        for child in self.children:
            leaves.extend(child.get_leaf_nodes())
        return leaves

def build_quadtree(img):
    """Build quadtree by recursively splitting high-variance regions"""
    root = QuadNode(0, 0, img.width, img.height, img)
    
    # Queue for breadth-first splitting
    queue = [root]
    
    while queue:
        node = queue.pop(0)
        if node.should_split():
            node.split(img)
            queue.extend(node.children)
    
    return root

# --- LOAD IMAGE ---
img = Image.open(IMAGE_PATH).convert("RGB")
img_w, img_h = img.size

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
root.bind_all("<q>", close_all)
root.bind_all("<Q>", close_all)

# --- SCREEN/AREA SETUP ---
screen_w = root.winfo_screenwidth()
screen_h = root.winfo_screenheight()

usable_w = max(300, screen_w - 2 * MARGIN)
usable_h = max(300, screen_h - 2 * MARGIN)

# Fit area to image aspect ratio
aspect = img_w / img_h
if usable_w / usable_h > aspect:
    area_h = usable_h
    area_w = int(area_h * aspect)
else:
    area_w = usable_w
    area_h = int(area_w / aspect)

area_x0 = (screen_w - area_w) // 2
area_y0 = (screen_h - area_h) // 2

# Scale factors from image coordinates to screen coordinates
scale_x = area_w / img_w
scale_y = area_h / img_h

# --- BUILD QUADTREE ---
print("Building quadtree...")
quadtree_root = build_quadtree(img)
leaf_nodes = quadtree_root.get_leaf_nodes()
print(f"Created {len(leaf_nodes)} windows (leaf nodes)")

# --- CREATE WINDOWS FROM LEAF NODES ---
for node in leaf_nodes:
    # Convert image coordinates to screen coordinates
    screen_x = area_x0 + node.x * scale_x
    screen_y = area_y0 + node.y * scale_y
    screen_w_node = node.w * scale_x
    screen_h_node = node.h * scale_y
    
    # Add small random jitter for organic look
    jx = random.uniform(-JITTER_POS, JITTER_POS) * screen_w_node
    jy = random.uniform(-JITTER_POS, JITTER_POS) * screen_h_node
    
    pos_x = int(screen_x + jx)
    pos_y = int(screen_y + jy)
    win_w = max(MIN_WINDOW_SIZE, int(screen_w_node))
    win_h = max(MIN_WINDOW_SIZE, int(screen_h_node))
    
    # Keep within screen bounds
    pos_x = max(0, min(pos_x, screen_w - win_w))
    pos_y = max(0, min(pos_y, screen_h - win_h))
    
    w = tk.Toplevel()
    w.title(TITLE_TEXT)
    w.protocol("WM_DELETE_WINDOW", close_all)
    w.configure(bg=node.color)
    w.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
    
    windows.append(w)

print(f"All {len(windows)} windows created!")
print("Press 'q' or 'Escape' to close all windows")

root.mainloop()
