import tkinter as tk
import random

def create_scattered_windows():
    # Get screen dimensions from a temporary root window
    temp_root = tk.Tk()
    screen_width = temp_root.winfo_screenwidth()
    screen_height = temp_root.winfo_screenheight()
    temp_root.destroy()
    
    windows = []
    
    def close_all_windows(event=None):
        for window in windows:
            try:
                window.destroy()
            except:
                pass
    
    for i in range(100):
        window = tk.Tk()
        window.title(f"Window {i+1}")
        
        # Set window size
        window_width = 200
        window_height = 150
        
        # Random position on screen
        x = random.randint(0, screen_width - window_width)
        y = random.randint(0, screen_height - window_height)
        
        window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # Add a label to identify the window
        label = tk.Label(window, text=f"Window #{i+1}", font=("Arial", 14))
        label.pack(expand=True)
        
        # Bind 'q' key to close all windows
        window.bind('<q>', close_all_windows)
        
        windows.append(window)
    
    # Start the main event loop
    tk.mainloop()

if __name__ == "__main__":
    create_scattered_windows()
