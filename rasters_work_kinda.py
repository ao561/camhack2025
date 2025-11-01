import os
import sys
import time
import random
import ctypes
from ctypes import wintypes
from collections import deque
from typing import Iterable, Sequence

from PIL import Image, ImageStat
import win32con
import win32gui
import win32api

# -------- SETTINGS --------
DEFAULT_IMAGES: Sequence[str] = ("obama.jpg", "rick.jpg")
TITLE_TEXT = "Program Window"
MARGIN = 80

# Raster grid (like a tiled framebuffer)
RASTER_COLUMNS = 20
RASTER_ROWS = 20
RASTER_COUNT = 2            # double buffer: 2 rasters total
JITTER_POS = 0.05           # small position jitter
MIN_CLIENT_SIZE = 20        # minimum client area for each tile window

# Flipping / run control
DISPLAY_DURATION_SECONDS = 3      # how long each image stays before flipping
RUN_LIMIT_SECONDS = 20            # total run time cap (0 = unlimited)

# Visibility/stacking behavior
USE_TOPMOST = False               # True -> force rasters above everything
MAX_VISIBLE_RASTERS = 3           # keep at most this many rasters visible; hide oldest when exceeded
NEVER_MINIMIZE = True             # ALWAYS keep this True (we only hide/show)

# Auto-destroy per window (0 disables; recommended 0 if you keep stacked rasters visible)
AUTO_CLOSE_SECONDS = 0
AUTO_CLOSE_MS = int(max(0, AUTO_CLOSE_SECONDS) * 1000)

RASTER_SIZE = RASTER_COLUMNS * RASTER_ROWS
TOTAL_WINDOWS = RASTER_COUNT * RASTER_SIZE

# -------- DPI awareness --------
def _make_dpi_aware() -> None:
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
gdi32 = ctypes.windll.gdi32

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]

user32.SetTimer.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.UINT, ctypes.c_void_p]
user32.KillTimer.argtypes = [wintypes.HWND, wintypes.UINT]
user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), wintypes.HBRUSH]
user32.AdjustWindowRectEx.argtypes = [
    ctypes.POINTER(RECT),
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD,
]
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]
user32.PeekMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]

def COLORREF(r: int, g: int, b: int) -> int:
    # Win32 COLORREF: 0x00BBGGRR
    return (r & 0xFF) | ((g & 0xFF) << 8) | ((b & 0xFF) << 16)

def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))

def adjust_window_rect_ex_for_client(
    w: int, h: int, style: int, exstyle: int, has_menu: bool = False
) -> tuple[int, int, int, int]:
    rect = RECT(0, 0, int(w), int(h))
    if not user32.AdjustWindowRectEx(ctypes.byref(rect), style, bool(has_menu), exstyle):
        return int(w), int(h), 0, 0
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return int(width), int(height), int(rect.left), int(rect.top)

def calc_avg_color(img: Image.Image, x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int]:
    ix0 = int(max(0, min(img.width, x0)))
    iy0 = int(max(0, min(img.height, y0)))
    ix1 = int(max(0, min(img.width, x1)))
    iy1 = int(max(0, min(img.height, y1)))
    if ix1 <= ix0 or iy1 <= iy0:
        return (0, 0, 0)
    region = img.crop((ix0, iy0, ix1, iy1))
    stat = ImageStat.Stat(region)
    return (int(stat.mean[0]), int(stat.mean[1]), int(stat.mean[2]))

# -------- Window bookkeeping --------
WNDCLASS_NAME = "RasterTileWindows_NeverMinimize"
WINDOWS: dict[int, dict[str, object]] = {}
LIVE_WINDOWS = 0
TIMER_ID = 1

def wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
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
        # Close everything fast
        for h in list(WINDOWS.keys()):
            try:
                win32gui.DestroyWindow(h)
            except:
                pass
        return 0

    if msg == win32con.WM_PAINT:
        ps = win32gui.BeginPaint(hwnd)
        hdc = ps[0]
        info = WINDOWS.get(hwnd)
        if info:
            l, t, r, b = win32gui.GetClientRect(hwnd)
            rect = RECT(l, t, r, b)
            user32.FillRect(hdc, ctypes.byref(rect), info["brush"])
        win32gui.EndPaint(hwnd, ps[1])
        return 0

    if msg == win32con.WM_DESTROY:
        info = WINDOWS.pop(hwnd, None)
        if info:
            brush = info.get("brush")
            if brush:
                gdi32.DeleteObject(brush)
        LIVE_WINDOWS -= 1
        if LIVE_WINDOWS <= 0:
            win32gui.PostQuitMessage(0)
        return 0

    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

