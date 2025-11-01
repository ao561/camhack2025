import math
import time
import tkinter as tk
from typing import Callable


TOTAL_WINDOWS = 100
WINDOW_SIZE = 30  # pixels
WINDOW_PADDING = 5  # pixels
MAX_COLUMNS = 10
VISIBLE_DURATION_MS = 2000  # how long each batch stays visible
PAUSE_DURATION_MS = 2000  # pause between batches
TOTAL_RUNTIME_SECONDS = 10
COLORS = (["white"] * (TOTAL_WINDOWS // 2)) + (["black"] * (TOTAL_WINDOWS // 2))


def create_window(
    root: tk.Tk,
    color: str,
    index: int,
    columns: int,
    base_x: int,
    base_y: int,
    on_close: Callable[[tk.Toplevel], None],
) -> tk.Toplevel:
    """Create and place a single colored window."""
    window = tk.Toplevel(root)
    row = index // columns
    column = index % columns
    x_offset = base_x + WINDOW_PADDING + column * (WINDOW_SIZE + WINDOW_PADDING)
    y_offset = base_y + WINDOW_PADDING + row * (WINDOW_SIZE + WINDOW_PADDING)

    window.geometry(f"{WINDOW_SIZE}x{WINDOW_SIZE}+{x_offset}+{y_offset}")
    window.configure(bg=color)
    window.overrideredirect(False)
    window.resizable(False, False)

    # Ensure black windows use white text if titles are shown, though canvas is empty.
    window.option_add("*Foreground", "white" if color == "black" else "black")
    window.protocol("WM_DELETE_WINDOW", lambda win=window: on_close(win))
    return window


def main() -> None:
    root = tk.Tk()
    columns = min(MAX_COLUMNS, TOTAL_WINDOWS)
    rows = math.ceil(TOTAL_WINDOWS / columns)

    # Center the grid roughly on screen by shifting the first window.
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    total_width = columns * WINDOW_SIZE + (columns + 1) * WINDOW_PADDING
    total_height = rows * WINDOW_SIZE + (rows + 1) * WINDOW_PADDING
    start_x = max((screen_width - total_width) // 2, 0)
    start_y = max((screen_height - total_height) // 2, 0)

    root.withdraw()

    windows: list[tk.Toplevel] = []
    profile_data: list[dict[str, float]] = []
    run_start = time.perf_counter()
    finished = False

    def all_windows_gone() -> bool:
        return not any(w.winfo_exists() for w in windows)

    def summarize_and_exit() -> None:
        nonlocal finished
        if finished:
            return
        finished = True
        total_elapsed = time.perf_counter() - run_start
        print(f"Completed window cycles in {total_elapsed:.2f} seconds.")
        if profile_data:
            avg_open = sum(entry["open_duration"] for entry in profile_data) / len(
                profile_data
            )
            avg_close = sum(
                entry.get("close_duration", 0.0) for entry in profile_data
            ) / len(profile_data)
            print(f"Average open time: {avg_open * 1000:.2f} ms")
            print(f"Average close time: {avg_close * 1000:.2f} ms")
            for entry in profile_data:
                close_ms = entry.get("close_duration")
                close_str = (
                    f"{close_ms * 1000:.2f} ms" if close_ms is not None else "N/A"
                )
                print(
                    f"Cycle {entry['cycle']:02d}: open {entry['open_duration'] * 1000:.2f} ms, close {close_str}"
                )
        root.quit()

    def on_window_close(window: tk.Toplevel) -> None:
        if window in windows:
            windows.remove(window)
        if window.winfo_exists():
            window.destroy()
        if all_windows_gone():
            # If user closes everything manually, schedule a pause before reopening.
            if time.perf_counter() - run_start < TOTAL_RUNTIME_SECONDS and not finished:
                root.after(PAUSE_DURATION_MS, spawn_windows)
            else:
                summarize_and_exit()

    def close_windows(entry: dict[str, float]) -> None:
        close_start = time.perf_counter()
        for win in list(windows):
            if win.winfo_exists():
                win.destroy()
            if win in windows:
                windows.remove(win)
        entry["close_duration"] = time.perf_counter() - close_start
        print(
            f"Cycle {entry['cycle']:02d} closed {TOTAL_WINDOWS} windows in "
            f"{entry['close_duration'] * 1000:.2f} ms"
        )
        if time.perf_counter() - run_start < TOTAL_RUNTIME_SECONDS:
            root.after(PAUSE_DURATION_MS, spawn_windows)
        else:
            summarize_and_exit()

    def spawn_windows() -> None:
        if finished:
            return
        elapsed = time.perf_counter() - run_start
        if elapsed >= TOTAL_RUNTIME_SECONDS:
            summarize_and_exit()
            return

        windows.clear()
        cycle_index = len(profile_data) + 1
        open_start = time.perf_counter()
        for index, color in enumerate(COLORS):
            window = create_window(
                root, color, index, columns, start_x, start_y, on_window_close
            )
            windows.append(window)
        open_duration = time.perf_counter() - open_start
        entry: dict[str, float] = {"cycle": cycle_index, "open_duration": open_duration}
        profile_data.append(entry)
        print(
            f"Cycle {cycle_index:02d} opened {TOTAL_WINDOWS} windows in "
            f"{open_duration * 1000:.2f} ms"
        )
        root.after(VISIBLE_DURATION_MS, lambda e=entry: close_windows(e))

    root.after(0, spawn_windows)

    # Keep references to prevent garbage collection.
    root.windows = windows  # type: ignore[attr-defined]
    root.mainloop()
    root.destroy()


if __name__ == "__main__":
    main()
