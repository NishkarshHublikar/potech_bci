"""
Requires: pip install pyserial
Run in a standalone Python process (close any Serial Monitor first so COM port is free)
"""

import atexit
import queue
import serial
import threading
import time
from collections import deque
import tkinter as tk

# ---------- USER CONFIG ----------
PORT = "COM9"         # change to your port if needed
BAUD = 9600           # change to match Serial.begin(...) on ESP
THRESHOLD = 120.0      # dead-zone threshold (absolute). Adjust to your needs
SMOOTH_WINDOW = 8     # moving average window (samples)
MAX_SIGNAL = 500.0    # value mapped to full brightness (10). adjust to your signal range
USE_SMOOTH = False    # whether the bulb uses smoothed value or raw value to decide
# ---------------------------------

# safe queue to pass values from serial thread to GUI/main thread
val_queue = queue.Queue()
stop_event = threading.Event()


def open_serial(port: str, baud: int):
    try:
        ser = serial.Serial(port, baud, timeout=1)
        # allow device to reboot after opening the port
        time.sleep(2.0)
        print("Connected to", ser.name)
        return ser
    except Exception as e:
        print("Could not open serial port:", e)
        return None


def serial_reader(ser: serial.Serial, q: "queue.Queue[float]", stop_ev: threading.Event):
    """Read lines from serial and push floats into queue."""
    while not stop_ev.is_set():
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            # try parsing float (if CSV, take first value)
            try:
                if "," in line:
                    line = line.split(",")[0]
                val = float(line)
            except ValueError:
                # ignore non-numeric lines
                continue
            q.put(val)
        except Exception as e:
            # keep running; print once every so often might help debugging
            print("Serial read error:", e)
            time.sleep(0.1)


# ---------- Tkinter bulb control ----------
class BulbApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("ESP8266 BCI Bulb (Thresholded)")
        self.canvas = tk.Canvas(root, width=320, height=420, bg="black")
        self.canvas.pack()
        # bulb circle
        self.bulb = self.canvas.create_oval(60, 30, 260, 230, fill="black", outline="white", width=2)
        # glowing halo (we will change its alpha-ish by color intensity)
        self.halo = self.canvas.create_oval(40, 10, 280, 250, fill="", outline="")
        # base
        self.canvas.create_rectangle(130, 200, 190, 290, fill="gray", outline="white")
        # status text
        self.raw_text = self.canvas.create_text(160, 310, text="Raw: --", fill="white", font=("Arial", 12))
        self.smooth_text = self.canvas.create_text(160, 335, text="Smooth: --", fill="white", font=("Arial", 12))
        mode_flag = "SMOOTH" if USE_SMOOTH else "RAW"
        self.mode_text = self.canvas.create_text(160, 360, text=f"Mode: {mode_flag}  TH={THRESHOLD}", fill="white", font=("Arial", 11))
        self.brightness_level = 0  # 0..10

    def set_brightness(self, level: int):
        """level: 0..10. Change bulb fill color according to brightness"""
        level = max(0, min(10, int(level)))
        self.brightness_level = level
        # compute color intensity; small level -> dim yellow; high level -> bright yellow
        # map 0..10 -> 0..255
        intensity = int((level / 10.0) * 255)
        intensity = max(0, min(255, intensity))
        # create a warm yellow color: (R,G,B) = (intensity, intensity, 20) -> hex
        color_hex = f"#{intensity:02x}{intensity:02x}{20:02x}"
        # create a halo color (lighter, but not too bright)
        halo_int = min(255, int(intensity * 1.0))
        halo_hex = f"#{halo_int:02x}{halo_int:02x}{10:02x}"
        # if level 0 -> turn off (black)
        if level == 0:
            self.canvas.itemconfig(self.bulb, fill="black")
            self.canvas.itemconfig(self.halo, fill="")
        else:
            self.canvas.itemconfig(self.bulb, fill=color_hex)
            self.canvas.itemconfig(self.halo, fill=halo_hex)

    def update_texts(self, raw: float, smooth: float):
        self.canvas.itemconfig(self.raw_text, text=f"Raw: {raw:.2f}")
        self.canvas.itemconfig(self.smooth_text, text=f"Smooth: {smooth:.2f}")


# ---------- helper functions ----------
def compute_moving_average(window_deque: deque, new_val: float) -> float:
    window_deque.append(new_val)
    return sum(window_deque) / len(window_deque)


def map_to_brightness(value_abs: float, threshold: float, max_signal: float) -> int:
    """
    Map absolute value (after thresholding) to 0..10 brightness.
    value_abs: absolute signal
    threshold: threshold below which it's considered off
    max_signal: value that maps to brightness 10
    """
    if value_abs <= threshold:
        return 0
    # linear mapping
    denom = (max_signal - threshold) if (max_signal - threshold) != 0 else 1.0
    normalized = (value_abs - threshold) / denom
    level = int(normalized * 10.0)
    if level < 0:
        level = 0
    if level > 10:
        level = 10
    return level


# ---------- main logic tying serial -> filter -> bulb ----------
def run_app():
    ser = open_serial(PORT, BAUD)
    if ser is None:
        print("Serial open failed. Make sure port and baud are correct and the port is free.")
        return

    # start reader thread
    t = threading.Thread(target=serial_reader, args=(ser, val_queue, stop_event), daemon=True)
    t.start()

    root = tk.Tk()
    app = BulbApp(root)

    # deque for smoothing
    window = deque(maxlen=SMOOTH_WINDOW)
    last_print_time = 0.0

    def poll_queue_and_update():
        nonlocal last_print_time
        updated = False
        raw_val = None
        smooth_val = None

        # consume all queued values, but keep last (for smoothing)
        while not val_queue.empty():
            try:
                raw_val = val_queue.get_nowait()
            except queue.Empty:
                break
            # update moving average
            smooth_val = compute_moving_average(window, raw_val)
            updated = True

        # if we got at least one new value, process it
        if updated and raw_val is not None and smooth_val is not None:
            # Decide whether to use smoothed value or raw to trigger bulb
            used_value = smooth_val if USE_SMOOTH else raw_val
            used_abs = abs(used_value)

            # get brightness
            level = map_to_brightness(used_abs, THRESHOLD, MAX_SIGNAL)
            app.set_brightness(level)

            # print to console occasionally for debugging / logging; do not flood
            now = time.time()
            if now - last_print_time > 0.05:  # print at most 20 Hz
                # print both raw and smoothed and brightness
                print(
                    f"Signal raw: {raw_val:.2f}  smooth: {smooth_val:.2f}  -> abs: {used_abs:.2f}  brightness: {level}"
                )
                last_print_time = now

            # update GUI text
            app.update_texts(raw_val, smooth_val)

        # schedule next poll
        root.after(20, poll_queue_and_update)  # poll every 20 ms

    # start polling loop
    root.after(20, poll_queue_and_update)

    # clean close on exit
    def on_close():
        stop_event.set()
        try:
            if ser and ser.is_open:
                ser.close()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    atexit.register(on_close)

    root.mainloop()


if __name__ == "__main__":
    run_app()


