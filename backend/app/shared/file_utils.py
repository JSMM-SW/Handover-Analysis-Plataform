import re
from pathlib import Path

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_filename(filename: str) -> str:
    """Reduces a client-supplied filename to a safe basename.

    Strips any directory components (protects against path traversal via
    '../' or absolute paths) and replaces characters outside a conservative
    whitelist, so the result is always safe to join under a fixed data
    directory.
    """
    name = Path(filename).name  # drops any directory component
    stem, _, suffix = name.rpartition(".")
    if not stem:
        stem, suffix = suffix, ""

    safe_stem = _UNSAFE_CHARS.sub("_", stem).strip("._") or "archivo"
    safe_suffix = _UNSAFE_CHARS.sub("", suffix).lower()

    return f"{safe_stem}.{safe_suffix}" if safe_suffix else safe_stem


def get_extension(filename: str) -> str:
    return Path(filename).suffix.lower()
