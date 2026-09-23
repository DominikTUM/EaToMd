"""Small, dependency-free slug helpers shared by path and anchor generation.

Both follow GitHub's own conventions (lowercase, spaces to hyphens, strip
punctuation, de-duplicate with -1/-2/...) so that generated Markdown looks
and links exactly the way it would when previewed on GitHub or in VS Code,
without relying on a non-standard {#id} attribute extension.
"""
from __future__ import annotations

import re
from typing import Dict

_STRIP_RE = re.compile(r"[^\w\- ]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")

_WINDOWS_INVALID_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def github_slug(text: str, seen: Dict[str, int]) -> str:
    """Slugify like GitHub's Markdown renderer, de-duplicating against
    `seen` (a counter dict the caller reuses across one document/file)."""
    slug = _STRIP_RE.sub("", text.lower())
    slug = _WHITESPACE_RE.sub("-", slug.strip())
    slug = slug or "section"

    count = seen.get(slug, 0)
    seen[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count}"


def safe_folder_name(text: str, seen: Dict[str, int]) -> str:
    """Sanitize a package name into a filesystem-safe folder name, and
    de-duplicate against sibling folders already created under `seen`."""
    name = _WINDOWS_INVALID_RE.sub("", text).strip().rstrip(".")
    name = _WHITESPACE_RE.sub(" ", name) or "package"

    count = seen.get(name.lower(), 0)
    seen[name.lower()] = count + 1
    return name if count == 0 else f"{name}-{count}"
