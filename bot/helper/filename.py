"""Conservative cleanup for Telegram media filenames."""

import re

from bot.config import Telegram


URL_PATTERN = re.compile(r"(?:https?://|www\.|t\.me/|telegram\.me/)\S+", re.IGNORECASE)
HANDLE_PATTERN = re.compile(r"(?<!\w)@[A-Za-z][A-Za-z0-9_]{3,}")
PROMO_BRACKETS = re.compile(
    r"[\[(][^\])]*(?:join|telegram|channel|downloaded from|www\.|https?://|t\.me|@)[^\])]*[\])]",
    re.IGNORECASE,
)
SEPARATORS = re.compile(r"[._|]+")
SPACES = re.compile(r"\s{2,}")


def clean_filename(value: str) -> str:
    """Remove obvious links/channel promotions without destroying media metadata."""
    name = str(value or "Untitled").strip()
    name = URL_PATTERN.sub(" ", name)
    name = PROMO_BRACKETS.sub(" ", name)
    name = HANDLE_PATTERN.sub(" ", name)
    if Telegram.FILENAME_CLEANUP_REGEX:
        name = re.sub(Telegram.FILENAME_CLEANUP_REGEX, " ", name, flags=re.IGNORECASE)
    name = SEPARATORS.sub(" ", name)
    name = SPACES.sub(" ", name).strip(" -–—[]()")
    return name[:500] or "Untitled"
