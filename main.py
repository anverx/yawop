"""Android entry point. buildozer/python-for-android runs this from the repo root
(source.dir = .), which puts the game/, worddata/ and assets/ trees on sys.path.

On desktop, prefer:  python -m game.main
"""

from game.app import WordApp

if __name__ == "__main__":
    WordApp().run()
