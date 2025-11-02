"""
server.py - Backend server for processing inputs and managing quadtree display
Handles: image upload, video processing, screen capture, webcam capture
"""

import os
import cv2
import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import subprocess
import threading
import time
from pathlib import Path
import base64
from PIL import Image
import io

app = Flask(__name__, static_folder='static')
CORS(app)

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)  # camhack2025 folder
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
FRAMES_FOLDER = os.path.join(BASE_DIR, 'frames')
IMAGES_FOLDER = os.path.join(BASE_DIR, 'images')
WINDOW_CREATOR = os.path.join(PARENT_DIR, 'WindowCreator')
GET_BLOCKS_PY = os.path.join(BASE_DIR, 'get_block2.py')
FASTER_SIMON_PY = os.path.join(BASE_DIR, 'faster_simon.py')
PREV_FRAME_PATH = os.path.join(BASE_DIR, 'prev_frame.jpg')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'avi', 'mov', 'webm'}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(FRAMES_FOLDER, exist_ok=True)
os.makedirs(IMAGES_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['FRAMES_FOLDER'] = FRAMES_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Global state
current_display_process = None
current_capture_thread = None
stop_capture_flag = threading.Event()
current_mode = None  # 'image', 'video', 'screen', 'webcam'
current_fps = 10
current_target_resolution = None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clear_frames_folder():
    """Clear existing frames"""
    for file in Path(FRAMES_FOLDER).glob('*'):
        if file.is_file():
            file.unlink()

def clear_images_folder():
    """Clear existing images"""
    for file in Path(IMAGES_FOLDER).glob('*'):
        if file.is_file():
            file.unlink()

def clear_prev_frame():
    """Clear previous frame cache"""
    if os.path.exists(PREV_FRAME_PATH):
        os.remove(PREV_FRAME_PATH)

def copy_frames_to_images():
    """Copy frames to images folder"""
    import shutil
    clear_images_folder()
    frames = sorted(Path(FRAMES_FOLDER).glob('frame_*.png'))
    for frame in frames:
        shutil.copy(str(frame), str(Path(IMAGES_FOLDER) / frame.name))
    return len(frames)

def get_image_aspect_ratio(image_path):
    """Get image dimensions"""
    try:
        img = Image.open(image_path)
        return img.size
    except:
        return None, None

def calculate_target_resolution(width, height, max_width=1920, max_height=1080):
    """Calculate target resolution maintaining aspect ratio"""
    if width is None or height is None:
        return "1024x768"
    
    aspect = width / height
    
    if width > max_width or height > max_height:
        if aspect > (max_width / max_height):
            target_w = max_width
            target_h = int(max_width / aspect)
        else:
            target_h = max_height
            target_w = int(max_height * aspect)
    else:
        target_w = width
        target_h = height
    
    return f"{target_w}x{target_h}"

def extract_video_frames(video_path, fps=10, max_frames=None):
    """Extract frames from video at specified FPS"""
    global current_fps, current_target_resolution, current_mode
    current_mode = 'video'
    current_fps = fps
    
    clear_frames_folder()
    clear_prev_frame()
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False, "Could not open video file"
    
    # Get video dimensions
    video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    current_target_resolution = calculate_target_resolution(video_width, video_height)
    print(f"Video: {video_width}x{video_height}, target: {current_target_resolution}")
    
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(video_fps / fps) if fps < video_fps else 1
    
    frame_count = 0
    saved_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_count % frame_interval == 0:
            frame_path = os.path.join(FRAMES_FOLDER, f'frame_{saved_count:04d}.png')
            cv2.imwrite(frame_path, frame)
            saved_count += 1
            
            if max_frames and saved_count >= max_frames:
                break
        
        frame_count += 1
    
    cap.release()
    print(f"Extracted {saved_count} frames at {fps} FPS")
    return True, f"Extracted {saved_count} frames"

def process_image_to_frame(image_path):
    """Copy/convert single image to frames folder"""
    global current_mode, current_target_resolution
    current_mode = 'image'
    
    clear_frames_folder()
    clear_prev_frame()
    
    print(f"Processing image: {image_path}")
    
    # Get original dimensions
    width, height = get_image_aspect_ratio(image_path)
    if width and height:
        current_target_resolution = calculate_target_resolution(width, height)
        print(f"Image: {width}x{height}, target: {current_target_resolution}")
    else:
        current_target_resolution = "1024x768"
    
    img = Image.open(image_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    frame_path = os.path.join(FRAMES_FOLDER, 'frame_0000.png')
    img.save(frame_path)
    
    print(f"Saved frame to: {frame_path}")
    
    return True, "Image ready for display"

def start_quadtree_display():
    """Start WindowCreator display with get_block2.py"""
    global current_display_process, current_mode, current_target_resolution
    
    stop_quadtree_display()
    
    # Check files
    if not os.path.exists(WINDOW_CREATOR):
        return False, f"WindowCreator not found at {WINDOW_CREATOR}"
    if not os.path.exists(GET_BLOCKS_PY):
        return False, f"get_block2.py not found"
    if not os.path.exists(FASTER_SIMON_PY):
        return False, f"faster_simon.py not found"
    
    frames = sorted(Path(FRAMES_FOLDER).glob('frame_*.png'))
    if not frames:
        return False, "No frames available"
    
    # Determine target resolution
    if current_mode in ['screen', 'webcam']:
        target_res = "2560x1600"
    elif current_target_resolution:
        target_res = current_target_resolution
    else:
        target_res = "1024x768"
    
    print(f"Starting WindowCreator: mode={current_mode}, target={target_res}")
    
    try:
        if current_mode in ['screen', 'webcam']:
            # Real-time mode
            cmd = [
                WINDOW_CREATOR,
                GET_BLOCKS_PY,
                '--mode', 'single',
                '--folder', 'frames',
                '--target', target_res
            ]
        elif current_mode == 'image':
            # Single image
            copy_frames_to_images()
            cmd = [
                WINDOW_CREATOR,
                GET_BLOCKS_PY,
                '--mode', 'single',
                '--folder', 'images',
                '--target', target_res
            ]
        else:  # video
            # All frames
            copy_frames_to_images()
            cmd = [
                WINDOW_CREATOR,
                GET_BLOCKS_PY,
                '--mode', 'all',
                '--folder', 'images',
                '--target', target_res
            ]
        
        print(f"Command: {' '.join(cmd)}")
        current_display_process = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return True, f"Started display with {len(frames)} frames at {target_res}"
    except Exception as e:
        return False, f"Error: {str(e)}"

def stop_quadtree_display():
    """Stop the quadtree display"""
    global current_display_process
    
    if current_display_process:
        current_display_process.terminate()
        try:
            current_display_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            current_display_process.kill()
        current_display_process = None
        clear_prev_frame()

def capture_screen_thread(fps=10, duration=None):
    """Capture screen in background thread"""
    global stop_capture_flag, current_mode, current_fps, current_target_resolution
    
    current_mode = 'screen'
    current_fps = fps
    current_target_resolution = "2560x1600"
    clear_frames_folder()
    clear_prev_frame()
    stop_capture_flag.clear()
    
    frame_count = 0
    start_time = time.time()
    frame_interval = 1.0 / fps
    max_frames = 100
    
    try:
        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            
            while not stop_capture_flag.is_set():
                if duration and (time.time() - start_time) > duration:
                    break
                
                # Capture screen
                screenshot = sct.grab(monitor)
                img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
                
                # Save frame with rolling index
                frame_index = frame_count % max_frames
                frame_path = os.path.join(FRAMES_FOLDER, f'frame_{frame_index:04d}.png')
                img.save(frame_path)
                frame_count += 1
                
                time.sleep(frame_interval)
    
    except Exception as e:
        print(f"Screen capture error: {e}")
    
    print(f"Screen capture finished: {frame_count} frames")

def capture_webcam_thread(fps=10, duration=None):
    """Capture webcam in background thread"""
    global stop_capture_flag, current_mode, current_fps, current_target_resolution
    
    current_mode = 'webcam'
    current_fps = fps
    current_target_resolution = "2560x1600"
    clear_frames_folder()
    clear_prev_frame()
    stop_capture_flag.clear()
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open webcam")
        return
    
    frame_count = 0
    start_time = time.time()
    frame_interval = 1.0 / fps
    max_frames = 100
    
    try:
        while not stop_capture_flag.is_set():
            if duration and (time.time() - start_time) > duration:
                break
            
            ret, frame = cap.read()
            if not ret:
                break
            
            # Save frame with rolling index
            frame_index = frame_count % max_frames
            frame_path = os.path.join(FRAMES_FOLDER, f'frame_{frame_index:04d}.png')
            cv2.imwrite(frame_path, frame)
            frame_count += 1
            
            time.sleep(frame_interval)
    
    except Exception as e:
        print(f"Webcam capture error: {e}")
    
    finally:
        cap.release()
    
    print(f"Webcam capture finished: {frame_count} frames")

# ============= API ROUTES =============

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/upload/image', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    success, message = process_image_to_frame(filepath)
    
    if success:
        return jsonify({'message': message, 'frames': 1})
    else:
        return jsonify({'error': message}), 500

@app.route('/api/upload/video', methods=['POST'])
def upload_video():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # Get FPS from request
    fps = int(request.form.get('fps', 10))
    max_frames = request.form.get('maxFrames')
    max_frames = int(max_frames) if max_frames else None
    
    success, message = extract_video_frames(filepath, fps=fps, max_frames=max_frames)
    
    if success:
        frame_count = len(list(Path(FRAMES_FOLDER).glob('frame_*.png')))
        return jsonify({'message': message, 'frames': frame_count})
    else:
        return jsonify({'error': message}), 500

@app.route('/api/capture/screen/start', methods=['POST'])
def start_screen_capture():
    global current_capture_thread
    
    data = request.json or {}
    fps = data.get('fps', 10)
    duration = data.get('duration')  # Optional duration in seconds
    
    if current_capture_thread and current_capture_thread.is_alive():
        return jsonify({'error': 'Capture already in progress'}), 400
    
    current_capture_thread = threading.Thread(
        target=capture_screen_thread,
        args=(fps, duration),
        daemon=True
    )
    current_capture_thread.start()
    
    return jsonify({'message': 'Screen capture started', 'fps': fps})

@app.route('/api/capture/screen/stop', methods=['POST'])
def stop_screen_capture():
    global stop_capture_flag
    
    stop_capture_flag.set()
    time.sleep(0.5)  # Give it time to finish
    
    frame_count = len(list(Path(FRAMES_FOLDER).glob('frame_*.png')))
    return jsonify({'message': 'Screen capture stopped', 'frames': frame_count})

@app.route('/api/capture/webcam/start', methods=['POST'])
def start_webcam_capture():
    global current_capture_thread
    
    data = request.json or {}
    fps = data.get('fps', 10)
    duration = data.get('duration')
    
    if current_capture_thread and current_capture_thread.is_alive():
        return jsonify({'error': 'Capture already in progress'}), 400
    
    current_capture_thread = threading.Thread(
        target=capture_webcam_thread,
        args=(fps, duration),
        daemon=True
    )
    current_capture_thread.start()
    
    return jsonify({'message': 'Webcam capture started', 'fps': fps})

@app.route('/api/capture/webcam/stop', methods=['POST'])
def stop_webcam_capture():
    global stop_capture_flag
    
    stop_capture_flag.set()
    time.sleep(0.5)
    
    frame_count = len(list(Path(FRAMES_FOLDER).glob('frame_*.png')))
    return jsonify({'message': 'Webcam capture stopped', 'frames': frame_count})

@app.route('/api/display/start', methods=['POST'])
def display_start():
    success, message = start_quadtree_display()
    
    if success:
        return jsonify({'message': message})
    else:
        return jsonify({'error': message}), 500

@app.route('/api/display/stop', methods=['POST'])
def display_stop():
    stop_quadtree_display()
    return jsonify({'message': 'Display stopped'})

@app.route('/api/status', methods=['GET'])
def status():
    frame_count = len(list(Path(FRAMES_FOLDER).glob('frame_*.png')))
    
    return jsonify({
        'frames': frame_count,
        'display_active': current_display_process is not None and current_display_process.poll() is None,
        'capture_active': current_capture_thread is not None and current_capture_thread.is_alive(),
        'mode': current_mode,
        'fps': current_fps,
        'target_resolution': current_target_resolution
    })

@app.route('/api/frames/clear', methods=['POST'])
def clear_frames():
    global current_mode, current_fps, current_target_resolution
    clear_frames_folder()
    clear_images_folder()
    clear_prev_frame()
    stop_quadtree_display()
    current_mode = None
    current_fps = 10
    current_target_resolution = None
    return jsonify({'message': 'Frames cleared'})

if __name__ == '__main__':
    print("Starting Quadtree Input Server...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)
