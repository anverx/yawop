# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build for the yawop desktop binary (Windows / Linux).

Bundles the Kivy SDL2/GLEW runtime, the shipped dictionaries + images, and the
game/worddata packages. kivyshell is expected to be pip-installed (CI runs
`pip install ./libs/kivyshell`) so PyInstaller collects it as a normal package.

Build:  pyinstaller yawop.spec --noconfirm      (output in dist/yawop/)
"""
from kivy_deps import glew, sdl2
from kivy.tools.packaging.pyinstaller_hooks import get_deps_all, hookspath, runtime_hooks
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

datas = [
    ("assets", "assets"),            # dictionaries + splash image
    ("game/assets", "game/assets"),  # W badge + enter icon
]
datas += collect_data_files("kivyshell")  # any fonts/icons the shared UI ships

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=datas,
    hookspath=hookspath(),
    runtime_hooks=runtime_hooks(),
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    **get_deps_all(),
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="yawop",
    debug=False,
    strip=False,
    upx=False,
    console=False,   # windowed GUI app (no console window)
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
    strip=False,
    upx=False,
    name="yawop",
)
