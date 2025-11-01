# Quadtree Display Input System

A comprehensive web-based system for capturing and processing various input types (images, videos, screen capture, webcam) to display as animated quadtree windows.

## Features

- **Image Upload**: Upload single images (PNG, JPG, JPEG)
- **Video Upload**: Upload videos (MP4, AVI, MOV, WEBM) with frame extraction
- **Screen Capture**: Real-time screen recording
- **Webcam Capture**: Real-time webcam recording
- **Web Interface**: Beautiful, user-friendly browser interface
- **Real-time Processing**: Frames are processed and ready for quadtree display

## Setup

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Compile Quadtree Display (if not already done)

Make sure `quadtree_video` is compiled:

```bash
clang++ -std=c++17 -fobjc-arc -framework Cocoa -O2 -o quadtree_video quadtree_video.mm
```

### 3. Create Required Directories

The server will auto-create these, but you can create them manually:

```bash
mkdir uploads frames static
```

### 4. Start the Server

```bash
python server.py
```

The server will start on `http://localhost:5000`

## Usage

### Web Interface

1. Open your browser to `http://localhost:5000`
2. Choose your input method from the tabs:
   - **Image**: Upload a single image
   - **Video**: Upload a video and set FPS/frame limits
   - **Screen Capture**: Record your screen with configurable FPS
   - **Webcam**: Record from your webcam
3. After processing, click "Start Quadtree Display" to launch the window animation

### Input Types

#### Image

- Supports: PNG, JPG, JPEG
- Creates a single frame for static display
- Drag & drop or click to upload

#### Video

- Supports: MP4, AVI, MOV, WEBM
- Configure frame extraction rate (FPS)
- Optional frame limit to reduce processing
- Automatically extracts frames and saves to `frames/` folder

#### Screen Capture

- Captures your entire screen in real-time
- Adjustable capture rate (1-30 FPS)
- Optional duration limit
- Stop capture when ready, then start display

#### Webcam

- Captures from your default webcam
- Adjustable capture rate (1-30 FPS)
- Optional duration limit
- Stop capture when ready, then start display

## API Endpoints

### Upload Endpoints

- `POST /api/upload/image` - Upload single image
- `POST /api/upload/video` - Upload video file

### Capture Endpoints

- `POST /api/capture/screen/start` - Start screen capture
- `POST /api/capture/screen/stop` - Stop screen capture
- `POST /api/capture/webcam/start` - Start webcam capture
- `POST /api/capture/webcam/stop` - Stop webcam capture

### Display Endpoints

- `POST /api/display/start` - Start quadtree display
- `POST /api/display/stop` - Stop quadtree display
- `POST /api/frames/clear` - Clear all frames
- `GET /api/status` - Get current status

## Directory Structure

```
camhack2025/
├── server.py              # Flask backend server
├── requirements.txt       # Python dependencies
├── quadtree_video.mm      # Quadtree display program
├── uploads/               # Uploaded files
├── frames/                # Processed frames (used by quadtree_video)
└── static/
    ├── index.html         # Web interface
    ├── style.css          # Styling
    └── app.js             # Frontend JavaScript
```

## Notes

- **Screen Capture** requires `mss` library (included in requirements.txt)
- **Webcam** uses OpenCV's VideoCapture
- **Video Processing** uses OpenCV for frame extraction
- The `frames/` folder is automatically managed and used by `quadtree_video`
- Frames are cleared between different inputs
- Display must be stopped before processing new input

## Troubleshooting

### "quadtree_video executable not found"

- Make sure you compiled `quadtree_video.mm`
- Ensure the executable is in the same directory as `server.py`

### Screen Capture Not Working (macOS)

- Grant screen recording permissions to Terminal/Python in System Preferences > Security & Privacy > Screen Recording

### Webcam Not Working

- Ensure your webcam is not in use by another application
- Grant camera permissions if prompted

### Video Upload Slow

- Large videos take time to process
- Consider setting a lower FPS or max frame limit
- Videos are processed server-side frame by frame

## Advanced Configuration

Edit `server.py` to customize:

- `MAX_FILE_SIZE`: Maximum upload size
- `UPLOAD_FOLDER`: Where uploads are stored
- `FRAMES_FOLDER`: Where processed frames are saved

Edit `quadtree_video.mm` to customize:

- `VARIANCE_THRESHOLD`: Controls detail level (lower = more windows)
- `MIN_WINDOW_SIZE`: Minimum window size in pixels
- `MAX_DEPTH`: Maximum quadtree depth
- `FRAME_DURATION`: Playback speed (seconds per frame)

## License

Part of the camhack2025 project.
