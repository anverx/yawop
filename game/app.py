"""yawop — a Wordle-style word puzzle built on kivyshell.

WordApp reuses kivyshell's GameShellApp + shared screens (splash/menu/calendar/
logbook); the only game-specific screens are the menu config and the word-grid
game screen. Answers come from the shipped dictionaries via worddata; plays and
completions are persisted with kivyshell's SqliteStore.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform

import worddata

from kivyshell.shell.app import GameShellApp
from kivyshell.shell.screens.splash import SplashScreen
from kivyshell.uikit import set_theme

from . import theme as T
from .calendar import WordCalendarScreen
from .gamescreen import WordGameScreen
from .logbook import WordLogbookScreen
from .menu import WordMenuScreen
from .store import WordStore, answer_of
from .wordgame import WordGame
from worddata.store import allowed_guesses, pack_allowed_guesses

DEFAULT_PACK = "subtlex-us"
DIFFICULTIES = ["easy", "medium", "hard"]
# Short labels for the Random Game subtitle (union across all languages' packs).
PACK_LABEL = {"subtlex-us": "US", "subtlex-uk": "UK", "wordle": "Official",
              "arcane": "Arcane", "surprise": "Surprise", "russian": "Русский"}

# ЙЦУКЕН keyboard with ё folded into е (32 keys). Rows: 12 / 11 / 9.
_CYRILLIC_ROWS = ["йцукенгшщзхъ", "фывапролджэ", "ячсмитьбю"]

# One entry per language "world". ADD A LANGUAGE by shipping its pack under
# assets/dictionaries/<pack>/ (with its own allowed_guesses.txt + tiers.json) and
# appending an entry here — nothing else is hardcoded to en/ru. Each world gets its
# OWN store/DB (subdir => separate calendar + streak), daily pack, on-screen keyboard,
# and Random-Game pack list. English keeps the root data dir so existing players'
# history is preserved; every other language lives in its own subdirectory.
LANGUAGES = [
    {"lang": "en", "label": "English", "pack": "subtlex-us", "subdir": "", "keyboard": None,
     "random_packs": [("subtlex-us", "US"), ("subtlex-uk", "UK"), ("wordle", "Official"), ("arcane", "Arcane")]},
    {"lang": "ru", "label": "Русский", "pack": "russian", "subdir": "ru", "keyboard": _CYRILLIC_ROWS,
     "random_packs": [("russian", "Русский")]},
]


class _LangProfile:
    """A language 'world': its own store (hence its own calendar/streak), daily pack,
    keyboard layout, per-key letter frequencies, guess set, and Random-Game packs.
    The app's active self.store / self._allowed point at the current profile's values."""

    def __init__(self, spec: dict, store: WordStore, ddir: str,
                 allowed: set, letter_mass: dict | None) -> None:
        self.lang = spec["lang"]
        self.label = spec["label"]
        self.pack = spec["pack"]
        self.keyboard = spec["keyboard"]
        self.random_packs = spec["random_packs"]
        self.store = store
        self.ddir = ddir
        self.allowed = allowed
        self.letter_mass = letter_mass

if platform not in ("android", "ios"):
    Window.size = (400, 720)


class WordApp(GameShellApp):
    def open_storage(self) -> None:
        set_theme(T.build_theme())
        from .wordgrid import compute_letter_mass
        # Build one profile (its own DB) per language world.
        self._profiles: dict[str, _LangProfile] = {}
        for spec in LANGUAGES:
            ddir = self.user_data_dir if not spec["subdir"] else os.path.join(self.user_data_dir, spec["subdir"])
            if spec["subdir"]:
                os.makedirs(ddir, exist_ok=True)
            store = WordStore()
            store.open(ddir)
            allowed = pack_allowed_guesses(spec["pack"]) or allowed_guesses()
            mass = compute_letter_mass(allowed) if spec["keyboard"] else None  # non-Latin board
            self._profiles[spec["lang"]] = _LangProfile(spec, store, ddir, allowed, mass)
        self._play_id: int | None = None
        self._day: str | None = None   # the dated daily currently in play (for finish recovery)
        self._allow_mature = bool(self._load_pref("allow_mature", False))
        self._activate(self._load_pref("lang", LANGUAGES[0]["lang"]))
        self._last_random = {"pack": self._active.pack, "difficulty": "medium"}
        self._log(f"open_storage (process start / build) lang={self._lang}")

    def _activate(self, lang: str) -> None:
        """Make `lang` the active world: bind self.store/_allowed to its profile."""
        self._active = self._profiles.get(lang) or self._profiles[LANGUAGES[0]["lang"]]
        self._lang = self._active.lang
        self.store = self._active.store
        self._allowed = self._active.allowed

    def close_storage(self) -> None:
        self._log("close_storage (on_stop)")
        for prof in getattr(self, "_profiles", {}).values():
            prof.store.close()

    # --- Android lifecycle ---
    # build() (hence open_storage) runs once per process. If the app is torn down on
    # backgrounding, on_stop closes the DB but the live widgets remain, so on return
    # the store is closed while the game is still playable -> writes/resume silently
    # operate on a dead connection (a clean win vanishes; the puzzle restarts every
    # open). Returning True from on_pause keeps the process alive so the connection
    # survives; on_resume re-opens defensively in case it didn't.
    def on_pause(self) -> bool:
        self._log("on_pause")
        return True

    def on_resume(self) -> None:
        self._log("on_resume")
        self._ensure_store()

    def on_stop(self) -> None:
        self._log("on_stop")
        super().on_stop()

    def _ensure_store(self) -> None:
        """Reopen any profile store whose connection was closed (e.g. an on_stop fired
        while the process lingered in the background), then re-bind the active one."""
        for prof in getattr(self, "_profiles", {}).values():
            if prof.store is None or not prof.store.is_open():
                self._log(f"store {prof.lang} was closed; reopening")
                prof.store.open(prof.ddir)
        if getattr(self, "_active", None) is not None:
            self.store = self._active.store

    # --- simple JSON prefs in user_data_dir (survives restarts) ---
    def _prefs_path(self) -> str:
        return os.path.join(self.user_data_dir, "settings.json")

    def _load_pref(self, key: str, default: Any) -> Any:
        try:
            with open(self._prefs_path(), encoding="utf-8") as f:
                return json.load(f).get(key, default)
        except (OSError, ValueError):
            return default

    def _save_pref(self, key: str, value: Any) -> None:
        data = {}
        try:
            with open(self._prefs_path(), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            pass
        data[key] = value
        try:
            with open(self._prefs_path(), "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass  # prefs are best-effort; a lost toggle just reverts to default

    def create_screens(self) -> list:
        self.menu_screen = WordMenuScreen(self, name="menu")
        self.game_screen = WordGameScreen(self, name="game")
        self.calendar_screen = WordCalendarScreen(self, name="calendar")
        self.logbook_screen = WordLogbookScreen(self, name="logbook")
        return [SplashScreen(name="splash"), self.menu_screen, self.game_screen,
                self.calendar_screen, self.logbook_screen]

    def on_build(self) -> None:
        # Show the word policy once, after the splash hands off to the menu.
        if not os.path.exists(self._policy_flag):
            Clock.schedule_once(lambda _dt: self.show_policy(mark_seen=True), self.splash_delay + 0.3)

    @property
    def _policy_flag(self) -> str:
        return os.path.join(self.user_data_dir, ".policy_seen")

    # --- menu data ---
    def streak_text(self) -> str:
        s = self.store.streak()
        return f"Streak: {s} day{'s' if s != 1 else ''}" if s > 0 else "Start a streak!"

    def daily_completion(self) -> dict[str, bool]:
        return self.store.today_completion()

    def daily_failed(self) -> dict[str, bool]:
        return self.store.today_failed()

    # --- language worlds ---
    def show_languages(self, instance: Any = None) -> None:
        """The 'Languages' menu item: pick a language world. Switching is live — each
        world keeps its own daily, calendar, and streak (separate DB)."""
        from kivyshell.uikit import FixedGrayRoundedButton, Popup, PopupContent, RoundedButton, TitleLabel
        content = PopupContent()
        content.add_widget(TitleLabel("Language"))
        holder: list = []
        for spec in LANGUAGES:
            current = spec["lang"] == self._lang
            btn = RoundedButton(text=spec["label"] + ("  (current)" if current else ""))
            btn.bind(on_press=lambda _x, lg=spec["lang"]: (holder[0].dismiss(), self.switch_language(lg)))
            content.add_widget(btn)
        close = FixedGrayRoundedButton(text="Close")
        content.add_widget(close)
        popup = Popup(content, height=160 + 52 * len(LANGUAGES), width_hint=0.8)
        holder.append(popup)
        close.bind(on_press=popup.dismiss)
        popup.open()

    def switch_language(self, lang: str) -> None:
        if lang == self._lang or lang not in self._profiles:
            return
        self._activate(lang)
        self._save_pref("lang", lang)
        self._last_random = {"pack": self._active.pack,
                             "difficulty": self._last_random.get("difficulty", "medium")}
        self._log(f"switch language -> {lang}")
        # Refresh the menu to the newly active world (streak + daily badges read self.store).
        if getattr(self, "menu_screen", None) is not None:
            self.sm.current = "menu"
            self.menu_screen.on_enter()

    # --- game flow ---
    def start_daily(self, difficulty: str) -> None:
        today = datetime.date.today().isoformat()
        if self.store.daily_finished(today, difficulty):  # already won or failed: no retry
            self._open_finished_daily(today, difficulty, f"Daily · {difficulty.title()}")
            return
        self._start(self._active.pack, difficulty, today, f"Daily · {difficulty.title()}")

    def _open_finished_daily(self, day: str, difficulty: str, subtitle: str,
                             return_to: str = "menu") -> None:
        """A finished daily can't be replayed, but it can be reviewed exactly as
        last seen. If it predates saved boards, just name the word instead."""
        snap = self.store.review_daily(day, difficulty)
        if snap:
            answer, guesses, elapsed_ms, _won = snap
            self._view_snapshot(answer, guesses, elapsed_ms, subtitle, return_to=return_to)
        else:
            self._show_already_played(day, difficulty)

    def start_random(self, instance: Any = None) -> None:
        """Open the Random Game options popup: difficulty + word pack."""
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.checkbox import CheckBox
        from kivy.uix.label import Label
        from kivy.uix.widget import Widget

        from kivyshell.uikit import (
            FixedGrayRoundedButton,
            FixedRoundedButton,
            Popup,
            PopupContent,
            SelectableButton,
            SelectableButtonGroup,
            SubtitleLabel,
            TitleLabel,
            get_styles,
            get_theme,
            styled,
        )

        packs = self._active.random_packs
        sel = dict(self._last_random)
        if sel["pack"] not in {pid for pid, _ in packs}:  # last pack may be another language's
            sel["pack"] = packs[0][0]
        content = PopupContent()
        content.add_widget(TitleLabel("Random Game"))

        content.add_widget(SubtitleLabel("Difficulty"))
        diff_row = styled(BoxLayout, "selection_row")
        diff_group = SelectableButtonGroup(on_select=lambda v: sel.__setitem__("difficulty", v))
        for d in DIFFICULTIES:
            b = SelectableButton(text=d.title(), selected=(d == sel["difficulty"]), **get_styles()["selection_btn"])
            diff_group.add(d, b)
            diff_row.add_widget(b)
        content.add_widget(diff_row)

        content.add_widget(SubtitleLabel("Word Pack"))
        pack_row = styled(BoxLayout, "selection_row")
        pack_group = SelectableButtonGroup(on_select=lambda v: sel.__setitem__("pack", v))
        for pid, label in packs:
            b = SelectableButton(text=label, selected=(pid == sel["pack"]), **get_styles()["selection_btn"])
            pack_group.add(pid, b)
            pack_row.add_widget(b)
        content.add_widget(pack_row)

        # Global toggle: allow vulgar/anatomical words to be served as answers.
        # (Slurs are never eligible regardless.) Persists across restarts and
        # applies to daily games too.
        content.add_widget(SubtitleLabel("Answers"))
        mature_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        cb = CheckBox(active=self._allow_mature, size_hint=(None, 1), width=dp(36))

        def _toggle_mature(_c: Any, val: bool) -> None:
            self._allow_mature = val
            self._save_pref("allow_mature", val)

        cb.bind(active=_toggle_mature)
        lbl = Label(text="Allow mature words as answers", font_name=get_theme().font_name,
                    font_size="14sp", color=get_theme().text_dark, halign="left", valign="middle")
        lbl.bind(size=lambda i, _v: setattr(i, "text_size", i.size))
        mature_row.add_widget(cb)
        mature_row.add_widget(lbl)
        content.add_widget(mature_row)

        content.add_widget(styled(Widget, "spacer_sm"))
        holder: list = []

        def on_play(_x: Any) -> None:
            self._last_random = dict(sel)
            holder[0].dismiss()
            self._start(sel["pack"], sel["difficulty"], None,
                        f"{PACK_LABEL.get(sel['pack'], sel['pack'])} · {sel['difficulty'].title()}")

        play = FixedRoundedButton(text="Play")
        play.bind(on_press=on_play)
        content.add_widget(play)
        cancel = FixedGrayRoundedButton(text="Cancel")
        content.add_widget(cancel)

        popup = Popup(content, height=440, width_hint=0.85)
        holder.append(popup)
        cancel.bind(on_press=popup.dismiss)
        popup.open()

    def play_date(self, d: datetime.date) -> None:
        """Tapping a calendar day: choose a difficulty, then play that day's word."""
        from kivyshell.uikit import FixedGrayRoundedButton, Popup, PopupContent, RoundedButton, SizeButtonRow, TitleLabel
        content = PopupContent()
        title = "Today's Word" if d == datetime.date.today() else d.strftime("%B %d, %Y")
        content.add_widget(TitleLabel(title, height=40))
        row = SizeButtonRow()
        popup_holder: list = []

        def choose(diff: str) -> None:
            popup_holder[0].dismiss()
            if self.store.daily_finished(d.isoformat(), diff):  # already won or failed: no retry
                self._open_finished_daily(d.isoformat(), diff, f"{title} · {diff.title()}",
                                          return_to="calendar")
                return
            self._start(self._active.pack, diff, d.isoformat(), f"{title} · {diff.title()}",
                        return_to="calendar")

        for diff in ("easy", "medium", "hard"):
            btn = RoundedButton(text=diff.title())
            btn.bind(on_press=lambda _x, dd=diff: choose(dd))
            row.add_widget(btn)
        content.add_widget(row)
        cancel = FixedGrayRoundedButton(text="Cancel")
        content.add_widget(cancel)
        popup = Popup(content, height=200, width_hint=0.8)
        popup_holder.append(popup)
        cancel.bind(on_press=popup.dismiss)
        popup.open()

    def _start(self, pack: str, difficulty: str, day: str | None, subtitle: str,
               return_to: str = "menu") -> None:
        # The mature toggle applies to random games only. Dated games (daily and
        # calendar dates, seed=day) must be identical for every player, so they
        # always draw from the standard filtered pool regardless of the setting.
        self._ensure_store()  # never run on a connection an on_stop may have closed
        allow_mature = self._allow_mature and day is None
        answer = worddata.pick_word(pack, difficulty, seed=day, allow_mature=allow_mature)
        self._current = (pack, difficulty, answer)
        resume = self.store.start(difficulty, day, answer)  # resumes an unfinished daily
        self._play_id = resume.play_id
        self._day = day
        self._log(f"start day={day} diff={difficulty} play_id={resume.play_id} resumed={len(resume.guesses)}")
        game = WordGame(answer)
        if resume.guesses:
            game.restore(resume.guesses)
        self._game = game
        # Only dated (daily/calendar) games are resumable; random games don't persist.
        on_progress = self._on_progress if day is not None else None
        self.game_screen.set_game(game, self._allowed, subtitle, self._on_finish,
                                  self.show_word_info, on_progress=on_progress,
                                  elapsed_ms=resume.elapsed_ms, return_to=return_to,
                                  keyboard=self._active.keyboard, letter_mass=self._active.letter_mass)
        self.sm.current = "game"

    def view_play(self, play: Any) -> None:
        """Reopen a finished game from the logbook (daily OR random), read-only."""
        snap = self.store.review_play(play.code, play.started_at)
        if not snap:
            self._show_review_unavailable(answer_of(play.code))
            return
        answer, guesses, elapsed_ms, _won = snap
        kind = "Daily" if play.date else "Random"
        self._view_snapshot(answer, guesses, elapsed_ms, f"{kind} · {play.variant_id.title()}",
                            return_to="logbook")

    def _view_snapshot(self, answer: str, guesses: list, elapsed_ms: int, subtitle: str,
                       return_to: str = "menu") -> None:
        """Rebuild a finished board and show it, frozen (no timer, no input, no re-record)."""
        game = WordGame(answer, max_guesses=max(6, len(guesses)))
        game.restore(guesses)
        game.finished = True  # replaying a loss short of max wouldn't set it on its own
        self._current = (self._active.pack, "", answer)
        self._game = game
        self._play_id = None  # viewing only: nothing to record or persist
        self.game_screen.set_game(game, self._allowed, subtitle, self._on_finish,
                                  self.show_word_info, on_progress=None, elapsed_ms=elapsed_ms,
                                  return_to=return_to,
                                  keyboard=self._active.keyboard, letter_mass=self._active.letter_mass)
        self.sm.current = "game"

    def _show_review_unavailable(self, answer: str) -> None:
        from kivyshell.uikit import FixedGrayRoundedButton, Popup, PopupContent, SubtitleLabel, TitleLabel
        content = PopupContent()
        content.add_widget(TitleLabel("No saved board"))
        content.add_widget(SubtitleLabel(f"This game has no saved board to review. The word was {answer.upper()}."))
        close = FixedGrayRoundedButton(text="Close")
        content.add_widget(close)
        popup = Popup(content, height=220)
        close.bind(on_press=popup.dismiss)
        popup.open()

    def _on_progress(self, guesses: list, elapsed_ms: int) -> None:
        if self._play_id is not None:
            self.store.save_progress(self._play_id, elapsed_ms, guesses)

    def _log(self, msg: str) -> None:
        """Append a timestamped line to a small event log (for chasing the elusive
        'win didn't record' bug). Exportable from the dev menu; best-effort."""
        try:
            import datetime
            with open(os.path.join(self.user_data_dir, "yawop_events.log"), "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now().isoformat()} {msg}\n")
        except Exception:  # noqa: BLE001
            pass

    def _on_finish(self, won: bool, duration_ms: int, attempts: int) -> None:
        _, difficulty, answer = self._current
        pid, recovered = self._play_id, False
        if pid is None and won and not self._game.lost and self._day is not None:
            # A CLEAN win with no play id shouldn't happen (only a bonus win after a
            # loss legitimately has no play id, and that's gated by game.lost above).
            # It means the play/session state got confused (an intermittent, so-far-
            # unreproducible bug). Re-acquire the day's play so the win still records
            # instead of being silently dropped.
            pid = self.store.start(difficulty, self._day, answer).play_id
            recovered = True
        if pid is not None:
            # record win AND lose, and snapshot the final board for later review
            self.store.finish(pid, won, duration_ms, attempts, list(self._game.guesses), duration_ms)
        self._log(f"finish day={self._day} diff={difficulty} won={won} lost={self._game.lost} "
                  f"play_id={pid} recovered={recovered}")
        self._play_id = None  # once recorded, 'another try' rounds don't re-record
        if won and not self._game.lost:
            self._show_success(answer, attempts, duration_ms)
        elif won:  # solved only in a bonus row after the game was already lost
            self._show_bonus_solved(answer)
        else:
            self._show_game_failed(answer)

    def _show_success(self, word: str, attempts: int, duration_ms: int) -> None:
        from kivy.metrics import dp
        from kivy.uix.image import Image
        from kivy.uix.label import Label
        from kivy.uix.widget import Widget

        from kivyshell.uikit import FixedGrayRoundedButton, FixedRoundedButton, Popup, PopupContent, get_theme

        theme = get_theme()
        secs = (duration_ms or 0) // 1000
        when = f"{secs} seconds" if secs < 60 else f"{secs // 60} min {secs % 60:02d} sec"
        tries = f"{attempts} {'try' if attempts == 1 else 'tries'}"

        content = PopupContent()
        # badge_icon is a tint-me silhouette; gold it (like the calendar's win badge)
        content.add_widget(Image(source=theme.badge_icon, color=theme.badge_on_time,
                                 size_hint_y=None, height=dp(64), fit_mode="contain"))

        def centered(text, size, color, h, bold=True):
            lbl = Label(text=text, font_name=theme.font_name, font_size=size, bold=bold, color=color,
                        size_hint_y=None, height=dp(h), halign="center", valign="middle")
            lbl.bind(size=lambda i, _v: setattr(i, "text_size", i.size))
            return lbl

        content.add_widget(centered("Success!", "26sp", (0.30, 0.62, 0.36, 1), 36))
        content.add_widget(centered(word.upper(), "30sp", self._ACCENT_DARK, 42))
        content.add_widget(centered(f"guessed in {tries} and {when}", "15sp", theme.text_dark, 26, bold=False))
        content.add_widget(Widget(size_hint_y=None, height=dp(4)))

        lookup = FixedRoundedButton(text="Look it up")
        content.add_widget(lookup)
        close = FixedGrayRoundedButton(text="Close")
        content.add_widget(close)
        popup = Popup(content, height=420)
        lookup.bind(on_press=lambda *_: (popup.dismiss(), self.show_word_info(word)))
        close.bind(on_press=popup.dismiss)
        popup.open()

    def _show_bonus_solved(self, word: str) -> None:
        """Subdued acknowledgement: solved in a bonus row, but the game was already
        lost, so no celebration (no gold badge, no time/tries stats)."""
        from kivy.metrics import dp
        from kivy.uix.label import Label
        from kivy.uix.widget import Widget

        from kivyshell.uikit import FixedGrayRoundedButton, FixedRoundedButton, Popup, PopupContent, get_theme

        theme = get_theme()
        content = PopupContent()

        def centered(text, size, color, h, bold=True):
            lbl = Label(text=text, font_name=theme.font_name, font_size=size, bold=bold, color=color,
                        size_hint_y=None, height=dp(h), halign="center", valign="middle")
            lbl.bind(size=lambda i, _v: setattr(i, "text_size", i.size))
            return lbl

        content.add_widget(centered("You've got it", "24sp", theme.text_dark, 34))
        content.add_widget(centered(word.upper(), "30sp", self._ACCENT_DARK, 42))
        content.add_widget(centered("…but the game was already lost.", "14sp", theme.text_medium, 24, bold=False))
        content.add_widget(Widget(size_hint_y=None, height=dp(4)))

        lookup = FixedRoundedButton(text="Look it up")
        content.add_widget(lookup)
        close = FixedGrayRoundedButton(text="Close")
        content.add_widget(close)
        popup = Popup(content, height=360)
        lookup.bind(on_press=lambda *_: (popup.dismiss(), self.show_word_info(word)))
        close.bind(on_press=popup.dismiss)
        popup.open()

    def _reveal_answer(self, answer: str) -> None:
        entry = worddata.lookup_entry(answer)
        definition = entry["senses"][0]["definition"] if entry and entry.get("senses") else ""
        self.game_screen.show_reveal(f"{answer.upper()} — {definition}" if definition else answer.upper())

    def _show_game_failed(self, answer: str) -> None:
        from kivyshell.uikit import FixedGrayRoundedButton, FixedRoundedButton, Popup, PopupContent, SubtitleLabel, TitleLabel
        content = PopupContent()
        content.add_widget(TitleLabel("Game Failed"))
        content.add_widget(SubtitleLabel("Out of tries — counts as a loss."))
        again = FixedRoundedButton(text="Another try")
        content.add_widget(again)
        reveal = FixedGrayRoundedButton(text="Reveal the word")
        content.add_widget(reveal)
        popup = Popup(content, height=250)
        again.bind(on_press=lambda *_: (popup.dismiss(), self.game_screen.another_try()))
        reveal.bind(on_press=lambda *_: (popup.dismiss(), self._reveal_answer(answer)))
        popup.open()

    def _show_already_played(self, day: str, difficulty: str) -> None:
        from kivyshell.uikit import FixedGrayRoundedButton, Popup, PopupContent, SubtitleLabel, TitleLabel
        answer = worddata.pick_word(self._active.pack, difficulty, seed=day)
        content = PopupContent()
        content.add_widget(TitleLabel("Already played"))
        content.add_widget(SubtitleLabel(f"That day's {difficulty} word was {answer.upper()}."))
        close = FixedGrayRoundedButton(text="Close")
        content.add_widget(close)
        popup = Popup(content, height=220)
        close.bind(on_press=popup.dismiss)
        popup.open()

    # Part-of-speech chip colors for the definition popup (foreground accents).
    _POS_COLORS = {
        "nou": (0.30, 0.52, 0.82, 1),   # noun  - blue
        "ver": (0.42, 0.67, 0.39, 1),   # verb  - green
        "adj": (0.86, 0.63, 0.24, 1),   # adjective - amber
        "adv": (0.55, 0.45, 0.80, 1),   # adverb - violet
    }
    _POS_DEFAULT = (0.47, 0.48, 0.50, 1)
    _ACCENT = (0.24, 0.47, 0.78, 1)      # section headers / quote bar
    _ACCENT_DARK = (0.16, 0.34, 0.62, 1)  # word title
    # Compact definition-source labels (dictionaryapi.dev is Wiktionary-sourced).
    _SRC_LABEL = {"wiktionary": "Wiktionary", "dictionaryapi.dev": "Wiktionary", "wordnet": "WordNet"}

    def show_word_info(self, word: str, committed: bool = True) -> None:
        """Popup: nicely structured, colorful definitions + usage examples."""
        from kivy.graphics import Color, Rectangle, RoundedRectangle
        from kivy.metrics import dp
        from kivy.uix.anchorlayout import AnchorLayout
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.label import Label
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.widget import Widget

        from kivyshell.uikit import FixedGrayRoundedButton, Popup, PopupContent, get_theme

        theme = get_theme()

        def para(text, size="14sp", color=None, bold=False):
            lbl = Label(text=text, font_name=theme.font_name, font_size=size, bold=bold,
                        color=color or theme.text_dark, size_hint_y=None, halign="left", valign="top")
            lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)),
                     texture_size=lambda i, s: setattr(i, "height", s[1] + dp(4)))
            return lbl

        def pos_color(label):
            return self._POS_COLORS.get((label or "")[:3].lower(), self._POS_DEFAULT)

        def chip(label, color):
            c = Label(text=label or "—", font_name=theme.font_name, font_size="11sp", bold=True,
                      color=(1, 1, 1, 1), size_hint=(None, None), halign="center", valign="middle")
            c.bind(texture_size=lambda i, s: setattr(i, "size", (s[0] + dp(14), s[1] + dp(6))))

            def draw(*_a):
                c.canvas.before.clear()
                with c.canvas.before:
                    Color(*color)
                    RoundedRectangle(pos=c.pos, size=c.size, radius=[dp(9)])
            c.bind(pos=draw, size=draw)
            return c

        def header(text):
            h = Label(text=text.upper(), font_name=theme.font_name, font_size="13sp", bold=True,
                      color=self._ACCENT, size_hint_y=None, height=dp(22), halign="left", valign="middle")
            h.bind(size=lambda i, _v: setattr(i, "text_size", i.size))
            return h

        def sense_row(pos_label, definition):
            row = BoxLayout(orientation="horizontal", size_hint_y=None, spacing=dp(8), height=dp(26))
            holder = AnchorLayout(anchor_x="left", anchor_y="top", size_hint=(None, 1), width=dp(66))
            holder.add_widget(chip(pos_label, pos_color(pos_label)))
            d = para(definition)
            d.bind(height=lambda i, h: setattr(row, "height", max(h, dp(26))))
            row.add_widget(holder)
            row.add_widget(d)
            return row

        def example_row(quote, who):
            row = BoxLayout(orientation="horizontal", size_hint_y=None, spacing=dp(8), height=dp(24))
            bar = Widget(size_hint=(None, 1), width=dp(3))

            def barbg(*_a):
                bar.canvas.before.clear()
                with bar.canvas.before:
                    Color(*self._ACCENT)
                    Rectangle(pos=bar.pos, size=bar.size)
            bar.bind(pos=barbg, size=barbg)
            col = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(1))
            col.bind(minimum_height=col.setter("height"),
                     height=lambda i, h: setattr(row, "height", max(h, dp(24))))
            col.add_widget(para(f"“{quote}”", size="13sp"))
            if who:
                col.add_widget(para(who, size="11sp", color=theme.text_medium))
            row.add_widget(bar)
            row.add_widget(col)
            return row

        entry = worddata.lookup_entry(word)
        content = PopupContent()

        # Colored word title + accent divider.
        title = Label(text=word.upper(), font_name=theme.font_name, font_size="30sp", bold=True,
                      color=self._ACCENT_DARK, size_hint_y=None, height=dp(44), halign="center", valign="middle")
        title.bind(size=lambda i, _v: setattr(i, "text_size", i.size))
        content.add_widget(title)
        divider = Widget(size_hint_y=None, height=dp(2))

        def div_bg(*_a):
            divider.canvas.before.clear()
            with divider.canvas.before:
                Color(self._ACCENT[0], self._ACCENT[1], self._ACCENT[2], 0.35)
                Rectangle(pos=divider.pos, size=divider.size)
        divider.bind(pos=div_bg, size=div_bg)
        content.add_widget(divider)

        # Provenance is a hint (it reveals a word is answer-eligible), so only show it
        # once the guess is committed — not when peeking a typed-but-unsubmitted word.
        if committed:
            from worddata.store import answer_packs
            apacks = answer_packs(word)
            if apacks:
                prov = Label(text="Can be the answer in:  " + "  ·  ".join(apacks),
                             color=(0.30, 0.62, 0.36, 1))
            else:
                prov = Label(text="Allowed as a guess only", color=theme.text_medium)
            prov.font_name, prov.font_size, prov.size_hint_y = theme.font_name, "12sp", None
            prov.halign, prov.valign = "center", "middle"
            prov.bind(width=lambda i, w: setattr(i, "text_size", (w, None)),
                      texture_size=lambda i, s: setattr(i, "height", s[1] + dp(4)))
            content.add_widget(prov)

        body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(7), padding=[dp(2), dp(6)])
        body.bind(minimum_height=body.setter("height"))
        if not entry or (not entry["senses"] and not entry["examples"]):
            body.add_widget(para("No definition on hand for this one yet — it's a valid word "
                                 "(see the source above), just an obscure one.", color=theme.text_medium))
        else:
            if entry["senses"]:
                body.add_widget(header("Definitions"))
                for s in entry["senses"]:
                    body.add_widget(sense_row(s.get("pos_label", ""), s.get("definition", "")))
            if entry["examples"]:
                body.add_widget(Widget(size_hint_y=None, height=dp(4)))
                body.add_widget(header("Usage"))
                for ex in entry["examples"]:
                    who = " — ".join(x for x in (ex.get("author"), ex.get("work")) if x)
                    body.add_widget(example_row(ex.get("text", ""), who))
            # compact one-line attribution of the definition source(s)
            srcs = []
            for s in entry["senses"]:
                lbl = self._SRC_LABEL.get(s.get("source"), (s.get("source") or "").title())
                if lbl and lbl not in srcs:
                    srcs.append(lbl)
            if srcs:
                credit = Label(text="via " + " · ".join(srcs), font_name=theme.font_name,
                               font_size="10sp", color=theme.text_medium, size_hint_y=None,
                               height=dp(16), halign="right", valign="middle")
                credit.bind(size=lambda i, _v: setattr(i, "text_size", i.size))
                body.add_widget(credit)

        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(body)
        content.add_widget(scroll)
        close = FixedGrayRoundedButton(text="Close")
        content.add_widget(close)
        popup = Popup(content, height=480)
        close.bind(on_press=popup.dismiss)
        popup.open()

    def show_policy(self, instance: Any = None, mark_seen: bool = False) -> None:
        """A human, one-time explanation of how we choose (and don't choose) words."""
        from kivy.graphics import Color, RoundedRectangle
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.label import Label
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.widget import Widget

        from kivyshell.uikit import FixedRoundedButton, Popup, PopupContent, get_theme

        theme = get_theme()
        RED = (0.80, 0.29, 0.29, 1)     # the hard block
        GREEN = (0.36, 0.60, 0.36, 1)   # what's allowed

        def para(text, size="14sp", color=None):
            lbl = Label(text=text, font_name=theme.font_name, font_size=size,
                        color=color or theme.text_dark, size_hint_y=None, halign="left", valign="top")
            lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)),
                     texture_size=lambda i, s: setattr(i, "height", s[1] + dp(4)))
            return lbl

        def block(bar_color, heading, text):
            row = BoxLayout(orientation="horizontal", size_hint_y=None, spacing=dp(10), height=dp(40))
            bar = Widget(size_hint=(None, 1), width=dp(4))

            def barbg(*_a):
                bar.canvas.before.clear()
                with bar.canvas.before:
                    Color(*bar_color)
                    RoundedRectangle(pos=bar.pos, size=bar.size, radius=[dp(2)])
            bar.bind(pos=barbg, size=barbg)
            col = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2))
            col.bind(minimum_height=col.setter("height"),
                     height=lambda i, h: setattr(row, "height", max(h, dp(40))))
            hd = Label(text=heading, font_name=theme.font_name, font_size="15sp", bold=True,
                       color=bar_color, size_hint_y=None, halign="left", valign="middle")
            hd.bind(width=lambda i, w: setattr(i, "text_size", (w, None)),
                    texture_size=lambda i, s: setattr(i, "height", s[1] + dp(2)))
            col.add_widget(hd)
            col.add_widget(para(text))
            row.add_widget(bar)
            row.add_widget(col)
            return row

        content = PopupContent()
        title = Label(text="About the words", font_name=theme.font_name, font_size="24sp", bold=True,
                      color=self._ACCENT_DARK, size_hint_y=None, height=dp(40), halign="center", valign="middle")
        title.bind(size=lambda i, _v: setattr(i, "text_size", i.size))
        content.add_widget(title)
        divider = Widget(size_hint_y=None, height=dp(2))

        def div_bg(*_a):
            divider.canvas.before.clear()
            with divider.canvas.before:
                Color(self._ACCENT[0], self._ACCENT[1], self._ACCENT[2], 0.35)
                RoundedRectangle(pos=divider.pos, size=divider.size, radius=[dp(1)])
        divider.bind(pos=div_bg, size=div_bg)
        content.add_widget(divider)

        body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(12), padding=[dp(2), dp(6)])
        body.bind(minimum_height=body.setter("height"))
        body.add_widget(para("yawop pulls its answers from real language: subtitles, books, "
                             "the official Wordle list. So every now and then a word turns up "
                             "that's crude or anatomical. Here's the honest deal."))
        body.add_widget(block(RED, "Slurs are out, completely.",
                              "You'll never see one as an answer, and the game won't even accept "
                              "one as a guess."))
        body.add_widget(block(GREEN, "Real words stay real.",
                              "Crude or anatomical words are still fair game as guesses: we're not "
                              "here to police the language. By default we just won't serve one up as "
                              "the answer of the day, because a puzzle shouldn't put an awkward word "
                              "on your screen when you didn't ask for it."))
        body.add_widget(block(self._ACCENT, "Want the unfiltered language?",
                              "Flip \"Allow mature words as answers\" in Random Game, and they're in "
                              "play as solutions too."))

        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(body)
        content.add_widget(scroll)
        btn = FixedRoundedButton(text="Got it")
        content.add_widget(btn)
        popup = Popup(content, height=470)
        btn.bind(on_press=popup.dismiss)
        if mark_seen:
            try:
                open(self._policy_flag, "w").close()
            except OSError:
                pass  # first-launch flag is best-effort; a re-show next time is harmless
        popup.open()

    def show_about(self, instance: Any = None) -> None:
        from kivy.uix.behaviors import ButtonBehavior
        from kivy.uix.label import Label

        from kivyshell.uikit import (CaptionLabel, FixedGrayRoundedButton, FixedRoundedButton,
                                     LinkButton, Popup, PopupContent, SubtitleLabel, TitleLabel, get_theme)

        from .version import __version__
        content = PopupContent()
        content.add_widget(TitleLabel("yawop"))
        content.add_widget(SubtitleLabel("Yet Another WOrd Puzzle"))

        # Tapping the version 5× quickly opens the hidden developer menu.
        class _TapLabel(ButtonBehavior, Label):
            pass
        theme = get_theme()
        taps = {"n": 0, "t": 0.0}
        ver = _TapLabel(text=f"version {__version__}", font_name=theme.font_name, font_size="12sp",
                        color=theme.text_medium, size_hint_y=None, height=24, bold=True)

        def _ver_tap(*_a: Any) -> None:
            import time as _t
            now = _t.time()
            taps["n"] = taps["n"] + 1 if now - taps["t"] < 2.0 else 1
            taps["t"] = now
            if taps["n"] >= 5:
                taps["n"] = 0
                popup.dismiss()
                self._show_dev_menu()

        ver.bind(on_press=_ver_tap)
        content.add_widget(ver)
        content.add_widget(CaptionLabel("Definitions: WordNet (Princeton) · Wiktionary (CC BY-SA)"))
        content.add_widget(CaptionLabel("License: GNU AGPL v3 · free & open source"))

        gh = LinkButton("github.com/anverx/yawop")
        gh.bind(on_press=lambda *_: self._open_url("https://github.com/anverx/yawop"))
        content.add_widget(gh)

        policy = FixedRoundedButton(text="About the words")
        content.add_widget(policy)
        close = FixedGrayRoundedButton(text="Close")
        content.add_widget(close)
        popup = Popup(content, height=380)
        policy.bind(on_press=lambda *_: (popup.dismiss(), self.show_policy()))
        close.bind(on_press=popup.dismiss)
        popup.open()

    def _open_url(self, url: str) -> None:
        import webbrowser
        webbrowser.open(url)

    def _show_dev_menu(self) -> None:
        """Hidden developer menu (reached by tapping the About version 5×). Exports the
        sqlite DB so a game's state can be inspected off-device."""
        import datetime

        from kivy.metrics import dp
        from kivy.uix.label import Label

        from kivyshell.uikit import FixedGrayRoundedButton, FixedRoundedButton, Popup, PopupContent, TitleLabel, get_theme

        theme = get_theme()
        content = PopupContent()
        content.add_widget(TitleLabel("Developer"))
        status = Label(text="", font_name=theme.font_name, font_size="12sp", color=theme.text_medium,
                       size_hint_y=None, height=dp(52), halign="center", valign="middle")
        status.bind(size=lambda i, _v: setattr(i, "text_size", i.size))
        content.add_widget(status)

        filename = f"yawop_{datetime.date.today().isoformat()}.db"

        def export_db(*_a: Any) -> None:
            import os
            path = self.store.db_path()
            if not path or not os.path.exists(path):
                status.text = "No database on disk."
                return
            from kivy.utils import platform
            if platform == "android":
                try:
                    with open(path, "rb") as f:
                        self._android_save_file(f.read(), "application/x-sqlite3", filename, status)
                except Exception as e:  # noqa: BLE001
                    status.text = f"Error: {e}"
            else:
                import shutil
                try:
                    dest = os.path.join(os.path.expanduser("~"), "Downloads", filename)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(path, dest)
                    status.text = f"Saved to {dest}"
                except Exception as e:  # noqa: BLE001
                    status.text = f"Error: {e}"

        def export_log(*_a: Any) -> None:
            path = os.path.join(self.user_data_dir, "yawop_events.log")
            if not os.path.exists(path):
                status.text = "No event log yet."
                return
            # Export as .txt (matches text/plain): Android's document picker rewrites a
            # mismatched extension to a fallback like "(invalid).txt".
            log_filename = f"yawop-events-{datetime.date.today().isoformat()}.txt"
            from kivy.utils import platform
            if platform == "android":
                try:
                    with open(path, "rb") as f:
                        self._android_save_file(f.read(), "text/plain", log_filename, status)
                except Exception as e:  # noqa: BLE001
                    status.text = f"Error: {e}"
            else:
                import shutil
                try:
                    dest = os.path.join(os.path.expanduser("~"), "Downloads", log_filename)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(path, dest)
                    status.text = f"Saved to {dest}"
                except Exception as e:  # noqa: BLE001
                    status.text = f"Error: {e}"

        btn = FixedRoundedButton(text="Export database")
        btn.bind(on_press=export_db)
        content.add_widget(btn)
        logbtn = FixedRoundedButton(text="Export event log")
        logbtn.bind(on_press=export_log)
        content.add_widget(logbtn)
        close = FixedGrayRoundedButton(text="Close")
        content.add_widget(close)
        popup = Popup(content, height=360)
        close.bind(on_press=popup.dismiss)
        popup.open()

    def _android_save_file(self, content_bytes: bytes, mime_type: str, filename: str, status: Any) -> None:
        """Let the user pick a save location via the system 'create document' dialog
        (Storage Access Framework) — no storage permission needed. Defaults near Downloads."""
        from android import activity as android_activity  # type: ignore
        from android import mActivity  # type: ignore
        from jnius import autoclass  # type: ignore

        Intent = autoclass("android.content.Intent")
        request_code = 9042

        def on_result(req_code: int, result_code: int, intent_data: Any) -> None:
            android_activity.unbind(on_activity_result=on_result)
            if req_code != request_code:
                return
            if result_code != -1 or intent_data is None:   # -1 == RESULT_OK
                status.text = "Export cancelled"
                return
            try:
                stream = mActivity.getContentResolver().openOutputStream(intent_data.getData())
                stream.write(content_bytes)
                stream.flush()
                stream.close()
                status.text = f"Exported {filename}"
            except Exception as e:  # noqa: BLE001
                status.text = f"Error saving: {e}"

        android_activity.bind(on_activity_result=on_result)
        intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType(mime_type)
        intent.putExtra(Intent.EXTRA_TITLE, filename)
        mActivity.startActivityForResult(intent, request_code)

    # Starting-strategy openers: a first word, then second-word options. The score is
    # the combined frequency of the DISTINCT letters the pair probes (overlaps count
    # once), so a good follow-up adds new common letters rather than repeating them.
    _FAVOURITE = ("RAISE", "POUND")
    _OPENERS = [
        ("SLATE", ["CRONY", "CLOUT", "PILOT"]),
        ("CRANE", ["TANGY", "PIOUS", "BIDET"]),
        ("ADIEU", ["CLIMB", "SHIRT", "SPORT"]),
    ]

    def show_help(self, instance: Any = None) -> None:
        from kivy.metrics import dp, sp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.label import Label
        from kivy.uix.scrollview import ScrollView

        from kivyshell.uikit import FixedGrayRoundedButton, Popup, PopupContent, SubtitleLabel, TitleLabel, get_theme

        from . import theme as T
        from .wordgrid import LETTER_MASS

        theme = get_theme()
        green, grey = (0.30, 0.62, 0.36, 1), theme.text_medium

        def pair_score(a: str, b: str) -> int:
            return sum(LETTER_MASS.get(c, 0) for c in set((a + b).lower()))

        def fit(lbl: Label) -> Label:
            lbl.bind(size=lambda i, _v: setattr(i, "text_size", i.size))
            return lbl

        def hx(c: tuple) -> str:
            return "%02x%02x%02x" % (int(c[0] * 255), int(c[1] * 255), int(c[2] * 255))

        content = PopupContent()
        content.add_widget(TitleLabel("How to play"))

        sv = ScrollView(size_hint=(1, 1))
        col = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=[0, dp(4)])
        col.bind(minimum_height=col.setter("height"))
        sv.add_widget(col)
        content.add_widget(sv)

        # Rules — colour the keywords with their tile colours.
        rules = ("Guess the hidden 5-letter word in six tries.\n"
                 f"[b][color={hx(T.TILE_CORRECT)}]Green[/color][/b] = right letter, right spot.\n"
                 f"[b][color={hx(T.TILE_PRESENT)}]Yellow[/color][/b] = right letter, wrong spot.\n"
                 f"[b][color={hx(T.TILE_ABSENT)}]Gray[/color][/b] = not in the word.")
        col.add_widget(fit(Label(text=rules, markup=True, font_name=theme.font_name, font_size="14sp",
                                 color=theme.text_dark, halign="center", valign="middle",
                                 size_hint_y=None, height=dp(104))))

        col.add_widget(SubtitleLabel("Starting strategies", size_hint_y=None, height=dp(30)))
        col.add_widget(fit(Label(
            text="Openers that probe many common letters. Score = combined frequency of the "
                 "distinct letters the pair tests (overlaps count once) — best in green.",
            font_name=theme.font_name, font_size="13sp", color=theme.text_medium,
            halign="center", valign="middle", size_hint_y=None, height=dp(58))))

        def opener_block(first: str, options: list[str], fav: bool = False) -> BoxLayout:
            block = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(72), spacing=dp(2))
            # » renders in Roboto (→ and ★ don't); mark the favourite with green text
            head = f"[b]{first}[/b]  »  then" + ("   (a favourite)" if fav else "")
            h = Label(text=head, markup=True, font_name=theme.font_name, font_size="15sp",
                      color=(theme.text_dark if not fav else green), size_hint_y=None, height=dp(24),
                      halign="left", valign="middle")
            block.add_widget(fit(h))
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(46), spacing=dp(6))
            ranked = sorted(options, key=lambda o: -pair_score(first, o))
            for i, o in enumerate(ranked):
                best = (i == 0)
                lbl = Label(text=f"[b]{o}[/b]\n[size={round(sp(11))}]{pair_score(first, o)}[/size]",
                            markup=True, font_name=theme.font_name, font_size="16sp",
                            color=(green if best else grey), halign="center", valign="middle")
                row.add_widget(fit(lbl))
            block.add_widget(row)
            return block

        fa, fb = self._FAVOURITE
        col.add_widget(opener_block(fa, [fb], fav=True))
        for first, opts in self._OPENERS:
            col.add_widget(opener_block(first, opts))

        close = FixedGrayRoundedButton(text="Close")
        content.add_widget(close)
        popup = Popup(content, height=540)
        close.bind(on_press=popup.dismiss)
        popup.open()
