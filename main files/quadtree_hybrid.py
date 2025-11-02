import os, sys, random, ctypes
from ctypes import wintypes
from PIL import Image, ImageStat
import win32con, win32gui, win32api

# -------- SETTINGS (match your Tk version) --------
IMAGE_PATH = "obama.jpg"
TITLE_TEXT = "Program Window"
MARGIN = 80
VARIANCE_THRESHOLD = 20
MIN_WINDOW_SIZE = 20
MAX_DEPTH = 8
JITTER_POS = 0.05
AUTO_CLOSE_SECONDS = 10

# -------- DPI awareness --------
def _make_dpi_aware():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
_make_dpi_aware()

# -------- ctypes WinAPI we use --------
user32 = ctypes.windll.user32
gdi32  = ctypes.windll.gdi32

class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

user32.SetTimer.argtypes        = [wintypes.HWND, wintypes.UINT, wintypes.UINT, ctypes.c_void_p]
user32.KillTimer.argtypes       = [wintypes.HWND, wintypes.UINT]
user32.FillRect.argtypes        = [wintypes.HDC, ctypes.POINTER(RECT), wintypes.HBRUSH]
user32.AdjustWindowRectEx.argtypes = [ctypes.POINTER(RECT), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
gdi32.DeleteObject.argtypes     = [wintypes.HGDIOBJ]

def COLORREF(r,g,b): return (r & 0xFF) | ((g & 0xFF) << 8) | ((b & 0xFF) << 16)

def adjust_window_rect_ex_for_client(w, h, style, exstyle, has_menu=False):
    rc = RECT(0, 0, int(w), int(h))
    if not user32.AdjustWindowRectEx(ctypes.byref(rc), int(style), bool(has_menu), int(exstyle)):
        return int(w), int(h)
    return rc.right - rc.left, rc.bottom - rc.top

# -------- Helper: Find most common color in image --------
def find_most_common_color(img):
    """Find the most common color in the image using quantization"""
    # Reduce to 256 colors for faster processing
    img_quant = img.quantize(colors=256)
    palette = img_quant.getpalette()
    pixels = list(img_quant.getdata())
    
    # Count pixel frequencies
    from collections import Counter
    counts = Counter(pixels)
    most_common_idx = counts.most_common(1)[0][0]
    
    # Get RGB from palette
    r = palette[most_common_idx * 3]
    g = palette[most_common_idx * 3 + 1]
    b = palette[most_common_idx * 3 + 2]
    
    print(f"Most common color: RGB({r}, {g}, {b})")
    return (r, g, b)

def colors_similar(color1, color2, threshold=30):
    """Check if two RGB colors are similar within threshold"""
    r1, g1, b1 = color1
    r2, g2, b2 = color2
    return (abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)) / 3 < threshold

# -------- Quadtree (same logic/order as your Tk code) --------
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
        if ix1 <= ix0 or iy1 <= iy0: return (0,0,0)
        stat = ImageStat.Stat(img.crop((ix0, iy0, ix1, iy1)))
        return (int(stat.mean[0]), int(stat.mean[1]), int(stat.mean[2]))

    def calc_variance(self, img):
        ix0, iy0, ix1, iy1 = self._clamped_box(img)
        if ix1 <= ix0 or iy1 <= iy0: return 0.0
        stat = ImageStat.Stat(img.crop((ix0, iy0, ix1, iy1)))
        return (sum(stat.stddev) / 3.0) if hasattr(stat, "stddev") else 0.0

    def should_split(self):
        return (self.variance > VARIANCE_THRESHOLD and
                min(self.w, self.h) > MIN_WINDOW_SIZE * 2 and
                self.depth < MAX_DEPTH)

    def split(self, img):
        hw, hh = self.w / 2.0, self.h / 2.0
        # TL, TR, BL, BR — matches your code’s order
        self.children = [
            QuadNode(self.x,        self.y,        hw, hh, img, self.depth+1),
            QuadNode(self.x + hw,   self.y,        hw, hh, img, self.depth+1),
            QuadNode(self.x,        self.y + hh,   hw, hh, img, self.depth+1),
            QuadNode(self.x + hw,   self.y + hh,   hw, hh, img, self.depth+1),
        ]

    def get_leaf_nodes(self):
        if not self.children: return [self]
        leaves = []
        for c in self.children: leaves.extend(c.get_leaf_nodes())  # DFS in TL,TR,BL,BR
        return leaves

