## --mode all for all the images in the folder
## --mode single for single image processing
## --target WxH for fixed canvas size, or 'first' to use first image size
## e.g. ./WindowCreator ./get_blocks.py --mode all --target 900x1440


import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"  # silence pygame banner

import sys
import json
import argparse
import inspect
import numpy as np
import skimage.io as io
import skimage.color as color
import skimage.transform as transform
from faster import get_blocks_from_imgs, reduce  # your existing functions

VALID_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".heic")

# ---------------- helpers ----------------

def rgb_to_hex(col):
    return '#%02x%02x%02x' % tuple(col)

def load_image_rgb_float01(p):
    """Load image and ensure (H,W,3) float32 in [0,1]."""
    im = io.imread(p)
    if im.ndim == 2:
        im = np.stack([im, im, im], axis=-1)
    elif im.ndim == 3 and im.shape[-1] >= 3:
        if im.shape[-1] > 3:  # RGBA -> RGB
            im = im[..., :3]
    else:
        raise ValueError(f"Unsupported image shape {im.shape} for {p}")

    if im.dtype.kind in "ui":
        im = im.astype(np.float32) / 255.0
    else:
        im = np.clip(im.astype(np.float32), 0.0, 1.0)
    return im

def safe_rotate(img, angle_deg):
    """Rotate image; support old/new skimage APIs."""
    sig = inspect.signature(transform.rotate)
    if "channel_axis" in sig.parameters:  # skimage >= 0.19
        return transform.rotate(
            img, angle_deg, resize=True, mode='edge',
            channel_axis=-1, preserve_range=True
        )
    else:  # older skimage
        return transform.rotate(
            img, angle_deg, resize=True, mode='edge',
            preserve_range=True
        )

def parse_target(s):
    s = s.strip().lower()
    if s == "first":
        return "first"
    try:
        w_str, h_str = s.split("x")
        w, h = int(w_str), int(h_str)
        if w <= 0 or h <= 0:
            raise ValueError
        return (w, h)
    except Exception:
        raise argparse.ArgumentTypeError("Target must be 'first' or like 800x600")

def pick_downsample(quality: str, explicit: float | None) -> float:
    if explicit is not None:
        return float(explicit)
    table = {
        "low":   0.25,    # fewer boxes, faster
        "med":   0.125,   # default
        "high":  0.0625,  # more boxes
        "ultra": 0.03125  # many boxes, slow
    }
    return table.get(quality, 0.125)

def prune_boxes(data, max_boxes):
    """Keep at most max_boxes largest rectangles (by area)."""
    if max_boxes is None or max_boxes <= 0 or len(data) <= max_boxes:
        return data
    # data tuples: (x, y, w, h, c)
    # sort by area descending, keep first N
    idx = np.argsort([-d[2]*d[3] for d in data])[:max_boxes]
    return [data[i] for i in idx]

# --------------- core ----------------

def process_one_image(img_path, target, rotate_deg, ds_factor, max_boxes):
    """
    load -> rotate -> choose canvas size -> resize -> downsample -> blocks -> scale -> prune
    """
    im = load_image_rgb_float01(img_path)

    if rotate_deg % 360 != 0:
        im = safe_rotate(im, rotate_deg).astype(np.float32)
        im = np.clip(im, 0.0, 1.0)

    # Decide canvas size
    if target == "first":
        target_w = im.shape[1]
        target_h = im.shape[0]
    else:
        target_w, target_h = target

    # Resize to fixed canvas
    im = transform.resize(
        im, (target_h, target_w, 3),
        mode='edge', anti_aliasing=True, preserve_range=True
    ).astype(np.float32)
    im = np.clip(im, 0.0, 1.0)

    # Downsample for speed / quality control
    im_down_color = reduce(im, ds_factor)
    im_down_gray  = color.rgb2gray(im_down_color)

    # Compute blocks on downsized image
    data = get_blocks_from_imgs(im_down_color, im_down_gray)

    # Scale blocks up to the fixed target canvas
    h_down, w_down, _ = im_down_color.shape
    ws = target_w / max(1, w_down)
    hs = target_h / max(1, h_down)

    blocks = []
    for (x, y, bw, bh, c) in data:
        c255 = np.clip((c * 255).astype(int), 0, 255)
        blocks.append((x * ws, y * hs, bw * ws, bh * hs, rgb_to_hex(tuple(c255))))

    # Optional cap on number of boxes
    blocks = prune_boxes(blocks, max_boxes)
    return blocks

# --------------- CLI ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["single", "all"], default="single",
                    help="single: one image; all: loop all images in folder")
    ap.add_argument("--target", type=parse_target, default="first",
                    help="Canvas size: 'first' (use first image) or WxH (e.g., 1280x720). Default: first")
    ap.add_argument("--rotate", type=int, default=-90,
                    help="Rotate degrees CCW before resize (default -90; 0 to disable)")
    ap.add_argument("--quality", choices=["low","med","high","ultra"], default="med",
                    help="Quality preset mapping to downsample factor (overridden by --downsample)")
    ap.add_argument("--downsample", type=float, default=None,
                    help="Explicit downsample factor (e.g., 0.125). Overrides --quality")
    ap.add_argument("--boxes", type=int, default=0,
                    help="Maximum number of boxes per frame (0 = no limit)")
    ap.add_argument("--folder", default="images",
                    help="Folder containing images (default: images)")
    args = ap.parse_args()

    ds_factor = pick_downsample(args.quality, args.downsample)

    base = os.path.dirname(os.path.abspath(__file__))
    images_dir = os.path.join(base, args.folder)
    if not os.path.isdir(images_dir):
        print(f"Error: images folder not found at {images_dir}", file=sys.stderr)
        sys.exit(1)

    img_files = [
        os.path.join(images_dir, f)
        for f in sorted(os.listdir(images_dir))
        if f.lower().endswith(VALID_EXTS)
    ]
    if not img_files:
        print(f"No images found in {images_dir}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.mode == "single":
            # For 'first' target: we naturally take the first image’s size after rotation
            result = process_one_image(img_files[0], args.target, args.rotate, ds_factor, args.boxes)
        else:
            # Determine canvas once if 'first' was requested (based on the first file)
            target_use = args.target
            if args.target == "first":
                # compute the rotated first to get its post-rotation shape
                im0 = load_image_rgb_float01(img_files[0])
                if args.rotate % 360 != 0:
                    im0 = safe_rotate(im0, args.rotate).astype(np.float32)
                target_use = (im0.shape[1], im0.shape[0])

            result = [
                process_one_image(p, target_use, args.rotate, ds_factor, args.boxes)
                for p in img_files
            ]

        print(json.dumps(result))
    except BrokenPipeError:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
