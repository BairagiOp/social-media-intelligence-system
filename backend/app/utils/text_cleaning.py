"""Text preprocessing utilities.

The original raw text is always preserved; cleaned text is written to a
separate `text_clean` column for model consumption.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MENTION_RE = re.compile(r"@\w{1,50}")
HASHTAG_RE = re.compile(r"#(\w{1,80})")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002700-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)
NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]")
WHITESPACE_RE = re.compile(r"\s+")

try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer

    _NLTK_READY = False
except Exception:  # pragma: no cover
    nltk = None

_stopwords: set[str] | None = None
_lemmatizer = None


def ensure_nltk_data() -> None:
    """Download required NLTK corpora once (idempotent, quiet)."""
    global _NLTK_READY, _stopwords, _lemmatizer
    if _NLTK_READY:
        return
    if nltk is None:
        raise RuntimeError("NLTK is not installed.")
    for resource in ("vader_lexicon", "stopwords", "wordnet", "omw-1.4", "punkt"):
        try:
            nltk.download(resource, quiet=True)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to download NLTK resource '{resource}': {exc}")
    _stopwords = set(stopwords.words("english"))
    _lemmatizer = WordNetLemmatizer()
    _NLTK_READY = True


def tokenize(text: str) -> list[str]:
    return [t for t in WHITESPACE_RE.split(text) if t]


def clean_text(
    text: str,
    *,
    lowercase: bool = True,
    handle_urls: str = "placeholder",   # placeholder | strip | keep
    handle_mentions: str = "strip",     # strip | placeholder | keep
    handle_hashtags: str = "unwrap",    # unwrap | strip | keep
    handle_emoji: bool = True,
    remove_stopwords: bool = False,
    lemmatize: bool = False,
) -> str:
    """Normalize a social-media post while preserving signal words."""
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", str(text))

    if handle_urls == "strip":
        text = URL_RE.sub(" ", text)
    elif handle_urls == "placeholder":
        text = URL_RE.sub(" url ", text)

    if handle_mentions == "strip":
        text = MENTION_RE.sub(" ", text)
    elif handle_mentions == "placeholder":
        text = MENTION_RE.sub(" userhandle ", text)

    if handle_hashtags == "unwrap":
        text = HASHTAG_RE.sub(r"\1", text)
    elif handle_hashtags == "strip":
        text = HASHTAG_RE.sub(" ", text)

    if handle_emoji:
        text = EMOJI_RE.sub(" ", text)

    if lowercase:
        text = text.lower()

    text = NON_ALNUM_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text).strip()

    tokens = tokenize(text)
    if remove_stopwords or lemmatize:
        ensure_nltk_data()
        if remove_stopwords and _stopwords:
            tokens = [t for t in tokens if t not in _stopwords and len(t) > 1]
        if lemmatize and _lemmatizer is not None:
            tokens = [_lemmatizer.lemmatize(t) for t in tokens]
    return " ".join(tokens)


def redact_ips(text: str) -> str:
    """Replace IPv4 addresses with a redaction marker."""
    if not text:
        return text if isinstance(text, str) else ""
    return IPV4_RE.sub("[redacted-ip]", str(text))


def preprocess_options_default() -> dict:
    return {
        "lowercase": True,
        "handle_urls": "placeholder",
        "handle_mentions": "strip",
        "handle_hashtags": "unwrap",
        "handle_emoji": True,
        "remove_stopwords": False,
        "lemmatatize": False,
    }


def clean_series(values: Iterable, **kwargs) -> list[str]:
    return [clean_text(v, **kwargs) for v in values]
