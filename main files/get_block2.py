from faster_simon import get_blocks_from_imgs, reduce

import numpy as np
import skimage.io as io
import skimage
import skimage.color as color
from scipy.ndimage import uniform_filter
from skimage.util import img_as_ubyte

import cv2
import numpy as np
import os.path as path
import skimage.io as io
import skimage

import skimage.color as color

import json
import sys

source_file_path = "prev_frame.jpg"

def rgb_to_hex(col):
    return '#%02x%02x%02x' % col

def get_blocks():
    target_file_path = sys.argv[1]
    target = io.imread(target_file_path)
    target = skimage.img_as_float(target)[..., :3]
    target.astype(np.float32)
    target = reduce(target, 0.25)

    try:
        source = io.imread(source_file_path)
        source = skimage.img_as_float(source)[..., :3]
        source.astype(np.float32)
    except:
        source = None

    if source.shape != target.shape:
        source = None

    blocks, curr_frame = get_blocks_from_imgs(target, source)

    new_data = []
    for (x,y,w,h,c) in blocks:

        c = c * 255
        c = c.astype(int)
        c = c.clip(0,255)
        c = tuple(c)
        new_data.append((x,y,w,h,rgb_to_hex(c)))

    print(new_data)

    curr_frame = curr_frame.clip(0, 1)

    image_uint8 = img_as_ubyte(curr_frame)

    io.imsave(source_file_path, image_uint8)

    return new_data


if __name__ == "__main__":
    print(json.dumps(get_blocks()))