# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

SPEC_DIR = os.getcwd()
SOURCE_DIR = os.path.abspath(os.path.join(SPEC_DIR, '..'))

datas = []
binaries = []
hiddenimports = ['win32api', 'win32con', 'win32gui', 'win32ui',
                 'pynput.keyboard._win32', 'pynput.mouse._win32', 'mss']

for modname in ('pynput', 'mss'):
    tmp_ret = collect_all(modname)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

datas += [
    (os.path.join(SPEC_DIR, 'README.txt'), '.'),
    (os.path.join(SOURCE_DIR, 'settings.json'), '.'),
    (os.path.join(SOURCE_DIR, 'VERSION'), '.'),
]

a = Analysis(
    [os.path.join(SOURCE_DIR, 'out_of_ore_gps_tool.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='OutOfOreGPS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