def register_window_class() -> None:
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

def create_colour_window_hidden(
    client_x: int, client_y: int, client_w: int, client_h: int, title: str, rgb: tuple[int, int, int]
) -> int:
    global LIVE_WINDOWS
    style = win32con.WS_OVERLAPPEDWINDOW & ~win32con.WS_MAXIMIZEBOX & ~win32con.WS_THICKFRAME
    exstyle = win32con.WS_EX_APPWINDOW  # you can add WS_EX_NOACTIVATE if you want zero focus changes

    win_w, win_h, frame_left, frame_top = adjust_window_rect_ex_for_client(client_w, client_h, style, exstyle, False)
    win_x = int(client_x + frame_left)
    win_y = int(client_y + frame_top)

    hwnd = win32gui.CreateWindowEx(
        exstyle,
        WNDCLASS_NAME,
        title,
        style,
        win_x,
        win_y,
        int(win_w),
        int(win_h),
        0,
        0,
        win32api.GetModuleHandle(None),
        None,
    )
    if not hwnd:
        raise RuntimeError("CreateWindowEx failed")

    r, g, b = rgb
    brush = gdi32.CreateSolidBrush(COLORREF(r, g, b))
    WINDOWS[hwnd] = {
        "brush": brush,
        "style": style,
        "exstyle": exstyle,
        "frame_offset": (frame_left, frame_top),
        "winrect": (win_x, win_y, int(win_w), int(win_h)),
    }
    LIVE_WINDOWS += 1

    # Keep hidden during pool/prepare (NEVER minimize)
    win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
    return hwnd

# ---- helpers for visibility / movement (NEVER minimize) ----
def hide_window(hwnd: int) -> None:
    win32gui.ShowWindow(hwnd, win32con.SW_HIDE)

def set_window_brush(hwnd: int, rgb: tuple[int, int, int]) -> None:
    info = WINDOWS.get(hwnd)
    if not info:
        return
    old_brush = info.get("brush")
    if old_brush:
        gdi32.DeleteObject(old_brush)
    r, g, b = rgb
    info["brush"] = gdi32.CreateSolidBrush(COLORREF(r, g, b))
    user32.InvalidateRect(hwnd, None, True)

def update_window_geometry(hwnd: int, client_x: int, client_y: int, client_w: int, client_h: int) -> None:
    info = WINDOWS.get(hwnd)
    if not info:
        return
    style = int(info["style"])
    exstyle = int(info["exstyle"])
    win_w, win_h, frame_left, frame_top = adjust_window_rect_ex_for_client(client_w, client_h, style, exstyle, False)
    win_x = int(client_x + frame_left)
    win_y = int(client_y + frame_top)
    info["frame_offset"] = (frame_left, frame_top)
    info["winrect"] = (win_x, win_y, int(win_w), int(win_h))

    # Update bounds *without* changing z-order and without activating
    SWP_NOACTIVATE = 0x0010
    SWP_NOZORDER = 0x0004
    win32gui.SetWindowPos(hwnd, 0, win_x, win_y, int(win_w), int(win_h), SWP_NOACTIVATE | SWP_NOZORDER)

