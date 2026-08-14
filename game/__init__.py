"""yawop game (Kivy) — built on the shared kivyshell library.

kivyshell is vendored as a git submodule at libs/kivyshell (its package sits one
level down, at libs/kivyshell/kivyshell/), so we put that dir on sys.path here.
This makes `import kivyshell` resolve the same way on desktop and inside the
Android APK, with no pip install and no duplicated copy. Guarded: if the submodule
isn't checked out (e.g. kivyshell is pip-installed instead), this is a no-op.
"""

import os as _os
import sys as _sys

_shell = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "libs", "kivyshell")
if _os.path.isdir(_os.path.join(_shell, "kivyshell")) and _shell not in _sys.path:
    _sys.path.insert(0, _shell)