def build_quadtree(img):
    root = QuadNode(0, 0, img.width, img.height, img)
    queue = [root]  # BFS splitting, same as your script
    while queue:
        node = queue.pop(0)
        if node.should_split():
            node.split(img)
            queue.extend(node.children)
    return root

# -------- Window plumbing --------
WNDCLASS_NAME = "QuadtreeColourTileClassOrdered"
WINDOWS = {}     # hwnd -> {"brush": HBRUSH}
LIVE_WINDOWS = 0
TIMER_ID = 1
AUTO_CLOSE_MS = AUTO_CLOSE_SECONDS * 1000

def wndproc(hwnd, msg, wparam, lparam):
    global LIVE_WINDOWS
    if msg == win32con.WM_CREATE:
        if AUTO_CLOSE_MS > 0:
            user32.SetTimer(hwnd, TIMER_ID, AUTO_CLOSE_MS, None)
        return 0

    if msg == win32con.WM_TIMER and wparam == TIMER_ID:
        user32.KillTimer(hwnd, TIMER_ID)
        win32gui.DestroyWindow(hwnd)
        return 0

    if msg == win32con.WM_KEYDOWN and wparam == win32con.VK_ESCAPE:
        for h in list(WINDOWS.keys()):
            try: win32gui.DestroyWindow(h)
            except: pass
        return 0

    if msg == win32con.WM_PAINT:
        ps = win32gui.BeginPaint(hwnd)
        hdc = ps[0]
        info = WINDOWS.get(hwnd)
        if info:
            l, t, r, b = win32gui.GetClientRect(hwnd)
            rc = RECT(l, t, r, b)
            user32.FillRect(hdc, ctypes.byref(rc), info["brush"])
        win32gui.EndPaint(hwnd, ps[1])
        return 0

    if msg == win32con.WM_DESTROY:
        info = WINDOWS.pop(hwnd, None)
        if info and info.get("brush"):
            gdi32.DeleteObject(info["brush"])
        LIVE_WINDOWS -= 1
        if LIVE_WINDOWS <= 0:
            win32gui.PostQuitMessage(0)
        return 0

    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

def register_window_class():
    wc = win32gui.WNDCLASS()
    wc.hInstance = win32api.GetModuleHandle(None)
    wc.lpszClassName = WNDCLASS_NAME
    wc.style = win32con.CS_HREDRAW | win32con.CS_VREDRAW
    wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
    wc.hbrBackground = win32gui.GetSysColorBrush(win32con.COLOR_WINDOW)  # we paint ourselves
    wc.lpfnWndProc = wndproc
    try:
        win32gui.RegisterClass(wc)
    except win32gui.error:
        pass

def create_colour_window_hidden(x, y, w, h, title, rgb):
    """Create the window HIDDEN; we’ll position+show later to control z-order."""
    global LIVE_WINDOWS
    style  = (win32con.WS_OVERLAPPEDWINDOW & ~win32con.WS_MAXIMIZEBOX & ~win32con.WS_THICKFRAME)
    exstyle = win32con.WS_EX_APPWINDOW

    win_w, win_h = adjust_window_rect_ex_for_client(w, h, style, exstyle, False)
    hwnd = win32gui.CreateWindowEx(
        exstyle, WNDCLASS_NAME, title, style,
        int(x), int(y), int(win_w), int(win_h),
        0, 0, win32api.GetModuleHandle(None), None
    )
    if not hwnd: raise RuntimeError("CreateWindowEx failed")

    r, g, b = rgb
    brush = gdi32.CreateSolidBrush(COLORREF(r, g, b))
    WINDOWS[hwnd] = {"brush": brush, "winrect": (int(x), int(y), int(win_w), int(win_h))}
    LIVE_WINDOWS += 1
    # DO NOT ShowWindow here — we’ll show in the ordered pass
    return hwnd

