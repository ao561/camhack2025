import tkinter as tk
from PIL import Image, ImageTk
import random

def create_image_mosaic(image_path, grid_cols=10, grid_rows=10):
    # Get screen dimensions
    temp_root = tk.Tk()
    screen_width = temp_root.winfo_screenwidth()
    screen_height = temp_root.winfo_screenheight()
    temp_root.destroy()
    
    # Load and resize image to fit screen
    img = Image.open(image_path)
    img = img.resize((screen_width - 100, screen_height - 100), Image.Resampling.LANCZOS)
    img_width, img_height = img.size
    
    # Calculate slice dimensions (with variation for different sizes)
    base_slice_width = img_width // grid_cols
    base_slice_height = img_height // grid_rows
    
    windows = []
    titlebar_height = 31  # Approximate for Windows, will measure actual
    root = None  # Will be set later
    
    def close_all_windows(event=None):
        for window in windows:
            try:
                window.destroy()
            except:
                pass
        if root:
            try:
                root.quit()
                root.destroy()
            except:
                pass
    
    # Create first window to measure actual titlebar height
    first_window = tk.Tk()
    first_window.title("Measuring...")
    first_window.geometry(f"{base_slice_width}x{base_slice_height}+0+0")
    first_window.update()
    titlebar_height = first_window.winfo_rooty() - first_window.winfo_y()
    first_window.destroy()
    
    start_x = 50
    start_y = 50
    current_y = start_y
    
    # Create main root window (hidden)
    root = tk.Tk()
    root.withdraw()  # Hide the root window
    
    # Bind quit keys to root window as well
    root.bind('<q>', close_all_windows)
    root.bind('<Q>', close_all_windows)
    root.bind('<Escape>', close_all_windows)
    
    for row in range(grid_rows):
        current_x = start_x
        # Vary slice height slightly for different window sizes
        slice_height = base_slice_height + random.randint(-10, 10)
        
        for col in range(grid_cols):
            # Vary slice width slightly for different window sizes
            slice_width = base_slice_width + random.randint(-10, 10)
            
            # Calculate crop box for this slice
            left = col * base_slice_width
            top = row * base_slice_height
            right = min(left + slice_width, img_width)
            bottom = min(top + slice_height, img_height)
            
            # Crop the image slice
            img_slice = img.crop((left, top, right, bottom))
            
            # Create window (use Toplevel instead of Tk)
            window = tk.Toplevel(root)
            window.title("")  # Empty title for cleaner look
            
            # Position window with overlap to hide title bar
            if row > 0:
                window_y = current_y - titlebar_height
            else:
                window_y = current_y
            
            window.geometry(f"{slice_width}x{slice_height}+{current_x}+{window_y}")
            
            # Display image slice
            photo = ImageTk.PhotoImage(img_slice)
            label = tk.Label(window, image=photo, bd=0, highlightthickness=0)
            label.image = photo  # Keep a reference
            label.pack(fill=tk.BOTH, expand=True)
            
            # Bind 'q' key to close all windows - bind to both window and label
            window.bind('<q>', close_all_windows)
            window.bind('<Q>', close_all_windows)
            window.bind('<Escape>', close_all_windows)
            label.bind('<q>', close_all_windows)
            label.bind('<Q>', close_all_windows)
            label.bind('<Escape>', close_all_windows)
            
            # Give the window focus ability
            window.focus_force()
            
            windows.append(window)
            
            current_x += slice_width
        
        current_y += slice_height
    
    tk.mainloop()

if __name__ == "__main__":
    # Replace with your image path
    image_path = "rick.jpg"  # Change this to your image file
    create_image_mosaic(image_path, grid_cols=10, grid_rows=10)
