"""
server.py - Backend server with WindowCreator integration and get_block2.py optimization
Handles: image upload, video processing, screen capture, webcam capture
Features: Frame differencing optimization, aspect ratio matching, real-time queue
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
import shutil
from PIL import Image

app = Flask(__name__, static_folder='static')
CORS(app)

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
FRAMES_FOLDER = os.path.join(BASE_DIR, 'frames')
IMAGES_FOLDER = os.path.join(BASE_DIR, 'images')
WINDOW_CREATOR = os.path.join(BASE_DIR, 'WindowCreator')
GET_BLOCKS_PY = os.path.join(BASE_DIR, 'get_block2.py')  # Using optimized version
FASTER_SIMON_PY = os.path.join(BASE_DIR, 'faster_simon.py')
PREV_FRAME_PATH = os.path.join(BASE_DIR, 'prev_frame.jpg')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'avi', 'mov', 'webm'}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

# Create directories
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
current_fps = 10  # FPS for video/capture modes
current_target_resolution = None  # Target resolution for WindowCreator

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clear_frames_folder():
    """Clear existing frames in frames/ folder"""
    for file in Path(FRAMES_FOLDER).glob('*'):
        if file.is_file():
            file.unlink()

def clear_images_folder():
    """Clear existing images in images/ folder"""
    for file in Path(IMAGES_FOLDER).glob('*'):
        if file.is_file():
            file.unlink()

def clear_prev_frame():
    """Clear previous frame cache for get_block2.py optimization"""
    if os.path.exists(PREV_FRAME_PATH):
        os.remove(PREV_FRAME_PATH)
        print(f"Cleared previous frame cache: {PREV_FRAME_PATH}")

def copy_frames_to_images():
    """Copy frames from frames/ to images/ folder for get_block2.py"""
    clear_images_folder()
    frames = sorted(Path(FRAMES_FOLDER).glob('frame_*.png'))
    for frame in frames:
        shutil.copy(str(frame), str(Path(IMAGES_FOLDER) / frame.name))
    return len(frames)

def get_image_aspect_ratio(image_path):
    """Get aspect ratio from image file"""
    try:
        img = Image.open(image_path)
        width, height = img.size
        return width, height
    except Exception as e:
        print(f"Error getting image dimensions: {e}")
        return None, None

def calculate_target_resolution(width, height, max_width=1920, max_height=1080):
    """Calculate target resolution maintaining aspect ratio"""
    if width is None or height is None:
        return "1024x768"
    
    aspect = width / height
    
    # Scale to fit within max dimensions while maintaining aspect ratio
    if width > max_width or height > max_height:
        if aspect > (max_width / max_height):
            # Width is the limiting factor
            target_w = max_width
            target_h = int(max_width / aspect)
        else:
            # Height is the limiting factor
            target_h = max_height
            target_w = int(max_height * aspect)
    else:
        # Use original dimensions if smaller than max
        target_w = width
        target_h = height
    
    return f"{target_w}x{target_h}"

def process_image_to_frame(image_path):
    """Copy/convert single image to frames folder"""
    global current_mode, current_target_resolution
    current_mode = 'image'
    
    clear_frames_folder()
    clear_prev_frame()  # Clear optimization cache
    
    print(f"Processing image: {image_path}")
    print(f"Frames folder: {FRAMES_FOLDER}")
    
    # Get original dimensions for aspect ratio
    width, height = get_image_aspect_ratio(image_path)
    if width and height:
        current_target_resolution = calculate_target_resolution(width, height)
        print(f"Image dimensions: {width}x{height}, target: {current_target_resolution}")
    else:
        current_target_resolution = "1024x768"
    
    img = Image.open(image_path)
    # Convert to RGB if necessary
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    frame_path = os.path.join(FRAMES_FOLDER, 'frame_0000.png')
    img.save(frame_path)
    
    print(f"Saved frame to: {frame_path}")
    print(f"File exists: {os.path.exists(frame_path)}")
    
    return True, "Image ready for display"

def extract_video_frames(video_path, fps=10, max_frames=None):
    """Extract frames from video at specified FPS"""
    global current_fps, current_target_resolution, current_mode
    current_mode = 'video'
    current_fps = fps
    
    clear_frames_folder()
    clear_prev_frame()  # Clear optimization cache
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False, "Could not open video file"
    
    # Get video dimensions for aspect ratio
    video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    current_target_resolution = calculate_target_resolution(video_width, video_height)
    print(f"Video dimensions: {video_width}x{video_height}, target: {current_target_resolution}")
    
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
    return True, f"Extracted {saved_count} frames at {fps} FPS"

def start_quadtree_display():
    """Start the WindowCreator display with get_block2.py optimization"""
    global current_display_process, current_mode, current_target_resolution
    
    # Stop any existing display
    stop_quadtree_display()
    
    # Check if WindowCreator binary exists
    if not os.path.exists(WINDOW_CREATOR):
        return False, f"WindowCreator binary not found at {WINDOW_CREATOR}"
    
    if not os.path.exists(GET_BLOCKS_PY):
        return False, f"get_block2.py not found at {GET_BLOCKS_PY}"
    
    if not os.path.exists(FASTER_SIMON_PY):
        return False, f"faster_simon.py not found at {FASTER_SIMON_PY}"
    
    # Check if frames exist in frames/ folder
    frames = sorted(Path(FRAMES_FOLDER).glob('frame_*.png'))
    if not frames:
        return False, "No frames available"
    
    # Determine target resolution
    if current_mode in ['screen', 'webcam']:
        target_res = "2560x1600"  # Fixed resolution for screen/webcam
    elif current_target_resolution:
        target_res = current_target_resolution  # Use calculated aspect ratio
    else:
        target_res = "1024x768"  # Fallback
    
    print(f"Starting WindowCreator with {len(frames)} frames")
    print(f"Mode: {current_mode}, FPS: {current_fps}, Target: {target_res}")
    
    try:
        if current_mode in ['screen', 'webcam']:
            # Real-time mode: use --mode single --folder frames
            # WindowCreator will continuously process from frames folder
            cmd = [
                WINDOW_CREATOR,
                GET_BLOCKS_PY,
                '--mode', 'single',
                '--folder', 'frames',
                '--target', target_res
            ]
            print(f"Real-time mode: Monitoring frames/ folder")
        elif current_mode == 'image':
            # Single image: copy to images/ and use --mode single
            copy_frames_to_images()
            cmd = [
                WINDOW_CREATOR,
                GET_BLOCKS_PY,
                '--mode', 'single',
                '--folder', 'images',
                '--target', target_res
            ]
            print(f"Image mode: Using images/ folder")
        else:  # video
            # Pre-processed frames: copy to images/ and use --mode all
            num_copied = copy_frames_to_images()
            cmd = [
                WINDOW_CREATOR,
                GET_BLOCKS_PY,
                '--mode', 'all',
                '--folder', 'images',
                '--target', target_res
            ]
            print(f"Video mode: Copied {num_copied} frames to images/")
        
        print(f"Running command: {' '.join(cmd)}")
        current_display_process = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        return True, f"Started WindowCreator display with {len(frames)} frames at {target_res}"
    except FileNotFoundError as e:
        return False, f"WindowCreator binary not found: {e}"
    except Exception as e:
        return False, f"Error starting display: {str(e)}"

def stop_quadtree_display():
    """Stop the WindowCreator display"""
    global current_display_process
    
    if current_display_process:
        current_display_process.terminate()
        try:
            current_display_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            current_display_process.kill()
        current_display_process = None
        clear_prev_frame()  # Clear optimization cache when stopping
        print("Stopped WindowCreator display")

def capture_screen_thread(fps=10, duration=None):
    """Capture screen in background thread - real-time queue"""
    global stop_capture_flag, current_mode, current_fps, current_target_resolution
    
    current_mode = 'screen'
    current_fps = fps
    current_target_resolution = "2560x1600"  # Fixed for screen capture
    clear_frames_folder()
    clear_prev_frame()  # Clear optimization cache
    stop_capture_flag.clear()
    
    frame_count = 0
    start_time = time.time()
    frame_interval = 1.0 / fps
    
    # Rolling window of 100 frames
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
    
    print(f"Screen capture finished: {frame_count} frames captured")

def capture_webcam_thread(fps=10, duration=None):
    """Capture webcam in background thread - real-time queue"""
    global stop_capture_flag, current_mode, current_fps, current_target_resolution
    
    current_mode = 'webcam'
    current_fps = fps
    current_target_resolution = "2560x1600"  # Fixed for webcam
    clear_frames_folder()
    clear_prev_frame()  # Clear optimization cache
    stop_capture_flag.clear()
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open webcam")
        return
    
    frame_count = 0
    start_time = time.time()
    frame_interval = 1.0 / fps
    
    # Rolling window of 100 frames
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
    
    print(f"Webcam capture finished: {frame_count} frames captured")

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
    print("Starting Quadtree Input Server with WindowCreator integration...")
    print("Using get_block2.py with frame differencing optimization")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)
