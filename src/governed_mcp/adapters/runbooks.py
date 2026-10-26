"""Runbooks as Markdown files in a folder, with a small YAML front matter block."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
MAX_BYTES = 64 * 1024


class Runbook(BaseModel):
    slug: str
    title: str
    service: str = "general"
    tags: list[str] = Field(default_factory=list)
    body: str


def _parse(slug: str, text: str) -> Runbook:
    meta: dict[str, object] = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            loaded = yaml.safe_load(text[4:end]) or {}
            meta = loaded if isinstance(loaded, dict) else {}
            body = text[end + 4 :].lstrip("\n")
    title = str(meta.get("title") or slug.replace("-", " ").capitalize())
    tags_raw = meta.get("tags")
    tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
    return Runbook(slug=slug, title=title, service=str(meta.get("service", "general")), tags=tags, body=body)


class RunbookStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        if not self._root.is_dir():
            raise FileNotFoundError(f"runbook folder not found: {self._root}")

    def _path(self, slug: str) -> Path | None:
        if not SLUG.match(slug):
            return None
        path = (self._root / f"{slug}.md").resolve()
        # Defence in depth: the slug pattern already forbids separators and dots.
        if path.parent != self._root or not path.is_file() or path.is_symlink():
            return None
        return path

    def get(self, slug: str) -> Runbook | None:
        path = self._path(slug)
        if path is None:
            return None
        raw = path.read_bytes()[:MAX_BYTES].decode("utf-8", errors="replace")
        return _parse(slug, raw)

    def all(self) -> list[Runbook]:
        out = []
        for path in sorted(self._root.glob("*.md")):
            book = self.get(path.stem)
            if book is not None:
                out.append(book)
        return out

    def search(self, query: str) -> list[tuple[int, Runbook]]:
        terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 1]
        scored = []
        for book in self.all():
            title, tags, body = book.title.lower(), " ".join(book.tags).lower(), book.body.lower()
            score = sum(5 * title.count(t) + 3 * tags.count(t) + body.count(t) for t in terms)
            if score:
                scored.append((score, book))
        scored.sort(key=lambda s: (-s[0], s[1].slug))
        return scored
