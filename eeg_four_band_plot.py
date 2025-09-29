"""
Live COM-port EEG reader that bandpass-filters into four bands (delta, alpha, beta, gamma)
and live-plots them in a 2x2 figure.

Requires: pip install pyserial numpy scipy matplotlib
Run: python eeg_four_band_plot.py
"""

import time
import serial
import threading
from collections import deque
import queue

import numpy as np
from scipy import signal
import matplotlib.pyplot as plt

# ---------- USER CONFIG ----------
PORT = "COM9"       # change to your COM port  
BAUD = 9600         # match your device (same as bulb_bci.py)
SAMPLE_RATE = 250   # Hz (approx sampling rate of incoming data)
BUFFER_SIZE = 2000  # samples kept for plotting
# ---------------------------------


class FourBandFilters:
    def __init__(self, sample_rate: int):
        self.sample_rate = sample_rate
        self.nyquist = sample_rate / 2.0
        self.filters = {}
        self.zi = {}
        bands_hz = {
            "delta": (0.5, 4),
            "alpha": (8, 13),
            "beta": (13, 30),
            "gamma": (30, 100),
        }
        for name, (lo, hi) in bands_hz.items():
            lo_n = lo / self.nyquist
            hi_n = hi / self.nyquist
            sos = signal.butter(4, [lo_n, hi_n], btype="band", output="sos")
            self.filters[name] = sos
            self.zi[name] = signal.sosfilt_zi(sos)

    def apply(self, sample: float):
        out = {}
        for name, sos in self.filters.items():
            y, self.zi[name] = signal.sosfilt(sos, [sample], zi=self.zi[name])
            out[name] = float(y[0])
        return out


class SerialEEGReader:
    def __init__(self, port: str, baud: int):
        self.port = port
        self.baud = baud
        self.ser = None
        self.thread = None
        self.stop_flag = threading.Event()
        self.val_queue = queue.Queue()

    def open(self):
        try:
            print(f"Attempting to open {self.port} at {self.baud} baud...")
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            # allow device to reboot after opening the port
            print("Waiting 2 seconds for device initialization...")
            time.sleep(2.0)
            print(f"Successfully connected to {self.ser.name}")
            print(f"Serial port settings: {self.ser.baudrate} baud, timeout={self.ser.timeout}s")
            return True
        except Exception as e:
            print(f"Could not open serial port {self.port}: {e}")
            print("Make sure:")
            print("1. The device is connected to the correct port")
            print("2. No other application is using the port (close Serial Monitor)")
            print("3. The baud rate matches your device settings")
            return False

    def _read_loop(self):
        """Read lines from serial and push floats into queue (based on bulb_bci.py)."""
        last_print = 0
        while not self.stop_flag.is_set():
            try:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                # try parsing float (if CSV, take first value)
                try:
                    if "," in line:
                        line = line.split(",")[0]
                    val = float(line)
                    self.val_queue.put(val)
                    
                    # Debug print occasionally (every 50 samples to avoid flooding)
                    last_print += 1
                    if last_print % 50 == 0:
                        print(f"Raw EEG (sample {last_print}): {val:.2f}")
                        
                except ValueError:
                    # ignore non-numeric lines
                    continue
            except Exception as e:
                # keep running; print once every so often might help debugging
                print(f"Serial read error: {e}")
                time.sleep(0.1)

    def start(self):
        if not self.open():
            return False
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        return True

    def read_latest(self):
        """Read all available values from queue and return the latest one."""
        latest_val = None
        while not self.val_queue.empty():
            try:
                latest_val = self.val_queue.get_nowait()
            except queue.Empty:
                break
        return latest_val

    def close(self):
        self.stop_flag.set()
        try:
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=1.0)
        except Exception:
            pass
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass


def main():
    filters = FourBandFilters(SAMPLE_RATE)
    reader = SerialEEGReader(PORT, BAUD)
    
    print(f"Attempting to connect to {PORT} at {BAUD} baud...")
    if not reader.start():
        print("Could not open serial port!")
        print("Make sure the port and baud are correct and the port is free.")
        print("Falling back to synthetic generator...")
        main_fall(0)
        return
    
    print("Serial connection established. Starting EEG data acquisition...")

    raw_buffer = deque(maxlen=BUFFER_SIZE)
    band_buffers = {
        "delta": deque(maxlen=BUFFER_SIZE),
        "alpha": deque(maxlen=BUFFER_SIZE),
        "beta": deque(maxlen=BUFFER_SIZE),
        "gamma": deque(maxlen=BUFFER_SIZE),
    }

    plt.ion()
    fig, axes = plt.subplots(2, 2, figsize=(12, 6))
    axes = axes.flatten()

    plot_lines = {}
    plot_cfg = [
        ("delta", "Delta (0.5-4 Hz)", "purple"),
        ("alpha", "Alpha (8-13 Hz)", "green"),
        ("beta",  "Beta (13-30 Hz)", "orange"),
        ("gamma", "Gamma (30-100 Hz)", "red"),
    ]
    for ax, (name, title, color) in zip(axes, plot_cfg):
        ax.set_title(title)
        ax.set_xlabel("Samples")
        ax.set_ylabel("Amplitude")
        ax.grid(True, alpha=0.3)
        (line,) = ax.plot([], [], color=color, linewidth=1)
        plot_lines[name] = line
    fig.tight_layout()

    print("Reading from", PORT, "at", BAUD, "baud. Close the figure window to stop.")

    try:
        last_ui = time.time()
        last_debug = time.time()
        sample_count = 0
        
        while plt.fignum_exists(fig.number):
            sample = reader.read_latest()
            if sample is None:
                plt.pause(0.001)
                continue

            raw_buffer.append(sample)
            bands = filters.apply(sample)
            for name in band_buffers:
                band_buffers[name].append(bands[name])
            
            sample_count += 1
            
            # Debug output every 2 seconds
            now = time.time()
            if now - last_debug > 2.0:
                print(f"Samples processed: {sample_count}, Raw: {sample:.2f}")
                print(f"  Delta: {bands['delta']:.3f}, Alpha: {bands['alpha']:.3f}")
                print(f"  Beta: {bands['beta']:.3f}, Gamma: {bands['gamma']:.3f}")
                print("---")
                last_debug = now

            # Update plots at ~20 Hz
            if now - last_ui > 0.05:
                for i, (name, _, _) in enumerate(plot_cfg):
                    data = list(band_buffers[name])
                    plot_lines[name].set_data(range(len(data)), data)
                    axes[i].relim()
                    axes[i].autoscale_view()
                plt.pause(0.001)
                last_ui = now

        plt.ioff()
    finally:
        reader.close()
        try:
            plt.close(fig)
        except Exception:
            pass
        print("Stopped.")


