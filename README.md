# 🎨 Shatter

Shatter is a unique visual art project that deconstructs images, videos, and real-time streams into an animated mosaic of native macOS windows. Inspired by creative media like Animator vs Animation, Shatter is an unconventional rendering software that uses individual, overlapping windows on a user's desktop to form an image.

The result is a dynamic, "shattered" effect created by colored rectangular blocks, each rendered as a separate, movable macOS window.

## 🌟 Key Features

-   **Native Window Rendering**: Utilizes a compiled macOS binary (`WindowCreator` based on the Cocoa framework) to render blocks as actual, movable windows, providing the project's signature effect.
-   **Multiple Input Sources**: Supports static images, videos, real-time screen captures, and live webcam feeds.
-   **Optimized Decomposition**: Features a variance-based quadtree algorithm combined with a probabilistic sampler for efficient image deconstruction.
-   **Performance Optimization**: Employs Frame Differencing to only update regions that change between frames, dramatically improving video and real-time stream performance.
-   **Web-Based Control Panel**: An intuitive HTML/Flask frontend for managing input sources, configuring settings, and starting/stopping the display.
-   **Aspect Ratio Preservation**: Automatically calculates and maintains the correct aspect ratio for uploaded images and videos.

## 🛠️ How It Works: System Architecture



Shatter operates using a three-part architecture:

1.  **Frontend Interface (`static/`)**: A user interacts with the Flask web UI at `http://localhost:5000` to select media or a live feed.
2.  **Flask Backend (`server.py`)**:
    * Handles HTTP requests and manages file storage.
    * Extracts video frames (using OpenCV) or initiates real-time frame capture (using `mss` for screen or `cv2` for webcam).
    * Orchestrates the entire process.
3.  **Core Processing & Rendering**:
    * The compiled `WindowCreator` (Objective-C/C++) application is executed by the server.
    * `WindowCreator` calls the Python processing scripts (`get_block2.py` / `faster_simon.py`). These scripts perform the frame differencing and the probabilistic, variance-based decomposition to generate the JSON block data.
    * `WindowCreator` reads the JSON and creates, moves, or updates the native macOS windows on the desktop, realizing the "shattered" animation.

## 💡 The Journey and Technical Breakthroughs

The project began by experimenting with Python's Tkinter on Windows, but the initial performance was extremely poor (capping at an unusable 1 FPS).

We shifted development to **macOS** and experimented with **Objective-C** for window handling. This move immediately produced a significant performance increase, achieving 10-15 FPS with the original quadtree code.

The final performance breakthrough came from implementing a new, optimized approach:

-   **Probabilistic Sampler**: Instead of searching the entire image on every frame, the algorithm was modified to focus on regions of high deviation (where the image changed most).
-   **Frame Differencing Optimization**: By iterating upon previous frames and only updating the blocks that had changed, the system achieved an amazing performance boost and seamless transitions between frames.

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
git clone [https://github.com/ao561/shatter_camhack2025.git](https://github.com/ao561/shatter_camhack2025.git)
cd shatter_camhack2025/main files
```

### 3. Install Python Dependencies

Install the required Python packages using pip.

```sh
pip install -r requirements.txt
```

### 4. Compile the Native Application

Compile the WindowCreator application using clang++. This binary is responsible for drawing the windows on your screen.

```sh
clang++ -std=c++17 main_simon.mm -framework Cocoa -framework Foundation -O2 -o WindowCreator
```
Note: If you encounter issues, you may have other .mm files. main_simon.mm is the correct source for WindowCreator.

## Usage

### 1. Start the server
Run the Flask server from the main files directory.
```sh
python server.py
```
### 2. Open the web interface
Open your web browser and navigate to:
http://localhost:5000

### 3. Choose an Input Source
-   **Image**: Upload a single image file. The display will be static.
-   **Video**: Upload a video file. Configure the desired FPS for frame extraction.
-   **Screen Capture**: Capture your screen in real-time. Click "Start Capture," wait a few seconds, then "Stop Capture."
-   **Webcam**: Capture from your webcam. Works just like screen capture.

### 4. Start the Display
After processing your chosen input, the "Frames" count in the status bar will update. Click the Start Quadtree Display button to begin the animation.

### 5. Stop the Display
Click the Stop Display button in the web UI or press the q or Esc key while the windows are active to close them.

## Core Components

-   **server.py**: The main Flask backend. It handles HTTP requests, manages file storage (uploads/, frames/), and orchestrates the capture and display processes.
-   **WindowCreator**: The compiled C++/Objective-C application that reads block data from JSON and renders the native macOS windows.
-   **get_block2.py**: A Python script called by WindowCreator. It uses frame differencing against a cached prev_frame.jpg to identify changed regions.
-   **faster_simon.py**: Contains the core probabilistic, variance-based decomposition algorithm for breaking an image into a set of colored blocks.
-   **static/**: Contains the HTML, CSS, and JavaScript for the user-friendly web interface.

## Troubleshooting

-   **WindowCreator not found**: Make sure you have successfully compiled main_simon.mm into a binary named WindowCreator in the main files directory as described in the setup instructions.
-   **Screen Capture Not Working on macOS**: You must grant screen recording permissions to your Terminal or the IDE you are using. Go to System Settings > Privacy & Security > Screen Recording and add your application.
-   **Webcam Not Found**: Ensure no other application is currently using your webcam. Grant camera access if your system prompts you.
-   **Permission Denied Errors**: If you encounter permission errors when running the script or compiling, ensure the files have the correct executable permissions (chmod +x WindowCreator).
