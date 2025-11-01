// app.js - Frontend JavaScript for Quadtree Input Manager

const API_BASE = '';

// State
let captureInterval = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initImageUpload();
    initVideoUpload();
    initScreenCapture();
    initWebcamCapture();
    initDisplayControls();
    updateStatus();
    
    // Auto-update status every 2 seconds
    setInterval(updateStatus, 2000);
});

// Tab Management
function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.dataset.tab;
            
            // Update active states
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            button.classList.add('active');
            document.getElementById(`${tabName}-tab`).classList.add('active');
        });
    });
}

// Image Upload
function initImageUpload() {
    const input = document.getElementById('image-input');
    const dropZone = document.getElementById('image-drop-zone');
    const preview = document.getElementById('image-preview');
    const previewImg = document.getElementById('image-preview-img');
    
    input.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleImageFile(e.target.files[0]);
        }
    });
    
    // Drag and drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        
        if (e.dataTransfer.files.length > 0) {
            handleImageFile(e.dataTransfer.files[0]);
        }
    });
    
    function handleImageFile(file) {
        // Show preview
        const reader = new FileReader();
        reader.onload = (e) => {
            previewImg.src = e.target.result;
            preview.style.display = 'block';
        };
        reader.readAsDataURL(file);
        
        // Upload
        const formData = new FormData();
        formData.append('file', file);
        
        showMessage('Uploading image...', 'info');
        
        fetch(`${API_BASE}/api/upload/image`, {
            method: 'POST',
            body: formData
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showMessage(data.error, 'error');
            } else {
                showMessage(data.message, 'success');
                updateStatus();
            }
        })
        .catch(err => {
            showMessage('Upload failed: ' + err.message, 'error');
        });
    }
}

// Video Upload
function initVideoUpload() {
    const input = document.getElementById('video-input');
    const dropZone = document.getElementById('video-drop-zone');
    const preview = document.getElementById('video-preview');
    const previewPlayer = document.getElementById('video-preview-player');
    
    input.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleVideoFile(e.target.files[0]);
        }
    });
    
    // Drag and drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        
        if (e.dataTransfer.files.length > 0) {
            handleVideoFile(e.dataTransfer.files[0]);
        }
    });
    
    function handleVideoFile(file) {
        // Show preview
        const url = URL.createObjectURL(file);
        previewPlayer.src = url;
        preview.style.display = 'block';
        
        // Upload
        const formData = new FormData();
        formData.append('file', file);
        formData.append('fps', document.getElementById('video-fps').value);
        
        const maxFrames = document.getElementById('video-max-frames').value;
        if (maxFrames) {
            formData.append('maxFrames', maxFrames);
        }
        
        showMessage('Uploading and processing video... This may take a moment.', 'info');
        
        fetch(`${API_BASE}/api/upload/video`, {
            method: 'POST',
            body: formData
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showMessage(data.error, 'error');
            } else {
                showMessage(data.message, 'success');
                updateStatus();
            }
        })
        .catch(err => {
            showMessage('Upload failed: ' + err.message, 'error');
        });
    }
}

