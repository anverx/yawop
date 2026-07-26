"""Single source of truth for the app version.

Shown on the About screen, and read by buildozer.spec (version.regex/filename) so
the Android package version matches. Bump on each release:
  - patch (0.2.x): fixes, data refreshes
  - minor (0.x.0): new features
  - major (x.0.0): big/breaking changes
The Android numeric_version (integer, must increase per Play upload) is set
automatically from the CI run number; this human version is bumped by hand here.
"""

__version__ = "0.5.22"
