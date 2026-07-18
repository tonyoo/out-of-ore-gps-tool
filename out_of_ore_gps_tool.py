import tkinter as tk
from tkinter import messagebox, filedialog
import threading
import time
import mss
from mss.exception import ScreenShotError
from pynput import keyboard
import win32api
import win32con
import win32gui
import json
import os
import math
import sys
import traceback
import logging
import copy
from datetime import datetime

LOG_FILE = "crash.log"
logging.basicConfig(filename=LOG_FILE, level=logging.WARNING,
                    format="%(asctime)s %(levelname)s: %(message)s",
                    filemode="a")

def global_excepthook(exc_type, exc_value, exc_traceback):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logging.critical(f"Unhandled exception:\n{msg}")

def thread_excepthook(args):
    msg = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    logging.critical(f"Thread exception:\n{msg}")

sys.excepthook = global_excepthook
threading.excepthook = thread_excepthook

def log_error(e, context=""):
    msg = f"{context}: {e}" if context else str(e)
    tb = traceback.format_exc()
    logging.warning(f"{msg}\n{tb}")


def get_settings_path():
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "settings.json")
    return "settings.json"


def get_version():
    """Read version from VERSION file (dev tree or bundled with the exe)."""
    candidates = []
    if getattr(sys, 'frozen', False):
        # PyInstaller one-file extracts datas into _MEIPASS
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidates.append(os.path.join(meipass, 'VERSION'))
        candidates.append(os.path.join(os.path.dirname(sys.executable), 'VERSION'))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, 'VERSION'))
    candidates.append(os.path.join(os.getcwd(), 'VERSION'))
    for path in candidates:
        try:
            if os.path.isfile(path):
                with open(path, 'r', encoding='utf-8') as f:
                    ver = f.read().strip()
                if ver:
                    return ver
        except OSError:
            continue
    return '0.0.0'


__version__ = get_version()
SETTINGS_FILE = get_settings_path()


def get_default_settings():
    """Factory defaults — matches the calibrated project settings.json."""
    return {
        "sets": [
            {"label": "Blade up", "x": 2003, "y": 201, "threshold": 200, "hotkey": "="},
            {"label": "Blade down", "x": 2004, "y": 213, "threshold": 200, "hotkey": "-"},
            {"label": "Blade left", "x": 2421, "y": 214, "threshold": 200, "hotkey": "["},
            {"label": "Blade right", "x": 2406, "y": 217, "threshold": 200, "hotkey": "]"},
            {
                "label": "Line Angle",
                "x": 1889,
                "y": 366,
                "threshold": 200,
                "x2": 2009,
                "y2": 244,
                "target_angle": 14.0,
                "hotkey_greater": "=",
                "hotkey_less": "-",
                "line_delay": 10,
                "line_hold": 50,
            },
        ],
        "global_hotkey": "f9",
        "preset_hotkeys": {
            "hotkey_1": "f6",
            "hotkey_2": "f7",
            "hotkey_3": "f8",
        },
        "press_delay": 100,
        "hold_mode": False,
        "window_width": 506,
        "window_height": 590,
        "start_includes": [True, True, True, True, True],
        "target_window": "Out Of Ore",
    }


class PixelMonitorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Out Of Ore GPS Tool v{__version__}")
        self.preview_thread = None
        self.preview_running = False
        self.active_set = 0
        self.key_lock = threading.Lock()
        self.cached_target_window = "OutOfOre"
        self.cached_press_delay = 50
        self.cached_hold_mode = False
        self.hotkey_bindings = []
        self.entries = {
            'x': [None]*5, 'y': [None]*5, 'pick_btn': [None]*5,
            'preview': [None]*5, 'hotkey': [None]*5,
            'start_btn': [None]*5, 'stop_btn': [None]*5, 'frame': [None]*5,
            'is_line_finder': [False]*5, 'x2': [None]*5, 'y2': [None]*5,
            'target_angle': [None]*5,
            'hotkey_greater': [None]*5, 'hotkey_less': [None]*5,
            'line_delay': [None]*5, 'line_hold': [None]*5,
            'indicator': [None]*5
        }
        self.running = [False]*5
        self.monitor_threads = [None]*5
        self.stop_events = [threading.Event() for _ in range(5)]

        self.load_settings()
        self.setup_gui()
        self.settings_snapshot = copy.deepcopy(self.settings)

    def setup_gui(self):
        w = self.settings.get('window_width', 750)
        h = self.settings.get('window_height', 700)
        self.root.geometry(f"{w}x{h}")

        self.main_canvas = tk.Canvas(self.root, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.root, orient="vertical", command=self.main_canvas.yview)
        self.scrollable_frame = tk.Frame(self.main_canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        )

        self.main_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.main_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.main_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.mousewheel_bind()

        sets_container = tk.Frame(self.scrollable_frame)
        sets_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        row1 = tk.Frame(sets_container)
        row1.pack(fill=tk.X)
        row2 = tk.Frame(sets_container)
        row2.pack(fill=tk.X)
        row3 = tk.Frame(sets_container)
        row3.pack(fill=tk.X)

        self.set_containers = [row1, row1, row2, row2, row3]

        for i in range(4):
            self.create_basic_set_widgets(i, self.settings['sets'][i]['label'])
            if i == 1:
                tk.Frame(self.set_containers[0], height=2, bg="gray").pack(fill=tk.X, pady=2)

        self.create_line_finder_set(4, self.settings['sets'][4]['label'])

        controls_frame = tk.LabelFrame(self.scrollable_frame, text="Controls", padx=8, pady=6)
        controls_frame.pack(fill=tk.X, padx=5, pady=(8, 4))

        controls_row1 = tk.Frame(controls_frame)
        controls_row1.pack(fill=tk.X, pady=1)
        tk.Label(controls_row1, text="Toggle All:", width=10, anchor="w").pack(side=tk.LEFT)
        self.global_hotkey_entry = tk.Entry(controls_row1, width=8)
        self.global_hotkey_entry.insert(0, self.settings.get('global_hotkey', 'f9'))
        self.global_hotkey_entry.pack(side=tk.LEFT, padx=(0, 2))
        global_rec_btn = tk.Button(controls_row1, text="Rec", width=3)
        global_rec_btn.pack(side=tk.LEFT, padx=(0, 10))
        global_rec_btn.config(command=lambda e=self.global_hotkey_entry, b=global_rec_btn: self.record_next_hotkey(e, b))
        tk.Label(controls_row1, text="Target:", width=8, anchor="w").pack(side=tk.LEFT)
        self.target_window_entry = tk.Entry(controls_row1, width=18)
        self.target_window_entry.insert(0, self.settings.get('target_window', 'Out Of Ore'))
        self.target_window_entry.pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(controls_row1, text="Delay:", width=7, anchor="w").pack(side=tk.LEFT)
        self.press_delay_entry = tk.Entry(controls_row1, width=6)
        self.press_delay_entry.insert(0, self.settings.get('press_delay', 50))
        self.press_delay_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.hold_mode_var = tk.BooleanVar(value=self.settings.get('hold_mode', False))
        tk.Checkbutton(controls_row1, text="Hold mode", variable=self.hold_mode_var).pack(side=tk.LEFT)

        controls_row2 = tk.Frame(controls_frame)
        controls_row2.pack(fill=tk.X, pady=1)

        preset_hotkeys = self.settings.get('preset_hotkeys', {})
        self.preset_hotkey_entries = []
        preset_rows = [
            ("Full", "1,2,3,4", "f6"),
            ("Auto level", "3,4", "f7"),
            ("H3", "3,4,5", "f8"),
        ]
        for index, (label, description, default_value) in enumerate(preset_rows, start=1):
            tk.Label(controls_row2, text=f"{label}:").pack(side=tk.LEFT)
            entry = tk.Entry(controls_row2, width=6)
            entry.insert(0, preset_hotkeys.get(f"hotkey_{index}", default_value))
            entry.pack(side=tk.LEFT, padx=(2, 2))
            rec_btn = tk.Button(controls_row2, text="Rec", width=3)
            rec_btn.pack(side=tk.LEFT, padx=(0, 2))
            rec_btn.config(command=lambda e=entry, b=rec_btn: self.record_next_hotkey(e, b))
            tk.Label(controls_row2, text=description).pack(side=tk.LEFT, padx=(0, 10))
            self.preset_hotkey_entries.append(entry)

        self.set_vars = []
        start_includes = self.settings.get('start_includes', [True]*5)
        for i in range(5):
            var = tk.BooleanVar(value=start_includes[i] if i < len(start_includes) else True)
            self.set_vars.append(var)

        btn_frame = tk.Frame(self.scrollable_frame)
        btn_frame.pack(pady=6)
        self.global_start_btn = tk.Button(btn_frame, text="Start All", command=self.start_all, width=12, bg="#90EE90")
        self.global_start_btn.grid(row=0, column=0, padx=3)

        self.stop_all_btn = tk.Button(btn_frame, text="Stop All", command=self.stop_all, width=12, bg="#FFB6C1", state=tk.DISABLED)
        self.stop_all_btn.grid(row=0, column=1, padx=3)

        self.save_btn = tk.Button(btn_frame, text="Save Settings", command=self.save_settings, width=12, bg="#87CEEB")
        self.save_btn.grid(row=0, column=2, padx=3)

        self.save_as_btn = tk.Button(btn_frame, text="Save As...", command=self.save_as_settings, width=12, bg="#87CEEB")
        self.save_as_btn.grid(row=0, column=3, padx=3)

        self.load_btn = tk.Button(btn_frame, text="Load", command=self.load_settings_file, width=10, bg="#FFD700")
        self.load_btn.grid(row=0, column=4, padx=3)

        self.debug_btn = tk.Button(btn_frame, text="Debug Log", command=self.open_debug_log, width=10, bg="#DDA0DD")
        self.debug_btn.grid(row=0, column=5, padx=3)

        self.status_label = tk.Label(self.scrollable_frame, text="Status: Stopped", fg="gray", font=("Arial", 11, "bold"))
        self.status_label.pack(pady=(4, 8))

        self.hotkey_listener = None
        self.hotkey_active = False
        self.keyboard_controller = keyboard.Controller()

        self.refresh_runtime_settings()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.start_preview()
        # Register F6/F7/F8/F9 (etc.) immediately — previously only after Start All
        try:
            self.setup_global_hotkey()
        except Exception as e:
            log_error(e, "startup hotkey setup")

    def open_debug_log(self):
        if os.path.exists(LOG_FILE):
            os.startfile(LOG_FILE)
        else:
            messagebox.showinfo("Debug Log", "No crash log found yet.")

    def mousewheel_bind(self):
        def _on_mousewheel(event):
            self.main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        self.main_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.main_canvas.bind("<Enter>", lambda e: self.main_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        self.main_canvas.bind("<Leave>", lambda e: self.main_canvas.unbind_all("<MouseWheel>"))

    def write_settings_file(self, settings, path=None):
        """Write settings dict to disk (default: SETTINGS_FILE)."""
        target = path or SETTINGS_FILE
        try:
            with open(target, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            return True
        except Exception as e:
            log_error(e, f"write settings file ({target})")
            return False

    def load_settings(self):
        default_settings = get_default_settings()
        created_or_reset = False

        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                self.settings = self.normalize_settings(loaded_settings, default_settings)
            except Exception as e:
                log_error(e, "load settings")
                self.settings = default_settings
                created_or_reset = True
        else:
            self.settings = default_settings
            created_or_reset = True

        if created_or_reset:
            self.write_settings_file(self.settings)

    def normalize_settings(self, settings, default_settings=None):
        if default_settings is None:
            default_settings = get_default_settings()
        else:
            default_settings = copy.deepcopy(default_settings)

        normalized = copy.deepcopy(default_settings)
        if not isinstance(settings, dict):
            settings = {}

        normalized.update({k: v for k, v in settings.items() if k != 'sets'})

        sets = settings.get('sets', [])
        normalized_sets = []
        for i, default_set in enumerate(default_settings['sets']):
            loaded_set = sets[i] if i < len(sets) and isinstance(sets[i], dict) else {}
            merged_set = dict(default_set)
            merged_set.update(loaded_set)
            normalized_sets.append(merged_set)
        normalized['sets'] = normalized_sets

        preset_defaults = default_settings.get('preset_hotkeys', {})
        loaded_presets = settings.get('preset_hotkeys', {})
        normalized['preset_hotkeys'] = dict(preset_defaults)
        if isinstance(loaded_presets, dict):
            normalized['preset_hotkeys'].update(loaded_presets)

        start_includes = settings.get('start_includes', default_settings.get('start_includes', [True] * 5))
        normalized['start_includes'] = [
            start_includes[i] if i < len(start_includes) else True
            for i in range(5)
        ]

        return normalized

    def collect_current_settings(self):
        collected = self.normalize_settings(self.settings)

        for i in range(5):
            collected['sets'][i]['x'] = int(self.entries['x'][i].get())
            collected['sets'][i]['y'] = int(self.entries['y'][i].get())
            # threshold stays settings-file only (not in UI)

            if self.entries['is_line_finder'][i]:
                collected['sets'][i]['x2'] = int(self.entries['x2'][i].get())
                collected['sets'][i]['y2'] = int(self.entries['y2'][i].get())
                collected['sets'][i]['target_angle'] = float(self.entries['target_angle'][i].get())
                collected['sets'][i]['hotkey_greater'] = self.entries['hotkey_greater'][i].get()
                collected['sets'][i]['hotkey_less'] = self.entries['hotkey_less'][i].get()
                collected['sets'][i]['line_delay'] = int(self.entries['line_delay'][i].get())
                collected['sets'][i]['line_hold'] = int(self.entries['line_hold'][i].get())
            else:
                collected['sets'][i]['hotkey'] = self.entries['hotkey'][i].get()

        collected['global_hotkey'] = self.global_hotkey_entry.get()
        collected['target_window'] = self.target_window_entry.get()
        collected['press_delay'] = int(self.press_delay_entry.get())
        collected['hold_mode'] = self.hold_mode_var.get()
        collected['window_width'] = self.root.winfo_width()
        collected['window_height'] = self.root.winfo_height()
        collected['start_includes'] = [var.get() for var in self.set_vars]
        collected['preset_hotkeys'] = {
            f"hotkey_{i+1}": self.preset_hotkey_entries[i].get()
            for i in range(3)
        }

        return collected

    def save_settings(self):
        try:
            self.settings = self.collect_current_settings()
            self.refresh_runtime_settings()

            with open(SETTINGS_FILE, 'w') as f:
                json.dump(self.settings, f, indent=4)

            # Re-bind global/preset hotkeys if the user edited them
            try:
                self.setup_global_hotkey()
            except Exception as e:
                log_error(e, "save settings hotkey setup")

            self.settings_snapshot = copy.deepcopy(self.settings)
            messagebox.showinfo("Saved", "Settings saved to settings.json")
        except Exception as e:
            log_error(e, "save settings")
            messagebox.showerror("Error", f"Failed to save: {e}")

    def save_as_settings(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="settings.json"
        )
        if file_path:
            try:
                self.settings = self.collect_current_settings()
                self.refresh_runtime_settings()

                with open(file_path, 'w') as f:
                    json.dump(self.settings, f, indent=4)

                try:
                    self.setup_global_hotkey()
                except Exception as e:
                    log_error(e, "save as hotkey setup")

                self.settings_snapshot = copy.deepcopy(self.settings)
                messagebox.showinfo("Saved", f"Settings saved to {file_path}")
            except Exception as e:
                log_error(e, "save as settings")
                messagebox.showerror("Error", f"Failed to save: {e}")

    def load_settings_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir="."
        )
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.settings = self.normalize_settings(json.load(f))

                self.root.geometry(f"{self.settings.get('window_width', 750)}x{self.settings.get('window_height', 700)}")

                for i in range(4):
                    self.entries['x'][i].delete(0, tk.END)
                    self.entries['x'][i].insert(0, str(self.settings['sets'][i].get('x', 100)))
                    self.entries['y'][i].delete(0, tk.END)
                    self.entries['y'][i].insert(0, str(self.settings['sets'][i].get('y', 100)))
                    self.entries['hotkey'][i].delete(0, tk.END)
                    self.entries['hotkey'][i].insert(0, str(self.settings['sets'][i].get('hotkey', 'a')))

                i = 4
                if len(self.settings['sets']) > 4:
                    self.entries['x'][i].delete(0, tk.END)
                    self.entries['x'][i].insert(0, str(self.settings['sets'][i].get('x', 100)))
                    self.entries['y'][i].delete(0, tk.END)
                    self.entries['y'][i].insert(0, str(self.settings['sets'][i].get('y', 100)))
                    self.entries['x2'][i].delete(0, tk.END)
                    self.entries['x2'][i].insert(0, str(self.settings['sets'][i].get('x2', 200)))
                    self.entries['y2'][i].delete(0, tk.END)
                    self.entries['y2'][i].insert(0, str(self.settings['sets'][i].get('y2', 200)))
                    self.entries['target_angle'][i].delete(0, tk.END)
                    self.entries['target_angle'][i].insert(0, str(self.settings['sets'][i].get('target_angle', 0)))
                    self.entries['hotkey_greater'][i].delete(0, tk.END)
                    self.entries['hotkey_greater'][i].insert(0, str(self.settings['sets'][i].get('hotkey_greater', 'd')))
                    self.entries['hotkey_less'][i].delete(0, tk.END)
                    self.entries['hotkey_less'][i].insert(0, str(self.settings['sets'][i].get('hotkey_less', 'a')))
                    self.entries['line_delay'][i].delete(0, tk.END)
                    self.entries['line_delay'][i].insert(0, str(self.settings['sets'][i].get('line_delay', 100)))
                    self.entries['line_hold'][i].delete(0, tk.END)
                    self.entries['line_hold'][i].insert(0, str(self.settings['sets'][i].get('line_hold', 50)))

                self.global_hotkey_entry.delete(0, tk.END)
                self.global_hotkey_entry.insert(0, self.settings.get('global_hotkey', 'f9'))
                preset_hotkeys = self.settings.get('preset_hotkeys', {})
                for i, entry in enumerate(self.preset_hotkey_entries, start=1):
                    entry.delete(0, tk.END)
                    entry.insert(0, preset_hotkeys.get(f"hotkey_{i}", f"f{5+i}"))
                self.target_window_entry.delete(0, tk.END)
                self.target_window_entry.insert(0, self.settings.get('target_window', 'OutOfOre'))
                self.press_delay_entry.delete(0, tk.END)
                self.press_delay_entry.insert(0, str(self.settings.get('press_delay', 50)))
                self.hold_mode_var.set(self.settings.get('hold_mode', False))
                self.refresh_runtime_settings()

                start_includes = self.settings.get('start_includes', [True]*5)
                for i in range(min(len(start_includes), len(self.set_vars))):
                    self.set_vars[i].set(start_includes[i])

                try:
                    self.setup_global_hotkey()
                except Exception as e:
                    log_error(e, "load settings hotkey setup")

                self.settings_snapshot = copy.deepcopy(self.settings)
                messagebox.showinfo("Loaded", f"Settings loaded from {file_path}")
            except Exception as e:
                log_error(e, "load settings file")
                messagebox.showerror("Error", f"Failed to load: {e}")

    def create_basic_set_widgets(self, set_num, title):
        container = self.set_containers[set_num]
        frame = tk.LabelFrame(container, text=title, padx=8, pady=6, width=180)
        frame.pack(side=tk.LEFT, padx=4, pady=4, fill=tk.BOTH, expand=True)
        self.entries['frame'][set_num] = frame

        pos_frame = tk.Frame(frame)
        pos_frame.pack(pady=2)
        tk.Label(pos_frame, text="X:").grid(row=0, column=0)
        entry_x = tk.Entry(pos_frame, width=6)
        entry_x.insert(0, str(self.settings['sets'][set_num].get('x', 100)))
        entry_x.grid(row=0, column=1, padx=(2, 6))
        tk.Label(pos_frame, text="Y:").grid(row=0, column=2)
        entry_y = tk.Entry(pos_frame, width=6)
        entry_y.insert(0, str(self.settings['sets'][set_num].get('y', 100)))
        entry_y.grid(row=0, column=3, padx=(2, 0))

        config_row = tk.Frame(frame)
        config_row.pack(pady=1)
        tk.Label(config_row, text="Key:").grid(row=0, column=0)
        hotkey_entry = tk.Entry(config_row, width=5)
        hotkey_entry.insert(0, self.settings['sets'][set_num].get('hotkey', chr(97 + set_num)))
        hotkey_entry.grid(row=0, column=1, padx=(2, 2))
        rec_btn = tk.Button(config_row, text="Rec", width=3, command=None)
        rec_btn.grid(row=0, column=2, padx=(0, 0))
        rec_btn.config(command=lambda e=hotkey_entry, b=rec_btn: self.record_next_hotkey(e, b))

        status_row = tk.Frame(frame)
        status_row.pack(fill=tk.X, pady=1)
        preview_label = tk.Label(status_row, text="R:0 G:0 B:0 | 0", fg="blue", font=("Arial", 9, "bold"))
        preview_label.pack(side=tk.LEFT)

        indicator_frame = tk.Frame(status_row, width=20, height=20, bg="gray")
        indicator_frame.pack(side=tk.RIGHT)
        indicator_frame.pack_propagate(False)
        indicator = tk.Canvas(indicator_frame, width=18, height=18, bg="gray", highlightthickness=0)
        indicator.pack()
        indicator_oval = indicator.create_oval(2, 2, 16, 16, fill="gray", outline="")

        btn_frame = tk.Frame(frame)
        btn_frame.pack(pady=3)
        pick_btn = tk.Button(btn_frame, text="Pick", command=lambda: self.pick_position(set_num), width=7)
        pick_btn.grid(row=0, column=0, padx=2)
        start_btn = tk.Button(btn_frame, text="Start", command=lambda: self.start_monitor(set_num), width=7)
        start_btn.grid(row=0, column=1, padx=2)
        stop_btn = tk.Button(btn_frame, text="Stop", command=lambda: self.stop_monitor(set_num), width=7, state=tk.DISABLED)
        stop_btn.grid(row=0, column=2, padx=2)

        self.entries['x'][set_num] = entry_x
        self.entries['y'][set_num] = entry_y
        self.entries['pick_btn'][set_num] = pick_btn
        self.entries['preview'][set_num] = preview_label
        self.entries['hotkey'][set_num] = hotkey_entry
        self.entries['start_btn'][set_num] = start_btn
        self.entries['stop_btn'][set_num] = stop_btn
        self.entries['indicator'][set_num] = (indicator, indicator_oval)

    def create_line_finder_set(self, set_num, title):
        self.entries['is_line_finder'][set_num] = True

        container = tk.Frame(self.set_containers[4])
        container.pack(side=tk.LEFT, padx=4, pady=4, fill=tk.BOTH, expand=True)

        frame = tk.LabelFrame(container, text=title, padx=8, pady=6, width=180)
        frame.pack(fill=tk.BOTH, expand=True)
        self.entries['frame'][set_num] = frame

        row1 = tk.Frame(frame)
        row1.pack(pady=1)
        tk.Label(row1, text="X1:").grid(row=0, column=0)
        entry_x = tk.Entry(row1, width=5)
        entry_x.insert(0, str(self.settings['sets'][set_num].get('x', 100)))
        entry_x.grid(row=0, column=1, padx=(2, 4))
        tk.Label(row1, text="Y1:").grid(row=0, column=2)
        entry_y = tk.Entry(row1, width=5)
        entry_y.insert(0, str(self.settings['sets'][set_num].get('y', 100)))
        entry_y.grid(row=0, column=3, padx=(2, 4))
        tk.Label(row1, text="X2:").grid(row=0, column=4)
        entry_x2 = tk.Entry(row1, width=5)
        entry_x2.insert(0, str(self.settings['sets'][set_num].get('x2', 200)))
        entry_x2.grid(row=0, column=5, padx=(2, 4))
        tk.Label(row1, text="Y2:").grid(row=0, column=6)
        entry_y2 = tk.Entry(row1, width=5)
        entry_y2.insert(0, str(self.settings['sets'][set_num].get('y2', 200)))
        entry_y2.grid(row=0, column=7, padx=(2, 0))

        row2 = tk.Frame(frame)
        row2.pack(fill=tk.X, pady=1)
        tk.Label(row2, text="Target:").grid(row=0, column=0)
        target_angle_entry = tk.Entry(row2, width=5)
        target_angle_entry.insert(0, str(self.settings['sets'][set_num].get('target_angle', 0)))
        target_angle_entry.grid(row=0, column=1, padx=(2, 4))
        tk.Label(row2, text=">:").grid(row=0, column=2)
        hotkey_greater_entry = tk.Entry(row2, width=4)
        hotkey_greater_entry.insert(0, self.settings['sets'][set_num].get('hotkey_greater', 'd'))
        hotkey_greater_entry.grid(row=0, column=3, padx=(2, 2))
        rec_greater_btn = tk.Button(row2, text="Rec", width=3)
        rec_greater_btn.grid(row=0, column=4, padx=(0, 4))
        rec_greater_btn.config(command=lambda e=hotkey_greater_entry, b=rec_greater_btn: self.record_next_hotkey(e, b))
        tk.Label(row2, text="<:").grid(row=0, column=5)
        hotkey_less_entry = tk.Entry(row2, width=4)
        hotkey_less_entry.insert(0, self.settings['sets'][set_num].get('hotkey_less', 'a'))
        hotkey_less_entry.grid(row=0, column=6, padx=(2, 2))
        rec_less_btn = tk.Button(row2, text="Rec", width=3)
        rec_less_btn.grid(row=0, column=7, padx=(0, 0))
        rec_less_btn.config(command=lambda e=hotkey_less_entry, b=rec_less_btn: self.record_next_hotkey(e, b))

        row3 = tk.Frame(frame)
        row3.pack(fill=tk.X, pady=1)
        tk.Label(row3, text="Delay:").grid(row=0, column=0)
        delay_entry = tk.Entry(row3, width=5)
        delay_entry.insert(0, str(self.settings['sets'][set_num].get('line_delay', 100)))
        delay_entry.grid(row=0, column=1, padx=(2, 4))
        tk.Label(row3, text="Hold:").grid(row=0, column=2)
        hold_entry = tk.Entry(row3, width=5)
        hold_entry.insert(0, str(self.settings['sets'][set_num].get('line_hold', 50)))
        hold_entry.grid(row=0, column=3, padx=(2, 8))

        preview_label = tk.Label(row3, text="Angle: -- deg", fg="blue", font=("Arial", 9, "bold"))
        preview_label.grid(row=0, column=4, padx=(0, 8))

        indicator_row = tk.Frame(row3)
        indicator_row.grid(row=0, column=5)
        tk.Label(indicator_row, text=">:", font=("Arial", 8)).grid(row=0, column=0, padx=2)
        indicator_greater_frame = tk.Frame(indicator_row, width=18, height=18, bg="gray")
        indicator_greater_frame.grid(row=0, column=1, padx=2)
        indicator_greater_frame.pack_propagate(False)
        indicator_greater = tk.Canvas(indicator_greater_frame, width=16, height=16, bg="gray", highlightthickness=0)
        indicator_greater.pack()
        indicator_greater_oval = indicator_greater.create_oval(2, 2, 14, 14, fill="gray", outline="")

        tk.Label(indicator_row, text="<:", font=("Arial", 8)).grid(row=0, column=2, padx=2)
        indicator_less_frame = tk.Frame(indicator_row, width=18, height=18, bg="gray")
        indicator_less_frame.grid(row=0, column=3, padx=2)
        indicator_less_frame.pack_propagate(False)
        indicator_less = tk.Canvas(indicator_less_frame, width=16, height=16, bg="gray", highlightthickness=0)
        indicator_less.pack()
        indicator_less_oval = indicator_less.create_oval(2, 2, 14, 14, fill="gray", outline="")

        btn_frame = tk.Frame(frame)
        btn_frame.pack(pady=3)
        pick_btn = tk.Button(btn_frame, text="Pick", command=lambda: self.pick_region(set_num), width=7)
        pick_btn.grid(row=0, column=0, padx=2)
        start_btn = tk.Button(btn_frame, text="Start", command=lambda: self.start_monitor(set_num), width=7)
        start_btn.grid(row=0, column=1, padx=2)
        stop_btn = tk.Button(btn_frame, text="Stop", command=lambda: self.stop_monitor(set_num), width=7, state=tk.DISABLED)
        stop_btn.grid(row=0, column=2, padx=2)

        self.entries['x'][set_num] = entry_x
        self.entries['y'][set_num] = entry_y
        self.entries['x2'][set_num] = entry_x2
        self.entries['y2'][set_num] = entry_y2
        self.entries['pick_btn'][set_num] = pick_btn
        self.entries['preview'][set_num] = preview_label
        self.entries['target_angle'][set_num] = target_angle_entry
        self.entries['hotkey_greater'][set_num] = hotkey_greater_entry
        self.entries['hotkey_less'][set_num] = hotkey_less_entry
        self.entries['line_delay'][set_num] = delay_entry
        self.entries['line_hold'][set_num] = hold_entry
        self.entries['start_btn'][set_num] = start_btn
        self.entries['stop_btn'][set_num] = stop_btn
        self.entries['indicator'][set_num] = {
            'greater': (indicator_greater, indicator_greater_oval),
            'less': (indicator_less, indicator_less_oval)
        }
        self.entries['hotkey'][set_num] = None

    def get_threshold(self, set_num):
        try:
            return int(self.settings['sets'][set_num].get('threshold', 200))
        except (TypeError, ValueError, KeyError, IndexError):
            return 200

    def find_line_angle(self, set_num, px1=None, py1=None, px2=None, py2=None, pthreshold=None):
        try:
            x1 = int(self.entries['x'][set_num].get()) if px1 is None else px1
            y1 = int(self.entries['y'][set_num].get()) if py1 is None else py1
            x2 = int(self.entries['x2'][set_num].get()) if px2 is None else px2
            y2 = int(self.entries['y2'][set_num].get()) if py2 is None else py2
            threshold = self.get_threshold(set_num) if pthreshold is None else pthreshold

            min_x, max_x = min(x1, x2), max(x1, x2)
            min_y, max_y = min(y1, y2), max(y1, y2)

            monitor = {"top": min_y, "left": min_x, "width": max_x - min_x + 1, "height": max_y - min_y + 1}
            if monitor["width"] <= 0 or monitor["height"] <= 0:
                return None

            for attempt in range(2):
                try:
                    with mss.mss() as sct:
                        img = sct.grab(monitor)
                    break
                except ScreenShotError:
                    if attempt == 1:
                        return None

            white_points = []

            for py in range(img.height):
                first_white = None
                last_white = None
                for px in range(img.width):
                    pixel = img.pixel(px, py)
                    brightness = (pixel[0] + pixel[1] + pixel[2]) // 3
                    if brightness >= threshold:
                        if first_white is None:
                            first_white = px
                        last_white = px

                if first_white is not None:
                    white_points.append((first_white, py))
                if last_white is not None and last_white != first_white:
                    white_points.append((last_white, py))

            if len(white_points) < 2:
                return None

            left_point = min(white_points, key=lambda p: p[0])
            right_point = max(white_points, key=lambda p: p[0])

            dx = right_point[0] - left_point[0]
            dy = right_point[1] - left_point[1]

            if abs(dx) < 1:
                angle = 90 if dy > 0 else -90
            else:
                angle = math.degrees(math.atan2(-dy, dx))

            return angle, (min_x + left_point[0], min_y + left_point[1]), (min_x + right_point[0], min_y + right_point[1])

        except Exception as e:
            log_error(e, f"find_line_angle set {set_num}")
            return None

    def refresh_runtime_settings(self):
        try:
            self.cached_target_window = self.target_window_entry.get().strip()
        except Exception as e:
            log_error(e, "refresh target_window")
            self.cached_target_window = self.settings.get('target_window', 'OutOfOre')

        try:
            self.cached_press_delay = max(0, int(self.press_delay_entry.get()))
        except Exception as e:
            log_error(e, "refresh press_delay")
            self.cached_press_delay = int(self.settings.get('press_delay', 50))

        try:
            self.cached_hold_mode = bool(self.hold_mode_var.get())
        except Exception as e:
            log_error(e, "refresh hold_mode")
            self.cached_hold_mode = bool(self.settings.get('hold_mode', False))

    def build_hotkey_binding(self, hotkey_str, callback):
        hotkey_text = (hotkey_str or "").lower().strip()
        if not hotkey_text:
            return None

        from pynput.keyboard import Key

        key_map = {
            'f1': Key.f1, 'f2': Key.f2, 'f3': Key.f3, 'f4': Key.f4,
            'f5': Key.f5, 'f6': Key.f6, 'f7': Key.f7, 'f8': Key.f8,
            'f9': Key.f9, 'f10': Key.f10, 'f11': Key.f11, 'f12': Key.f12,
            'pageup': Key.page_up, 'pagedown': Key.page_down,
            'home': Key.home, 'end': Key.end, 'insert': Key.insert,
            'delete': Key.delete, 'space': Key.space, 'tab': Key.tab,
            'enter': Key.enter, 'escape': Key.esc, 'esc': Key.esc,
            'up': Key.up, 'down': Key.down, 'left': Key.left, 'right': Key.right,
        }

        return {
            "raw": hotkey_text,
            "special": key_map.get(hotkey_text),
            "callback": callback,
        }

    def _build_reverse_key_map(self):
        from pynput.keyboard import Key
        return {
            Key.f1: "f1", Key.f2: "f2", Key.f3: "f3", Key.f4: "f4",
            Key.f5: "f5", Key.f6: "f6", Key.f7: "f7", Key.f8: "f8",
            Key.f9: "f9", Key.f10: "f10", Key.f11: "f11", Key.f12: "f12",
            Key.page_up: "pageup", Key.page_down: "pagedown",
            Key.home: "home", Key.end: "end", Key.insert: "insert",
            Key.delete: "delete", Key.space: "space", Key.tab: "tab",
            Key.enter: "enter", Key.esc: "escape",
            Key.up: "up", Key.down: "down", Key.left: "left", Key.right: "right",
        }

    def record_next_hotkey(self, entry_widget, rec_button):
        original_text = rec_button.cget("text")
        original_state = rec_button.cget("state")
        rec_button.config(text="Listening...", state=tk.DISABLED, fg="red")

        reverse_map = self._build_reverse_key_map()

        def on_press(key):
            try:
                result = None
                if hasattr(key, 'char') and key.char:
                    result = key.char
                elif hasattr(key, 'name'):
                    name_lower = key.name.lower()
                    for spec_key, name_str in reverse_map.items():
                        if hasattr(key, 'value') and hasattr(spec_key, 'value') and key.value == spec_key.value:
                            result = name_str
                            break
                    if result is None:
                        result = name_lower
                if result is None:
                    return

                def apply_result():
                    entry_widget.delete(0, tk.END)
                    entry_widget.insert(0, result)
                    rec_button.config(text=original_text, state=original_state, fg="black")
                self.root.after(0, apply_result)
            except Exception as e:
                log_error(e, "record_next_hotkey")
                def restore():
                    rec_button.config(text=original_text, state=original_state, fg="black")
                self.root.after(0, restore)

            return False  # stop listener after one key

        listener = keyboard.Listener(on_press=on_press, suppress=False)
        listener.start()

    def hotkey_matches(self, key, binding):
        if not binding:
            return False

        try:
            key_str = str(key).lower().strip()

            if binding["special"]:
                if hasattr(key, 'value') and hasattr(binding["special"], 'value'):
                    if key.value == binding["special"].value:
                        return True
                elif key == binding["special"]:
                    return True

            if f"'{binding['raw']}'" in key_str or key_str == f"'{binding['raw']}'":
                return True

            if len(binding["raw"]) == 1:
                char = key_str.strip("'\"")
                if char == binding["raw"]:
                    return True
        except Exception as e:
            log_error(e, "hotkey_matches")
            return False

        return False

    def start_preview(self):
        self.preview_running = True
        self.root.after(0, self.preview_loop)

    def preview_loop(self):
        if not self.preview_running:
            return

        for set_num in range(5):
            try:
                if self.entries['is_line_finder'][set_num]:
                    x = int(self.entries['x'][set_num].get())
                    y = int(self.entries['y'][set_num].get())
                    x2 = int(self.entries['x2'][set_num].get())
                    y2 = int(self.entries['y2'][set_num].get())
                    thr = self.get_threshold(set_num)
                    tgt = float(self.entries['target_angle'][set_num].get())
                    threading.Thread(target=self._preview_line_angle, args=(set_num, x, y, x2, y2, thr, tgt), daemon=True).start()
                else:
                    x = int(self.entries['x'][set_num].get())
                    y = int(self.entries['y'][set_num].get())
                    color = self.get_pixel_color(x, y)
                    if color:
                        brightness = sum(color[:3]) // 3
                        self.update_preview(color, brightness, set_num)
            except Exception as e:
                log_error(e, f"preview_loop set {set_num}")

        self.root.after(200, self.preview_loop)

    def _preview_line_angle(self, set_num, x, y, x2, y2, thr, tgt):
        result = self.find_line_angle(set_num, x, y, x2, y2, thr)
        if result:
            angle, p1, p2 = result
            target = tgt
            text = f"Angle: {angle:.1f} deg (target: {target} deg)"
            fg = "green"
        else:
            text = "No line found"
            fg = "gray"
        self.root.after(0, lambda t=text, f=fg, s=set_num: self.entries['preview'][s].config(text=t, fg=f))

    def update_preview(self, color, brightness, set_num):
        self.entries['preview'][set_num].config(text=f"R:{color[0]} G:{color[1]} B:{color[2]} | {brightness}")

    def get_pixel_color(self, x, y):
        for attempt in range(2):
            try:
                with mss.mss() as sct:
                    monitor = {"top": y, "left": x, "width": 1, "height": 1}
                    img = sct.grab(monitor)
                return img.pixel(0, 0)
            except ScreenShotError:
                if attempt == 0:
                    continue
                return None

    def pick_position(self, set_num):
        self.active_set = set_num
        self.entries['pick_btn'][set_num].config(text="Click anywhere...", state=tk.DISABLED)
        self.root.update()
        self.root.after(100, lambda: self.wait_for_click(set_num))

    def pick_region(self, set_num):
        self.active_set = set_num
        self.entries['pick_btn'][set_num].config(text="Click P1...", state=tk.DISABLED)
        self.root.update()
        self.root.after(100, lambda: self.wait_for_region_p1(set_num))

    def wait_for_click(self, set_num):
        def get_click():
            state = win32api.GetAsyncKeyState(win32con.VK_LBUTTON)
            if state < 0:
                x, y = win32api.GetCursorPos()
                return x, y
            return None

        def check_loop():
            pos = get_click()
            if pos:
                self.set_position(*pos)
            else:
                if self.entries['pick_btn'][set_num]['state'] == 'disabled':
                    self.root.after(50, lambda: check_loop())

        check_loop()

    def wait_for_region_p1(self, set_num):
        def get_click():
            state = win32api.GetAsyncKeyState(win32con.VK_LBUTTON)
            if state < 0:
                x, y = win32api.GetCursorPos()
                return x, y
            return None

        def check_loop():
            pos = get_click()
            if pos:
                self.set_region_p1(*pos)
            else:
                if self.entries['pick_btn'][set_num]['state'] == 'disabled':
                    self.root.after(50, lambda: check_loop())

        check_loop()

    def wait_for_region_p2(self, set_num):
        def get_click():
            state = win32api.GetAsyncKeyState(win32con.VK_LBUTTON)
            if state < 0:
                x, y = win32api.GetCursorPos()
                return x, y
            return None

        def check_loop():
            pos = get_click()
            if pos:
                self.set_region_p2(*pos)
            else:
                if self.entries['pick_btn'][set_num]['state'] == 'disabled':
                    self.root.after(50, lambda: check_loop())

        check_loop()

    def set_position(self, x, y):
        set_num = self.active_set
        self.entries['x'][set_num].delete(0, tk.END)
        self.entries['x'][set_num].insert(0, str(x))
        self.entries['y'][set_num].delete(0, tk.END)
        self.entries['y'][set_num].insert(0, str(y))
        self.entries['pick_btn'][set_num].config(text="Pick Position", state=tk.NORMAL)

    def set_region_p1(self, x, y):
        set_num = self.active_set
        self.entries['x'][set_num].delete(0, tk.END)
        self.entries['x'][set_num].insert(0, str(x))
        self.entries['y'][set_num].delete(0, tk.END)
        self.entries['y'][set_num].insert(0, str(y))
        self.entries['pick_btn'][set_num].config(text="Click P2...", state=tk.DISABLED)
        self.root.after(100, lambda: self.wait_for_region_p2(set_num))

    def set_region_p2(self, x, y):
        set_num = self.active_set
        self.entries['x2'][set_num].delete(0, tk.END)
        self.entries['x2'][set_num].insert(0, str(x))
        self.entries['y2'][set_num].delete(0, tk.END)
        self.entries['y2'][set_num].insert(0, str(y))
        self.entries['pick_btn'][set_num].config(text="Pick Region", state=tk.NORMAL)

    def start_all(self):
        self.refresh_runtime_settings()
        if any(self.running):
            self.stop_all()
        for set_num in range(5):
            if self.set_vars[set_num].get():
                self.start_monitor(set_num)
        try:
            self.setup_global_hotkey()
        except Exception as e:
            log_error(e, "start_all hotkey setup")

    def stop_all(self):
        for set_num in range(5):
            if self.running[set_num]:
                self.stop_monitor(set_num)

    def start_selected_sets(self, set_numbers, status_text=None):
        self.refresh_runtime_settings()
        self.stop_all()
        for set_num in set_numbers:
            if 0 <= set_num < len(self.running) and self.set_vars[set_num].get():
                self.start_monitor(set_num)
        try:
            self.setup_global_hotkey()
        except Exception as e:
            log_error(e, "start_selected_sets hotkey setup")
        if status_text:
            self.status_label.config(text=status_text, fg="green")

    def setup_global_hotkey(self):
        self.refresh_runtime_settings()
        hotkey_str = self.global_hotkey_entry.get().lower().strip()

        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception as e:
                log_error(e, "stop hotkey listener")

        self.hotkey_active = True
        preset_actions = [
            ("hotkey_1", [0, 1, 2, 3], "Status: Preset 1 started sets 1, 2, 3, 4"),
            ("hotkey_2", [2, 3], "Status: Preset 2 started sets 3, 4"),
            ("hotkey_3", [2, 3, 4], "Status: Preset 3 started sets 3, 4, 5"),
        ]
        self.hotkey_bindings = []

        # Global hotkey toggles start/stop (README: F9 toggles all sets)
        toggle_binding = self.build_hotkey_binding(hotkey_str, self.toggle_all)
        if toggle_binding:
            self.hotkey_bindings.append(toggle_binding)

        preset_hotkeys = self.settings.get('preset_hotkeys', {})
        for index, (setting_key, set_numbers, status_text) in enumerate(preset_actions):
            entry_value = self.preset_hotkey_entries[index].get().strip()
            preset_hotkeys[setting_key] = entry_value
            binding = self.build_hotkey_binding(
                entry_value,
                lambda sets=set_numbers, text=status_text: self.start_selected_sets(sets, text)
            )
            if binding:
                self.hotkey_bindings.append(binding)
        self.settings['preset_hotkeys'] = preset_hotkeys

        def on_press(key):
            if not self.hotkey_active:
                return

            try:
                for binding in self.hotkey_bindings:
                    if self.hotkey_matches(key, binding):
                        self.root.after(0, binding["callback"])
                        break
            except Exception as e:
                log_error(e, "hotkey on_press")

        self.hotkey_listener = keyboard.Listener(on_press=on_press, suppress=False)
        self.hotkey_listener.start()

        self.root.after(500, lambda: self.update_status_buttons())

    def toggle_all(self):
        if any(self.running):
            self.stop_all()
            self.status_label.config(text="Status: Stopped (by hotkey)", fg="orange")
        else:
            self.start_all()
            self.status_label.config(text="Status: Started (by hotkey)", fg="green")

    def start_monitor(self, set_num):
        if self.running[set_num]:
            return

        try:
            self.refresh_runtime_settings()
            x = int(self.entries['x'][set_num].get())
            y = int(self.entries['y'][set_num].get())
            threshold = self.get_threshold(set_num)

            if self.entries['is_line_finder'][set_num]:
                x2 = int(self.entries['x2'][set_num].get())
                y2 = int(self.entries['y2'][set_num].get())
                target_angle = float(self.entries['target_angle'][set_num].get())
                hotkey_greater = self.entries['hotkey_greater'][set_num].get()
                hotkey_less = self.entries['hotkey_less'][set_num].get()
                line_delay = int(self.entries['line_delay'][set_num].get())
                line_hold = int(self.entries['line_hold'][set_num].get())
                hotkey = None
            else:
                hotkey = self.entries['hotkey'][set_num].get()
                x2, y2, target_angle, hotkey_greater, hotkey_less, line_delay, line_hold = None, None, None, None, None, None, None
        except ValueError:
            messagebox.showerror("Error", "Invalid input values")
            return

        self.running[set_num] = True
        self.stop_events[set_num] = threading.Event()
        stop_event = self.stop_events[set_num]
        self.entries['start_btn'][set_num].config(state=tk.DISABLED)
        self.entries['stop_btn'][set_num].config(state=tk.NORMAL)
        self.update_status_buttons()

        if self.entries['is_line_finder'][set_num]:
            self.monitor_threads[set_num] = threading.Thread(target=self.monitor_loop_line,
                args=(set_num, x, y, x2, y2, threshold, target_angle, hotkey_greater, hotkey_less, line_delay, line_hold, stop_event), daemon=True)
        else:
            self.monitor_threads[set_num] = threading.Thread(target=self.monitor_loop,
                args=(set_num, x, y, threshold, hotkey, stop_event), daemon=True)
        self.monitor_threads[set_num].start()

    def stop_monitor(self, set_num):
        self.running[set_num] = False
        self.stop_events[set_num].set()
        self.entries['start_btn'][set_num].config(state=tk.NORMAL)
        self.entries['stop_btn'][set_num].config(state=tk.DISABLED)
        self.set_indicator_off(set_num)
        self.update_status_buttons()

    def update_status_buttons(self):
        running_count = sum(self.running)

        if running_count == 5:
            self.status_label.config(text="Status: All 5 Running", fg="green")
        elif running_count > 0:
            self.status_label.config(text=f"Status: {running_count} Set(s) Running", fg="green")
        else:
            self.status_label.config(text="Status: Stopped", fg="gray")

        if running_count > 0:
            self.global_start_btn.config(text="Restart All", state=tk.NORMAL)
            self.stop_all_btn.config(state=tk.NORMAL)
        else:
            self.global_start_btn.config(text="Start All", state=tk.NORMAL)
            self.stop_all_btn.config(state=tk.DISABLED)

    def is_target_window_open(self):
        try:
            target_window = self.cached_target_window
            if not target_window:
                return True

            def enum_callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title and target_window.lower() in title.lower():
                        windows.append(hwnd)
                return True

            windows = []
            win32gui.EnumWindows(enum_callback, windows)
            return len(windows) > 0
        except Exception as e:
            log_error(e, "is_target_window_open")
            return False

    def is_window_focused(self):
        try:
            target_window = self.cached_target_window
            if not target_window:
                return True

            if not self.is_target_window_open():
                return False

            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                title = win32gui.GetWindowText(hwnd)
                if title:
                    app_title_lower = title.lower()
                    if "out of ore" in app_title_lower and "gps" in app_title_lower:
                        return False
                    if target_window.lower() in app_title_lower:
                        return True
            return False
        except Exception as e:
            log_error(e, "is_window_focused")
            return False

    def set_indicator_on(self, set_num, indicator_type=None):
        try:
            if self.entries['is_line_finder'][set_num]:
                if indicator_type == 'greater':
                    indicator, oval = self.entries['indicator'][set_num]['greater']
                    indicator.itemconfig(oval, fill="lime green")
                elif indicator_type == 'less':
                    indicator, oval = self.entries['indicator'][set_num]['less']
                    indicator.itemconfig(oval, fill="lime green")
            else:
                indicator, oval = self.entries['indicator'][set_num]
                indicator.itemconfig(oval, fill="lime green")
        except Exception as e:
            log_error(e, f"set_indicator_on set {set_num}")

    def set_indicator_off(self, set_num, indicator_type=None):
        try:
            if self.entries['is_line_finder'][set_num]:
                if indicator_type == 'greater':
                    indicator, oval = self.entries['indicator'][set_num]['greater']
                    indicator.itemconfig(oval, fill="gray")
                elif indicator_type == 'less':
                    indicator, oval = self.entries['indicator'][set_num]['less']
                    indicator.itemconfig(oval, fill="gray")
                else:
                    indicator, oval = self.entries['indicator'][set_num]['greater']
                    indicator.itemconfig(oval, fill="gray")
                    indicator, oval = self.entries['indicator'][set_num]['less']
                    indicator.itemconfig(oval, fill="gray")
            else:
                indicator, oval = self.entries['indicator'][set_num]
                indicator.itemconfig(oval, fill="gray")
        except Exception as e:
            log_error(e, f"set_indicator_off set {set_num}")

    def resolve_key(self, key_str):
        from pynput.keyboard import Key
        key_map = {
            'f1': Key.f1, 'f2': Key.f2, 'f3': Key.f3, 'f4': Key.f4,
            'f5': Key.f5, 'f6': Key.f6, 'f7': Key.f7, 'f8': Key.f8,
            'f9': Key.f9, 'f10': Key.f10, 'f11': Key.f11, 'f12': Key.f12,
            'pageup': Key.page_up, 'pagedown': Key.page_down,
            'home': Key.home, 'end': Key.end, 'insert': Key.insert,
            'delete': Key.delete, 'space': Key.space, 'tab': Key.tab,
            'enter': Key.enter, 'escape': Key.esc, 'esc': Key.esc,
            'up': Key.up, 'down': Key.down, 'left': Key.left, 'right': Key.right,
        }
        text = (key_str or "").lower().strip()
        if text in key_map:
            return key_map[text]
        if len(text) == 1:
            return text
        return text

    def press_key(self, key):
        try:
            if not self.is_window_focused():
                return
            delay = self.cached_press_delay / 1000.0
            hold = self.cached_hold_mode
            resolved = self.resolve_key(key)
            with self.key_lock:
                self.keyboard_controller.press(resolved)
                if not hold:
                    time.sleep(delay)
                    self.keyboard_controller.release(resolved)
                else:
                    time.sleep(delay)
        except Exception as e:
            log_error(e, "press_key")

    def monitor_loop(self, set_num, x, y, threshold, hotkey, stop_event):
        interval = 0.05
        set_label = f"Set {set_num+1}"
        while not stop_event.is_set():
            try:
                color = self.get_pixel_color(x, y)
                condition_met = color and all(c >= threshold for c in color[:3])

                if condition_met:
                    self.press_key(hotkey)
                    self.root.after(0, lambda s=set_label, h=hotkey: self.status_label.config(text=f"Status: {s} pressed {h}!", fg="orange"))
                    self.root.after(0, lambda sn=set_num: self.set_indicator_on(sn))
                else:
                    self.root.after(0, lambda sn=set_num: self.set_indicator_off(sn))
            except Exception as e:
                log_error(e, f"monitor_loop set {set_num}")
            stop_event.wait(interval)

    def monitor_loop_line(self, set_num, x1, y1, x2, y2, threshold, target_angle, hotkey_greater, hotkey_less, line_delay, line_hold, stop_event):
        interval = line_delay / 1000.0
        hold_time = line_hold / 1000.0
        last_direction = None

        while not stop_event.is_set():
            try:
                result = self.find_line_angle(set_num, x1, y1, x2, y2, threshold)
                if result:
                    angle, p1, p2 = result

                    if angle > target_angle:
                        key = hotkey_greater
                        direction = "greater"
                    else:
                        key = hotkey_less
                        direction = "less"

                    resolved = self.resolve_key(key)
                    with self.key_lock:
                        self.keyboard_controller.press(resolved)
                        time.sleep(hold_time)
                        self.keyboard_controller.release(resolved)

                    if direction != last_direction:
                        if last_direction:
                            self.root.after(0, lambda sn=set_num, dt=last_direction: self.set_indicator_off(sn, dt))
                        self.root.after(0, lambda sn=set_num, dt=direction: self.set_indicator_on(sn, dt))
                        last_direction = direction

                    self.root.after(0, lambda a=angle, t=target_angle, k=key, d=direction: self.status_label.config(
                        text=f"Status: Angle {a:.1f}° vs {t}° ({d}) - pressed {k}", fg="orange"))
                else:
                    if last_direction:
                        self.root.after(0, lambda sn=set_num: self.set_indicator_off(sn))
                        last_direction = None
                    self.root.after(0, lambda: self.status_label.config(text="Status: No line found", fg="gray"))
            except Exception as e:
                log_error(e, f"monitor_loop_line set {set_num}")
            stop_event.wait(interval)

    def hold_key(self, key):
        try:
            if not self.is_window_focused():
                return
            resolved = self.resolve_key(key)
            with self.key_lock:
                self.keyboard_controller.press(resolved)
        except Exception as e:
            log_error(e, "hold_key")

    def release_key(self, key):
        try:
            resolved = self.resolve_key(key)
            with self.key_lock:
                self.keyboard_controller.release(resolved)
        except Exception as e:
            log_error(e, "release_key")

    def has_unsaved_changes(self):
        try:
            current = self.collect_current_settings()
        except Exception:
            return False
        ignore_keys = {"window_width", "window_height"}
        for key in set(list(current.keys()) + list(self.settings_snapshot.keys())):
            if key in ignore_keys:
                continue
            if key == "sets":
                for i, (cur_set, snap_set) in enumerate(zip(current["sets"], self.settings_snapshot["sets"])):
                    for k in set(list(cur_set.keys()) + list(snap_set.keys())):
                        if cur_set.get(k) != snap_set.get(k):
                            return True
            elif key == "preset_hotkeys":
                if current.get(key) != self.settings_snapshot.get(key):
                    return True
            elif current.get(key) != self.settings_snapshot.get(key):
                return True
        return False

    def on_close(self):
        if self.has_unsaved_changes():
            answer = messagebox.askyesnocancel("Unsaved Changes", "You have unsaved settings changes.\nWould you like to save before closing?")
            if answer is None:  # Cancel
                return
            if answer:  # Yes
                try:
                    self.settings = self.collect_current_settings()
                    self.refresh_runtime_settings()
                    with open(SETTINGS_FILE, 'w') as f:
                        json.dump(self.settings, f, indent=4)
                    self.settings_snapshot = copy.deepcopy(self.settings)
                except Exception as e:
                    log_error(e, "on_close save")
                    messagebox.showerror("Error", f"Failed to save: {e}")
                    return

        self.preview_running = False
        self.running = [False]*5
        self.hotkey_active = False
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception as e:
                log_error(e, "on_close stop listener")
        self.root.destroy()

if __name__ == "__main__":
    import ctypes
    if not ctypes.windll.shell32.IsUserAnAdmin():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Admin Required", "This tool must be run as administrator.\nRight-click and select 'Run as administrator'.")
        sys.exit(0)
    root = tk.Tk()
    app = PixelMonitorGUI(root)
    root.mainloop()
