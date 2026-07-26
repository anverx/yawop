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

# Application versioning. Sourced from game/version.py (single source of truth,
# also shown on the About screen) so the package version can't drift from the app.
version.regex = __version__\s*=\s*['"]([^'"]+)['"]
version.filename = %(source.dir)s/game/version.py
# Numeric version code for Android (must increment for updates!)
android.numeric_version = 1

# Application requirements (this is a p4a RECIPE list, not pip — no git URLs).
# kivyshell (the shared UI lib) is pure Python and is vendored as a git submodule
# at libs/kivyshell; game/__init__.py puts it on sys.path, so it bundles as plain
# source and needs no entry here. CI must checkout with submodules: recursive.
requirements = python3,kivy,pillow,pyjnius,cython==3.0.12

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

# Launcher icon: the raven (wisdom) cut from the splash art.
icon.filename = %(source.dir)s/game/assets/icon.png

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
