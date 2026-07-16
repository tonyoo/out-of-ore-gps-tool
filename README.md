# Out Of Ore GPS Tool

A pixel-monitoring automation tool for the game Out Of Ore. Monitors screen pixels and presses keys automatically when conditions are met.

## Setup

```
run.bat
```

Or manually:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python out_of_ore_gps_tool.py
```

## Features

### Sets 1-4 (Single Pixel Monitor)
- Monitor a screen position; press a key when all RGB channels ≥ threshold
- Configurable: X, Y, threshold, hotkey
- Preview shows live R/G/B values and brightness

### Set 5 (Line Angle Finder)
- Scans a rectangular region for white pixels, calculates the angle of the detected line
- Presses one key if angle > target, another if angle < target
- Corrects continuously on every cycle (not just on direction change)
- Configurable: X1/Y1, X2/Y2, threshold, target angle, greater/less hotkeys, delay, hold

### Controls
- **Global hotkey** (default F9) — toggles all sets on/off
- **Target window** — only presses keys when this window is focused (prevents background input)
- **Press delay** (ms) — how long between key press and release
- **Hold mode** — keep key held instead of tap-release
- **Preset rows** — F6 starts sets 1-4, F7 starts sets 3-4, F8 starts sets 3-5

### Start All Includes
Checkboxes control which sets are started by the "Start All" button and preset hotkeys.

## Settings (settings.json)

Full example:

```json
{
    "sets": [
        {"label": "Blade up",  "x": 2003, "y": 201, "threshold": 200, "hotkey": "="},
        {"label": "Blade down","x": 2004, "y": 213, "threshold": 200, "hotkey": "-"},
        {"label": "Blade left", "x": 2421, "y": 214, "threshold": 200, "hotkey": "["},
        {"label": "Blade right","x": 2406, "y": 217, "threshold": 200, "hotkey": "]"},
        {
            "label": "Line Angle", "x": 1889, "y": 366, "threshold": 200,
            "x2": 2009, "y2": 244, "target_angle": 14.0,
            "hotkey_greater": "=", "hotkey_less": "-",
            "line_delay": 10, "line_hold": 50
        }
    ],
    "global_hotkey": "f9",
    "preset_hotkeys": {"hotkey_1": "f6", "hotkey_2": "f7", "hotkey_3": "f8"},
    "press_delay": 100,
    "hold_mode": false,
    "window_width": 506,
    "window_height": 657,
    "start_includes": [true, true, true, true, false],
    "target_window": "Out Of Ore"
}
```

## Troubleshooting

- **Keys not pressing** — make sure the target window is focused and visible
- **Hotkeys ignored** — run as administrator for global hotkeys
- **Line find error** — ensure both X/Y endpoints define a valid region with contrasting content
