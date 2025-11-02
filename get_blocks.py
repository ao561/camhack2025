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

def rgb_to_hex(col):
    return '#%02x%02x%02x' % tuple(col)

def load_image_rgb_float01(p):
    """Load image and ensure (H,W,3) float32 in [0,1]."""
    im = io.imread(p)
    if im.ndim == 2:
        im = np.stack([im, im, im], axis=-1)
    elif im.ndim == 3 and im.shape[-1] >= 3:
        if im.shape[-1] > 3:
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
    if "channel_axis" in sig.parameters:
        return transform.rotate(
            img, angle_deg, resize=True, mode='edge',
            channel_axis=-1, preserve_range=True
        )
    else:
        return transform.rotate(
            img, angle_deg, resize=True, mode='edge',
            preserve_range=True
        )

def parse_target(s):
    try:
        w_str, h_str = s.lower().split("x")
        w, h = int(w_str), int(h_str)
        if w <= 0 or h <= 0:
            raise ValueError
        return w, h
    except Exception:
        raise argparse.ArgumentTypeError("Target must be like 800x600")

def get_blocks_single(img_path, target_w, target_h, rotate_deg=90):
    """Process one image: load → rotate → resize to (target_h,target_w) → blocks → scale to target canvas."""
    im = load_image_rgb_float01(img_path)

    if rotate_deg % 360 != 0:
        im = safe_rotate(im, rotate_deg).astype(np.float32)
        im = np.clip(im, 0.0, 1.0)

    # --- Force all images to the SAME canvas size ---
    # Note skimage.transform.resize takes (output_h, output_w, channels)
    im = transform.resize(
        im, (target_h, target_w, 3),
        mode='edge', anti_aliasing=True, preserve_range=True
    ).astype(np.float32)
    im = np.clip(im, 0.0, 1.0)

    # Downsample for speed before segmentation (optional but matches previous flow)
    im_down_color = reduce(im, 0.125)
    im_down_gray  = color.rgb2gray(im_down_color)

    # Compute blocks on the downsized image
    data = get_blocks_from_imgs(im_down_color, im_down_gray)

    # Scale blocks up to the **fixed** target canvas
    h_down, w_down, _ = im_down_color.shape
    ws = target_w / max(1, w_down)
    hs = target_h / max(1, h_down)

    blocks = []
    for (x, y, bw, bh, c) in data:
        c255 = np.clip((c * 255).astype(int), 0, 255)
        blocks.append((x * ws, y * hs, bw * ws, bh * hs, rgb_to_hex(tuple(c255))))
    return blocks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["single", "all"], default="single")
    ap.add_argument("--target", type=parse_target, default="800x600",
                    help="Force all frames to this WxH canvas (default 800x600)")
    ap.add_argument("--rotate", type=int, default=-90,
                    help="Rotate degrees CCW before resize (default 90; use 0 to disable)")
    args = ap.parse_args()

    target_w, target_h = args.target

    base = os.path.dirname(os.path.abspath(__file__))
    images_dir = os.path.join(base, "images")
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
            result = get_blocks_single(img_files[0], target_w, target_h, rotate_deg=args.rotate)
        else:
            result = [get_blocks_single(p, target_w, target_h, rotate_deg=args.rotate) for p in img_files]

        print(json.dumps(result))
    except BrokenPipeError:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