// Screen Capture
function initScreenCapture() {
    const startBtn = document.getElementById('screen-start-btn');
    const stopBtn = document.getElementById('screen-stop-btn');
    
    startBtn.addEventListener('click', () => {
        const fps = document.getElementById('screen-fps').value;
        const duration = document.getElementById('screen-duration').value;
        
        const payload = { fps: parseInt(fps) };
        if (duration) {
            payload.duration = parseInt(duration);
        }
        
        fetch(`${API_BASE}/api/capture/screen/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showMessage(data.error, 'error');
            } else {
                showMessage(data.message, 'success');
                startBtn.disabled = true;
                stopBtn.disabled = false;
            }
        })
        .catch(err => {
            showMessage('Failed to start capture: ' + err.message, 'error');
        });
    });
    
    stopBtn.addEventListener('click', () => {
        fetch(`${API_BASE}/api/capture/screen/stop`, {
            method: 'POST'
        })
        .then(res => res.json())
        .then(data => {
            showMessage(data.message, 'success');
            startBtn.disabled = false;
            stopBtn.disabled = true;
            updateStatus();
        })
        .catch(err => {
            showMessage('Failed to stop capture: ' + err.message, 'error');
        });
    });
}

// Webcam Capture
function initWebcamCapture() {
    const startBtn = document.getElementById('webcam-start-btn');
    const stopBtn = document.getElementById('webcam-stop-btn');
    
    startBtn.addEventListener('click', () => {
        const fps = document.getElementById('webcam-fps').value;
        const duration = document.getElementById('webcam-duration').value;
        
        const payload = { fps: parseInt(fps) };
        if (duration) {
            payload.duration = parseInt(duration);
        }
        
        fetch(`${API_BASE}/api/capture/webcam/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showMessage(data.error, 'error');
            } else {
                showMessage(data.message, 'success');
                startBtn.disabled = true;
                stopBtn.disabled = false;
            }
        })
        .catch(err => {
            showMessage('Failed to start capture: ' + err.message, 'error');
        });
    });
    
    stopBtn.addEventListener('click', () => {
        fetch(`${API_BASE}/api/capture/webcam/stop`, {
            method: 'POST'
        })
        .then(res => res.json())
        .then(data => {
            showMessage(data.message, 'success');
            startBtn.disabled = false;
            stopBtn.disabled = true;
            updateStatus();
        })
        .catch(err => {
            showMessage('Failed to stop capture: ' + err.message, 'error');
        });
    });
}

// Display Controls
function initDisplayControls() {
    const startBtn = document.getElementById('display-start-btn');
    const stopBtn = document.getElementById('display-stop-btn');
    const clearBtn = document.getElementById('clear-btn');
    
    startBtn.addEventListener('click', () => {
        fetch(`${API_BASE}/api/display/start`, {
            method: 'POST'
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showMessage(data.error, 'error');
            } else {
                showMessage(data.message, 'success');
                updateStatus();
            }
        })
        .catch(err => {
            showMessage('Failed to start display: ' + err.message, 'error');
        });
    });
    
    stopBtn.addEventListener('click', () => {
        fetch(`${API_BASE}/api/display/stop`, {
            method: 'POST'
        })
        .then(res => res.json())
        .then(data => {
            showMessage(data.message, 'success');
            updateStatus();
        })
        .catch(err => {
            showMessage('Failed to stop display: ' + err.message, 'error');
        });
    });
    
    clearBtn.addEventListener('click', () => {
        if (confirm('Clear all frames? This will stop any active display.')) {
            fetch(`${API_BASE}/api/frames/clear`, {
                method: 'POST'
            })
            .then(res => res.json())
            .then(data => {
                showMessage(data.message, 'success');
                updateStatus();
            })
            .catch(err => {
                showMessage('Failed to clear frames: ' + err.message, 'error');
            });
        }
    });
}

// Status Updates
function updateStatus() {
    fetch(`${API_BASE}/api/status`)
        .then(res => res.json())
        .then(data => {
            // Update frame count
            document.getElementById('frame-count').textContent = data.frames;
            
            // Update display status
            const displayStatus = document.getElementById('display-status');
            if (data.display_active) {
                displayStatus.textContent = 'Active';
                displayStatus.className = 'value active';
                document.getElementById('display-start-btn').disabled = true;
                document.getElementById('display-stop-btn').disabled = false;
            } else {
                displayStatus.textContent = 'Inactive';
                displayStatus.className = 'value inactive';
                document.getElementById('display-start-btn').disabled = data.frames === 0;
                document.getElementById('display-stop-btn').disabled = true;
            }
            
            // Update capture status
            const captureStatus = document.getElementById('capture-status');
            if (data.capture_active) {
                captureStatus.textContent = 'Active';
                captureStatus.className = 'value active';
            } else {
                captureStatus.textContent = 'Inactive';
                captureStatus.className = 'value inactive';
            }
        })
        .catch(err => {
            console.error('Status update failed:', err);
        });
}

// Message Display
function showMessage(text, type = 'info') {
    const messagesContainer = document.getElementById('messages');
    const message = document.createElement('div');
    message.className = `message ${type}`;
    message.textContent = text;
    
    messagesContainer.insertBefore(message, messagesContainer.firstChild);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        message.style.opacity = '0';
        setTimeout(() => message.remove(), 300);
    }, 5000);
}
