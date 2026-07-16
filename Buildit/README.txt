OutOfOre GPS Tool - Build Instructions
========================================

Prerequisites:
  - Python 3.x installed
  - Required packages: pyinstaller, mss, pynput, pywin32
  - Install with: pip install pyinstaller mss pynput pywin32

How to Build:
  1. Double-click build_exe.bat
  2. The .exe will be created in the "dist" subfolder

Output:
  - dist\OutOfOreGPS.exe  (standalone executable, ~15-30 MB)

Usage:
  - Place OutOfOreGPS.exe anywhere on your system
  - Run it; a settings.json will be created next to the .exe on first save
  - The tool monitors screen pixels and presses keys in the "OutOfOre" game window

Notes:
  - The .exe is portable - no Python installation needed on the target machine
  - Windows may show a SmartScreen warning; click "More info" then "Run anyway"
  - Some antivirus software may flag auto-hotkey tools; this is a false positive
