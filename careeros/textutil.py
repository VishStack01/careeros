"""Small text helpers: HTML to text, sentence quoting, slugs."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "ul", "ol", "section", "article"}


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    """Turn posting HTML (possibly entity-escaped twice, as Greenhouse does) into plain text."""
    if not raw:
        return ""
    text = raw
    if "&lt;" in text and "<" not in text:
        text = html.unescape(text)
    p = _Stripper()
    p.feed(text)
    out = "".join(p.parts)
    out = re.sub(r"[ \t\r\f\v\xa0]+", " ", out)
    out = re.sub(r"\n\s*\n+", "\n", out)
    return out.strip()


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])|\n")


def sentences(text: str) -> list[str]:
    return [s.strip(" -•\t") for s in _SENT_SPLIT.split(text or "") if s.strip(" -•\t")]


def quote_around(text: str, start: int, end: int, limit: int = 220) -> str:
    """Return the sentence (or line) of `text` that contains text[start:end]."""
    if not text:
        return ""
    left = max(text.rfind("\n", 0, start), text.rfind(". ", 0, start))
    left = 0 if left < 0 else left + 1
    right_candidates = [i for i in (text.find("\n", end), text.find(". ", end)) if i >= 0]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    q = text[left:right].strip(" -•\t\n")
    if len(q) > limit:
        mid = (start - left)
        lo = max(0, mid - limit // 2)
        q = ("…" if lo else "") + q[lo:lo + limit].strip() + "…"
    return q


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9+#.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def slug(s: str, maxlen: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:maxlen].rstrip("-")
