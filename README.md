# Shatter

Shatter is a visual art project that deconstructs images, videos, and real-time streams into an animated mosaic of native macOS windows. Using a variance-based quadtree algorithm, it breaks down visual media into colored rectangular blocks, which are then rendered as individual, overlapping windows on the user's desktop.

The system features a comprehensive web-based UI for managing input sources, including file uploads, screen capture, and webcam feeds, all processed and orchestrated by a Python backend.

## Key Features

-   **Multiple Input Sources**: Process static images (PNG, JPG), videos (MP4, WEBM), real-time screen captures, and live webcam feeds.
-   **Quadtree Decomposition**: Analyzes input frames to generate a set of colored rectangular blocks based on visual complexity.
-   **Native Window Rendering**: Utilizes a compiled macOS binary (`WindowCreator`) to render the blocks as actual, movable windows on the desktop.
-   **Frame Differencing Optimization**: For video and real-time streams, only the regions that change between frames are updated, dramatically improving performance.
-   **Web-Based Control Panel**: An intuitive frontend to upload media, start/stop captures, and control the display, all from your browser.
-   **Aspect Ratio Preservation**: Automatically calculates and maintains the correct aspect ratio for uploaded images and videos.

## How It Works

Shatter's architecture combines a web frontend, a Python backend server, and a native macOS application for rendering.

1.  **Frontend Interface (`static/`)**: A user interacts with the web UI at `http://localhost:5000` to select an input source (image, video, etc.) and configure settings.
2.  **Flask Backend (`server.py`)**: The server receives the user's request.
    -   For **uploads**, it saves the file.
    -   For **video**, it extracts frames using OpenCV.
    -   For **real-time capture**, it starts a background thread using `mss` (screen) or `cv2` (webcam) to continuously save frames to a directory.
3.  **WindowCreator (macOS App)**: When the user starts the display, the server executes the compiled `WindowCreator` binary.
4.  **Python Processing (`get_block2.py` & `faster_simon.py`)**: `WindowCreator` calls the `get_block2.py` script. This script reads the input frame(s), compares them against a cached previous frame (`prev_frame.jpg`) to find differences, and runs a variance-based algorithm to generate a JSON list of colored rectangular blocks.
5.  **Rendering**: `WindowCreator` parses the JSON output and creates, moves, or updates the corresponding native macOS windows on the screen, creating the "shattered" effect.

## Setup and Installation

This project is designed for **macOS** due to its reliance on the Cocoa framework for window creation.

### 1. Prerequisites

-   macOS
-   Python 3.x
-   Xcode Command Line Tools (for the `clang++` compiler)
    ```sh
    xcode-select --install
    ```

### 2. Clone the Repository

```sh
git clone https://github.com/ao561/shatter_camhack2025.git
cd shatter_camhack2025/main files
```

### 3. Install Python Dependencies

Install the required Python packages using pip.

```sh
pip install -r requirements.txt
```

### 4. Compile the Native Application

Compile the `WindowCreator` application using `clang++`. This binary is responsible for drawing the windows on your screen.

```sh
clang++ -std=c++17 main_simon.mm -framework Cocoa -framework Foundation -O2 -o WindowCreator
```
*Note: If you encounter issues, you may have other `.mm` files. `main_simon.mm` is the correct source for `WindowCreator`.*

## Usage

### 1. Start the Server

Run the Flask server from the `main files` directory.

```sh
python server.py
```

### 2. Open the Web Interface

Open your web browser and navigate to:

**http://localhost:5000**

### 3. Choose an Input Source

-   **Image**: Upload a single image file. The display will be static.
-   **Video**: Upload a video file. Configure the desired FPS for frame extraction.
-   **Screen Capture**: Capture your screen in real-time. Click "Start Capture," wait a few seconds, then "Stop Capture."
-   **Webcam**: Capture from your webcam. Works just like screen capture.

### 4. Start the Display

After processing your chosen input, the "Frames" count in the status bar will update. Click the **`Start Quadtree Display`** button to begin the animation.

### 5. Stop the Display

Click the **`Stop Display`** button in the web UI or press the `q` or `Esc` key while the windows are active to close them.

## Core Components

-   `server.py`: The main Flask backend. It handles HTTP requests, manages file storage (`uploads/`, `frames/`), and orchestrates the capture and display processes.
-   `WindowCreator`: The compiled C++/Objective-C application that reads block data and renders the native macOS windows.
-   `get_block2.py`: A Python script called by `WindowCreator`. It uses frame differencing against a cached `prev_frame.jpg` to identify changed regions and generates the final list of rectangular blocks to be rendered.
-   `faster_simon.py`: Contains the core variance-based, probabilistic algorithm for decomposing an image into a set of colored blocks.
-   `static/`: Contains the HTML, CSS, and JavaScript for the user-friendly web interface.

## Troubleshooting

-   **WindowCreator not found**: Make sure you have successfully compiled `main_simon.mm` into a binary named `WindowCreator` in the `main files` directory as described in the setup instructions.
-   **Screen Capture Not Working on macOS**: You must grant screen recording permissions to your Terminal or the IDE you are using. Go to `System Settings > Privacy & Security > Screen Recording` and add your application.
-   **Webcam Not Found**: Ensure no other application is currently using your webcam. Grant camera access if your system prompts you.
-   **Permission Denied Errors**: If you encounter permission errors when running the script or compiling, ensure the files have the correct executable permissions (`chmod +x WindowCreator`).
