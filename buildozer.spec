[app]

# App name
title = yawop

# Package name
package.name = yawop

# Package domain (used for Android package identifier)
package.domain = com.yawop

# Source code directory. yawop keeps its code in packages (game/, worddata/) plus
# the built dictionaries under assets/, so the whole repo root is the source and
# the top-level main.py is the entry point.
source.dir = .

# Source files to include. jsonl + txt are needed for the shipped dictionaries.
source.include_exts = py,png,jpg,jpeg,kv,atlas,json,jsonl,txt,ttf

# Keep build/tooling trees out of the APK (pipeline data, tests, CI, caches).
source.exclude_dirs = tests, pipeline, .github, .git, .buildozer, bin, __pycache__

# Application versioning
version = 0.1.0
# Numeric version code for Android (must increment for updates!)
android.numeric_version = 1

# Application requirements.
# NOTE: kivyshell (the shared UI lib) is a pip/git dependency in requirements.txt,
# but python-for-android's requirements list below is a RECIPE list, not pip, and
# cannot take a git+ URL. Wiring kivyshell into the Android build needs one of:
# publish kivyshell to PyPI (then add 'kivyshell' here), write a p4a recipe, or
# vendor the package into this repo. Until then the APK builds but can't import
# kivyshell at runtime. (Same open item as yaque.)
requirements = python3,kivy,pillow,cython==3.0.12

# Supported orientations (portrait, landscape, all)
orientation = portrait

# Android fullscreen mode
fullscreen = 1

# Android permissions
android.permissions =

# Android API levels
android.minapi = 21
android.api = 35
android.ndk = 25b

# Android architecture
android.archs = arm64-v8a, armeabi-v7a

# Pin to a tagged p4a release for reproducible builds
p4a.branch = v2026.05.09

# Android features
android.allow_backup = True

# Presplash
android.presplash_color = #F2F2F2
presplash.filename = %(source.dir)s/assets/images/splash.jpeg

# Launcher icon: none yet. Add icon.filename (and optionally the adaptive-icon
# layers) once a yawop app icon exists; buildozer uses the default Kivy icon
# meanwhile.

# Debug keystore (for consistent signing across builds).
# On CI this file is restored from secrets / generated into the repo root; locally
# you can create your own with keytool.
android.debug_keystore = %(source.dir)s/debug.keystore
android.debug_keystore_alias = androiddebugkey
android.debug_keystore_passwd = android
android.debug_keyalias_passwd = android

[buildozer]

# Build log level (0 = error, 1 = info, 2 = debug)
log_level = 2

# Build warnings
warn_on_root = 1
