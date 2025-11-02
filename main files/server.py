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
UPLOAD_FOLDER = 'uploads'
FRAMES_FOLDER = 'frames'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'avi', 'mov', 'webm'}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(FRAMES_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['FRAMES_FOLDER'] = FRAMES_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Global state
current_display_process = None
current_capture_thread = None
stop_capture_flag = threading.Event()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clear_frames_folder():
    """Clear existing frames"""
    for file in Path(FRAMES_FOLDER).glob('*'):
        if file.is_file():
            file.unlink()

def extract_video_frames(video_path, fps=10, max_frames=None):
    """Extract frames from video at specified FPS"""
    clear_frames_folder()
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False, "Could not open video file"
    
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
    return True, f"Extracted {saved_count} frames"

def process_image_to_frame(image_path):
    """Copy/convert single image to frames folder"""
    clear_frames_folder()
    
    img = Image.open(image_path)
    # Convert to RGB if necessary
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    frame_path = os.path.join(FRAMES_FOLDER, 'frame_0000.png')
    img.save(frame_path)
    
    return True, "Image ready for display"

def start_quadtree_display():
    """Start the quadtree video display"""
    global current_display_process
    
    # Stop any existing display
    stop_quadtree_display()
    
    # Check if frames exist
    frames = sorted(Path(FRAMES_FOLDER).glob('frame_*.png'))
    if not frames:
        return False, "No frames available"
    
    # Start quadtree_video executable
    # Note: Assumes quadtree_video is compiled and in the same directory
    try:
        current_display_process = subprocess.Popen(['./quadtree_video'])
        return True, f"Started display with {len(frames)} frames"
    except FileNotFoundError:
        return False, "quadtree_video executable not found. Please compile first."
    except Exception as e:
        return False, f"Error starting display: {str(e)}"

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

def capture_screen_thread(fps=10, duration=None):
    """Capture screen in background thread"""
    global stop_capture_flag
    
    clear_frames_folder()
    stop_capture_flag.clear()
    
    frame_count = 0
    start_time = time.time()
    frame_interval = 1.0 / fps
    
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
                
                # Save frame
                frame_path = os.path.join(FRAMES_FOLDER, f'frame_{frame_count:04d}.png')
                img.save(frame_path)
                frame_count += 1
                
                time.sleep(frame_interval)
    
    except Exception as e:
        print(f"Screen capture error: {e}")
    
    print(f"Screen capture finished: {frame_count} frames")

def capture_webcam_thread(fps=10, duration=None):
    """Capture webcam in background thread"""
    global stop_capture_flag
    
    clear_frames_folder()
    stop_capture_flag.clear()
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Could not open webcam")
        return
    
    frame_count = 0
    start_time = time.time()
    frame_interval = 1.0 / fps
    
    try:
        while not stop_capture_flag.is_set():
            if duration and (time.time() - start_time) > duration:
                break
            
            ret, frame = cap.read()
            if not ret:
                break
            
            # Save frame
            frame_path = os.path.join(FRAMES_FOLDER, f'frame_{frame_count:04d}.png')
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
        'capture_active': current_capture_thread is not None and current_capture_thread.is_alive()
    })

@app.route('/api/frames/clear', methods=['POST'])
def clear_frames():
    clear_frames_folder()
    stop_quadtree_display()
    return jsonify({'message': 'Frames cleared'})

if __name__ == '__main__':
    print("Starting Quadtree Input Server...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)