def main():
    if not os.path.isfile(IMAGE_PATH):
        print(f"File not found: {IMAGE_PATH}")
        sys.exit(1)

    img = Image.open(IMAGE_PATH).convert("RGB")
    img_w, img_h = img.size

    sw = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
    sh = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
    usable_w = max(300, sw - 2 * MARGIN)
    usable_h = max(300, sh - 2 * MARGIN)

    aspect = img_w / img_h
    if usable_w / usable_h > aspect:
        area_h = usable_h
        area_w = int(area_h * aspect)
    else:
        area_w = usable_w
        area_h = int(area_w / aspect)

    area_x0 = (sw - area_w) // 2
    area_y0 = (sh - area_h) // 2

    scale_x = area_w / img_w
    scale_y = area_h / img_h

    # Find most common color for background
    print("Finding most common color...")
    bg_color = find_most_common_color(img)

    print("Building quadtree...")
    root = build_quadtree(img)
    leaves = root.get_leaf_nodes()
    print(f"Total leaf nodes: {len(leaves)}")
    
    # Filter out leaves that match the background color
    filtered_leaves = [node for node in leaves if not colors_similar(node.color, bg_color)]
    print(f"Filtered to {len(filtered_leaves)} windows (skipped {len(leaves) - len(filtered_leaves)} background windows)")
    leaves = filtered_leaves

    register_window_class()

    # Create background window first (full screen area with most common color)
    print(f"Creating background window with color RGB{bg_color}...")
    bg_hwnd = create_colour_window_hidden(area_x0, area_y0, area_w, area_h, "Background", bg_color)

    # First pass: create all windows HIDDEN, store handles in leaf order
    handles = []
    for node in leaves:
        screen_x = area_x0 + node.x * scale_x
        screen_y = area_y0 + node.y * scale_y
        screen_w_node = node.w * scale_x
        screen_h_node = node.h * scale_y

        # jitter like your Tk code
        jx = random.uniform(-JITTER_POS, JITTER_POS) * screen_w_node
        jy = random.uniform(-JITTER_POS, JITTER_POS) * screen_h_node

        pos_x = int(max(0, min(screen_x + jx, sw)))
        pos_y = int(max(0, min(screen_y + jy, sh)))
        win_w = max(MIN_WINDOW_SIZE, int(screen_w_node))
        win_h = max(MIN_WINDOW_SIZE, int(screen_h_node))

        handles.append(
            create_colour_window_hidden(pos_x, pos_y, win_w, win_h, TITLE_TEXT, node.color)
        )

    # Second pass: SHOW in correct z-order (background first, then foreground windows)
    SWP_NOSIZE = 0x0001
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040

    # Show ALL foreground windows first in their correct order
    prev = win32con.HWND_TOP
    for i, hwnd in enumerate(handles):
        x, y, ww, hh = WINDOWS[hwnd]["winrect"]
        win32gui.SetWindowPos(hwnd, prev, x, y, 0, 0,
                              SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        prev = hwnd
    
    # Then show background and push it to the BOTTOM (behind all foreground windows)
    x, y, ww, hh = WINDOWS[bg_hwnd]["winrect"]
    # Use the last foreground window handle to insert background below the entire stack
    win32gui.SetWindowPos(bg_hwnd, win32con.HWND_BOTTOM, x, y, 0, 0,
                          SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)

    print(f"Created {len(handles) + 1} windows total (1 background + {len(handles)} foreground). Esc closes; auto-close in {AUTO_CLOSE_SECONDS}s.")
    win32gui.PumpMessages()

if __name__ == "__main__":
    main()