def show_window_front(hwnd: int) -> None:
    # Show + bring to front/top (no activation)
    info = WINDOWS.get(hwnd)
    if not info:
        return
    x, y, w, h = info["winrect"]
    SWP_NOSIZE = 0x0001
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    insert_after = win32con.HWND_TOPMOST if USE_TOPMOST else win32con.HWND_TOP
    win32gui.SetWindowPos(hwnd, insert_after, x, y, int(w), int(h), SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
    if AUTO_CLOSE_MS > 0:
        user32.KillTimer(hwnd, TIMER_ID)
        user32.SetTimer(hwnd, TIMER_ID, AUTO_CLOSE_MS, None)
    win32gui.UpdateWindow(hwnd)

# ---- pool / raster operations ----
def create_window_pool(total: int) -> list[int]:
    handles: list[int] = []
    for _ in range(total):
        hwnd = create_colour_window_hidden(0, 0, MIN_CLIENT_SIZE, MIN_CLIENT_SIZE, TITLE_TEXT, (0, 0, 0))
        hide_window(hwnd)
        handles.append(hwnd)
    return handles

def build_raster_cells(img: Image.Image, screen_w: int, screen_h: int) -> list[dict[str, object]]:
    img_w, img_h = img.size
    usable_w = max(300, screen_w - 2 * MARGIN)
    usable_h = max(300, screen_h - 2 * MARGIN)

    aspect = img_w / img_h
    if usable_w / usable_h > aspect:
        area_h = usable_h
        area_w = int(area_h * aspect)
    else:
        area_w = usable_w
        area_h = int(area_w / aspect)

    area_x0 = (screen_w - area_w) // 2
    area_y0 = (screen_h - area_h) // 2

    scale_x = area_w / img_w
    scale_y = area_h / img_h

    cell_img_w = img_w / RASTER_COLUMNS
    cell_img_h = img_h / RASTER_ROWS

    cells: list[dict[str, object]] = []
    for row in range(RASTER_ROWS):
        for column in range(RASTER_COLUMNS):
            img_x0 = column * cell_img_w
            img_y0 = row * cell_img_h
            img_x1 = (column + 1) * cell_img_w
            img_y1 = (row + 1) * cell_img_h

            color = calc_avg_color(img, img_x0, img_y0, img_x1, img_y1)

            screen_x = area_x0 + img_x0 * scale_x
            screen_y = area_y0 + img_y0 * scale_y
            client_w = max(MIN_CLIENT_SIZE, int(cell_img_w * scale_x))
            client_h = max(MIN_CLIENT_SIZE, int(cell_img_h * scale_y))

            jx = random.uniform(-JITTER_POS, JITTER_POS) * client_w
            jy = random.uniform(-JITTER_POS, JITTER_POS) * client_h

            pos_x = int(clamp(screen_x + jx, 0, max(0, screen_w - client_w)))
            pos_y = int(clamp(screen_y + jy, 0, max(0, screen_h - client_h)))

            cells.append(
                {
                    "x": pos_x,
                    "y": pos_y,
                    "w": client_w,
                    "h": client_h,
                    "color": color,
                }
            )
    return cells

def load_raster_cells(image_path: str, screen_w: int, screen_h: int) -> list[dict[str, object]]:
    with Image.open(image_path) as source:
        img = source.convert("RGB")
        return build_raster_cells(img, screen_w, screen_h)

def prepare_raster(handles: Iterable[int], cells: list[dict[str, object]]) -> None:
    # Prepare fully hidden (like drawing to a back buffer)
    for hwnd, cell in zip(handles, cells):
        update_window_geometry(hwnd, cell["x"], cell["y"], cell["w"], cell["h"])
        set_window_brush(hwnd, cell["color"])
        hide_window(hwnd)  # NEVER minimize

def display_raster(handles: Iterable[int]) -> None:
    # Flip: show all tiles in this raster in a consistent z-chain, on top of current stack
    SWP_NOSIZE = 0x0001
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    insert_after = win32con.HWND_TOPMOST if USE_TOPMOST else win32con.HWND_TOP

    prev = 0
    for hwnd in handles:
        info = WINDOWS.get(hwnd)
        if not info:
            continue
        x, y, w, h = info["winrect"]
        # Start above current desktop stack, then chain within this raster
        if prev == 0:
            win32gui.SetWindowPos(hwnd, insert_after, x, y, int(w), int(h),
                                  SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        else:
            # Place directly above the previous tile in this raster for stable ordering
            win32gui.SetWindowPos(hwnd, prev, x, y, int(w), int(h),
                                  SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
        prev = hwnd

        if AUTO_CLOSE_MS > 0:
            user32.KillTimer(hwnd, TIMER_ID)
            user32.SetTimer(hwnd, TIMER_ID, AUTO_CLOSE_MS, None)
        win32gui.UpdateWindow(hwnd)

def hide_raster(handles: Iterable[int]) -> None:
    # Hide (NOT minimize) a whole raster
    for hwnd in handles:
        hide_window(hwnd)

# -------- Message pump --------
def pump_messages() -> bool:
    msg = wintypes.MSG()
    while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, win32con.PM_REMOVE):
        if msg.message == win32con.WM_QUIT:
            return False
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return True

def validate_images(paths: Sequence[str]) -> list[str]:
    valid: list[str] = []
    for path in paths:
        if os.path.isfile(path):
            valid.append(path)
        else:
            print(f"Skipping missing image: {path}")
    return valid

# -------- Sequence orchestration (double buffer, layered flips) --------
def sequence_display(image_paths: Sequence[str]) -> None:
    if not image_paths:
        print("No images to display.")
        return

    register_window_class()
    handles = create_window_pool(TOTAL_WINDOWS)
    rasters = [handles[i * RASTER_SIZE : (i + 1) * RASTER_SIZE] for i in range(RASTER_COUNT)]

    screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
    screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)

    current_idx = 0
    current_raster = 0
    display_count = len(image_paths)
    per_image_duration = DISPLAY_DURATION_SECONDS
    start_time = time.time()
    end_time = start_time + RUN_LIMIT_SECONDS if RUN_LIMIT_SECONDS > 0 else float("inf")

    # Prepare first raster off-screen
    print(f"Preparing raster {current_raster} for {image_paths[0]}...")
    cells = load_raster_cells(image_paths[0], screen_w, screen_h)
    prepare_raster(rasters[current_raster], cells)

    # Visible raster history (topmost is newest)
    visible_stack: deque[list[int]] = deque(maxlen=MAX_VISIBLE_RASTERS)

    # Flip to first raster (layer it on top)
    display_raster(rasters[current_raster])
    visible_stack.append(rasters[current_raster])
    print(f"Displaying {image_paths[0]} with {RASTER_SIZE} windows.")

    # Prepare the other buffer if more images exist
    next_idx = 1
    upcoming_raster = 1 - current_raster if display_count > 1 else None
    if upcoming_raster is not None:
        if next_idx < display_count:
            print(f"Preparing raster {upcoming_raster} for {image_paths[next_idx]}...")
            next_cells = load_raster_cells(image_paths[next_idx], screen_w, screen_h)
            prepare_raster(rasters[upcoming_raster], next_cells)

    switch_deadline = time.time() + per_image_duration

    while True:
        if not pump_messages():
            break

        now = time.time()
        if now >= end_time:
            # Clean shutdown
            for h in list(WINDOWS.keys()):
                try:
                    win32gui.DestroyWindow(h)
                except:
                    pass
            break

        # Flip when due
        if upcoming_raster is not None and next_idx < display_count and now >= switch_deadline:
            # Show prepared raster ON TOP; do not hide previous (layering)
            display_raster(rasters[upcoming_raster])
            visible_stack.append(rasters[upcoming_raster])
            print(f"Displaying {image_paths[next_idx]} with {RASTER_SIZE} windows.")

            # Optionally hide older rasters if we exceed cap
            while len(visible_stack) > MAX_VISIBLE_RASTERS:
                old = visible_stack.popleft()
                hide_raster(old)

            # Advance
            current_raster = upcoming_raster
            current_idx = next_idx
            next_idx += 1
            switch_deadline = now + per_image_duration

            # Prepare the next back buffer if any
            if next_idx < display_count:
                upcoming_raster = 1 - current_raster
                print(f"Preparing raster {upcoming_raster} for {image_paths[next_idx]}...")
                next_cells = load_raster_cells(image_paths[next_idx], screen_w, screen_h)
                prepare_raster(rasters[upcoming_raster], next_cells)
            else:
                upcoming_raster = None

        time.sleep(0.004)  # tiny sleep to keep CPU chill

def main() -> None:
    if len(sys.argv) > 1:
        raw_paths = sys.argv[1:]
    else:
        raw_paths = list(DEFAULT_IMAGES)
    image_paths = validate_images(raw_paths)
    if not image_paths:
        print("Nothing to do: no valid image paths provided.")
        return
    sequence_display(image_paths)

if __name__ == "__main__":
    main()
