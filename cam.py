import cv2
from skimage.util import img_as_float

import json
from screeninfo import get_monitors

import os

from get_block2 import get_blocks_with_target, reduce, rgb_to_hex
import tempfile

def write_blocks(blocks, path="blocks.json"):
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix="blocks_", suffix=".tmp")
    os.close(fd)

    with open(tmp_path, "w") as f:
        json.dump(blocks, f)

    # Atomic rename replaces old file only after full write completes
    os.replace(tmp_path, path)

screen = get_monitors()[0]  # Primary monitor
screen_width = screen.width
screen_height = screen.height

cap = cv2.VideoCapture(0)

os.remove("prev_frame.jpg")

if not cap.isOpened():
    print("Error: Could not open webcam.")
    exit()

while True:
    ret, frame_bgr = cap.read()
    
    if not ret:
        break
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    frame_rgb = cv2.flip(frame_rgb, 1)
    frame_rgb = reduce(frame_rgb, 0.25)

    frame_float = img_as_float(frame_rgb)
    
    blocks = get_blocks_with_target(frame_float)

    imh, imw = frame_rgb.shape[:2]

    scale = 3

    serialized_blocks = [{"x": y * scale, "y": (imh-(x+w)) * scale, "w": h*scale, "h": w*scale, "color": c} for (x,y,w,h,c) in blocks]

    with open("blocks.json", "w") as f:
        json.dump(serialized_blocks, f)


cap.release()
cv2.destroyAllWindows()