def main_fall(mode: int = 0):
    """
    Fallback mode that generates synthetic EEG-like raw samples and plots four bands.
    mode: reserved for future scenarios; 0 = mixed amplitudes cycling low/moderate/high.
    """
    filters = FourBandFilters(SAMPLE_RATE)

    raw_buffer = deque(maxlen=BUFFER_SIZE)
    band_buffers = {
        "delta": deque(maxlen=BUFFER_SIZE),
        "alpha": deque(maxlen=BUFFER_SIZE),
        "beta": deque(maxlen=BUFFER_SIZE),
        "gamma": deque(maxlen=BUFFER_SIZE),
    }

    plt.ion()
    fig, axes = plt.subplots(2, 2, figsize=(12, 6))
    axes = axes.flatten()

    plot_lines = {}
    plot_cfg = [
        ("delta", "Delta (0.5-4 Hz)", "purple"),
        ("alpha", "Alpha (8-13 Hz)", "green"),
        ("beta",  "Beta (13-30 Hz)", "orange"),
        ("gamma", "Gamma (30-100 Hz)", "red"),
    ]
    for ax, (name, title, color) in zip(axes, plot_cfg):
        ax.set_title(title)
        ax.set_xlabel("Samples")
        ax.set_ylabel("Amplitude")
        ax.grid(True, alpha=0.3)
        (line,) = ax.plot([], [], color=color, linewidth=1)
        plot_lines[name] = line
    fig.tight_layout()

    print("Synthetic fallback running (mode=0). Close the figure window to stop.")

    # time state
    t = 0.0
    dt = 1.0 / float(SAMPLE_RATE)
    last_ui = time.time()

    # schedule: 8s low, 8s moderate, 8s high, repeat
    segment_len_s = 8.0
    segment_samples = int(segment_len_s * SAMPLE_RATE)
    seg_names = ["low", "moderate", "high"]
    seg_idx = 0
    seg_count = 0

    # base frequencies (Hz) for composing raw signal
    f_delta = 2.0
    f_alpha = 10.0
    f_beta  = 20.0
    f_gamma = 40.0

    try:
        while plt.fignum_exists(fig.number):
            # choose amplitude by segment
            seg = seg_names[seg_idx]
            if seg == "low":
                a_delta, a_alpha, a_beta, a_gamma = 30.0, 20.0, 10.0, 5.0
                noise_scale = 5.0
            elif seg == "moderate":
                a_delta, a_alpha, a_beta, a_gamma = 60.0, 40.0, 25.0, 15.0
                noise_scale = 10.0
            else:  # high
                a_delta, a_alpha, a_beta, a_gamma = 120.0, 90.0, 60.0, 40.0
                noise_scale = 15.0

            # compose raw
            raw = (
                a_delta * np.sin(2 * np.pi * f_delta * t)
                + a_alpha * np.sin(2 * np.pi * f_alpha * t + 0.7)
                + a_beta  * np.sin(2 * np.pi * f_beta  * t + 1.3)
                + a_gamma * np.sin(2 * np.pi * f_gamma * t + 2.1)
                + np.random.normal(0.0, noise_scale)
            )

            raw_buffer.append(raw)
            bands = filters.apply(raw)
            for name in band_buffers:
                band_buffers[name].append(bands[name])

            # update segment
            seg_count += 1
            if seg_count >= segment_samples:
                seg_count = 0
                seg_idx = (seg_idx + 1) % len(seg_names)

            # advance time
            t += dt

            # Update plots at ~20 Hz
            now = time.time()
            if now - last_ui > 0.05:
                for i, (name, _, _) in enumerate(plot_cfg):
                    data = list(band_buffers[name])
                    plot_lines[name].set_data(range(len(data)), data)
                    axes[i].relim()
                    axes[i].autoscale_view()
                plt.pause(0.001)
                last_ui = now

    finally:
        try:
            plt.close(fig)
        except Exception:
            pass
        print("Stopped (synthetic fallback).")


if __name__ == "__main__":
    main()
    # main_fall()



