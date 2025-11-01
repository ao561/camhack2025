# epic_renderer.py
# Usage:
#   python epic_renderer.py path/to/image.jpg --max-windows 70
#   python epic_renderer.py path/to/image.jpg --tile 64 --seconds 15 --topmost
#
# Defaults:
#   TILE_SIZE = 96 px
#   AUTO_CLOSE_SECONDS = 10 s

import sys, os, math, ctypes, argparse
from ctypes import wintypes
from PIL import Image
import win32con, win32gui, win32api

# --------- Tweakable defaults ----------
TILE_SIZE = 96
AUTO_CLOSE_SECONDS = 10

# --------- DPI awareness ----------
def _make_dpi_aware():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
_make_dpi_aware()

# --------- Globals ----------
WINDOWS = {}  # hwnd -> {"brush": HBRUSH}
LIVE_WINDOWS = 0
TIMER_ID = 1
AUTO_CLOSE_MS = AUTO_CLOSE_SECONDS * 1000
WNDCLASS_NAME = "MonoTileWinClass"

# --------- WinAPI via ctypes ----------
user32 = ctypes.windll.user32
gdi32  = ctypes.windll.gdi32

class RECT(ctypes.Structure):
    _fields_ = [("left",   wintypes.LONG),
                ("top",    wintypes.LONG),
                ("right",  wintypes.LONG),
                ("bottom", wintypes.LONG)]

# Prototypes we use
user32.SetTimer.argtypes   = [wintypes.HWND, wintypes.UINT, wintypes.UINT, ctypes.c_void_p]
user32.KillTimer.argtypes  = [wintypes.HWND, wintypes.UINT]
user32.AdjustWindowRectEx.argtypes = [ctypes.POINTER(RECT), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.FillRect.argtypes   = [wintypes.HDC, ctypes.POINTER(RECT), wintypes.HBRUSH]
gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]

def colorref(r, g, b):
    # Win32 COLORREF = 0x00BBGGRR (macro RGB packs as r | g<<8 | b<<16)
    return (r & 0xFF) | ((g & 0xFF) << 8) | ((b & 0xFF) << 16)

def adjust_window_rect_ex_for_client(w, h, style, exstyle, has_menu=False):
    rc = RECT(0, 0, int(w), int(h))
    if not user32.AdjustWindowRectEx(ctypes.byref(rc), int(style), bool(has_menu), int(exstyle)):
        return int(w), int(h)
    return rc.right - rc.left, rc.bottom - rc.top

