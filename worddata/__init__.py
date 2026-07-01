"""Game-runtime access to the shipped word dictionaries.

Reads the built-in dictionaries under assets/dictionaries/ (published by the
build pipeline). Stdlib-only; independent of the pipeline's tooling.

    from worddata import pick_word, lookup_entry
"""

__all__ = ["pick_word", "lookup_entry"]


def __getattr__(name):  # lazy so `python -m worddata.pick` doesn't double-import
    if name == "pick_word":
        from .pick import pick_word
        return pick_word
    if name == "lookup_entry":
        from .lookup import lookup_entry
        return lookup_entry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
