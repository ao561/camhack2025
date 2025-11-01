import random
import numpy as np
import cv2
import skimage.io as io
import skimage
import skimage.color as color
from scipy.ndimage import uniform_filter
import pygame

import cv2
import numpy as np
import os.path as path
import skimage.io as io
import skimage

import skimage.color as color

import pygame
import random

DOWNSCALE = 0.125
# number of shapes
ROUNDS = 100
CANDIDATES_BASE = 6
VAR_WINDOW = 15
MIN_SIZE = 6
STEEPNESS = 2.0
MAX_CANDIDATES = 30

def reduce(img, factor):
    return cv2.resize(img, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)

def local_variance(gray, ksize=15):
    mean = uniform_filter(gray, size=ksize, mode='reflect')
    mean_sq = uniform_filter(gray * gray, size=ksize, mode='reflect')
    var = mean_sq - mean * mean
    var[var < 0] = 0.0
    return var

def get_sigmoid_size(current_round, total_rounds, max_size, min_size, steepness=2.0):
    progress = current_round / (total_rounds - 1) if total_rounds > 1 else 1.0
    x = (progress * 2 - 1) * steepness
    y_norm = 1.0 / (1.0 + np.exp(x))
    size_range = max_size - min_size
    current_size = (y_norm * size_range) + min_size
    return int(max(min_size, round(current_size)))

def fitness_from_error(total_error, num_pixels):
    return total_error / num_pixels

def clamp_rect(x, y, w, h, H, W):
    if x < 0:
        w += x
        x = 0
    if y < 0:
        h += y
        y = 0
    w = max(0, min(w, H - x))
    h = max(0, min(h, W - y))
    return x, y, w, h

def get_blocks_from_imgs(im_down_color, im_down_gray):
    blocks = []

    H, W, _ = im_down_color.shape

    target = im_down_color.astype(np.float32)
    current_im = np.full_like(target, target.mean(axis=(0,1), keepdims=True), dtype=np.float32)

    avg_color = target.mean(axis=(0, 1))
    blocks.append((0, 0, W, H, avg_color.copy()))

    error_map = np.mean((target - current_im) ** 2, axis=2)
    total_error = error_map.sum()
    num_pixels = error_map.size

    var_map = local_variance(im_down_gray, ksize=VAR_WINDOW)

    var_alpha = 50.0
    combined = error_map / (1.0 + var_map * var_alpha)

    combined[combined < 0] = 0.0
    sum_combined = combined.sum()
    if sum_combined == 0:
        prob_map = np.ones_like(combined) / combined.size
    else:
        prob_map = combined.ravel() / sum_combined
    

    cdf = np.cumsum(prob_map)

    for cur_round in range(ROUNDS):
        candidates = min(MAX_CANDIDATES, int(CANDIDATES_BASE * (1.0 - (cur_round / float(ROUNDS))) + MAX_CANDIDATES))

        u = np.random.rand(candidates)
        idxs = np.searchsorted(cdf, u)

        best_fit = fitness_from_error(total_error, num_pixels)
        best_block = None
        for idx in idxs:
            y_pix, x_pix = divmod(int(idx), W)
            max_size = min(H, W)
            base_m = get_sigmoid_size(cur_round, ROUNDS, max_size, MIN_SIZE, steepness=STEEPNESS)
            local_var = var_map[y_pix, x_pix]
            scale = 1.0 / (1.0 + local_var * 30.0)
            scale = np.clip(scale, 0.25, 1.0)
            m = max(MIN_SIZE, int(base_m * scale))
            rand_w = random.randint(MIN_SIZE, max(MIN_SIZE, m))
            rand_h = random.randint(MIN_SIZE, max(MIN_SIZE, m))

            x0 = y_pix
            y0 = x_pix
            w = rand_w
            h = rand_h

            x0, y0, w, h = clamp_rect(x0, y0, w, h, H, W)

            if w == 0 or h == 0:
                continue
            roi_target = target[x0:x0+w, y0:y0+h]
            roi_current = current_im[x0:x0+w, y0:y0+h]

            avg_color = roi_target.reshape(-1, 3).mean(axis=0)

            old_err_sum = np.sum((roi_target - roi_current) ** 2)
            new_err_sum = np.sum((roi_target - avg_color) ** 2)

            new_total_error = total_error - old_err_sum + new_err_sum
            curr_fit = fitness_from_error(new_total_error, num_pixels)
            if curr_fit < best_fit:
                best_fit = curr_fit
                best_block = (x0, y0, w, h, avg_color, old_err_sum, new_err_sum)

        if best_block is not None:
            x0, y0, w, h, avg_color, old_err_sum, new_err_sum = best_block
            blocks.append((x0, y0, w, h, avg_color))
            current_im[x0:x0+w, y0:y0+h] = avg_color
            new_err_map_roi = np.mean((target[x0:x0+w, y0:y0+h] - avg_color) ** 2, axis=2)
            prev_err_map_roi = error_map[x0:x0+w, y0:y0+h]
            total_error = total_error - prev_err_map_roi.sum() + new_err_map_roi.sum()
            error_map[x0:x0+w, y0:y0+h] = new_err_map_roi

            pad = max(1, int(max(w,h)/2))
            xa = max(0, x0 - pad); xb = min(H, x0 + w + pad)
            ya = max(0, y0 - pad); yb = min(W, y0 + h + pad)
            combined[xa:xb, ya:yb] = error_map[xa:xb, ya:yb] / (1.0 + var_map[xa:xb, ya:yb] * var_alpha)

            sum_combined = combined.sum()
            if sum_combined <= 0:
                prob_map = np.ones_like(combined) / combined.size
            else:
                prob_map = combined.ravel() / sum_combined
            cdf = np.cumsum(prob_map)
    return blocks


if __name__ == "__main__":
    try:
        p = path.dirname(path.abspath(__file__))
        img_path = path.join(p, path.join('images','obama.jpg'))
    except NameError:
        p = '.' 
        img_path = path.join(p, 'images', 'obama.jpg')
        print(f"Warning: __file__ not defined. Assuming image is at {img_path}")


    im = io.imread(img_path)
    im = skimage.img_as_float(im)
    im.astype(np.float32)

    w,h,_ = im.shape
    w = int(w / 2)
    h = int(h / 2)

    print(w, h)

    im_down_color = reduce(im, DOWNSCALE)

    im_down_gray = color.rgb2gray(im_down_color)

    im_h, im_w, _ = im_down_color.shape

    wpad, hpad = 10, 10

    ws = w / im_w
    hs = h / im_w

    blocks = get_blocks_from_imgs(im_down_color, im_down_gray)

    pygame.init()

    screen = pygame.display.set_mode((h + 2 * hpad, w + 2 * wpad))
    pygame.display.set_caption("Drawing Rectangles from an Array")
    clock = pygame.time.Clock()

    running = True
    while running:
        for event in pygame.event.get():
                if event.type == pygame.QUIT:
                        running = False

        screen.fill((255,0,0))
        pygame.draw.rect(screen, (0,0,0), (wpad, hpad, w, h))

        blocks = get_blocks_from_imgs(im_down_color, im_down_gray)

        for (x, y, w, h, c) in blocks:
                c = c * 255
                c = c.astype(int)
                c = c.clip(0,255)
                pygame.draw.rect(screen, tuple(c), (y * hs + hpad, x * ws + wpad, h * hs, w * ws))
        pygame.display.flip()
        clock.tick(60)
    pygame.quit()
