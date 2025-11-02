from faster import get_blocks_from_imgs, reduce

import numpy as np
import skimage.io as io
import skimage
import skimage.color as color
from scipy.ndimage import uniform_filter

import cv2
import numpy as np
import os.path as path
import skimage.io as io
import skimage

import skimage.color as color

import json
import sys

def rgb_to_hex(col):
    return '#%02x%02x%02x' % col

def get_blocks():
    try:
        try:
            p = path.dirname(path.abspath(__file__))
            img_path = path.join(p, path.join('images','obama.jpg'))
        except NameError:
            p = '.' 
            img_path = path.join(p, 'images', 'obama.jpg')
            print(f"Warning: __file__ not defined. Assuming image is at {img_path}")


        im = io.imread(img_path)
        im = skimage.img_as_float(im)
        # Rotate image 90 degrees clockwise
        im = skimage.transform.rotate(im, -90, resize=True)  # negative angle for clockwise
        im.astype(np.float32)

        w,h,_ = im.shape
        w = int(w / 2)
        h = int(h / 2)

        print(w, h)

        im_down_color = reduce(im, 0.125)

        im_down_gray = color.rgb2gray(im_down_color)

        im_h, im_w, _ = im_down_color.shape

        ws = 2 * w / im_w
        hs = 2 * h / im_h

        data = get_blocks_from_imgs(im_down_color, im_down_gray)
        new_data = []
        for (x,y,w,h,c) in data:

            c = c * 255
            c = c.astype(int)
            c = c.clip(0,255)
            c = tuple(c)
            new_data.append((x*ws,y*hs,w*ws,h*hs,rgb_to_hex(c)))
        return new_data
    except Exception as e:
        # Print errors to standard error
        print(f"Error in Python script: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    print(json.dumps(get_blocks()))