def center_origin(img_w, img_h):
    sw = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
    sh = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
    return max(0, (sw - img_w) // 2), max(0, (sh - img_h) // 2)

def determine_tile_size(img_w, img_h, tile_arg, max_windows):
    if tile_arg and tile_arg > 0:
        return max(1, int(tile_arg))

    if max_windows and max_windows > 0:
        area = max(1, img_w * img_h)
        tile = int(math.sqrt(area / max_windows))
        tile = max(1, tile)
        # Do not exceed the larger dimension; ensures at least one tile in each axis.
        tile = min(tile, max(img_w, img_h))
        return tile

    return TILE_SIZE

# --------- Window proc ----------
def wndproc(hwnd, msg, wparam, lparam):
    global LIVE_WINDOWS
    if msg == win32con.WM_CREATE:
        user32.SetTimer(hwnd, TIMER_ID, AUTO_CLOSE_MS, None)
        return 0

    if msg == win32con.WM_TIMER and wparam == TIMER_ID:
        user32.KillTimer(hwnd, TIMER_ID)
        win32gui.DestroyWindow(hwnd)
        return 0

    if msg == win32con.WM_KEYDOWN and wparam == win32con.VK_ESCAPE:
        win32gui.DestroyWindow(hwnd)
        return 0

    if msg == win32con.WM_PAINT:
        ps = win32gui.BeginPaint(hwnd)
        hdc = ps[0]
        # fill client area with our solid brush
        info = WINDOWS.get(hwnd)
        if info:
            # get client rect
            l, t, r, b = win32gui.GetClientRect(hwnd)
            rc = RECT(l, t, r, b)
            user32.FillRect(hdc, ctypes.byref(rc), info["brush"])
        win32gui.EndPaint(hwnd, ps[1])
        return 0

    if msg == win32con.WM_DESTROY:
        # clean brush
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
    wc.hbrBackground = win32gui.GetSysColorBrush(win32con.COLOR_WINDOW)  # placeholder; we paint ourselves
    wc.lpfnWndProc = wndproc
    try:
        win32gui.RegisterClass(wc)
    except win32gui.error:
        pass  # already registered

def create_colour_window(x, y, w, h, title, rgb, topmost=False):
    global LIVE_WINDOWS
    style = win32con.WS_POPUP
    exstyle = win32con.WS_EX_APPWINDOW | (win32con.WS_EX_TOPMOST if topmost else 0)

    win_w, win_h = adjust_window_rect_ex_for_client(w, h, style, exstyle, has_menu=False)

    hwnd = win32gui.CreateWindowEx(
        exstyle, WNDCLASS_NAME, title, style,
        int(x), int(y), int(win_w), int(win_h),
        0, 0, win32api.GetModuleHandle(None), None
    )
    if not hwnd:
        raise RuntimeError("CreateWindowEx failed")

    # make the solid brush for this window
    r, g, b = rgb
    brush = gdi32.CreateSolidBrush(colorref(r, g, b))

    WINDOWS[hwnd] = {"brush": brush}

    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
    win32gui.UpdateWindow(hwnd)

    LIVE_WINDOWS += 1
    return hwnd

# --------- Main tiling ----------
def render_image_as_colour_windows(image_path, tile_override=None, max_windows=None, seconds=AUTO_CLOSE_SECONDS, topmost=False):
    global AUTO_CLOSE_MS, LIVE_WINDOWS
    AUTO_CLOSE_MS = max(1, int(max(seconds, 0.01) * 1000))
    LIVE_WINDOWS = 0
    WINDOWS.clear()

    img = Image.open(image_path).convert("RGB")
    img_w, img_h = img.size

    tile_size = determine_tile_size(img_w, img_h, tile_override, max_windows)

    tiles_x = math.ceil(img_w / tile_size)
    tiles_y = math.ceil(img_h / tile_size)
    pad_w, pad_h = tiles_x * tile_size, tiles_y * tile_size
    if (pad_w, pad_h) != (img_w, img_h):
        padded = Image.new("RGB", (pad_w, pad_h), (0, 0, 0))
        padded.paste(img, (0, 0))
        img = padded
        img_w, img_h = img.size

    total_windows = tiles_x * tiles_y
    print(f"Spawning {total_windows} windows ({tiles_x}x{tiles_y}) at {tile_size}px tiles.")

    origin_x, origin_y = center_origin(img_w, img_h)

    for ty in range(tiles_y):
        for tx in range(tiles_x):
            x0, y0 = tx * tile_size, ty * tile_size
            tile = img.crop((x0, y0, x0 + tile_size, y0 + tile_size))

            # single colour: average via 1x1 downscale (fast & nice)
            avg_rgb = tile.resize((1, 1), Image.BOX).getpixel((0, 0))

            create_colour_window(
                origin_x + x0, origin_y + y0,
                tile_size, tile_size,
                f"tile ({tx},{ty})",
                avg_rgb,
                topmost=topmost
            )

def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Render an image as many coloured windows by tiling it across multiple HWNDs."
    )
    parser.add_argument("image", help="Path to the image file to render.")
    parser.add_argument(
        "--tile",
        type=int,
        help="Explicit tile size in pixels. Overrides --max-windows if both are provided.",
    )
    parser.add_argument(
        "--max-windows",
        type=int,
        help="Approximate maximum number of windows to spawn by adjusting tile size.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=AUTO_CLOSE_SECONDS,
        help="Seconds before each window auto-closes (default: %(default)s).",
    )
    parser.add_argument(
        "--topmost",
        action="store_true",
        help="Keep the spawned windows above other applications.",
    )
    return parser.parse_args(argv)

def main(argv=None):
    args = parse_args(argv or sys.argv[1:])

    if not os.path.isfile(args.image):
        print(f"File not found: {args.image}")
        sys.exit(1)

    register_window_class()
    render_image_as_colour_windows(
        args.image,
        tile_override=args.tile,
        max_windows=args.max_windows,
        seconds=args.seconds,
        topmost=args.topmost,
    )
    win32gui.PumpMessages()

if __name__ == "__main__":
    main()
